from datetime import date
from threading import Event, Thread

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.models import DiaryDiscussionMessage, DiaryDiscussionSession, DiarySummary, InvestmentDiary, InvestmentTag
from app.services import diary_discussions as chats
from app.services import diary_summaries as summaries
from app.services import investment_diary as originals


@pytest.fixture
def records(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'records.db'}")
    monkeypatch.setattr(settings, "personal_knowledge_dir", str(tmp_path / "knowledge"))
    monkeypatch.setattr(settings, "workspace", "formal")
    monkeypatch.setattr(originals, "DATA_DIR", tmp_path / "runtime")
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        chats.initialize_diary_support(db)
    def db_override():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = db_override
    monkeypatch.setattr(chats, "active_ai_runtime", lambda db: {"enabled": True, "has_api_key": True,
        "api_key": "fictional", "base_url": "http://invalid.example", "provider": "test", "model": "test"})
    client = TestClient(app)  # No startup against the real runtime database.
    yield client, sessions, tmp_path, monkeypatch
    client.close()
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def diary(client, body="虚构：通胀与利率如何影响估值？", day="2026-10-07"):
    response = client.post("/api/diaries", json={"record_date": day, "body": body})
    assert response.status_code == 201, response.text
    return response.json()["item"]["id"]


def session(client, ids):
    response = client.post("/api/diary-discussions", json={"record_date": "2026-10-07", "diary_ids": ids, "question": "解释传导机制", "background": "虚构学习背景"})
    assert response.status_code == 201, response.text
    return response.json()["item"]["id"]


def message(client, sid, task, body="虚构问题"):
    response = client.post(f"/api/diary-discussions/{sid}/messages", json={"task": task, "body": body})
    assert response.status_code == 201, response.text
    return response.json()["message_id"]


def generate(client, sid, mid, task, consent=True):
    return client.post(f"/api/diary-analysis/{task}", json={"session_id": sid, "message_id": mid, "consent_external_ai": consent})


def candidate():
    return {"title": "虚构学习结论", "body": "贴现率改变影响估值，需区分盈利预期及风险溢价。", "keywords": ["虚构案例"], "tag_ids": [1, 3], "new_tags": []}


def external(**overrides):
    return {"record_date": "2026-10-07", "body": "虚构外部讨论结论", "source_type": "external_discussion", "source_note": "测试平台", "confirmed": True, **overrides}


def test_external_summary_confirmation_transaction_and_original_fidelity(records):
    client, sessions, root, _ = records
    original = "  虚构原话：满仓不是保证。\n"
    did = diary(client, original)
    tag = {"name": "机会成本", "definition": "放弃其他选择的代价", "aliases": ["替代成本"]}
    denied = client.post("/api/diary-summaries", json=external(confirmed=False, diary_ids=[did], new_tags=[tag]))
    assert denied.status_code == 400
    assert not list(root.glob("knowledge/02_分析与复盘/**/*.md"))
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(InvestmentTag)) == 8
    saved = client.post("/api/diary-summaries", json=external(diary_ids=[did], new_tags=[tag]))
    assert saved.status_code == 201, saved.text
    assert saved.json()["item"]["tags"][0]["name"] == "机会成本"
    assert summaries.summary_path(date(2026, 10, 7)).read_text(encoding="utf-8").endswith("虚构外部讨论结论\n")
    assert client.get(f"/api/diaries/{did}").json()["item"]["body"] == original


def test_one_daily_summary_update_date_search_and_reopen(records):
    client, sessions, _, _ = records
    result = client.post("/api/diary-summaries", json=external(tag_ids=[1], keywords=["事件%标记"]))
    sid = result.json()["item"]["id"]
    assert client.post("/api/diary-summaries", json=external()).status_code == 409
    assert client.get("/api/diary-summaries", params={"q": "%"}).json()["count"] == 1
    assert client.get("/api/diary-summaries", params={"tag_id": 1}).json()["count"] == 1
    edited = client.put(f"/api/diary-summaries/{sid}", json=external(record_date="2026-11-02", body="虚构更正内容"))
    assert edited.json()["item"]["id"] == sid
    assert "调整日期" in summaries.summary_path(date(2026, 10, 7)).read_text(encoding="utf-8")
    reopened = create_engine(get_settings().database_url)
    with Session(reopened) as db:
        assert db.get(DiarySummary, sid).body == "虚构更正内容"
    reopened.dispose()


