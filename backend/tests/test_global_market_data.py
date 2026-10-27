"""P-011: synthetic in-memory ledger; no network and no real account data."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from sqlalchemy import select, func

from test_data_sources import db, asset, patch_adapter
from app.adapters.akshare_adapter import AKShareAdapter
from app.adapters.akshare_global import TROY_OUNCE_GRAMS
from app.models import Account, ExchangeRate, PortfolioEvent, QuoteSummary
from app.services import data_sources as ds, fx_rates, market_fx
from app.services.portfolio import service as ledger
from app.services.portfolio.performance import instant, iso
from app.services.sync import pull_account_market_data

NOW = datetime(2026, 10, 27, 2, tzinfo=timezone.utc)
GOLD = "CN.GOLD.SYNTHETIC"


def seed(db, *, fx=True, gold=True, stocks=True, cash_only=False):
    positions = []
    if stocks and not cash_only:
        positions.append(asset(code="US.AAPL", market="US", currency="USD", quantity="10", average_cost="1", cost_cny_amount="70", price="2"))
    if gold and not cash_only:
        positions.append(asset(code=GOLD, asset_type="precious_metal", unit="gram", quantity="10.5", average_cost="500", price="600"))
    ledger.save_opening(db, "a", {"effective_at":iso(NOW-timedelta(days=60)), "cash":{"CNY":"1000","USD":"1000"}, "positions":positions,
        "fx":{"USD":{"rate":"7", "at":iso(NOW-timedelta(days=60))}} if fx else {}})


def fx_result(rate="8", at=None):
    return {"status":"available","message":"已取日度汇率","fx":[{"currency":"USD","rate":rate,"at":iso(at or NOW),"source":"akshare · SAFE中间价","rate_date":"2026-10-27","time_precision":"day","fetched_at":iso(NOW)}]}


def adapter(monkeypatch):
    sdk = AKShareAdapter()
    calls = []
    def call(action, **kw):
        calls.append(action)
        if action == "fx": return [{"日期":"2026-10-27","美元":800,"港元":100}]
        if action == "us": return [{"date":"2026-10-26","open":2,"close":3,"high":4,"low":1,"volume":100}]
        if action == "gold": return [{"date":"2026-10-26","close":3100}]
        raise AssertionError(action)
    monkeypatch.setattr(sdk,"_call",call)
    patch_adapter(monkeypatch,lambda a,k:sdk.fetch(a,k,NOW))
    return sdk,calls


def test_fx_units_date_publication_and_one_sdk_fetch(monkeypatch):
    sdk = AKShareAdapter(); calls=[]
    monkeypatch.setattr(sdk,"_call",lambda *a,**k:calls.append(a) or [{"日期":"2026-10-26","美元":700,"港元":90},{"日期":"2026-10-27","美元":800,"港元":100}])
    usd=sdk.fetch({"currency":"USD"},"fx",NOW)
    hkd=sdk.fetch({"currency":"HKD"},"fx",NOW)
    early=sdk.fetch({"currency":"USD"},"fx",NOW-timedelta(hours=1))
    assert usd["fx"][0]["rate"]=="8.0" and hkd["fx"][0]["rate"]=="1.0"
    assert early["fx"][0]["rate"]=="7.0" and len(calls)==1
    assert usd["fx"][0]["rate_date"]=="2026-10-27"


@pytest.mark.parametrize("day,hour",[("2026-01-02",21),("2026-07-02",20)])
def test_us_close_uses_dst_and_rejects_unfinished_bar(monkeypatch,day,hour):
    sdk=AKShareAdapter()
    monkeypatch.setattr(sdk,"_call",lambda *a,**k:[{"date":day,"close":3}])
    a=asset(code="US.VOO",market="US",currency="USD",asset_type="etf")
    before=datetime.fromisoformat(day).replace(hour=hour,tzinfo=timezone.utc)
    assert sdk.fetch(a,"quote",before)["status"]=="empty"
    r=sdk.fetch(a,"quote",before+timedelta(minutes=20))
    assert r["quotes"][0]["quote_time"].hour==hour and r["quotes"][0]["price_date"]==day


def test_gold_converts_once_and_filters_current_day(monkeypatch):
    sdk,_=adapter(monkeypatch)
    monkeypatch.setattr(sdk,"_call",lambda *a,**k:[{"date":"2026-10-26","close":3100},{"date":"2026-10-27","close":9999}])
    a=asset(code=GOLD,asset_type="precious_metal",unit="gram",conversion_fx=fx_result()["fx"][0])
    r=sdk.fetch(a,"quote",NOW)["quotes"][0]
    assert r["current_price"]==pytest.approx(float(Decimal(3100)*8/TROY_OUNCE_GRAMS))
    assert r["price_kind"]=="reference" and r["reference"]["price_date"]=="2026-10-26"
    assert r["reference"]["fx_date"]=="2026-10-27" and r["currency"]=="CNY"


def test_fx_is_persisted_before_stock_and_gold_requests(db,monkeypatch):
    seed(db); sdk,calls=adapter(monkeypatch)
    r=pull_account_market_data(db,db.get(Account,"a"),"quote")
    assert calls==["fx","us","gold"] and r["status"]=="success"
    assert r["fx_updates"][0]["status"]=="updated"
    current=ledger.calculate(db)["current"]
    us=next(p for p in current["positions"] if p["code"]=="US.AAPL")
    gold=next(p for p in current["positions"] if p["code"]==GOLD)
    assert us["market_value_cny"]==240 and us["cost_cny"]==70 and us["quantity"]==10
    assert float(gold["market_value_cny"])==pytest.approx(float(Decimal(3100)*8/TROY_OUNCE_GRAMS)*10.5)
    assert ledger.calculate(db)["ledger"].accounts["a"]["cash"]=={"CNY":Decimal(1000),"USD":Decimal(1000)}
    assert gold["quote"]["price_kind"]=="reference" and not any("估算" in i for i in current["issues"])


def test_failed_fx_keeps_old_rate_and_date_while_prices_update(db,monkeypatch):
    seed(db); sdk,calls=adapter(monkeypatch)
    base=sdk._call
    monkeypatch.setattr(sdk,"_call",lambda action,**kw: (_ for _ in ()).throw(RuntimeError("ProxyError")) if action=="fx" else base(action,**kw))
    r=pull_account_market_data(db,db.get(Account,"a"),"quote")
    assert r["fx_updates"][0]["status"]=="carried" and r["fx_updates"][0]["rate"]=="7"
    assert instant(r["fx_updates"][0]["at"])==instant(NOW-timedelta(days=60))
    current=ledger.calculate(db)["current"]
    assert next(p for p in current["positions"] if p["code"]=="US.AAPL")["market_value_cny"]==210
    assert "沿用" in r["message"] and len(list(db.scalars(select(QuoteSummary))))==2


def test_no_saved_fx_never_uses_fixed_rate(db,monkeypatch):
    seed(db,fx=False); sdk,_=adapter(monkeypatch)
    base=sdk._call
    monkeypatch.setattr(sdk,"_call",lambda action,**kw: (_ for _ in ()).throw(RuntimeError("ProxyError")) if action=="fx" else base(action,**kw))
    r=pull_account_market_data(db,db.get(Account,"a"),"quote")
    assert r["status"]=="partial" and r["fx_updates"][0]["status"]=="missing"
    assert ledger.calculate(db)["current"]["total_assets"] is None
    assert db.scalar(select(QuoteSummary).where(QuoteSummary.code==GOLD)) is None
    assert ledger.calculate(db)["prices"].fx.keys()=={"CNY"}


def test_cash_only_account_updates_fx(db,monkeypatch):
    seed(db,cash_only=True); _,calls=adapter(monkeypatch)
    r=pull_account_market_data(db,db.get(Account,"a"),"quote")
    assert calls==["fx"] and r["status"]=="success"
    assert ledger.calculate(db)["current"]["cash_value"]==9000


def test_display_cache_fallback_is_imported_without_expiry_cutoff(db,monkeypatch):
    seed(db,fx=False,gold=False)
    db.add(ExchangeRate(base_currency="CNY",quote_currency="USD",source="frankfurter",rate=0.125,rate_time=NOW-timedelta(days=30),fetched_at=NOW-timedelta(days=29),expires_at=NOW-timedelta(days=28),is_stale=True,raw_payload={"rate":0.125}));db.commit()
    patch_adapter(monkeypatch,lambda *_:{"status":"timeout","message":"超时"})
    r=pull_account_market_data(db,db.get(Account,"a"),"quote")
    assert Decimal(r["fx_updates"][0]["rate"])==8 and r["fx_updates"][0]["status"]=="carried"
    assert ledger.calculate(db)["prices"].fx["USD"]["source"]=="frankfurter"


def test_latest_fx_does_not_rewrite_earlier_trade_cost_or_history(db,monkeypatch):
    seed(db,gold=False)
    at=datetime.now(timezone.utc)-timedelta(minutes=5)
    ledger.save_trade(db,{"account_id":"a",**asset(code="US.AAPL",market="US",currency="USD"),"effective_at":iso(at),"side":"BUY","quantity":"1","price":"2","fees":"1"})
    before=ledger.calculate(db)["current"]["positions"][0]["cost_cny"]
    historical=ledger.calculate(db,until=at)["current"]["total_assets"]
    patch_adapter(monkeypatch,lambda a,k:fx_result(at=at-timedelta(minutes=10)) if k=="fx" else {"status":"empty","message":"无新日线"})
    pull_account_market_data(db,db.get(Account,"a"),"quote")
    assert before==91 and ledger.calculate(db)["current"]["positions"][0]["cost_cny"]==before
    assert ledger.calculate(db,until=at)["current"]["total_assets"]==historical


def test_repeated_update_is_idempotent(db,monkeypatch):
    seed(db); adapter(monkeypatch)
    pull_account_market_data(db,db.get(Account,"a"),"quote")
    count=db.scalar(select(func.count()).select_from(PortfolioEvent))
    pull_account_market_data(db,db.get(Account,"a"),"quote")
    assert db.scalar(select(func.count()).select_from(PortfolioEvent))==count


@pytest.mark.parametrize("kind,sample",[("fx",None),("quote","us"),("quote","gold")])
def test_public_probes_do_not_write_prices_or_ledger(db,monkeypatch,kind,sample):
    adapter(monkeypatch)
    assert ds.probe(db,"akshare",kind,sample=sample)["status"]=="available"
    assert db.scalar(select(func.count()).select_from(PortfolioEvent))==0
    assert db.scalar(select(func.count()).select_from(QuoteSummary))==0


def test_display_prefers_shared_fx_without_frankfurter_request(db,monkeypatch):
    seed(db); adapter(monkeypatch)
    pull_account_market_data(db,db.get(Account,"a"),"quote")
    monkeypatch.setattr(fx_rates,"fetch_frankfurter_rate",lambda *_:pytest.fail("shared saved FX must be used"))
    r=fx_rates.get_rate(db,"CNY","USD")
    assert r.rate==0.125 and "SAFE" in r.source


def test_gold_actual_trade_fees_and_closed_profit_survive_reference_updates(db,monkeypatch):
    seed(db,stocks=False)
    g=asset(code=GOLD,asset_type="precious_metal",unit="gram")
    ledger.save_trade(db,{"account_id":"a",**g,"effective_at":iso(NOW-timedelta(days=20)),"side":"BUY","quantity":"1","price":"500","fees":"5"})
    adapter(monkeypatch)
    pull_account_market_data(db,db.get(Account,"a"),"quote")
    current=ledger.calculate(db)["current"]["positions"][0]
    assert current["quantity"]==Decimal("11.5") and current["cost"]==5755
    assert ledger.calculate(db)["ledger"].accounts["a"]["cash"]["CNY"]==495
    ledger.save_trade(db,{"account_id":"a",**g,"effective_at":iso(datetime.now(timezone.utc)),"side":"SELL","quantity":"11.5","price":"700","fees":"2"})
    p=ledger.calculate(db)["current"]["positions"][0]
    assert p["quantity"]==0 and p["realized"]==2293


def test_one_failed_fx_sdk_request_is_shared_by_currencies(db,monkeypatch):
    sdk=AKShareAdapter(); calls=[]
    def fail(*a,**k):
        calls.append(a)
        raise RuntimeError("ProxyError")
    monkeypatch.setattr(sdk,"_call",fail)
    patch_adapter(monkeypatch,lambda a,k:sdk.fetch(a,k,NOW))
    p=ds.choose(db,"fx","CN"); adapters={}
    assert ds.fetch(db,p,{"currency":"USD"},"fx",adapters)["status"]=="request_failed"
    assert ds.fetch(db,p,{"currency":"HKD"},"fx",adapters)["status"]=="request_failed"
    assert len(calls)==1


def test_older_upstream_rate_does_not_replace_recent_saved_rate(db,monkeypatch):
    seed(db,gold=False)
    ledger.save_event(db,{"account_id":"a","kind":"valuation","effective_at":iso(NOW-timedelta(hours=1)),
        "data":{"fx":{"USD":{"rate":"9","at":iso(NOW-timedelta(hours=1))}}}})
    patch_adapter(monkeypatch,lambda a,k:fx_result(rate="8",at=NOW-timedelta(days=1)) if k=="fx" else {"status":"empty","message":"无新价格"})
    r=pull_account_market_data(db,db.get(Account,"a"),"quote")
    assert r["fx_updates"][0]["status"]=="carried" and r["fx_updates"][0]["rate"]=="9"
    assert ledger.calculate(db)["prices"].fx["USD"]["rate"]=="9"


def test_receipt_time_prevents_inflight_trade_cost_rewrite(db,monkeypatch):
    seed(db,gold=False)
    before=datetime.now(timezone.utc)
    def fetch(a,k):
        if k=="fx":
            ledger.save_trade(db,{"account_id":"a",**asset(code="US.AAPL",market="US",currency="USD"),
                "effective_at":iso(datetime.now(timezone.utc)),"side":"BUY","quantity":"1","price":"2","fees":"1"})
            return fx_result(rate="8",at=before-timedelta(minutes=20))
        return {"status":"empty","message":"无新价格"}
    patch_adapter(monkeypatch,fetch)
    pull_account_market_data(db,db.get(Account,"a"),"quote")
    assert ledger.calculate(db)["current"]["positions"][0]["cost_cny"]==91
