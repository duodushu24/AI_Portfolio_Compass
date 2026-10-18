from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models import Account, AccountSnapshot, Deal, HoldingObservationBatch, PortfolioEvent, PortfolioOpening, PositionSnapshot, QuoteSummary
from .ledger import ASSET_UNITS, ASSETS, ZERO, asset_unit, currency, key, number
from .performance import instant, iso, public, replay


def facts(db):
    db.flush()
    return (list(db.scalars(select(PortfolioOpening))),
            list(db.scalars(select(Deal).where(Deal.ledger_data != {}))),
            list(db.scalars(select(PortfolioEvent))))


@event.listens_for(Session, "after_flush")
def _ledger_changed(db, context):
    if any(isinstance(row, (PortfolioOpening, Deal, PortfolioEvent)) for row in db.new | db.dirty | db.deleted):
        db.info.pop("portfolio_calculations", None)


@event.listens_for(Session, "after_commit")
@event.listens_for(Session, "after_rollback")
def _transaction_ended(db):
    db.info.pop("portfolio_calculations", None)


def calculate(db, scope="all", until=None, *, compact=False):
    # Sessions are request-scoped. Never share a financial result across requests.
    db.flush()
    cache = db.info.setdefault("portfolio_calculations", {})
    cache_key = (scope, instant(until) if until else None, compact)
    if cache_key not in cache:
        cache[cache_key] = replay(*facts(db), scope=scope,
            until=until or datetime.now(timezone.utc).replace(tzinfo=None),
            latest_current=until is None, compact=compact)
    return cache[cache_key]


def enrolled(db, account_id):
    return db.get(PortfolioOpening, account_id) is not None


def validate(db):
    openings, deals, events = facts(db)
    replay(openings, deals, events)
    for row in openings:
        replay(openings, deals, events, row.account_id)


def transaction(db, action):
    try:
        result = action()
        db.flush()
        validate(db)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def asset(data):
    result = dict(data)
    result["code"] = str(data.get("code", "")).strip()
    result["currency"] = currency(data.get("currency", ""))
    result["market"] = str(data.get("market", "")).upper()
    if result["market"] in {"SH", "SZ", "BJ"}:
        result["market"] = "CN"
    result["asset_type"] = str(data.get("asset_type", "stock"))
    result["unit"] = asset_unit(result["asset_type"], data.get("unit"))
    if result["asset_type"] == "precious_metal":
        if not str(data.get("name") or "").strip():
            raise ValueError("请填写银行及黄金产品名称")
        if result["market"] != "CN" or result["currency"] != "CNY":
            raise ValueError("银行贵金属目前按境内 CNY、克单位记账")
        result["code"] = result["code"].upper() or f"CN.GOLD.{uuid4().hex.upper()}"
        if not result["code"].startswith("CN.GOLD."):
            raise ValueError("银行黄金请使用独立的 CN.GOLD.产品标识，不同银行产品不能共用代码")
    elif result["code"].upper().startswith("CN.GOLD."):
        raise ValueError("CN.GOLD.标识仅用于按克记账的银行贵金属")
    result["name"] = str(data.get("name") or result["code"]).strip()
    if not result["code"] or result["market"] not in {"CN", "HK", "US"}:
        raise ValueError("请填写标的代码和 CN/HK/US 市场")
    result["code"] = result["code"].upper()
    if "." not in result["code"]:
        result["code"] = result["market"] + "." + result["code"]
    prefix = result["code"].split(".", 1)[0]
    code_market = "CN" if prefix in {"CN", "SH", "SZ", "BJ", "FUND"} else prefix
    if code_market != result["market"]:
        raise ValueError("标的代码前缀与市场不一致")
    if result["asset_type"] not in ASSETS:
        raise ValueError("此资产类型或数量单位尚未支持明确的现金记账")
    if result["unit"] != ASSET_UNITS[result["asset_type"]]:
        raise ValueError("数量单位不匹配：场外基金用 fund_unit，贵金属用 gram，其余证券用 share")
    return result


