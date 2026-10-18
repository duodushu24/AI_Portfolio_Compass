"""Financial contracts for as-of FX, explicit overrides and retrospective corrections."""
from copy import deepcopy
from decimal import Decimal as D

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Account, Deal
from app.services.portfolio import service as s


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fx.db'}")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        db.add(Account(account_id="a"))
        db.commit()
        s.save_opening(db, "a", {"effective_at": "2026-01-01T00:00:00Z", "positions": [], "cash": {"USD": "1000"},
            "fx": {"USD": {"rate": "7", "at": "2026-01-01T00:00:00Z", "source": "confirmed opening"}}})
        yield db
    engine.dispose()


def trade(db, day, side, *, price="10", hour="12", fx=None):
    return s.save_trade(db, {"account_id": "a", "effective_at": f"2026-01-{day:02}T{hour}:00:00Z", "code": "US.SYNTH",
        "market": "US", "currency": "USD", "asset_type": "stock", "side": side, "quantity": "10", "price": price,
        **({"fx": fx} if fx else {})})


def quote(db, actual, rate, *, recorded="2026-01-05T12:00:00Z", rid=None, estimate=False):
    return s.save_event(db, {"account_id": "a", "kind": "valuation", "effective_at": recorded,
        "data": {"fx": {"USD": {"rate": rate, "at": actual, "source": "saved historical observation", "is_estimate": estimate}}}}, rid)


def test_carry_opening_and_explicit_old_rate_preserve_cash_native_profit(db):
    trade(db, 1, "BUY")
    trade(db, 2, "SELL", price="12", fx={"USD": {"rate": "6.8", "at": "2026-01-02T09:00:00Z", "source": "manual sell"}})
    closed = s.closed_positions(db, "a")
    item = closed["items"][0]
    assert D(item["realized"]) == 20 and D(item["realized_cny"]) == 116  # 120*6.8 - 100*7.
    assert closed["summary"]["missing_cny_count"] == 0
    assert closed["summary"]["estimated_cny_count"] == 1
    assert [t["fx"]["rate"] for t in item["trades"]] == ["7", "6.8"]
    assert all(t["fx"]["carried"] for t in item["trades"])
    assert s.overview(db, "a")["current"]["cash"][0]["amount"] == "1020"


def test_backfill_uses_actual_time_even_before_its_parent_record_and_recomputes_on_correction_void(db):
    trade(db, 2, "BUY")
    trade(db, 4, "SELL", price="12")
    assert D(s.closed_positions(db, "a")["items"][0]["realized_cny"]) == 140
    rid = quote(db, "2026-01-02T08:00:00Z", "6.5")
    assert D(s.closed_positions(db, "a")["items"][0]["realized_cny"]) == 130
    earlier = s.overview(db, "a", until="2026-01-02T12:00:00Z")["current"]
    assert D(earlier["positions"][0]["cost_cny"]) == 650
    assert earlier["fx_basis"]["USD"]["recorded_at"] == "2026-01-05T12:00:00Z"
    quote(db, "2026-01-02T08:00:00Z", "6", rid=rid)
    assert D(s.closed_positions(db, "a")["items"][0]["realized_cny"]) == 120
    s.void(db, "event", rid)
    assert D(s.closed_positions(db, "a")["items"][0]["realized_cny"]) == 140


def test_future_actual_rate_never_fills_earlier_cost_and_currency_cannot_cross(db):
    row = s.overview(db, "a")["openings"][0]
    row["fx"] = {}
    s.save_opening(db, "a", row, correction=True)
    trade(db, 2, "BUY")
    quote(db, "2026-01-03T08:00:00Z", "6")
    s.save_event(db, {"account_id": "a", "kind": "valuation", "effective_at": "2026-01-05T13:00:00Z", "data": {
        "fx": {"HKD": {"rate": "0.9", "at": "2026-01-01T00:00:00Z"}}}})
    trade(db, 4, "SELL", price="12")
    assert s.closed_positions(db, "a")["items"][0]["realized_cny"] is None
    early = s.overview(db, "a", until="2026-01-02T12:00:00Z")["current"]
    assert early["positions"][0]["cost_cny"] is None and early["positions"][0]["fx"] is None
    assert any("缺少 USD" in i for i in early["issues"])


