from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, AccountSnapshot, Deal, PortfolioEvent, PortfolioOpening, PositionSnapshot, QuoteSummary
from .ledger import ASSETS, ZERO, currency, key, number
from .performance import instant, iso, public, replay


def facts(db):
    db.flush()
    return (list(db.scalars(select(PortfolioOpening))),
            list(db.scalars(select(Deal).where(Deal.ledger_data != {}))),
            list(db.scalars(select(PortfolioEvent))))


def calculate(db, scope="all", until=None):
    return replay(*facts(db), scope=scope, until=until or datetime.now(timezone.utc).replace(tzinfo=None))


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
    result["unit"] = str(data.get("unit") or ("fund_unit" if result["asset_type"] == "fund" else "share"))
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
    if result["asset_type"] not in ASSETS or result["unit"] not in {"share", "fund_unit"}:
        raise ValueError("此资产类型或数量单位尚未支持明确的现金记账")
    if (result["asset_type"] == "fund") != (result["unit"] == "fund_unit"):
        raise ValueError("场外基金按 fund_unit 份额记账，其余已支持证券按 share 数量记账")
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
        if instant(item["at"]) > at or item["price_kind"] not in {"price", "nav", "estimate"}:
            raise ValueError("报价类型无效或实际报价时间晚于记录时间")
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


def save_opening(db, account_id, payload, correction=False):
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
        item["average_cost"] = None if item.get("average_cost") in (None, "") else str(number(item["average_cost"], minimum=ZERO))
        item["cost_cny_amount"] = None if item.get("cost_cny_amount") in (None, "") else str(number(item["cost_cny_amount"], minimum=ZERO))
        if item["currency"] == "CNY" and item["average_cost"] is not None:
            item["cost_cny_amount"] = str(number(item["average_cost"]) * number(item["quantity"]))
        if item.get("price") not in (None, ""):
            prices.append({**item, "at": item.get("price_at") or iso(at)})
        positions.append(item)
    prices = list({key(asset(p)): p for p in prices}.values())
    cash = {currency(c): str(number(v, minimum=ZERO)) for c, v in payload.get("cash", {}).items()}
    liabilities = {currency(c): str(number(v, minimum=ZERO)) for c, v in payload.get("liabilities", {}).items()}
    data = {"positions": positions, "cash": cash, "liabilities": liabilities, "effective_at": iso(at),
            "source": str(payload.get("source") or "用户确认期初"), **quotes({"prices": prices, "fx": payload.get("fx", {})}, at)}
    included_at = instant(payload.get("included_at") or at) if payload.get("included", True) else None
    excluded_at = instant(payload["excluded_at"]) if payload.get("excluded_at") else None
    if included_at and (included_at < at or excluded_at and excluded_at <= included_at):
        raise ValueError("账户纳入不能早于建档，移出必须晚于纳入")
    def write():
        row = previous or PortfolioOpening(account_id=account_id)
        row.effective_at, row.included_at, row.excluded_at, row.data = at, included_at, excluded_at, data
        db.add(row)
        return account_id
    return transaction(db, write)


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


FUNDS = {"deposit", "withdrawal", "transfer", "dividend", "interest", "fee", "fx", "subscription", "settle", "cancel_subscription", "split", "position_transfer"}


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
        if kind in {"split", "position_transfer"}:
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


def overview(db, scope="all", until=None, code=None):
    result = calculate(db, scope, until)
    points = result["points"]
    if code:
        points = [{**p, "positions": [i for i in p["positions"] if i["code"] == code]} for p in points]
        points = [p for p in points if p["positions"]]
    openings, deals, events = facts(db)
    ids = {o.account_id for o in openings} if scope == "all" else {scope}
    records = [{"id": d.id, "category": "trade", "kind": "trade", "account_id": d.account_id,
                "effective_at": iso(d.deal_time), "data": d.ledger_data, "is_void": d.is_void}
               for d in deals if d.account_id in ids and (not code or d.code == code)]
    records += [{"id": e.id, "category": "event", "kind": e.kind, "account_id": e.account_id,
                 "effective_at": iso(e.effective_at), "data": e.data, "is_void": e.is_void}
                for e in events if (e.account_id in ids or e.data.get("to_account_id") in ids) and (not code or e.data.get("code") == code or any(p["code"] == code for p in e.data.get("prices", [])))]
    return public({"scope": scope, "currency": "CNY", "current": points[-1] if points else None, "points": points,
        "records": sorted(records, key=lambda r: (r["effective_at"], r["category"], r["id"]), reverse=True),
        "openings": [{"account_id": o.account_id, "effective_at": iso(o.effective_at), "included": o.included_at is not None,
                      "included_at": iso(o.included_at) if o.included_at else None, "excluded_at": iso(o.excluded_at) if o.excluded_at else None,
                      **o.data} for o in openings if o.account_id in ids]})


