from __future__ import annotations

from copy import deepcopy
from bisect import bisect_right
from datetime import datetime, timezone
from decimal import Decimal

from .ledger import Ledger, ZERO, key, number
from .profit import ProfitCarry


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
        self.fx = {"CNY": {"rate": "1", "at": None, "source": "本币"}}

    def update(self, data, at):
        for item in data.get("prices", []):
            if item.get("price") is None or item.get("valuation_origin") == "trade":
                continue
            k = key(item)
            previous = self.prices.get(k)
            if not previous or instant(item["at"]) >= instant(previous["at"]):
                self.prices[k] = deepcopy(item)
        for curr, item in data.get("fx", {}).items():
            previous = self.fx.get(curr)
            if curr != "CNY" and (not previous or instant(item["at"]) >= instant(previous["at"])):
                self.fx[curr] = deepcopy(item)

    def rate(self, curr):
        item = self.fx.get(curr)
        return number(item["rate"]) if item else None

    def value(self, ledger, accounts, at, *, include_cycles=True):
        positions, cash, pending, liabilities, issues, needs = [], [], [], [], [], []
        total, market_value, cash_value = ZERO, ZERO, ZERO
        estimated = False

        def convert(curr, amount, account_id):
            nonlocal estimated
            if amount == ZERO:
                return ZERO
            fx = self.fx.get(curr)
            if not fx:
                issues.append(f"缺少 {curr}/CNY 汇率")
                requirement = {"kind": "fx", "account_id": account_id, "currency": curr,
                               "at": iso(at), "action": "valuation", "context": "valuation"}
                if requirement not in needs:
                    needs.append(requirement)
                return None
            if fx.get("is_estimate"):
                estimated = True
                issues.append(f"{curr}/CNY 使用估算汇率：{fx['source']}")
            return amount * number(fx["rate"])

        for account_id in sorted(accounts):
            book = ledger.accounts[account_id]
            for k, p in book["positions"].items():
                quote = self.prices.get(k)
                # A partial update retains the last dated unit price, including for
                # imported accounts. Never substitute a future quote or total value.
                if quote and instant(quote["at"]) > at:
                    quote = None
                q, cost = p["quantity"], p["cost"]
                price = number(quote["price"]) if quote else None
                mv = q * price if price is not None else ZERO if not q else None
                native_gain = mv - cost if mv is not None and cost is not None and q else ZERO if not q else None
                cny = ZERO if not q else convert(p["currency"], mv, account_id) if mv is not None else None
                if q and quote is None:
                    issues.append(f"{p.get('name') or p['code']} 缺少市值价")
                    needs.append({"kind": "price", "account_id": account_id, "at": iso(at),
                                  "code": p["code"], "name": p.get("name") or p["code"],
                                  "currency": p["currency"], "unit": p["unit"],
                                  "action": "valuation", "context": "valuation"})
                    if p["currency"] not in self.fx:
                        # Report both absent inputs in one pass, rather than
                        # revealing the FX requirement only after the price is filled.
                        convert(p["currency"], Decimal(1), account_id)
                if q and quote and quote.get("price_kind") == "estimate":
                    estimated = True
                    issues.append(f"{p.get('name') or p['code']} 使用估算价格/净值")
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
                cny = convert(curr, amount, account_id) if amount else ZERO
                cash.append({"account_id": account_id, "currency": curr, "amount": amount, "value_cny": cny})
                if cny is not None:
                    total += cny
                    cash_value += cny
            for record_id, item in book["pending"].items():
                cny = convert(item["currency"], item["amount"], account_id)
                pending.append({"account_id": account_id, "pending_id": record_id, **item, "value_cny": cny})
                if cny is not None:
                    total += cny
            for curr, amount in book["liabilities"].items():
                cny = convert(curr, amount, account_id) if amount else ZERO
                liabilities.append({"account_id": account_id, "currency": curr, "amount": amount, "value_cny": cny})
                if cny is not None:
                    total -= cny
        for account_id in sorted(accounts):
            if ledger.accounts[account_id].get("unallocated_dividends"):
                issues.append(f"{account_id} 有分红尚未归属标的/持有阶段；现金已计入，清仓收益待核对")
        complete = not needs
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
                "liabilities": liabilities, "asset_returns": asset_returns, "issues": sorted(set(issues)),
                "data_needs": needs, "quality": "missing" if not complete else "estimated" if estimated else "complete"}


