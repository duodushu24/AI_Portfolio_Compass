"""P-011: synthetic money, in-memory SQLite, stubbed SDK; live probes run separately."""
from datetime import datetime, timedelta, timezone
import subprocess

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Account, DataProviderConfig, PortfolioEvent, QuoteSummary, NewsItem
from app.services import data_sources as ds, providers
from app.services.sync import pull_account_market_data
from app.services.portfolio import service as ledger
from app.adapters.akshare_adapter import AKShareAdapter

T = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)


def asset(**kw):
    return {"code": "CN.000001", "name": "示例股票", "market": "CN", "asset_type": "stock", "currency": "CNY", "unit": "share", **kw}


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as session:
        session.add_all([Account(account_id="a", base_currency="CNY", import_mode="local"), Account(account_id="b", base_currency="CNY")])
        session.commit()
        yield session
    engine.dispose()


def opening(db, aid="a", positions=None):
    ledger.save_opening(db, aid, {"effective_at": T.isoformat(), "cash": {"CNY": "1000"}, "positions": positions if positions is not None else [asset(quantity="10", average_cost="8", price="10")]})


def fake_quote(a, price=11):
    return {"status": "available", "message": "示例有效价格", "quotes": [{"code": a["code"], "provider": "akshare", "market": "CN", "current_price": price,
        "quote_time": T + timedelta(days=1), "is_delayed": True, "price_kind": "price", "currency": a["currency"], "unit": a["unit"],
        "price_date": "2026-01-02", "time_precision": "day", "fetched_at": datetime.now(timezone.utc).isoformat()}]}


def patch_adapter(monkeypatch, handler):
    class Adapter:
        def fetch(self, a, kind):
            return handler(a, kind)
    monkeypatch.setattr(providers, "_akshare_factory", lambda _: Adapter())


def test_default_is_free_and_catalog_has_only_real_adapters(db):
    c = ds.catalog(db)["items"]
    assert {p["id"] for p in c} == {"akshare", "futu", "marketaux"}
    assert next(p for p in c if p["id"] == "akshare")["config"]["enabled"] is True
    assert next(p for p in c if p["id"] == "futu")["group"] == "paid"
    assert next(p for p in c if p["id"] == "futu")["config"]["enabled"] is False
    assert ds.choose(db, "quote", "CN").name == "akshare"
    assert ds.choose(db, "quote", "US") is None  # No hidden paid fallback.


def test_secret_save_mask_keep_clear_and_validation(db):
    result = ds.save_config(db, "marketaux", {"api_token": "synthetic-private-token", "enabled": True})
    assert "synthetic-private-token" not in str(result)
    ds.save_config(db, "marketaux", {"api_token": ""})
    assert db.get(DataProviderConfig, "marketaux").data["api_token"] == "synthetic-private-token"
    ds.save_config(db, "marketaux", {"api_token": None})
    assert ds.availability(db, providers.provider_registry().get("marketaux"))[0] == "not_configured"
    for payload in [{"port": 0}, {"enabled": "yes"}, {"host": {"bad": "shape"}}]:
        with pytest.raises(ValueError):
            ds.save_config(db, "futu", payload)


def test_paid_opt_in_and_legacy_account_override(db):
    db.get(Account, "a").market_data_provider = "futu"; db.commit()
    assert ds.config(db, providers.provider_registry().get("futu"))["enabled"] is True
    assert ds.choose(db, "quote", "CN", "futu").name == "futu"
    ds.save_config(db, "futu", {"enabled": False})
    assert ds.availability(db, ds.choose(db, "quote", "CN", "futu"))[0] == "disabled"
    assert ds.choose(db, "quote", "CN").name == "akshare"


def test_probe_really_calls_adapter_but_never_writes_prices(db, monkeypatch):
    calls = []
    patch_adapter(monkeypatch, lambda a, k: calls.append((a["code"], k)) or fake_quote(a))
    result = ds.probe(db, "akshare")
    assert result["status"] == "available" and calls == [("CN.000001", "quote")]
    assert db.scalar(select(func.count()).select_from(QuoteSummary)) == 0
    assert db.scalar(select(func.count()).select_from(PortfolioEvent)) == 0
    ds.save_config(db, "akshare", {"enabled": False})
    ds.probe(db, "akshare")
    assert len(calls) == 1


def test_manual_account_price_update_is_shared_idempotent_and_not_estimated(db, monkeypatch):
    opening(db); opening(db, "b")
    calls = []
    patch_adapter(monkeypatch, lambda a, k: calls.append(a["code"]) or fake_quote(a))
    result = pull_account_market_data(db, db.get(Account, "a"), "quote")
    assert result["inserted_count"] == 1 and result["status"] == "success"
    current = ledger.calculate(db)["current"]
    assert all(p["price"] == 11 and p["cost"] == 80 and p["quantity"] == 10 for p in current["positions"])
    assert current["cash_value"] == 2000
    assert all(p["quote"]["price_kind"] == "price" for p in current["positions"])
    pull_account_market_data(db, db.get(Account, "b"), "quote")
    assert calls == ["CN.000001"]
    assert db.scalar(select(func.count()).select_from(PortfolioEvent)) == 1
    assert db.scalar(select(QuoteSummary)).metadata_json["price_date"] == "2026-01-02"


