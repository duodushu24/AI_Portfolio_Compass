from copy import deepcopy
from decimal import Decimal as D

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Account, Deal, PortfolioEvent, PortfolioOpening
from app.services.portfolio import service
from app.services.portfolio.gf_import import link_existing_dividends, prepare, replace_ledger


def sources():
    flows, statements = [], []
    def row(day, business, amount, cash, qty="0", code=None, post=None, fee="0", gross="0", price="0"):
        sequence = str(len(flows) + 1)
        flows.append({"资产账户": "synthetic", "发生日期": day, "发生时间": "09:30:00", "流水序号": sequence,
                      "业务名称": business, "发生金额": amount, "剩余金额": cash, "发生数量": qty, "证券代码": code,
                      "证券名称": "测试ETF" if code else None, "币种": "人民币", "成交价格": price})
        if code:
            statements.append({"资金账号": "synthetic", "业务日期": day, "发生时间": "09:30:00", "流水序号": sequence,
                "业务标志名称": business, "清算金额": amount, "后资金额": cash, "成交数量": qty, "证券代码": code,
                "成交价格": price, "证券交易费用": fee, "成交金额": gross, "净佣金": fee,
                "印花税": "0", "过户费": "0", "证管费": "0", "经手费": "0", "其他费": "0", "后证券额": post})
    row("2026-01-01", "银行转存", "1000", "1000")
    row("2026-01-02", "证券买入", "-100.5", "899.5", "10", "510000", "10", ".5", "100", "10")
    row("2026-01-03", "红股入账", "0", "899.5", "10", "510000", "20")
    row("2026-01-04", "股息入账", "5", "904.5", "0", "510000", "20")
    row("2026-01-05", "证券卖出", "59.5", "964", "-10", "510000", "10", ".5", "60", "6")
    row("2026-01-06", "银行转取", "-100", "864")
    return flows, statements


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as session:
        session.add_all([Account(account_id="gf", display_name="广发测试", institution=""), Account(account_id="other", display_name="其他测试")])
        session.commit()
        yield session
    engine.dispose()


def test_joint_import_cash_cost_scope_and_idempotency(db):
    service.save_opening(db, "other", {"effective_at": "2026-01-01T00:00:00Z", "cash": {"CNY": "500"}, "positions": []})
    service.save_trade(db, {"account_id": "other", "effective_at": "2026-01-02T02:00:00Z", "code": "CN.510000",
        "market": "CN", "asset_type": "etf", "currency": "CNY", "quantity": "3", "price": "10", "side": "BUY"})
    before = service.overview(db, "other")
    assert D(before["current"]["total_assets"]) == D("500")
    batch = prepare(*sources())
    report = replace_ledger(db, "gf", batch, commit=True)
    assert report["records"] == 6 and report["cash"]["CNY"] == "864.0"
    assert D(report["cost"]) == D("36")
    assert D(report["closed_profit"]) == 0
    overview = service.overview(db, "gf")
    assert overview["current"]["total_assets"] is None
    assert all(p["cumulative_return"] is None and p["profit"] is None for p in overview["points"])
    assert overview["current"]["positions"][0]["price"] is None
    assert service.overview(db, "other")["current"] == before["current"]
    assert replace_ledger(db, "gf", batch, commit=True)["status"] == "already_imported"
    assert len(list(db.scalars(select(Deal).where(Deal.account_id == "gf", Deal.is_void.is_(False))))) == 2


def test_preview_and_failed_replacement_leave_no_partial_rows(db):
    batch = prepare(*sources())
    replace_ledger(db, "gf", batch)
    assert db.get(PortfolioOpening, "gf") is None
    bad = deepcopy(batch)
    bad["expected"]["cash"] = "1"
    with pytest.raises(ValueError, match="现金"):
        replace_ledger(db, "gf", bad, commit=True)
    assert db.get(PortfolioOpening, "gf") is None
    assert not list(db.scalars(select(Deal).where(Deal.account_id == "gf")))


def test_source_conflict_duplicate_and_missing_cash_fail():
    flows, statements = sources()
    broken = deepcopy(statements)
    broken[0]["清算金额"] = "-99"
    with pytest.raises(ValueError, match="不一致"):
        prepare(flows, broken)
    with pytest.raises(ValueError, match="重复"):
        prepare(flows, [*statements, statements[0]])
    missing = deepcopy(flows)
    missing[0]["发生金额"] = "999"
    with pytest.raises(ValueError, match="不连续"):
        prepare(missing, statements)


