from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, HoldingObservationBatch, PositionSnapshot, ReturnObservation
from app.services.holding_history import new_batch, positions_as_of, utc_naive
from app.services import return_history as service

router = APIRouter(prefix="/api/returns", tags=["returns"])


class PriceInput(BaseModel):
    position_id: int
    account_id: str
    code: str
    price: Decimal | None = Field(default=None, ge=0)
    price_at: datetime | None = None
    source: str = Field(default="手工", max_length=100)
    price_kind: Literal["price", "nav", "estimate"] = "price"
    fx_rate: Decimal | None = Field(default=None, gt=0)
    cost_cny_amount: Decimal | None = Field(default=None, gt=0)
    confirm_average_cost: bool = False


class ObservationInput(BaseModel):
    observed_at: datetime
    account_ids: list[str] = Field(min_length=1)
    currency: Literal["CNY", "HKD", "USD"] = "CNY"
    note: str = Field(default="", max_length=2000)
    inputs: list[PriceInput] = Field(default_factory=list)


@router.get("/draft")
def draft(account_id: str = "all", observed_at: datetime = Query(...), currency: Literal["CNY", "HKD", "USD"] = "CNY",
          account_ids: list[str] | None = Query(None), db: Session = Depends(get_db)):
    try: accounts = service.scope_accounts(db, account_id, account_ids)
    except ValueError as exc: raise HTTPException(400, str(exc)) from exc
    return {"account_ids": accounts, "items": service.draft(db, accounts, utc_naive(observed_at), currency)}


def save(db: Session, request: ObservationInput, row: ReturnObservation | None = None):
    accounts = sorted(set(request.account_ids))
    if any(not db.get(Account, a) for a in accounts): raise HTTPException(400, "账户不存在")
    at = utc_naive(request.observed_at)
    current = {(p.account_id, p.code): p for p in service.holdings(db, accounts, at)}
    expected = {key: p.id for key, p in current.items()}
    keys = [(i.account_id, i.code) for i in request.inputs]
    if len(keys) != len(set(keys)): raise HTTPException(400, "每个账户标的只能填写一项")
    for item in request.inputs:
        if expected.get((item.account_id, item.code)) != item.position_id:
            raise HTTPException(409, "持仓已变化，请重新读取该时点的持仓")
        if item.price is not None and (not item.price_at or not item.source.strip()):
            raise HTTPException(400, "价格需注明实际时间和来源")
        if item.price_at and utc_naive(item.price_at) > at:
            raise HTTPException(400, "不能使用观察时点之后的价格")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row = row or ReturnObservation(created_at=now)
    row.observed_at, row.account_ids, row.currency, row.note = at, accounts, request.currency, request.note
    inputs = []
    for i in request.inputs:
        value = i.model_dump(mode="json")
        value["price_at"] = service.iso(i.price_at) if i.price_at else None
        value["collected_at"] = service.iso(now)
        holding = current[(i.account_id, i.code)]
        value["holding_quantity"] = str(service.decimal(holding.quantity))
        value["holding_average_cost"] = str(service.decimal(holding.average_cost))
        value["holding_currency"] = holding.raw_currency.upper()
        value["price_currency"] = holding.raw_currency.upper()
        inputs.append(value)
    row.inputs = inputs
    service.recalculate(db, row)
    db.add(row)
    db.commit()
    return {"item": service.observation_dict(row)}


@router.post("/observations", status_code=201)
def create_observation(request: ObservationInput, db: Session = Depends(get_db)):
    return save(db, request)


@router.put("/observations/{observation_id}")
def edit_observation(observation_id: int, request: ObservationInput, db: Session = Depends(get_db)):
    row = db.get(ReturnObservation, observation_id)
    if not row: raise HTTPException(404, "记录不存在")
    return save(db, request, row)


@router.delete("/observations/{observation_id}")
def delete_observation(observation_id: int, db: Session = Depends(get_db)):
    row = db.get(ReturnObservation, observation_id)
    if not row: raise HTTPException(404, "记录不存在")
    db.delete(row)
    db.commit()
    return {"status": "deleted"}


