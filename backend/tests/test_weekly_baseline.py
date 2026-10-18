"""Close-based portfolio baseline preserves the complete transaction ledger."""
from decimal import Decimal as D

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Account, PortfolioOpening
from app.services.portfolio import service as s


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'weekly.db'}")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        db.add_all([Account(account_id="cn"), Account(account_id="us")])
        db.commit()
        s.save_opening(db, "cn", {"effective_at": "2026-01-01T00:00:00Z", "cash": {"CNY": "100"}, "positions": []})
        opening = db.get(PortfolioOpening, "cn")
        opening.data = {**opening.data, "valuation_policy": "explicit_only"}
        db.commit()
        s.save_trade(db, {"account_id": "cn", "effective_at": "2026-01-02T02:00:00Z", "code": "CN.TEST",
            "market": "CN", "currency": "CNY", "asset_type": "etf", "side": "BUY", "quantity": "5", "price": "10"})
        s.save_opening(db, "us", {"effective_at": "2026-01-02T12:00:00Z", "cash": {"USD": "10"},
            "positions": [{"code": "US.TEST", "market": "US", "currency": "USD", "quantity": "2", "average_cost": "10"}]})
        yield db
    engine.dispose()


def close(db, day, cn="12", us="10", fx="7", *, baseline=False, estimate=False):
    return s.save_event(db, {"account_id": "cn", "kind": "valuation", "effective_at": f"2026-01-{day:02}T20:00:00Z",
        "data": {"valuation_date": f"2026-01-{day:02}", **({"performance_baseline": "all"} if baseline else {}),
            "prices": [{"code": "CN.TEST", "market": "CN", "currency": "CNY", "asset_type": "etf", "price": cn, "at": f"2026-01-{day:02}T07:00:00Z"},
                       {"code": "US.TEST", "market": "US", "currency": "USD", "price": us}],
            "fx": {"USD": {"rate": fx, "source": "user interpolation" if estimate else "user", "is_estimate": estimate}}}})


def test_close_baseline_and_later_sales_dividends_do_not_rewrite_cost_or_cash(db):
    before = s.calculate(db)["ledger"].accounts
    baseline_id = close(db, 2, baseline=True)
    result = s.overview(db)
    first = result["points"][0]
    assert first["record_id"] == baseline_id and first["valuation_date"] == "2026-01-02"
    assert D(first["total_assets"]) == 320 and D(first["profit"]) == 0 and D(first["nav"]) == 1
    assert first["quality"] == "complete"
    assert s.calculate(db)["ledger"].accounts == before
    s.save_trade(db, {"account_id": "cn", "effective_at": "2026-01-03T02:00:00Z", "code": "CN.TEST", "market": "CN",
        "currency": "CNY", "asset_type": "etf", "side": "SELL", "quantity": "2", "price": "13"})
    s.save_event(db, {"account_id": "cn", "kind": "dividend", "effective_at": "2026-01-03T08:00:00Z",
        "data": {"code": "CN.TEST", "market": "CN", "currency": "CNY", "asset_type": "etf", "amount": "3"}})
    assert s.overview(db)["points"][-1]["profit"] is None
    close(db, 4, cn="14", us="11", fx="6.9", estimate=True)
    current = s.overview(db)["current"]
    assert D(current["total_assets"]) == D("341.8")
    assert D(current["profit"]) == D("21.8") and D(current["cumulative_return"]) == D("21.8") / 320
    assert current["quality"] == "estimated" and any("估算汇率" in i for i in current["issues"])
    assert s.overview(db)["points"][0]["profit"] == "0"
    # A later cash dividend changes current assets without making up a historical close.
    s.save_event(db, {"account_id": "cn", "kind": "interest", "effective_at": "2026-01-05T08:00:00Z", "data": {"amount": "1"}})
    result = s.overview(db)
    assert D(result["current"]["profit"]) == D("22.8")
    assert result["points"][-1]["profit"] is None
    compact = s.overview(db, view="chart")
    assert compact["current"] == result["current"]
    assert compact["points"][0]["valuation_date"] == "2026-01-02"
    assert s.point_detail(db, "all", first["observed_at"], "valuation", "cn", baseline_id) == first


def test_missing_funding_boundary_blocks_returns_until_boundary_is_supplied(db):
    close(db, 2, baseline=True)
    s.save_event(db, {"account_id": "cn", "kind": "deposit", "effective_at": "2026-01-03T08:00:00Z", "data": {"amount": "100"}})
    close(db, 4)
    assert s.overview(db)["current"]["profit"] is None
    s.save_event(db, {"account_id": "cn", "kind": "valuation", "effective_at": "2026-01-03T08:00:00Z", "data": {
        "prices": [{"code": "CN.TEST", "market": "CN", "currency": "CNY", "asset_type": "etf", "price": "12"}]}})
    current = s.overview(db)["current"]
    assert D(current["profit"]) == 0 and D(current["cumulative_return"]) == 0
    assert D(current["net_flows"]) == 100
    assert any("沿用" in i for i in current["performance_issues"])


def test_baseline_requires_complete_assets_and_void_restores_legacy_restriction(db):
    with pytest.raises(ValueError, match="收益基准需要"):
        s.save_event(db, {"account_id": "cn", "kind": "valuation", "effective_at": "2026-01-02T20:00:00Z", "data": {
            "performance_baseline": "all", "fx": {"USD": "7"}}})
    assert all(p["cumulative_return"] is None for p in s.overview(db)["points"])
    rid = close(db, 2, baseline=True)
    close(db, 4)
    s.void(db, "event", rid)
    assert all(p["cumulative_return"] is None for p in s.overview(db)["points"])


def test_estimate_marker_and_actual_close_date_survive_storage(db):
    with pytest.raises(ValueError, match="同一交易日期"):
        s.save_event(db, {"account_id": "cn", "kind": "valuation", "effective_at": "2026-01-03T20:00:00Z", "data": {
            "valuation_date": "2026-01-03", "prices": [{"code": "CN.TEST", "market": "CN", "currency": "CNY", "price": "12", "at": "2026-01-02T07:00:00Z"}]}})
    close(db, 2, baseline=True)
    close(db, 4, estimate=True)
    assert s.overview(db)["current"]["positions"][0]["quote"]["at"] == "2026-01-04T07:00:00Z"
    assert s.overview(db)["current"]["positions"][1]["fx"]["is_estimate"] is True
