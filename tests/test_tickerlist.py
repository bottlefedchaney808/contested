import httpx

from contested.tickerlist import download_ticker_list, load_ticker_set


def test_load_ticker_set(tmp_path):
    p = tmp_path / "t.txt"
    p.write_text("# comment\nGME\n\namc\nMMM\n", encoding="utf-8")
    assert load_ticker_set(p) == frozenset({"GME", "AMC", "MMM"})


def test_download_parses_nasdaq(tmp_path):
    listed = "Symbol\tCompany Name\nGME\tGameStop\nMMM\t3M\n"
    other = "Symbol\tCompany Name\nAAPL\tApple\n"
    def handler(request: httpx.Request) -> httpx.Response:
        if "nasdaqlisted" in request.url.path:
            return httpx.Response(200, text=listed)
        return httpx.Response(200, text=other)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    dest = tmp_path / "tickers_us.txt"
    got = download_ticker_list(dest, client=client)
    assert got == frozenset({"GME", "MMM", "AAPL"})
    assert dest.is_file()


def test_download_failure_raises(tmp_path):
    import pytest
    from contested.tickerlist import TickerListError
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(TickerListError):
        download_ticker_list(tmp_path / "t.txt", client=client)
