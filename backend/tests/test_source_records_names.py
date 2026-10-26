"""Source management and cosmetic name edits: synthetic accounts, in-memory SQLite."""
from copy import deepcopy
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Account, Deal, PortfolioEvent, PortfolioOpening, PositionSnapshot
from app.services.portfolio import service as s, security_names as names, source_records as sources

T = datetime(2026, 1, 1, 8)


def at(day=0):
    return (T + timedelta(days=day)).isoformat() + "Z"


def asset(**kw):
    return {"code": "CN.TEST", "market": "CN", "currency": "CNY", "unit": "share", "asset_type": "etf",
            "name": "XD虚构资产", "quantity": "10", "average_cost": "8", "price": "10", **kw}


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as session:
        session.add_all([Account(account_id="a", base_currency="CNY"), Account(account_id="b", base_currency="CNY")])
        session.commit()
        yield session
    engine.dispose()


def opening(db, aid="a", **kw):
    return s.save_opening(db, aid, {"effective_at": at(), "cash": {"CNY": "1000"}, "positions": [asset()], **kw})


def source(db, **kw):
    row = PositionSnapshot(account_id="a", code="TEST", market="CN", name="旧名称", asset_type="ETF", unit="",
                           quantity=10, average_cost=8, current_price=10, raw_currency="CNY", snapshot_time=T + timedelta(days=1),
                           sync_id="import_excel_synthetic")
    for k, v in kw.items():
        setattr(row, k, v)
    db.add(row)
    db.commit()
    return row


def money(db):
    c = s.calculate(db)["current"]
    return {"totals": {k: c.get(k) for k in ("total_assets", "cash_value", "market_value", "profit", "cumulative_profit", "cumulative_return", "cumulative_profit_rate", "nav")},
            "positions": [{**{k: p.get(k) for k in ("account_id", "code", "quantity", "cost", "average_cost", "cost_cny", "price", "floating", "realized", "dividends")},
                           "quote": {k: v for k, v in (p.get("quote") or {}).items() if k != "name"}} for p in c["positions"]]}


def test_rename_updates_existing_records_all_accounts_and_keeps_money_dates(db, monkeypatch):
    opening(db)
    opening(db, "b")
    s.save_trade(db, {**asset(), "account_id": "a", "side": "BUY", "quantity": "2", "price": "11", "effective_at": at(1)})
    s.save_event(db, {"account_id": "a", "kind": "valuation", "effective_at": at(2), "data": {"prices": [asset(price="12")]}})
    row = source(db)
    unrelated = source(db, code="OTHER", name="其他标的", snapshot_time=T + timedelta(days=3))
    before = money(db)
    # Verify the rename does not invoke financial validation even for incomplete books.
    monkeypatch.setattr(s, "validate", lambda *_: pytest.fail("renaming must not validate financial facts"))
    result = names.rename(db, "TEST", "虚构新名称", "CN")
    assert result["code"] == "CN.TEST" and row.name == "虚构新名称" and unrelated.name == "其他标的"
    assert money(db) == before
    assert {p["name"] for p in s.calculate(db)["current"]["positions"]} == {"虚构新名称"}
    assert all(r.data["positions"][0]["name"] == "虚构新名称" for r in db.scalars(select(PortfolioOpening)))
    assert db.scalar(select(Deal)).ledger_data["name"] == "虚构新名称"
    assert db.scalar(select(PortfolioEvent)).data["prices"][0]["name"] == "虚构新名称"
    assert db.scalar(select(PortfolioEvent)).effective_at == T + timedelta(days=2)


def test_unknown_blank_and_invalid_names_do_not_change_records(db):
    opening(db)
    for code, name in [("CN.TEST", " "), ("CN.TEST", "a\nb"), ("CN.MISSING", "新名称")]:
        with pytest.raises(ValueError):
            names.rename(db, code, name)
    assert db.get(PortfolioOpening, "a").data["positions"][0]["name"] == "XD虚构资产"