def test_imported_ledger_carries_prior_valuation_but_never_uses_future_quotes(db):
    replace_ledger(db, "gf", prepare(*sources()), commit=True)
    service.save_event(db, {"account_id": "gf", "kind": "valuation", "effective_at": "2026-01-07T07:00:00Z",
        "data": {"prices": [{"code": "CN.510000", "market": "CN", "asset_type": "etf", "currency": "CNY",
                             "unit": "share", "price": "7", "at": "2026-01-07T07:00:00Z"}]}})
    assert service.overview(db, "gf")["current"]["total_assets"] == "934.0"
    service.save_event(db, {"account_id": "gf", "kind": "interest", "effective_at": "2026-01-08T07:00:00Z", "data": {"amount": "1"}})
    result = service.overview(db, "gf")
    assert result["current"]["total_assets"] == "935.0"
    assert result["current"]["positions"][0]["quote"]["at"] == "2026-01-07T07:00:00Z"
    assert not result["current"]["issues"]
    assert result["points"][-1]["total_assets"] == "935.0"
    assert service.overview(db, "gf", "2026-01-08T07:00:00Z")["current"]["total_assets"] == "935.0"
    assert service.overview(db, "gf", "2026-01-06T07:00:00Z")["current"]["positions"][0]["price"] is None
    assert result["current"]["cumulative_return"] is None  # Earlier funding really lacks valuations.
    assert result["current"]["performance_needs"]
    # The legacy readers must show the same present values, without writing snapshots.
    assert service.projection_positions(db, "gf")[0].current_price == 7
    assert service.projection_accounts(db, "gf")[0].total_assets == 935


def test_explicit_estimate_is_labelled_and_cross_account_trade_does_not_replace_it(db):
    replace_ledger(db, "gf", prepare(*sources()), commit=True)
    def quote(price, day, kind="price"):
        service.save_event(db, {"account_id": "gf", "kind": "valuation", "effective_at": f"2026-01-{day}T07:00:00Z",
            "data": {"prices": [{"code": "CN.510000", "market": "CN", "asset_type": "etf", "currency": "CNY",
                "unit": "share", "price": price, "at": f"2026-01-{day}T07:00:00Z", "price_kind": kind}]}})
    quote("7", "07")
    quote("90", "08", "estimate")
    current = service.overview(db, "gf")["current"]
    assert current["positions"][0]["price"] == "90" and current["quality"] == "estimated"
    service.save_opening(db, "other", {"effective_at": "2026-01-01T00:00:00Z", "cash": {"CNY": "500"}, "positions": []})
    service.save_trade(db, {"account_id": "other", "effective_at": "2026-01-09T07:00:00Z", "code": "CN.510000",
        "market": "CN", "asset_type": "etf", "currency": "CNY", "quantity": "1", "price": "100", "side": "BUY"})
    assert service.overview(db, "gf")["current"]["positions"][0]["price"] == "90"
    quote("8", "10")
    assert service.overview(db, "gf")["current"]["positions"][0]["price"] == "8"
    service.save_event(db, {"account_id": "gf", "kind": "share_credit", "effective_at": "2026-01-11T07:00:00Z",
        "data": {"code": "CN.510000", "market": "CN", "asset_type": "etf", "currency": "CNY", "unit": "share", "quantity": "10"}})
    assert service.overview(db, "gf")["current"]["positions"][0]["price"] is None


def test_reimport_detects_edited_records_and_opening_keeps_price_policy(db):
    batch = prepare(*sources())
    replace_ledger(db, "gf", batch, commit=True)
    service.save_opening(db, "gf", {"effective_at": batch["start"], "positions": [], "cash": {"CNY": "0"}}, correction=True)
    assert db.get(PortfolioOpening, "gf").data["valuation_policy"] == "explicit_only"
    deal = db.scalar(select(Deal).where(Deal.account_id == "gf"))
    deal.ledger_data = {**deal.ledger_data, "note": "changed"}
    db.commit()
    with pytest.raises(ValueError, match="现有账目已更改"):
        replace_ledger(db, "gf", batch, commit=True)


def test_link_legacy_cash_dividend_adds_metadata_without_reposting_cash(db):
    batch = prepare(*sources())
    replace_ledger(db, "gf", batch, commit=True)
    row = db.scalar(select(PortfolioEvent).where(PortfolioEvent.kind == "dividend"))
    row.data = {k: v for k, v in row.data.items() if k not in {"code", "name", "market", "asset_type", "unit", "quantity"}}
    db.commit()
    before = service.calculate(db, "gf")["ledger"].accounts["gf"]["cash"]["CNY"]
    assert link_existing_dividends(db, "gf", batch) == 1
    service.validate(db)
    db.commit()
    result = service.calculate(db, "gf")
    assert result["ledger"].accounts["gf"]["cash"]["CNY"] == before
    assert result["current"]["positions"][0]["dividends"] == 5
    assert link_existing_dividends(db, "gf", batch) == 0
