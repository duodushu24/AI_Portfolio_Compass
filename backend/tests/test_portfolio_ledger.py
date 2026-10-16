"""S-002: public service/API contracts, synthetic money, isolated SQLite only."""
from datetime import datetime, timedelta
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Account, Deal, HoldingObservationBatch, PortfolioEvent, PortfolioOpening, PositionSnapshot
from app.services.portfolio import service as s
from app.services.sync import latest_positions, latest_account_snapshots

T = datetime(2026, 10, 1, 8)


def gold(**changes):
    return asset(code="CN.GOLD.BANK_A", name="虚构甲银行积存金", asset_type="precious_metal", unit="gram", **changes)


def when(days=0):
    return (T + timedelta(days=days)).isoformat() + "Z"


def asset(**changes):
    return {"code": "CN.TEST", "name": "虚构测试资产", "market": "CN", "asset_type": "stock", "currency": "CNY", "unit": "share", **changes}


@pytest.fixture
def records(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'ledger.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    def isolated():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = isolated
    import app.services.sync as sync
    for name in ("_create_profile", "_create_review", "_mark_freshness_states", "refresh_trade_reviews"):
        monkeypatch.setattr(sync, name, lambda *args: None)
    with sessions() as db:
        db.add_all([Account(account_id="test-a", base_currency="CNY", enabled=True), Account(account_id="test-b", base_currency="CNY", enabled=False)])
        db.commit()
    client = TestClient(app)
    yield client, sessions
    client.close()
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def opening(db, account="test-a", cash="1000", positions=None, day=0, **kw):
    return s.save_opening(db, account, {"effective_at": when(day), "cash": {"CNY": cash}, "positions": positions or [], **kw})


def trade(db, side="BUY", quantity="10", price="10", day=1, fees="0", account="test-a", **kw):
    return s.save_trade(db, {**asset(), "account_id": account, "side": side, "quantity": quantity, "price": price,
                            "fees": fees, "effective_at": when(day), **kw})


def event(db, kind, day, account="test-a", **data):
    return s.save_event(db, {"account_id": account, "kind": kind, "effective_at": when(day), "data": data})


def value(db, day, price, **kw):
    return event(db, "valuation", day, prices=[{**asset(), "price": price, "at": when(day), "source": "虚构", **kw}])


def current(db, scope="all"):
    return s.calculate(db, scope)["current"]


def test_average_cost_cash_fees_partial_exit_rebuy(records):
    _, sessions = records
    with sessions() as db:
        opening(db, positions=[asset(quantity="100", average_cost="10", price="12")])
        trade(db, quantity="50", price="14", fees="5")
        p = current(db)["positions"][0]
        assert p["quantity"] == 150 and p["cost"] == 1705 and p["average_cost"] == D(1705) / 150
        trade(db, "SELL", "30", "15", day=2, fees="3")
        p = current(db)["positions"][0]
        assert p["quantity"] == 120 and p["cost"] == 1364 and p["realized"] == 106
        assert current(db)["cash_value"] == 742
        trade(db, "SELL", "120", "16", day=3, fees="7")
        p = current(db)["positions"][0]
        assert p["quantity"] == 0 and p["cost"] == 0 and p["holding_return"] is None and p["realized"] == 655
        assert current(db)["cash_value"] == 2655
        trade(db, "BUY", "10", "20", day=4)
        p = current(db)["positions"][0]
        assert p["average_cost"] == 20 and p["cycle"] == 2 and p["realized"] == 655


def test_nav_deposit_44_percent_640_and_opening_floating_not_recounted(records):
    _, sessions = records
    with sessions() as db:
        opening(db, cash="0", positions=[asset(quantity="100", average_cost="8", price="10")])
        assert current(db)["profit"] == 0 and current(db)["positions"][0]["floating"] == 200
        value(db, 1, "12")
        assert current(db)["cumulative_return"] == D("0.2")
        event(db, "deposit", 2, currency="CNY", amount="1000")
        p = current(db)
        assert abs(p["cumulative_return"] - D("0.2")) < D("1e-25") and p["profit"] == 200
        value(db, 3, "16.4")  # 1640 holdings + 1000 cash = 2640.
        p = current(db)
        assert abs(p["cumulative_return"] - D("0.44")) < D("1e-25") and p["profit"] == 640
        assert p["performance_issues"]  # Deposit used a prior dated quote.


def test_transfer_scope_membership_and_disabled_setting(records):
    _, sessions = records
    with sessions() as db:
        opening(db)
        opening(db, "test-b", cash="500", day=1)
        assert current(db)["total_assets"] == 1500 and current(db)["profit"] == 0
        event(db, "transfer", 2, currency="CNY", amount="200", to_account_id="test-b", fees="2")
        assert current(db)["total_assets"] == 1498 and current(db)["profit"] == -2
        assert current(db, "test-a")["net_flows"] == -200 and current(db, "test-a")["profit"] == -2
        assert current(db, "test-b")["net_flows"] == 200 and current(db, "test-b")["profit"] == 0
        payload = s.overview(db, "test-b")["openings"][0]
        payload["excluded_at"] = when(3)
        s.save_opening(db, "test-b", payload, True)
        assert current(db)["total_assets"] == 798 and current(db)["profit"] == -2
        assert current(db, "test-b")["total_assets"] == 700


def test_all_cash_full_withdrawal_and_new_interval(records):
    _, sessions = records
    with sessions() as db:
        opening(db)
        event(db, "interest", 1, currency="CNY", amount="200")
        event(db, "withdrawal", 2, currency="CNY", amount="1200")
        p = current(db)
        assert p["ended"] and p["units"] == 0 and p["cumulative_return"] == D("0.2") and p["profit"] == 200
        event(db, "deposit", 3, currency="CNY", amount="500")
        p = current(db)
        assert p["interval"] == 2 and p["cumulative_return"] == 0 and p["profit"] == 0


def test_zero_opening_then_funding_and_fractional_fund(records):
    _, sessions = records
    with sessions() as db:
        opening(db, cash="0")
        event(db, "deposit", 1, currency="CNY", amount="100")
        trade(db, day=2, quantity="12.3456", price="1.2345", asset_type="fund", unit="fund_unit")
        p = current(db)["positions"][0]
        assert p["quantity"] == D("12.3456") and p["cost"] == D("15.24064320")
        with pytest.raises(ValueError):
            trade(db, day=3, quantity="1", price="1", asset_type="fund", unit="share")


def test_pending_subscription_redemption_dividend_and_expense(records):
    _, sessions = records
    with sessions() as db:
        opening(db)
        reserve = event(db, "subscription", 1, currency="CNY", amount="200")
        assert current(db)["total_assets"] == 1000 and current(db)["cash_value"] == 800
        buy = trade(db, day=2, quantity="100", price="1.99", fees="1", asset_type="fund", unit="fund_unit", pending_id=f"event:{reserve}")
        assert current(db)["total_assets"] == 999 and not current(db)["pending"]
        sell = trade(db, "SELL", "100", "2.2", day=3, fees="2", asset_type="fund", unit="fund_unit", settlement="pending")
        assert current(db)["total_assets"] == 1018 and current(db)["cash_value"] == 800
        event(db, "settle", 4, pending_id=f"deal:{sell}")
        assert current(db)["total_assets"] == 1018 and current(db)["cash_value"] == 1018
        event(db, "dividend", 5, currency="CNY", amount="20")
        event(db, "fee", 6, currency="CNY", amount="3")
        assert current(db)["profit"] == 35 and current(db)["positions"][0]["realized"] == 18
        with pytest.raises(ValueError):
            s.void(db, "trade", buy)  # Would create a later oversell; no half mutation.
        assert not db.get(Deal, buy).is_void


def test_fx_historic_cost_not_fabricated_and_cash_fx_income(records):
    _, sessions = records
    with sessions() as db:
        s.save_opening(db, "test-a", {"effective_at": when(), "cash": {"USD": "100"},
            "positions": [asset(code="US.TEST", market="US", currency="USD", quantity="10", average_cost="5", price="10")],
            "fx": {"USD": {"rate": "7", "at": when()}}})
        p = current(db)
        assert p["total_assets"] == 1400 and p["positions"][0]["cost_cny"] is None
        event(db, "valuation", 1, fx={"USD": {"rate": "8", "at": when(1)}})
        assert current(db)["profit"] == 200 and current(db)["positions"][0]["floating_cny"] is None
        event(db, "fx", 2, currency="USD", amount="50", to_currency="CNY", to_amount="400", fees="1")
        assert current(db)["total_assets"] == 1592
        assert s.calculate(db, until=T)["current"]["total_assets"] == 1400
        trade(db, day=3, quantity="1", price="10", code="US.NEW", market="US", currency="USD")
        p = next(p for p in current(db)["positions"] if p["code"] == "US.NEW")
        assert p["cost"] == 10 and p["cost_cny"] is None  # Prior FX is a valuation estimate, not an exact acquiring cost.


def test_missing_price_fx_unknown_and_zero_cost(records):
    _, sessions = records
    with sessions() as db:
        opening(db, positions=[asset(quantity="10", average_cost=None)])
        p = current(db)
        assert p["total_assets"] is None and p["cumulative_return"] is None
        value(db, 1, "12")
        assert current(db)["positions"][0]["floating"] is None
        assert current(db)["cumulative_return"] is None and current(db)["profit"] is None
        value(db, 0, "10")
        assert current(db)["total_assets"] == 1120 and current(db)["profit"] == 20
        payload = s.overview(db, "test-a")["openings"][0]
        payload.pop("prices", None)
        payload["positions"][0]["average_cost"] = "0"
        s.save_opening(db, "test-a", payload, True)
        assert current(db)["positions"][0]["holding_return"] is None


def test_backdated_correction_code_time_fees_replay_and_atomic_oversell(records):
    _, sessions = records
    with sessions() as db:
        opening(db)
        b = trade(db, quantity="20", price="10")
        trade(db, "SELL", "10", "12", day=3)
        s.save_trade(db, {**asset(), "account_id": "test-a", "effective_at": when(2), "side": "BUY", "quantity": "30", "price": "9", "fees": "3"}, b)
        p = current(db)
        assert p["positions"][0]["quantity"] == 20 and p["positions"][0]["average_cost"] == D("9.1")
        assert p["positions"][0]["realized"] == 29 and p["cash_value"] == 847
        with pytest.raises(ValueError):
            trade(db, "SELL", "21", "20", day=4)
        assert len(list(db.scalars(select(Deal)))) == 2
        with pytest.raises(ValueError):
            s.save_trade(db, {**asset(code="CN.OTHER"), "account_id": "test-a", "effective_at": when(2), "side": "BUY", "quantity": "30", "price": "9"}, b)
        assert db.get(Deal, b).code == "CN.TEST"


def test_exact_flow_boundary_backfill_and_quote_correction(records):
    _, sessions = records
    with sessions() as db:
        opening(db, cash="0", positions=[asset(quantity="100", average_cost="10", price="10")])
        event(db, "deposit", 2, currency="CNY", amount="1000")
        value(db, 3, "14")
        assert current(db)["cumulative_return"] == D("0.2")
        quote = value(db, 2, "12")  # At exact flow boundary: valuation precedes flow.
        assert abs(current(db)["cumulative_return"] - D("2400") / (D(1000) + D(1000) / D("1.2")) + 1) < D("1e-25")
        original = s.calculate(db, until=T)["current"]
        s.save_event(db, {"account_id": "test-a", "kind": "valuation", "effective_at": when(2), "data": {"prices": [{**asset(), "price": "13", "at": when(2)}]}}, quote)
        assert s.calculate(db, until=T)["current"] == original


def test_shared_price_value_input_and_current_projection_consistency(records):
    _, sessions = records
    with sessions() as db:
        opening(db, positions=[asset(quantity="10", average_cost="8", price="10")])
        opening(db, "test-b", cash="0", positions=[asset(quantity="20", average_cost="9", price="10")])
        event(db, "valuation", 1, prices=[{**asset(), "market_value": "150", "at": when(1)}])
        prices = latest_positions(db)
        assert all(p.current_price == 15 for p in prices)
        assert sum(p.normalized_market_value for p in prices) == 450
        assert sum(p.total_assets for p in latest_account_snapshots(db)) == 1450
        assert current(db)["total_assets"] == 1450


def test_split_and_custody_transfer_preserve_cost_and_scope(records):
    _, sessions = records
    with sessions() as db:
        opening(db, positions=[asset(quantity="10", average_cost="8", price="10")])
        opening(db, "test-b", cash="0")
        event(db, "split", 1, **asset(), factor="2")
        p = current(db)["positions"][0]
        assert p["quantity"] == 20 and p["cost"] == 80 and p["price"] == 5
        event(db, "position_transfer", 2, **asset(), quantity="6", to_account_id="test-b")
        assert current(db)["total_assets"] == 1100 and current(db)["profit"] == 0
        assert current(db, "test-b")["positions"][0]["cost"] == 24
        assert current(db, "test-b")["opening_assets"] == 30 and current(db, "test-b")["profit"] == 0


def test_api_complete_loop_closed_detail_correction_and_guards(records):
    client, sessions = records
    payload = {"effective_at": when(), "positions": [], "cash": {"CNY": "1000"}}
    assert client.put("/api/portfolio/accounts/test-a/opening", json=payload).status_code == 200
    response = client.post("/api/portfolio/trades", json={**asset(), "account_id": "test-a", "effective_at": when(1), "side": "BUY", "quantity": "10", "price": "10", "fees": "1"})
    assert response.status_code == 200, response.text
    assert client.post("/api/portfolio/events", json={"account_id": "test-a", "kind": "valuation", "effective_at": when(2), "data": {"prices": [{**asset(), "price": "12", "at": when(2)}]}}).status_code == 200
    assert client.post("/api/portfolio/trades", json={**asset(), "account_id": "test-a", "effective_at": when(3), "side": "SELL", "quantity": "10", "price": "12", "fees": "1"}).status_code == 200
    detail = client.get("/api/positions/CN.TEST?account_id=test-a")
    assert detail.status_code == 200, detail.text
    assert detail.json()["position"]["quantity"] == 0
    assert D(detail.json()["performance"]["current"]["positions"][0]["realized"]) == 18
    assert client.get("/api/positions/kline/CN.TEST?account_id=test-a").status_code == 200
    assert client.post("/api/data/accounts/test-a/positions", json={"code": "CN.TEST", "snapshot_time": when(4)}).status_code == 409
    bad = client.post("/api/portfolio/trades", json={**asset(), "account_id": "test-a", "effective_at": when(4), "side": "BUY", "quantity": "NaN", "price": "10"})
    assert bad.status_code == 400
    assert client.get("/api/portfolio/overview?account_id=test-a").json()["current"]["profit"] == "18"


def test_import_reconciliation_deal_dedup_and_source_preservation(records):
    _, sessions = records
    from app.services.imports import ImportSnapshot
    from app.services.sync import persist_snapshot
    with sessions() as db:
        opening(db)
        source = PositionSnapshot(account_id="test-a", code="CN.TEST", market="CN", quantity=99, average_cost=10, current_price=10,
            raw_currency="CNY", normalized_currency="CNY", snapshot_time=T + timedelta(days=2), sync_id="source", cost_method="average")
        db.add(source); db.commit()
        snapshot = ImportSnapshot([], [], [], deals=[{"account_id": "test-a", "deal_id": "import-1", "code": "CN.TEST", "market": "CN", "quantity": 10, "price": 10,
            "side": "BUY", "deal_time": T + timedelta(days=1), "raw_payload": {"currency": "CNY", "fee": 1}}])
        persist_snapshot(db, "isolated-import", snapshot)
        persist_snapshot(db, "isolated-import-again", snapshot)
        assert current(db)["positions"][0]["quantity"] == 10
        assert current(db)["cash_value"] == 899
        assert len(list(db.scalars(select(Deal)))) == 1 and db.get(PositionSnapshot, source.id).quantity == 99
        assert s.reconcile(db, "test-a")[0]["ledger_quantity"] == "10"


def test_cross_account_trade_quote_adapter_price_and_no_projection_writes(records):
    client, sessions = records
    with sessions() as db:
        opening(db, positions=[asset(quantity="10", average_cost="8", price="10")])
        opening(db, "test-b", cash="500")
        trade(db, day=1, account="test-b", quantity="5", price="12")
        assert current(db, "test-a")["positions"][0]["price"] == 12
        s.ingest_quotes(db, [{"code": "CN.TEST", "current_price": 14, "quote_time": T + timedelta(days=2), "provider": "synthetic-adapter"}], "mock")
        s.validate(db); db.commit()
        assert current(db, "test-a")["positions"][0]["price"] == 14
        assert current(db, "test-b")["positions"][0]["price"] == 14
        # A provider can return an old close; observation happens now, quote time stays old.
        s.ingest_quotes(db, [{"code": "CN.TEST", "current_price": 9, "quote_time": T - timedelta(days=1), "provider": "synthetic-adapter"}], "old-close")
        s.validate(db); db.commit()
        assert current(db)["positions"][0]["price"] == 14
    result = client.patch("/api/positions/CN.TEST/layer", json={"position_layer": "核心长期仓", "reason": "虚构验证"})
    assert result.status_code == 200, result.text
    with sessions() as db:
        assert not list(db.scalars(select(PositionSnapshot)))
        assert all(p.position_layer == "核心长期仓" for p in latest_positions(db))


def test_missing_native_currency_does_not_become_zero_in_legacy_views(records, monkeypatch):
    client, sessions = records
    import app.main as main
    monkeypatch.setattr(main, "fx_display_rates", lambda *args: ({"CNY": 1}, {}))
    with sessions() as db:
        opening(db, cash="0", positions=[asset(code="US.TEST", market="US", currency="USD", quantity="10", average_cost=None, price="10")])
    dto = client.get("/api/positions?account_id=test-a").json()["items"][0]
    assert dto["average_cost"] is None and dto["normalized_market_value"] is None
    dashboard = client.get("/api/dashboard?account_id=test-a").json()
    assert dashboard["portfolio"]["total_assets"] is None
    assert dashboard["portfolio"]["total_position_value"] is None


def test_zero_cash_tiny_overspend_is_rejected_and_invalid_dates_are_400(records):
    client, sessions = records
    with sessions() as db:
        opening(db, cash="0")
        with pytest.raises(ValueError):
            trade(db, quantity="1", price="0.000000001")
        assert not list(db.scalars(select(Deal)))
    response = client.post("/api/portfolio/events", json={"account_id": "test-a", "kind": "deposit", "effective_at": None, "data": {"amount": "1"}})
    assert response.status_code == 400


def test_sqlite_additive_upgrade_keeps_old_deal(tmp_path, monkeypatch):
    import app.database as database
    from types import SimpleNamespace
    from sqlalchemy import text
    engine = create_engine(f"sqlite:///{tmp_path / 'upgrade.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE deals (id INTEGER PRIMARY KEY, deal_id VARCHAR, order_id VARCHAR, code VARCHAR, side VARCHAR, price FLOAT, quantity FLOAT, deal_time DATETIME, market VARCHAR, account_id VARCHAR, raw_payload JSON)"))
        conn.execute(text("INSERT INTO deals VALUES (1,'old-source','','CN.OLD','BUY',10,2,'2026-09-01 08:00:00','CN','old-account','{}')"))
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "settings", SimpleNamespace(database_url="sqlite:///synthetic-upgrade.db"))
    database.init_db()
    with sessionmaker(bind=engine)() as db:
        old = db.get(Deal, 1)
        assert old.code == "CN.OLD" and old.quantity == 2 and old.ledger_data == {} and old.is_void is False
        assert not list(db.scalars(select(PortfolioOpening)))
    engine.dispose()


