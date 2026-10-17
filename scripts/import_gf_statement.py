"""Local GF joint import: preview on a SQLite backup before a scoped replacement."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.config import get_settings
from app.services.portfolio.gf_import import prepare, replace_ledger


def read(path):
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        iterator = sheet.values
        headers = next(iterator)
        return [dict(zip(headers, r)) for r in iterator if any(v is not None for v in r)]
    finally:
        workbook.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flows", type=Path, required=True)
    parser.add_argument("--statement", type=Path, required=True)
    parser.add_argument("--account", required=True)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    url = get_settings().database_url
    if not url.startswith("sqlite:///"):
        raise ValueError("仅支持本地 SQLite")
    database = (args.database or Path(url.removeprefix("sqlite:///"))).resolve()
    if not database.is_file():
        raise ValueError("目标数据库不存在，禁止创建空库冒充导入")
    batch = prepare(read(args.flows), read(args.statement))
    work = ROOT / ".runtime" / "gf-import" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6])
    work.mkdir(parents=True)
    backup, trial = work / "before.db", work / "trial.db"
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(backup) as target:
            source.backup(target)
    with sqlite3.connect(backup) as source, sqlite3.connect(trial) as target:
        source.backup(target)
    (work / "normalized.json").write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
    engine = create_engine("sqlite:///" + str(trial))
    try:
        with Session(engine, autoflush=False) as db:
            preview = replace_ledger(db, args.account, batch, commit=True)
    finally:
        engine.dispose()
    result = {"preview": preview, "backup": str(backup), "applied": False}
    if args.apply:
        engine = create_engine("sqlite:///" + str(database))
        try:
            with Session(engine, autoflush=False) as db:
                db.connection().exec_driver_sql("BEGIN IMMEDIATE")
                result["result"] = replace_ledger(db, args.account, batch, commit=True)
                result["applied"] = True
        finally:
            engine.dispose()
    (work / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
