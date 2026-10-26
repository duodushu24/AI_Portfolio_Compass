from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import data_sources

router = APIRouter(prefix="/api/data-sources", tags=["data-sources"])


def call(action):
    try:
        return action()
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("")
def catalog(db: Session = Depends(get_db)):
    return data_sources.catalog(db)


@router.put("/{provider_id}")
def configure(provider_id: str, payload: dict = Body(...), db: Session = Depends(get_db)):
    return call(lambda: data_sources.save_config(db, provider_id, payload))


@router.post("/{provider_id}/check")
def check(provider_id: str, payload: dict = Body(default_factory=dict), db: Session = Depends(get_db)):
    return call(lambda: data_sources.probe(db, provider_id, str(payload.get("data_type") or "quote")))