def test_complete_discussion_context_correction_recovery_and_confirm_gate(records):
    client, sessions, _, monkeypatch = records
    selected = diary(client)
    diary(client, "虚构不应发送的无关原文")
    sid = session(client, [selected])
    calls = []
    def model(runtime, messages):
        calls.append(messages)
        if len(calls) == 1:
            return {"analysis": "虚构分析：不能把立即买入当成教学结论。", "summary": candidate()}
        if len(calls) == 2:
            return {"answer": "已吸收你的纠正：收益率和政策利率不同。"}
        return {**candidate(), "body": "已吸收纠正：收益率并非政策利率；估值仍受预期影响。"}
    monkeypatch.setattr(chats, "call_diary_model", model)
    mid = message(client, sid, "analyze")
    assert generate(client, sid, mid, "analyze").status_code == 200
    assert "无关原文" not in str(calls[0])
    assert generate(client, sid, mid, "analyze").status_code == 200
    assert len(calls) == 1  # Retrying a completed request does not bill again.
    assert client.get("/api/diary-summaries").json()["count"] == 0
    assert "立即买入" in client.get(f"/api/diary-discussions/{sid}").json()["item"]["messages"][1]["body"]
    mid = message(client, sid, "discuss", "纠正：我说的是收益率，不是政策利率。")
    assert generate(client, sid, mid, "discuss").status_code == 200
    assert any("不能把立即买入" in m["content"] for m in calls[1])
    payload = external(source_type="in_app_ai", diary_ids=[selected], session_ids=[sid], **candidate())
    assert client.post("/api/diary-summaries", json=payload).status_code == 409
    mid = message(client, sid, "summarize", "请整理总结")
    result = generate(client, sid, mid, "summarize")
    assert result.status_code == 200, result.text
    assert any("纠正" in m["content"] for m in calls[2])
    saved = client.post("/api/diary-summaries", json={**payload, "body": result.json()["item"]["candidate"]["body"]})
    assert saved.status_code == 201, saved.text
    with sessions() as db:
        assert len(chats.discussion_payload(db, db.get(DiaryDiscussionSession, sid))["messages"]) == 6
    assert client.get(f"/api/diary-discussions/{sid}").json()["item"]["candidate"]["body"] == saved.json()["item"]["body"]


def test_authorization_and_unconfigured_model_do_not_generate(records):
    client, _, _, monkeypatch = records
    sid = session(client, [diary(client)])
    mid = message(client, sid, "analyze")
    monkeypatch.setattr(chats, "call_diary_model", lambda *_: pytest.fail("Should not call model"))
    assert generate(client, sid, mid, "analyze", False).status_code == 403
    monkeypatch.setattr(chats, "active_ai_runtime", lambda _: {"enabled": False})
    assert generate(client, sid, mid, "analyze").status_code == 400
    assert client.get(f"/api/diary-discussions/{sid}").json()["item"]["messages"][0]["status"] == "pending"


def test_model_failure_and_restart_recover_messages_retry_without_duplicates(records):
    client, sessions, _, monkeypatch = records
    sid = session(client, [diary(client)])
    mid = message(client, sid, "analyze")
    monkeypatch.setattr(chats, "call_diary_model", lambda *_: {"analysis": "虚构非法标签", "summary": {**candidate(), "tag_ids": [999]}})
    assert generate(client, sid, mid, "analyze").status_code == 502
    with sessions() as db:
        item = db.get(DiaryDiscussionSession, sid)
        item.generation_status = "running"
        db.get(DiaryDiscussionMessage, mid).status = "running"
        db.commit()
        chats.initialize_diary_support(db)
    recovered = client.get(f"/api/diary-discussions/{sid}").json()["item"]
    assert recovered["generation_status"] == "failed" and len(recovered["messages"]) == 1
    monkeypatch.setattr(chats, "call_diary_model", lambda *_: {"analysis": "虚构恢复答复", "summary": candidate()})
    assert generate(client, sid, mid, "analyze").status_code == 200
    assert len(client.get(f"/api/diary-discussions/{sid}").json()["item"]["messages"]) == 2


def test_file_failure_retry_and_failed_tag_transaction(records):
    client, sessions, _, monkeypatch = records
    real_writer = summaries.write_summary_day
    monkeypatch.setattr(summaries, "write_summary_day", lambda *_: (_ for _ in ()).throw(OSError("denied")))
    response = client.post("/api/diary-summaries", json=external())
    saved = response.json()
    assert saved["database_saved"] and not saved["markdown_saved"]
    mid = saved["item"]["id"]
    monkeypatch.setattr(summaries, "write_summary_day", real_writer)
    assert client.post(f"/api/diary-summaries/{mid}/retry-markdown").json()["markdown_saved"]
    tag = {"name": "虚构新概念", "definition": "虚构定义"}
    bad = client.put(f"/api/diary-summaries/{mid}", json=external(new_tags=[tag, {"name": "利率", "definition": "重复"}]))
    assert bad.status_code == 409
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(DiarySummary)) == 1
        assert db.scalar(select(InvestmentTag).where(InvestmentTag.name == "虚构新概念")) is None


