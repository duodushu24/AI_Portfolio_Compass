"""Carried observations, independent return requirements and repairable inputs."""
from copy import deepcopy
from decimal import Decimal as D

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Account, PortfolioOpening
from app.services.portfolio import service as s


def at(day):
    return f"2026-01-{day:02}T08:00:00Z"


def asset(code="CN.ONE", **extra):
    return {"code": code, "name": f"Sample {code}", "market": "CN", "currency": "CNY",
            "asset_type": "etf", "quantity": "5", "average_cost": "8", "price": "10", **extra}


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'valuation.db'}")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        db.add(Account(account_id="a", display_name="Sample account"))
        db.commit()
        s.save_opening(db, "a", {"effective_at": at(1), "cash": {"CNY": "100"}, "positions": [asset()]})
        yield db
    engine.dispose()


def event(db, day, kind="valuation", **data):
    return s.save_event(db, {"account_id": "a", "kind": kind, "effective_at": at(day), "data": data})


def buy(db, day, code="CN.TWO"):
    return s.save_trade(db, {**asset(code), "account_id": "a", "effective_at": at(day),
                             "side": "BUY", "quantity": "2", "price": "10"})


def test_partial_updates_reuse_unit_price_and_original_date_after_quantity_change(db):
    row = db.get(PortfolioOpening, "a")
    s.save_opening(db, "a", {**deepcopy(row.data), "positions": [asset(), asset("CN.TWO")]}, correction=True)
    original = deepcopy(db.get(PortfolioOpening, "a").data)
    buy(db, 2, "CN.ONE")
    event(db, 3, prices=[asset("CN.TWO", price="12", at=at(3))])
    result = s.overview(db)
    current = result["current"]
    one, two = current["positions"]
    assert D(one["quantity"]) == 7 and D(one["market_value"]) == 70
    assert one["quote"]["at"] == at(1) and two["quote"]["at"] == at(3)
    assert current["quality"] == "complete" and not current["issues"]
    assert all(p["profit"] is not None and p["cumulative_return"] is not None for p in result["points"])
    assert s.overview(db, view="chart")["current"] == current == result["points"][-1]
    assert db.get(PortfolioOpening, "a").data == original


def test_missing_boundary_blocks_rate_but_amount_survives_and_backfill_repairs_rate(db):
    buy(db, 2)
    event(db, 3, "deposit", amount="50")
    event(db, 4, prices=[asset("CN.TWO", price="12")])
    current = s.overview(db)["current"]
    assert D(current["total_assets"]) == 204 and D(current["net_flows"]) == 50
    assert D(current["profit"]) == 4 and current["cumulative_return"] is None
    assert D(current["cumulative_profit"]) == 14
    assert current["performance_needs"] == [{"kind": "price", "account_id": "a", "at": at(3),
        "code": "CN.TWO", "name": "Sample CN.TWO", "currency": "CNY", "unit": "share",
        "action": "valuation", "context": "cash_flow"}]
    event(db, 3, prices=[asset("CN.TWO", price="10")])
    repaired = s.overview(db)["current"]
    assert D(repaired["profit"]) == 4 and D(repaired["cumulative_return"]) == D("0.02")
    assert not repaired["performance_needs"]
    early = s.overview(db, until=at(2))["current"]
    assert early["total_assets"] is None  # The later actual quote never fills earlier days.


def test_opening_lists_exact_missing_price_fx_and_cost_without_filling_from_later_quote(db):
    s.save_opening(db, "a", {"effective_at": at(1), "cash": {"CNY": "100"}, "positions": [
        asset("US.ONE", market="US", currency="USD", price=None, average_cost=None)]}, correction=True)
    event(db, 4, prices=[asset("US.ONE", market="US", currency="USD", price="12")], fx={"USD": "7"})
    current = s.overview(db)["current"]
    assert current["profit"] is None and current["cumulative_return"] is None
    needs = current["cumulative_needs"]
    assert {(n["kind"], n["at"], n["action"]) for n in needs} == {
        ("price", at(1), "opening"), ("fx", at(1), "opening"), ("cost", at(1), "opening")}
    assert all(n["account_id"] == "a" for n in needs)
    assert next(n for n in needs if n["kind"] == "price")["name"] == "Sample US.ONE"


def test_missing_flow_fx_remains_actionable_after_current_fx_is_available(db):
    event(db, 2, "deposit", amount="10", currency="USD")
    event(db, 3, fx={"USD": "7"})
    current = s.overview(db)["current"]
    assert current["total_assets"] is not None and current["profit"] is None
    assert current["net_flows"] is None and current["cumulative_return"] is None
    assert current["performance_needs"][0]["kind"] == "fx"
    assert current["cumulative_needs"][0] == {"kind": "fx", "account_id": "a", "currency": "USD",
        "at": at(2), "action": "valuation", "context": "cash_flow"}
    event(db, 2, fx={"USD": "7"})
    assert D(s.overview(db)["current"]["profit"]) == 0
    assert D(s.overview(db)["current"]["cumulative_return"]) == 0


def test_unknown_historical_cny_cost_has_its_own_supplement_field(db):
    s.save_opening(db, "a", {"effective_at": at(1), "cash": {"CNY": "100"}, "fx": {"USD": "7"},
        "positions": [asset("US.ONE", market="US", currency="USD")]}, correction=True)
    current = s.overview(db)["current"]
    assert D(current["profit"]) == 0 and current["cumulative_profit"] is None
    assert [n["kind"] for n in current["cumulative_needs"]] == ["cost_cny"]