def test_account_correction_duplicate_external_deal_id_keeps_both_sources(records):
    client, sessions = records
    with sessions() as db:
        opening(db)
        opening(db, "test-b")
        record_id = trade(db, deal_id="same-source-id")
        trade(db, account="test-b", deal_id="same-source-id")
    response = client.put(f"/api/portfolio/trades/{record_id}", json={**asset(), "account_id": "test-b", "effective_at": when(1), "side": "BUY", "quantity": "10", "price": "10"})
    assert response.status_code == 400
    with sessions() as db:
        assert db.get(Deal, record_id).account_id == "test-a"
        assert len(list(db.scalars(select(Deal)))) == 2


def test_realized_profit_includes_opening_gain_while_period_profit_starts_at_market_value(records):
    client, sessions = records
    with sessions() as db:
        db.get(Account, "test-a").display_name = "示例证券账户"
        db.commit()
        s.save_opening(db, "test-a", {"effective_at": when(), "positions": [asset(code="US.TEST", market="US", currency="USD", quantity="10", average_cost="10", price="15")],
            "cash": {"USD": "0"}, "fx": {"USD": {"rate": "7", "at": when()}}})
        trade(db, "SELL", "10", "17", day=1, fees="1", code="US.TEST", market="US", currency="USD", fx={"USD": {"rate": "7", "at": when(1)}})
        trade(db, quantity="20", price="4", day=2, fees="1", code="US.NEW", market="US", currency="USD", fx={"USD": {"rate": "7", "at": when(2)}})
        p = current(db)
        sold = next(a for a in p["positions"] if a["code"] == "US.TEST")
        assert sold["realized"] == 69  # Average cost 100; net sale proceeds 169.
        assert p["opening_assets"] == 1050  # Opening market value 150 USD, not cost 100 USD.
        assert p["total_assets"] == 1176 and p["profit"] == 126  # (19 USD new gain - 1 USD new buy fee) * 7.
    response = client.get("/api/portfolio/overview?account_id=test-a")
    assert response.status_code == 200
    assert response.json()["account_names"] == {"test-a": "示例证券账户"}


