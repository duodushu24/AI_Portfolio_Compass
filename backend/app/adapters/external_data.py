"""Optional adapters. Registration and credentials are owned by the shared catalog."""
from copy import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class FutuDataAdapter:
    def __init__(self, config):
        from app.adapters.futu_adapter import FutuReadOnlyAdapter
        self.adapter = FutuReadOnlyAdapter()
        self.adapter.settings = copy(self.adapter.settings)
        self.adapter.settings.futu_host = config["host"]
        self.adapter.settings.futu_port = int(config["port"])
        self.adapter.settings.news_provider = "futu"

    def fetch(self, asset, data_type, now=None):
        from app.services.providers import normalize_symbol
        if asset.get("asset_type") in {"fund", "precious_metal"}:
            return {"status": "unsupported", "message": "富途证券报价不适用于场外基金或银行黄金，请选择相应来源或手动更新"}
        code = normalize_symbol(asset["code"], "futu")
        now = now or datetime.now(timezone.utc)
        if data_type == "news":
            rows, error = self.adapter.fetch_news_items([{**asset, "code": code}])
            for row in rows:
                row["code"] = asset["code"]
            return {"status": "available" if rows else "request_failed" if error else "empty", "news": rows,
                    "message": "已获取富途新闻" if rows else "富途未返回新闻，请核对该市场权限"}
        rows = self.adapter.fetch_quote_summaries([code])
        for row in rows:
            row.update(code=asset["code"], currency=asset["currency"], unit=asset["unit"], price_kind="price", fetched_at=now.isoformat())
        return {"status": "available" if rows else "request_failed", "quotes": rows,
                "message": "已获取富途行情" if rows else "富途未返回行情，请核对连接及该市场权限"}


class MarketauxAdapter:
    def __init__(self, config):
        self.token = config.get("api_token", "")

    def fetch(self, asset, data_type, now=None):
        if data_type != "news" or asset["market"] != "US":
            return {"status": "unsupported", "message": "当前仅支持美股相关新闻"}
        now = now or datetime.now(timezone.utc)
        params = urlencode({"api_token": self.token, "symbols": asset["code"].split(".", 1)[-1],
            "published_after": (now - timedelta(days=7)).isoformat(), "limit": 3})
        with urlopen(Request("https://api.marketaux.com/v1/news/all?" + params, headers={"User-Agent": "PortfolioCompass/1.0"}), timeout=12) as response:
            data = json.load(response)
        if data.get("error"):
            return {"status": "permission_denied", "message": "新闻服务未授权或额度不足，请在数据源配置中检查"}
        rows = []
        for r in data.get("data", []):
            url = str(r.get("url") or "")
            if not url.startswith(("http://", "https://")) or not r.get("title"):
                continue
            rows.append({"news_id": "marketaux:" + hashlib.sha256((asset["code"] + url).encode()).hexdigest(),
                "code": asset["code"], "market": "US", "provider": "marketaux", "news_type": "news",
                "title": r["title"], "source": r.get("source", "Marketaux"), "url": url,
                "publish_time": datetime.fromisoformat(r["published_at"].replace("Z", "+00:00")) if r.get("published_at") else None,
                "fetched_at": now})
        return {"status": "available" if rows else "empty", "news": rows,
                "message": "新闻已获取" if rows else "本次未检索到匹配新闻"}
