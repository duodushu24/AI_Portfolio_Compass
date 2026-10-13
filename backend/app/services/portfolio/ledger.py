from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation

ZERO = Decimal(0)
CURRENCIES = {"CNY", "HKD", "USD"}
ASSETS = {"stock", "etf", "fund", "bond", "leveraged_etf"}


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

    def open(self, account_id, data):
        if account_id in self.accounts:
            raise ValueError("账户已建档")
        book = {"positions": {}, "cash": {c: number(v) for c, v in data["cash"].items()},
                "pending": {}, "liabilities": {c: number(v) for c, v in data.get("liabilities", {}).items()}}
        for item in data["positions"]:
            q = number(item["quantity"])
            cost = None if item.get("average_cost") is None else number(item["average_cost"]) * q
            book["positions"][key(item)] = {**deepcopy(item), "quantity": q, "cost": cost,
                "cost_cny": None if item.get("cost_cny_amount") is None else number(item["cost_cny_amount"]),
                "realized": ZERO, "realized_cny": ZERO, "cycle": 1, "first_at": data["effective_at"], "last_at": data["effective_at"]}
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
            raise ValueError("同一标的数量单位与期初/已有账目不一致，请核对股票数量或基金份额")
        p = book["positions"].get(k)
        if p is None:
            p = {**deepcopy(data), "quantity": ZERO, "cost": ZERO, "cost_cny": ZERO,
                 "realized": ZERO, "realized_cny": ZERO, "cycle": 0, "first_at": at, "last_at": at}
            book["positions"][k] = p
        q, price, fee = (number(data[n]) for n in ("quantity", "price", "fees"))
        before = deepcopy(p)
        amount = q * price
        gain = None
        if data["side"] == "BUY":
            if not p["quantity"]:
                p["cycle"] += 1
                p["first_at"] = at
                p["cost"], p["cost_cny"] = ZERO, ZERO
            if p["cost"] is not None:
                p["cost"] += amount + fee
            p["cost_cny"] = p["cost_cny"] + (amount + fee) * fx if p["cost_cny"] is not None and fx is not None else None
            pending_id = data.get("pending_id")
            if pending_id:
                reserved = book["pending"].pop(str(pending_id), None)
                if not reserved or reserved["currency"] != data["currency"] or reserved["kind"] != "subscription":
                    raise ValueError("申购确认需关联有效的同币种待确认款项")
                self.cash(account_id, data["currency"], reserved["amount"] - amount - fee)
            else:
                self.cash(account_id, data["currency"], -amount - fee)
            p["quantity"] += q
        else:
            if q > p["quantity"] or not p["quantity"]:
                raise ValueError(f"{data['code']} 卖出数量超过此时点可用持仓")
            disposed = p["cost"] * q / p["quantity"] if p["cost"] is not None else None
            disposed_cny = p["cost_cny"] * q / p["quantity"] if p["cost_cny"] is not None else None
            gain = amount - fee - disposed if disposed is not None else None
            p["realized"] = p["realized"] + gain if p["realized"] is not None and gain is not None else None
            gain_cny = (amount - fee) * fx - disposed_cny if disposed_cny is not None and fx is not None else None
            p["realized_cny"] = p["realized_cny"] + gain_cny if p["realized_cny"] is not None and gain_cny is not None else None
            p["quantity"] -= q
            p["cost"] = p["cost"] - disposed if disposed is not None else None
            p["cost_cny"] = p["cost_cny"] - disposed_cny if disposed_cny is not None else None
            if data.get("settlement") == "pending":
                if amount < fee:
                    raise ValueError("待到账赎回款不能为负，请核对费用")
                book["pending"][str(data["record_id"])] = {"amount": amount - fee, "currency": data["currency"], "kind": "redemption", "code": data["code"]}
            else:
                self.cash(account_id, data["currency"], amount - fee)
            if not p["quantity"]:
                p["cost"], p["cost_cny"] = ZERO, ZERO
        p["last_at"] = at
        return {"before_quantity": before["quantity"], "after_quantity": p["quantity"],
                "before_cost": before["cost"], "after_cost": p["cost"], "realized": gain}

    def event(self, account_id, kind, data, record_id, at):
        if account_id not in self.accounts:
            raise ValueError("记录日期早于账户建档")
        book = self.accounts[account_id]
        curr = data.get("currency", "CNY")
        amount = number(data.get("amount", 0))
        fee = number(data.get("fees", 0))
        if kind in {"deposit", "dividend", "interest"}:
            self.cash(account_id, curr, amount - fee)
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
        elif kind in {"split", "position_transfer"}:
            p = book["positions"].get(key(data))
            if not p or not p["quantity"]:
                raise ValueError("调整标的在此时点没有持仓")
            if kind == "split":
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
                moved.update(quantity=q, realized=ZERO, realized_cny=ZERO)
                for name in ("cost", "cost_cny"):
                    moved[name] = p[name] * f if p[name] is not None else None
                    p[name] = p[name] - moved[name] if moved[name] is not None else None
                other = target["positions"].get(key(data))
                if other:
                    other["quantity"] += q
                    for name in ("cost", "cost_cny"):
                        other[name] = other[name] + moved[name] if other[name] is not None and moved[name] is not None else None
                else:
                    target["positions"][key(data)] = moved
                p["quantity"] -= q
            p["last_at"] = at
        else:
            raise ValueError("不支持的账目类型")
