"""Laboratorio de validación estadística (walk-forward, fuera de muestra, sin mirar el futuro).

Mide, para un activo y una temporalidad operativa, qué tan bien predice el puntaje técnico la dirección del precio a
distintos horizontes, y compara tres formas de combinar las temporalidades:
  1. Solo la operativa.
  2. MTF con los pesos de la curva log-normal (core/mtf.py).
  3. MTF con pesos estimados de los datos (regresión logística con regularización, ajustada SOLO en el pasado).

Reglas para no engañarse:
* Las temporalidades mayores solo aportan su última vela CERRADA en cada instante (fin de la vela ≤ fin de la operativa).
* Los modelos se ajustan con datos anteriores al tramo evaluado (expanding window, reajuste por bloques).
* Las muestras a horizonte H se solapan: los intervalos de confianza usan N efectivo = N / H.

Métricas:
* Acierto direccional (|puntaje| ≥ 15) con IC 95 % de Wilson sobre N efectivo.
* IC de Spearman (puntaje vs retorno futuro) con IC 95 % por la transformación de Fisher sobre N efectivo.
* Brier score de la probabilidad calibrada de subida y Brier skill score frente a la tasa base (1 − Brier/Brier_base).
* Curva de calibración por deciles de probabilidad.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import data, mtf as MTF
from .technical import compute_all, score_series
from .timeframes import TIMEFRAMES

DURACION = {"10m": pd.Timedelta(minutes=10), "30m": pd.Timedelta(minutes=30), "1h": pd.Timedelta(hours=1),
            "4h": pd.Timedelta(hours=4), "1D": pd.Timedelta(days=1), "1W": pd.Timedelta(days=7),
            "1M": pd.Timedelta(days=31)}
UMBRAL = 15


# ------------------------------------------------------------------ estadística básica (solo numpy)
def wilson(k: int, n: float, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n if n else 0
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - h), min(1.0, c + h))


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 5:
        return float("nan")
    rx, ry = pd.Series(x).rank().to_numpy(), pd.Series(y).rank().to_numpy()
    return float(np.corrcoef(rx, ry)[0, 1])


def fisher_ci(r: float, n_eff: float, z: float = 1.96) -> tuple[float, float]:
    if not np.isfinite(r) or n_eff <= 4:
        return (float("nan"), float("nan"))
    zr = np.arctanh(np.clip(r, -0.999, 0.999))
    se = 1 / math.sqrt(n_eff - 3)
    return (float(np.tanh(zr - z * se)), float(np.tanh(zr + z * se)))


def logit_fit(X: np.ndarray, y: np.ndarray, l2: float = 1.0, iters: int = 50) -> np.ndarray:
    """Regresión logística con regularización L2 (Newton-IRLS). X incluye la columna de unos; no se penaliza."""
    w = np.zeros(X.shape[1])
    pen = np.full(X.shape[1], l2)
    pen[0] = 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(X @ w, -30, 30)))
        g = X.T @ (p - y) + pen * w
        Hm = (X * (p * (1 - p))[:, None]).T @ X + np.diag(pen) + 1e-9 * np.eye(len(w))
        step = np.linalg.solve(Hm, g)
        w -= step
        if np.max(np.abs(step)) < 1e-7:
            break
    return w


def _sig(z):
    return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


# ------------------------------------------------------------------ datos alineados
def puntajes(ticker: str, tf: str, provider: str = "yahoo", av_key: str = "", settings: dict | None = None) -> pd.DataFrame:
    """Puntaje técnico por vela y precio de cierre; índice = FIN de la vela (cuándo se conoce)."""
    raw = data.history_tf(ticker, tf, provider, av_key)
    d = compute_all(raw, settings)
    s = score_series(d)
    out = pd.DataFrame({"close": d["Close"], "score": s})
    idx = out.index
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert("America/New_York").tz_localize(None)
    out.index = idx + DURACION[tf]
    return out.dropna()


def tabla_mtf(ticker: str, tf: str, provider: str = "yahoo", av_key: str = "", settings: dict | None = None) -> pd.DataFrame:
    """Puntajes de la tríada alineados a las velas de la operativa con la última vela CERRADA de cada mayor."""
    tfs = MTF.triada(tf)
    base = puntajes(ticker, tf, provider, av_key, settings).rename(columns={"score": tf})
    base = base.reset_index().rename(columns={"index": "t"})
    base["t"] = pd.to_datetime(base["t"])
    for t in tfs[1:]:
        try:
            m = puntajes(ticker, t, provider, av_key, settings)[["score"]].rename(columns={"score": t})
        except Exception:
            continue
        m = m.reset_index().rename(columns={"index": "t"})
        m["t"] = pd.to_datetime(m["t"])
        base = pd.merge_asof(base.sort_values("t"), m.sort_values("t"), on="t", direction="backward")
    return base.set_index("t").dropna()


# ------------------------------------------------------------------ evaluación
def _metricas(score: np.ndarray, fwd: np.ndarray, prob: np.ndarray | None, h: int) -> dict:
    n = len(score)
    n_eff = n / max(h, 1)
    sel = np.abs(score) >= UMBRAL
    hit = (np.sign(score[sel]) == np.sign(fwd[sel])) & (fwd[sel] != 0)
    k, m_ = int(hit.sum()), int(sel.sum())
    m_eff = m_ / max(h, 1)
    acc = k / m_ if m_ else float("nan")
    lo, hi = wilson(round(acc * m_eff) if m_ else 0, m_eff)
    ic = spearman(score, fwd)
    ic_lo, ic_hi = fisher_ci(ic, n_eff)
    out = {"n": n, "n_efectivo": n_eff, "senales": m_, "acierto": acc, "acierto_lo": lo, "acierto_hi": hi,
           "ic": ic, "ic_lo": ic_lo, "ic_hi": ic_hi}
    if prob is not None:
        y = (fwd > 0).astype(float)
        brier = float(np.mean((prob - y) ** 2))
        base = float(np.mean(y))
        brier_b = float(np.mean((base - y) ** 2))
        out.update({"brier": brier, "brier_base": brier_b, "bss": 1 - brier / brier_b if brier_b else float("nan")})
    return out


def walk_forward_prob(X: np.ndarray, y: np.ndarray, inicio: int, bloque: int, h: int, l2: float = 1.0) -> np.ndarray:
    """Probabilidad fuera de muestra: para cada bloque, el modelo se ajusta solo con lo anterior (dejando un hueco
    de h velas para que ninguna etiqueta de entrenamiento mire dentro del bloque evaluado)."""
    p = np.full(len(y), np.nan)
    for a in range(inicio, len(y), bloque):
        tr = max(0, a - h)
        if tr < 50:
            continue
        w = logit_fit(X[:tr], y[:tr], l2)
        b = min(len(y), a + bloque)
        p[a:b] = _sig(X[a:b] @ w)
    return p


def _crudo(ticker: str, tf: str, horizontes_dias, provider, av_key, settings) -> dict:
    """Series fuera de muestra por horizonte para un activo: puntajes, probabilidades y retornos futuros."""
    T = tabla_mtf(ticker, tf, provider, av_key, settings)
    tfs = [t for t in MTF.triada(tf) if t in T.columns]
    bpd = TIMEFRAMES[tf]["bars_day"]
    close = T["close"].to_numpy(float)
    S = T[tfs].to_numpy(float) / 100.0
    out = {"tfs": tfs, "desde": T.index[0], "hasta": T.index[-1], "velas": len(T), "corr": T[tfs], "h": {}}
    for hd in horizontes_dias:
        h = max(1, int(round(hd * bpd * 7 / 5)))  # días de calendario → velas (≈ 5 sesiones por 7 días)
        if len(close) <= h + 150:
            continue
        fwd = np.full(len(close), np.nan)
        fwd[:-h] = close[h:] / close[:-h] - 1
        ok = np.isfinite(fwd)
        Sk, fk = S[ok], fwd[ok]
        y = (fk > 0).astype(float)
        inicio, bloque = int(len(y) * 0.4), max(h, len(y) // 20)
        w_k = MTF.pesos(hd, tfs)
        s_op = Sk[:, 0]
        s_mtf = Sk @ np.array([w_k[t] for t in tfs])
        ones = np.ones((len(y), 1))
        p_op = walk_forward_prob(np.hstack([ones, s_op[:, None]]), y, inicio, bloque, h)
        p_mk = walk_forward_prob(np.hstack([ones, s_mtf[:, None]]), y, inicio, bloque, h)
        p_rg = walk_forward_prob(np.hstack([ones, Sk]), y, inicio, bloque, h, l2=5.0)
        ev = np.isfinite(p_op) & np.isfinite(p_mk) & np.isfinite(p_rg)
        tr = len(y) - h
        w_full = logit_fit(np.hstack([ones[:tr], Sk[:tr]]), y[:tr], 5.0)[1:] if tr > 50 else np.full(len(tfs), np.nan)
        sig = np.sign(np.where(np.abs(Sk * 100) >= UMBRAL, Sk, 0))
        out["h"][hd] = {"h": h, "fwd": fk[ev], "s_op": s_op[ev], "s_mtf": s_mtf[ev],
                        "s_rg": (p_rg[ev] - 0.5) * 2, "p_op": p_op[ev], "p_mk": p_mk[ev], "p_rg": p_rg[ev],
                        "alin": (np.abs(sig.sum(axis=1)) == len(tfs))[ev], "w_curva": w_k, "w_logit": w_full}
    return out


def evaluar(tickers, tf: str, horizontes_dias=(1, 3, 7, 14, 30), provider: str = "yahoo", av_key: str = "",
            settings: dict | None = None, min_n_eff: float = 20) -> dict:
    """Evalúa uno o varios activos (los resultados se agrupan: más muestra, intervalos más estrechos)."""
    if isinstance(tickers, str):
        tickers = [tickers]
    crudos, errores = {}, {}
    for t in tickers:
        try:
            crudos[t] = _crudo(t, tf, horizontes_dias, provider, av_key, settings)
        except Exception as e:  # sin datos suficientes para ese activo
            errores[t] = str(e)
    if not crudos:
        raise RuntimeError("Ningún activo tuvo datos suficientes: " + "; ".join(f"{k}: {v}" for k, v in errores.items()))
    tfs = next(iter(crudos.values()))["tfs"]
    corr = pd.concat([c["corr"] for c in crudos.values() if c["tfs"] == tfs]).corr(method="spearman")
    res, calib = [], {}
    for hd in horizontes_dias:
        partes = [c["h"][hd] for c in crudos.values() if hd in c["h"] and c["tfs"] == tfs]
        if not partes:
            continue
        h = partes[0]["h"]
        cat = {k: np.concatenate([p_[k] for p_ in partes]) for k in ("fwd", "s_op", "s_mtf", "s_rg", "p_op", "p_mk",
                                                                       "p_rg", "alin")}
        if len(cat["fwd"]) / h < min_n_eff:
            continue
        fila = {"horizonte_dias": hd, "velas": h, "activos": len(partes)}
        for nombre, sk, pk in (("operativa", "s_op", "p_op"), ("mtf_curva", "s_mtf", "p_mk"), ("mtf_estimado", "s_rg", "p_rg")):
            fila[nombre] = _metricas(cat[sk] * 100, cat["fwd"], cat[pk], h)
        fila["pesos_curva"] = partes[0]["w_curva"]
        wl = np.nanmean(np.vstack([np.clip(p_["w_logit"], 0, None) for p_ in partes]), axis=0)
        fila["pesos_estimados"] = ({t: float(wl[i] / wl.sum()) for i, t in enumerate(tfs)} if np.nansum(wl) > 0
                                   else {t: None for t in tfs})
        al, op = cat["alin"], np.abs(cat["s_op"] * 100) >= UMBRAL
        fila["alineadas"] = _metricas(cat["s_op"][al] * 100, cat["fwd"][al], None, h) if al.sum() > 20 else None
        fila["no_alineadas"] = (_metricas(cat["s_op"][~al & op] * 100, cat["fwd"][~al & op], None, h)
                                if (~al & op).sum() > 20 else None)
        res.append(fila)
        pr, yy = cat["p_mk"], (cat["fwd"] > 0).astype(float)
        if len(pr) > 100:
            q = pd.qcut(pr, 10, duplicates="drop")
            calib[hd] = (pd.DataFrame({"p": pr, "y": yy, "q": q}).groupby("q", observed=True)
                         .agg(pred=("p", "mean"), obs=("y", "mean"), n=("y", "size")).reset_index(drop=True))
    c0 = list(crudos.values())
    return {"tickers": list(crudos), "errores": errores, "tf": tf, "tfs": tfs,
            "desde": str(min(c["desde"] for c in c0)), "hasta": str(max(c["hasta"] for c in c0)),
            "velas": sum(c["velas"] for c in c0), "horizontes": res, "correlacion": corr, "calibracion": calib}
