import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

from core.fuentes import marketdata as MD

_spec = importlib.util.spec_from_file_location("bf", Path(__file__).resolve().parents[1] / "scripts/backfill_marketdata_oi.py")
BF = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BF)


def test_iv_recupera_la_volatilidad():
    S, K, T, s = np.array([100.0, 100, 100]), np.array([95.0, 100, 110]), np.array([0.1] * 3), 0.35
    call = np.array([True, False, True])
    precio = MD._bs(S, K, T, s, call)
    assert np.allclose(MD.iv_vectorizada(precio, S, K, T, call), s, atol=1e-4)


def test_iv_nula_si_el_precio_es_incoherente():
    iv = MD.iv_vectorizada(np.array([0.0, np.nan, 1.0]), np.array([100.0] * 3), np.array([80.0] * 3),
                           np.array([0.1] * 3), np.array([True] * 3))  # 1.0 < intrínseco de 20
    assert np.isnan(iv).all()


def _respuesta():
    exp = int(pd.Timestamp("2025-03-21 16:00", tz="America/New_York").timestamp())
    S, T = 100.0, 30 / 365
    filas = [(K, lado) for K in (70, 90, 100, 110, 140) for lado in ("call", "put")]
    precios = [float(MD._bs(np.array(S), np.array(K), np.array(T), 0.3, np.array(l == "call"))) for K, l in filas]
    return {"s": "ok", "optionSymbol": [f"X{i}" for i in range(len(filas))], "expiration": [exp] * len(filas),
            "side": [l for _, l in filas], "strike": [K for K, _ in filas], "dte": [30] * len(filas),
            "bid": [p * 0.98 for p in precios], "ask": [p * 1.02 for p in precios], "last": precios,
            "volume": [10] * len(filas), "openInterest": [500] * len(filas), "underlyingPrice": [S] * len(filas),
            "iv": [None] * len(filas)}


def test_tabla_filtra_delta_y_usa_tipos_ligeros():
    df = MD.a_tabla(_respuesta(), "2025-02-19")
    assert len(df) and df["delta"].abs().between(0.10, 0.90).all()
    assert not ((df["strike"] == 70) & (df["tipo"] == 1)).any()      # call muy dentro del dinero: Δ≈1, fuera
    assert not ((df["strike"] == 140) & (df["tipo"] == 1)).any()     # call muy lejano: Δ≈0, fuera
    assert dict(df.dtypes.astype(str)) == MD.ESQUEMA
    assert df["oi"].eq(500).all() and np.allclose(df["iv"], 0.3, atol=0.02)
    assert BF._de_dia(int(df["vencimiento"].iloc[0])) == "2025-03-21"
    assert BF._de_dia(int(df["fecha"].iloc[0])) == "2025-02-19"


def test_progreso_no_repite_fechas():
    p = BF.Progreso()
    f = BF.fechas_objetivo(0.1, hoy=pd.Timestamp("2025-06-10").date())
    assert f[0] == "2025-06-09" and f == sorted(f, reverse=True)
    p.marcar("AAPL", f[:5])
    assert BF.Progreso(__import__("json").loads(p.a_json())).pendientes("AAPL", f) == f[5:]


def test_unir_sin_duplicados():
    a = MD.a_tabla(_respuesta(), "2025-02-19")
    df = BF.unir(a, [a, MD.a_tabla(_respuesta(), "2025-02-20")])
    assert len(df) == 2 * len(a) and dict(df.dtypes.astype(str)) == MD.ESQUEMA
    assert BF.nombre_parquet("BRK.B") == "BRK-B_oi.parquet"


def test_cliente_para_al_agotar_saldo():
    c = MD.Cliente(token="x", limite_creditos=10)
    c.consumidos = 10
    try:
        c.cadena("AAPL", "2025-02-19")
        assert False
    except MD.SinCreditos:
        pass
