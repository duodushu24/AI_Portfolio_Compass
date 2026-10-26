"""Manage imported holding observations independently from enrolled accounting facts."""
from decimal import Decimal

from sqlalchemy import select

from app.models import Account, HoldingObservationBatch, PortfolioOpening, PositionSnapshot
from .ledger import ASSET_UNITS, ZERO, number
from .performance import instant, iso, public, replay
from .security_names import security_code

TYPE_ALIASES = {"股票": "stock", "基金": "fund", "债券": "bond", "ETF": "etf", "贵金属": "precious_metal"}


def identity(row, account):
    saved = (row.reconciliation_data or {}).get("match")
    if saved:
        return saved["code"], saved["currency"], saved["unit"]
    code = security_code(row.code, row.market)
    kind = TYPE_ALIASES.get(row.asset_type, row.asset_type)
    unit = row.unit or ASSET_UNITS.get(kind)
    curr = (row.raw_currency or account.base_currency).upper()
    return (code, curr, unit) if code and unit and curr in {"CNY", "USD", "HKD"} else None


def _source_label(row, batch):
    source = (batch.source if batch else "") or row.sync_id or ""
    if source.startswith(("import_excel", "excel")):
        return "Excel 导入"
    if source.startswith(("manual", "手工")):
        return "手工录入"
    if "futu" in source.lower():
        return "富途同步"
    return "导入资料" if source else "未记录"


def list_records(db, account_id):
    account = db.get(Account, account_id)
    if not account:
        raise ValueError("账户不存在")
    batches = {b.id: b for b in db.scalars(select(HoldingObservationBatch).where(HoldingObservationBatch.account_id == account_id))}
    rows = db.scalars(select(PositionSnapshot).where(PositionSnapshot.account_id == account_id)
                      .order_by(PositionSnapshot.snapshot_time.desc(), PositionSnapshot.id.desc()))
    return {"enrolled": db.get(PortfolioOpening, account_id) is not None, "items": [
        {"id": r.id, "account_id": r.account_id, "code": r.code, "name": r.name,
         "source": _source_label(r, batches.get(r.batch_id)), "source_at": iso(r.snapshot_time),
         "imported_at": iso(batches[r.batch_id].created_at) if r.batch_id in batches else None,
         "currency": r.raw_currency or account.base_currency, "unit": r.unit or ASSET_UNITS.get(TYPE_ALIASES.get(r.asset_type, r.asset_type)),
         "asset_type": r.asset_type, "quantity": str(r.quantity), "price": str(r.current_price),
         "average_cost": str(r.average_cost) if r.cost_method == "diluted" else None,
         "cost_method": r.cost_method, "is_void": bool(r.is_void),
         "enabled": (r.reconciliation_data or {}).get("enabled", True),
         "match": (r.reconciliation_data or {}).get("match")}
        for r in rows]}


def update_record(db, account_id, record_id, changes):
    row = db.get(PositionSnapshot, record_id)
    if not row or row.account_id != account_id:
        raise ValueError("导入记录不存在")
    if not changes or changes.keys() - {"enabled", "is_void", "match"}:
        raise ValueError("仅能修改核对状态、对应标的或删除状态")
    try:
        data = dict(row.reconciliation_data or {})
        for field in ("enabled", "is_void"):
            if field in changes:
                if not isinstance(changes[field], bool):
                    raise ValueError("状态必须为布尔值")
                if field == "is_void":
                    row.is_void = changes[field]
                else:
                    data[field] = changes[field]
        if "match" in changes:
            target = changes["match"]
            if target is None:
                data.pop("match", None)
            else:
                if not isinstance(target, dict):
                    raise ValueError("请选择有效的对应标的")
                from .service import calculate
                current = calculate(db, account_id, row.snapshot_time, compact=True)["current"]
                choices = current["positions"] if current else []
                match = next((p for p in choices if all(p[k] == target.get(k) for k in ("code", "currency", "unit"))), None)
                source = identity(row, db.get(Account, account_id))
                source_unit = source[2] if source else row.unit
                compatible = match and (match["unit"] == source_unit or {match["unit"], source_unit} <= {"share", "fund_unit"})
                if not compatible or match["currency"] != (row.raw_currency or db.get(Account, account_id).base_currency):
                    raise ValueError("请选择当时账目中同币种、数量单位相容的标的；核对不进行单位换算")
                data["match"] = {k: match[k] for k in ("code", "currency", "unit")}
        row.reconciliation_data = data
        if "is_void" in changes and not db.get(PortfolioOpening, account_id):
            from app.services.return_history import refresh_observations
            refresh_observations(db)
        db.commit()
        return {"id": row.id}
    except Exception:
        db.rollback()
        raise


