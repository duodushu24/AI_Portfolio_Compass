from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Deal, HoldingObservationBatch, PositionSnapshot, ReturnObservation
from app.services.holding_history import positions_as_of, utc_naive


def excluded_sources(db: Session) -> set[str]:
    from app.services.sync import sample_template_sync_ids
    return sample_template_sync_ids(db)


def scope_accounts(db: Session, account_id: str, selected: list[str] | None = None) -> list[str]:
    if selected is not None:
        if not selected or any(not db.get(Account, a) for a in selected):
            raise ValueError("所选账户范围无效")
        return sorted(set(selected))
    if account_id != "all":
        if not db.get(Account, account_id):
            raise ValueError("账户不存在")
        return [account_id]
    return sorted(db.scalars(select(Account.account_id).where(Account.enabled == True)).all())  # noqa: E712


def holdings(db: Session, accounts: list[str], at: datetime, *, include_void: bool = False) -> list[PositionSnapshot]:
    return [p for p in positions_as_of(db, at=at, excluded_sync_ids=excluded_sources(db), include_void=include_void) if p.account_id in accounts]


def iso(value: datetime) -> str:
    return utc_naive(value).isoformat() + "Z"


def decimal(value) -> Decimal:
    return Decimal(str(value))


def recalculate(db: Session, observation: ReturnObservation) -> None:
    supplied = {(i["account_id"], i["code"]): i for i in observation.inputs}
    items = []
    known_cost = Decimal(0)
    known_value = Decimal(0)
    for row in holdings(db, observation.account_ids, observation.observed_at, include_void=True):
        if row.is_void:
            items.append({"position_id": row.id, "account_id": row.account_id, "code": row.code, "name": row.name,
                "quantity": None, "average_cost": None, "raw_currency": row.raw_currency, "cost_method": "unknown",
                "cost": None, "price": None, "fx_rate": None, "price_at": None, "source": "错误持仓记录已作废",
                "price_kind": "price", "collected_at": None, "stale": False,
                "problems": ["持仓记录已作废，数量和成本需重新核对"], "market_value": None, "pnl": None, "return_ratio": None})
            continue
        entry = supplied.get((row.account_id, row.code), {})
        q, avg = decimal(row.quantity), decimal(row.average_cost)
        raw_currency = row.raw_currency.upper()
        cost_method = row.cost_method
        same_cost_fact = (entry.get("position_id") == row.id
            and entry.get("holding_quantity") == str(q)
            and entry.get("holding_average_cost") == str(avg)
            and entry.get("holding_currency") == raw_currency)
        # Confirmation belongs to the selected holding fact; never reuse it for a replacement.
        if same_cost_fact and entry.get("confirm_average_cost"):
            cost_method = "average"
        price = decimal(entry["price"]) if entry.get("price") is not None else None
        price_currency = entry.get("price_currency", entry.get("holding_currency"))
        currency_mismatch = bool(price_currency and price_currency != raw_currency)
        if currency_mismatch:
            price = None
        rate = Decimal(1) if raw_currency == observation.currency else None
        if observation.currency == "CNY" and raw_currency != "CNY" and entry.get("fx_rate"):
            rate = decimal(entry["fx_rate"])
        raw_cost = q * avg if avg > 0 and cost_method == "average" else None
        supported_units = row.asset_type in {"stock", "fund", "etf", "leveraged_etf"}
        if not supported_units:
            raw_cost = None
        cost = raw_cost if raw_currency == observation.currency else None
        if observation.currency == "CNY" and raw_currency != "CNY" and raw_cost is not None:
            basis = row.cost_cny_amount
            if same_cost_fact and entry.get("cost_cny_amount"):
                basis = entry["cost_cny_amount"]
            cost = decimal(basis) if basis else None
        problems = []
        if currency_mismatch: problems.append("报价币种与持仓不一致，请重新核对观察")
        if not supported_units: problems.append("此资产的数量/报价单位尚未支持")
        if price is None: problems.append("缺少价格/净值")
        if raw_cost is None: problems.append("平均成本待核对")
        if cost is None and raw_cost is not None: problems.append("缺少已确认的折算成本")
        if rate is None: problems.append("缺少观察时汇率或币种不一致")
        value = q * price * rate if price is not None and rate is not None else None
        pnl = value - cost if value is not None and cost is not None else None
        roi = pnl / cost if pnl is not None and cost and cost > 0 else None
        price_at = entry.get("price_at")
        stale = bool(price_at and utc_naive(datetime.fromisoformat(price_at.replace("Z", "+00:00"))) < observation.observed_at)
        items.append({"position_id": row.id, "account_id": row.account_id, "code": row.code,
            "name": row.name, "quantity": str(q), "average_cost": str(avg), "raw_currency": raw_currency,
            "cost_method": cost_method, "cost": str(cost) if cost is not None else None,
            "price": str(price) if price is not None else None, "fx_rate": str(rate) if rate is not None else None,
            "price_at": price_at, "source": entry.get("source", ""), "price_kind": entry.get("price_kind", "price"),
            "collected_at": entry.get("collected_at"), "stale": stale, "problems": problems,
            "market_value": str(value) if value is not None else None,
            "pnl": str(pnl) if pnl is not None else None, "return_ratio": str(roi) if roi is not None else None})
        if roi is not None:
            known_cost += cost
            known_value += value
    complete = bool(items) and all(i["return_ratio"] is not None for i in items)
    excluded = excluded_sources(db)
    full_accounts = {b.account_id for b in db.scalars(select(HoldingObservationBatch).where(
        HoldingObservationBatch.completeness == "full", HoldingObservationBatch.market == "",
        HoldingObservationBatch.observed_at <= observation.observed_at)).all() if b.sync_id not in excluded}
    asset_returns = {}
    for code in {i["code"] for i in items}:
        group = [i for i in items if i["code"] == code]
        if any(i["return_ratio"] is None for i in group):
            asset_returns[code] = None
        else:
            cost = sum((decimal(i["cost"]) for i in group), Decimal(0))
            pnl = sum((decimal(i["pnl"]) for i in group), Decimal(0))
            asset_returns[code] = str(pnl / cost) if cost > 0 else None
    observation.result = {"items": items, "holding_count": len(items),
        "asset_returns": asset_returns,
        "scope_warning": any(a not in full_accounts for a in observation.account_ids),
        "covered_count": sum(i["return_ratio"] is not None for i in items),
        "status": "complete" if complete else "partial" if items else "empty",
        "return_ratio": str((known_value - known_cost) / known_cost) if complete and known_cost > 0 else None,
        "covered_cost": str(known_cost), "covered_market_value": str(known_value),
        "price_warning": any(i["stale"] or i["price_kind"] == "estimate" for i in items),
        "holdings_changed": any(i["position_id"] != supplied.get((i["account_id"], i["code"]), {}).get("position_id") for i in items)}


