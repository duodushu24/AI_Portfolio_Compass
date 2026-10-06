from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from threading import RLock

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import DATA_DIR, get_settings
from app.models import InvestmentDiary
from app.schemas import InvestmentDiarySaveRequest


# The local backend runs in one process. Serialize day-file regeneration so
# concurrent saves cannot overwrite another entry's newly committed content.
_save_lock = RLock()


def diary_root() -> Path:
    settings = get_settings()
    demo = settings.workspace == "demo" or "demo" in settings.database_url.lower()
    root = DATA_DIR / "demo_personal_knowledge" if demo else Path(settings.personal_knowledge_dir).expanduser()
    return root / "01_原始资料" / "复盘日记"


def day_path(record_date: date) -> Path:
    return diary_root() / str(record_date.year) / f"{record_date.month}月" / f"{record_date:%m.%d}.md"


def diary_payload(item: InvestmentDiary) -> dict:
    return {
        "id": item.id,
        "record_date": item.record_date.isoformat(),
        "title": item.title,
        "body": item.body,
        "topics": item.topics,
        "keywords": item.keywords,
        "source_type": item.source_type,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
        "markdown_path": str(day_path(item.record_date)),
        "markdown_saved": not item.pending_markdown_dates,
    }


def list_diaries(db: Session, start_date: date | None, end_date: date | None, query: str, offset: int, limit: int) -> dict:
    statement = select(InvestmentDiary)
    if start_date:
        statement = statement.where(InvestmentDiary.record_date >= start_date)
    if end_date:
        statement = statement.where(InvestmentDiary.record_date <= end_date)
    if query.strip():
        # contains(autoescape) treats user '%' and '_' as literal search text.
        topics = func.json_each(InvestmentDiary.topics).table_valued("value").alias("topics")
        keywords = func.json_each(InvestmentDiary.keywords).table_valued("value").alias("keywords")
        statement = statement.where(or_(
            InvestmentDiary.title.contains(query.strip(), autoescape=True),
            InvestmentDiary.body.contains(query.strip(), autoescape=True),
            select(1).select_from(topics).where(topics.c.value.contains(query.strip(), autoescape=True)).exists(),
            select(1).select_from(keywords).where(keywords.c.value.contains(query.strip(), autoescape=True)).exists(),
        ))
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = db.scalars(statement.order_by(InvestmentDiary.record_date.desc(), InvestmentDiary.id.desc()).offset(offset).limit(limit)).all()
    return {"items": [diary_payload(item) for item in items], "count": total, "root": str(diary_root())}


def save_diary(db: Session, request: InvestmentDiarySaveRequest, item: InvestmentDiary | None = None) -> dict:
    with _save_lock:
        now = datetime.now(timezone.utc)
        affected = set(item.pending_markdown_dates or []) if item else set()
        if item:
            affected.add(item.record_date.isoformat())
        else:
            item = InvestmentDiary(created_at=now, source_type="user")
        item.record_date = request.record_date
        item.title = request.title
        item.body = request.body
        item.topics = request.topics
        item.keywords = request.keywords
        item.updated_at = now
        affected.add(item.record_date.isoformat())
        item.pending_markdown_dates = sorted(affected)
        db.add(item)
        db.commit()  # A failed DB write never creates a Markdown file.
        return _write_pending(db, item)


def retry_markdown(db: Session, item: InvestmentDiary) -> dict:
    with _save_lock:
        # Also permits an explicit regeneration of the current day file.
        item.pending_markdown_dates = sorted(set(item.pending_markdown_dates or []) | {item.record_date.isoformat()})
        db.commit()
        return _write_pending(db, item)


def _write_pending(db: Session, item: InvestmentDiary) -> dict:
    failures = []
    remaining = []
    for value in item.pending_markdown_dates:
        record_date = date.fromisoformat(value)
        try:
            _write_day(db, record_date)
        except OSError as exc:
            remaining.append(value)
            failures.append(f"{value}：{exc}")
    item.pending_markdown_dates = remaining
    db.commit()
    db.refresh(item)
    return {
        "item": diary_payload(item),
        "database_saved": True,
        "markdown_saved": not remaining,
        "message": "原文已保存" if not remaining else "记录已入库，文件保存失败；可重试文件保存。",
        "file_errors": failures,
    }


def _write_day(db: Session, record_date: date) -> None:
    items = db.scalars(select(InvestmentDiary).where(InvestmentDiary.record_date == record_date).order_by(InvestmentDiary.id)).all()
    path = day_path(record_date)
    if not items:
        # A date correction may leave the old day empty. Keep a readable marker
        # rather than deleting an existing user file.
        if path.exists():
            path.write_text(f"# {record_date.isoformat()} 投资日记\n\n本日暂无记录，条目已调整日期。\n", encoding="utf-8")
        return
    blocks = [f"# {record_date.isoformat()} 投资日记\n"]
    for item in items:
        title = item.title or "日记"
        block = f"## {title}（记录 {item.id}）\n\n"
        if item.topics:
            block += f"主题：{'、'.join(item.topics)}\n\n"
        if item.keywords:
            block += f"关键词：{'、'.join(item.keywords)}\n\n"
        block += item.body + "\n"
        blocks.append(block)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(blocks), encoding="utf-8")
