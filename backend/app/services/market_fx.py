"""Fetch FX before prices; retain dated saved facts on failure, never a fixed rate."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from app.models import ExchangeRate, PortfolioOpening
from .portfolio.performance import instant, iso


def valid_rate(value):
    try:
        rate = Decimal(str(value))
        return rate if rate.is_finite() and 0 < rate <= Decimal("1e24") else None
    except Exception:
        return None


def latest_saved(db, currency, now=None, *, include_display_cache=True):
    from .portfolio.service import calculate
    now = instant(now or datetime.now(timezone.utc))
    candidates = []
    fact = calculate(db)["prices"].fx.get(currency)
    if fact and valid_rate(fact.get("rate")) and fact.get("at") and instant(fact["at"]) <= now:
        candidates.append(dict(fact))
    rows = db.scalars(select(ExchangeRate).where(
        ((ExchangeRate.base_currency == currency) & (ExchangeRate.quote_currency == "CNY")) |
        ((ExchangeRate.base_currency == "CNY") & (ExchangeRate.quote_currency == currency))))
    for row in rows:
        if not include_display_cache and row.source == "frankfurter":
            continue
        if row.source == "static_fallback" or not row.rate_time or instant(row.rate_time) > now or not valid_rate(row.rate):
            continue
        if row.fetched_at and instant(row.fetched_at) > now:
            continue
        payload = row.raw_payload or {}
        if "rate" in payload and not valid_rate(payload["rate"]):
            continue
        rate = Decimal(str(row.rate)) if row.base_currency == currency else 1 / Decimal(str(row.rate))
        candidates.append({"rate": str(rate), "at": iso(row.rate_time), "source": payload.get("source") or row.source,
            "rate_date": payload.get("rate_date") or instant(row.rate_time).date().isoformat(),
            "fetched_at": iso(row.fetched_at) if row.fetched_at else None})
    return max(candidates, key=lambda r: instant(r["at"])) if candidates else None


def update(db, account_id, currencies, adapters, now=None):
    from . import data_sources
    from .portfolio.service import save_event, calculate
    fixed_time = now
    now = now or datetime.now(timezone.utc)
    rates, items, changed = {}, [], 0
    def publish(fact, currency):
        current = calculate(db)["prices"].fx.get(currency)
        different = not current or instant(current["at"]) != instant(fact["at"]) or Decimal(str(current["rate"])) != Decimal(str(fact["rate"]))
        if different and db.get(PortfolioOpening, account_id):
            received_at = fixed_time or datetime.now(timezone.utc)
            save_event(db, {"account_id": account_id, "kind": "valuation", "effective_at": iso(received_at),
                "data": {"fx": {currency: {**fact, "available_from": iso(received_at)}}, "note": "手动更新行情：先更新汇率"}}, commit=False)
        return int(different)
    for currency in sorted(set(currencies) - {"CNY"}):
        previous = latest_saved(db, currency, now)
        provider = data_sources.choose(db, "fx", "CN")
        result = data_sources.fetch(db, provider, {"code": currency + "/CNY", "currency": currency, "market": "CN"}, "fx", adapters)
        if result["status"] == "available":
            try:
                row = next(r for r in result["fx"] if r["currency"] == currency)
                if not valid_rate(row["rate"]) or instant(row["at"]) > instant(now):
                    raise ValueError("invalid rate")
                if previous and instant(row["at"]) < instant(previous["at"]):
                    changed += publish(previous, currency)
                    rates[currency] = previous
                    items.append({"currency": currency, "status": "carried", **previous,
                        "message": f"{currency}/CNY 来源尚无更新汇率，沿用 {previous.get('rate_date') or instant(previous['at']).date().isoformat()} 的有效记录"})
                    continue
                with db.begin_nested():
                    cached = db.scalar(select(ExchangeRate).where(ExchangeRate.base_currency == currency,
                        ExchangeRate.quote_currency == "CNY", ExchangeRate.source == provider.name))
                    if cached and cached.rate_time and instant(cached.rate_time) == instant(row["at"]) and Decimal(str(cached.rate)) != Decimal(str(row["rate"])):
                        raise ValueError("conflicting rate")
                    fact = {k: row[k] for k in ("rate", "at", "source", "rate_date", "time_precision", "fetched_at") if k in row}
                    # Automatic observations can value the present without rewriting earlier costs.
                    received_at = fixed_time or datetime.now(timezone.utc)
                    fact["available_from"] = iso(received_at)
                    fact["fetched_at"] = iso(received_at)
                    ledger_changed = publish(fact, currency)
                    cached = cached or ExchangeRate(base_currency=currency, quote_currency="CNY", source=provider.name)
                    cached.rate, cached.rate_time, cached.fetched_at = float(row["rate"]), instant(row["at"]), instant(received_at)
                    cached.expires_at, cached.is_stale, cached.raw_payload = instant(received_at + timedelta(minutes=15)), False, {**row, "fetched_at": fact["fetched_at"]}
                    db.add(cached); db.flush()
                rates[currency] = fact
                changed += int(ledger_changed)
                items.append({"currency": currency, "status": "updated", **fact, "message": result["message"]})
                continue
            except (ValueError, TypeError, KeyError, StopIteration):
                result = {"status": "invalid_data", "message": "汇率日期、数值无效或与同一时点记录冲突"}
        if previous:
            changed += publish(previous, currency)
            rates[currency] = previous
            items.append({"currency": currency, "status": "carried", **previous,
                "message": f"{currency}/CNY 本次未更新，沿用 {previous.get('rate_date') or instant(previous['at']).date().isoformat()} 的有效汇率；{result['message']}"})
        else:
            items.append({"currency": currency, "status": "missing", "message": f"缺少有效 {currency}/CNY 汇率，请补录或稍后重试；{result['message']}"})
    return {"rates": rates, "items": items, "updated_count": changed}
