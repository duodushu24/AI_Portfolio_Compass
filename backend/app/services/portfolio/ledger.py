from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation

ZERO = Decimal(0)
CURRENCIES = {"CNY", "HKD", "USD"}
ASSET_UNITS = {"stock": "share", "etf": "share", "fund": "fund_unit", "bond": "share", "leveraged_etf": "share", "precious_metal": "gram"}
ASSETS = set(ASSET_UNITS)


def asset_unit(asset_type, unit=None):
    """Explicit source units win; old securities retain their historical defaults."""
    return unit or ASSET_UNITS.get(asset_type, "share")


def number(value, *, minimum=None) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("金额、数量和价格必须是有效数字") from exc
    if not result.is_finite() or abs(result) > Decimal("1e24") or (minimum is not None and result < minimum):
        raise ValueError("金额、数量和价格超出有效范围")
    return result


def currency(value) -> str:
    value = str(value).strip().upper()
    if value not in CURRENCIES:
        raise ValueError("目前账目支持 CNY、HKD、USD；其他币种需要明确换算口径")
    return value


def key(data) -> tuple[str, str, str]:
    return (data["code"], data["currency"], data.get("unit", "share"))


class Ledger:
    def __init__(self):
        self.accounts: dict[str, dict] = {}

    @staticmethod
    def phase(p, at, cost=ZERO, cost_cny=ZERO, opening_kind="buy"):
        p.update(cost=cost, cost_cny=cost_cny, first_at=at, last_at=at,
                 cycle_buy_total=cost, cycle_buy_cny=cost_cny, cycle_sell_total=ZERO,
                 cycle_sell_cny=ZERO, cycle_dividends=ZERO, cycle_dividends_cny=ZERO,
                 cycle_dividend_records=[], cycle_trades=[], opening_kind=opening_kind)

    @staticmethod
    def closed_totals(p):
        for target, field in (("realized", "realized"), ("realized_cny", "realized_cny")):
            values = [c[field] for c in p["closed_cycles"]]
            p[target] = sum(values, ZERO) if all(v is not None for v in values) else None

    def open(self, account_id, data):
        if account_id in self.accounts:
            raise ValueError("账户已建档")
        book = {"positions": {}, "cash": {c: number(v) for c, v in data["cash"].items()},
                "pending": {}, "liabilities": {c: number(v) for c, v in data.get("liabilities", {}).items()},
                "unallocated_dividends": []}
        for item in data["positions"]:
            q = number(item["quantity"])
            confirmed = item.get("cost_method", data.get("cost_method")) == "diluted"
            cost = number(item["average_cost"]) * q if confirmed and item.get("average_cost") is not None else None
            cny = number(item["cost_cny_amount"]) if confirmed and item.get("cost_cny_amount") is not None else None
            position = {**deepcopy(item), "quantity": q, "realized": ZERO, "realized_cny": ZERO,
                        "cycle": 1, "closed_cycles": []}
            self.phase(position, data["effective_at"], cost, cny, "snapshot")
            book["positions"][key(item)] = position
        book["valuation_policy"] = data.get("valuation_policy", "trade_observations")
        self.accounts[account_id] = book

    def cash(self, account_id, curr, delta):
        book = self.accounts.get(account_id)
        if book is None:
            raise ValueError(f"账户 {account_id} 在此时点尚未建档")
        result = book["cash"].get(curr, ZERO) + delta
        # Cash-only accounts: no implicit margin borrowing.
        if result < ZERO:
            raise ValueError(f"账户 {account_id} 的 {curr} 现金不足，请补录真实资金或核对日期")
        book["cash"][curr] = max(result, ZERO)

    def trade(self, account_id, data, at, fx=None):
        if account_id not in self.accounts:
            raise ValueError("成交日期早于账户建档，请核对起点")
        book = self.accounts[account_id]
        k = key(data)
        if any(p["code"] == data["code"] and p["currency"] == data["currency"] and p["unit"] != data["unit"] for p in book["positions"].values()):
            raise ValueError("同一标的数量单位与期初/已有账目不一致，请核对股、份或克")
        p = book["positions"].get(k)
        if p is None:
            p = {**deepcopy(data), "quantity": ZERO, "realized": ZERO, "realized_cny": ZERO,
                 "cycle": 0, "closed_cycles": []}
            self.phase(p, at)
            book["positions"][k] = p
        q, price, fee = (number(data[n]) for n in ("quantity", "price", "fees"))
        before = deepcopy(p)
        amount = number(data["gross_amount"]) if data.get("gross_amount") is not None else q * price
        gain = None
        detail = {"record_id": data.get("record_id"), "at": at, "side": data["side"],
                  "quantity": q, "price": price, "fees": fee, "gross_amount": amount}
        if data["side"] == "BUY":
            if not p["quantity"]:
                p["cycle"] += 1
                self.phase(p, at)
            expense = amount + fee
            for field in ("cost", "cycle_buy_total"):
                p[field] = p[field] + expense if p[field] is not None else None
            for field in ("cost_cny", "cycle_buy_cny"):
                p[field] = p[field] + expense * fx if p[field] is not None and fx is not None else None
            pending_id = data.get("pending_id")
            if pending_id:
                reserved = book["pending"].pop(str(pending_id), None)
                if not reserved or reserved["currency"] != data["currency"] or reserved["kind"] != "subscription":
                    raise ValueError("申购确认需关联有效的同币种待确认款项")
                self.cash(account_id, data["currency"], reserved["amount"] - expense)
            else:
                self.cash(account_id, data["currency"], -expense)
            p["quantity"] += q
            detail["cash_amount"] = -expense
        else:
            if q > p["quantity"] or not p["quantity"]:
                raise ValueError(f"{data['code']} 卖出数量超过此时点可用持仓")
            income = amount - fee
            p["cost"] = p["cost"] - income if p["cost"] is not None else None
            p["cost_cny"] = p["cost_cny"] - income * fx if p["cost_cny"] is not None and fx is not None else None
            p["cycle_sell_total"] += income
            p["cycle_sell_cny"] = p["cycle_sell_cny"] + income * fx if p["cycle_sell_cny"] is not None and fx is not None else None
            p["quantity"] -= q
            detail["cash_amount"] = income
            if data.get("settlement") == "pending":
                if income < ZERO:
                    raise ValueError("待到账赎回款不能为负，请核对费用")
                book["pending"][str(data["record_id"])] = {"amount": income, "currency": data["currency"], "kind": "redemption", "code": data["code"]}
            else:
                self.cash(account_id, data["currency"], income)
        p["cycle_trades"].append(detail)
        if data["side"] == "SELL" and not p["quantity"]:
            trading = -p["cost"] if p["cost"] is not None else None
            gain = trading + p["cycle_dividends"] if trading is not None else None
            gain_cny = -p["cost_cny"] + p["cycle_dividends_cny"] if p["cost_cny"] is not None and p["cycle_dividends_cny"] is not None else None
            basis = p["cycle_buy_total"]
            p["closed_cycles"].append({"cycle": p["cycle"], "opened_at": p["first_at"], "closed_at": at,
                "realized": gain, "realized_cny": gain_cny, "disposed_cost": basis, "buy_total": basis,
                "sell_total": p["cycle_sell_total"], "trading_profit": trading,
                "dividends": p["cycle_dividends"], "dividends_cny": p["cycle_dividends_cny"],
                "dividend_records": deepcopy(p["cycle_dividend_records"]),
                "opening_kind": p["opening_kind"], "trades": deepcopy(p["cycle_trades"]),
                "return": gain / basis if gain is not None and basis is not None and basis > ZERO else None})
            self.closed_totals(p)
            p["cost"], p["cost_cny"] = ZERO, ZERO
        p["last_at"] = at
        return {"before_quantity": before["quantity"], "after_quantity": p["quantity"],
                "before_cost": before["cost"], "after_cost": p["cost"], "realized": gain}

    def dividend(self, book, data, record_id, at, net, fx):
        matches = [p for p in book["positions"].values() if p["code"] == data.get("code") and p["currency"] == data.get("currency", "CNY")
                   and (not data.get("unit") or p["unit"] == data["unit"])]
        p = matches[0] if len(matches) == 1 else None
        cycle = int(data["cycle"]) if data.get("cycle") not in (None, "") else None
        if p and cycle is None:
            candidates = [c["cycle"] for c in p["closed_cycles"]] + ([p["cycle"]] if p["quantity"] else [])
            cycle = candidates[0] if len(candidates) == 1 else None
        record = {"record_id": record_id, "at": at, "amount": net, "currency": data.get("currency", "CNY"), "cycle": cycle}
        closed = next((c for c in p["closed_cycles"] if c["cycle"] == cycle), None) if p else None
        target = closed if closed is not None else p if p and p["quantity"] and p["cycle"] == cycle else None
        if target is None:
            if data.get("require_attribution"):
                raise ValueError("现金分红需选择明确标的和持有阶段；清仓再买入不能猜测归属")
            book["unallocated_dividends"].append(record)
            return
        converted = net if record["currency"] == "CNY" else net * fx if fx is not None else None
        if closed is not None:
            closed["dividends"] += net
            closed["dividends_cny"] = closed["dividends_cny"] + converted if closed["dividends_cny"] is not None and converted is not None else None
            closed["dividend_records"].append(record)
            closed["realized"] = closed["realized"] + net if closed["realized"] is not None else None
            closed["realized_cny"] = closed["realized_cny"] + converted if closed["realized_cny"] is not None and converted is not None else None
            basis = closed["buy_total"]
            closed["return"] = closed["realized"] / basis if closed["realized"] is not None and basis is not None and basis > ZERO else None
            self.closed_totals(p)
        else:
            p["cycle_dividends"] += net
            p["cycle_dividends_cny"] = p["cycle_dividends_cny"] + converted if p["cycle_dividends_cny"] is not None and converted is not None else None
            p["cycle_dividend_records"].append(record)

    def event(self, account_id, kind, data, record_id, at, fx=None):
        if account_id not in self.accounts:
            raise ValueError("记录日期早于账户建档")
        book = self.accounts[account_id]
        curr = data.get("currency", "CNY")
        amount = number(data.get("amount", 0))
        fee = number(data.get("fees", 0))
        if kind in {"deposit", "dividend", "interest"}:
            self.cash(account_id, curr, amount - fee)
            if kind == "dividend":
                self.dividend(book, data, record_id, at, amount - fee, fx)
        elif kind in {"withdrawal", "fee"}:
            self.cash(account_id, curr, -amount - fee)
        elif kind == "transfer":
            self.cash(account_id, curr, -amount - fee)
            self.cash(data["to_account_id"], curr, amount)
        elif kind == "fx":
            self.cash(account_id, curr, -amount - fee)
            self.cash(account_id, data["to_currency"], number(data["to_amount"]))
        elif kind == "subscription":
            self.cash(account_id, curr, -amount)
            book["pending"][str(record_id)] = {"amount": amount, "currency": curr, "kind": kind, "code": data.get("code", "")}
        elif kind in {"settle", "cancel_subscription"}:
            pending = book["pending"].pop(str(data["pending_id"]), None)
            expected = "redemption" if kind == "settle" else "subscription"
            if not pending or pending["kind"] != expected:
                raise ValueError("需关联有效待到账赎回或待确认申购记录")
            self.cash(account_id, pending["currency"], pending["amount"])
        elif kind in {"split", "share_credit", "position_transfer"}:
            p = book["positions"].get(key(data))
            if not p or not p["quantity"]:
                raise ValueError("调整标的在此时点没有持仓")
            if kind == "share_credit":
                # Broker credit belongs to this account only; total cost is unchanged.
                p["quantity"] += number(data["quantity"])
                p["last_at"] = at
            elif kind == "split":
                # A corporate split changes the asset unit in every enrolled account.
                for other in self.accounts.values():
                    related = other["positions"].get(key(data))
                    if related and related["quantity"]:
                        related["quantity"] *= number(data["factor"])
                        related["last_at"] = at
            else:
                q = number(data["quantity"])
                if q > p["quantity"]:
                    raise ValueError("转托管数量超过持仓")
                target = self.accounts.get(data["to_account_id"])
                if target is None:
                    raise ValueError("转入账户尚未建档")
                moved = deepcopy(p)
                f = q / p["quantity"]
                moved.update(quantity=q, realized=ZERO, realized_cny=ZERO, cycle=1, closed_cycles=[])
                moved_cost = p["cost"] * f if p["cost"] is not None else None
                moved_cny = p["cost_cny"] * f if p["cost_cny"] is not None else None
                self.phase(moved, at, moved_cost, moved_cny, "transfer")
                for field, basis, value in (("cost", "cycle_buy_total", moved_cost), ("cost_cny", "cycle_buy_cny", moved_cny)):
                    p[field] = p[field] - value if p[field] is not None and value is not None else None
                    p[basis] = p[basis] - value if p[basis] is not None and value is not None else None
                other = target["positions"].get(key(data))
                if other:
                    if not other["quantity"]:
                        other["cycle"] += 1
                        self.phase(other, at, ZERO, ZERO, "transfer")
                    other["quantity"] += q
                    for field, basis, value in (("cost", "cycle_buy_total", moved_cost), ("cost_cny", "cycle_buy_cny", moved_cny)):
                        other[field] = other[field] + value if other[field] is not None and value is not None else None
                        other[basis] = other[basis] + value if other[basis] is not None and value is not None else None
                else:
                    target["positions"][key(data)] = moved
                p["quantity"] -= q
            p["last_at"] = at
        else:
            raise ValueError("不支持的账目类型")
