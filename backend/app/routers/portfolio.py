from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.portfolio import service

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def call(action):
    try:
        return action()
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/overview")
def overview(account_id: str = "all", at: datetime | None = None, code: str | None = None, db: Session = Depends(get_db)):
    return call(lambda: service.overview(db, account_id, at, code))


@router.get("/closed")
def closed(account_id: str = "all", start: datetime | None = None, end: datetime | None = None,
           keyword: str = "", db: Session = Depends(get_db)):
    return call(lambda: service.closed_positions(db, account_id, start, end, keyword))


@router.get("/accounts/{account_id}/opening")
def opening(account_id: str, db: Session = Depends(get_db)):
    result = service.overview(db, account_id)["openings"]
    return call(lambda: {"confirmed": bool(result), "opening": result[0] if result else service.source_opening(db, account_id),
                         "reconciliation": service.reconcile(db, account_id) if result else []})


@router.put("/accounts/{account_id}/opening")
def save_opening(account_id: str, payload: dict = Body(...), correction: bool = False, db: Session = Depends(get_db)):
    call(lambda: service.save_opening(db, account_id, payload, correction))
    return service.overview(db, account_id)


@router.post("/trades")
def trade(payload: dict = Body(...), db: Session = Depends(get_db)):
    return {"id": call(lambda: service.save_trade(db, payload))}


@router.post("/accounts/{account_id}/history/preview")
def preview_history(account_id: str, payload: dict = Body(...), db: Session = Depends(get_db)):
    return call(lambda: service.rebuild_history(db, account_id, payload, preview=True))


@router.post("/accounts/{account_id}/history")
def save_history(account_id: str, payload: dict = Body(...), db: Session = Depends(get_db)):
    return call(lambda: service.rebuild_history(db, account_id, payload))


@router.put("/trades/{record_id}")
def edit_trade(record_id: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    return {"id": call(lambda: service.save_trade(db, payload, record_id))}


@router.post("/events")
def event(payload: dict = Body(...), db: Session = Depends(get_db)):
    return {"id": call(lambda: service.save_event(db, payload))}


@router.put("/events/{record_id}")
def edit_event(record_id: int, payload: dict = Body(...), db: Session = Depends(get_db)):
    return {"id": call(lambda: service.save_event(db, payload, record_id))}


@router.delete("/{category}/{record_id}")
def remove(category: str, record_id: int, db: Session = Depends(get_db)):
    if category not in {"trades", "events"}:
        raise HTTPException(404)
    return {"id": call(lambda: service.void(db, "trade" if category == "trades" else "event", record_id))}
