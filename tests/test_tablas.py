import numpy as np
import pandas as pd

from core import market, tables
from core.data import _synthetic


def test_rendimientos_acciones_y_cripto():
    idx = pd.bdate_range(end="2026-11-06", periods=300)
    df = pd.DataFrame({"Close": np.arange(1, 301, dtype=float)}, index=idx)
    r = market.rendimientos(df, "AAPL")
    assert round(r["1D"], 4) == round((300 / 299 - 1) * 100, 4)
    assert round(r["7D"], 4) == round((300 / 295 - 1) * 100, 4)      # 5 sesiones
    assert round(r["6M"], 4) == round((300 / 174 - 1) * 100, 4)      # 126 sesiones
    rc = market.rendimientos(df, "BTC-USD")
    assert round(rc["7D"], 4) == round((300 / 293 - 1) * 100, 4)     # 7 días corridos
    short = market.rendimientos(df.tail(10), "AAPL")
    assert short["1M"] is None and short["1D"] is not None


def test_spark_tail():
    s = list(range(200))
    assert len(market.spark_tail(s, "1M", "AAPL")) == 22
    assert len(market.spark_tail(s, "7D", "BTC-USD")) == 8


def test_prefs_por_defecto_y_validacion():
    p = market.prefs({}, "acciones")
    assert p["perf"] == ["1D", "7D", "1M", "6M"] and p["grafico"] == "3M"
    S = market.with_prefs({}, "cripto", {"perf": ["30d", "1h", "xx"], "grafico": "zz", "filas": 7})
    pc = market.prefs(S, "cripto")
    assert pc["perf"] == ["1h", "30d"] and pc["grafico"] == "7 días" and pc["filas"] == 50


def test_columnas_acciones_y_cripto():
    from core.scanner import scan
    prices = {t: _synthetic(t) for t in ["AAPL", "MSFT"]}
    res = scan(prices, 0, 0, 3, 1.5, 20)
    assert {"Ret 1D", "Ret 7D", "Ret 1M", "Ret 6M", "Spark"} <= set(res.columns)
    p = market.prefs({}, "acciones")
    mk, cfg, fm = tables.columnas(res, "acciones", p)
    assert list(mk.columns[:2]) == ["Logo", "Precio"] and "Últimos 3M" in mk and len(mk["Últimos 3M"].iloc[0]) == 64
    assert fm["perf"] == ["1D", "7D", "1M", "6M"]
    pc = market.prefs({}, "cripto")
    dfc = pd.DataFrame({"Ticker": ["BTC-USD"], "Precio": [1.0], "Ret 1D": [2.0], "Spark": [[1, 2, 3, 4, 5, 6, 7, 8, 9]]})
    cm = {"BTC-USD": {"nombre": "Bitcoin", "logo": "x", "precio": 68000, "1h": 0.2, "24h": None, "7d": -2.6,
                      "30d": 5.0, "volumen": 1e10, "cap": 1.5e12, "fdv": 1.6e12, "cap_fdv": 0.94, "ranking": 1,
                      "spark": [1, 2, 3]}}
    mk, cfg, fm = tables.columnas(dfc, "cripto", pc, cm)
    assert mk.loc[0, "Moneda"] == "Bitcoin" and mk.loc[0, "Precio"] == 68000
    assert mk.loc[0, "24h"] == 2.0          # sin dato de CoinGecko: usa el del escaneo
    assert mk.loc[0, "Últimos 7 días"] == [1, 2, 3]


def test_formatos():
    assert tables.money_compact(1527938282288) == "$1.53 T"
    assert tables.money_compact(10515357574) == "$10.52 B"
    assert tables.perf_fmt(-2.63) == "▼ 2.6%" and tables.perf_fmt(0.2) == "▲ 0.2%"
    assert tables.price_fmt(0.00001234) == "$0.00001234" and tables.price_fmt(0.9994) == "$0.9994"
    assert tables.price_fmt(75980.82) == "$75,980.82"
