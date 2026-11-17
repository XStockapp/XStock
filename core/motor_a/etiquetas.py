"""Etiquetas de triple barrera (López de Prado, Advances in Financial Machine Learning, cap. 3).

Para cada día t (entrada al cierre de t) se fijan dos barreras a ±k·σ·√H del precio y un límite de H sesiones:
  1 → el máximo intradía toca la barrera superior antes de que el mínimo toque la inferior
  0 → toca primero la inferior
  si en H sesiones no toca ninguna → se etiqueta por el signo del retorno al final (barrera vertical)
  si ambas se tocan el mismo día → se decide por la dirección del cierre de ese día (no hay dato intradía)
Se guarda también qué barrera se tocó (1 superior, −1 inferior, 2 ambas el mismo día, 0 ninguna): la etiqueta de
MOVIMIENTO es «tocó alguna» (barrera ≠ 0), sin importar la dirección.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def triple_barrera(df: pd.DataFrame, sigma_d: pd.Series, H: int = 10, k: float = 1.0) -> pd.DataFrame:
    h = df["High"].to_numpy(float)
    l = df["Low"].to_numpy(float)
    c = df["Close"].to_numpy(float)
    s = sigma_d.to_numpy(float)
    n = len(c)
    y = np.full(n, np.nan)
    tipo = np.full(n, np.nan)  # 1 = superior, −1 = inferior, 0 = vertical
    dias = np.full(n, np.nan)
    ret_h = np.full(n, np.nan)  # retorno log a H sesiones en σ (para medir la ventaja económica)
    for i in range(n - H):
        if not np.isfinite(s[i]) or s[i] <= 0:
            continue
        w = k * s[i] * np.sqrt(H)
        up, dn = c[i] * np.exp(w), c[i] * np.exp(-w)
        hh, ll = h[i + 1:i + 1 + H], l[i + 1:i + 1 + H]
        tu = np.argmax(hh >= up) if (hh >= up).any() else H
        td = np.argmax(ll <= dn) if (ll <= dn).any() else H
        ret_h[i] = np.log(c[i + H] / c[i]) / (s[i] * np.sqrt(H))
        if tu == H and td == H:
            y[i], tipo[i], dias[i] = float(c[i + H] > c[i]), 0, H
        elif tu < td:
            y[i], tipo[i], dias[i] = 1.0, 1, tu + 1
        elif td < tu:
            y[i], tipo[i], dias[i] = 0.0, -1, td + 1
        else:  # ambas el mismo día
            j = i + 1 + tu
            y[i], tipo[i], dias[i] = float(c[j] >= c[j - 1]), 2, tu + 1
    return pd.DataFrame({"y": y, "barrera": tipo, "dias": dias, "ret_h_sigma": ret_h}, index=df.index)
