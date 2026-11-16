"""Velas de evento: detección de movimientos anómalos y su causa probable.

Detección (solo con precios, sin mirar el futuro: cada vela se compara con las 60 anteriores):
* retorno anormal: |z| ≥ 4, con z = retorno log / σ robusta (1.4826 × mediana de desviaciones absolutas);
* gap de apertura ≥ 2 ATR respecto al cierre anterior;
* |z| ≥ 3 con volumen ≥ 3 × el promedio de 20 sesiones.

Causa, en orden: resultados trimestrales/anuales (fechas de Yahoo), dividendo o split, movimiento de todo el mercado
(SPY) o del sector (ETF del sector) en la misma dirección, noticia de ±1 día (Alpaca News, que guarda historial; si
no, Yahoo), y si no hay nada, «sin causa identificada».

Uso: marcar las velas en el gráfico, avisar de un evento reciente (señales menos fiables) o de resultados próximos
(gap e IV crush en opciones), recortar el rango verdadero en el ATR y separar en el backtest las operaciones que
cruzan un evento.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import streamlit as st

from . import data

ETF_SECTOR = {"Semiconductors": "SMH", "Technology": "XLK", "Financial Services": "XLF", "Financial": "XLF",
              "Healthcare": "XLV", "Energy": "XLE", "Consumer Cyclical": "XLY", "Consumer Defensive": "XLP",
              "Industrials": "XLI", "Communication Services": "XLC", "Utilities": "XLU", "Real Estate": "XLRE",
              "Basic Materials": "XLB", "Tecnología": "XLK", "Finanzas": "XLF", "Salud": "XLV", "Energía": "XLE",
              "Consumo discrecional": "XLY", "Consumo básico": "XLP", "Industria": "XLI", "Comunicaciones": "XLC",
              "Servicios públicos": "XLU", "Inmobiliario": "XLRE", "Materiales": "XLB"}
Z_ANOM, GAP_ATR, VOL_X = 4.0, 2.0, 3.0


def detectar(d: pd.DataFrame, ventana: int = 60) -> pd.DataFrame:
    """Columnas: ret, z, gap_atr, vol_x, anomala (bool). Velas diarias con Open/High/Low/Close/Volume."""
    c = d["Close"].astype(float)
    r = np.log(c / c.shift(1))
    med = r.shift(1).rolling(ventana, min_periods=20).median()
    mad = (r.shift(1) - med).abs().rolling(ventana, min_periods=20).median()
    sig = 1.4826 * mad
    z = (r - med) / sig.replace(0, np.nan)
    tr = pd.concat([d["High"] - d["Low"], (d["High"] - c.shift()).abs(), (d["Low"] - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.shift(1).rolling(14, min_periods=5).mean()
    gap = (d["Open"] - c.shift(1)) / atr
    vol = d["Volume"].astype(float)
    vx = vol / vol.shift(1).rolling(20, min_periods=5).mean()
    an = (z.abs() >= Z_ANOM) | (gap.abs() >= GAP_ATR) | ((z.abs() >= 3) & (vx >= VOL_X))
    return pd.DataFrame({"ret": np.expm1(r), "z": z, "gap_atr": gap, "vol_x": vx, "anomala": an.fillna(False)})


def _fecha(x) -> date:
    t = pd.Timestamp(x)
    if t.tzinfo is not None:
        t = t.tz_convert("America/New_York")
    return t.date()


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fechas_resultados(ticker: str) -> list[str]:
    """Fechas (pasadas y futuras) de publicación de resultados según Yahoo Finance."""
    if data._demo():
        return []
    try:
        import yfinance as yf
        df = yf.Ticker(ticker).get_earnings_dates(limit=24)
        return sorted({_fecha(i).isoformat() for i in df.index}) if df is not None else []
    except Exception:
        return []


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def acciones_corporativas(ticker: str) -> dict:
    if data._demo():
        return {}
    try:
        import yfinance as yf
        a = yf.Ticker(ticker).actions
        out = {}
        for i, row in a.iterrows():
            if row.get("Stock Splits"):
                out[_fecha(i).isoformat()] = f"Split {row['Stock Splits']:g}:1"
            elif row.get("Dividends"):
                out[_fecha(i).isoformat()] = f"Dividendo ${row['Dividends']:.2f}"
        return out
    except Exception:
        return {}


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def noticias_dia(ticker: str, dia: str) -> list[dict]:
    """Titulares de ±1 día alrededor de `dia` (Alpaca News; guarda historial)."""
    if data._demo():
        return []
    try:
        from . import alpaca
        if not alpaca.available():
            return []
        d0 = date.fromisoformat(dia)
        import requests
        r = requests.get("https://data.alpaca.markets/v1beta1/news", headers=alpaca._headers(), timeout=20,
                         params={"symbols": ticker, "start": (d0 - timedelta(days=1)).isoformat() + "T00:00:00Z",
                                 "end": (d0 + timedelta(days=1)).isoformat() + "T23:59:59Z", "limit": 10,
                                 "sort": "desc"})
        r.raise_for_status()
        return [{"titulo": n.get("headline"), "fuente": n.get("source"), "link": n.get("url"),
                 "fecha": n.get("created_at", "")[:10], "simbolos": n.get("symbols") or []}
                for n in r.json().get("news", []) if n.get("headline")]
    except Exception:
        return []


def _relevante(ticker: str, items: list[dict]) -> dict | None:
    """El titular más específico: el que menciona solo a este símbolo, o el primero."""
    if not items:
        return None
    solo = [n for n in items if n.get("simbolos") == [ticker]]
    return (solo or items)[0]


@st.cache_data(ttl=3600, show_spinner=False)
def _serie_ret(sym: str) -> pd.Series:
    try:
        h = data.history_tf(sym, "1D")
        r = h["Close"].astype(float).pct_change()
        r.index = [_fecha(i) for i in h.index]
        return r
    except Exception:
        return pd.Series(dtype=float)


def analizar(ticker: str, d_diario: pd.DataFrame, sector: str = "", industria: str = "", dias: int = 400,
             con_noticias: bool = True) -> list[dict]:
    """Eventos de las últimas `dias` velas diarias con su causa probable (más reciente primero)."""
    det = detectar(d_diario).tail(dias)
    filas = det[det["anomala"]]
    if filas.empty:
        return []
    res_fechas = set(fechas_resultados(ticker))
    corp = acciones_corporativas(ticker)
    spy = _serie_ret("SPY") if ticker.upper() != "SPY" else pd.Series(dtype=float)
    etf = ETF_SECTOR.get(industria) or ETF_SECTOR.get(sector)
    sec = _serie_ret(etf) if etf and etf != ticker.upper() else pd.Series(dtype=float)
    out = []
    n_news = 0  # titulares solo para los 6 eventos más recientes (los que se muestran): una llamada de red por evento
    for i, row in filas.iloc[::-1].iterrows():
        f = _fecha(i)
        fs = f.isoformat()
        causa, tipo, titular = None, None, None
        cerca = {(f - timedelta(days=k)).isoformat() for k in (0, 1)}  # resultados tras el cierre se ven al día siguiente
        if res_fechas & cerca:
            causa, tipo = "Publicación de resultados", "resultados"
        elif fs in corp:
            causa, tipo = corp[fs], "corporativo"
        else:
            rm, rs = spy.get(f, np.nan), sec.get(f, np.nan)
            ret = row["ret"]
            if np.isfinite(rm) and abs(rm) >= 0.02 and np.sign(rm) == np.sign(ret):
                causa, tipo = f"Movimiento de todo el mercado (SPY {rm * 100:+.1f}%)", "mercado"
            elif np.isfinite(rs) and abs(rs) >= 0.5 * abs(ret) and abs(rs) >= 0.02 and np.sign(rs) == np.sign(ret):
                causa, tipo = f"Movimiento del sector ({etf} {rs * 100:+.1f}%)", "sector"
        if con_noticias and tipo in (None, "sector", "mercado") and n_news < 6:
            n_news += 1
            n = _relevante(ticker, noticias_dia(ticker, fs))
            if n:
                titular = n
                if tipo is None:
                    causa, tipo = "Noticia", "noticia"
        out.append({"fecha": fs, "ret": float(row["ret"]), "z": float(row["z"]) if np.isfinite(row["z"]) else None,
                    "gap_atr": float(row["gap_atr"]) if np.isfinite(row["gap_atr"]) else None,
                    "vol_x": float(row["vol_x"]) if np.isfinite(row["vol_x"]) else None,
                    "tipo": tipo or "sin_causa", "causa": causa or "Sin causa identificada",
                    "titular": titular, "cierre": float(d_diario.loc[i, "Close"])})
    return out


def proximos_resultados(ticker: str, hoy: date | None = None) -> date | None:
    hoy = hoy or datetime.now().date()
    fut = [date.fromisoformat(x) for x in fechas_resultados(ticker) if date.fromisoformat(x) >= hoy]
    return min(fut) if fut else None


def marcadores(eventos: list[dict], df: pd.DataFrame) -> list[dict]:
    """Ubica cada evento en la primera vela de su día dentro de `df` (cualquier temporalidad)."""
    if df is None or df.empty or not eventos:
        return []
    fechas = pd.Series([_fecha(i) for i in df.index], index=df.index)
    out = []
    for e in eventos:
        f = date.fromisoformat(e["fecha"])
        idx = fechas.index[fechas == f]
        if len(idx):
            i0 = idx[0]
            out.append({**e, "x": i0, "y": float(df.loc[idx, "Low"].min())})
    return out


def avisos(eventos: list[dict], d_diario: pd.DataFrame, prox_res: date | None, hoy: date | None = None) -> list[str]:
    """Advertencias para el análisis: evento en las últimas 5 sesiones y resultados en los próximos 14 días."""
    hoy = hoy or datetime.now().date()
    out = []
    if eventos and len(d_diario) >= 5:
        lim = _fecha(d_diario.index[-5])
        rec = [e for e in eventos if date.fromisoformat(e["fecha"]) >= lim]
        if rec:
            e = rec[0]
            out.append(f"Vela de evento reciente ({e['fecha']}, {e['ret'] * 100:+.1f}%: {e['causa'].lower()}). "
                       "Los indicadores de corto plazo todavía la incluyen; sus señales son menos fiables durante unas "
                       "sesiones y los soportes o resistencias que dejó el gap pesan menos.")
    if prox_res and 0 <= (prox_res - hoy).days <= 14:
        out.append(f"Resultados el {prox_res:%d/%m} (en {(prox_res - hoy).days} días): riesgo de gap que el análisis "
                   "técnico no anticipa. Ajusta el tamaño o espera a la publicación.")
    return out


def texto(e: dict) -> str:
    t = f"{e['fecha']} · {e['ret'] * 100:+.1f}% · {e['causa']}"
    if e.get("titular"):
        t += f" — {e['titular']['titulo']}"
    return t


def mascara_dias(d_diario: pd.DataFrame) -> set:
    """Fechas con vela de evento (solo precio), para separar operaciones en el backtest."""
    det = detectar(d_diario)
    return {_fecha(i) for i in det.index[det["anomala"]]}
