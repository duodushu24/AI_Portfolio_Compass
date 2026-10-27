"""Provider-neutral configuration, selection and public-data probes; no ledger writes."""
from datetime import datetime, timezone
from importlib.util import find_spec
import subprocess
import math

from sqlalchemy import select, delete

from app.config import get_settings
from app.models import Account, DataProviderConfig, DataSourceState
from .providers import provider_registry, normalize_market


def _environment_order(kind):
    settings = get_settings()
    value = ""
    if kind == "quote":
        value = settings.market_data_provider_priority
    elif kind == "news":
        value = settings.news_provider_priority or settings.news_provider
    return [v.strip().lower() for v in value.split(",") if v.strip()]


def config(db, provider):
    row = db.get(DataProviderConfig, provider.name) if db is not None else None
    data = dict(row.data or {}) if row else {}
    settings = get_settings()
    for field in provider.fields:
        if field["key"] not in data:
            env = field.get("env") or ({"host": "futu_host", "port": "futu_port"}.get(field["key"]) if provider.name == "futu" else "")
            data[field["key"]] = getattr(settings, env, None) if env else field.get("default", "")
    legacy_futu = provider.name == "futu" and db is not None and db.scalar(select(Account.account_id).where(
        (Account.market_data_provider == "futu") | (Account.news_data_provider == "futu")).limit(1)) is not None
    explicit_futu = "futu" in _environment_order("quote") or "futu" in _environment_order("news")
    data.setdefault("enabled", provider.name == "akshare" or provider.name == "futu" and (legacy_futu or explicit_futu) or provider.name == "marketaux" and bool(data.get("api_token")))
    return data


def availability(db, provider):
    if provider is None:
        return "unsupported", "该市场或资产暂无已实现来源，可手动更新"
    if not provider.factory:
        return "not_implemented", "该来源尚未实现取数接口"
    values = config(db, provider)
    if not values["enabled"]:
        return "disabled", "来源未启用，可在 AI与高级设置 → 数据源 中配置"
    if provider.name == "akshare" and find_spec("akshare") is None:
        return "dependency_missing", "AKShare 未安装，请按项目依赖安装说明安装"
    if any(f["type"] == "secret" and not values.get(f["key"]) for f in provider.fields):
        return "not_configured", "缺少 API Key，请在数据源中配置"
    return "configured", "已配置，尚需实际请求验证"


def catalog(db):
    result = []
    for p in provider_registry()._providers.values():
        if not p.factory:
            continue
        values = config(db, p)
        secrets = {f["key"] for f in p.fields if f["type"] == "secret"}
        status, message = availability(db, p)
        row = db.get(DataProviderConfig, p.name)
        result.append({"id": p.name, "label": p.label, "group": p.group, "description": p.license_note,
            "checks": list(p.checks) or [{"data_type": k, "label": {"quote": "行情／净值", "news": "新闻", "fx": "汇率"}[k]} for k in p.data_types if k in {"quote", "news", "fx"}],
            "capabilities": list(p.data_types), "markets": list(p.markets), "fields": list(p.fields),
            "config": {k: v for k, v in values.items() if k not in secrets and k != "last_check"},
            "secrets": {k: bool(values.get(k)) for k in secrets},
            "status": status, "message": message, "last_check": (row.data or {}).get("last_check") if row else None})
    return {"items": sorted(result, key=lambda r: (r["id"] != "akshare", r["label"]))}


def save_config(db, provider_id, payload):
    p = provider_registry().get(provider_id)
    if not p or not p.factory:
        raise ValueError("数据源尚未实现")
    allowed = {f["key"] for f in p.fields} | {"enabled", "preferred_quote", "preferred_news", "preferred_fx"}
    if payload.keys() - allowed:
        raise ValueError("配置包含不支持的字段")
    values = config(db, p)
    for k in ("enabled", "preferred_quote", "preferred_news", "preferred_fx"):
        if k in payload and type(payload[k]) is not bool:
            raise ValueError("启用和默认选择必须为布尔值")
        if k.startswith("preferred_") and payload.get(k) and k.removeprefix("preferred_") not in p.data_types:
            raise ValueError("此来源未实现所选能力")
    for field in p.fields:
        k = field["key"]
        if k not in payload or field["type"] == "secret" and payload[k] == "":
            continue  # Blank secret means unchanged; explicit null clears.
        value = payload[k]
        if field["type"] == "number":
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise ValueError("端口或超时时间需要填写整数")
            low, high = (3, 60) if k == "timeout_seconds" else (1, 65535)
            if not low <= value <= high:
                raise ValueError("端口或超时时间超出范围")
        elif value is not None and (not isinstance(value, str) or len(value) > 500 or any(c in value for c in "\r\n")):
            raise ValueError("配置值格式无效")
        values[k] = value
    values.update({k: payload[k] for k in ("enabled", "preferred_quote", "preferred_news", "preferred_fx") if k in payload})
    values.pop("last_check", None)
    try:
        row = db.get(DataProviderConfig, p.name) or DataProviderConfig(provider_id=p.name)
        row.data = values
        db.add(row)
        db.execute(delete(DataSourceState).where(DataSourceState.provider == p.name))
        for capability in ("quote", "news", "fx"):
            preference = "preferred_" + capability
            if values.get(preference):
                for other in db.scalars(select(DataProviderConfig).where(DataProviderConfig.provider_id != p.name)):
                    other.data = {**other.data, preference: False}
        db.commit()
    except Exception:
        db.rollback()
        raise
    return catalog(db)


