"""AKShare observations. The SDK runs in a bounded child process, never the ledger."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys


class AKShareAdapter:
    def __init__(self, config=None):
        self.config = config or {}
        self._fund_codes = None
        from .akshare_global import GlobalMarketData
        self.global_data = GlobalMarketData(lambda action, **kw: self._call(action, **kw))

    def _call(self, action, **kwargs):
        # Several SDK methods have no timeout parameter. A child gives every call
        # a real deadline without changing global HTTP settings in the web app.
        worker_env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
        # Own the JSON wire encoding instead of inheriting the Windows console's
        # code page. Capture bytes so a decode failure is raised here, not hidden
        # in subprocess's background reader thread as a later None/JSON error.
        result = subprocess.run([sys.executable, "-X", "utf8", str(Path(__file__).resolve())],
            input=json.dumps({"action": action, "kwargs": kwargs}).encode("utf-8"), env=worker_env,
            capture_output=True, timeout=int(self.config.get("timeout_seconds", 20)),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise RuntimeError("dependency_missing" if b"ModuleNotFoundError" in result.stderr else "request_failed")
        try:
            stdout = result.stdout.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError("encoding_error") from exc
        reply = json.loads(stdout)
        if "error" in reply:
            raise RuntimeError(reply["error"])
        return reply["items"]

    def kind(self, asset):
        kind = {"基金": "fund", "ETF": "etf", "股票": "stock", "债券": "bond", "leveraged_etf": "etf"}.get(asset.get("asset_type"), asset.get("asset_type", "stock"))
        if kind == "bond":
            if self._fund_codes is None:
                self._fund_codes = {str(r["基金代码"]) for r in self._call("fund_codes")}
            return "fund" if asset["code"].split(".")[-1] in self._fund_codes else "unsupported"
        return kind

    def fetch(self, asset, data_type, now=None):
        now = now or datetime.now(timezone.utc)
        if data_type == "fx":
            return self.global_data.fx(asset, now)
        if data_type == "quote" and asset.get("asset_type") == "precious_metal":
            return self.global_data.gold(asset, now)
        if data_type == "quote" and asset.get("market") == "US":
            return self.global_data.us(asset, now)
        local = now.astimezone(timezone(timedelta(hours=8)))
        symbol = asset["code"].split(".")[-1]
        if asset.get("market") != "CN" or len(symbol) != 6 or not symbol.isdigit():
            return {"status": "unsupported", "message": "AKShare 首批仅支持境内证券和场外基金；此标的可手动更新"}
        kind = self.kind(asset)
        if data_type == "news":
            if kind != "stock":
                return {"status": "unsupported", "message": "首批个股新闻不覆盖此资产类型，不能据此判断没有相关事件"}
            rows = self._call("news", symbol=symbol)
            items = []
            for r in rows:
                url = str(r.get("新闻链接") or "")
                if not url.startswith(("http://", "https://")) or not r.get("新闻标题"):
                    continue
                published = datetime.fromisoformat(str(r["发布时间"])).replace(tzinfo=local.tzinfo).astimezone(timezone.utc) if r.get("发布时间") else None
                if published and published > now:
                    continue
                items.append({"news_id": "akshare:" + hashlib.sha256((asset["code"] + url).encode()).hexdigest(),
                    "code": asset["code"], "market": "CN", "provider": "akshare", "news_type": "news",
                    "title": str(r["新闻标题"]), "source": str(r.get("文章来源") or "东方财富"),
                    "publish_time": published, "fetched_at": now, "url": url,
                    "related_securities": [{"code": asset["code"]}]})
            return {"status": "available" if items else "empty", "news": items, "message": "新闻已获取" if items else "本次未检索到匹配新闻"}
        if kind not in {"stock", "etf", "fund"}:
            return {"status": "unsupported", "message": "此资产类型暂不支持自动获取，可手动更新"}
        allowed_units = {"fund_unit", "share"} if kind == "fund" else {"share"}
        if asset.get("currency", "CNY") != "CNY" or asset.get("unit", "share") not in allowed_units:
            return {"status": "conflict", "message": "此来源返回人民币证券/基金单位价格，与持仓币种或数量单位不符，请核对后手动更新"}
        exchange_symbol = ("sh" if symbol.startswith(("5", "6", "9")) else "sz") + symbol
        if kind == "fund":
            rows = self._call("fund", symbol=symbol)
            date_key, close_key, upstream = "净值日期", "单位净值", "eastmoney"
        else:
            rows = self._call("etf" if kind == "etf" else "stock", symbol=exchange_symbol,
                              start_date=(local - timedelta(days=400)).strftime("%Y%m%d"), end_date=local.strftime("%Y%m%d"))
            date_key, close_key, upstream = "date", "close", "sina"
        valid = []
        for r in rows:
            day = datetime.fromisoformat(str(r[date_key])[:10]).date()
            # Do not turn an unfinished daily bar into a closing observation.
            if day > local.date() or day == local.date() and (local.hour, local.minute) < (15, 10):
                continue
            value = float(r[close_key])
            if value <= 0 or not math.isfinite(value):
                continue
            valid.append((day, value, r))
        if not valid:
            return {"status": "empty", "message": "来源尚无可用的已完成交易日价格或正式净值"}
        valid.sort(key=lambda r: r[0])
        day, price, _ = valid[-1]
        # Day precision is explicit metadata; 15:00 CN is the close boundary,
        # never a claim that the provider supplied a second-precision timestamp.
        when = datetime.combine(day, datetime.min.time(), tzinfo=local.tzinfo).replace(hour=15).astimezone(timezone.utc)
        quote = {"code": asset["code"], "provider": "akshare", "market": "CN", "current_price": price,
                 "quote_time": when, "is_delayed": True, "license_note": "AKShare 公开来源，按上游使用条件使用",
                 "price_kind": "nav" if kind == "fund" else "price", "currency": asset.get("currency", "CNY"),
                 "unit": asset.get("unit", "share"), "price_date": day.isoformat(), "time_precision": "day",
                 "upstream": upstream, "fetched_at": now.isoformat()}
        bars = [] if kind == "fund" else [{"code": asset["code"], "provider": "akshare", "period": "K_DAY",
            "time_key": d.isoformat(), "open": float(r.get("open", p)), "close": p,
            "high": float(r.get("high", p)), "low": float(r.get("low", p)),
            "volume": float(r.get("volume", 0)), "turnover": float(r.get("amount", 0))} for d, p, r in valid[-250:]]
        return {"status": "available", "quotes": [quote], "bars": bars, "message": "已获取正式净值" if kind == "fund" else "已获取收盘行情"}


def _worker():
    import contextlib
    import io
    import akshare as ak
    request = json.loads(sys.stdin.read())
    functions = {"stock": ak.stock_zh_a_daily, "etf": ak.fund_etf_hist_sina,
                 "fund": ak.fund_open_fund_info_em, "news": ak.stock_news_em, "fund_codes": ak.fund_name_em,
                 "us": ak.stock_us_daily, "gold": ak.futures_foreign_hist, "fx": ak.currency_boc_safe}
    action, kwargs = request["action"], request["kwargs"]
    if action == "etf":
        kwargs = {"symbol": kwargs["symbol"]}
    elif action == "fund":
        kwargs["indicator"] = "单位净值走势"
    elif action in {"stock", "us"}:
        kwargs["adjust"] = ""
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            frame = functions[action](**kwargs)
        if action in {"us", "gold"}:
            frame = frame.tail(500)
        print(json.dumps({"items": json.loads(frame.to_json(orient="records", date_format="iso"))}, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__}))


if __name__ == "__main__":
    _worker()
