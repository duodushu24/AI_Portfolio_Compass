from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, Callable

from app.config import get_settings


MARKET_ALIASES = {
    "SH": "CN",
    "SZ": "CN",
    "SSE": "CN",
    "SZSE": "CN",
    "CN": "CN",
    "HK": "HK",
    "US": "US",
}


@dataclass(frozen=True)
class ProviderCapability:
    data_type: str
    markets: tuple[str, ...]
    realtime: bool = False
    delayed: bool = True
    requires_account: bool = False
    supports_news: bool = False
    supports_announcements: bool = False


@dataclass
class ProviderHealth:
    provider: str
    status: str
    message: str = ""
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AccountProvider(Protocol):
    name: str

    def health(self) -> ProviderHealth:
        ...

    def capabilities(self) -> list[ProviderCapability]:
        ...

    def fetch_snapshot(self) -> Any:
        ...


class MarketDataProvider(Protocol):
    name: str

    def health(self) -> ProviderHealth:
        ...

    def capabilities(self) -> list[ProviderCapability]:
        ...

    def fetch_quote_summaries(self, codes: list[str]) -> list[dict[str, Any]]:
        ...


class NewsProvider(Protocol):
    name: str

    def health(self) -> ProviderHealth:
        ...

    def capabilities(self) -> list[ProviderCapability]:
        ...

    def fetch_news(self, codes: list[str]) -> list[dict[str, Any]]:
        ...


@dataclass
class StaticProvider:
    name: str
    label: str
    data_types: tuple[str, ...]
    markets: tuple[str, ...]
    required_settings: tuple[str, ...] = ()
    requires_account: bool = False
    realtime: bool = False
    delayed: bool = True
    license_note: str = ""
    group: str = "paid"
    factory: Callable | None = None
    fields: tuple[dict, ...] = ()
    capability_markets: dict[str, tuple[str, ...]] = field(default_factory=dict)
    checks: tuple[dict, ...] = ()

    def health(self) -> ProviderHealth:
        settings = get_settings()
        missing = [key for key in self.required_settings if not str(getattr(settings, key, "") or "").strip()]
        if missing:
            env_names = ", ".join(_setting_to_env_name(key) for key in missing)
            return ProviderHealth(self.name, "not_configured", f"未配置 {env_names}")
        return ProviderHealth(self.name, "configured", "已配置，等待同步或接口检测")

    def capabilities(self) -> list[ProviderCapability]:
        return [
            ProviderCapability(
                data_type=data_type,
                markets=self.capability_markets.get(data_type, self.markets),
                realtime=self.realtime,
                delayed=self.delayed,
                requires_account=self.requires_account,
                supports_news=data_type == "news",
                supports_announcements=data_type in {"announcement", "filing"},
            )
            for data_type in self.data_types
        ]