def quotes(data, at):
    result = {"prices": [], "fx": {}}
    seen = set()
    for item in data.get("prices", []):
        item = asset(item)
        if key(item) in seen:
            raise ValueError("同一次更新中同标的、币种和单位只填写一次报价")
        seen.add(key(item))
        value = item.get("price")
        if value is None:
            continue
        item["price"] = str(number(value, minimum=ZERO))
        item["at"] = iso(item.get("at") or at)
        item["source"] = str(item.get("source") or "手工")
        item["price_kind"] = item.get("price_kind", "nav" if item["asset_type"] == "fund" else "price")
        if instant(item["at"]) > at or item["price_kind"] not in {"price", "nav", "estimate", "redemption", "bank_value"}:
            raise ValueError("报价类型无效或实际报价时间晚于记录时间")
        if item["price_kind"] in {"redemption", "bank_value"} and item["asset_type"] != "precious_metal":
            raise ValueError("银行黄金报价口径仅适用于贵金属")
        result["prices"].append({name: item[name] for name in ("code", "name", "market", "asset_type", "currency", "unit", "price", "at", "source", "price_kind")})
    for curr, item in data.get("fx", {}).items():
        curr = currency(curr)
        item = dict(item) if isinstance(item, dict) else {"rate": item}
        rate = number(item["rate"], minimum=Decimal("0.000000000001"))
        if curr == "CNY" and rate != 1:
            raise ValueError("CNY 本币汇率必须为 1")
        when = iso(item.get("at") or at)
        if instant(when) > at:
            raise ValueError("汇率实际时间晚于记录时间")
        result["fx"][curr] = {"rate": str(rate), "at": when, "source": str(item.get("source") or "手工")}
    return result


def save_opening(db, account_id, payload, correction=False, commit=True):
    if not db.get(Account, account_id):
        raise ValueError("账户不存在，请先在账户管理创建账户")
    previous = db.get(PortfolioOpening, account_id)
    if previous and not correction:
        raise ValueError("期初已确认；修改请使用期初纠错，日常数量变动记录买卖")
    at = instant(payload["effective_at"])
    positions, seen = [], set()
    prices = list(payload.get("prices", []))
    for item in payload.get("positions", []):
        item = asset(item)
        if key(item) in seen:
            raise ValueError("期初同标的币种单位不能重复")
        seen.add(key(item))
        item = {name: item.get(name) for name in ("code", "name", "market", "asset_type", "currency", "unit", "quantity", "average_cost", "price", "price_at", "cost_cny_amount", "position_layer", "source_position_id")}
        item["quantity"] = str(number(item["quantity"], minimum=ZERO))
        item["average_cost"] = None if item.get("average_cost") in (None, "") else str(number(item["average_cost"]))
        item["cost_cny_amount"] = None if item.get("cost_cny_amount") in (None, "") else str(number(item["cost_cny_amount"]))
        item["cost_method"] = "diluted"
        if item["currency"] == "CNY" and item["average_cost"] is not None:
            item["cost_cny_amount"] = str(number(item["average_cost"]) * number(item["quantity"]))
        if item.get("price") not in (None, ""):
            prices.append({**item, "at": item.get("price_at") or iso(at)})
        positions.append(item)
    prices = list({key(asset(p)): p for p in prices}.values())
    cash = {currency(c): str(number(v, minimum=ZERO)) for c, v in payload.get("cash", {}).items()}
    liabilities = {currency(c): str(number(v, minimum=ZERO)) for c, v in payload.get("liabilities", {}).items()}
    data = {"positions": positions, "cash": cash, "liabilities": liabilities, "cost_method": "diluted", "effective_at": iso(at),
            "source": str(payload.get("source") or "用户确认期初"), **quotes({"prices": prices, "fx": payload.get("fx", {})}, at)}
    if previous and previous.data.get("history_checkpoints"):
        data["history_checkpoints"] = deepcopy(previous.data["history_checkpoints"])
    if previous:
        for field in ("valuation_policy", "gf_import"):
            if field in previous.data:
                data[field] = deepcopy(previous.data[field])
    included_at = instant(payload.get("included_at") or at) if payload.get("included", True) else None
    excluded_at = instant(payload["excluded_at"]) if payload.get("excluded_at") else None
    if included_at and (included_at < at or excluded_at and excluded_at <= included_at):
        raise ValueError("账户纳入不能早于建档，移出必须晚于纳入")
    def write():
        row = previous or PortfolioOpening(account_id=account_id)
        row.effective_at, row.included_at, row.excluded_at, row.data = at, included_at, excluded_at, data
        db.add(row)
        return account_id
    return transaction(db, write) if commit else write()


