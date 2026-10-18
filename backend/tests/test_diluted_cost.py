"""Single diluted-cost contract; synthetic data, no live providers or daily prices."""
from decimal import Decimal as D

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Account, Deal, PortfolioEvent
from app.services.portfolio import service as s


def at(day):
    return f"2026-01-{day:02}T07:00:00Z"


def asset(**kw):
    return {"code": "CN.SYNTH", "name": "虚构资产", "market": "CN", "asset_type": "etf", "currency": "CNY", "unit": "share", **kw}


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'diluted.db'}")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as session:
        session.add_all([Account(account_id="a", display_name="虚构账户"), Account(account_id="b", display_name="虚构转入")])
        session.commit()
        s.save_opening(session, "a", {"effective_at": at(1), "positions": [], "cash": {"CNY": "2000", "USD": "1000"},
            "fx": {"USD": {"rate": "7", "at": at(1)}}})
        yield session
    engine.dispose()


def trade(db, day, side, q, price, fees="0", **kw):
    return s.save_trade(db, {**asset(), "account_id": "a", "effective_at": at(day), "side": side,
                           "quantity": q, "price": price, "fees": fees, **kw})


def dividend(db, day, amount, **kw):
    return s.save_event(db, {"account_id": "a", "kind": "dividend", "effective_at": at(day),
        "data": {**asset(), "amount": amount, **kw}})


def position(db):
    return s.calculate(db, "a")["current"]["positions"][0]


def test_partial_sale_dividend_close_and_same_day_rebuy(db):
    trade(db, 2, "BUY", "100", "10", "2")
    trade(db, 3, "SELL", "40", "12", "1")
    p = position(db)
    assert p["cost"] == 523 and p["diluted_cost"] == D(523) / 60
    assert p["floating"] == 197 and p["realized"] == 0
    assert s.closed_positions(db, "a")["summary"]["count"] == 0
    before = s.calculate(db, "a")["current"]
    dividend(db, 4, "30")
    p = position(db)
    assert p["cost"] == 493 and p["floating"] == 227 and p["dividends"] == 30
    assert s.calculate(db, "a")["current"]["total_assets"] == before["total_assets"] + 30
    trade(db, 5, "SELL", "60", "11", "2")
    c = s.closed_positions(db, "a")["items"][0]
    assert D(c["trading_profit"]) == 135 and D(c["dividends"]) == 30 and D(c["realized"]) == 165
    assert D(c["return"]) == D(165) / 1002
    # The same day is still a new phase, even without a midnight boundary.
    s.save_trade(db, {**asset(), "account_id": "a", "effective_at": "2026-01-05T07:01:00Z", "side": "BUY", "quantity": "10", "price": "20"})
    p = position(db)
    assert p["cycle"] == 2 and p["cost"] == 200 and p["dividends"] == 0
    assert p["realized"] == 165 and len(p["closed_cycles"]) == 1


def test_late_dividend_updates_original_phase_once_and_wrong_phase_rolls_back(db):
    trade(db, 2, "BUY", "10", "10")
    trade(db, 3, "SELL", "10", "11")
    trade(db, 4, "BUY", "5", "20")
    original_cash = s.calculate(db, "a")["ledger"].accounts["a"]["cash"]["CNY"]
    with pytest.raises(ValueError, match="持有阶段"):
        dividend(db, 5, "7")
    assert s.calculate(db, "a")["ledger"].accounts["a"]["cash"]["CNY"] == original_cash
    event_id = dividend(db, 5, "7", cycle=1)
    p = position(db)
    assert p["cost"] == 100 and p["dividends"] == 0 and p["realized"] == 17
    assert p["closed_cycles"][0]["dividends"] == 7
    assert s.calculate(db, "a")["ledger"].accounts["a"]["cash"]["CNY"] == original_cash + 7
    # Editing the same fact replays cash rather than appending another payment.
    s.save_event(db, {"account_id": "a", "kind": "dividend", "effective_at": at(5), "data": {**asset(), "amount": "9", "cycle": 1}}, event_id)
    assert position(db)["realized"] == 19
    assert s.calculate(db, "a")["ledger"].accounts["a"]["cash"]["CNY"] == original_cash + 9
    assert len(list(db.scalars(select(PortfolioEvent)))) == 1


@pytest.mark.parametrize("sale_price,net_cost", [("3", "-5"), ("2", "0")])
def test_negative_and_zero_net_cost_are_valid_without_false_percentages(db, sale_price, net_cost):
    trade(db, 2, "BUY", "10", "1")
    trade(db, 3, "SELL", "5", sale_price)
    p = position(db)
    assert p["cost"] == D(net_cost) and p["holding_return"] is None and p["realized"] == 0
    assert p["diluted_cost"] == D(net_cost) / 5
    trade(db, 4, "SELL", "5", "1")
    assert position(db)["closed_cycles"][0]["realized"] == D(sale_price) * 5 - 5


def test_foreign_closed_profit_uses_recorded_cash_flow_rates(db):
    foreign = {"code": "US.SYNTH", "market": "US", "currency": "USD"}
    trade(db, 2, "BUY", "10", "10", **foreign, fx={"USD": {"rate": "7", "at": at(2)}})
    trade(db, 3, "SELL", "5", "12", **foreign, fx={"USD": {"rate": "8", "at": at(3)}})
    trade(db, 4, "SELL", "5", "11", **foreign, fx={"USD": {"rate": "9", "at": at(4)}})
    dividend(db, 5, "2", **foreign, cycle=1, fx={"USD": {"rate": "10", "at": at(5)}})
    c = s.closed_positions(db, "a")["items"][0]
    assert D(c["realized"]) == 17 and D(c["realized_cny"]) == 295


