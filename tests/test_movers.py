import pandas as pd
import pytest

from core import alpaca, movers


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    movers._NOMBRES.clear()


class R:
    def __init__(self, js, code=200):
        self._js, self.status_code = js, code

    def json(self):
        return self._js


def test_valida_acciones():
    assert movers._accion_valida("NVDA", 188.0)
    assert movers._accion_valida("BRK.B", 450.0)
    assert not movers._accion_valida("ABCDW", 3.0)    # warrant
    assert not movers._accion_valida("PENY", 0.8)     # menos de $2
    assert not movers._accion_valida("ABC.WS", 5.0)


def test_alzas_alpaca_con_nombres(monkeypatch):
    def fake_get(path, params, session=None):
        assert path == "/v1beta1/screener/stocks/movers"
        return {"gainers": [{"symbol": "KRMN", "price": 46.48, "percent_change": 37.9},
                            {"symbol": "ABCDW", "price": 4.0, "percent_change": 90.0},
                            {"symbol": "PENY", "price": 0.5, "percent_change": 80.0},
                            {"symbol": "FLY", "price": 20.86, "percent_change": 37.0}]}

    monkeypatch.setattr(alpaca, "_get", fake_get)
    monkeypatch.setattr(movers.requests, "get", lambda url, **kw: R({"name": "Karman Holdings Inc. Common Stock"})
                        if url.endswith("KRMN") else R({}, 404))
    rows = movers.acciones_alzas(5)
    assert [r["ticker"] for r in rows] == ["KRMN", "FLY"]
    assert rows[0]["nombre"] == "Karman Holdings Inc." and rows[0]["var"] == 37.9
    assert rows[1]["nombre"] == "FLY"  # sin nombre en Alpaca: queda el símbolo
    assert rows[0]["logo"].endswith("/KRMN.png")


def test_tendencias_por_volumen_en_dolares(monkeypatch):
    def fake_get(path, params, session=None):
        if "most-actives" in path:
            return {"most_actives": [{"symbol": s} for s in ["SOXS", "NVDA", "TSLA", "PENY"]]}
        return {"SOXS": {"latestTrade": {"p": 3.1}, "dailyBar": {"v": 9e6, "vw": 3.1}, "prevDailyBar": {"c": 3.0}},
                "NVDA": {"latestTrade": {"p": 190.0}, "dailyBar": {"v": 4e6, "vw": 189}, "prevDailyBar": {"c": 185.0}},
                "TSLA": {"latestTrade": {"p": 250.0}, "dailyBar": {"v": 2e6, "vw": 251}, "prevDailyBar": {"c": 255.0}},
                "PENY": {"latestTrade": {"p": 0.9}, "dailyBar": {"v": 9e9, "vw": 0.9}, "prevDailyBar": {"c": 0.8}}}

    monkeypatch.setattr(alpaca, "_get", fake_get)
    monkeypatch.setattr(movers, "nombres", lambda syms: {s: s.title() for s in syms})
    rows = movers.acciones_tendencias(3)
    assert [r["ticker"] for r in rows] == ["NVDA", "TSLA", "SOXS"]
    assert round(rows[1]["var"], 2) == round((250 / 255 - 1) * 100, 2)


def test_respaldo_finviz(monkeypatch):
    monkeypatch.setattr(alpaca, "_get", lambda *a, **k: (_ for _ in ()).throw(alpaca.AlpacaError("500")))
    import core.finviz as fz
    monkeypatch.setattr(fz, "screener_df", lambda sig, f, limit: pd.DataFrame(
        {"Ticker": ["AAA", "BBB"], "Company": ["Aaa Corp", "Bbb Inc"], "Price": [10.0, 5.0], "Change": [0.12, 0.30]}))
    rows = movers.acciones_alzas(5)
    assert [r["ticker"] for r in rows] == ["BBB", "AAA"] and rows[0]["var"] == pytest.approx(30.0)


def test_cripto(monkeypatch):
    def fake_cg(path, params):
        if path == "/search/trending":
            return {"coins": [{"item": {"symbol": "usdt", "name": "Tether"}},
                              {"item": {"symbol": "sol", "name": "Solana", "small": "img",
                                        "data": {"price": "$182.30", "price_change_percentage_24h": {"usd": 6.8}}}}]}
        return [{"symbol": "btc", "name": "Bitcoin", "current_price": 68000, "price_change_percentage_24h": 2.0,
                 "total_volume": 3e10, "image": "b"},
                {"symbol": "pepe", "name": "Pepe", "current_price": 1e-5, "price_change_percentage_24h": 30.0,
                 "total_volume": 9e8, "image": "p"},
                {"symbol": "tiny", "name": "Tiny", "current_price": 1, "price_change_percentage_24h": 90.0,
                 "total_volume": 1e5, "image": "t"},
                {"symbol": "usdc", "name": "USDC", "current_price": 1, "price_change_percentage_24h": 0.1,
                 "total_volume": 9e9, "image": "u"}]

    monkeypatch.setattr(movers, "_cg", fake_cg)
    t = movers.cripto_tendencias(5)
    assert t == [{"ticker": "SOL-USD", "nombre": "Solana", "precio": 182.3, "var": 6.8, "logo": "img"}]
    a = movers.cripto_alzas(5)
    assert [r["ticker"] for r in a] == ["PEPE-USD", "BTC-USD"]  # sin estables ni monedas sin volumen
