from app.services.providers import account_provider_statuses, normalize_symbol, provider_registry


def test_provider_registry_exposes_only_implemented_routes():
    registry = provider_registry()

    hk_quote = registry.choose(data_type="quote", market="HK", preferred=["futu"])
    us_news = registry.choose(data_type="news", market="US", broker_provider="", preferred=["alpha_vantage"])
    cn_announcement = registry.choose(data_type="announcement", market="CN", broker_provider="")

    assert hk_quote is not None
    assert hk_quote.name == "futu"
    assert us_news is None  # A registered placeholder cannot fetch data.
    assert cn_announcement is None
    assert registry.choose(data_type="quote", market="CN").name == "akshare"


def test_non_futu_cn_account_does_not_route_to_futu_opend():
    states = account_provider_statuses("alipay", ["CN"])
    quote = next(item for item in states if item["data_type"] == "quote")
    news = next(item for item in states if item["data_type"] == "news")

    assert quote["provider"] == "akshare"
    assert news["provider"] == "akshare"
    assert quote["status"] == "configured"
    assert all(item["provider"] != "futu" for item in states)


def test_provider_status_does_not_offer_unimplemented_us_source():
    states = account_provider_statuses("manual", ["US"])
    quote = next(item for item in states if item["data_type"] == "quote")

    assert quote["status"] == "configured"
    assert quote["provider"] == "akshare"
    news = next(item for item in states if item["data_type"] == "news")
    assert news["status"] == "unsupported"


def test_symbol_normalization_for_supported_markets():
    assert normalize_symbol("US.AAPL", "alpaca") == "AAPL"
    assert normalize_symbol("HK.00700", "futu") == "HK.00700"
    assert normalize_symbol("CN.510300", "futu") == "SH.510300"
    assert normalize_symbol("CN.600519", "tushare") == "600519.SH"
    assert normalize_symbol("CN.000001", "tushare") == "000001.SZ"
