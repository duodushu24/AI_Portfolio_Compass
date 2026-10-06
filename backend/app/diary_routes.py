from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import InvestmentDiary
from app.schemas import InvestmentDiarySaveRequest
from app.services.investment_diary import diary_payload, list_diaries, retry_markdown, save_diary


router = APIRouter(prefix="/api/diaries", tags=["investment-diaries"])


@router.get("")
def diaries(
    start_date: date | None = None,
    end_date: date | None = None,
    q: str = Query("", max_length=200),
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(400, "开始日期不能晚于结束日期")
    return list_diaries(db, start_date, end_date, q, offset, limit)


def _get_diary(db: Session, diary_id: int) -> InvestmentDiary:
    item = db.get(InvestmentDiary, diary_id)
    if item is None:
        raise HTTPException(404, "日记不存在")
    return item


def _save(db: Session, request: InvestmentDiarySaveRequest, item: InvestmentDiary | None = None) -> dict:
    try:
        return save_diary(db, request, item)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500, "数据库保存未完成，请重新打开日记列表核对后再保存。") from None


@router.post("", status_code=201)
def create_diary(request: InvestmentDiarySaveRequest, db: Session = Depends(get_db)) -> dict:
    return _save(db, request)


@router.get("/{diary_id}")
def diary_detail(diary_id: int, db: Session = Depends(get_db)) -> dict:
    return {"item": diary_payload(_get_diary(db, diary_id))}


@router.put("/{diary_id}")
def edit_diary(diary_id: int, request: InvestmentDiarySaveRequest, db: Session = Depends(get_db)) -> dict:
    return _save(db, request, _get_diary(db, diary_id))


@router.post("/{diary_id}/retry-markdown")
def retry_diary_markdown(diary_id: int, db: Session = Depends(get_db)) -> dict:
    item = _get_diary(db, diary_id)
    try:
        return retry_markdown(db, item)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500, "文件保存状态未完成更新，请重新打开日记核对。") from None
