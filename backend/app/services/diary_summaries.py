from datetime import date, datetime, timezone
from threading import RLock

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.diary_schemas import SummaryInput, TagInput
from app.models import DiaryDiscussionSession, DiarySummary, DiarySummaryTag, InvestmentDiary, InvestmentTag
from app.services.investment_diary import diary_root


write_lock = RLock()  # The supported local backend uses a single process.
SEED_TAGS = {
    "通胀": "价格水平、购买力及通胀形成和传导机制。",
    "流动性": "资金供给、融资条件或市场交易流动性，具体含义在总结中说明。",
    "利率": "政策利率、收益率、贴现率及其资产传导。",
    "汇率": "货币相对价格、汇率驱动及跨币种敞口。",
    "风险偏好": "投资者承担风险的意愿及其市场变化，不泛指一切投资风险。",
    "估值": "价格与盈利、现金流及预期之间的关系。",
    "仓位管理": "资金分配、集中度、加减仓及组合敞口。",
    "风险管理": "风险识别、情景、损失承受和应对机制。",
}


def now():
    return datetime.now(timezone.utc)


def timestamp(value: datetime) -> str:
    # SQLite strips timezone information; API timestamps must still identify UTC.
    return value.replace(tzinfo=timezone.utc).isoformat()


def get_item(db: Session, model, item_id: int):
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(404, "记录不存在")
    return item


def tag_payload(item: InvestmentTag) -> dict:
    return {"id": item.id, "name": item.name, "definition": item.definition, "aliases": item.aliases}


def tags(db: Session) -> list[dict]:
    return [tag_payload(t) for t in db.scalars(select(InvestmentTag).order_by(InvestmentTag.id))]


def normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def save_tag(db: Session, data: TagInput, item: InvestmentTag | None = None) -> InvestmentTag:
    name = " ".join(data.name.split())
    aliases = list(dict.fromkeys(v for v in data.aliases if normalized(v) != normalized(name)))
    names = {normalized(v) for v in [name, *aliases]}
    for other in db.scalars(select(InvestmentTag)):
        if item and other.id == item.id:
            continue
        if names & {normalized(v) for v in [other.name, *other.aliases]}:
            raise HTTPException(409, f"标签名称或别名与“{other.name}”重复，请复用或合并")
    item = item or InvestmentTag()
    item.name, item.definition, item.aliases = name, data.definition, aliases
    db.add(item)
    db.flush()
    return item


def validate_diaries(db: Session, ids: list[int], record_date: date | None = None) -> list[int]:
    ids = list(dict.fromkeys(ids))
    for item_id in ids:
        item = get_item(db, InvestmentDiary, item_id)
        if record_date and item.record_date != record_date:
            raise HTTPException(400, "初次分析只能选择归属日期当天的日记")
    return ids


def validate_tags(db: Session, ids: list[int]) -> list[int]:
    ids = list(dict.fromkeys(ids))
    for item_id in ids:
        get_item(db, InvestmentTag, item_id)
    return ids


def summary_path(record_date: date):
    root = diary_root().parent.parent / "02_分析与复盘" / "日记总结"
    return root / str(record_date.year) / f"{record_date.month}月" / f"{record_date:%m.%d}.md"


def summary_payload(db: Session, item: DiarySummary) -> dict:
    selected = db.scalars(select(InvestmentTag).join(DiarySummaryTag, DiarySummaryTag.tag_id == InvestmentTag.id)
                          .where(DiarySummaryTag.summary_id == item.id).order_by(InvestmentTag.id)).all()
    return {
        "id": item.id, "record_date": item.record_date.isoformat(), "diary_ids": item.diary_ids,
        "session_ids": item.session_ids, "title": item.title, "body": item.body, "keywords": item.keywords,
        "source_type": item.source_type, "source_note": item.source_note, "tags": [tag_payload(t) for t in selected],
        "created_at": timestamp(item.created_at), "updated_at": timestamp(item.updated_at),
        "markdown_path": str(summary_path(item.record_date)), "markdown_saved": not item.pending_markdown_dates,
    }