def test_explicit_quote_wins_this_trade_but_does_not_replace_later_history(db):
    quote(db, "2026-01-02T09:00:00Z", "6.8")
    trade(db, 2, "BUY", fx={"USD": {"rate": "6.5", "at": "2026-01-02T08:00:00Z"}})
    trade(db, 3, "SELL", price="12")
    c = s.closed_positions(db, "a")["items"][0]
    assert D(c["realized_cny"]) == 166
    assert [t["fx"]["rate"] for t in c["trades"]] == ["6.5", "6.8"]
    assert c["trades"][0]["fx"]["selection"] == "explicit"


def test_newer_actual_quote_is_chosen_even_if_older_quote_was_recorded_later(db):
    quote(db, "2026-01-02T09:00:00Z", "6.8", recorded="2026-01-05T12:00:00Z")
    quote(db, "2026-01-02T08:00:00Z", "6.2", recorded="2026-01-06T12:00:00Z")
    trade(db, 3, "BUY")
    p = s.overview(db, "a", until="2026-01-03T12:00:00Z")["current"]["positions"][0]
    assert D(p["cost_cny"]) == 680
    assert p["fx"]["at"] == "2026-01-02T09:00:00Z"


def test_same_actual_time_correction_is_deterministic_and_does_not_mutate_facts(db):
    quote(db, "2026-01-02T08:00:00Z", "6.5")
    quote(db, "2026-01-02T08:00:00Z", "6.6", recorded="2026-01-06T12:00:00Z", estimate=True)
    trade(db, 3, "BUY")
    saved = deepcopy(db.scalar(select(Deal)).ledger_data)
    current = s.overview(db, "a")["current"]
    assert D(current["positions"][0]["cost_cny"]) == 660
    assert current["positions"][0]["fx"]["is_estimate"] is True
    assert db.scalar(select(Deal)).ledger_data == saved
    assert s.overview(db, "a", view="chart")["current"] == current


def test_dividend_and_external_flows_share_asof_rate_without_double_count(db):
    trade(db, 1, "BUY")
    s.save_event(db, {"account_id": "a", "kind": "dividend", "effective_at": "2026-01-02T12:00:00Z", "data": {
        "code": "US.SYNTH", "market": "US", "currency": "USD", "amount": "10"}})
    trade(db, 3, "SELL", price="12")
    c = s.closed_positions(db, "a")["items"][0]
    assert D(c["realized"]) == 30 and D(c["realized_cny"]) == 210
    assert c["dividend_records"][0]["fx"]["rate"] == "7"
    before = s.overview(db, "a")["current"]
    s.save_event(db, {"account_id": "a", "kind": "deposit", "effective_at": "2026-01-04T12:00:00Z", "data": {"currency": "USD", "amount": "100"}})
    after = s.overview(db, "a")["current"]
    assert D(after["profit"]) == D(before["profit"]) == 210
    assert D(after["cumulative_return"]) == D(before["cumulative_return"])
    assert D(after["net_flows"]) == 700


def test_known_native_snapshot_cost_is_not_retroactively_converted_at_opening_rate(db):
    s.save_opening(db, "a", {"effective_at": "2026-01-01T00:00:00Z", "cash": {"USD": "1000"},
        "positions": [{"code": "US.SYNTH", "market": "US", "currency": "USD", "quantity": "10", "average_cost": "10", "price": "10"}],
        "fx": {"USD": "7"}}, correction=True)
    trade(db, 2, "SELL", price="12")
    c = s.closed_positions(db, "a")["items"][0]
    assert D(c["realized"]) == 20 and c["realized_cny"] is None
