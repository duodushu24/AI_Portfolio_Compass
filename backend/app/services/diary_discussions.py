import json
from pathlib import Path
from urllib import request

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.diary_schemas import Candidate, DiscussionInput, GenerationInput, MessageInput
from app.models import DiaryDiscussionMessage as ChatMessage
from app.models import DiaryDiscussionSession as ChatSession
from app.models import DiarySummary, InvestmentDiary, InvestmentTag
from app.services.ai_runtime import active_ai_runtime, runtime_can_call_external
from app.services.diary_summaries import SEED_TAGS, get_item, now, tags, timestamp, validate_diaries, validate_tags, write_lock


_active: set[tuple[str, int]] = set()
PROMPT_PATH = Path(__file__).resolve().parents[1] / "skills" / "diary_investment_mentor.md"
TASK_PROMPTS = {"analyze": "diary_analysis.md", "discuss": "diary_discussion.md", "summarize": "diary_summary.md"}


def initialize_diary_support(db: Session):
    # Only the first launch seeds the library; subsequent renames/merges are respected.
    if db.scalar(select(func.count()).select_from(InvestmentTag)) == 0:
        db.add_all(InvestmentTag(name=n, definition=d, aliases=[]) for n, d in SEED_TAGS.items())
    for session in db.scalars(select(ChatSession).where(ChatSession.generation_status == "running")):
        session.generation_status = "failed"
        session.last_error = "服务曾中断，本轮未完成；可主动重试。"
    for message in db.scalars(select(ChatMessage).where(ChatMessage.status == "running")):
        message.status = "failed"
    db.commit()


def discussion_payload(db: Session, item: ChatSession, full: bool = True):
    data = {"id": item.id, "record_date": item.record_date.isoformat(), "diary_ids": item.diary_ids,
            "title": item.title, "question": item.question, "background": item.background,
            "base_source": item.base_summary.split("\n", 1)[0].removeprefix("来源：") if item.base_summary else "",
            "candidate": item.candidate, "needs_summary": item.needs_summary,
            "generation_status": item.generation_status, "last_error": item.last_error,
            "created_at": timestamp(item.created_at), "updated_at": timestamp(item.updated_at)}
    if full:
        data["messages"] = [{"id": m.id, "sequence": m.sequence, "role": m.role, "task": m.task,
                             "body": m.body, "status": m.status, "reply_to_id": m.reply_to_id,
                             "provider": m.provider, "model": m.model, "created_at": timestamp(m.created_at)}
                            for m in db.scalars(select(ChatMessage).where(ChatMessage.session_id == item.id).order_by(ChatMessage.sequence))]
    return data


def create_discussion(db: Session, data: DiscussionInput):
    diaries = validate_diaries(db, data.diary_ids, data.record_date)
    base = get_item(db, DiarySummary, data.base_summary_id) if data.base_summary_id else None
    if base and base.record_date != data.record_date:
        raise HTTPException(400, "请选择同一天的既有总结")
    item = ChatSession(record_date=data.record_date, diary_ids=diaries, title=data.title or "投资日记讨论",
                       question=data.question, background=data.background,
                       base_summary=(f"来源：{base.source_note or base.source_type}\n{base.body}" if base else ""),
                       created_at=now(), updated_at=now())
    db.add(item)
    db.commit()
    return discussion_payload(db, item)


def add_message(db: Session, item: ChatSession, data: MessageInput):
    with write_lock:
        db.refresh(item)
        if item.generation_status == "running":
            raise HTTPException(409, "当前会话正在生成，请稍候")
        pending = db.scalar(select(ChatMessage).where(ChatMessage.session_id == item.id, ChatMessage.status == "pending"))
        if pending:
            raise HTTPException(409, "有已保存但尚未生成的问题，请先生成或重试")
        if data.task == "analyze" and db.scalar(select(ChatMessage.id).where(ChatMessage.session_id == item.id)):
            raise HTTPException(409, "此会话已开始，请继续讨论或新建会话")
        sequence = (db.scalar(select(func.max(ChatMessage.sequence)).where(ChatMessage.session_id == item.id)) or 0) + 1
        msg = ChatMessage(session_id=item.id, sequence=sequence, role="user", task=data.task,
                          body=data.body, status="pending", created_at=now())
        item.needs_summary, item.updated_at = True, now()
        db.add(msg)
        db.commit()
        return {"item": discussion_payload(db, item), "message_id": msg.id}