def test_account_names_include_transfer_counterparty_and_reflect_rename(records):
    client, sessions = records
    with sessions() as db:
        db.get(Account, "test-a").display_name = "示例转出账户"
        db.get(Account, "test-b").display_name = "示例转入账户"
        db.commit()
        opening(db)
        opening(db, "test-b", cash="0")
        event(db, "transfer", 1, amount="10", currency="CNY", to_account_id="test-b")
    names = client.get("/api/portfolio/overview?account_id=test-b").json()["account_names"]
    assert names == {"test-a": "示例转出账户", "test-b": "示例转入账户"}
    with sessions() as db:
        db.get(Account, "test-a").display_name = "更新后的账户名称"
        db.commit()
    assert client.get("/api/portfolio/overview?account_id=test-b").json()["account_names"]["test-a"] == "更新后的账户名称"


def test_closed_cycle_return_uses_all_disposed_cost_and_survives_rebuy(records):
    client, sessions = records
    with sessions() as db:
        opening(db)
        trade(db, quantity="10", price="10", fees="1")
        trade(db, "SELL", quantity="4", price="12", fees="1", day=2)
        trade(db, "SELL", quantity="6", price="13", fees="2", day=3)
        p = current(db)["positions"][0]
        # Net sale proceeds 47 + 76; cost 101; profit 22, return 22/101.
        assert p["closed_return"] == D(22) / D(101)
        assert p["closed_cycles"][0]["disposed_cost"] == 101
        assert p["closed_cycles"][0]["realized"] == 22
        trade(db, quantity="2", price="20", day=4)
        p = current(db)["positions"][0]
        assert p["closed_return"] is None and p["cycle"] == 2
        assert p["closed_cycles"][0]["realized"] == 22
        trade(db, "SELL", quantity="2", price="15", day=5)
        p = current(db)["positions"][0]
        assert p["realized"] == 12 and p["closed_return"] == D("-0.25")
        assert [c["realized"] for c in p["closed_cycles"]] == [22, -10]
    result = client.get("/api/data/accounts/test-a/overview").json()
    assert result["positions"] == []
    assert result["ledger_positions"][0]["closed_return"] == "-0.25"


