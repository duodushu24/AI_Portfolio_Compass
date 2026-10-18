from __future__ import annotations

from copy import deepcopy
from bisect import bisect_right
from datetime import datetime, timezone
from decimal import Decimal

from .ledger import Ledger, ZERO, key, number


def instant(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise ValueError("请填写有效的实际时间")
    if value.tzinfo:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def iso(value):
    return instant(value).isoformat() + "Z"


def public(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return iso(value)
    if isinstance(value, dict):
        return {str(k): public(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [public(v) for v in value]
    return value


class FxHistory:
    """Saved dated facts, including backfills; never the mutable live FX cache."""
    def __init__(self, timeline):
        self.rows, self.times = {}, {}
        for order, (timestamp, _, _, kind, owner, data, record_id) in enumerate(timeline):
            for curr, item in data.get("fx", {}).items():
                if curr == "CNY":
                    continue
                fact = {**deepcopy(item), "recorded_at": iso(timestamp),
                        "record_type": kind, "record_id": record_id, "account_id": owner}
                self.rows.setdefault(curr, []).append((instant(item["at"]), order, fact))
        for curr, rows in self.rows.items():
            rows.sort(key=lambda row: (row[0], row[1]))
            self.times[curr] = [row[0] for row in rows]

    def at(self, at, preferred=None):
        result = {"CNY": {"rate": "1", "at": None, "source": "本币"}}
        for curr, rows in self.rows.items():
            index = bisect_right(self.times[curr], at) - 1
            if index >= 0:
                result[curr] = {**deepcopy(rows[index][2]), "selection": "latest"}
        for curr, item in (preferred or {}).items():
            if curr != "CNY" and instant(item["at"]) <= at:
                result[curr] = {**deepcopy(item), "selection": "explicit"}
        for curr, item in result.items():
            if curr != "CNY":
                item["carried"] = instant(item["at"]) < at
        return result


class Prices:
    def __init__(self):
        self.prices = {}
        self.real_prices = {}
        self.observed_at = {}
        self.close_dates = {}
        self.fx = {"CNY": {"rate": "1", "at": None, "source": "本币"}}

    def update(self, data, at):
        for item in data.get("prices", []):
            if item.get("price") is None:
                continue
            k = key(item)
            previous = self.prices.get(k)
            if not previous or instant(item["at"]) >= instant(previous["at"]):
                self.prices[k] = deepcopy(item)
            # Keep genuine observations independently of newer trade/estimate values.
            if item.get("price_kind") != "estimate" and item.get("valuation_origin") != "trade":
                previous_real = self.real_prices.get(k)
                if not previous_real or instant(item["at"]) >= instant(previous_real["at"]):
                    self.real_prices[k] = deepcopy(item)
                    self.observed_at[k] = at
                    self.close_dates[k] = data.get("valuation_date")
        for curr, item in data.get("fx", {}).items():
            previous = self.fx.get(curr)
            if curr != "CNY" and (not previous or instant(item["at"]) >= instant(previous["at"])):
                self.fx[curr] = deepcopy(item)

    def rate(self, curr):
        item = self.fx.get(curr)
        return number(item["rate"]) if item else None

    def value(self, ledger, accounts, at, *, latest=False, include_cycles=True):
        positions, cash, pending, liabilities, issues = [], [], [], [], []
        total, market_value, cash_value = ZERO, ZERO, ZERO

        def convert(curr, amount):
            if amount == ZERO:
                return ZERO
            fx = self.fx.get(curr)
            if not fx:
                issues.append(f"缺少 {curr}/CNY 汇率")
                return None
            if curr != "CNY" and instant(fx["at"]) < at:
                issues.append(f"{curr}/CNY 沿用 {fx['at']} 汇率")
            if fx.get("is_estimate"):
                issues.append(f"{curr}/CNY 使用估算汇率：{fx['source']}")
            return amount * number(fx["rate"])

        for account_id in sorted(accounts):
            book = ledger.accounts[account_id]
            for k, p in book["positions"].items():
                quote = self.prices.get(k)
                if ledger.accounts[account_id].get("valuation_policy") == "explicit_only":
                    quote = self.real_prices.get(k)
                    same_batch = self.observed_at.get(k) == at and self.close_dates.get(k)
                    if quote and (instant(quote["at"]) > at or not latest and instant(quote["at"]) != at and not same_batch):
                        quote = None
                q, cost = p["quantity"], p["cost"]
                price = number(quote["price"]) if quote else None
                mv = q * price if price is not None else ZERO if not q else None
                native_gain = mv - cost if mv is not None and cost is not None and q else ZERO if not q else None
                cny = ZERO if not q else convert(p["currency"], mv) if mv is not None else None
                if q and quote is None:
                    issues.append(f"{account_id}/{p['code']} 缺少价格")
                same_close = self.observed_at.get(k) == at and self.close_dates.get(k) and quote == self.real_prices.get(k)
                if q and quote and instant(quote["at"]) < at and not same_close:
                    issues.append(f"{p['code']} 沿用 {quote['at']} 报价")
                if q and quote and quote.get("price_kind") == "estimate":
                    issues.append(f"{p['code']} 使用估算价格/净值")
                if q and cny is not None:
                    total += cny
                    market_value += cny
                positions.append({"account_id": account_id, "code": p["code"], "name": p.get("name", p["code"]),
                    "market": p["market"], "asset_type": p.get("asset_type", "stock"), "unit": p["unit"], "currency": p["currency"],
                    "quantity": q, "cost": cost, "cost_cny": p["cost_cny"],
                    "average_cost": cost / q if cost is not None and q else None,
                    "diluted_cost": cost / q if cost is not None and q else None, "cost_method": "diluted",
                    "dividends": p["cycle_dividends"] if q else ZERO,
                    "dividends_cny": p["cycle_dividends_cny"] if q else ZERO,
                    "price": price, "market_value": mv, "market_value_cny": cny,
                    "floating": native_gain, "holding_return": native_gain / cost if q and cost is not None and cost > ZERO and native_gain is not None else None,
                    "floating_cny": cny - p["cost_cny"] if q and cny is not None and p["cost_cny"] is not None else None,
                    "realized": p["realized"], "realized_cny": p["realized_cny"], "cycle": p["cycle"],
                    "closed_cycles": deepcopy(p["closed_cycles"]) if include_cycles else [],
                    "closed_return": p["closed_cycles"][-1]["return"] if not q and p["closed_cycles"] and p["closed_cycles"][-1]["cycle"] == p["cycle"] else None,
                    "quote": quote, "fx": self.fx.get(p["currency"]), "last_at": p["last_at"], "first_at": p["first_at"],
                    "position_layer": p.get("position_layer") or "中期配置仓"})
            for curr, amount in book["cash"].items():
                cny = convert(curr, amount) if amount else ZERO
                cash.append({"account_id": account_id, "currency": curr, "amount": amount, "value_cny": cny})
                if cny is not None:
                    total += cny
                    cash_value += cny
            for record_id, item in book["pending"].items():
                cny = convert(item["currency"], item["amount"])
                pending.append({"account_id": account_id, "pending_id": record_id, **item, "value_cny": cny})
                if cny is not None:
                    total += cny
            for curr, amount in book["liabilities"].items():
                cny = convert(curr, amount) if amount else ZERO
                liabilities.append({"account_id": account_id, "currency": curr, "amount": amount, "value_cny": cny})
                if cny is not None:
                    total -= cny
        for account_id in sorted(accounts):
            if ledger.accounts[account_id].get("unallocated_dividends"):
                issues.append(f"{account_id} 有分红尚未归属标的/持有阶段；现金已计入，清仓收益待核对")
        complete = not any("缺少" in s for s in issues)
        for p in positions:
            p["position_weight"] = p["market_value_cny"] / total if complete and total > ZERO and p["market_value_cny"] is not None else None
        asset_returns = {}
        for code in {p["code"] for p in positions}:
            group = [p for p in positions if p["code"] == code and p["quantity"]]
            cost = sum((p["cost"] or ZERO for p in group), ZERO)
            available = group and len({(p["currency"], p["unit"]) for p in group}) == 1 and all(p["cost"] is not None and p["floating"] is not None for p in group)
            asset_returns[code] = sum((p["floating"] for p in group), ZERO) / cost if available and cost > ZERO else None
        return {"total_assets": total if complete else None, "known_assets": total,
                "market_value": market_value if all(p["market_value_cny"] is not None for p in positions) else None,
                "cash_value": cash_value if all(c["value_cny"] is not None for c in cash) else None,
                "positions": positions, "cash": cash, "pending": pending,
                "liabilities": liabilities, "asset_returns": asset_returns, "issues": sorted(set(issues)), "quality": "missing" if not complete else "estimated" if issues else "complete"}


def replay(openings, deals, events, scope="all", until=None, *, latest_current=False, compact=False):
    """Deterministic replay; no current FX cache, network, or edits to source rows."""
    timeline = []
    for row in openings:
        timeline.append((row.effective_at, 0, row.account_id, "opening", row.account_id, row.data, None))
        if row.included_at is not None:
            timeline.append((row.included_at, 2, row.account_id, "include", row.account_id, {}, None))
        if row.excluded_at is not None:
            timeline.append((row.excluded_at, 4, row.account_id, "exclude", row.account_id, {}, None))
    for row in deals:
        if row.ledger_data and not row.is_void:
            data = {**row.ledger_data, "record_id": f"deal:{row.id}"}
            timeline.append((row.deal_time, 3, f"deal:{row.id:012}", "trade", row.account_id, data, row.id))
    for row in events:
        if not row.is_void:
            timeline.append((row.effective_at, 1 if row.kind == "valuation" else 3, f"event:{row.id:012}", row.kind, row.account_id, row.data, row.id))
    timeline.sort(key=lambda e: (instant(e[0]), e[1], e[2]))
    fx_history = FxHistory(timeline)
    ledger, prices, included, points = Ledger(), Prices(), set(), []
    units, base, net_flows, last_nav = ZERO, None, ZERO, None
    interval, valid, cumulative_issues = 0, True, set()
    missing_opening_at = None
    last_at = None
    baseline_active = False
    for timestamp, _, _, kind, account_id, data, record_id in timeline:
        at = instant(timestamp)
        if until and at > instant(until):
            break
        last_at = at
        before_scope = set(included) if scope == "all" else {scope} & set(ledger.accounts)
        if kind == "opening":
            ledger.open(account_id, data)
            prices.update(data, at)
        elif kind == "valuation":
            prices.update(data, at)
        else:
            prices.update(data, at)
        # A backdated observation can repair earlier transactions, but no rate
        # whose actual time is later than this event may enter its calculation.
        prices.fx = fx_history.at(at, data.get("fx"))
        # A trade price is a dated observation; it also values the same asset in other accounts.
        if kind == "trade" and ledger.accounts[account_id].get("valuation_policy") != "explicit_only":
            prices.update({"prices": [{**{n: data[n] for n in ("code", "currency", "unit")},
                "price": data["price"], "at": iso(at), "source": data.get("source", "成交"), "valuation_origin": "trade", "price_kind": "nav" if data["asset_type"] == "fund" else "price"}]}, at)
        if kind == "split":
            quote = prices.prices.get(key(data))
            if quote:
                prices.prices[key(data)] = {**quote, "price": str(number(quote["price"]) / number(data["factor"])), "source": "原报价按拆分比例调整", "price_kind": "estimate"}
        if kind in {"split", "share_credit"}:
            # A pre-adjustment unit price is not a post-adjustment market quote.
            prices.real_prices.pop(key(data), None)
        before = prices.value(ledger, before_scope, at, include_cycles=False)
        before_assets = before["total_assets"]
        flow, changes = ZERO, None
        if kind == "include":
            included.add(account_id)
        elif kind == "exclude":
            included.discard(account_id)
        elif kind == "trade":
            cost_fx = prices.fx.get(data["currency"])
            changes = ledger.trade(account_id, data, iso(at), prices.rate(data["currency"]), cost_fx)
        elif kind not in {"opening", "valuation"}:
            # Cash + custody transfers are one fact with both sides applied atomically.
            if kind == "position_transfer":
                p = ledger.accounts[account_id]["positions"].get(key(data))
                quote = prices.prices.get(key(data))
                rate = prices.rate(data["currency"])
                value = number(data["quantity"]) * number(quote["price"]) * rate if p and quote and rate is not None else None
                delta = int(data["to_account_id"] in before_scope) - int(account_id in before_scope)
                flow = value * delta if value is not None else None if delta else ZERO
            rate_item = prices.fx.get(data.get("currency", "CNY"))
            ledger.event(account_id, kind, data, f"event:{record_id}", iso(at), prices.rate(data.get("currency", "CNY")), rate_item)
            if kind in {"deposit", "withdrawal", "transfer"}:
                factor = int(account_id in before_scope) * (1 if kind == "deposit" else -1)
                if kind == "transfer":
                    factor += int(data["to_account_id"] in before_scope)
                rate = prices.rate(data["currency"])
                flow = number(data["amount"]) * factor * rate if rate is not None else None if factor else ZERO
        selected = set(included) if scope == "all" else {scope} & set(ledger.accounts)
        result = prices.value(ledger, selected, at, include_cycles=not compact)
        assets = result["total_assets"]
        if (kind in {"include", "exclude"} and scope == "all") or (kind == "opening" and scope == account_id):
            flow = assets - before_assets if assets is not None and before_assets is not None else None
        relevant = selected | before_scope
        if not relevant:
            continue
        # Events outside this scope can still change shared quotes; only emit relevant points.
        quoted = {key(i) for i in data.get("prices", [])}
        if kind == "trade" and ledger.accounts[account_id].get("valuation_policy") != "explicit_only":
            quoted.add(key(data))
        if kind == "split":
            quoted.add(key(data))
        held = {k for aid in relevant for k, p in ledger.accounts[aid]["positions"].items() if p["quantity"]}
        held_currencies = {k[1] for k in held} | {c for aid in relevant for c, amount in ledger.accounts[aid]["cash"].items() if amount}
        affects = account_id in relevant or kind == "valuation" or data.get("to_account_id") in relevant or bool(quoted & held) or bool(set(data.get("fx", {})) & held_currencies)
        if not affects:
            continue
        estimated_flow = flow not in (None, ZERO) and before["quality"] != "complete" and base is not None
        is_baseline = scope == "all" and kind == "valuation" and data.get("performance_baseline") == "all"
        if is_baseline:
            if assets is None or assets <= ZERO:
                raise ValueError("收益基准需要全部纳入账户的完整报价、汇率及正净资产")
            base, units, net_flows, last_nav = assets, assets, ZERO, Decimal(1)
            interval, valid, missing_opening_at = 1, True, None
            baseline_active = True
            cumulative_issues.clear()
            points.clear()
        if base is None and assets is None and missing_opening_at is None:
            missing_opening_at = at
        if base is None and assets is not None and assets > ZERO and (missing_opening_at is None or at == missing_opening_at):
            base, units, net_flows, last_nav = assets, assets, ZERO, Decimal(1)
            interval += 1
            valid = True
            if missing_opening_at == at:
                cumulative_issues.clear()
        elif base is not None and not is_baseline:
            if flow is None or before_assets is None or assets is None:
                if flow != ZERO:
                    valid = False
            else:
                net_flows += flow
                if flow:
                    if units > ZERO and before_assets > ZERO:
                        nav_before = before_assets / units
                        last_nav = nav_before
                        units += flow / nav_before
                    elif units == ZERO and assets > ZERO:
                        base, units, net_flows, last_nav = assets, assets, ZERO, Decimal(1)
                        interval += 1
                        valid = True
                        cumulative_issues.clear()
                    else:
                        valid = False
                if units < Decimal("-0.00000001"):
                    raise ValueError("出金或范围移出超过账户净资产")
                if abs(units) < Decimal("0.00000001"):
                    units = ZERO
                if units > ZERO:
                    last_nav = assets / units
        if base is None and missing_opening_at is not None:
            cumulative_issues.add("期初完整估值缺失；请补录期初时点报价/汇率或纠正期初，后续市值不能替代收益起点")
        if estimated_flow:
            cumulative_issues.add(f"{iso(at)} 资金流使用沿用报价/汇率估值，补录当时报价可重算")
        if baseline_active and any(fx.get("is_estimate") for fx in prices.fx.values()):
            cumulative_issues.add("历史观察包含用户授权的估算汇率；相关日期的人民币收益为估算值")
        if not valid:
            cumulative_issues.add("资金流边界资料缺失，需补录后才能还原净值")
        if any(ledger.accounts[aid].get("valuation_policy") == "explicit_only" for aid in selected) and not baseline_active:
            cumulative_issues = {"历史估值未补齐，暂不计算历史收益率；当前持仓可显示带日期的真实报价"}
        result.update(observed_at=iso(at), account_ids=sorted(selected), event_type=kind,
            fx_basis={curr: deepcopy(item) for curr, item in prices.fx.items() if curr != "CNY" and curr in held_currencies},
            valuation_date=data.get("valuation_date") if kind == "valuation" else None,
            record_id=record_id, account_id=account_id, data=data, changes=changes,
            units=units, nav=last_nav if valid and assets is not None else None,
            cumulative_return=last_nav - 1 if valid and last_nav is not None and assets is not None else None,
            profit=assets - base - net_flows if base is not None and assets is not None and valid else None,
            opening_assets=base, net_flows=net_flows, external_flow=flow, interval=interval,
            ended=units == ZERO and base is not None, performance_issues=sorted(cumulative_issues))
        if any(ledger.accounts[aid].get("valuation_policy") == "explicit_only" for aid in selected) and not baseline_active:
            # Missing valuations at funding boundaries cannot be repaired with later quotes.
            result.update(nav=None, cumulative_return=None, profit=None)
        points.append(deepcopy(result))
    current = deepcopy(points[-1]) if points else None
    if current and compact:
        # Closed stages belong in the current/detail view, not every history point.
        for p in current["positions"]:
            p["closed_cycles"] = deepcopy(ledger.accounts[p["account_id"]]["positions"][key(p)]["closed_cycles"])
    if current and latest_current:
        selected = set(current["account_ids"])
        if any(ledger.accounts[aid].get("valuation_policy") == "explicit_only" for aid in selected):
            # Only the present view may use an older genuine quote. Historical points
            # stay missing; this overlay must never become a saved valuation fact.
            current.update(prices.value(ledger, selected, last_at, latest=True))
            if baseline_active and valid and current["total_assets"] is not None:
                nav = current["total_assets"] / units if units > ZERO else last_nav
                current.update(nav=nav, cumulative_return=nav - 1 if nav is not None else None,
                               profit=current["total_assets"] - base - net_flows)
    return {"points": points, "current": current, "ledger": ledger, "prices": prices, "as_of": iso(last_at) if last_at else None}