def test_reconciliation_normalizes_code_type_and_compares_historical_quantity(db):
    opening(db, positions=[asset(code="CN.000001", asset_type="fund", unit="fund_unit", quantity="12")])
    row = source(db, code="000001", asset_type="基金", quantity=10)
    r = sources.reconcile(db, "a", [row.id], include_equal=True)[0]
    assert r["status"] == "mismatch" and r["ledger_quantity"] == "12" and r["source_quantity"] == "10.0"
    assert r["source_average_cost"] is None  # Unknown source cost is not compared.


def test_unit_conflict_never_becomes_zero_and_explicit_match_is_reconciliation_only(db):
    opening(db, positions=[asset(code="CN.000001", asset_type="bond")])
    row = source(db, code="000001", asset_type="基金")
    before = money(db)
    r = sources.reconcile(db, "a", [row.id], include_equal=True)[0]
    assert r["status"] == "unmatched" and r["ledger_quantity"] is None
    target = {"code": "CN.000001", "currency": "CNY", "unit": "share"}
    sources.update_record(db, "a", row.id, {"match": target})
    assert sources.reconcile(db, "a", [row.id], include_equal=True)[0]["status"] == "equal"
    assert row.code == "000001" and row.unit == "" and money(db) == before


def test_uncovered_and_unmatched_are_actionable_not_zero(db):
    opening(db)
    early = source(db, snapshot_time=T - timedelta(days=1))
    unknown = source(db, code="NO_MATCH")
    results = sources.reconcile(db, "a", [early.id, unknown.id], include_equal=True)
    assert [r["status"] for r in results] == ["uncovered", "unmatched"]
    assert all(r["ledger_quantity"] is None for r in results)


def test_stop_delete_restore_sources_do_not_change_enrolled_finances(db):
    opening(db)
    older = source(db, quantity=9, snapshot_time=T)
    row = source(db)
    before = money(db)
    sources.update_record(db, "a", row.id, {"enabled": False})
    assert sources.reconcile(db, "a", [row.id], include_equal=True) == []
    sources.update_record(db, "a", row.id, {"is_void": True})
    assert len(sources.list_records(db, "a")["items"]) == 2
    assert sources.reconcile(db, "a") == []  # Deletion must not revive an older snapshot.
    sources.update_record(db, "a", row.id, {"is_void": False, "enabled": True})
    assert sources.reconcile(db, "a", [row.id], include_equal=True)[0]["status"] == "equal"
    assert not older.is_void and money(db) == before


def test_source_ownership_and_bad_match_roll_back_all_changes(db):
    opening(db)
    row = source(db)
    with pytest.raises(ValueError):
        sources.update_record(db, "b", row.id, {"is_void": True})
    with pytest.raises(ValueError):
        sources.update_record(db, "a", row.id, {"is_void": True, "match": {"code": "CN.NO", "currency": "CNY", "unit": "share"}})
    assert not row.is_void


def test_old_sources_report_unknown_import_time_instead_of_guessing(db):
    row = source(db)
    result = sources.list_records(db, "a")
    assert not result["enrolled"]
    assert result["items"][0]["imported_at"] is None and result["items"][0]["source"] == "Excel 导入"
    sources.update_record(db, "a", row.id, {"is_void": True})
    sources.update_record(db, "a", row.id, {"is_void": False})
    assert not row.is_void


def test_later_import_reuses_corrected_name_without_new_name_storage(db, monkeypatch):
    from app.services.imports import ImportSnapshot
    from app.services.sync import persist_snapshot
    import app.services.sync as sync
    for name in ("_create_profile", "_create_review", "_mark_freshness_states", "refresh_trade_reviews"):
        monkeypatch.setattr(sync, name, lambda *_: None)
    opening(db)
    names.rename(db, "CN.TEST", "用户确认名称")
    snapshot = ImportSnapshot(accounts=[], account_snapshots=[], positions=[{
        "account_id": "a", "code": "CN.TEST", "name": "XD来源旧名称", "market": "CN", "asset_type": "etf", "unit": "share",
        "quantity": 10, "average_cost": 8, "current_price": 10, "raw_market_value": 100,
        "raw_currency": "CNY", "normalized_currency": "CNY", "normalized_market_value": 100,
        "position_weight": 1, "profit_loss_ratio": 0, "snapshot_time": T + timedelta(days=1),
    }])
    persist_snapshot(db, "import_excel_new", snapshot)
    db.commit()
    assert db.scalar(select(PositionSnapshot)).name == "用户确认名称"
    assert s.calculate(db)["current"]["positions"][0]["name"] == "用户确认名称"