def choose(db, data_type, market, explicit=""):
    registry = provider_registry()
    supports = lambda p: p and any(c.data_type == data_type and market in c.markets for c in p.capabilities())
    if explicit:
        p = registry.get(explicit)
        return p if supports(p) else None
    candidates = [p for p in registry._providers.values() if p.factory and supports(p)]
    preferred = [p for p in candidates if config(db, p).get("preferred_" + data_type) and config(db, p)["enabled"]]
    if preferred:
        return preferred[0]
    by_name = {p.name: p for p in candidates}
    for name in _environment_order(data_type):
        p = by_name.get(name)
        if p and availability(db, p)[0] == "configured":
            return p  # Only explicit environment selections can choose a paid source.
    return next((p for p in candidates if p.name == "akshare"), None)  # Never fall back to a paid source.


def account_states(db, markets, market_provider="", news_provider=""):
    rows = []
    for market in sorted({normalize_market(m) for m in markets} or {"CN"}):
        for kind, explicit in (("quote", market_provider), ("news", news_provider)):
            p = choose(db, kind, market, explicit)
            status, message = availability(db, p)
            rows.append({"provider": p.name if p else explicit, "provider_label": p.label if p else "未支持",
                "data_type": kind, "market": market, "status": status, "message": message,
                "checked_at": None, "license_note": p.license_note if p else "",
                "capabilities": [c.__dict__ for c in p.capabilities()] if p else []})
    return rows


def fetch(db, p, asset, kind, adapters=None):
    status, message = availability(db, p)
    if status != "configured":
        return {"status": status, "message": message}
    try:
        if adapters is None:
            adapter = p.factory(config(db, p))
        else:
            if p.name not in adapters:
                adapters[p.name] = p.factory(config(db, p))
            adapter = adapters[p.name]
        return adapter.fetch(asset, kind)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "message": "请求超时，原有数据已保留，请稍后重试"}
    except Exception as e:
        if getattr(e, "code", None) in {401, 403, 429}:
            return {"status": "permission_denied", "message": "来源授权失败或额度不足，请在数据源中检查 Key 和权限"}
        reason = str(e) if isinstance(e, RuntimeError) else type(e).__name__
        messages = {"dependency_missing": "AKShare 依赖未安装完整，请按安装说明重装依赖",
                    "ProxyError": "上游或代理连接失败，请检查本机代理设置或稍后重试",
                    "SSLError": "来源证书验证失败，请检查本机证书和代理设置",
                    "Timeout": "来源请求超时，请稍后重试", "ReadTimeout": "来源请求超时，请稍后重试",
                    "KeyError": "来源字段格式发生变化，请更新适配器后重试",
                    "JSONDecodeError": "来源未返回预期数据，请稍后重试或更新适配器"}
        return {"status": "dependency_missing" if reason == "dependency_missing" else "request_failed",
                "message": messages.get(reason, "来源请求或解析失败，原有数据已保留，请稍后检测连接")}


def probe(db, provider_id, kind="quote", market=None, sample=None):
    p = provider_registry().get(provider_id)
    if not p or not p.factory or kind not in {"quote", "news", "fx"} or kind not in p.data_types:
        raise ValueError("此来源未实现所选能力")
    market = "US" if sample == "us" else market or p.markets[0]
    samples = {"CN": ("CN.000001", "CNY"), "US": ("US.AAPL", "USD"), "HK": ("HK.00700", "HKD")}
    if market not in p.markets or market not in samples:
        raise ValueError("此来源未提供该市场的检测示例")
    code, currency = samples[market]
    asset = {"code": code, "name": "公开检测示例", "market": market, "asset_type": "stock", "currency": currency, "unit": "share"}
    adapters = {}
    if kind == "fx":
        asset.update(code="USD/CNY", currency="USD")
    elif sample == "gold":
        asset.update(code="CN.GOLD.PUBLIC_PROBE", market="CN", currency="CNY", unit="gram", asset_type="precious_metal")
        fx_result = fetch(db, p, {"code": "USD/CNY", "currency": "USD", "market": "CN"}, "fx", adapters)
        asset["conversion_fx"] = next(iter(fx_result.get("fx", [])), None)
    result = fetch(db, p, asset, kind, adapters)
    # Only a verified public observation proves quote availability; config never does.
    if result["status"] == "available" and not any(result.get(k) for k in ("quotes", "news", "fx")):
        result = {"status": "empty", "message": "来源本次未返回可验证的数据"}
    if result["status"] == "available":
        try:
            if kind == "quote":
                from .portfolio.performance import instant
                valid = any(r.get("code") == asset["code"] and math.isfinite(float(r["current_price"])) and float(r["current_price"]) > 0
                    and instant(r["quote_time"]) <= datetime.now(timezone.utc).replace(tzinfo=None)
                    and r.get("currency") == asset["currency"] and r.get("unit") == asset["unit"] for r in result.get("quotes", []))
            elif kind == "fx":
                from .portfolio.performance import instant
                valid = any(r["currency"] == "USD" and math.isfinite(float(r["rate"])) and float(r["rate"]) > 0
                    and instant(r["at"]) <= datetime.now(timezone.utc).replace(tzinfo=None) for r in result.get("fx", []))
            else:
                valid = any(r.get("title") and str(r.get("url") or "").startswith(("http://", "https://")) for r in result.get("news", []))
        except (ValueError, TypeError, KeyError):
            valid = False
        if not valid:
            result = {"status": "invalid_data", "message": "来源返回的价格、日期或新闻字段不完整，未通过检测，请更新适配器后重试"}
    check = {"status": result["status"], "message": result["message"], "checked_at": datetime.now(timezone.utc).isoformat(),
             "data_type": kind, "sample": sample, "sample_count": len(result.get("quotes", result.get("news", result.get("fx", []))))}
    row = db.get(DataProviderConfig, provider_id) or DataProviderConfig(provider_id=provider_id)
    row.data = {**config(db, p), "last_check": check}
    db.add(row); db.commit()
    return check