def rebuild_history(db, account_id, payload, *, preview=False):
    """Move an existing opening backwards and add its missing history as one transaction."""
    def write():
        old = db.get(PortfolioOpening, account_id)
        if old is None:
            raise ValueError("请先设置账户起点；新账户可从零持仓和首笔入金开始")
        original = deepcopy(old.data)
        old_at, new_at = old.effective_at, instant(payload["opening"]["effective_at"])
        if new_at >= old_at:
            raise ValueError("补录历史的新起点必须早于原起点")
        before = calculate(db, account_id, old_at)["current"]
        start = {**payload["opening"], "positions": [], "liabilities": {}, "source": "从首笔交易前补录历史",
                 "included": old.included_at is not None,
                 "included_at": iso(new_at if old.included_at == old_at else old.included_at) if old.included_at else None,
                 "excluded_at": iso(old.excluded_at) if old.excluded_at else None}
        save_opening(db, account_id, start, correction=True, commit=False)
        db.flush()
        if not payload.get("records"):
            raise ValueError("请添加新起点至原起点之间的历史买卖或资金记录")
        for record in payload["records"]:
            at = instant(record["effective_at"])
            if not new_at <= at <= old_at:
                raise ValueError("本批历史记录必须位于新起点与原起点之间")
            if record["kind"] == "trade":
                save_trade(db, {**record["data"], "account_id": account_id, "effective_at": iso(at)}, commit=False)
            else:
                save_event(db, {"account_id": account_id, "kind": record["kind"], "effective_at": iso(at),
                                "data": record["data"]}, commit=False)
        # Keep the original dated prices as observations, not a second initialization.
        if original.get("prices") or original.get("fx"):
            save_event(db, {"account_id": account_id, "kind": "valuation", "effective_at": iso(old_at),
                "data": {"prices": original.get("prices", []), "fx": original.get("fx", {}), "note": "保留原起点报价依据"}}, commit=False)
        db.flush()
        validate(db)
        after = calculate(db, account_id, old_at)["current"]
        differences = []
        def check(label, expected, actual):
            if expected is None:
                return  # An unknown old cost is not an authoritative checkpoint.
            if actual is None or abs(number(expected) - number(actual)) > Decimal("0.000001"):
                differences.append({"item": label, "before": public(expected), "after": public(actual)})
        old_positions = {key(p): p for p in before["positions"]}
        new_positions = {key(p): p for p in after["positions"]}
        for k in old_positions.keys() | new_positions.keys():
            p, q = old_positions.get(k), new_positions.get(k)
            label = f"{k[0]} · {k[1]} · {k[2]}"
            check(label + " 数量", p["quantity"] if p else ZERO, q["quantity"] if q else ZERO)
            check(label + " 剩余成本", p["cost"] if p else ZERO, q["cost"] if q else ZERO)
        for field, label in (("cash", "现金"), ("liabilities", "负债")):
            b = {p["currency"]: p["amount"] for p in before[field]}
            a = {p["currency"]: p["amount"] for p in after[field]}
            for curr in b.keys() | a.keys():
                check(f"{curr} {label}", b.get(curr, ZERO), a.get(curr, ZERO))
        if before["pending"] != after["pending"]:
            differences.append({"item": "待确认 / 待到账款项", "before": "原起点款项", "after": "补录后的款项不同"})
        if not preview and differences and not payload.get("confirm_differences", False):
            raise ValueError("原起点的数量、成本或现金存在差异，请先试算核对并明确确认差异")
        checkpoint = {"effective_at": iso(old_at), "positions": original["positions"], "cash": original["cash"],
                      "liabilities": original.get("liabilities", {}), "source": original.get("source", "原期初")}
        old.data = {**old.data, "history_checkpoints": [*original.get("history_checkpoints", []), checkpoint]}
        return public({"checkpoint_at": iso(old_at), "new_start": iso(new_at), "differences": differences,
                       "current": calculate(db, account_id)["current"], "record_count": len(payload["records"])})
    if not preview:
        return transaction(db, write)
    try:
        return write()
    finally:
        db.rollback()  # A preview never leaves openings, events or deals behind.