def test_transfer_preserves_net_cost_without_closing_a_phase(db):
    s.save_opening(db, "b", {"effective_at": at(1), "positions": [], "cash": {"CNY": "0"}})
    trade(db, 2, "BUY", "10", "10")
    trade(db, 3, "SELL", "2", "20")
    s.save_event(db, {"account_id": "a", "kind": "position_transfer", "effective_at": at(4),
        "data": {**asset(), "quantity": "4", "to_account_id": "b"}})
    a = s.calculate(db, "a")["ledger"].accounts["a"]["positions"][("CN.SYNTH", "CNY", "share")]
    b = s.calculate(db, "b")["ledger"].accounts["b"]["positions"][("CN.SYNTH", "CNY", "share")]
    assert a["cost"] == b["cost"] == 30 and not a["closed_cycles"] and not b["closed_cycles"]
    assert a["realized"] == b["realized"] == 0


def test_weekly_total_return_is_cash_based_and_has_no_dividend_double_count(db):
    trade(db, 2, "BUY", "100", "10")
    s.save_event(db, {"account_id": "a", "kind": "valuation", "effective_at": at(7), "data": {"prices": [{**asset(), "price": "9", "at": at(7)}]}})
    before = s.calculate(db, "a")["current"]["total_assets"]
    dividend(db, 8, "100", cycle=1)
    after = s.calculate(db, "a")["current"]
    assert after["total_assets"] == before + 100
    assert after["profit"] == 0  # 100 price loss + 100 cash dividend.
    assert after["positions"][0]["floating"] == 0
    assert after["positions"][0]["dividends"] == 100
    assert after["external_flow"] == 0 and after["units"] == 9000


def test_negative_opening_basis_and_legacy_unknown_basis(db):
    s.save_opening(db, "b", {"effective_at": at(1), "cash": {"CNY": "0"},
        "positions": [{**asset(), "quantity": "2", "average_cost": "-3", "price": "10"}]})
    assert s.calculate(db, "b")["current"]["positions"][0]["cost"] == -6
    from app.services.portfolio.ledger import Ledger
    ledger = Ledger()
    ledger.open("old", {"effective_at": at(1), "cash": {"CNY": "0"},
                        "positions": [{**asset(), "quantity": "2", "average_cost": "3"}]})
    assert ledger.accounts["old"]["positions"][("CN.SYNTH", "CNY", "share")]["cost"] is None


def test_dividend_correction_void_and_quote_do_not_double_count(db):
    trade(db, 2, "BUY", "10", "10")
    before = s.calculate(db, "a")["current"]
    event_id = dividend(db, 3, "12")
    p = position(db)
    assert p["quantity"] == 10 and p["cost"] == 88 and p["floating"] == 12
    assert p["price"] == before["positions"][0]["price"]
    s.save_event(db, {"account_id": "a", "kind": "dividend", "effective_at": at(3),
        "data": {**asset(), "amount": "15"}}, event_id)
    assert position(db)["cost"] == 85
    assert s.calculate(db, "a")["current"]["cash_value"] == before["cash_value"] + 15
    s.save_event(db, {"account_id": "a", "kind": "valuation", "effective_at": at(4),
        "data": {"prices": [{**asset(), "price": "9", "at": at(4)}]}})
    assert position(db)["cost"] == 85 and position(db)["floating"] == 5
    s.void(db, "event", event_id)
    assert position(db)["cost"] == 100 and position(db)["floating"] == -10
    assert s.calculate(db, "a")["current"]["cash_value"] == before["cash_value"]


def test_foreign_dividend_before_close_and_negative_cost(db):
    foreign = {"code": "US.SYNTH", "market": "US", "currency": "USD"}
    trade(db, 2, "BUY", "2", "10", **foreign, fx={"USD": {"rate": "7", "at": at(2)}})
    dividend(db, 3, "25", **foreign, fx={"USD": {"rate": "8", "at": at(3)}})
    p = position(db)
    assert p["cost"] == -5 and p["cost_cny"] == -60 and p["holding_return"] is None
    trade(db, 4, "SELL", "2", "9", **foreign, fx={"USD": {"rate": "9", "at": at(4)}})
    c = s.closed_positions(db, "a")["items"][0]
    assert D(c["trading_profit"]) == -2 and D(c["dividends"]) == 25
    assert D(c["realized"]) == 23 and D(c["realized_cny"]) == 222


def test_dividend_transfer_carries_discounted_cost_without_extra_cash(db):
    s.save_opening(db, "b", {"effective_at": at(1), "positions": [], "cash": {"CNY": "0"}})
    trade(db, 2, "BUY", "10", "10")
    dividend(db, 3, "20")
    cash = s.calculate(db)["current"]["cash_value"]
    s.save_event(db, {"account_id": "a", "kind": "position_transfer", "effective_at": at(4),
        "data": {**asset(), "quantity": "5", "to_account_id": "b"}})
    current = s.calculate(db)["current"]
    assert current["cash_value"] == cash
    assert [p["cost"] for p in current["positions"]] == [40, 40]
    trade(db, 5, "SELL", "5", "10")
    s.save_trade(db, {**asset(), "account_id": "b", "effective_at": at(5), "side": "SELL", "quantity": "5", "price": "10"})
    assert D(s.closed_positions(db)["summary"]["realized_cny"]) == 20