def write_summary_day(db: Session, record_date: date):
    item = db.scalar(select(DiarySummary).where(DiarySummary.record_date == record_date))
    path = summary_path(record_date)
    if item is None:
        if path.exists():
            path.write_text(f"# {record_date} 日记总结\n\n总结已调整日期。\n", encoding="utf-8")
        return
    payload = summary_payload(db, item)
    links = "、".join(str(v) for v in item.diary_ids) or "未关联原文"
    sessions = "、".join(str(v) for v in item.session_ids) or "无本项目讨论记录"
    text = (f"# {record_date} · {item.title or '日记总结'}\n\n"
            f"来源：{item.source_note or item.source_type}\n\n关联原文：{links}\n\n讨论会话：{sessions}\n\n"
            f"标签：{'、'.join(t['name'] for t in payload['tags'])}\n\n"
            f"关键词：{'、'.join(item.keywords)}\n\n{item.body}\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def retry_markdown(db: Session, item: DiarySummary, add_current: bool = True) -> dict:
    with write_lock:
        if add_current:
            item.pending_markdown_dates = sorted(set(item.pending_markdown_dates or []) | {item.record_date.isoformat()})
            db.commit()
        failures, remaining = [], []
        for value in item.pending_markdown_dates:
            try:
                write_summary_day(db, date.fromisoformat(value))
            except OSError:
                remaining.append(value)
                failures.append(f"{value}：文件写入失败，请检查目录权限后重试")
        item.pending_markdown_dates = remaining
        db.commit()
        return {"item": summary_payload(db, item), "database_saved": True, "markdown_saved": not remaining,
                "message": "总结已确认保存" if not remaining else "总结已入库，文件保存失败；可重试文件保存。",
                "file_errors": failures}


def save_summary(db: Session, data: SummaryInput, item: DiarySummary | None = None) -> dict:
    with write_lock:
        if not data.confirmed:
            raise HTTPException(400, "请核对最终内容并明确确认保存")
        if not data.body.strip():
            raise HTTPException(400, "总结正文不能为空")
        existing = db.scalar(select(DiarySummary).where(DiarySummary.record_date == data.record_date))
        if existing and (item is None or existing.id != item.id):
            raise HTTPException(409, "该日期已有总结，请打开现有总结合并编辑后确认更新")
        diary_ids = validate_diaries(db, data.diary_ids)
        session_ids = list(dict.fromkeys(data.session_ids))
        for session_id in session_ids:
            session = get_item(db, DiaryDiscussionSession, session_id)
            if session.generation_status == "running" or session.needs_summary:
                raise HTTPException(409, "讨论已更新或正在生成，请先整理当前总结")
            if not set(session.diary_ids) <= set(diary_ids):
                raise HTTPException(400, "总结关联原文必须包含讨论所选原文")
        if data.source_type == "in_app_ai" and not session_ids:
            raise HTTPException(400, "本项目 AI 总结必须关联讨论会话")
        if not diary_ids and not data.source_note.strip():
            raise HTTPException(400, "未关联原文时请填写来源说明")
        tag_ids = validate_tags(db, data.tag_ids)
        for proposed in data.new_tags:
            tag_ids.append(save_tag(db, proposed).id)
        tag_ids = list(dict.fromkeys(tag_ids))
        affected = set(item.pending_markdown_dates or []) if item else set()
        if item:
            affected.add(item.record_date.isoformat())
        else:
            item = DiarySummary(created_at=now())
        item.record_date, item.diary_ids, item.session_ids = data.record_date, diary_ids, session_ids
        item.title, item.body, item.keywords = data.title, data.body, list(dict.fromkeys(data.keywords))
        item.source_type, item.source_note, item.updated_at = data.source_type, data.source_note, now()
        affected.add(data.record_date.isoformat())
        item.pending_markdown_dates = sorted(affected)
        db.add(item)
        db.flush()
        db.execute(delete(DiarySummaryTag).where(DiarySummaryTag.summary_id == item.id))
        db.add_all(DiarySummaryTag(summary_id=item.id, tag_id=t) for t in tag_ids)
        db.commit()
        return retry_markdown(db, item, add_current=False)


def list_summaries(db: Session, start_date=None, end_date=None, q="", tag_id=None, offset=0, limit=30):
    statement = select(DiarySummary)
    if start_date:
        statement = statement.where(DiarySummary.record_date >= start_date)
    if end_date:
        statement = statement.where(DiarySummary.record_date <= end_date)
    if tag_id:
        statement = statement.where(DiarySummary.id.in_(select(DiarySummaryTag.summary_id).where(DiarySummaryTag.tag_id == tag_id)))
    if q.strip():
        keywords = func.json_each(DiarySummary.keywords).table_valued("value").alias("keywords")
        statement = statement.where(or_(DiarySummary.title.contains(q.strip(), autoescape=True),
                                       DiarySummary.body.contains(q.strip(), autoescape=True),
                                       select(1).select_from(keywords).where(keywords.c.value.contains(q.strip(), autoescape=True)).exists()))
    count = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = db.scalars(statement.order_by(DiarySummary.record_date.desc()).offset(offset).limit(limit))
    return {"items": [summary_payload(db, v) for v in items], "count": count}


def refresh_tag_files(db: Session, summary_ids: list[int]) -> list[str]:
    items = [get_item(db, DiarySummary, v) for v in summary_ids]
    for item in items:
        item.pending_markdown_dates = sorted(set(item.pending_markdown_dates or []) | {item.record_date.isoformat()})
    db.commit()  # Mark all affected dates before any filesystem write.
    failures = []
    for item in items:
        failures.extend(retry_markdown(db, item, False)["file_errors"])
    return failures


def merge_tag(db: Session, source_id: int, target_id: int):
    with write_lock:
        if source_id == target_id:
            raise HTTPException(400, "请选择另一个目标标签")
        source, target = get_item(db, InvestmentTag, source_id), get_item(db, InvestmentTag, target_id)
        affected = list(db.scalars(select(DiarySummaryTag.summary_id).where(DiarySummaryTag.tag_id == source_id)))
        target.aliases = list(dict.fromkeys([*target.aliases, source.name, *source.aliases]))
        for item_id in affected:
            if db.get(DiarySummaryTag, (item_id, target_id)) is None:
                db.add(DiarySummaryTag(summary_id=item_id, tag_id=target_id))
        db.execute(delete(DiarySummaryTag).where(DiarySummaryTag.tag_id == source_id))
        # Session candidates also use ordinary IDs. Migrate them without rewriting messages.
        for session in db.scalars(select(DiaryDiscussionSession)):
            candidate = dict(session.candidate or {})
            if source_id in candidate.get("tag_ids", []):
                candidate["tag_ids"] = list(dict.fromkeys(target_id if t == source_id else t for t in candidate["tag_ids"]))
                session.candidate = candidate
        db.delete(source)
        db.flush()
        return {"item": tag_payload(target), "file_errors": refresh_tag_files(db, affected)}