def save_trade(db, payload, record_id=None, commit=True):
    account_id = str(payload["account_id"])
    opening = db.get(PortfolioOpening, account_id)
    if not opening:
        raise ValueError("请先确认该账户期初")
    at = instant(payload["effective_at"])
    if at < opening.effective_at:
        raise ValueError("成交早于建档，不能重复驱动期初账目")
    data = {name: value for name, value in asset(payload).items() if name in {"code", "name", "market", "asset_type", "currency", "unit"}}
    data["side"] = str(payload.get("side", "")).upper()
    if data["side"] not in {"BUY", "SELL"}:
        raise ValueError("买卖方向必须为 BUY/SELL")
    data["quantity"] = str(number(payload["quantity"], minimum=Decimal("0.000000000001")))
    data["price"] = str(number(payload["price"], minimum=ZERO))
    data["fees"] = str(number(payload.get("fees", 0), minimum=ZERO))
    data["settlement"] = payload.get("settlement", "cash")
    if data["settlement"] not in {"cash", "pending"} or data["side"] == "BUY" and data["settlement"] == "pending":
        raise ValueError("待到账仅用于已确认赎回；申购确认请关联待确认款")
    data["pending_id"] = payload.get("pending_id") or None
    data["note"] = str(payload.get("note", ""))
    data["source"] = str(payload.get("source") or "手工成交")
    data.update(quotes({"fx": payload.get("fx", {})}, at))
    row = db.get(Deal, record_id) if record_id else None
    if record_id and not row:
        raise ValueError("成交不存在")
    def write():
        nonlocal row
        row = row or Deal(deal_id=str(payload.get("deal_id") or f"manual_{uuid4().hex}"))
        conflict = db.scalar(select(Deal).where(Deal.account_id == account_id, Deal.deal_id == row.deal_id))
        if conflict and conflict.id != row.id:
            raise ValueError("该账户已有相同成交号；请核对来源记录，不能合并或覆盖另一笔成交")
        row.account_id, row.code, row.side = account_id, data["code"], data["side"]
        row.market, row.price, row.quantity, row.deal_time = data["market"], float(data["price"]), float(data["quantity"]), at
        row.ledger_data, row.is_void = public(data), False
        if not row.raw_payload:
            row.raw_payload = public(payload.get("raw_payload") or {"source": data["source"]})
        db.add(row)
        db.flush()
        return row.id
    return transaction(db, write) if commit else write()


FUNDS = {"deposit", "withdrawal", "transfer", "dividend", "interest", "fee", "fx", "subscription", "settle", "cancel_subscription", "split", "share_credit", "position_transfer"}


def save_event(db, payload, record_id=None, commit=True):
    account_id, kind, at = str(payload["account_id"]), str(payload["kind"]), instant(payload["effective_at"])
    if not enrolled(db, account_id):
        raise ValueError("请先确认账户期初")
    if kind != "valuation" and kind not in FUNDS:
        raise ValueError("无效记录类型")
    data = dict(payload.get("data", {}))
    data["note"] = str(data.get("note", ""))
    if kind == "valuation":
        # Market value input is converted once using the actual-time ledger quantity.
        state = calculate(db, account_id, at)["ledger"]
        book = state.accounts.get(account_id, {})
        for item in data.get("prices", []):
            if item.get("market_value") not in (None, ""):
                if item.get("price") not in (None, ""):
                    raise ValueError("价格和市值请任选一种输入")
                p = book.get("positions", {}).get(key(asset(item)))
                if not p or not p["quantity"]:
                    raise ValueError("输入市值需要该实际时点的持仓数量")
                item["price"] = str(number(item["market_value"], minimum=ZERO) / p["quantity"])
        data = {"note": data["note"], **quotes(data, at)}
        if not data["prices"] and not data["fx"]:
            raise ValueError("请至少填写一项价格、市值或汇率")
    else:
        data["currency"] = currency(data.get("currency", "CNY"))
        for field in ("amount", "fees"):
            data[field] = str(number(data.get(field, 0), minimum=ZERO))
        if kind == "dividend":
            if number(data["amount"]) <= number(data["fees"]):
                raise ValueError("净分红金额必须大于零")
            if not str(data.get("code") or "").strip():
                raise ValueError("现金分红请选择所属标的")
            data = asset(data)
            if data.get("cycle") not in (None, ""):
                cycle = number(data["cycle"], minimum=Decimal(1))
                if cycle != int(cycle):
                    raise ValueError("持有阶段编号必须为正整数")
                data["cycle"] = int(cycle)
            data["require_attribution"] = True
        if kind in {"transfer", "position_transfer"}:
            if data.get("to_account_id") == account_id or not enrolled(db, str(data.get("to_account_id", ""))):
                raise ValueError("转入端必须是另一个已建档账户")
        if kind == "fx":
            data["to_currency"] = currency(data.get("to_currency", ""))
            data["to_amount"] = str(number(data.get("to_amount"), minimum=Decimal("0.000000000001")))
            if data["currency"] == data["to_currency"]:
                raise ValueError("换汇需两种不同币种")
        if kind in {"settle", "cancel_subscription"} and not data.get("pending_id"):
            raise ValueError("请选择待确认/到账记录")
        if kind in {"split", "share_credit", "position_transfer"}:
            data = asset(data)
            field = "factor" if kind == "split" else "quantity"
            data[field] = str(number(data.get(field), minimum=Decimal("0.000000000001")))
        data.update(quotes({"fx": data.get("fx", {})}, at))
    row = db.get(PortfolioEvent, record_id) if record_id else None
    if record_id and not row:
        raise ValueError("记录不存在")
    def write():
        nonlocal row
        row = row or PortfolioEvent(created_at=datetime.now(timezone.utc).replace(tzinfo=None))
        row.account_id, row.kind, row.effective_at, row.data, row.is_void = account_id, kind, at, data, False
        db.add(row)
        db.flush()
        return row.id
    return transaction(db, write) if commit else write()


