"""Reconcile GF settlement and cash exports before a scoped ledger replacement.

This importer never fetches prices. Workbook rows and account identifiers stay local.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json

from sqlalchemy import select

from app.models import Account, Deal, PortfolioEvent, PortfolioOpening
from . import service
from .ledger import Ledger, ZERO, number
from .performance import instant, iso, public

TZ = timezone(timedelta(hours=8))
IGNORED = {"申购配号", "转存管转入", "转存管转出"}
EVENTS = {"银行转存": "deposit", "银行转取": "withdrawal", "利息归本": "interest", "股息入账": "dividend", "红股入账": "share_credit"}


def stamp(day, clock="00:00:00"):
    return datetime.strptime(str(day).replace("/", "-") + " " + str(clock), "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ).astimezone(timezone.utc).replace(tzinfo=None)


def prepare(flows, statements):
    if not flows or not statements:
        raise ValueError("两份来源均不能为空")
    account_ids = {str(r["资产账户"]) for r in flows} | {str(r["资金账号"]) for r in statements}
    if len(account_ids) != 1 or "None" in account_ids:
        raise ValueError("两份文件必须属于同一资金账户")
    source_account = next(iter(account_ids))
    digest = sha256(json.dumps([flows, statements], sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    lookup, statement_lookup = {}, {}
    for r in statements:
        k = (str(r["业务日期"]).replace("/", "-"), str(r["流水序号"]))
        if k in statement_lookup:
            raise ValueError("对账单存在重复流水标识")
        statement_lookup[k] = r
    records, ignored, checkpoints = [], [], []
    cash, book = ZERO, Ledger()
    book.open("source", {"positions": [], "cash": {"CNY": "0"}})
    counts, totals = Counter(), Counter()
    previous_day = None
    for index, r in enumerate(flows, 2):
        day, clock, business = str(r["发生日期"]).replace("/", "-"), r["发生时间"], r["业务名称"]
        at = stamp(day, clock)
        if previous_day and day < previous_day:
            raise ValueError("资金流水业务日期不是递增顺序")
        previous_day = day
        k = (day, str(r["流水序号"]))
        if k in lookup:
            raise ValueError("资金流水存在重复流水标识")
        lookup[k] = r
        if r["币种"] != "人民币":
            raise ValueError("本次适配仅支持人民币普通账户")
        amount, balance, qty = (number(r[n]) for n in ("发生金额", "剩余金额", "发生数量"))
        cash += amount
        if cash != balance or cash < ZERO:
            raise ValueError(f"资金流水第 {index} 行现金余额不连续，不能推定缺失资金")
        s = statement_lookup.get(k)
        if s:
            for a, b in (("清算金额", "发生金额"), ("后资金额", "剩余金额"), ("成交数量", "发生数量"), ("成交价格", "成交价格")):
                if number(s[a]) != number(r[b]):
                    raise ValueError(f"第 {index} 行两份来源的 {a} 不一致")
            if s["发生时间"] != clock or str(s["证券代码"] or "") != str(r["证券代码"] or "") or s["业务标志名称"] != business:
                raise ValueError(f"第 {index} 行两份来源的业务不一致")
        ref = {"source": "gf_statement", "batch": digest, "source_account": source_account,
               "source_key": ":".join(k), "flow_row": index, "source_order": index, "original_at": iso(at)}
        counts[business] += 1
        totals[business] += amount
        if business in IGNORED:
            if amount != ZERO or business != "申购配号" and qty != ZERO:
                raise ValueError("被忽略业务包含非零资产变化")
            ignored.append({**ref, "business": business})
            continue
        data = {"currency": "CNY", "amount": str(abs(amount)), "fees": "0", "source": "广发对账单", "import_ref": ref}
        if business in {"证券买入", "证券卖出", "红股入账"}:
            if not s:
                raise ValueError("证券业务缺少对应对账单")
            code = str(r["证券代码"]).strip()
            if len(code) != 6 or not code.isdigit():
                raise ValueError("证券代码无效")
            name = str(r["证券名称"])
            data.update(code="CN." + code, name=name, market="CN", asset_type="etf" if "ETF" in name.upper() or "基金" in name else "stock", unit="share", quantity=str(abs(qty)))
        if business in {"证券买入", "证券卖出"}:
            buy = business == "证券买入"
            fee, gross = number(s["证券交易费用"], minimum=ZERO), number(s["成交金额"], minimum=ZERO)
            components = sum((number(s[n], minimum=ZERO) for n in ("净佣金", "印花税", "过户费", "证管费", "经手费", "其他费")), ZERO)
            if fee != components or amount != (-gross if buy else gross) - fee or (qty <= 0 if buy else qty >= 0):
                raise ValueError("成交方向、费用或清算金额不一致")
            data.update(side="BUY" if buy else "SELL", price=str(number(s["成交价格"], minimum=ZERO)), fees=str(fee), gross_amount=str(gross), settlement="cash")
            kind = "trade"
            book.trade("source", data, iso(at), Decimal(1))
        elif business in EVENTS:
            kind = EVENTS[business]
            if business == "红股入账":
                if amount != ZERO or qty <= ZERO:
                    raise ValueError("红股入账数量或金额无效")
            elif (amount >= ZERO if kind == "withdrawal" else amount <= ZERO) or qty != ZERO:
                raise ValueError("资金业务方向或数量无效")
            book.event("source", kind, data, str(index), iso(at))
        else:
            raise ValueError(f"存在未适配业务：{business}")
        if book.accounts["source"]["cash"]["CNY"] != balance:
            raise ValueError("业务映射后现金与来源不一致")
        if s and business in {"证券买入", "证券卖出", "红股入账"}:
            p = book.accounts["source"]["positions"][(data["code"], "CNY", "share")]
            if p["quantity"] != number(s["后证券额"]):
                raise ValueError("业务映射后证券余额与来源不一致")
        records.append({"kind": kind, "at": iso(at), "data": data})
        checkpoints.append({"at": iso(at), "date": day, "cash": str(balance)})
    if set(statement_lookup) - set(lookup):
        raise ValueError("存在资金流水未覆盖的对账单记录")
    positions = {p["code"]: str(p["quantity"]) for p in book.accounts["source"]["positions"].values() if p["quantity"]}
    costs = sum((p["cost"] for p in book.accounts["source"]["positions"].values()), ZERO)
    # Only the last source balance of each day is comparable to a chronological replay.
    daily = {p["date"]: p["cash"] for p in checkpoints}
    return {"source_account": source_account, "digest": digest, "records": records, "ignored": ignored,
            "start": iso(stamp(flows[0]["发生日期"])), "daily_cash": daily,
            "expected": {"cash": str(cash), "positions": positions, "cost": str(costs)},
            "counts": dict(counts), "totals": {k: str(v) for k, v in totals.items()}}


def replace_ledger(db, account_id, batch, *, commit=False):
    account = db.get(Account, account_id)
    if not account or "广发" not in ((account.display_name or "") + (account.institution or "")):
        raise ValueError("目标必须是已存在的广发账户")
    opening = db.get(PortfolioOpening, account_id)
    old_ref = opening.data.get("gf_import", {}) if opening else {}
    if old_ref.get("source_account") not in (None, batch["source_account"]):
        raise ValueError("目标账户已绑定其他资金账户")
    if old_ref.get("digest") == batch["digest"]:
        actual = [{"kind": "trade", "at": iso(d.deal_time), "data": d.ledger_data}
                  for d in db.scalars(select(Deal).where(Deal.account_id == account_id, Deal.is_void.is_(False)))]
        actual += [{"kind": e.kind, "at": iso(e.effective_at), "data": e.data}
                   for e in db.scalars(select(PortfolioEvent).where(PortfolioEvent.account_id == account_id,
                       PortfolioEvent.is_void.is_(False), PortfolioEvent.kind != "valuation"))]
        canonical = lambda rs: sorted(json.dumps(r, sort_keys=True, ensure_ascii=False) for r in rs)
        if canonical(actual) != canonical(batch["records"]):
            raise ValueError("来源批次相同但现有账目已更改，不能静默跳过或覆盖")
        return {"status": "already_imported", "expected": batch["expected"]}
    # Transfers affect both endpoints; a single-account replacement must not silently
    # remove the other side or leave an inbound transfer attached to this new book.
    for e in db.scalars(select(PortfolioEvent).where(PortfolioEvent.is_void.is_(False))):
        if e.kind in {"transfer", "position_transfer"} and account_id in {e.account_id, e.data.get("to_account_id")}:
            raise ValueError("目标存在跨账户转移，请先核对两端，不能单账户覆盖")
    try:
        for d in db.scalars(select(Deal).where(Deal.account_id == account_id)):
            d.is_void = True
        for e in db.scalars(select(PortfolioEvent).where(PortfolioEvent.account_id == account_id)):
            if e.kind != "valuation":
                e.is_void = True
        opening = opening or PortfolioOpening(account_id=account_id)
        opening.effective_at = instant(batch["start"])
        opening.included_at, opening.excluded_at = opening.effective_at, None
        opening.data = {"positions": [], "cash": {"CNY": "0"}, "liabilities": {}, "prices": [], "fx": {},
                        "source": "广发完整明细重建", "valuation_policy": "explicit_only",
                        "gf_import": {"digest": batch["digest"], "source_account": batch["source_account"], "ignored": batch["ignored"]}}
        db.add(opening)
        for r in batch["records"]:
            data, at = r["data"], instant(r["at"])
            if r["kind"] == "trade":
                deal_id = "gf:" + data["import_ref"]["source_key"]
                row = db.scalar(select(Deal).where(Deal.account_id == account_id, Deal.deal_id == deal_id))
                row = row or Deal(account_id=account_id, deal_id=deal_id)
                row.code, row.market, row.side = data["code"], "CN", data["side"]
                row.price, row.quantity, row.deal_time = float(data["price"]), float(data["quantity"]), at
                row.ledger_data, row.raw_payload, row.is_void = data, {"import_ref": data["import_ref"]}, False
                db.add(row)
            else:
                db.add(PortfolioEvent(account_id=account_id, kind=r["kind"], effective_at=at, data=data,
                                      is_void=False, created_at=datetime.now(timezone.utc).replace(tzinfo=None)))
        db.flush()
        service.validate(db)
        for day, expected in batch["daily_cash"].items():
            end = stamp(day, "23:59:59")
            ledger = service.calculate(db, account_id, end)["ledger"]
            if ledger.accounts[account_id]["cash"]["CNY"] != number(expected):
                raise ValueError("日终现金回放与券商余额不一致")
        result = service.calculate(db, account_id)
        book = result["ledger"].accounts[account_id]
        actual = {p["code"]: str(p["quantity"]) for p in book["positions"].values() if p["quantity"]}
        if actual.keys() != batch["expected"]["positions"].keys() or any(number(v) != number(batch["expected"]["positions"][k]) for k, v in actual.items()):
            raise ValueError("末端持仓核对失败")
        if book["cash"]["CNY"] != number(batch["expected"]["cash"]):
            raise ValueError("末端现金核对失败")
        cost = sum((p["cost"] for p in book["positions"].values()), ZERO)
        if abs(cost - number(batch["expected"]["cost"])) > Decimal("0.00000001"):
            raise ValueError("末端成本核对失败")
        report = public({"status": "imported" if commit else "preview", "records": len(batch["records"]),
                         "cash": book["cash"], "positions": actual, "cost": cost,
                         "realized_sales": sum((p["realized"] for p in book["positions"].values()), ZERO),
                         "daily_checks": len(batch["daily_cash"]), "ignored": len(batch["ignored"])})
        if commit:
            db.commit()
        else:
            db.rollback()
        return report
    except Exception:
        db.rollback()
        raise