class FutuProvider(StaticProvider):
    def __init__(self) -> None:
        super().__init__(
            name="futu",
            label="Futu / moomoo OpenD",
            data_types=("quote", "kline", "technical", "news"),
            markets=("US", "HK", "CN"),
            requires_account=True,
            realtime=True,
            delayed=False,
            license_note="需用户本地 OpenD 与账户授权；数据许可以券商账户为准。",
        )

    def health(self) -> ProviderHealth:
        try:
            from app.adapters.futu_adapter import FutuReadOnlyAdapter

            ok, message = FutuReadOnlyAdapter().health()
            return ProviderHealth(self.name, "available" if ok else "unavailable", message)
        except Exception as exc:  # pragma: no cover - depends on local OpenD
            return ProviderHealth(self.name, "unavailable", _safe_error(exc))


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, StaticProvider] = {}

    def register(self, provider: StaticProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> StaticProvider | None:
        return self._providers.get(name)

    def providers_for(self, data_type: str, market: str) -> list[StaticProvider]:
        normalized_market = normalize_market(market)
        providers = []
        for provider in self._providers.values():
            if provider.factory and any(cap.data_type == data_type and normalized_market in cap.markets for cap in provider.capabilities()):
                providers.append(provider)
        return providers

    def choose(self, *, data_type: str, market: str, broker_provider: str = "", preferred: list[str] | None = None) -> StaticProvider | None:
        candidates = self.providers_for(data_type, market)
        if not candidates:
            return None
        order = _provider_order(data_type, market, broker_provider, preferred)
        by_name = {provider.name: provider for provider in candidates}
        for name in order:
            if name in by_name:
                return by_name[name]
        return None


def provider_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(FutuProvider())
    registry.register(StaticProvider("alpaca", "Alpaca Market Data", ("quote", "news"), ("US",), ("alpaca_api_key", "alpaca_secret_key"), realtime=True, delayed=True, license_note="美股市场数据与新闻，免费层覆盖有限。"))
    registry.register(StaticProvider("polygon", "Polygon / Massive", ("quote", "kline"), ("US",), ("polygon_api_key",), realtime=True, delayed=True, license_note="商业行情源，按用户订阅权限使用。"))
    registry.register(StaticProvider("fmp", "Financial Modeling Prep", ("quote", "news"), ("US", "HK"), ("fmp_api_key",), delayed=True, license_note="独立 API，覆盖范围以官方接口和订阅层级为准。"))
    registry.register(StaticProvider("alpha_vantage", "Alpha Vantage", ("quote", "news"), ("US", "HK"), ("alpha_vantage_api_key",), delayed=True, license_note="独立 API，免费层有频率限制。"))
    registry.register(StaticProvider("tushare", "Tushare Pro", ("quote", "kline", "announcement"), ("CN", "HK"), ("tushare_token",), delayed=True, license_note="A股优先，港股按接口实际可用性检测。"))
    registry.register(StaticProvider("marketaux", "Marketaux", ("news",), ("US",), ("marketaux_api_token",), delayed=True, license_note="市场新闻 API，按用户自带 token 使用。"))
    registry.register(StaticProvider("sec_edgar", "SEC EDGAR", ("filing", "announcement"), ("US",), (), delayed=True, license_note="官方公告源；仅缓存元数据与链接。"))
    registry.register(StaticProvider("hkexnews", "HKEXnews", ("announcement",), ("HK",), (), delayed=True, license_note="港股公告源；仅缓存元数据与链接。"))
    registry.register(StaticProvider("cninfo", "巨潮资讯 CNINFO", ("announcement",), ("CN",), (), delayed=True, license_note="A股公告源；仅缓存元数据与链接。"))
    # This is the single catalog for implemented adapters and generated UI fields.
    futu = registry.get("futu")
    futu.factory, futu.fields = _futu_factory, (
        {"key": "host", "label": "OpenD 地址", "type": "text", "default": "127.0.0.1"},
        {"key": "port", "label": "OpenD 端口", "type": "number", "default": 11111})
    futu.license_note = "需登录 OpenD 并取得相应行情权限；实际费用依服务商权限规则，不代表每次请求收费。"
    registry.register(StaticProvider("akshare", "AKShare", ("quote", "news", "kline", "fx"), ("CN", "US"),
        group="free", factory=_akshare_factory, license_note="免费来源：境内股票/ETF、基金净值、美股股票/ETF 收盘价、国际金价折算参考与日度人民币中间价；新闻首批覆盖境内个股。",
        capability_markets={"news": ("CN",), "fx": ("CN",)},
        checks=({"label": "行情／净值", "data_type": "quote"}, {"label": "美股行情", "data_type": "quote", "sample": "us"},
                {"label": "金价折算", "data_type": "quote", "sample": "gold"}, {"label": "汇率", "data_type": "fx"}, {"label": "新闻", "data_type": "news"}),
        fields=({"key": "timeout_seconds", "label": "单次请求超时（秒）", "type": "number", "default": 20},)))
    marketaux = registry.get("marketaux")
    marketaux.group, marketaux.factory = "free", _marketaux_factory
    marketaux.fields = ({"key": "api_token", "label": "API Key", "type": "secret", "env": "marketaux_api_token"},)
    marketaux.license_note = "可选免费额度，需自行申请 Key；当前仅支持美股相关新闻，非默认来源。"
    return registry


def _akshare_factory(config):
    from app.adapters.akshare_adapter import AKShareAdapter
    return AKShareAdapter(config)


def _futu_factory(config):
    from app.adapters.external_data import FutuDataAdapter
    return FutuDataAdapter(config)


def _marketaux_factory(config):
    from app.adapters.external_data import MarketauxAdapter
    return MarketauxAdapter(config)


def normalize_market(value: str) -> str:
    text = str(value or "").strip().upper()
    return MARKET_ALIASES.get(text, text or "US")


def normalize_symbol(code: str, provider: str = "internal") -> str:
    market, symbol = split_symbol(code)
    if provider == "futu" or provider == "internal":
        if market == "CN" and symbol.startswith(("5", "6", "9")):
            return f"SH.{symbol}"
        if market == "CN":
            return f"SZ.{symbol}"
        return f"{market}.{symbol}"
    if provider in {"alpaca", "polygon", "alpha_vantage", "fmp", "marketaux"}:
        return symbol if market == "US" else f"{market}:{symbol}"
    if provider == "tushare":
        if market == "CN" and symbol.startswith(("6", "9")):
            return f"{symbol}.SH"
        if market == "CN":
            return f"{symbol}.SZ"
        if market == "HK":
            return f"{symbol}.HK"
    return f"{market}.{symbol}"


def split_symbol(code: str) -> tuple[str, str]:
    text = str(code or "").strip().upper()
    if "." in text:
        left, right = text.split(".", 1)
        if left in {"US", "HK", "CN", "SH", "SZ"}:
            return normalize_market(left), right
        return normalize_market(right), left
    if ":" in text:
        left, right = text.split(":", 1)
        return normalize_market(left), right
    if text.isdigit() and len(text) == 6:
        return "CN", text
    if text.isdigit() and len(text) <= 5:
        return "HK", text.zfill(5)
    return "US", text


def account_provider_statuses(broker_provider: str, markets: list[str], market_data_provider: str = "", news_data_provider: str = "", db=None) -> list[dict[str, Any]]:
    from .data_sources import account_states
    return account_states(db, markets, market_data_provider, news_data_provider)


def _status_row(provider_name: str, data_type: str, market: str, health: ProviderHealth, provider: StaticProvider | None = None) -> dict[str, Any]:
    return {
        "provider": provider_name or health.provider,
        "provider_label": provider.label if provider else provider_name,
        "data_type": data_type,
        "market": market,
        "status": health.status,
        "message": health.message,
        "checked_at": health.checked_at,
        "capabilities": [cap.__dict__ for cap in provider.capabilities()] if provider else [],
        "license_note": provider.license_note if provider else "",
    }


def _provider_order(data_type: str, market: str, broker_provider: str, preferred: list[str] | None) -> list[str]:
    return _dedupe([*(preferred or []), *(["akshare"] if market == "CN" and data_type in {"quote", "news", "kline"} else [])])


def _configured_priority(value: str) -> list[str]:
    return [item.strip().lower() for item in str(value or "").split(",") if item.strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _setting_to_env_name(name: str) -> str:
    return {
        "alpaca_api_key": "ALPACA_API_KEY",
        "alpaca_secret_key": "ALPACA_SECRET_KEY",
        "alpha_vantage_api_key": "ALPHA_VANTAGE_API_KEY",
        "fmp_api_key": "FMP_API_KEY",
        "polygon_api_key": "POLYGON_API_KEY",
        "tushare_token": "TUSHARE_TOKEN",
        "marketaux_api_token": "MARKETAUX_API_TOKEN",
    }.get(name, name.upper())


def _safe_error(exc: Exception) -> str:
    return str(exc).replace("\n", " ")[:300]