def source_opening(db, account_id):
    from app.services.holding_history import positions_as_of
    rows = positions_as_of(db, account_id)
    account = db.get(Account, account_id)
    if not account:
        raise ValueError("账户不存在")
    snapshot = db.scalar(select(AccountSnapshot).where(AccountSnapshot.account_id == account_id).order_by(AccountSnapshot.snapshot_time.desc()))
    return public({"account_id": account_id, "effective_at": iso(datetime.now(timezone.utc)), "included": True,
        "positions": [{"code": p.code, "name": p.name, "market": p.market, "asset_type": p.asset_type,
            "unit": "fund_unit" if p.asset_type == "fund" else "share", "currency": p.raw_currency or account.base_currency,
            "quantity": str(p.quantity), "average_cost": str(p.average_cost) if p.cost_method == "average" else None,
            "price": str(p.current_price) if p.current_price else None, "price_at": iso(p.snapshot_time),
            "cost_cny_amount": str(p.cost_cny_amount) if p.cost_cny_amount is not None else None,
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
    result = calculate(db, "all", now)
    at = instant(result["as_of"]) if result["as_of"] else now
    rows = []
    for aid in ids:
        if aid not in result["ledger"].accounts:
            continue
        current = result["prices"].value(result["ledger"], {aid}, at)
        total = current["total_assets"]
        for p in current["positions"]:
            if not include_closed and not p["quantity"]:
                continue
            row = PositionSnapshot(id=None, account_id=aid, code=p["code"], name=p["name"], market=p["market"], asset_type=p["asset_type"],
                quantity=float(p["quantity"]), average_cost=float(p["average_cost"] or ZERO), current_price=float(p["price"] or ZERO),
                raw_market_value=float(p["market_value"] or ZERO), raw_currency=p["currency"], normalized_market_value=float(p["market_value_cny"] or ZERO),
                normalized_currency="CNY", exchange_rate_to_base=float(number(p["fx"]["rate"])) if p["fx"] else None,
                position_weight=float(p["market_value_cny"] / total) if total and p["market_value_cny"] is not None else 0,
                profit_loss_ratio=float(p["holding_return"]) if p["holding_return"] is not None else 0,
                cost_method="average" if p["cost"] is not None else "unknown", cost_cny_amount=p["cost_cny"],
                position_layer=p["position_layer"], layer_source="ledger", layer_confidence="高", layer_reason="平均成本账目",
                missing_market_code=False, snapshot_time=max(instant(p["last_at"]), instant(p["quote"]["at"]) if p["quote"] else instant(p["last_at"])), sync_id="portfolio_ledger", is_void=False,
                first_buy_time=instant(p["first_at"]), last_trade_time=instant(p["last_at"]))
            row.ledger_result = public(p)
            rows.append(row)
    return rows


def projection_accounts(db, account_id=None):
    rows = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = calculate(db, "all", now)
    at = instant(result["as_of"]) if result["as_of"] else now
    for o in db.scalars(select(PortfolioOpening)):
        if account_id not in (None, "all", o.account_id):
            continue
        if account_id in (None, "all") and (o.included_at is None or o.included_at > now or o.excluded_at is not None and o.excluded_at <= now):
            continue
        if o.account_id in result["ledger"].accounts:
            p = result["prices"].value(result["ledger"], {o.account_id}, at)
            rows.append(AccountSnapshot(account_id=o.account_id, total_assets=float(p["total_assets"] or p["known_assets"]),
                cash=float(p["cash_value"] or ZERO), market_value=float(p["market_value"] or ZERO),
                raw_currency_values={"currency": "CNY", "ledger_quality": p["quality"], "ledger_total": public(p["total_assets"]), "ledger_cash": public(p["cash_value"]), "ledger_market": public(p["market_value"])},
                snapshot_time=at, sync_id="portfolio_ledger"))
    return rows


def reconcile(db, account_id):
    from app.services.holding_history import positions_as_of
    current = calculate(db, account_id)["current"]
    if not current:
        return []
    canonical = {p["code"]: p for p in current["positions"]}
    differences = []
    for row in positions_as_of(db, account_id):
        p = canonical.get(row.code)
        q, avg = (p["quantity"], p["average_cost"]) if p else (ZERO, None)
        if q != number(row.quantity) or row.cost_method == "average" and avg != number(row.average_cost):
            differences.append({"code": row.code, "source_at": iso(row.snapshot_time), "source_quantity": str(row.quantity),
                "ledger_quantity": str(q), "source_average_cost": str(row.average_cost), "ledger_average_cost": str(avg) if avg is not None else None})
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
            related = [p for p in book["positions"].values() if p["code"] == row["code"]]
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
    result = calculate(db)
    rows = {}
    for k, q in result["prices"].prices.items():
        code = k[0]
        if code in codes:
            rows[code] = QuoteSummary(code=code, current_price=float(number(q["price"])), quote_time=instant(q["at"]),
                provider=q["source"], sync_id="portfolio_ledger", is_delayed=q.get("price_kind") == "estimate", market=q.get("market", ""),
                exchange="", license_note="已确认账目采用的报价", change_ratio=0, volume=0, ma_summary={}, support_price=None, resistance_price=None)
    return rows
