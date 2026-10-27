"""Daily USD securities, London XAU reference and dated CNY FX observations."""
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
import math
import re
from zoneinfo import ZoneInfo

CN = timezone(timedelta(hours=8))
NY = ZoneInfo("America/New_York")
TROY_OUNCE_GRAMS = Decimal("31.1034768")


def positive(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result > 0 else None
    except (TypeError, ValueError):
        return None


class GlobalMarketData:
    def __init__(self, call):
        self.call = call
        self.fx_rows = None
        self.gold_rows = None
        self.errors = {}

    def once(self, action, **kw):
        if action in self.errors:
            raise self.errors[action]
        try:
            return self.call(action, **kw)
        except Exception as exc:
            self.errors[action] = exc
            raise

    def fx(self, asset, now):
        currency = asset.get("currency")
        column = {"USD": "美元", "HKD": "港元"}.get(currency)
        if not column:
            return {"status": "unsupported", "message": "自动汇率首批支持 USD/CNY、HKD/CNY"}
        if self.fx_rows is None:
            self.fx_rows = self.once("fx")
        valid = []
        for row in self.fx_rows:
            day = datetime.fromisoformat(str(row["日期"])[:10]).date()
            # SAFE publishes daily fixing at 09:15 CN; raw source has day precision.
            when = datetime.combine(day, time(9, 15), CN)
            rate = positive(row.get(column))
            if rate and when <= now:
                valid.append((when, Decimal(str(rate)) / 100))
        if not valid:
            return {"status": "empty", "message": f"来源尚无有效的 {currency}/CNY 日度汇率"}
        when, rate = max(valid)
        return {"status": "available", "message": f"已获取 {currency}/CNY 日度中间价", "fx": [{
            "currency": currency, "rate": str(rate), "at": when.isoformat(), "rate_date": when.date().isoformat(),
            "source": "akshare · SAFE中间价", "provider": "akshare", "upstream": "safe",
            "time_precision": "day", "fetched_at": now.isoformat()}]}

    def us(self, asset, now):
        symbol = asset["code"].split(".", 1)[-1]
        if asset.get("asset_type") not in {"stock", "etf", "leveraged_etf"} or not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,20}", symbol):
            return {"status": "unsupported", "message": "美股免费行情首批支持股票和 ETF，可手动更新其他类型"}
        if asset.get("currency") != "USD" or asset.get("unit") != "share":
            return {"status": "conflict", "message": "美股来源按美元/股报价，请核对持仓币种及单位"}
        rows = self.call("us", symbol=symbol)
        valid = []
        for r in rows:
            day = datetime.fromisoformat(str(r["date"])[:10]).date()
            close = datetime.combine(day, time(16), NY)
            price = positive(r.get("close"))
            if price and close + timedelta(minutes=15) <= now:
                valid.append((day, close, price, r))
        if not valid:
            return {"status": "empty", "message": "尚无可用的已收盘美股日线，请稍后更新"}
        valid.sort(key=lambda x: x[0])
        day, when, price, _ = valid[-1]
        quote = {"code": asset["code"], "provider": "akshare", "market": "US", "currency": "USD", "unit": "share",
            "current_price": price, "quote_time": when.astimezone(timezone.utc), "price_date": day.isoformat(),
            "time_precision": "day", "price_kind": "price", "upstream": "sina", "fetched_at": now.isoformat(), "is_delayed": True}
        bars = [{"code": asset["code"], "provider": "akshare", "period": "K_DAY", "time_key": d.isoformat(),
            "open": positive(r.get("open")) or p, "high": positive(r.get("high")) or p,
            "low": positive(r.get("low")) or p, "close": p, "volume": positive(r.get("volume")) or 0, "turnover": 0}
            for d, _, p, r in valid[-250:]]
        return {"status": "available", "message": "已获取美股不复权收盘行情", "quotes": [quote], "bars": bars}

    def gold(self, asset, now):
        if asset.get("currency") != "CNY" or asset.get("unit") != "gram" or not asset["code"].startswith("CN.GOLD."):
            return {"status": "conflict", "message": "黄金折算仅适用于人民币、克单位的独立黄金产品"}
        if self.gold_rows is None:
            # XAU is Sina's London spot reference/CFD, never COMEX GC futures.
            self.gold_rows = self.once("gold", symbol="XAU")
        valid = []
        for row in self.gold_rows:
            day = datetime.fromisoformat(str(row["date"])[:10]).date()
            price = positive(row.get("close"))
            # Conservative day end: never use the still-changing current UTC day.
            when = datetime.combine(day, time(23, 59, 59), timezone.utc)
            if price and when <= now:
                valid.append((when, Decimal(str(price))))
        if not valid:
            return {"status": "empty", "message": "尚无已完成日线的国际金价参考值"}
        fx = asset.get("conversion_fx")
        if not fx or not positive(fx.get("rate")):
            return {"status": "missing", "message": "国际金价已获取，但缺少有效 USD/CNY 汇率；请补录汇率后更新"}
        gold_at, usd_price = max(valid)
        fx_at = datetime.fromisoformat(fx["at"].replace("Z", "+00:00"))
        if fx_at > now:
            return {"status": "invalid_data", "message": "汇率日期晚于本次更新，未折算黄金市值"}
        when = max(gold_at, fx_at)
        reference = {"symbol": "XAU", "label": "新浪伦敦金现货参考（CFD）", "price_usd_oz": str(usd_price),
            "price_date": gold_at.date().isoformat(), "fx_rate": str(fx["rate"]), "fx_at": fx["at"],
            "fx_date": fx.get("rate_date") or fx_at.astimezone(CN).date().isoformat(), "fx_source": fx["source"]}
        quote = {"code": asset["code"], "provider": "akshare", "market": "CN", "currency": "CNY", "unit": "gram",
            "current_price": float(usd_price * Decimal(str(fx["rate"])) / TROY_OUNCE_GRAMS), "quote_time": when,
            "price_date": max(reference["price_date"], reference["fx_date"]), "time_precision": "day",
            "price_kind": "reference", "valuation_method": "international_spot_fx", "reference": reference,
            "upstream": "sina:XAU", "fetched_at": now.isoformat(), "is_delayed": True}
        return {"status": "available", "message": "已按国际金价和 USD/CNY 折算人民币/克参考价", "quotes": [quote]}