def test_partial_failure_keeps_old_price_and_does_not_change_cash_or_cost(db, monkeypatch):
    opening(db, positions=[asset(quantity="10", average_cost="8", price="10"), asset(code="CN.600000", quantity="5", average_cost="6", price="7")])
    patch_adapter(monkeypatch, lambda a, k: fake_quote(a) if a["code"] == "CN.000001" else {"status": "timeout", "message": "请求超时"})
    result = pull_account_market_data(db, db.get(Account, "a"), "quote")
    assert result["status"] == "partial" and result["failures"][0]["code"] == "CN.600000"
    p = {p["code"]: p for p in ledger.calculate(db)["current"]["positions"]}
    assert p["CN.000001"]["price"] == 11 and p["CN.600000"]["price"] == 7
    assert p["CN.600000"]["cost"] == 30 and ledger.calculate(db)["current"]["cash_value"] == 1000


def test_unsupported_market_cannot_silently_connect_futu(db, monkeypatch):
    opening(db, positions=[asset(code="US.AAPL", market="US", currency="USD", quantity="1", average_cost="10", price="10")],)
    monkeypatch.setattr(providers, "_futu_factory", lambda _: pytest.fail("must not call paid source"))
    result = pull_account_market_data(db, db.get(Account, "a"), "quote")
    assert result["failures"][0]["status"] == "unsupported"


def test_adapter_uses_completed_day_unadjusted_prices_and_preserves_unit(monkeypatch):
    adapter = AKShareAdapter()
    calls = []
    def load(action, **kw):
        calls.append((action, kw))
        return [{"date": "2026-01-02", "close": 11}, {"date": "2026-01-03", "close": 12}]
    monkeypatch.setattr(adapter, "_call", load)
    result = adapter.fetch(asset(), "quote", datetime(2026, 1, 3, 1, tzinfo=timezone.utc))
    assert result["quotes"][0]["price_date"] == "2026-01-02"
    assert result["quotes"][0]["current_price"] == 11 and calls[0][1]["symbol"] == "sz000001"
    assert result["quotes"][0]["time_precision"] == "day"


def test_bond_fund_routes_to_unit_nav_without_changing_ledger_type(monkeypatch):
    adapter = AKShareAdapter()
    def load(action, **kw):
        if action == "fund_codes": return [{"基金代码": "021151"}]
        assert action == "fund"
        return [{"净值日期": "2026-01-02", "单位净值": 1.1, "累计净值": 8.8}]
    monkeypatch.setattr(adapter, "_call", load)
    result = adapter.fetch(asset(code="CN.021151", asset_type="bond"), "quote", T + timedelta(days=3))
    assert result["quotes"][0]["price_kind"] == "nav" and result["quotes"][0]["current_price"] == 1.1
    assert result["quotes"][0]["unit"] == "share"


def test_news_dedup_timestamp_and_unsupported_asset_types(db, monkeypatch):
    opening(db)
    adapter = AKShareAdapter()
    monkeypatch.setattr(adapter, "_call", lambda *a, **k: [{"新闻标题": "示例新闻", "新闻链接": "https://example.com/item", "发布时间": "2026-01-02 16:00:00", "文章来源": "示例来源"}])
    one = adapter.fetch(asset(), "news", T + timedelta(days=3))
    patch_adapter(monkeypatch, lambda a, k: one)
    pull_account_market_data(db, db.get(Account, "a"), "news")
    pull_account_market_data(db, db.get(Account, "a"), "news")
    assert db.scalar(select(func.count()).select_from(NewsItem)) == 1
    assert adapter.fetch(asset(asset_type="etf"), "news", T)["status"] == "unsupported"


def test_timeout_and_missing_dependency_are_explicit(db, monkeypatch):
    patch_adapter(monkeypatch, lambda *_: (_ for _ in ()).throw(subprocess.TimeoutExpired("sdk", 10)))
    assert ds.fetch(db, ds.choose(db, "quote", "CN"), asset(), "quote")["status"] == "timeout"
    monkeypatch.setattr(ds, "find_spec", lambda _: None)
    assert ds.availability(db, ds.choose(db, "quote", "CN"))[0] == "dependency_missing"


def test_new_provider_is_registered_once_and_appears_in_generic_catalog(db, monkeypatch):
    registry = providers.provider_registry()
    registry.register(providers.StaticProvider("sample_paid", "示例付费接口", ("quote",), ("US",),
        factory=lambda _: object(), fields=({"key": "api_token", "label": "示例 Key", "type": "secret"},)))
    monkeypatch.setattr(ds, "provider_registry", lambda: registry)
    sample = next(p for p in ds.catalog(db)["items"] if p["id"] == "sample_paid")
    assert sample["group"] == "paid" and sample["fields"][0]["key"] == "api_token"