@pytest.mark.parametrize("cost", [None, "0"])
def test_closed_cycle_unknown_or_zero_cost_has_no_percentage(records, cost):
    _, sessions = records
    with sessions() as db:
        opening(db, positions=[asset(quantity="1", average_cost=cost, price="10")])
        trade(db, "SELL", quantity="1", price="12")
        p = current(db)["positions"][0]
        assert p["closed_return"] is None
        assert len(p["closed_cycles"]) == 1
        assert p["closed_cycles"][0]["realized"] == (None if cost is None else D(12))


def test_transfer_out_does_not_reuse_a_previous_cycle_exit_percentage(records):
    _, sessions = records
    with sessions() as db:
        opening(db)
        opening(db, "test-b", cash="0")
        trade(db, quantity="2", price="10")
        trade(db, "SELL", quantity="2", price="11", day=2)
        trade(db, quantity="2", price="20", day=3)
        event(db, "position_transfer", 4, **asset(), quantity="2", to_account_id="test-b")
        p = current(db, "test-a")["positions"][0]
        assert p["quantity"] == 0 and p["closed_return"] is None
        assert len(p["closed_cycles"]) == 1 and p["closed_cycles"][0]["return"] == D("0.1")


def test_reconciliation_compares_snapshot_time_not_current_exit(records):
    _, sessions = records
    with sessions() as db:
        opening(db, positions=[asset(quantity="10", average_cost="8", price="10")])
        db.add(PositionSnapshot(account_id="test-a", code="CN.TEST", market="CN", asset_type="stock", quantity=10,
            average_cost=8, cost_method="average", raw_currency="CNY", snapshot_time=T, sync_id="source"))
        db.commit()
        trade(db, "SELL", quantity="10", price="12")
        assert s.reconcile(db, "test-a") == []
        source = db.scalar(select(PositionSnapshot))
        source.average_cost = 9
        db.commit()
        diff = s.reconcile(db, "test-a")[0]
        assert diff["status"] == "mismatch" and diff["ledger_quantity"] == "10"
        assert diff["reason"] == "同一时点的平均成本不同"


