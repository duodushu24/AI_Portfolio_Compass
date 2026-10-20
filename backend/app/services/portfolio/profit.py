"""Account profit carry, independent of cash, cost and performance baselines."""
from .ledger import ZERO, number


class ProfitCarry:
    def __init__(self):
        self.accounts = {}

    def open(self, account_id, data, value, at):
        gains = [p["floating_cny"] for p in value["positions"] if p["quantity"]]
        gain = sum(gains, ZERO) if all(v is not None for v in gains) else None
        carry = data.get("historical_profit_cny")
        needs = [{**n, "at": at, "action": "opening", "context": "opening"} for n in value["data_needs"]]
        for p in value["positions"]:
            if p["quantity"] and (p["cost"] is None or p["cost_cny"] is None):
                needs.append({"kind": "cost" if p["cost"] is None else "cost_cny", "account_id": account_id,
                              "code": p["code"], "name": p["name"], "currency": p["currency"], "unit": p["unit"],
                              "at": at, "action": "opening", "context": "opening"})
        self.accounts[account_id] = {
            "assets": value["total_assets"], "gain": gain,
            "carry": number(carry) if carry not in (None, "") else ZERO, "flows": ZERO,
            "needs": needs,
        }

    def flow(self, account_id, amount, needs=()):
        row = self.accounts[account_id]
        row["flows"] = row["flows"] + amount if row["flows"] is not None and amount is not None else None
        if amount is None:
            row["needs"].extend(n for n in needs if n not in row["needs"])

    def summary(self, value, selected):
        amounts = {aid: ZERO for aid in selected}
        for field, sign, name in (("positions", 1, "market_value_cny"), ("cash", 1, "value_cny"),
                                  ("pending", 1, "value_cny"), ("liabilities", -1, "value_cny")):
            for item in value[field]:
                aid, amount = item["account_id"], item[name]
                amounts[aid] = amounts[aid] + sign * amount if amounts[aid] is not None and amount is not None else None
        rows = []
        for aid in sorted(selected):
            row, assets = self.accounts[aid], amounts[aid]
            period = assets - row["assets"] - row["flows"] if all(v is not None for v in (assets, row["assets"], row["flows"])) else None
            initial = row["carry"] + row["gain"] if row["carry"] is not None and row["gain"] is not None else None
            rows.append({"account_id": aid, "historical_profit_cny": row["carry"], "opening_holding_profit": row["gain"],
                         "opening_profit": initial, "profit_since_opening": period,
                         "cumulative_profit": initial + period if initial is not None and period is not None else None})
        missing = [r["account_id"] for r in rows if r["cumulative_profit"] is None]
        needs = [n for aid in missing for n in self.accounts[aid]["needs"]]
        needs += [n for n in value["data_needs"] if n["account_id"] in missing]
        known = sum((r["cumulative_profit"] for r in rows if r["cumulative_profit"] is not None), ZERO)
        profit = known if not missing else None
        assets = sum(amounts.values(), ZERO) if all(v is not None for v in amounts.values()) else None
        investment = assets - profit if assets is not None and profit is not None else None
        rate = profit / investment if investment is not None and investment > ZERO else None
        return {"cumulative_profit": profit, "cumulative_net_investment": investment, "cumulative_profit_rate": rate,
                "known_cumulative_profit": known,
                "missing_cumulative_accounts": missing, "account_profits": rows, "cumulative_needs": needs}