def void(db, category, record_id):
    row = db.get(Deal if category == "trade" else PortfolioEvent, record_id)
    if row is None or row.is_void or category == "trade" and not row.ledger_data:
        raise ValueError("有效账目不存在")
    def write():
        row.is_void = True
        return row.id
    return transaction(db, write)


def overview(db, scope="all", until=None, code=None, view="full"):
    if view not in {"full", "current", "chart", "records"}:
        raise ValueError("未知组合视图")
    result = calculate(db, scope, until, compact=view != "full")
    points = result["points"]
    if code:
        points = [{**p, "positions": [i for i in p["positions"] if i["code"] == code]} for p in points]
        points = [p for p in points if p["positions"]]
    if view == "chart":
        chart_fields = {"observed_at", "event_type", "record_id", "account_id", "interval", "ended",
                        "total_assets", "nav", "units", "profit", "opening_assets", "cumulative_return", "asset_returns"}
        points = [{k: v for k, v in p.items() if k in chart_fields} for p in points]
    openings, deals, events = facts(db)
    ids = {o.account_id for o in openings} if scope == "all" else {scope}
    name_ids = ids | {e.account_id for e in events if e.data.get("to_account_id") in ids}
    name_ids |= {e.data["to_account_id"] for e in events if e.account_id in ids and e.data.get("to_account_id")}
    account_names = {a.account_id: (a.display_name or "").strip() or (a.institution or "").strip() or "未命名账户"
                     for a in db.scalars(select(Account).where(Account.account_id.in_(name_ids)))}
    records = [{"id": d.id, "category": "trade", "kind": "trade", "account_id": d.account_id,
                "effective_at": iso(d.deal_time), "data": d.ledger_data, "is_void": d.is_void}
               for d in deals if d.account_id in ids and (not code or d.code == code)]
    records += [{"id": e.id, "category": "event", "kind": e.kind, "account_id": e.account_id,
                 "effective_at": iso(e.effective_at), "data": e.data, "is_void": e.is_void}
                for e in events if (e.account_id in ids or e.data.get("to_account_id") in ids) and (not code or e.data.get("code") == code or any(p["code"] == code for p in e.data.get("prices", [])))]
    now = instant(result["as_of"]) if result["as_of"] else datetime.now(timezone.utc).replace(tzinfo=None)
    included_ids = {o.account_id for o in openings if o.included_at and o.included_at <= now and (not o.excluded_at or o.excluded_at > now)}
    current = result["current"]
    if current and code:
        current = {**current, "positions": [p for p in current["positions"] if p["code"] == code]}
    return public({"scope": scope, "currency": "CNY", "account_names": account_names,
        "coverage": {"included_accounts": sorted(included_ids), "unenrolled_accounts": [a.account_id for a in db.scalars(select(Account)) if a.account_id not in {o.account_id for o in openings}]},
        "holdings": aggregate_assets(current["positions"]) if current else [],
        "allocation": allocation(current),
        "current": current, "points": points if view in {"full", "chart"} else [],
        "records": sorted(records, key=lambda r: (r["effective_at"], r["category"], r["id"]), reverse=True) if view in {"full", "records"} or code else [],
        "openings": [{"account_id": o.account_id, "effective_at": iso(o.effective_at), "included": o.included_at is not None,
                      "included_at": iso(o.included_at) if o.included_at else None, "excluded_at": iso(o.excluded_at) if o.excluded_at else None,
                      **o.data} for o in openings if o.account_id in ids]})


def point_detail(db, scope, at, event_type, owner_id, record_id=None, code=None):
    result = calculate(db, scope, at, compact=True)
    point = next((p for p in result["points"] if p["observed_at"] == iso(at) and p["event_type"] == event_type
                  and p["account_id"] == owner_id and p["record_id"] == record_id), None)
    if point is None:
        raise ValueError("收益记录不存在，请刷新后重试")
    if code:
        point = {**point, "positions": [p for p in point["positions"] if p["code"] == code]}
    return public(point)


