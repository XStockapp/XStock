"""Variables del Motor A. Todas se calculan con datos hasta el cierre del día t (nada del futuro) y se expresan en la
escala de la propia acción: retornos y distancias divididos por su volatilidad diaria (σ de 20 sesiones). Así un
+2σ en SPY y en AMD significan lo mismo para el modelo aunque en % sean muy distintos."""
from __future__ import annotations

import numpy as np
import pandas as pd

VENTANA_SIGMA = 20


def _sigma(r: pd.Series, n: int) -> pd.Series:
    return r.rolling(n, min_periods=n).std()


def _rsi(c: pd.Series, n: int = 14) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def _adx(h, l, c, n: int = 14) -> pd.Series:
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    pdm = (h.diff()).where((h.diff() > -l.diff()) & (h.diff() > 0), 0.0)
    mdm = (-l.diff()).where((-l.diff() > h.diff()) & (-l.diff() > 0), 0.0)
    atr = tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    pdi = 100 * pdm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / atr
    mdi = 100 * mdm.ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False, min_periods=n).mean(), (pdi - mdi) / 100


def por_accion(df: pd.DataFrame) -> pd.DataFrame:
    """Variables diarias de UNA acción a partir de OHLCV diario (índice = fecha)."""
    o, h, l, c, v = (df[k].astype(float) for k in ("Open", "High", "Low", "Close", "Volume"))
    r = np.log(c / c.shift())
    s20 = _sigma(r, VENTANA_SIGMA)
    s5, s60 = _sigma(r, 5), _sigma(r, 60)
    X = pd.DataFrame(index=df.index)
    # momentum y reversión en σ (retorno de n días / σ·√n)
    for n in (1, 5, 10, 20, 60, 120):
        X[f"ret_{n}"] = np.log(c / c.shift(n)) / (s20 * np.sqrt(n))
    # distancia a medias en σ
    for n in (20, 50, 200):
        X[f"dist_sma{n}"] = np.log(c / c.rolling(n, min_periods=n).mean()) / s20
    X["pend_sma50"] = np.log(c.rolling(50).mean() / c.rolling(50).mean().shift(10)) / (s20 * np.sqrt(10))
    # régimen de volatilidad
    X["vol_5_20"] = s5 / s20
    X["vol_20_60"] = s20 / s60
    X["vol_anual"] = s20 * np.sqrt(252)
    X["rango_dia"] = np.log(h / l) / s20  # rango del día en σ
    X["gap"] = np.log(o / c.shift()) / s20
    X["cierre_en_rango"] = (c - l) / (h - l).replace(0, np.nan)  # 0 = cerró en el mínimo, 1 = en el máximo
    # osciladores clásicos (ya acotados)
    X["rsi14"] = _rsi(c) / 100
    ema12, ema26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    X["macd_hist"] = (macd - macd.ewm(span=9, adjust=False).mean()) / (c * s20)
    adx, di = _adx(h, l, c)
    X["adx"], X["di_neto"] = adx / 100, di
    m20, sd20 = c.rolling(20).mean(), c.rolling(20).std()
    X["boll_pb"] = (c - (m20 - 2 * sd20)) / (4 * sd20).replace(0, np.nan)
    # máximos / mínimos de 52 semanas en σ
    X["dist_max252"] = np.log(c / h.rolling(252, min_periods=120).max()) / s20
    X["dist_min252"] = np.log(c / l.rolling(252, min_periods=120).min()) / s20
    # volumen relativo (z-score del log-volumen)
    lv = np.log(v.replace(0, np.nan))
    X["vol_rel"] = (lv - lv.rolling(20).mean()) / lv.rolling(20).std()
    X["dolar_vol"] = np.log((c * v).rolling(20).mean())  # liquidez (log USD diarios)
    X["sigma_d"] = s20  # se usa para las barreras; no es variable del modelo
    return X.replace([np.inf, -np.inf], np.nan)


def de_mercado(spy: pd.DataFrame) -> pd.DataFrame:
    """Contexto de mercado (SPY) común a todas las acciones de un mismo día."""
    c = spy["Close"].astype(float)
    r = np.log(c / c.shift())
    s20 = _sigma(r, VENTANA_SIGMA)
    M = pd.DataFrame(index=spy.index)
    for n in (5, 20, 60):
        M[f"mkt_ret_{n}"] = np.log(c / c.shift(n)) / (s20 * np.sqrt(n))
    M["mkt_dist_sma200"] = np.log(c / c.rolling(200).mean()) / s20
    M["mkt_vol_anual"] = s20 * np.sqrt(252)
    M["mkt_vol_20_60"] = s20 / _sigma(r, 60)
    return M


def relativas(X: pd.DataFrame, M: pd.DataFrame) -> pd.DataFrame:
    """Fuerza relativa frente al mercado (en σ de la acción)."""
    Z = X.join(M, how="left")
    for n in (5, 20, 60):
        Z[f"rel_{n}"] = Z[f"ret_{n}"] - Z[f"mkt_ret_{n}"] * (Z["mkt_vol_anual"] / Z["vol_anual"])
    return Z
