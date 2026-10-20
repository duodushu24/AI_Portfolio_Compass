"""Legacy baseline gaps are readable and repairable without execution quotes."""
from copy import deepcopy
from decimal import Decimal as D

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Account, Deal, PortfolioEvent
from app.services.portfolio import service as s


def at(day):
    return f"2026-01-{day:02}T20:00:00Z"


ASSET = {"code": "CN.SAMPLE", "name": "Sample asset", "market": "CN", "currency": "CNY", "asset_type": "stock", "unit": "share"}


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'baseline.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        db.add(Account(account_id="a", display_name="Sample account")); db.commit()
        s.save_opening(db, "a", {"effective_at": at(1), "cash": {"CNY": "100"}, "positions": []})
        s.save_trade(db, {**ASSET, "account_id": "a", "effective_at": at(2), "side": "BUY", "quantity": "5", "price": "10"})
        # A record accepted by the old execution-price policy, not a new write.
        legacy = PortfolioEvent(account_id="a", kind="valuation", effective_at=s.instant(at(3)),
            data={"performance_baseline": "all", "valuation_date": "2026-01-03", "prices": [],
                  "fx": {"USD": {"rate": "7", "at": at(3), "source": "saved"}}}, is_void=False, created_at=s.instant(at(3)))
        db.add(legacy); db.commit()
        yield db, legacy.id
    engine.dispose()


def quote(db, day, price="12", *, actual=None):
    return s.save_event(db, {"account_id": "a", "kind": "valuation", "effective_at": at(day),
        "data": {"prices": [{**ASSET, "price": price, "at": actual or at(day)}]}})


def test_missing_legacy_baseline_keeps_current_assets_and_does_not_silently_rebase(db):
    db, rid = db
    original = deepcopy(db.get(PortfolioEvent, rid).data)
    quote(db, 4)
    s.save_event(db, {"account_id": "a", "kind": "deposit", "effective_at": at(5), "data": {"amount": "20"}})
    result = s.overview(db)
    current = result["current"]
    assert D(current["total_assets"]) == 130 and D(current["cash_value"]) == 70
    assert D(current["positions"][0]["market_value"]) == 60
    assert D(current["net_flows"]) == 20 and D(current["cumulative_profit"]) == 10
    assert current["profit"] is None and current["cumulative_return"] is None and current["opening_assets"] is None
    assert current["performance_baseline"] == {"at": at(3), "valuation_date": "2026-01-03", "record_id": rid, "status": "missing"}
    assert current["performance_needs"] == [{"kind": "price", "account_id": "a", "at": at(3),
        "code": ASSET["code"], "name": ASSET["name"], "currency": "CNY", "unit": "share",
        "action": "valuation", "context": "baseline", "valuation_date": "2026-01-03"}]
    assert all(p["profit"] is None and p["cumulative_return"] is None for p in result["points"])
    assert result["points"][0]["record_id"] == rid
    assert s.overview(db, view="chart")["current"] == current
    assert s.point_detail(db, "all", at(3), "valuation", "a", rid) == result["points"][0]
    assert db.get(PortfolioEvent, rid).data == original and not db.dirty and not db.new


@pytest.mark.parametrize("sold", [False, True])
def test_later_record_at_same_baseline_time_repairs_even_an_already_sold_asset(db, sold):
    db, rid = db
    quote(db, 4)
    if sold:
        s.save_trade(db, {**ASSET, "account_id": "a", "effective_at": at(5), "side": "SELL", "quantity": "5", "price": "13"})
    before = s.overview(db)["current"]
    assert before["performance_needs"][0]["at"] == at(3)
    historical = s.overview(db, "a", until=at(3))["current"]
    assert D(historical["positions"][0]["quantity"]) == 5
    backfill = quote(db, 3, "10", actual="2026-01-03T07:00:00Z")
    assert backfill > rid  # Original baseline sorts first by record ID.
    after = s.overview(db)["current"]
    assert D(after["opening_assets"]) == 100 and D(after["profit"]) == (15 if sold else 10)
    assert D(after["cumulative_return"]) == (D("0.15") if sold else D("0.1"))
    assert after["performance_baseline"]["status"] == "complete" and not after["performance_needs"]
    assert after["cash"] == before["cash"]
    assert D(after["positions"][0]["quantity"]) == (0 if sold else 5)
    assert db.get(PortfolioEvent, rid).data["prices"] == []
    s.void(db, "event", backfill)
    assert s.overview(db)["current"]["performance_baseline"]["status"] == "missing"
    assert s.overview(db)["current"]["profit"] is None