def test_disabled_futu_health_never_probes_opend(db, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "_opend_health_with_timeout", lambda *_: pytest.fail("must not connect OpenD"))
    result = main.health(db)
    assert result["futu"]["enabled"] is False and not result["futu"]["opend_connected"]


def test_disabled_futu_sync_and_review_never_connect(db, monkeypatch):
    from app.services.sync import run_manual_sync
    from app.services.trade_review import _price_after
    from app.services.ai_decision_cards import _fetch_technical_summaries
    monkeypatch.setattr(providers, "_futu_factory", lambda _: pytest.fail("must not connect OpenD"))
    assert run_manual_sync(db).status == "已跳过"
    assert _price_after(db, "US.AAPL", T, 1, fetch_market_data=True) is None
    assert _fetch_technical_summaries(["US.AAPL"], db)["US.AAPL"]["daily"]["status"] == "missing"


def test_saved_selection_overrides_existing_environment(db, monkeypatch):
    from copy import copy
    settings = copy(ds.get_settings())
    settings.news_provider_priority = "marketaux"
    settings.marketaux_api_token = "synthetic-environment-token"
    monkeypatch.setattr(ds, "get_settings", lambda: settings)
    assert ds.choose(db, "news", "US").name == "marketaux"
    ds.save_config(db, "akshare", {"preferred_news": True})
    assert ds.choose(db, "news", "CN").name == "akshare"
    ds.save_config(db, "marketaux", {"enabled": False})
    assert ds.choose(db, "news", "US") is None


def test_router_handlers_validate_and_persist_only_configuration(db, monkeypatch):
    from fastapi import HTTPException
    from app.routers import data_sources as routes
    patch_adapter(monkeypatch, lambda a, k: fake_quote(a))
    assert routes.catalog(db)["items"]
    assert routes.configure("akshare", {"timeout_seconds": 15}, db)["items"]
    assert routes.check("akshare", {"data_type": "quote"}, db)["status"] == "available"
    assert db.scalar(select(func.count()).select_from(PortfolioEvent)) == 0
    with pytest.raises(HTTPException) as error:
        routes.configure("marketaux", {"preferred_quote": True}, db)
    assert error.value.status_code == 400


def test_currency_and_unit_mismatch_does_not_write_foreign_or_gram_price(monkeypatch):
    adapter = AKShareAdapter()
    monkeypatch.setattr(adapter, "_call", lambda *_a, **_k: pytest.fail("invalid identity must not fetch"))
    assert adapter.fetch(asset(currency="USD"), "quote")["status"] == "conflict"
    assert adapter.fetch(asset(unit="gram"), "quote")["status"] == "conflict"


def test_conflicting_price_rolls_back_only_that_asset(db, monkeypatch):
    from app.services.sync import _persist_quote_rows
    opening(db)
    _persist_quote_rows(db, "first", fake_quote(asset())["quotes"]); db.commit()
    before = db.scalar(select(func.count()).select_from(PortfolioEvent))
    patch_adapter(monkeypatch, lambda a,k: fake_quote(a, 12))
    # Remove the short cache marker so a conflicting upstream observation is checked.
    row = db.scalar(select(QuoteSummary)); row.metadata_json = {**row.metadata_json, "fetched_at": "2026-01-02T00:00:00Z"}; db.commit()
    result = pull_account_market_data(db, db.get(Account,"a"), "quote")
    assert result["failures"][0]["status"] == "conflict"
    assert db.scalar(select(func.count()).select_from(PortfolioEvent)) == before
    assert ledger.calculate(db)["current"]["positions"][0]["price"] == 11


def test_cached_daily_bars_work_for_review_without_futu(db, monkeypatch):
    from app.models import KlineSnapshot
    from app.services.trade_review import _price_after
    db.add(KlineSnapshot(code="CN.000001",provider="akshare",period="K_DAY",time_key="2026-01-02",close=11,snapshot_time=T,sync_id="synthetic")); db.commit()
    monkeypatch.setattr(providers,"_futu_factory",lambda _: pytest.fail("cached data needs no OpenD"))
    assert _price_after(db,"CN.000001",T,1,fetch_market_data=True) == 11


def test_bad_probe_is_not_available_and_agent_reads_do_not_write(db, monkeypatch):
    from app.services.profile_agent_tools import get_latest_quotes, get_recent_news
    patch_adapter(monkeypatch, lambda a,k: fake_quote(a, 0))
    assert ds.probe(db, "akshare")["status"] == "invalid_data"
    assert get_recent_news(db, "a", {"codes":["CN.000001"]}, {})["status"] == "empty"
    from app.services.sync import _persist_quote_rows
    opening(db)
    _persist_quote_rows(db, "synthetic", fake_quote(asset())["quotes"]); db.commit()
    before = db.scalar(select(func.count()).select_from(PortfolioEvent))
    result = get_latest_quotes(db, "a", {"codes":["CN.000001"]}, {})
    assert result["status"] == "ok" and result["items"][0]["source"] == "akshare"
    assert db.scalar(select(func.count()).select_from(PortfolioEvent)) == before
