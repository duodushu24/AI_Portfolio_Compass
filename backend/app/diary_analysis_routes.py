from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.diary_schemas import (Candidate, DiscussionInput, GenerationInput, MergeTagInput, MessageInput,
                               SuggestTagsInput, SummaryInput, TagInput)
from app.models import DiaryDiscussionSession, DiarySummary, DiarySummaryTag, InvestmentTag
from app.services import diary_discussions as chats
from app.services import diary_summaries as summaries


router = APIRouter(tags=["diary-analysis"])


def mutate(db: Session, action):
    try:
        return action()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500, "数据库操作未完成，请重新打开记录核对保存状态后重试。") from None
    except HTTPException:
        db.rollback()
        raise


@router.get("/api/investment-tags")
def tag_list(db: Session = Depends(get_db)):
    return {"items": summaries.tags(db)}


@router.post("/api/investment-tags", status_code=201)
def create_tag(data: TagInput, db: Session = Depends(get_db)):
    def action():
        with summaries.write_lock:
            item = summaries.save_tag(db, data)
            db.commit()
            return {"item": summaries.tag_payload(item)}
    return mutate(db, action)


@router.put("/api/investment-tags/{tag_id}")
def edit_tag(tag_id: int, data: TagInput, db: Session = Depends(get_db)):
    def action():
        with summaries.write_lock:
            item = summaries.save_tag(db, data, summaries.get_item(db, InvestmentTag, tag_id))
            affected = list(db.scalars(select(DiarySummaryTag.summary_id).where(DiarySummaryTag.tag_id == tag_id)))
            return {"item": summaries.tag_payload(item), "file_errors": summaries.refresh_tag_files(db, affected)}
    return mutate(db, action)


@router.post("/api/investment-tags/{tag_id}/merge")
def merge_tag(tag_id: int, data: MergeTagInput, db: Session = Depends(get_db)):
    return mutate(db, lambda: summaries.merge_tag(db, tag_id, data.target_id))


@router.get("/api/diary-summaries")
def summary_list(start_date: date | None = None, end_date: date | None = None, q: str = Query("", max_length=200),
                 tag_id: int | None = None, offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100),
                 db: Session = Depends(get_db)):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(400, "开始日期不能晚于结束日期")
    return summaries.list_summaries(db, start_date, end_date, q, tag_id, offset, limit)


@router.get("/api/diary-summaries/{summary_id}")
def summary_detail(summary_id: int, db: Session = Depends(get_db)):
    return {"item": summaries.summary_payload(db, summaries.get_item(db, DiarySummary, summary_id))}


@router.post("/api/diary-summaries", status_code=201)
def create_summary(data: SummaryInput, db: Session = Depends(get_db)):
    return mutate(db, lambda: summaries.save_summary(db, data))


@router.put("/api/diary-summaries/{summary_id}")
def edit_summary(summary_id: int, data: SummaryInput, db: Session = Depends(get_db)):
    return mutate(db, lambda: summaries.save_summary(db, data, summaries.get_item(db, DiarySummary, summary_id)))


@router.post("/api/diary-summaries/{summary_id}/retry-markdown")
def retry_summary(summary_id: int, db: Session = Depends(get_db)):
    return mutate(db, lambda: summaries.retry_markdown(db, summaries.get_item(db, DiarySummary, summary_id)))


@router.get("/api/diary-discussions")
def discussion_list(record_date: date | None = None, diary_id: int | None = None,
                    offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100), db: Session = Depends(get_db)):
    statement = select(DiaryDiscussionSession)
    if record_date:
        statement = statement.where(DiaryDiscussionSession.record_date == record_date)
    if diary_id:
        from sqlalchemy import func
        ids = func.json_each(DiaryDiscussionSession.diary_ids).table_valued("value")
        statement = statement.where(select(1).select_from(ids).where(ids.c.value == diary_id).exists())
    from sqlalchemy import func
    count = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = db.scalars(statement.order_by(DiaryDiscussionSession.updated_at.desc()).offset(offset).limit(limit))
    return {"items": [chats.discussion_payload(db, v, False) for v in items], "count": count}


@router.post("/api/diary-discussions", status_code=201)
def create_discussion(data: DiscussionInput, db: Session = Depends(get_db)):
    return mutate(db, lambda: {"item": chats.create_discussion(db, data)})


@router.get("/api/diary-discussions/{session_id}")
def discussion_detail(session_id: int, db: Session = Depends(get_db)):
    return {"item": chats.discussion_payload(db, summaries.get_item(db, DiaryDiscussionSession, session_id))}


@router.put("/api/diary-discussions/{session_id}")
def save_candidate(session_id: int, data: Candidate, db: Session = Depends(get_db)):
    def action():
        with summaries.write_lock:
            item = summaries.get_item(db, DiaryDiscussionSession, session_id)
            if item.generation_status == "running":
                raise HTTPException(409, "正在生成，候选编辑暂不能保存")
            summaries.validate_tags(db, data.tag_ids)
            item.candidate, item.updated_at = data.model_dump(), summaries.now()
            db.commit()
            return {"item": chats.discussion_payload(db, item)}
    return mutate(db, action)


@router.post("/api/diary-discussions/{session_id}/messages", status_code=201)
def add_message(session_id: int, data: MessageInput, db: Session = Depends(get_db)):
    return mutate(db, lambda: chats.add_message(db, summaries.get_item(db, DiaryDiscussionSession, session_id), data))


@router.post("/api/diary-analysis/analyze")
def analyze(data: GenerationInput, db: Session = Depends(get_db)):
    return mutate(db, lambda: {"item": chats.generate(db, data, "analyze")})


@router.post("/api/diary-analysis/discuss")
def discuss(data: GenerationInput, db: Session = Depends(get_db)):
    return mutate(db, lambda: {"item": chats.generate(db, data, "discuss")})


@router.post("/api/diary-analysis/summarize")
def summarize(data: GenerationInput, db: Session = Depends(get_db)):
    return mutate(db, lambda: {"item": chats.generate(db, data, "summarize")})


@router.post("/api/diary-analysis/suggest-tags")
def suggest_tags(data: SuggestTagsInput, db: Session = Depends(get_db)):
    return chats.suggest_tags(db, data.body, data.consent_external_ai)
