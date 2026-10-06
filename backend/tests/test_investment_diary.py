from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.database import get_db
from app.main import app
from app.models import InvestmentDiary
from app.services import investment_diary as service


@pytest.fixture
def diary_app(tmp_path, monkeypatch):
    settings = get_settings()
    database_path = tmp_path / "records.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{database_path}")
    monkeypatch.setattr(settings, "workspace", "formal")
    monkeypatch.setattr(settings, "personal_knowledge_dir", str(tmp_path / "knowledge"))
    monkeypatch.setattr(service, "DATA_DIR", tmp_path / "runtime")
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
    InvestmentDiary.__table__.create(engine)
    sessions = sessionmaker(bind=engine)

    def isolated_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = isolated_db
    # No application startup: tests never initialise the real runtime database.
    client = TestClient(app)
    yield client, sessions, tmp_path, database_path
    client.close()
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def entry(body="虚构测试记录", record_date="2026-10-04", **kwargs):
    return {"record_date": record_date, "body": body, **kwargs}


def create(client, **kwargs):
    response = client.post("/api/diaries", json=entry(**kwargs))
    assert response.status_code == 201, response.text
    return response.json()


def test_same_day_keeps_originals_and_survives_database_reopen(diary_app):
    client, sessions, root, database_path = diary_app
    original = "  虚构记录：先观察。\n\n第二段保留缩进。  \n"
    first = create(client, body=original, title="测试观察", topics=["仓位管理"])
    second = create(client, body="虚构记录：补充计划。")
    assert first["markdown_saved"] and second["markdown_saved"]
    path = root / "knowledge/01_原始资料/复盘日记/2026/10月/10.04.md"
    text = path.read_text(encoding="utf-8")
    assert original in text
    assert "虚构记录：补充计划。" in text
    assert text.count("## ") == 2
    assert list(path.parent.iterdir()) == [path]
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(InvestmentDiary)) == 2
    reopened = create_engine(f"sqlite:///{database_path}")
    with Session(reopened) as db:
        assert db.get(InvestmentDiary, first["item"]["id"]).body == original
    reopened.dispose()
    assert client.get(f"/api/diaries/{first['item']['id']}").json()["item"]["body"] == original


def test_edit_and_move_date_regenerates_both_days_without_losing_other_entries(diary_app):
    client, _, _, _ = diary_app
    first = create(client, body="虚构旧内容")["item"]
    create(client, body="虚构同日另一条")
    response = client.put(f"/api/diaries/{first['id']}", json=entry(body="虚构更正内容", record_date="2026-11-02"))
    result = response.json()
    assert result["item"]["id"] == first["id"]
    assert result["markdown_saved"]
    old = service.day_path(date(2026, 10, 4)).read_text(encoding="utf-8")
    new = service.day_path(date(2026, 11, 2)).read_text(encoding="utf-8")
    assert "虚构旧内容" not in old and "虚构更正内容" not in old
    assert "虚构同日另一条" in old
    assert "虚构更正内容" in new
    assert client.get("/api/diaries").json()["count"] == 2


def test_date_and_literal_keyword_filters_include_chinese_labels(diary_app):
    client, _, _, _ = diary_app
    first = create(client, body="虚构普通内容", topics=["  再平衡 ", "再平衡"], keywords=["观察%标记"])["item"]
    create(client, body="虚构其他内容", record_date="2026-10-05")
    create(client, body="虚构另一天", record_date="2025-12-31")
    assert first["topics"] == ["再平衡"]
    assert client.get("/api/diaries", params={"q": "再平衡"}).json()["items"][0]["id"] == first["id"]
    assert client.get("/api/diaries", params={"q": "%"}).json()["count"] == 1
    result = client.get("/api/diaries", params={"start_date": "2026-10-01", "end_date": "2026-10-31", "limit": 1, "offset": 1}).json()
    assert result["count"] == 2
    assert result["items"][0]["record_date"] == "2026-10-04"