def aggregate_assets(positions):
    """Merge compatible holdings on the server; keep their account rows for drilldown."""
    groups = {}
    for p in positions:
        groups.setdefault(key(p), []).append(p)
    merged = []
    for group in groups.values():
        active = [p for p in group if p["quantity"] > ZERO]
        if not active:
            continue
        p = {**active[0], "account_id": "all", "account_positions": active}
        for field in ("quantity", "cost", "cost_cny", "market_value", "market_value_cny", "floating", "realized", "realized_cny", "dividends", "dividends_cny", "position_weight"):
            rows = group if field in {"realized", "realized_cny"} else active
            p[field] = sum((r[field] for r in rows), ZERO) if all(r[field] is not None for r in rows) else None
        p["average_cost"] = p["cost"] / p["quantity"] if p["cost"] is not None else None
        p["diluted_cost"] = p["average_cost"]
        p["holding_return"] = p["floating"] / p["cost"] if p["cost"] is not None and p["cost"] > ZERO and p["floating"] is not None else None
        merged.append(p)
    return sorted(merged, key=lambda p: p["market_value_cny"] or ZERO, reverse=True)


def allocation(current):
    if not current or current["total_assets"] is None or current["total_assets"] <= ZERO:
        return []
    amounts = {}
    for p in current["positions"]:
        if p["quantity"]:
            amounts[p["asset_type"]] = amounts.get(p["asset_type"], ZERO) + p["market_value_cny"]
    for field in ("cash", "pending", "liabilities"):
        value = sum((p["value_cny"] for p in current[field]), ZERO)
        if value:
            amounts[field] = value if field != "liabilities" else -value
    return [{"type": kind, "weight": amount / current["total_assets"]} for kind, amount in amounts.items()]


def closed_positions(db, account_id="all", start=None, end=None, keyword=""):
    start, end = instant(start) if start else None, instant(end) if end else None
    if start and end and start > end:
        raise ValueError("开始日期不能晚于结束日期")
    result = calculate(db, compact=True)
    names = {a.account_id: a.display_name or a.institution or "未命名账户" for a in db.scalars(select(Account))}
    items = []
    for aid, book in result["ledger"].accounts.items():
        if account_id != "all" and aid != account_id:
            continue
        for p in book["positions"].values():
            if keyword.strip().casefold() not in f"{p['code']} {p['name']}".casefold():
                continue
            for c in p["closed_cycles"]:
                at = instant(c["closed_at"])
                if start and at < start or end and at > end:
                    continue
                # A snapshot/transfer is not proof of the original purchase date.
                items.append({**c, "account_id": aid, "account_name": names.get(aid, "未命名账户"),
                    **{n: p[n] for n in ("code", "name", "currency", "unit")},
                    "holding_days": (at.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8))).date()
                        - instant(c["opened_at"]).replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8))).date()).days if c["opening_kind"] == "buy" else None})
    items.sort(key=lambda r: (r["closed_at"], r["account_id"], r["code"], r["cycle"]), reverse=True)
    known = [r for r in items if r["realized"] is not None]
    cny = [r for r in items if r["realized_cny"] is not None]
    native = {}
    for row in known:
        native[row["currency"]] = native.get(row["currency"], ZERO) + row["realized"]
    return public({"items": items, "summary": {"count": len(items), "symbol_count": len({r["code"] for r in items}),
        "win_rate": number(sum(r["realized"] > ZERO for r in known)) / len(known) if known else None,
        "known_count": len(known), "unknown_count": len(items) - len(known),
        "realized_cny": sum((r["realized_cny"] for r in cny), ZERO) if len(cny) == len(items) else None,
        "known_realized_cny": sum((r["realized_cny"] for r in cny), ZERO),
        "missing_cny_count": len(items) - len(cny), "by_currency": native}})


