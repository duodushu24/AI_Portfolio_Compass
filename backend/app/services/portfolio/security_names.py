"""Edit existing security names without changing an accounting fact or adding aliases."""
from copy import deepcopy

from sqlalchemy import select

from app.models import Deal, PortfolioEvent, PortfolioOpening, PositionSnapshot


def security_code(code, market=""):
    code, market = str(code or "").strip().upper(), str(market or "").strip().upper()
    aliases = {"SH": "CN", "SZ": "CN", "BJ": "CN", "FUND": "CN"}
    market = aliases.get(market, market)
    if "." in code:
        prefix, symbol = code.split(".", 1)
        prefix = aliases.get(prefix, prefix)
        return f"{prefix}.{symbol}" if prefix in {"CN", "US", "HK"} and symbol else None
    return f"{market}.{code}" if code and market in {"CN", "US", "HK"} else None


def _assets(value):
    if isinstance(value, dict):
        if value.get("code") and "name" in value:
            yield value
        for k, child in value.items():
            if k not in {"raw_payload", "import_ref"}:
                yield from _assets(child)
    elif isinstance(value, list):
        for child in value:
            yield from _assets(child)


def existing_names(db):
    """Use enrolled names first; source observations are a fallback for new books."""
    result = {}
    for model, field in ((PortfolioOpening, "data"), (Deal, "ledger_data"), (PortfolioEvent, "data")):
        for row in db.scalars(select(model)):
            for item in _assets(getattr(row, field)):
                code = security_code(item["code"], item.get("market"))
                name = str(item.get("name") or "").strip()
                if code and name and name.upper() not in {code, code.split(".", 1)[1]}:
                    result.setdefault(code, name)
    for row in db.scalars(select(PositionSnapshot).order_by(PositionSnapshot.snapshot_time.desc(), PositionSnapshot.id.desc())):
        code = security_code(row.code, row.market)
        if code and row.name and row.name.upper() not in {code, code.split(".", 1)[1]}:
            result.setdefault(code, row.name)
    return result


def reuse_names(value, names):
    """Import boundaries reuse names already recorded for the same security."""
    value = deepcopy(value)
    for item in _assets(value):
        code = security_code(item["code"], item.get("market"))
        name = str(item.get("name") or "").strip()
        if code in names:
            item["name"] = names[code]
        else:
            # Only the known mainland ex-dividend marker, never arbitrary prefixes.
            if code and code.startswith("CN.") and name.startswith("XD") and len(name) > 2:
                name = name[2:].strip()
            item["name"] = name
            if code and name:
                names[code] = name
    return value


def rename(db, code, name, market=""):
    code = security_code(code, market)
    name = str(name or "").strip()
    if not code or not name or len(name) > 120 or any(c in name for c in "\r\n\t"):
        raise ValueError("请填写有效标的代码及 1—120 字的名称")
    count = 0
    try:
        for model, field in ((PortfolioOpening, "data"), (Deal, "ledger_data"), (PortfolioEvent, "data")):
            for row in db.scalars(select(model)):
                data = deepcopy(getattr(row, field))
                changed = False
                for item in _assets(data):
                    if security_code(item["code"], item.get("market")) == code:
                        count += 1
                        item["name"], changed = name, True
                if changed:
                    if model is PortfolioOpening and data.get("opening_import"):
                        from types import SimpleNamespace
                        from .opening_import import signature
                        data["opening_import"] = {**data["opening_import"], "signature": signature(SimpleNamespace(
                            data=data, effective_at=row.effective_at, included_at=row.included_at, excluded_at=row.excluded_at))}
                    setattr(row, field, data)
        for row in db.scalars(select(PositionSnapshot)):
            if security_code(row.code, row.market) == code:
                row.name = name
                count += 1
        # Unenrolled trades can carry their editable name only in raw_payload.
        for row in db.scalars(select(Deal)):
            if security_code(row.code, row.market) == code and "name" in (row.raw_payload or {}):
                row.raw_payload = {**row.raw_payload, "name": name}
                count += 1
        if not count:
            raise ValueError("标的不存在，请刷新持仓后重试")
        # No ledger validation/rebasing: only names changed, including in incomplete books.
        db.commit()
        return {"code": code, "name": name, "updated_count": count}
    except Exception:
        db.rollback()
        raise
