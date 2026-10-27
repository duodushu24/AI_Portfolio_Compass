"""Exercise the real process boundary without SDK/network or financial records."""
import json
import os
import subprocess

import pytest

from app.adapters.akshare_adapter import AKShareAdapter
from app.services import data_sources


def test_worker_round_trip_overrides_gbk_parent_without_changing_parent_env(monkeypatch):
    monkeypatch.setenv("PYTHONUTF8", "0")
    monkeypatch.setenv("PYTHONIOENCODING", "gbk")
    real_run = subprocess.run
    script = """import json,sys
request=json.load(sys.stdin)
print(json.dumps({'items':[{'name':'中文基金🧭','stdout':sys.stdout.encoding,'stderr':sys.stderr.encoding,'utf8_mode':sys.flags.utf8_mode,'request':request}]},ensure_ascii=False))
"""
    def local_worker(cmd, **kwargs):
        return real_run([*cmd[:-1], "-c", script], **kwargs)
    monkeypatch.setattr(subprocess, "run", local_worker)
    row = AKShareAdapter()._call("fund", symbol="中文请求")[0]
    assert row["name"] == "中文基金🧭"
    assert row["stdout"] == row["stderr"] == "utf-8" and row["utf8_mode"] == 1
    assert row["request"] == {"action":"fund", "kwargs":{"symbol":"中文请求"}}
    assert os.environ["PYTHONUTF8"] == "0" and os.environ["PYTHONIOENCODING"] == "gbk"


def test_invalid_worker_bytes_produce_actionable_source_error(monkeypatch):
    monkeypatch.setattr(subprocess,"run",lambda cmd,**kw:subprocess.CompletedProcess(cmd,0,stdout=b"\xbe\xbb",stderr=b""))
    result=data_sources.fetch(None,data_sources.provider_registry().get("akshare"),
        {"code":"CN.006567","market":"CN","asset_type":"fund","unit":"fund_unit","currency":"CNY"},"quote")
    assert result["status"] == "encoding_error" and "字符编码不一致" in result["message"]
    assert "更新后端" in result["message"]


@pytest.mark.parametrize("stdout,stderr,returncode,reason",[
    (b"",b"ModuleNotFoundError: akshare",1,"dependency_missing"),
    (b"",b"worker stopped",1,"request_failed"),
    (json.dumps({"error":"KeyError"}).encode(),b"",0,"KeyError"),
])
def test_worker_failure_classification_survives_binary_transport(monkeypatch,stdout,stderr,returncode,reason):
    monkeypatch.setattr(subprocess,"run",lambda cmd,**kw:subprocess.CompletedProcess(cmd,returncode,stdout=stdout,stderr=stderr))
    with pytest.raises(RuntimeError,match=reason):
        AKShareAdapter()._call("fund",symbol="006567")