def test_reconciliation_older_source_is_uncovered_not_missing_trade(records):
    _, sessions = records
    with sessions() as db:
        opening(db, day=1)
        db.add(PositionSnapshot(account_id="test-a", code="CN.TEST", market="CN", quantity=10,
            average_cost=8, cost_method="average", raw_currency="CNY", snapshot_time=T, sync_id="old-source"))
        db.commit()
        diff = s.reconcile(db, "test-a")[0]
        assert diff["status"] == "uncovered" and diff["ledger_quantity"] is None


def test_reconciliation_full_snapshot_can_prove_absence_partial_cannot(records):
    _, sessions = records
    with sessions() as db:
        opening(db, positions=[asset(quantity="10", average_cost="8", price="10")])
        batch = HoldingObservationBatch(account_id="test-a", observed_at=T + timedelta(days=1), completeness="partial",
            market="CN", source="synthetic", sync_id="source", created_at=T)
        db.add(batch); db.commit()
        assert s.reconcile(db, "test-a") == []
        batch.completeness = "full"; db.commit()
        diff = s.reconcile(db, "test-a")[0]
        assert diff["source_quantity"] == "0" and diff["ledger_quantity"] == "10"


def test_zero_opening_first_deposit_and_buy_price_are_not_duplicate_positions(records):
    _, sessions = records
    with sessions() as db:
        opening(db, cash="0", day=-1)
        event(db, "deposit", 0, amount="1000", currency="CNY")
        trade(db, quantity="10", price="10", fees="1")
        p = current(db)["positions"][0]
        assert p["price"] == 10 and p["average_cost"] == D("10.1")
        assert p["quantity"] == 10 and p["floating"] == -1
        assert current(db)["profit"] == -1 and current(db)["cash_value"] == 899