def test_opening_read_no_longer_runs_reconciliation(db, monkeypatch):
    from app.routers.portfolio import opening as opening_api
    opening(db)
    monkeypatch.setattr(s, "reconcile", lambda *_: pytest.fail("read must not reconcile"))
    assert opening_api("a", db)["reconciliation"] == []


def test_new_import_cleans_only_known_mainland_xd_prefix():
    value = names.reuse_names([asset(), asset(code="US.XDIV", market="US", name="XDIV Fund")], {})
    assert value[0]["name"] == "虚构资产" and value[1]["name"] == "XDIV Fund"


def test_api_sources_rename_and_validation_use_isolated_database(db):
    from fastapi import HTTPException
    from app.routers.portfolio import sources as read_sources, reconcile_sources, rename_security, edit_source
    opening(db)
    row = source(db)
    before = money(db)
    assert read_sources("a", db)["items"][0]["id"] == row.id
    assert reconcile_sources("a", {"source_ids": [row.id]}, db)["items"][0]["status"] == "equal"
    assert rename_security({"code": "CN.TEST", "name": "API确认名称"}, db)["name"] == "API确认名称"
    assert edit_source("a", row.id, {"is_void": True}, db)["id"] == row.id
    for aid, payload in [("b", {"is_void": False}), ("a", {"match": "invalid"})]:
        with pytest.raises(HTTPException) as error:
            edit_source(aid, row.id, payload, db)
        assert error.value.status_code == 400
    assert money(db) == before


def test_additive_source_metadata_migration_preserves_legacy_row(monkeypatch):
    from sqlalchemy import text
    import app.database as database
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("create table position_snapshots(id integer primary key, code varchar, quantity float)"))
        connection.execute(text("insert into position_snapshots(id,code,quantity) values(1,'000001',12)"))
    monkeypatch.setattr(database, "engine", engine)
    database._ensure_sqlite_columns()
    with engine.connect() as connection:
        row = connection.execute(text("select code,quantity,reconciliation_data from position_snapshots")).one()
        assert tuple(row) == ("000001", 12, "{}")
    engine.dispose()


def test_gf_reimport_retains_renamed_security_and_original_amounts(db):
    from test_gf_import import sources as synthetic_gf_sources
    from app.services.portfolio.gf_import import prepare, replace_ledger
    from decimal import Decimal
    db.add(Account(account_id="gf", display_name="广发测试"))
    db.commit()
    batch = prepare(*synthetic_gf_sources())
    report = replace_ledger(db, "gf", batch, commit=True)
    assert Decimal(report["cash"]["CNY"]) == 864 and Decimal(report["cost"]) == 36
    code = next(iter(report["positions"]))
    names.rename(db, code, "用户确认名称")
    assert replace_ledger(db, "gf", batch, commit=True)["status"] == "already_imported"
    assert s.calculate(db, "gf")["current"]["positions"][0]["name"] == "用户确认名称"


def test_full_batch_absence_requires_all_members_to_remain_enabled(db):
    from app.models import HoldingObservationBatch
    opening(db, positions=[asset(), asset(code="CN.OTHER")])
    row = source(db)
    batch = HoldingObservationBatch(account_id="a", market="CN", completeness="full", observed_at=row.snapshot_time,
                                    created_at=T, sync_id="synthetic", source="excel")
    db.add(batch); db.flush(); row.batch_id = batch.id; db.commit()
    assert any(r["code"] == "CN.OTHER" and r["source_quantity"] == "0" for r in sources.reconcile(db, "a"))
    sources.update_record(db, "a", row.id, {"enabled": False})
    assert sources.reconcile(db, "a") == []