def test_explicit_estimate_is_available_but_keeps_estimate_identity(db):
    event(db, 2, prices=[asset(price="12", price_kind="estimate")])
    current = s.overview(db)["current"]
    assert D(current["profit"]) == 10 and current["quality"] == "estimated"
    assert current["positions"][0]["quote"]["price_kind"] == "estimate"
    assert not current["data_needs"] and any("估算" in i for i in current["issues"])


@pytest.mark.parametrize("policy", [None, "trade_observations", "explicit_only"])
def test_buy_sell_correction_and_void_preserve_market_price_and_actual_date(db, policy):
    if policy:
        row = db.get(PortfolioOpening, "a")
        row.data = {**row.data, "valuation_policy": policy}
        db.commit()
    trade_data = {**asset(), "account_id": "a", "effective_at": at(2),
                  "side": "BUY", "quantity": "2", "price": "12", "fees": "1"}
    buy_id = s.save_trade(db, trade_data)
    current = s.overview(db)["current"]
    position = current["positions"][0]
    original_quote = deepcopy(position["quote"])
    assert D(position["price"]) == 10 and original_quote["at"] == at(1)
    assert D(position["quantity"]) == 7 and D(position["cost"]) == 65
    assert D(position["market_value"]) == 70 and D(current["cash_value"]) == 75
    assert D(current["profit"]) == -5
    sell_id = s.save_trade(db, {**trade_data, "side": "SELL", "price": "14", "effective_at": at(3)})
    current = s.overview(db)["current"]
    position = current["positions"][0]
    assert position["quote"] == original_quote and D(position["market_value"]) == 50
    assert D(position["quantity"]) == 5 and D(position["cost"]) == 38
    assert D(current["cash_value"]) == 102 and D(current["profit"]) == 2
    event(db, 4, prices=[asset(price="12")])
    refreshed = s.overview(db)["current"]["positions"][0]["quote"]
    assert refreshed["at"] == at(4) and D(refreshed["price"]) == 12
    s.save_trade(db, {**trade_data, "price": "13"}, buy_id)
    current = s.overview(db)["current"]
    assert current["positions"][0]["quote"] == refreshed and D(current["cash_value"]) == 100
    s.void(db, "trade", sell_id)
    current = s.overview(db)["current"]
    assert current["positions"][0]["quote"] == refreshed
    assert D(current["positions"][0]["quantity"]) == 7 and D(current["cash_value"]) == 73
    early = s.overview(db, until=at(2))["current"]["positions"][0]
    assert D(early["price"]) == 10 and early["quote"]["at"] == at(1)


@pytest.mark.parametrize("asset_type,unit,code", [
    ("stock", "share", "CN.NEW"), ("fund", "fund_unit", "CN.FUND"),
    ("precious_metal", "gram", "CN.GOLD.SAMPLE"),
])
def test_first_buy_has_no_quote_until_separate_valuation(db, asset_type, unit, code):
    new_asset = asset(code, asset_type=asset_type, unit=unit)
    s.save_trade(db, {**new_asset, "account_id": "a", "effective_at": at(2),
                      "side": "BUY", "quantity": "2", "price": "10"})
    current = s.overview(db)["current"]
    p = next(p for p in current["positions"] if p["code"] == code)
    assert p["price"] is None and p["quote"] is None and p["market_value"] is None
    assert D(p["quantity"]) == 2 and D(p["cost"]) == 20 and D(current["cash_value"]) == 80
    assert current["total_assets"] is None and current["profit"] is None
    assert any(n["kind"] == "price" and n["code"] == code and n["at"] == at(2) for n in current["data_needs"])
    event(db, 3, prices=[{**new_asset, "price": "12"}])
    current = s.overview(db)["current"]
    p = next(p for p in current["positions"] if p["code"] == code)
    assert D(p["market_value"]) == 24 and p["quote"]["at"] == at(3)
    assert D(current["profit"]) == 4
    assert next(p for p in s.overview(db, until=at(2))["current"]["positions"] if p["code"] == code)["quote"] is None


def test_other_account_trade_does_not_change_shared_quote_or_emit_quote_point(db):
    db.add(Account(account_id="b")); db.commit()
    s.save_opening(db, "b", {"effective_at": at(1), "cash": {"CNY": "100"}, "positions": []})
    before = s.overview(db, "a")
    s.save_trade(db, {**asset(), "account_id": "b", "effective_at": at(2),
                      "side": "BUY", "quantity": "2", "price": "15"})
    after = s.overview(db, "a")
    assert after["points"] == before["points"] and after["current"] == before["current"]
    b = s.overview(db, "b")["current"]["positions"][0]
    assert D(b["price"]) == 10 and b["quote"]["at"] == at(1)


def test_full_sale_without_any_market_quote_restores_amount_and_return_immediately(db):
    buy(db, 2)
    assert s.overview(db)["current"]["total_assets"] is None
    s.save_trade(db, {**asset("CN.TWO"), "account_id": "a", "effective_at": at(3),
                      "side": "SELL", "quantity": "2", "price": "12"})
    current = s.overview(db)["current"]
    closed = next(p for p in current["positions"] if p["code"] == "CN.TWO")
    assert closed["quote"] is None and closed["price"] is None and D(closed["realized"]) == 4
    assert D(current["total_assets"]) == 154 and D(current["profit"]) == 4
    assert abs(D(current["cumulative_return"]) - D(4) / 150) < D("1e-25")
    assert not current["data_needs"]