def history_payload(**changes):
    return {"opening": {"effective_at": when(0), "cash": {"CNY": "1000"}}, "records": [
        {"kind": "trade", "effective_at": when(1), "data": {**asset(), "side": "BUY", "quantity": "10", "price": "10", "fees": "1"}}], **changes}


def test_history_preview_rollback_then_atomic_save_restores_full_profit(records):
    client, sessions = records
    with sessions() as db:
        opening(db, day=3, cash="899", positions=[asset(quantity="10", average_cost="10.1", price="12")])
        trade(db, "SELL", quantity="10", price="13", fees="2", day=4)
        assert current(db)["profit"] == 8
    endpoint = "/api/portfolio/accounts/test-a/history"
    preview = client.post(endpoint + "/preview", json=history_payload())
    assert preview.status_code == 200, preview.text
    assert preview.json()["differences"] == [] and preview.json()["current"]["profit"] == "27"
    with sessions() as db:
        assert db.get(PortfolioOpening, "test-a").effective_at == T + timedelta(days=3)
        assert len(list(db.scalars(select(Deal)))) == 1
        assert len(list(db.scalars(select(PortfolioEvent)))) == 0
    result = client.post(endpoint, json=history_payload())
    assert result.status_code == 200, result.text
    with sessions() as db:
        assert current(db)["profit"] == 27 and current(db)["total_assets"] == 1027
        assert s.calculate(db, "test-a", T + timedelta(days=3))["current"]["positions"][0]["price"] == 12
        origin = db.get(PortfolioOpening, "test-a")
        assert origin.effective_at == T and origin.included_at == T
        assert origin.data["history_checkpoints"][0]["cash"] == {"CNY": "899"}
        assert len(list(db.scalars(select(Deal)))) == 2
    assert client.post(endpoint, json=history_payload()).status_code == 400