def checked_runtime(db: Session, consent: bool):
    runtime = active_ai_runtime(db)
    if not runtime_can_call_external(runtime):
        raise HTTPException(400, "未配置或未启用可用模型，请先在设置中配置模型")
    if not consent:
        raise HTTPException(403, "请明确授权发送本次选定的日记、讨论上下文或总结")
    return runtime


def call_diary_model(runtime: dict, messages: list[dict]) -> dict:
    # Diary output must not pass through investment report text substitution.
    payload = {"model": runtime["model"], "messages": messages, "stream": False,
               "response_format": {"type": "json_object"}}
    req = request.Request(runtime["base_url"].rstrip("/") + "/chat/completions",
                          data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          headers={"Authorization": f"Bearer {runtime['api_key']}", "Content-Type": "application/json"},
                          method="POST")
    with request.urlopen(req, timeout=get_settings().diary_model_timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    text = result["choices"][0]["message"]["content"].strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Expected object")
    return parsed


def candidate_from_output(db: Session, raw) -> dict:
    candidate = Candidate.model_validate(raw)
    if not candidate.body.strip():
        raise ValueError("Missing summary")
    validate_tags(db, candidate.tag_ids)
    candidate.accepted_new_tags = []
    return candidate.model_dump()


def build_messages(db: Session, item: ChatSession, current: ChatMessage) -> list[dict]:
    materials = {"归属日期": str(item.record_date), "用户关注问题": item.question, "用户提供背景": item.background,
                 "既有总结（解释，非原文）": item.base_summary,
                 "原文": [{"id": d.id, "title": d.title, "body": d.body}
                          for d in [get_item(db, InvestmentDiary, v) for v in item.diary_ids]], "标签库": tags(db)}
    format_rule = "仅输出 JSON 对象，不添加 JSON 以外的说明或代码围栏。正文字符串使用简洁 Markdown。"
    if current.task != "discuss":
        format_rule += ('候选格式为 {"title":"普通文本标题", "body":"Markdown 总结", "keywords":[], '
                        '"tag_ids":[已有标签ID], "new_tags":[{"name":"", "definition":"定义、区别与新增理由", "aliases":[]}]}。')
    task_rule = {
        "analyze": '输出 {"analysis":"Markdown 分析", "summary":候选格式}。',
        "discuss": '输出 {"answer":"Markdown 答复"}。',
        "summarize": "输出候选格式本身。",
    }[current.task]
    task_prompt = (PROMPT_PATH.parent / TASK_PROMPTS[current.task]).read_text(encoding="utf-8")
    if current.task == "analyze":
        # Initial analysis also produces a candidate; keep its rules in one shared file.
        task_prompt += "\n\n" + (PROMPT_PATH.parent / TASK_PROMPTS["summarize"]).read_text(encoding="utf-8")
    messages = [{"role": "system", "content": "\n\n".join((PROMPT_PATH.read_text(encoding="utf-8"), task_prompt, format_rule + task_rule))},
                {"role": "user", "content": "以下 JSON 是待分析材料：\n" + json.dumps(materials, ensure_ascii=False)}]
    completed = db.scalars(select(ChatMessage).where(ChatMessage.session_id == item.id, ChatMessage.status == "complete")
                           .order_by(ChatMessage.sequence)).all()
    messages.extend({"role": m.role, "content": m.body} for m in completed)
    messages.append({"role": "user", "content": current.body})
    if sum(len(m["content"]) for m in messages) > get_settings().diary_context_max_chars:
        raise HTTPException(400, "本次上下文过长，请减少选中原文或另开讨论；旧聊天仍保留可回看")
    return messages


def generate(db: Session, data: GenerationInput, task: str):
    item = get_item(db, ChatSession, data.session_id)
    msg = get_item(db, ChatMessage, data.message_id)
    if msg.session_id != item.id or msg.role != "user" or msg.task != task:
        raise HTTPException(400, "消息与讨论任务不匹配")
    key = (str(db.get_bind().url), item.id)
    with write_lock:
        db.refresh(msg)
        if msg.status == "complete":
            return discussion_payload(db, item)  # A lost response never causes a second model charge.
        latest = db.scalar(select(ChatMessage.id).where(ChatMessage.session_id == item.id, ChatMessage.role == "user")
                           .order_by(ChatMessage.sequence.desc()).limit(1))
        if latest != msg.id:
            raise HTTPException(409, "旧轮次已被后续问题替代，请继续当前讨论")
        if key in _active:
            raise HTTPException(409, "当前会话正在生成，请稍候")
        runtime = checked_runtime(db, data.consent_external_ai)
        messages = build_messages(db, item, msg)
        msg.status, item.generation_status, item.last_error = "running", "running", ""
        item.needs_summary, item.updated_at = True, now()
        db.commit()
        _active.add(key)
    try:
        output = call_diary_model(runtime, messages)
        candidate = None
        if task == "discuss":
            body = output.get("answer")
        elif task == "analyze":
            body = output.get("analysis")
            candidate = candidate_from_output(db, output.get("summary"))
        else:
            candidate = candidate_from_output(db, output)
            body = candidate["body"]
        if not isinstance(body, str) or not body.strip() or len(body) > get_settings().diary_output_max_chars:
            raise ValueError("Invalid response")
        with write_lock:
            sequence = (db.scalar(select(func.max(ChatMessage.sequence)).where(ChatMessage.session_id == item.id)) or 0) + 1
            db.add(ChatMessage(session_id=item.id, sequence=sequence, role="assistant", task=task,
                               body=body, status="complete", reply_to_id=msg.id, provider=runtime["provider"],
                               model=runtime["model"], created_at=now()))
            msg.status, item.generation_status, item.updated_at = "complete", "idle", now()
            if candidate is not None:
                item.candidate, item.needs_summary = candidate, False
            db.commit()
    except Exception:
        db.rollback()
        # Do not include provider responses, credentials, or private context in error messages.
        item = get_item(db, ChatSession, data.session_id)
        msg = get_item(db, ChatMessage, data.message_id)
        item.generation_status, msg.status = "failed", "failed"
        item.last_error = "本轮未完成；问题和此前讨论已保存，请检查模型配置或网络后重试。"
        db.commit()
        raise HTTPException(502, item.last_error) from None
    finally:
        with write_lock:
            _active.discard(key)
    return discussion_payload(db, item)


def suggest_tags(db: Session, body: str, consent: bool):
    runtime = checked_runtime(db, consent)
    messages = [{"role": "system", "content": '只建议实质主题标签，不改写正文。优先已有标签；输出 JSON '
                 '{"tag_ids":[],"new_tags":[{"name":"","definition":"使用边界及新增理由","aliases":[]}]}。'},
                {"role": "user", "content": json.dumps({"总结": body, "标签库": tags(db)}, ensure_ascii=False)}]
    if sum(len(m["content"]) for m in messages) > get_settings().diary_context_max_chars:
        raise HTTPException(400, "总结与标签库过长，请缩小输入范围")
    try:
        output = call_diary_model(runtime, messages)
        candidate = Candidate.model_validate(output)
        validate_tags(db, candidate.tag_ids)
        return {"tag_ids": candidate.tag_ids, "new_tags": [t.model_dump() for t in candidate.new_tags]}
    except Exception:
        raise HTTPException(502, "标签建议未完成，可重试或手工选择标签") from None