def test_database_failure_never_reports_success_or_writes_file(records):
    client, sessions, root, monkeypatch = records
    def fail_commit(_):
        raise SQLAlchemyError("fictional failure")
    monkeypatch.setattr(sessions.class_, "commit", fail_commit)
    result = client.post("/api/diary-summaries", json=external(new_tags=[{"name": "虚构标签", "definition": "虚构"}]))
    assert result.status_code == 500
    assert not list(root.glob("knowledge/02_分析与复盘/**/*.md"))
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(DiarySummary)) == 0
        assert db.scalar(select(func.count()).select_from(InvestmentTag)) == 8


def test_tags_rename_alias_merge_preserve_links_and_markdown(records):
    client, _, _, _ = records
    saved = client.post("/api/diary-summaries", json=external(tag_ids=[1, 3])).json()["item"]
    rename = client.put("/api/investment-tags/1", json={"name": "通胀机制", "definition": "价格传导", "aliases": ["通胀"]})
    assert rename.status_code == 200
    assert "通胀机制" in summaries.summary_path(date(2026, 10, 7)).read_text(encoding="utf-8")
    assert client.post("/api/investment-tags", json={"name": " 通胀 ", "definition": "重复"}).status_code == 409
    merged = client.post("/api/investment-tags/1/merge", json={"target_id": 3})
    assert merged.status_code == 200
    result = client.get(f"/api/diary-summaries/{saved['id']}").json()["item"]
    assert [t["id"] for t in result["tags"]] == [3]
    assert "通胀机制" in result["tags"][0]["aliases"]


def test_tag_suggestion_sends_only_summary_and_does_not_modify_library(records):
    client, sessions, _, monkeypatch = records
    diary(client, "虚构不应出现在标签建议中的日记")
    calls = []
    def model(runtime, messages):
        calls.append(messages)
        return {"tag_ids": [1], "new_tags": [{"name": "供需", "definition": "商品供应需求"}]}
    monkeypatch.setattr(chats, "call_diary_model", model)
    response = client.post("/api/diary-analysis/suggest-tags", json={"body": "虚构通胀总结", "consent_external_ai": True})
    assert response.status_code == 200
    assert "不应出现在" not in str(calls)
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(InvestmentTag)) == 8


def test_concurrent_generation_and_candidate_save_are_blocked(records):
    client, _, _, monkeypatch = records
    sid = session(client, [diary(client)])
    mid = message(client, sid, "analyze")
    entered, release = Event(), Event()
    result = []
    def model(*_):
        entered.set()
        assert release.wait(10)
        return {"analysis": "虚构慢回复", "summary": candidate()}
    monkeypatch.setattr(chats, "call_diary_model", model)
    worker = Thread(target=lambda: result.append(generate(client, sid, mid, "analyze")))
    worker.start()
    try:
        assert entered.wait(5)
        assert generate(client, sid, mid, "analyze").status_code == 409
        assert client.put(f"/api/diary-discussions/{sid}", json=candidate()).status_code == 409
        assert client.get(f"/api/diary-discussions/{sid}").json()["item"]["generation_status"] == "running"
    finally:
        release.set()
        worker.join(10)
    assert result[0].status_code == 200


def test_demo_summary_ignores_formal_knowledge_path(records):
    client, _, root, monkeypatch = records
    settings = get_settings()
    monkeypatch.setattr(settings, "workspace", "demo")
    saved = client.post("/api/diary-summaries", json=external()).json()
    assert saved["markdown_saved"]
    assert str(root / "runtime" / "demo_personal_knowledge") in saved["item"]["markdown_path"]
    assert not (root / "knowledge" / "02_分析与复盘").exists()


def test_external_summary_source_is_retained_when_starting_discussion(records):
    client, _, _, monkeypatch = records
    did = diary(client)
    base = client.post("/api/diary-summaries", json=external(source_note="ChatGPT 外部讨论", diary_ids=[did])).json()["item"]
    result = client.post("/api/diary-discussions", json={"record_date": "2026-10-07", "diary_ids": [did], "base_summary_id": base["id"]})
    assert result.status_code == 201
    item = result.json()["item"]
    assert item["base_source"] == "ChatGPT 外部讨论"
    assert item["created_at"].endswith("+00:00")
    assert base["created_at"].endswith("+00:00")
    def model(runtime, messages):
        assert "ChatGPT 外部讨论" in str(messages)
        assert "虚构外部讨论结论" in str(messages)
        return {"analysis": "虚构补充分析", "summary": candidate()}
    monkeypatch.setattr(chats, "call_diary_model", model)
    mid = message(client, item["id"], "analyze")
    assert generate(client, item["id"], mid, "analyze").status_code == 200
    assert client.get(f"/api/diary-discussions/{item['id']}").json()["item"]["base_source"] == "ChatGPT 外部讨论"
