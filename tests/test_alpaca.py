"""Pruebas de core/alpaca.py con respuestas simuladas (formato de la API v2 de Alpaca)."""
import pandas as pd
import pytest

from core import alpaca, data


class Resp:
    def __init__(self, js, code=200):
        self._js, self.status_code, self.text = js, code, str(js)

    def json(self):
        return self._js


def _intraday_rows(day="2026-11-02", start_utc_h=13, n=36, px=100.0):
    """Barras de 30 min desde las 13:00 UTC (8:00 NY): incluye premercado y posmercado."""
    t0 = pd.Timestamp(f"{day} {start_utc_h}:00", tz="UTC")
    rows = []
    for i in range(n):
        p = px + i * 0.1
        rows.append({"t": (t0 + pd.Timedelta(minutes=30 * i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "o": p, "h": p + 0.5, "l": p - 0.5, "c": p + 0.2, "v": 1000 + i})
    return rows


def _daily_rows(n=300, px=50.0):
    days = pd.bdate_range(end="2026-11-06", periods=n)
    return [{"t": f"{d:%Y-%m-%d}T05:00:00Z", "o": px + i, "h": px + i + 1, "l": px + i - 1, "c": px + i + 0.5, "v": 1e6}
            for i, d in enumerate(days)]


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.delenv("TRADING_DEMO", raising=False)
    alpaca.CACHE.clear()
    yield
    alpaca.CACHE.clear()


def install(monkeypatch, handler):
    calls = []

    def fake_get(self_or_url, *a, **kw):
        url = self_or_url if isinstance(self_or_url, str) else a[0]
        calls.append((url, dict(kw.get("params") or {})))
        return handler(url, kw.get("params") or {}, kw.get("headers") or {})

    monkeypatch.setattr(alpaca.requests, "get", fake_get)
    monkeypatch.setattr(alpaca.requests.Session, "get", fake_get)
    return calls


def test_pagination_and_daily(monkeypatch):
    rows = _daily_rows(300)

    def h(url, p, hd):
        assert hd["APCA-API-KEY-ID"] == "k" and p["feed"] == "sip" and p["adjustment"] == "all"
        if p.get("page_token") == "x":
            return Resp({"bars": {"AAPL": rows[150:]}, "next_page_token": None})
        return Resp({"bars": {"AAPL": rows[:150]}, "next_page_token": "x"})

    calls = install(monkeypatch, h)
    df = alpaca.bars("AAPL", "1D")
    assert len(df) == 300 and len(calls) == 2
    assert list(df.columns) == alpaca.OHLCV
    assert df.index[-1] == pd.Timestamp("2026-11-06")  # normalizado a la fecha de NY
    # segunda llamada sale de la caché
    alpaca.bars("AAPL", "1D")
    assert len(calls) == 2


def test_sip_falls_back_to_iex(monkeypatch):
    def h(url, p, hd):
        if p["feed"] == "sip":
            return Resp({"message": "subscription does not permit querying recent SIP data"}, 403)
        return Resp({"bars": {"AAPL": _daily_rows(100)}})

    calls = install(monkeypatch, h)
    assert len(alpaca.bars("AAPL", "1D")) == 100
    assert [c[1]["feed"] for c in calls] == ["sip", "iex"]


def test_intraday_regular_session_and_alignment(monkeypatch):
    install(monkeypatch, lambda u, p, h: Resp({"bars": {"AAPL": _intraday_rows()}}))
    m30 = alpaca.bars("AAPL", "30m")
    assert m30.index.min().strftime("%H:%M") == "09:30" and m30.index.max().strftime("%H:%M") == "15:30"
    assert len(m30) == 13
    alpaca.CACHE.clear()
    h1 = alpaca.bars("AAPL", "1h")
    assert [t.strftime("%H:%M") for t in h1.index] == ["09:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30"]
    first = m30.iloc[:2]
    assert h1.iloc[0]["Open"] == first["Open"].iloc[0] and h1.iloc[0]["Volume"] == first["Volume"].sum()
    alpaca.CACHE.clear()
    h4 = alpaca.bars("AAPL", "4h")
    assert [t.strftime("%H:%M") for t in h4.index] == ["09:30", "13:30"]
    assert h4["Volume"].sum() == m30["Volume"].sum()


def test_symbol_mapping_and_crypto(monkeypatch):
    def h(url, p, hd):
        if "crypto" in url:
            assert p["symbols"] == "BTC/USD"
            return Resp({"bars": {"BTC/USD": _intraday_rows(n=48, px=70000)}})
        assert p["symbols"] == "BRK.B"
        return Resp({"bars": {"BRK.B": _daily_rows(80)}})

    install(monkeypatch, h)
    assert len(alpaca.bars("BRK-B", "1D")) == 80
    btc = alpaca.bars("BTC-USD", "30m")
    assert len(btc) == 48  # cripto 24/7: sin filtro de sesión


def test_batch_and_weekly(monkeypatch):
    install(monkeypatch, lambda u, p, h: Resp({"bars": {s: _daily_rows(260) for s in p["symbols"].split(",")}}))
    got = alpaca.batch_bars(["AAPL", "MSFT", "NVDA"], "1D", 2)
    assert set(got) == {"AAPL", "MSFT", "NVDA"}
    alpaca.CACHE.clear()
    w = alpaca.bars("AAPL", "1W")
    assert all(d.dayofweek == 4 for d in w.index)  # semanas cerradas el viernes


def test_data_layer_uses_alpaca_and_falls_back(monkeypatch):
    install(monkeypatch, lambda u, p, h: Resp({"bars": {"AAPL": _daily_rows(400)}}))
    df = data.history_tf("AAPL", "1D")
    assert df.attrs["fuente"].startswith("Alpaca") and len(df) == 400

    alpaca.CACHE.clear()
    install(monkeypatch, lambda u, p, h: Resp({"message": "boom"}, 500))
    called = {}

    class FakeTicker:
        def __init__(self, t):
            called["t"] = t

        def history(self, **kw):
            idx = pd.bdate_range(end="2026-11-06", periods=100)
            return pd.DataFrame({"Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5, "Volume": 10.0}, index=idx)

    import yfinance
    monkeypatch.setattr(yfinance, "Ticker", FakeTicker)
    df = data.history_tf("AAPL", "1D")
    assert df.attrs["fuente"] == "Yahoo Finance" and called["t"] == "AAPL"


def test_no_keys_means_yahoo_for_stocks(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY")
    assert not alpaca.available()
    assert not data._use_alpaca("AAPL", "yahoo")
    assert data._use_alpaca("BTC-USD", "yahoo")  # cripto no necesita clave
    assert not data._use_alpaca("AAPL", "alphavantage")


def test_latest_bar(monkeypatch):
    install(monkeypatch, lambda u, p, h: Resp({"bars": {"AAPL": {"t": "2026-11-06T20:59:00Z", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 9}}}))
    b = alpaca.latest_bar("AAPL")
    assert b["Close"] == 1.5 and b["t"] == pd.Timestamp("2026-11-06 15:59")


def test_scanner_batch_uses_alpaca_then_yahoo_for_missing(monkeypatch):
    install(monkeypatch, lambda u, p, h: Resp({"bars": {s: _daily_rows(260) for s in p["symbols"].split(",") if s != "XYZ"}}))
    asked = {}

    def fake_download(part, **kw):
        asked["part"] = list(part)
        idx = pd.bdate_range(end="2026-11-06", periods=50)
        return pd.DataFrame({"Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5, "Volume": 10.0}, index=idx)

    import yfinance
    monkeypatch.setattr(yfinance, "download", fake_download)
    got = data.batch_history(["AAPL", "MSFT", "XYZ"], "2y")
    assert set(got) == {"AAPL", "MSFT", "XYZ"} and asked["part"] == ["XYZ"]