def refresh_observations(db: Session) -> None:
    db.flush()
    for row in db.scalars(select(ReturnObservation)).all():
        recalculate(db, row)


def observation_dict(row: ReturnObservation) -> dict:
    return {"id": row.id, "observed_at": iso(row.observed_at), "account_ids": row.account_ids,
            "currency": row.currency, "note": row.note, "inputs": row.inputs, **row.result}


def draft(db: Session, accounts: list[str], at: datetime, currency: str) -> list[dict]:
    earlier = list(db.scalars(select(ReturnObservation).where(ReturnObservation.observed_at <= at)
                   .order_by(ReturnObservation.observed_at.desc(), ReturnObservation.id.desc())).all())
    result = []
    for row in holdings(db, accounts, at):
        last_input = next((i for obs in earlier for i in obs.inputs
                           if i.get("position_id") == row.id and obs.currency == currency
                           and i.get("holding_quantity") == str(decimal(row.quantity))
                           and i.get("holding_average_cost") == str(decimal(row.average_cost))
                           and i.get("holding_currency") == row.raw_currency.upper()), {})
        result.append({"position_id": row.id, "account_id": row.account_id, "code": row.code,
            "name": row.name, "quantity": row.quantity, "average_cost": row.average_cost,
            "raw_currency": row.raw_currency, "snapshot_time": iso(row.snapshot_time),
            "cost_method": row.cost_method,
            "confirm_average_cost": row.cost_method == "average" or last_input.get("confirm_average_cost", False),
            "cost_cny_amount": last_input.get("cost_cny_amount") or (str(row.cost_cny_amount) if row.cost_cny_amount else None),
            "price": last_input.get("price", str(row.current_price) if row.current_price > 0 else None),
            "price_at": last_input.get("price_at", iso(row.snapshot_time)),
            "fx_rate": last_input.get("fx_rate"), "source": last_input.get("source", "持仓记录"),
            "price_kind": last_input.get("price_kind", "price")})
    return result


def events(db: Session, accounts: list[str], start: datetime | None = None, end: datetime | None = None) -> list[dict]:
    query = select(Deal).where(Deal.account_id.in_(accounts), Deal.deal_time.is_not(None))
    if start: query = query.where(Deal.deal_time >= start)
    if end: query = query.where(Deal.deal_time <= end)
    rows = db.scalars(query.order_by(Deal.deal_time, Deal.id)).all()
    result = []
    excluded = excluded_sources(db)
    for deal in rows:
        history = list(db.scalars(select(PositionSnapshot).where(PositionSnapshot.account_id == deal.account_id,
            PositionSnapshot.code == deal.code, PositionSnapshot.is_void == False)  # noqa: E712
            .order_by(PositionSnapshot.snapshot_time)).all())
        market = history[-1].market if history else deal.market
        boundaries = list(db.scalars(select(HoldingObservationBatch).where(
            HoldingObservationBatch.account_id == deal.account_id,
            HoldingObservationBatch.completeness == "full")).all())
        times = {p.snapshot_time for p in history if p.sync_id not in excluded}
        times.update(b.observed_at for b in boundaries if (not b.market or b.market == market) and b.sync_id not in excluded)
        before = max((at for at in times if at < deal.deal_time), default=None)
        after = min((at for at in times if at >= deal.deal_time), default=None)
        def fact(at):
            if at is None: return None
            p = next((p for p in positions_as_of(db, deal.account_id, at, excluded) if p.code == deal.code), None)
            return {"quantity": p.quantity if p else 0, "average_cost": p.average_cost if p else None,
                    "observed_at": iso(at)}
        result.append({"id": deal.id, "account_id": deal.account_id, "code": deal.code,
            "side": deal.side, "price": deal.price, "quantity": deal.quantity,
            "deal_time": iso(deal.deal_time), "fees": {k: (deal.raw_payload or {}).get(k) for k in ("fee", "commission", "tax")},
            "before": fact(before), "after": fact(after),
            "detail_note": "前后为最近持仓观察，未计算成交时点收益、归因及已实现盈亏。"})
    return result