def test_history_mismatch_requires_confirmation_and_invalid_cash_rolls_back(records):
    client, sessions = records
    with sessions() as db:
        opening(db, day=3, cash="900", positions=[asset(quantity="10", average_cost="10.1", price="12")])
    endpoint = "/api/portfolio/accounts/test-a/history"
    preview = client.post(endpoint + "/preview", json=history_payload()).json()
    assert preview["differences"] == [{"item": "CNY 现金", "before": "900", "after": "899"}]
    assert client.post(endpoint, json=history_payload()).status_code == 400
    invalid = history_payload(opening={"effective_at": when(0), "cash": {"CNY": "0"}})
    assert client.post(endpoint + "/preview", json=invalid).status_code == 400
    with sessions() as db:
        assert db.get(PortfolioOpening, "test-a").effective_at == T + timedelta(days=3)
        assert not list(db.scalars(select(Deal))) and not list(db.scalars(select(PortfolioEvent)))
    assert client.post(endpoint, json=history_payload(confirm_differences=True)).status_code == 200


def test_gold_grams_cash_cost_fees_valuation_and_closed_return(records):
    client, sessions = records
    with sessions() as db:
        opening(db, cash="10000")
    buy = {**gold(), "account_id": "test-a", "effective_at": when(1), "side": "BUY", "quantity": "10.125", "price": "600", "fees": "10.125"}
    response = client.post("/api/portfolio/trades", json=buy)
    assert response.status_code == 200, response.text
    trade_id = response.json()["id"]
    with sessions() as db:
        p = current(db)["positions"][0]
        assert p["unit"] == "gram" and p["average_cost"] == 601
        assert current(db)["cash_value"] == D("3914.875")
        trade(db, "SELL", "4.125", "650", day=2, fees="5", **gold())
        event(db, "valuation", 3, prices=[{**gold(), "market_value": "3900", "price_kind": "bank_value", "at": when(3), "source": "虚构银行展示市值"}])
        p = current(db)["positions"][0]
        assert p["quantity"] == 6 and p["cost"] == 3606 and p["realized"] == D("197.125")
        assert p["price"] == 650 and p["floating"] == 294 and p["quote"]["price_kind"] == "bank_value"
        # A securities adapter cannot overwrite bank product quotes.
        s.ingest_quotes(db, [{"code": gold()["code"], "quote_time": T + timedelta(days=4), "current_price": 1}], "fake-stock-provider")
        assert current(db)["positions"][0]["price"] == 650
        trade(db, "SELL", "6", "650", day=4, **gold())
        p = current(db)["positions"][0]
        assert p["quantity"] == 0 and p["realized"] == D("491.125")
        assert p["closed_return"] == D("491.125") / D("6085.125")
    payload = client.get("/api/portfolio/overview?account_id=test-a").json()
    assert payload["current"]["positions"][0]["unit"] == "gram"
    assert any(r["id"] == trade_id and r["kind"] == "trade" for r in payload["records"])
    kline = client.get(f"/api/positions/kline/{gold()['code']}?account_id=test-a")
    assert kline.status_code == 200 and kline.json()["items"] == []
    assert "银行黄金" in kline.json()["message"]


def test_gold_products_have_independent_quotes_and_no_live_pull(records, monkeypatch):
    _, sessions = records
    from app.main import _aggregate_positions
    from app.services.sync import pull_account_market_data
    from app.adapters.futu_adapter import FutuReadOnlyAdapter
    def forbidden(*args, **kwargs):
        raise AssertionError("bank products must not call securities adapters")
    monkeypatch.setattr(FutuReadOnlyAdapter, "fetch_quote_summaries", forbidden)
    with sessions() as db:
        a = s.asset({**gold(), "code": ""})
        b = s.asset({**gold(), "code": "", "name": "虚构乙银行账户金"})
        assert a["code"] != b["code"]
        opening(db, cash="0", positions=[{**a, "quantity": "2", "average_cost": "600", "price": "620"}])
        opening(db, "test-b", cash="0", positions=[{**b, "quantity": "3", "average_cost": "610", "price": "630"}])
        event(db, "valuation", 2, prices=[{**a, "price": "650", "price_kind": "redemption", "at": when(2), "source": "虚构甲银行回购价"}])
        positions = {p["code"]: p for p in current(db)["positions"]}
        assert positions[a["code"]]["price"] == 650 and positions[b["code"]]["price"] == 630
        rows = s.projection_positions(db)
        assert all(p.unit == "gram" and p.missing_market_code for p in rows)
        assert {p["unit"] for p in _aggregate_positions(rows)} == {"gram"}
        assert pull_account_market_data(db, db.get(Account, "test-a"), "quote")["status"] == "empty"