def replay(openings, deals, events, scope="all", until=None, *, compact=False, strict_baselines=()):
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
    # Quotes backfilled at the exact baseline instant must be available even
    # when their record ID sorts after the original baseline record.
    baseline_times = {instant(e[0]) for e in timeline if e[3] == "valuation" and e[5].get("performance_baseline") == "all"}
    baseline_batches, loaded_batches = {}, set()
    for entry in timeline:
        if entry[3] == "valuation" and instant(entry[0]) in baseline_times:
            baseline_batches.setdefault(instant(entry[0]), []).append(entry[5])
    fx_history = FxHistory(timeline)
    ledger, prices, included, points = Ledger(), Prices(), set(), []
    profits = ProfitCarry()
    units, base, net_flows, last_nav = ZERO, None, ZERO, None
    interval, valid, cumulative_issues = 0, True, set()
    flow_total_valid, performance_needs = True, []
    missing_opening_at = None
    pending_baseline, baseline_info = False, None
    last_at = None
    for timestamp, _, _, kind, account_id, data, record_id in timeline:
        at = instant(timestamp)
        if until and at > instant(until):
            break
        last_at = at
        before_scope = set(included) if scope == "all" else {scope} & set(ledger.accounts)
        if kind == "opening":
            ledger.open(account_id, data)
        # Execution prices are accounting facts, not closing prices or fund NAVs.
        # Only explicit opening/valuation observations may update market prices.
        if kind == "valuation" and at in baseline_batches:
            if at not in loaded_batches:
                for valuation in baseline_batches[at]:
                    prices.update(valuation, at)
                loaded_batches.add(at)
        elif kind in {"opening", "valuation"}:
            prices.update(data, at)
        # A backdated observation can repair earlier transactions, but no rate
        # whose actual time is later than this event may enter its calculation.
        prices.fx = fx_history.at(at, data.get("fx"))
        if kind == "opening":
            profits.open(account_id, data, prices.value(ledger, {account_id}, at, include_cycles=False), iso(at))
        if kind == "split":
            quote = prices.prices.get(key(data))
            if quote:
                prices.prices[key(data)] = {**quote, "price": str(number(quote["price"]) / number(data["factor"])), "source": "原报价按拆分比例调整", "price_kind": "estimate"}
        if kind == "share_credit":
            # Its ex-rights price cannot be inferred from the credited quantity.
            prices.prices.pop(key(data), None)
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
                transfer_needs = []
                if not quote:
                    transfer_needs.append({"kind": "price", "account_id": account_id, "at": iso(at),
                        "code": data["code"], "name": (p or data).get("name") or data["code"], "currency": data["currency"],
                        "unit": data["unit"], "action": "valuation", "context": "cash_flow"})
                if rate is None:
                    transfer_needs.append({"kind": "fx", "account_id": account_id, "at": iso(at),
                        "currency": data["currency"], "action": "valuation", "context": "cash_flow"})
                profits.flow(account_id, -value if value is not None else None, transfer_needs)
                profits.flow(data["to_account_id"], value, transfer_needs)
            rate_item = prices.fx.get(data.get("currency", "CNY"))
            ledger.event(account_id, kind, data, f"event:{record_id}", iso(at), prices.rate(data.get("currency", "CNY")), rate_item)
            if kind in {"deposit", "withdrawal", "transfer"}:
                factor = int(account_id in before_scope) * (1 if kind == "deposit" else -1)
                if kind == "transfer":
                    factor += int(data["to_account_id"] in before_scope)
                rate = prices.rate(data["currency"])
                flow = number(data["amount"]) * factor * rate if rate is not None else None if factor else ZERO
                amount = number(data["amount"]) * rate if rate is not None else None
                flow_needs = [{"kind": "fx", "account_id": account_id, "at": iso(at),
                    "currency": data["currency"], "action": "valuation", "context": "cash_flow"}] if rate is None else []
                profits.flow(account_id, amount if kind == "deposit" else -amount if amount is not None else None, flow_needs)
                if kind == "transfer":
                    profits.flow(data["to_account_id"], amount, flow_needs)
        selected = set(included) if scope == "all" else {scope} & set(ledger.accounts)
        result = prices.value(ledger, selected, at, include_cycles=not compact)
        assets = result["total_assets"]
        if (kind in {"include", "exclude"} and scope == "all") or (kind == "opening" and scope == account_id):
            flow = assets - before_assets if assets is not None and before_assets is not None else None
        relevant = selected | before_scope
        if not relevant:
            continue
        # Events outside this scope can still change shared quotes; only emit relevant points.
        quoted = {key(i) for i in data.get("prices", [])} if kind in {"opening", "valuation"} else set()
        if kind == "split":
            quoted.add(key(data))
        held = {k for aid in relevant for k, p in ledger.accounts[aid]["positions"].items() if p["quantity"]}
        held_currencies = {k[1] for k in held} | {c for aid in relevant for c, amount in ledger.accounts[aid]["cash"].items() if amount}
        affects = account_id in relevant or kind == "valuation" or data.get("to_account_id") in relevant or bool(quoted & held) or bool(set(data.get("fx", {})) & held_currencies)
        if not affects:
            continue
        estimated_flow = flow not in (None, ZERO) and before["quality"] == "estimated" and base is not None
        is_baseline = scope == "all" and kind == "valuation" and data.get("performance_baseline") == "all"
        if is_baseline:
            pending_baseline = assets is None or assets <= ZERO
            if pending_baseline and record_id in strict_baselines:
                raise ValueError("收益基准需要全部纳入账户的完整报价、汇率及正净资产")
            baseline_info = {"at": iso(at), "valuation_date": data.get("valuation_date"),
                             "record_id": record_id, "status": "missing" if assets is None else "nonpositive" if assets <= ZERO else "complete"}
            base, units, net_flows, last_nav = (None, ZERO, ZERO, None) if pending_baseline else (assets, assets, ZERO, Decimal(1))
            interval, valid, missing_opening_at = 1, not pending_baseline, None
            flow_total_valid, performance_needs = True, []
            cumulative_issues.clear()
            points.clear()
            if pending_baseline:
                performance_needs = [{**n, "context": "baseline", "valuation_date": data.get("valuation_date")} for n in result["data_needs"]]
                cumulative_issues.add("收益基准估值待补齐；请补录基准日的报价或汇率" if assets is None else "收益基准净资产须为正；请核对基准时点资金或重新设置基准")
        if pending_baseline and not is_baseline:
            if flow is None:
                flow_total_valid = False
            else:
                net_flows += flow
        if not pending_baseline and base is None and assets is None and missing_opening_at is None:
            missing_opening_at = at
            performance_needs = [{**n, "context": "opening", "action": "opening"} for n in result["data_needs"]]
        if not pending_baseline and base is None and assets is not None and assets > ZERO and (missing_opening_at is None or at == missing_opening_at):
            base, units, net_flows, last_nav = assets, assets, ZERO, Decimal(1)
            interval += 1
            valid = True
            flow_total_valid, performance_needs = True, []
            if missing_opening_at == at:
                cumulative_issues.clear()
        elif base is not None and not is_baseline:
            # The amount only needs net flows, not the portfolio valuation at
            # every flow boundary. Share-based returns need both independently.
            if flow is None:
                flow_total_valid = False
            else:
                net_flows += flow
            if flow is None or before_assets is None or assets is None:
                if flow != ZERO:
                    valid = False
                    for n in before["data_needs"] + result["data_needs"]:
                        requirement = {**n, "context": "cash_flow"}
                        if requirement not in performance_needs:
                            performance_needs.append(requirement)
            else:
                if flow:
                    if units > ZERO and before_assets > ZERO:
                        nav_before = before_assets / units
                        last_nav = nav_before
                        units += flow / nav_before
                    elif units == ZERO and assets > ZERO:
                        base, units, net_flows, last_nav = assets, assets, ZERO, Decimal(1)
                        interval += 1
                        valid = True
                        flow_total_valid, performance_needs = True, []
                        cumulative_issues.clear()
                    else:
                        valid = False
                if units < Decimal("-0.00000001"):
                    raise ValueError("出金或范围移出超过账户净资产")
                if abs(units) < Decimal("0.00000001"):
                    units = ZERO
            # A fully sold unquoted position restores a known portfolio value.
            # With no external flow, its prior missing price does not block NAV.
            if units > ZERO and assets is not None:
                last_nav = assets / units
        if base is None and missing_opening_at is not None:
            cumulative_issues.add("期初完整估值缺失；请补录期初时点报价/汇率或纠正期初，后续市值不能替代收益起点")
        if estimated_flow:
            cumulative_issues.add("部分资金进出时使用了明确标记的估算值，统计期收益率含估算")
        if any(fx.get("is_estimate") for fx in prices.fx.values()):
            cumulative_issues.add("历史观察包含用户授权的估算汇率；相关日期的人民币收益为估算值")
        if not valid and not pending_baseline:
            cumulative_issues.add("资金进出时缺少估值，统计期收益率待补齐" if performance_needs else "资金进出前净资产非正，无法计算统计期收益率")
        result.update(observed_at=iso(at), account_ids=sorted(selected), event_type=kind,
            fx_basis={curr: deepcopy(item) for curr, item in prices.fx.items() if curr != "CNY" and curr in held_currencies},
            valuation_date=data.get("valuation_date") if kind == "valuation" else None,
            record_id=record_id, account_id=account_id, data=data, changes=changes,
            performance_baseline=deepcopy(baseline_info),
            units=units, nav=last_nav if valid and assets is not None else None,
            cumulative_return=last_nav - 1 if valid and last_nav is not None and assets is not None else None,
            profit=assets - base - net_flows if base is not None and assets is not None and flow_total_valid else None,
            opening_assets=base, net_flows=net_flows if flow_total_valid else None, external_flow=flow, interval=interval,
            ended=units == ZERO and base is not None, performance_issues=sorted(cumulative_issues),
            performance_needs=deepcopy(performance_needs))
        result.update(profits.summary(result, selected))
        points.append(deepcopy(result))
    current = deepcopy(points[-1]) if points else None
    if current and compact:
        # Closed stages belong in the current/detail view, not every history point.
        for p in current["positions"]:
            p["closed_cycles"] = deepcopy(ledger.accounts[p["account_id"]]["positions"][key(p)]["closed_cycles"])
    return {"points": points, "current": current, "ledger": ledger, "prices": prices, "as_of": iso(last_at) if last_at else None}
