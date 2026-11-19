"""Backtest del método TradingLatino (EMA 55 + Squeeze Momentum de LazyBear + ADX con nivel clave 23).

Reglas codificadas tal como las describe la guía (checklist alcista; la bajista es el espejo):
  DIRECCIÓN  precio por encima de la EMA 55.
  IMPULSO    el Squeeze Momentum sale de un valle rojo: el histograma cruza a positivo (estricta) o sigue negativo
             pero pierde fuerza, «rojo transparentito» (relajada); y no hay squeeze (cruces grises).
  FUERZA     el ADX(14) está sobre 23 y con pendiente positiva (estricta: lo cruzó en las últimas 3 velas).
Entrada en la APERTURA de la vela siguiente (sin mirar el futuro). Salidas: horizonte fijo de 5/10/20 velas y la
salida táctica del método (el momentum pierde fuerza: histograma «verde transparentito», o cierre bajo la EMA 55;
máximo 40 velas). Costos: 0.10 % ida y vuelta.

Para saber qué aporta cada pieza se mide también cada filtro por separado (ablación) y la referencia sin filtro.
Las estadísticas usan el promedio por fecha (las acciones se mueven juntas: contar cada señal como independiente
inflaría la significancia).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

COSTO = 0.001
HS = (5, 10, 20)
CRIPTO = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "LTC-USD", "LINK-USD", "AVAX-USD", "BCH-USD",
          "DOT-USD", "UNI-USD", "AAVE-USD"]


def _tr(df):
    pc = df["Close"].shift()
    return pd.concat([df["High"] - df["Low"], (df["High"] - pc).abs(), (df["Low"] - pc).abs()], axis=1).max(axis=1)


def _lsma(s: pd.Series, n: int) -> pd.Series:
    """Regresión lineal móvil evaluada en la última vela (linreg de Pine con offset 0)."""
    x = np.arange(n, dtype=float)
    xm = x.mean()
    w = (x - xm) / ((x - xm) ** 2).sum()

    def f(y):
        return y.mean() + (w * y).sum() * (n - 1 - xm)
    return s.rolling(n).apply(f, raw=True)


def indicadores(df: pd.DataFrame) -> pd.DataFrame:
    c = df["Close"]
    d = pd.DataFrame(index=df.index)
    d["ema55"] = c.ewm(span=55, adjust=False).mean()
    n = 20
    basis, dev = c.rolling(n).mean(), 2.0 * c.rolling(n).std(ddof=0)
    kma, krg = c.rolling(n).mean(), _tr(df).rolling(n).mean() * 1.5
    d["sq_on"] = ((basis - dev) > (kma - krg)) & ((basis + dev) < (kma + krg))
    mid = ((df["High"].rolling(n).max() + df["Low"].rolling(n).min()) / 2 + kma) / 2
    d["val"] = _lsma(c - mid, n)
    up, dn = df["High"].diff(), -df["Low"].diff()
    pdm = up.where((up > dn) & (up > 0), 0.0)
    ndm = dn.where((dn > up) & (dn > 0), 0.0)
    tr = _tr(df).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    pdi = 100 * pdm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() / tr
    ndi = 100 * ndm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean() / tr
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    d["adx"] = dx.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    return d


def senales(df: pd.DataFrame, d: pd.DataFrame) -> pd.DataFrame:
    c, v, pv, a = df["Close"], d["val"], d["val"].shift(), d["adx"]
    S = pd.DataFrame(index=df.index)
    def primera(x):  # solo la vela en que la condición empieza a cumplirse (no repetir la misma señal)
        x = x.fillna(False).astype(bool)
        return x & ~x.shift(fill_value=False)

    def reciente(x, k):  # ocurrió en alguna de las últimas k velas
        return x.fillna(False).astype(int).rolling(k, min_periods=1).max().astype(bool)
    adx_ok = (a > 23) & (a > a.shift())
    adx_cruce = adx_ok & reciente(a <= 23, 5)  # cruzó el nivel 23 hace pocas velas y sigue subiendo
    sin_squeeze = ~d["sq_on"]
    for lado, s in (("L", 1), ("C", -1)):
        dir_ = (c > d["ema55"]) if s == 1 else (c < d["ema55"])
        cruce = (s * v > 0) & (s * pv <= 0)
        crece = (s * v > 0) & (s * v > s * pv) & reciente(cruce, 3)  # montañita recién nacida y creciendo
        pierde = (s * v < 0) & (s * v > s * pv)  # valle que pierde fuerza (rojo transparentito)
        S[f"{lado}_estricta"] = primera(dir_ & crece & sin_squeeze & adx_cruce)
        S[f"{lado}_relajada"] = primera(dir_ & (crece | pierde) & sin_squeeze & adx_ok)
        # ablación: cada pieza sola y combinaciones de dos
        S[f"{lado}_solo_ema"] = dir_
        S[f"{lado}_solo_squeeze"] = primera(crece & sin_squeeze)
        S[f"{lado}_solo_adx"] = primera(adx_cruce)
        S[f"{lado}_ema_squeeze"] = primera(dir_ & crece & sin_squeeze)
        S[f"{lado}_ema_adx"] = primera(dir_ & adx_cruce)
    S["todas_las_velas"] = True
    return S


def resultados(df: pd.DataFrame, d: pd.DataFrame, S: pd.DataFrame, ticker: str) -> list[dict]:
    o, c = df["Open"].to_numpy(), df["Close"].to_numpy()
    val, ema = d["val"].to_numpy(), d["ema55"].to_numpy()
    n = len(df)
    filas = []
    for col in S.columns:
        lado = -1 if col.startswith("C_") else 1
        idx = np.flatnonzero(S[col].to_numpy())
        if col in ("todas_las_velas", "L_solo_ema", "C_solo_ema"):
            idx = idx[idx % 5 == 0]  # referencias muy frecuentes: 1 de cada 5 velas basta y ahorra memoria
        for i in idx:
            e = i + 1
            if e >= n or not np.isfinite(o[e]) or i < 60:
                continue
            f = {"ticker": ticker, "fecha": df.index[i], "regla": col}
            for H in HS:
                j = e + H - 1
                f[f"r{H}"] = lado * (c[j] / o[e] - 1) - COSTO if j < n else np.nan
            # salida táctica del método: momentum pierde fuerza o cierre al otro lado de la EMA 55 (máx. 40 velas)
            j = e
            while j < min(n - 1, e + 40):
                pierde = lado * val[j] > 0 and lado * val[j] < lado * val[j - 1]
                rompe = lado * (c[j] - ema[j]) < 0
                if pierde or rompe:
                    break
                j += 1
            f["r_tactica"] = lado * (c[j] / o[e] - 1) - COSTO
            f["velas_tactica"] = j - e + 1
            filas.append(f)
    return filas


def resumir(R: pd.DataFrame) -> pd.DataFrame:
    out = []
    ref = {H: R.loc[R["regla"] == "todas_las_velas", f"r{H}"].mean() for H in HS}
    for regla, g in R.groupby("regla"):
        fila = {"regla": regla, "senales": len(g), "acciones": g["ticker"].nunique()}
        for k in [f"r{H}" for H in HS] + ["r_tactica"]:
            x = g[k].dropna()
            por_fecha = x.groupby(g.loc[x.index, "fecha"]).mean()
            t = por_fecha.mean() / (por_fecha.std(ddof=1) / np.sqrt(len(por_fecha))) if len(por_fecha) > 2 else np.nan
            fila[f"{k}_media%"] = 100 * x.mean()
            fila[f"{k}_acierto%"] = 100 * (x > 0).mean()
            fila[f"{k}_t"] = t
        fila["velas_tactica"] = g["velas_tactica"].mean()
        lado = -1 if regla.startswith("C_") else 1
        fila["exceso_r10%"] = 100 * (g["r10"].mean() - lado * ref[10]) if regla != "todas_las_velas" else 0.0
        out.append(fila)
    return pd.DataFrame(out).set_index("regla")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=300)
    ap.add_argument("--marco", default="1D", help="1D o 1W")
    a = ap.parse_args()
    from core.motor_a import dataset as DS
    from core import alpaca
    tickers = DS.universo(maximo=a.max)
    barras = DS.descargar(tickers, desde_anios=11)
    try:
        cr = alpaca.batch_bars(CRIPTO, "1D", 6)
    except Exception as e:
        print(f"Cripto no disponible: {e}")
        cr = {}
    todas = []
    for grupo, B in (("acciones", barras), ("cripto", cr)):
        filas = []
        for t, df in B.items():
            df = df.dropna(subset=["Open", "Close"])
            if a.marco == "1W":
                df = df.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last",
                                               "Volume": "sum"}).dropna()
            if len(df) < 150:
                continue
            d = indicadores(df)
            filas += resultados(df, d, senales(df, d), t)
        if not filas:
            continue
        R = pd.DataFrame(filas)
        R["grupo"] = grupo
        todas.append(R)
        T = resumir(R)
        pd.set_option("display.width", 250)
        print(f"\n===== {grupo.upper()} · marco {a.marco} · {R['ticker'].nunique()} símbolos · "
              f"{R['fecha'].min():%Y-%m} → {R['fecha'].max():%Y-%m} =====")
        cols = ["senales", "r5_media%", "r10_media%", "r10_acierto%", "r10_t", "r20_media%", "r20_t",
                "r_tactica_media%", "r_tactica_acierto%", "r_tactica_t", "velas_tactica", "exceso_r10%"]
        print(T[cols].round(2).to_string())
        # robustez en el tiempo de la regla principal
        for regla in ("L_estricta", "L_relajada", "C_relajada"):
            g = R[R["regla"] == regla]
            if len(g):
                anual = g.groupby(g["fecha"].dt.year)["r10"].agg(["count", "mean"])
                anual["mean"] *= 100
                print(f"{regla} por año (n, retorno medio a 10 velas %):",
                      "; ".join(f"{y}: {int(r['count'])}, {r['mean']:+.2f}" for y, r in anual.iterrows()))
    if todas:
        R = pd.concat(todas)
        Path("datos/motor_a").mkdir(parents=True, exist_ok=True)
        R.to_parquet(f"datos/motor_a/tradinglatino_{a.marco}.parquet")
        json.dump({g: resumir(R[R["grupo"] == g]).round(4).reset_index().to_dict("records")
                   for g in R["grupo"].unique()},
                  open(f"datos/motor_a/reporte_tradinglatino_{a.marco}.json", "w"), default=float, indent=1)


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