def reconcile(db, account_id, source_ids=None, *, include_equal=False):
    from app.services.holding_history import positions_as_of
    from .service import facts
    account, opening = db.get(Account, account_id), db.get(PortfolioOpening, account_id)
    if not account or not opening:
        return []
    history, cache, seen, results = facts(db), {}, set(), []

    def at_time(at):
        at = instant(at)
        if at not in cache:
            cache[at] = replay(*history, scope=account_id, until=at, compact=True)["current"]
        return cache[at]

    def compare(k, at, quantity, name, source_id=None, average=None, compare_cost=False, proven_absent=False):
        marker = (source_id, k, instant(at))
        if marker in seen:
            return
        seen.add(marker)
        current = at_time(at)
        positions = current["positions"] if current else []
        p = next((p for p in positions if (p["code"], p["currency"], p["unit"]) == k), None)
        item = {"source_id": source_id, "name": name, "code": k[0] if k else "", "currency": k[1] if k else "",
                "unit": k[2] if k else None, "source_at": iso(at), "source_quantity": str(quantity),
                "source_average_cost": str(average) if compare_cost else None,
                "ledger_quantity": None, "ledger_average_cost": None}
        if instant(at) < opening.effective_at:
            item.update(status="uncovered", reason="资料日期早于账户起点，当前无法核对")
        elif not p and not proven_absent:
            item.update(status="unmatched", reason="未能匹配同一标的、币种和数量单位，请确认对应标的",
                        candidates=[{n: p[n] for n in ("code", "name", "currency", "unit")} for p in positions])
        else:
            ledger_q, ledger_avg = (p["quantity"], p["average_cost"]) if p else (ZERO, None)
            item.update(ledger_quantity=str(ledger_q), ledger_average_cost=str(ledger_avg) if compare_cost and ledger_avg is not None else None)
            q_diff = abs(ledger_q - number(quantity)) > Decimal("0.00000001")
            c_diff = compare_cost and ledger_q > ZERO and (ledger_avg is None or abs(ledger_avg - number(average)) > Decimal("0.000001"))
            item.update(status="mismatch" if q_diff or c_diff else "equal",
                        reason="同一时点的数量不同" if q_diff else "同一时点的摊薄成本不同" if c_diff else "核对一致")
        if item["status"] != "equal" or include_equal:
            results.append(item)

    if source_ids is None:
        rows = positions_as_of(db, account_id)
    else:
        rows = list(db.scalars(select(PositionSnapshot).where(PositionSnapshot.account_id == account_id, PositionSnapshot.id.in_(source_ids))))
        if len(rows) != len(set(source_ids)):
            raise ValueError("部分导入记录不存在，请刷新后重试")
    for row in rows:
        if row.is_void or (row.reconciliation_data or {}).get("enabled", True) is False:
            continue
        compare(identity(row, account), row.snapshot_time, row.quantity, row.name or row.code, row.id,
                row.average_cost, row.cost_method == "diluted")
        if results and results[-1]["source_id"] == row.id and not results[-1]["code"]:
            results[-1].update(code=row.code, currency=row.raw_currency or account.base_currency)
    # A disabled/deleted member makes a full batch unsuitable for absence checks.
    full_scopes = {}
    for batch in db.scalars(select(HoldingObservationBatch).where(HoldingObservationBatch.account_id == account_id,
            HoldingObservationBatch.completeness == "full").order_by(HoldingObservationBatch.observed_at, HoldingObservationBatch.id)):
        full_scopes[batch.market] = batch
    for market, batch in full_scopes.items():
        members = list(db.scalars(select(PositionSnapshot).where(PositionSnapshot.batch_id == batch.id)))
        if source_ids is not None and not {r.id for r in members} <= set(source_ids):
            continue
        if any(r.is_void or (r.reconciliation_data or {}).get("enabled", True) is False or identity(r, account) is None for r in members):
            continue
        current = at_time(batch.observed_at)
        source_keys = {identity(r, account) for r in positions_as_of(db, account_id, batch.observed_at)}
        for p in current["positions"] if current else []:
            k = (p["code"], p["currency"], p["unit"])
            # An unresolved same-code unit must not also become a false absence.
            if p["quantity"] and (not market or p["market"] == market) and k not in source_keys and not any(i and i[0] == p["code"] for i in source_keys):
                compare(k, batch.observed_at, ZERO, p["name"], proven_absent=True)
    return public(results)