def test_invalid_input_does_not_create_records_or_files(diary_app):
    client, _, root, _ = diary_app
    for invalid in [entry(body=" \n "), entry(record_date="2026-02-30"), entry(topics=["x" * 81])]:
        assert client.post("/api/diaries", json=invalid).status_code == 422
    assert client.get("/api/diaries", params={"start_date": "2026-10-05", "end_date": "2026-10-04"}).status_code == 400
    assert client.get("/api/diaries/999").status_code == 404
    assert client.put("/api/diaries/999", json=entry()).status_code == 404
    assert client.get("/api/diaries").json()["count"] == 0
    assert not (root / "knowledge").exists()


def test_file_failure_is_saved_in_db_and_retry_does_not_duplicate(diary_app, monkeypatch):
    client, _, _, _ = diary_app
    write_day = service._write_day

    def deny_write(*args):
        raise PermissionError("虚构测试：目录不可写")

    monkeypatch.setattr(service, "_write_day", deny_write)
    result = create(client, body="虚构文件失败测试")
    assert result["database_saved"] and not result["markdown_saved"]
    assert result["file_errors"]
    diary_id = result["item"]["id"]
    assert not client.get(f"/api/diaries/{diary_id}").json()["item"]["markdown_saved"]
    monkeypatch.setattr(service, "_write_day", write_day)
    retried = client.post(f"/api/diaries/{diary_id}/retry-markdown").json()
    assert retried["markdown_saved"]
    assert retried["item"]["id"] == diary_id
    assert client.get("/api/diaries").json()["count"] == 1
    assert "虚构文件失败测试" in service.day_path(date(2026, 10, 4)).read_text(encoding="utf-8")


def test_failed_old_date_write_can_be_retried_after_reopen(diary_app, monkeypatch):
    client, sessions, _, _ = diary_app
    item = create(client, body="虚构待纠正日期内容")["item"]
    write_day = service._write_day

    def deny_old_day(db, value):
        if value == date(2026, 10, 4):
            raise PermissionError("虚构旧日期写入失败")
        write_day(db, value)

    monkeypatch.setattr(service, "_write_day", deny_old_day)
    result = client.put(f"/api/diaries/{item['id']}", json=entry(body="虚构调整后", record_date="2026-10-05")).json()
    assert not result["markdown_saved"]
    with sessions() as db:
        assert db.get(InvestmentDiary, item["id"]).pending_markdown_dates == ["2026-10-04"]
    monkeypatch.setattr(service, "_write_day", write_day)
    assert client.post(f"/api/diaries/{item['id']}/retry-markdown").json()["markdown_saved"]
    old = service.day_path(date(2026, 10, 4)).read_text(encoding="utf-8")
    assert "虚构待纠正日期内容" not in old
    assert "本日暂无记录" in old


def test_database_failure_never_reports_success_or_writes_markdown(diary_app, monkeypatch):
    client, _, root, _ = diary_app

    def deny_commit(self):
        raise SQLAlchemyError("虚构数据库写入失败")

    monkeypatch.setattr(Session, "commit", deny_commit)
    response = client.post("/api/diaries", json=entry())
    assert response.status_code == 500
    assert "数据库保存未完成" in response.json()["detail"]
    assert not (root / "knowledge").exists()


@pytest.mark.parametrize("workspace,database_name", [("demo", "records.db"), ("formal", "demo.db")])
def test_demo_always_ignores_formal_knowledge_directory(diary_app, monkeypatch, workspace, database_name):
    client, _, root, _ = diary_app
    monkeypatch.setattr(get_settings(), "workspace", workspace)
    monkeypatch.setattr(get_settings(), "database_url", f"sqlite:///{root / database_name}")
    result = create(client)
    assert result["markdown_saved"]
    assert not (root / "knowledge").exists()
    assert (root / "runtime/demo_personal_knowledge/01_原始资料/复盘日记/2026/10月/10.04.md").is_file()