def source_opening(db, account_id):
    from app.services.holding_history import positions_as_of
    rows = positions_as_of(db, account_id)
    account = db.get(Account, account_id)
    if not account:
        raise ValueError("账户不存在")
    snapshot = db.scalar(select(AccountSnapshot).where(AccountSnapshot.account_id == account_id).order_by(AccountSnapshot.snapshot_time.desc()))
    return public({"account_id": account_id, "effective_at": iso(datetime.now(timezone.utc)), "included": True,
        "positions": [{"code": p.code, "name": p.name, "market": p.market, "asset_type": p.asset_type,
            "unit": asset_unit(p.asset_type, p.unit), "currency": p.raw_currency or account.base_currency,
            "quantity": str(p.quantity), "average_cost": str(p.average_cost) if p.cost_method == "diluted" else None, "cost_method": p.cost_method,
            "price": str(p.current_price) if p.current_price else None, "price_at": iso(p.snapshot_time),
            "cost_cny_amount": str(p.cost_cny_amount) if p.cost_method == "diluted" and p.cost_cny_amount is not None else None,
            "source_position_id": p.id, "position_layer": p.position_layer} for p in rows],
        "cash": {account.base_currency: str(snapshot.cash if snapshot else account.cash)},
        "fx": {}, "source": "已有标准资料，待用户核对币种现金、期初均价和实际日期"})


def projection_positions(db, account_id=None, include_closed=False):
    # Transitional readers consume detached projections; never persist them as facts.
    openings = list(db.scalars(select(PortfolioOpening)))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ids = {o.account_id for o in openings if account_id in (None, "all", o.account_id)}
    if account_id in (None, "all"):
        ids &= {o.account_id for o in openings if o.included_at and o.included_at <= now and (o.excluded_at is None or o.excluded_at > now)}
    result = calculate(db, compact=True)
    at = instant(result["as_of"]) if result["as_of"] else now
    rows = []
    for aid in ids:
        if aid not in result["ledger"].accounts:
            continue
        current = result["prices"].value(result["ledger"], {aid}, at, latest=True)
        total = current["total_assets"]
        for p in current["positions"]:
            if not include_closed and not p["quantity"]:
                continue
            row = PositionSnapshot(id=None, account_id=aid, code=p["code"], name=p["name"], market=p["market"], asset_type=p["asset_type"],
                unit=p["unit"], quantity=float(p["quantity"]), average_cost=float(p["average_cost"] or ZERO), current_price=float(p["price"] or ZERO),
                raw_market_value=float(p["market_value"] or ZERO), raw_currency=p["currency"], normalized_market_value=float(p["market_value_cny"] or ZERO),
                normalized_currency="CNY", exchange_rate_to_base=float(number(p["fx"]["rate"])) if p["fx"] else None,
                position_weight=float(p["market_value_cny"] / total) if total and p["market_value_cny"] is not None else 0,
                profit_loss_ratio=float(p["holding_return"]) if p["holding_return"] is not None else 0,
                cost_method="diluted" if p["cost"] is not None else "unknown", cost_cny_amount=p["cost_cny"],
                position_layer=p["position_layer"], layer_source="ledger", layer_confidence="高", layer_reason="摊薄成本账目",
                missing_market_code=p["asset_type"] == "precious_metal", snapshot_time=max(instant(p["last_at"]), instant(p["quote"]["at"]) if p["quote"] else instant(p["last_at"])), sync_id="portfolio_ledger", is_void=False,
                first_buy_time=instant(p["first_at"]), last_trade_time=instant(p["last_at"]))
            row.ledger_result = public(p)
            rows.append(row)
    return rows


def projection_accounts(db, account_id=None):
    rows = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = calculate(db, compact=True)
    at = instant(result["as_of"]) if result["as_of"] else now
    for o in db.scalars(select(PortfolioOpening)):
        if account_id not in (None, "all", o.account_id):
            continue
        if account_id in (None, "all") and (o.included_at is None or o.included_at > now or o.excluded_at is not None and o.excluded_at <= now):
            continue
        if o.account_id in result["ledger"].accounts:
            p = result["prices"].value(result["ledger"], {o.account_id}, at, latest=True)
            rows.append(AccountSnapshot(account_id=o.account_id, total_assets=float(p["total_assets"] or p["known_assets"]),
                cash=float(p["cash_value"] or ZERO), market_value=float(p["market_value"] or ZERO),
                raw_currency_values={"currency": "CNY", "ledger_quality": p["quality"], "ledger_total": public(p["total_assets"]), "ledger_cash": public(p["cash_value"]), "ledger_market": public(p["market_value"])},
                snapshot_time=at, sync_id="portfolio_ledger"))
    return rows