def test_same_time_backfill_correction_and_void_follow_record_order(db):
    db, _ = db
    quote(db, 4)
    first = quote(db, 3, "10")
    second = quote(db, 3, "11")
    assert D(s.overview(db)["current"]["opening_assets"]) == 105
    s.save_event(db, {"account_id": "a", "kind": "valuation", "effective_at": at(3),
        "data": {"prices": [{**ASSET, "price": "9"}]}}, second)
    assert D(s.overview(db)["current"]["opening_assets"]) == 95
    s.void(db, "event", second)
    assert D(s.overview(db)["current"]["opening_assets"]) == 100
    assert db.get(PortfolioEvent, first).is_void is False


def test_new_incomplete_baseline_is_rejected_without_blocking_other_repairs(db):
    db, rid = db
    with pytest.raises(ValueError, match="收益基准需要"):
        s.save_event(db, {"account_id": "a", "kind": "valuation", "effective_at": at(4),
            "data": {"performance_baseline": "all", "fx": {"USD": "7"}}})
    assert len(list(db.scalars(select(PortfolioEvent)))) == 1
    assert s.overview(db)["current"]["performance_baseline"]["record_id"] == rid
    quote(db, 4)
    assert s.overview(db)["current"]["total_assets"] is not None


def test_nonpositive_legacy_baseline_waits_for_an_explicit_valid_baseline(db):
    db, rid = db
    db.delete(db.scalar(select(Deal)))
    s.save_opening(db, "a", {"effective_at": at(1), "cash": {"CNY": "0"}, "positions": []}, correction=True)
    s.save_event(db, {"account_id": "a", "kind": "deposit", "effective_at": at(4), "data": {"amount": "100"}})
    current = s.overview(db)["current"]
    assert D(current["total_assets"]) == 100 and current["opening_assets"] is None
    assert current["performance_baseline"]["status"] == "nonpositive" and current["cumulative_return"] is None
    assert any("净资产须为正" in text for text in current["performance_issues"])
    new = s.save_event(db, {"account_id": "a", "kind": "valuation", "effective_at": at(5),
        "data": {"performance_baseline": "all", "fx": {"USD": "7"}}})
    current = s.overview(db)["current"]
    assert current["performance_baseline"]["record_id"] == new != rid
    assert D(current["opening_assets"]) == 100 and D(current["profit"]) == 0


def test_missing_baseline_fx_remains_missing_until_historical_fx_is_supplied(db):
    db, rid = db
    db.delete(db.scalar(select(Deal)))
    s.save_opening(db, "a", {"effective_at": at(1), "cash": {"USD": "100"}, "positions": []}, correction=True)
    legacy = db.get(PortfolioEvent, rid)
    legacy.data = {**legacy.data, "fx": {}, "prices": [{**ASSET, "price": "1", "at": at(3)}]}
    db.commit()
    s.save_event(db, {"account_id": "a", "kind": "valuation", "effective_at": at(4), "data": {"fx": {"USD": "7"}}})
    current = s.overview(db)["current"]
    assert D(current["total_assets"]) == 700 and current["profit"] is None
    assert current["performance_needs"][0]["kind"] == "fx" and current["performance_needs"][0]["context"] == "baseline"
    s.save_event(db, {"account_id": "a", "kind": "valuation", "effective_at": at(3), "data": {"fx": {"USD": "7"}}})
    assert D(s.overview(db)["current"]["opening_assets"]) == 700
    assert D(s.overview(db)["current"]["cumulative_return"]) == 0


@pytest.mark.parametrize("current_quoted", [False, True])
def test_public_read_routes_and_backfill_work_with_a_legacy_baseline_gap(db, monkeypatch, current_quoted):
    from fastapi.testclient import TestClient
    from app.database import get_db
    from app.main import app
    import app.main as main
    import app.services.sync as sync
    db, _ = db
    if current_quoted:
        quote(db, 4)
    for name in ("_create_profile", "_create_review", "_mark_freshness_states", "refresh_trade_reviews"):
        monkeypatch.setattr(sync, name, lambda *args: None)
    monkeypatch.setattr(main, "fx_display_rates", lambda *args: ({"CNY": 1}, {}))
    def isolated():
        with Session(db.get_bind(), autoflush=False) as reader:
            yield reader
    app.dependency_overrides[get_db] = isolated
    client = TestClient(app)
    try:
        for path in ("/api/accounts", "/api/positions?account_id=all", "/api/dashboard?account_id=all", "/api/review/trades?account_id=all"):
            response = client.get(path)
            assert response.status_code == 200, (path, response.text)
        overview = client.get("/api/portfolio/overview?account_id=all&view=chart").json()
        assert len(overview["holdings"]) == 1 and overview["current"]["profit"] is None
        response = client.post("/api/portfolio/events", json={"account_id": "a", "kind": "valuation", "effective_at": at(3),
            "data": {"prices": [{**ASSET, "price": "10"}]}})
        assert response.status_code == 200, response.text
        after = client.get("/api/portfolio/overview?account_id=all&view=current").json()["current"]
        assert D(after["profit"]) == (10 if current_quoted else 0) and not after["performance_needs"]
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