def test_gold_unit_validation_and_source_round_trip(records):
    client, sessions = records
    for changes in ({"unit": "share"}, {"currency": "USD"}, {"market": "US"}, {"code": "CN.TEST"}):
        with pytest.raises(ValueError):
            s.asset({**gold(), **changes})
    assert s.asset({**asset(), "asset_type": "fund", "unit": ""})["unit"] == "fund_unit"
    response = client.post("/api/data/accounts/test-a/positions", json={**gold(), "quantity": 2.125, "average_cost": 600,
        "current_price": 650, "snapshot_time": when(0), "cost_method": "average"})
    assert response.status_code == 200, response.text
    with sessions() as db:
        draft = s.source_opening(db, "test-a")
        assert draft["positions"][0]["unit"] == "gram"
        # Explicit units from a source survive building the opening and reconciliation.
        draft["effective_at"] = when(0)
        s.save_opening(db, "test-a", draft)
        assert s.reconcile(db, "test-a") == []
        p = s.projection_positions(db, "test-a")[0]
        from app.main import _position_to_dict
        assert _position_to_dict(p)["unit"] == "gram"


def test_gold_excel_preview_confirm_source_and_trade_import(records):
    from io import BytesIO
    from openpyxl import Workbook
    from app.services.imports import preview_import, confirm_import
    _, sessions = records
    def workbook_bytes(sheet, rows):
        book = Workbook(); book.active.title = sheet
        for row in rows: book.active.append(row)
        buffer = BytesIO(); book.save(buffer)
        return buffer.getvalue()
    content = workbook_bytes("持仓快照", [
        ["code", "name", "quantity", "current_price", "average_cost", "market", "asset_type", "currency", "unit", "snapshot_time"],
        ["CN.GOLD.IMPORT", "虚构银行积存金", 1.125, 650, 600, "CN", "precious_metal", "CNY", "gram", when(0)]])
    preview = preview_import("excel", "synthetic.xlsx", content, "test-a", "CNY")
    assert preview["can_confirm"] and preview["positions"][0]["unit"] == "gram"
    with sessions() as db:
        confirm_import(db, preview)
        assert s.source_opening(db, "test-a")["positions"][0]["unit"] == "gram"
        opening(db, cash="2000")
        deals = workbook_bytes("成交记录", [
            ["deal_id", "code", "side", "price", "quantity", "deal_time", "market", "currency", "fee", "asset_type", "unit"],
            ["gold-buy-1", "CN.GOLD.IMPORT", "BUY", 600, 1.125, when(1), "CN", "CNY", 1, "precious_metal", "gram"]])
        trade_preview = preview_import("excel", "synthetic-deals.xlsx", deals, "test-a", "CNY")
        assert trade_preview["can_confirm"], trade_preview["errors"]
        confirm_import(db, trade_preview)
        p = current(db)["positions"][0]
        assert p["quantity"] == D("1.125") and p["unit"] == "gram" and p["cost"] == 676


def test_unit_column_upgrade_preserves_legacy_rows(monkeypatch):
    from sqlalchemy import text
    import app.database as database
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("create table position_snapshots (id integer primary key, asset_type varchar, quantity float)"))
        conn.execute(text("insert into position_snapshots values (1, 'fund', 12.3456)"))
    monkeypatch.setattr(database, "engine", engine)
    database._ensure_sqlite_columns()
    with engine.connect() as conn:
        row = conn.execute(text("select asset_type, quantity, unit from position_snapshots")).one()
        assert tuple(row) == ("fund", 12.3456, "")
        assert s.asset_unit(row.asset_type, row.unit) == "fund_unit"
    engine.dispose()


def test_gold_backfill_and_trade_correction_replay(records):
    _, sessions = records
    with sessions() as db:
        opening(db, day=3, cash="799.25", positions=[{**gold(), "quantity": "2.125", "average_cost": "600", "price": "650"}])
        payload = {"opening": {"effective_at": when(0), "cash": {"CNY": "2074.25"}},
            "records": [{"kind": "trade", "effective_at": when(1), "data": {**gold(), "side": "BUY", "quantity": "2.125", "price": "600"}}]}
        preview = s.rebuild_history(db, "test-a", payload, preview=True)
        assert preview["differences"] == []
        assert db.get(PortfolioOpening, "test-a").effective_at == T + timedelta(days=3)
        s.rebuild_history(db, "test-a", payload)
        p = current(db)["positions"][0]
        assert p["quantity"] == D("2.125") and p["floating"] == D("106.25") and p["unit"] == "gram"
        row = db.scalar(select(Deal))
        s.save_trade(db, {**gold(), "account_id": "test-a", "effective_at": when(1), "side": "BUY", "quantity": "2.125", "price": "600", "fees": "2.125"}, row.id)
        assert current(db)["positions"][0]["average_cost"] == 601
        assert current(db)["cash_value"] == D("797.125")