@router.get("/history")
def history(account_id: str = "all", at: datetime | None = None, db: Session = Depends(get_db)):
    accounts = service.scope_accounts(db, account_id)
    query = select(PositionSnapshot).where(PositionSnapshot.account_id.in_(accounts))
    batch_query = select(HoldingObservationBatch).where(HoldingObservationBatch.account_id.in_(accounts))
    if at:
        query = query.where(PositionSnapshot.snapshot_time <= utc_naive(at))
        batch_query = batch_query.where(HoldingObservationBatch.observed_at <= utc_naive(at))
    excluded = service.excluded_sources(db)
    current = {p.id for p in positions_as_of(db, at=at, excluded_sync_ids=excluded) if p.account_id in accounts}
    batches = list(db.scalars(batch_query.order_by(HoldingObservationBatch.observed_at.desc())).all())
    completeness = {b.id: b.completeness for b in batches}
    return {"items": [{"id": p.id, "account_id": p.account_id, "code": p.code, "name": p.name,
        "quantity": p.quantity, "average_cost": p.average_cost, "cost_method": p.cost_method,
        "cost_cny_amount": str(p.cost_cny_amount) if p.cost_cny_amount else None,
        "current_price": p.current_price, "raw_currency": p.raw_currency, "snapshot_time": service.iso(p.snapshot_time),
        "market": p.market, "asset_type": p.asset_type, "position_layer": p.position_layer,
        "is_void": p.is_void, "is_current": p.id in current, "batch_id": p.batch_id,
        "completeness": completeness.get(p.batch_id, "unknown")}
        for p in db.scalars(query.order_by(PositionSnapshot.snapshot_time.desc(), PositionSnapshot.id.desc())).all() if p.sync_id not in excluded],
        "batches": [{"id": b.id, "account_id": b.account_id, "market": b.market, "completeness": b.completeness,
            "observed_at": service.iso(b.observed_at), "source": b.source} for b in batches if b.sync_id not in excluded],
        "current_ids": sorted(current)}


class EmptyScopeInput(BaseModel):
    observed_at: datetime
    market: str = ""
    confirmation: Literal["EMPTY_SCOPE"]


@router.post("/accounts/{account_id}/empty")
def confirm_empty(account_id: str, request: EmptyScopeInput, db: Session = Depends(get_db)):
    if not db.get(Account, account_id): raise HTTPException(404, "账户不存在")
    from app.services.providers import normalize_market
    market = normalize_market(request.market) if request.market else ""
    if request.market and market not in {"CN", "HK", "US"}: raise HTTPException(400, "市场范围无效")
    new_batch(db, account_id, request.observed_at, completeness="full", market=market, source="用户确认空仓")
    service.refresh_observations(db)
    db.commit()
    return {"status": "saved"}


@router.get("/series")
def series(account_id: str = "all", currency: Literal["CNY", "HKD", "USD"] = "CNY", start: datetime | None = None,
           end: datetime | None = None, account_ids: list[str] | None = Query(None), db: Session = Depends(get_db)):
    try: accounts = service.scope_accounts(db, account_id, account_ids)
    except ValueError as exc: raise HTTPException(400, str(exc)) from exc
    query = select(ReturnObservation).where(ReturnObservation.currency == currency)
    if start: query = query.where(ReturnObservation.observed_at >= utc_naive(start))
    if end: query = query.where(ReturnObservation.observed_at <= utc_naive(end))
    rows = [r for r in db.scalars(query.order_by(ReturnObservation.observed_at, ReturnObservation.id)).all() if r.account_ids == accounts]
    return {"account_ids": accounts, "currency": currency, "items": [service.observation_dict(r) for r in rows],
        "available_scopes": sorted({tuple(r.account_ids) for r in db.scalars(select(ReturnObservation).where(ReturnObservation.currency == currency)).all()}),
        "events": service.events(db, accounts, utc_naive(start) if start else None, utc_naive(end) if end else None),
        "other_scope_count": sum(r.account_ids != accounts for r in db.scalars(query).all()),
        "cumulative_available": False, "cumulative_reason": "累计收益需要成交成本结转及现金、入出金记录，将在后续阶段提供。"}
