"""Read-path contracts: bounded replay, unchanged accounting, no writes on GET."""
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
import pytest

from app.database import Base
from app.models import Account, Deal, TradeReview, PortfolioEvent
from app.services.portfolio import service as s
from app.services.portfolio.performance import public
from app.services.trade_review import trade_review_payload, update_trade_review_intent


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'reads.db'}")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as db:
        db.add(Account(account_id="a", display_name="Synthetic"))
        db.commit()
        s.save_opening(db, "a", {"effective_at": "2026-01-01T08:00:00Z", "cash": {"CNY": "10000"}, "positions": []})
        for day, side, qty, price in [(2, "BUY", 100, 10), (3, "SELL", 40, 12), (5, "SELL", 60, 11), (6, "BUY", 10, 20)]:
            s.save_trade(db, {"account_id": "a", "effective_at": f"2026-01-{day:02}T08:00:00Z", "code": "CN.TEST", "name": "Synthetic ETF",
                "market": "CN", "asset_type": "etf", "currency": "CNY", "unit": "share", "side": side, "quantity": str(qty), "price": str(price), "fees": "1"})
        s.save_event(db, {"account_id": "a", "kind": "dividend", "effective_at": "2026-01-04T08:00:00Z",
            "data": {"code": "CN.TEST", "market": "CN", "asset_type": "etf", "currency": "CNY", "unit": "share", "amount": "30"}})
        yield db
    engine.dispose()


def replay_counter(monkeypatch):
    calls = []
    replay = s.replay
    def counted(*args, **kwargs):
        calls.append(kwargs)
        return replay(*args, **kwargs)
    monkeypatch.setattr(s, "replay", counted)
    return calls


def test_compact_history_preserves_current_and_every_financial_point(db):
    full = s.overview(db)
    compact = s.overview(db, view="chart")
    assert full["current"] == compact["current"]
    assert full["holdings"] == compact["holdings"]
    for expected, actual in zip(full["points"], compact["points"], strict=True):
        for p in expected["positions"]:
            p["closed_cycles"] = []
        assert {k: v for k, v in expected.items() if k in actual} == {k: v for k, v in actual.items() if k != "transaction"}
        if expected["event_type"] == "trade":
            assert actual["transaction"]["code"] == expected["data"]["code"]
            assert actual["transaction"]["side"] == expected["data"]["side"]
        detail = s.point_detail(db, "all", expected["observed_at"], expected["event_type"], expected["account_id"], expected["record_id"])
        assert detail == expected
    assert s.overview(db, view="current")["points"] == []
    assert s.overview(db, view="current")["records"] == []
    assert s.overview(db, view="records")["records"] == full["records"]
    # Historical copies stay detached when a later dividend updates a closed phase.
    s.save_event(db, {"account_id": "a", "kind": "dividend", "effective_at": "2026-01-07T08:00:00Z",
        "data": {"code": "CN.TEST", "market": "CN", "asset_type": "etf", "currency": "CNY", "unit": "share", "cycle": 1, "amount": "7"}})
    assert compact["current"]["positions"][0]["closed_cycles"][0]["dividends"] == "30"


def test_request_shares_replay_and_flush_commit_rollback_invalidate(db, monkeypatch):
    calls = replay_counter(monkeypatch)
    s.projection_positions(db)
    s.projection_accounts(db)
    s.projection_quotes(db, {"CN.TEST"})
    before = s.overview(db, view="current")["current"]
    assert len(calls) == 1
    row = db.scalar(select(PortfolioEvent).where(PortfolioEvent.kind == "dividend"))
    row.data = {**row.data, "amount": "40"}
    assert s.overview(db, view="current")["current"]["cash_value"] != before["cash_value"]
    assert len(calls) == 2
    db.rollback()
    assert s.overview(db, view="current")["current"] == before
    assert len(calls) == 3
    db.commit()
    s.overview(db, view="current")
    assert len(calls) == 4
    # An as-of result must not reuse the current quote overlay.
    historical = s.overview(db, until="2026-01-03T08:00:00Z", view="current")
    assert historical["current"]["positions"][0]["quantity"] == "60"


def test_review_read_batches_prices_and_first_intent_can_be_saved(db, monkeypatch):
    calls = replay_counter(monkeypatch)
    original = public(s.facts(db)[1][0].ledger_data)
    result = trade_review_payload(db)
    assert len(result["items"]) == 4 and len(calls) == 1
    assert not db.new and not db.dirty
    assert db.scalar(select(func.count()).select_from(TradeReview)) == 0
    review = update_trade_review_intent(db, result["items"][0]["review_id"], {"note": "Synthetic intent"})
    assert review.user_note == "Synthetic intent"
    stored_at = review.updated_at
    again = trade_review_payload(db)
    assert next(i for i in again["items"] if i["review_id"] == review.review_id)["user_note"] == "Synthetic intent"
    assert review.updated_at == stored_at and not db.dirty and not db.new
    assert public(s.facts(db)[1][0].ledger_data) == original
    assert db.scalar(select(func.count()).select_from(Deal)) == 4