def reconcile(db, account_id):
    from app.services.holding_history import positions_as_of
    opening = db.get(PortfolioOpening, account_id)
    if not opening:
        return []
    account = db.get(Account, account_id)
    history = facts(db)
    cache = {}
    def at_time(at):
        at = instant(at)
        if at not in cache:
            cache[at] = replay(*history, scope=account_id, until=at, compact=True)["current"]
        return cache[at]
    differences = []
    seen = set()
    def compare(code, curr, unit, at, q, avg=None, compare_cost=False):
        marker = (code, curr, unit, instant(at))
        if marker in seen:
            return
        seen.add(marker)
        current = at_time(at)
        p = next((p for p in current["positions"] if key(p) == (code, curr, unit)), None) if current else None
        item = {"code": code, "currency": curr, "unit": unit, "source_at": iso(at), "source_quantity": str(q),
                "source_average_cost": str(avg) if compare_cost else None}
        if instant(at) < opening.effective_at:
            differences.append({**item, "status": "uncovered", "ledger_quantity": None, "ledger_average_cost": None,
                                "reason": "来源日期早于账户统计起点，暂无法核对"})
            return
        quantity, average = (p["quantity"], p["average_cost"]) if p else (ZERO, None)
        quantity_differs = abs(quantity - number(q)) > Decimal("0.00000001")
        cost_differs = compare_cost and quantity > ZERO and (average is None or abs(average - number(avg)) > Decimal("0.000001"))
        if quantity_differs or cost_differs:
            differences.append({**item, "status": "mismatch", "ledger_quantity": str(quantity),
                "ledger_average_cost": str(average) if average is not None else None,
                "reason": "同一时点的数量不同" if quantity_differs else "同一时点的摊薄成本不同"})
    for row in positions_as_of(db, account_id):
        compare(row.code, row.raw_currency or account.base_currency, asset_unit(row.asset_type, row.unit),
                row.snapshot_time, row.quantity, row.average_cost, row.cost_method == "diluted")
    # Only a full observation proves that unlisted assets were absent. Partial imports do not.
    full_scopes = {}
    for batch in db.scalars(select(HoldingObservationBatch).where(HoldingObservationBatch.account_id == account_id,
            HoldingObservationBatch.completeness == "full").order_by(HoldingObservationBatch.observed_at, HoldingObservationBatch.id)):
        full_scopes[batch.market] = batch
    for market, batch in full_scopes.items():
        current = at_time(batch.observed_at)
        if current is None:
            continue
        rows = positions_as_of(db, account_id, batch.observed_at)
        source_keys = {(r.code, r.raw_currency or account.base_currency, asset_unit(r.asset_type, r.unit)) for r in rows}
        for p in current["positions"]:
            if p["quantity"] and (not market or p["market"] == market) and key(p) not in source_keys:
                compare(p["code"], p["currency"], p["unit"], batch.observed_at, ZERO)
    return differences


def ingest_quotes(db, rows, source):
    """Adapter quotes enter the same dated valuation facts as manual quotes."""
    if not list(db.scalars(select(PortfolioOpening.account_id))):
        return
    result = calculate(db)
    grouped = {}
    observed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    for row in rows:
        at = instant(row["quote_time"])
        for account_id, book in result["ledger"].accounts.items():
            related = [p for p in book["positions"].values() if p["code"] == row["code"] and p["asset_type"] != "precious_metal"]
            if not related:
                continue
            # A market quote has a single currency/unit; do not guess across ambiguous assets.
            if len({key(p) for p in related}) != 1:
                raise ValueError("同一行情代码对应不同币种/单位，需确认来源报价口径")
            p = related[0]
            grouped.setdefault((account_id, observed_at), []).append({**{n: p[n] for n in ("code", "name", "market", "asset_type", "currency", "unit")},
                "price": str(row["current_price"]), "at": iso(at), "source": str(row.get("provider") or source), "price_kind": "estimate" if row.get("is_delayed") else "price"})
            break  # One shared quote, not duplicate per account.
    for (account_id, at), prices in grouped.items():
        save_event(db, {"account_id": account_id, "kind": "valuation", "effective_at": at,
                       "data": {"prices": prices, "note": source}}, commit=False)


def projection_quotes(db, codes):
    result = calculate(db, compact=True)
    rows = {}
    for k, q in result["prices"].prices.items():
        code = k[0]
        if code in codes:
            rows[code] = QuoteSummary(code=code, current_price=float(number(q["price"])), quote_time=instant(q["at"]),
                provider=q["source"], sync_id="portfolio_ledger", is_delayed=q.get("price_kind") == "estimate", market=q.get("market", ""),
                exchange="", license_note="已确认账目采用的报价", change_ratio=0, volume=0, ma_summary={}, support_price=None, resistance_price=None)
    return rows
