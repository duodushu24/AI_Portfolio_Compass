"""Account profit carry, independent of cash, cost and performance baselines."""
from .ledger import ZERO, number


class ProfitCarry:
    def __init__(self):
        self.accounts = {}

    def open(self, account_id, data, value):
        gains = [p["floating_cny"] for p in value["positions"] if p["quantity"]]
        gain = sum(gains, ZERO) if all(v is not None for v in gains) else None
        carry = data.get("historical_profit_cny")
        self.accounts[account_id] = {
            "assets": value["total_assets"], "gain": gain,
            "carry": number(carry) if carry not in (None, "") else ZERO, "flows": ZERO,
        }

    def flow(self, account_id, amount):
        row = self.accounts[account_id]
        row["flows"] = row["flows"] + amount if row["flows"] is not None and amount is not None else None

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
        known = sum((r["cumulative_profit"] for r in rows if r["cumulative_profit"] is not None), ZERO)
        return {"cumulative_profit": known if not missing else None, "known_cumulative_profit": known,
                "missing_cumulative_accounts": missing, "account_profits": rows}
