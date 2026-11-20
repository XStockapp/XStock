"""Estrategias guardadas que se pueden integrar al Motor A (botón del motor en Opciones).

Cada estrategia tiene reglas codificadas y su backtest (tools/backtest_tradinglatino.py en la rama del análisis):
solo las validadas pueden activarse; las demás del panel Estrategias se muestran «sin reglas aún».

TradingLatino · giro (anexo del método): tras un movimiento con fuerza en contra (ADX > 23 con el DI contrario
dominante), el Squeeze Momentum forma un valle que asciende y el ADX gira a la baja; se confirma con el RSI en zona
extrema y el cruce del MACD. Las funciones de cálculo son las MISMAS del backtest, para que la señal en vivo sea la
que se midió.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

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
    d["pdi"], d["ndi"] = pdi, ndi
    d["atr"] = tr
    d["vol_ma20"] = df["Volume"].rolling(20).mean()
    dlt = c.diff()
    g = dlt.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    p_ = (-dlt.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    d["rsi"] = 100 - 100 / (1 + g / p_.replace(0, np.nan))
    m = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    d["macd"], d["macd_sig"] = m, m.ewm(span=9, adjust=False).mean()
    return d


def vrvp(df: pd.DataFrame, d: pd.DataFrame, idx: np.ndarray, lado: int, n: int = 100, bins: int = 24):
    """Aproximación del VRVP (perfil de volumen del rango visible) en las velas idx: volumen por nivel de precio de
    las últimas n velas. Para una compra (espejo para venta) es favorable que haya un nodo de alto volumen (≥ p70 de
    los niveles) entre el precio y 1 ATR por debajo (soporte), y aparte se mide si NO hay un nodo muy fuerte (≥ p90)
    hasta 1.5 ATR por encima (sin techo)."""
    tp = ((df["High"] + df["Low"] + df["Close"]) / 3).to_numpy()
    vol = df["Volume"].fillna(0).to_numpy()
    c, atr = df["Close"].to_numpy(), d["atr"].to_numpy()
    ok, libre, nodo = np.zeros(len(df), bool), np.zeros(len(df), bool), np.zeros(len(df), bool)
    for i in idx:
        if i < n or not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        h, bordes = np.histogram(tp[i - n + 1:i + 1], bins=bins, weights=vol[i - n + 1:i + 1])
        if h.sum() <= 0:
            continue
        centros = (bordes[:-1] + bordes[1:]) / 2
        dist = lado * (centros - c[i])  # > 0: del lado al que se quiere ir
        hvn, fuerte = h >= np.percentile(h, 70), h >= np.percentile(h, 90)
        soporte = (hvn & (dist <= 0) & (dist >= -atr[i])).any()
        techo = (fuerte & (dist > 0) & (dist <= 1.5 * atr[i])).any()
        k = min(max(np.searchsorted(bordes, c[i]) - 1, 0), bins - 1)  # nivel donde está el precio
        ok[i], libre[i], nodo[i] = soporte, not techo, fuerte[k] or (k > 0 and fuerte[k - 1]) or (k < bins - 1 and fuerte[k + 1])
    return ok, libre, nodo


def senales_anexo(df: pd.DataFrame, d: pd.DataFrame) -> pd.DataFrame:
    """Lógica de giro del anexo (como la usa el indicador «Multiple strategies [LPWN]»):
    direccionalidad = pendiente del Squeeze Momentum (sube → alcista); el ADX con pendiente negativa tras un
    movimiento fuerte indica que ese movimiento pierde fuerza.
      GIRO ALCISTA: movimiento bajista previo con fuerza (ADX llegó a > 23 con −DI > +DI) · valle rojo que asciende
                    (momentum < 0 y subiendo) · ADX girando a la baja.
      + RSI: el RSI(14) estuvo en zona baja (< 35) en las últimas 5 velas.
      + MACD: la línea MACD cruzó sobre su señal en las últimas 3 velas (confirmación completa del usuario).
      CONTINUACIÓN (Jaime Merino): direccionalidad alcista y ADX con pendiente positiva cruzando 23.
    Espejo para el lado bajista."""
    v, pv, a = d["val"], d["val"].shift(), d["adx"]

    def primera(x):
        x = x.fillna(False).astype(bool)
        return x & ~x.shift(fill_value=False)

    def reciente(x, k):
        return x.fillna(False).astype(int).rolling(k, min_periods=1).max().astype(bool)
    S = pd.DataFrame(index=df.index)
    adx_baja, adx_sube = a < a.shift(), a > a.shift()
    for lado, s in (("L", 1), ("C", -1)):
        contra_fuerte = (a > 23) & ((d["ndi"] > d["pdi"]) if s == 1 else (d["pdi"] > d["ndi"]))
        previo = reciente(contra_fuerte, 10)
        valle_sube = (s * v < 0) & (s * v > s * pv)
        giro = primera(previo & valle_sube & adx_baja)
        rsi_ext = reciente((d["rsi"] < 35) if s == 1 else (d["rsi"] > 65), 5)
        macd_x = (s * (d["macd"] - d["macd_sig"]) > 0) & (s * (d["macd"].shift() - d["macd_sig"].shift()) <= 0)
        S[f"{lado}_giro"] = giro
        S[f"{lado}_giro_rsi"] = primera(previo & valle_sube & adx_baja & rsi_ext)
        S[f"{lado}_giro_rsi_macd"] = primera(reciente(previo & valle_sube & adx_baja, 5) & reciente(rsi_ext, 8)
                                             & macd_x)
        S[f"{lado}_continuacion"] = primera((s * v > s * pv) & adx_sube & reciente(a <= 23, 3) & (a > 23))
        # referencia: solo «valle que asciende», sin ADX ni confirmaciones
        S[f"{lado}_solo_valle_sube"] = primera(valle_sube)
        # filtros discrecionales del anexo: VRVP (soporte de volumen debajo, sin techo fuerte encima) y la regla de
        # la EMA 55: no operar si el precio está pegado a la EMA 55 en contra y sin volumen
        cerca_ema = (s * (d["ema55"] - df["Close"]) > 0) & (s * (d["ema55"] - df["Close"]) < 0.5 * d["atr"])
        ema_mala = cerca_ema & (df["Volume"] < d["vol_ma20"])
        base = [f"{lado}_giro", f"{lado}_giro_rsi_macd", f"{lado}_solo_valle_sube"]
        cand = np.flatnonzero(S[base].any(axis=1).to_numpy())
        sop, lib, _ = vrvp(df, d, cand, s)
        ok_v, sin_techo = pd.Series(sop, index=df.index), pd.Series(lib, index=df.index)
        for b in base:
            S[f"{b}_vrvp"] = S[b] & ok_v
            S[f"{b}_sintecho"] = S[b] & sin_techo
            S[f"{b}_ema55"] = S[b] & ~ema_mala
            S[f"{b}_filtros"] = S[b] & ok_v & ~ema_mala
    S["todas_las_velas"] = True
    return S




# ------------------------------------------------------------------ catálogo
# Resultados del backtest (entrada en la apertura siguiente, 0.10 % de costos, salida táctica del método).
# 1D: 296 acciones líquidas 2016-2026 · 1h: 91 acciones 2022-2026.
CATALOGO = {
    "tradinglatino": {
        "nombre": "TradingLatino · giro", "validada": True,
        "resumen": "Valle del Squeeze que asciende + ADX girando, con RSI y MACD como confirmación",
        "stats": {
            "1D": {"retorno": 1.00, "acierto": 48.4, "ref": 0.33, "acuerdo": 0.50, "desacuerdo": 1.09,
                   "acierto_acuerdo": 48.1, "acierto_desacuerdo": 48.5},
            "1h": {"retorno": 0.34, "acierto": 43.7, "ref": 0.05},
        },
    },
    "pullback": {"nombre": "Pullback a la media en tendencia", "validada": False},
    "breakout": {"nombre": "Ruptura con volumen", "validada": False},
    "reversal": {"nombre": "Reversión en sobreventa", "validada": False},
    "trend": {"nombre": "Seguimiento de tendencia", "validada": False},
}


def senal_tradinglatino(df: pd.DataFrame, ventana: int = 3) -> dict | None:
    """Estado en vivo del giro en las últimas `ventana` velas cerradas. None si no hay datos suficientes.
    {direccion: 'alcista'|'bajista'|None, confirmada: bool, velas: n desde la señal, detalle: texto}."""
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < 120:
        return None
    d = indicadores(df)
    S = senales_anexo(df, d)
    for lado, nombre in (("L", "alcista"), ("C", "bajista")):
        for regla, conf in ((f"{lado}_giro_rsi_macd", True), (f"{lado}_giro", False)):
            ult = S[regla].to_numpy()[-ventana:]
            if ult.any():
                velas = int(ventana - 1 - np.flatnonzero(ult)[-1])
                return {"direccion": nombre, "confirmada": conf, "velas": velas,
                        "detalle": ("giro confirmado con RSI y MACD" if conf else "giro sin confirmar (falta RSI/MACD)")
                        + (" en la última vela" if velas == 0 else f" hace {velas} velas")}
    v, pv = float(d["val"].iat[-1]), float(d["val"].iat[-2])
    a, pa = float(d["adx"].iat[-1]), float(d["adx"].iat[-2])
    dirm = "alcista" if v > pv else "bajista"
    return {"direccion": None, "confirmada": False, "velas": None,
            "detalle": f"sin giro · direccionalidad {dirm}, ADX {a:.1f} {'subiendo' if a > pa else 'bajando'}"}
