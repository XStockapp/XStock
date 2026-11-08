"""
Tablas de mercado (watchlist y resultados del escáner) al estilo de los rankings de CoinGecko:
logo, rendimiento por periodo con flechas de color, volumen, capitalización y mini gráfico.
Acciones y cripto usan columnas distintas. El botón "Personalizar" guarda las preferencias en el
perfil del usuario.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from . import market, profiles
from .ui import GREEN, MUTED, RED


def money_compact(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "—"
    a = abs(v)
    for div, suf in ((1e12, " T"), (1e9, " B"), (1e6, " M"), (1e3, " K")):
        if a >= div:
            return f"${v / div:,.2f}{suf}"
    return f"${v:,.0f}"


def price_fmt(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    if abs(v) >= 1 or v == 0:
        return f"${v:,.2f}"
    import math
    dec = min(10, max(4, -int(math.floor(math.log10(abs(v)))) + 3))  # 4 cifras significativas, sin notación científica
    return f"${v:.{dec}f}"


def perf_fmt(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{'▲' if v >= 0 else '▼'} {abs(v):.1f}%"


def perf_css(v) -> str:
    if v is None or pd.isna(v):
        return f"color: {MUTED}"
    return f"color: {GREEN if v >= 0 else RED}; font-weight: 600"


# ---------------------------------------------------------------- personalizar
def personalizar(kind: str, key: str, col=None, tecnicas: bool = True) -> dict:
    """Botón "Personalizar" con las opciones de columnas. Devuelve las preferencias vigentes y las
    guarda en el perfil cuando cambian."""
    S = profiles.merge_settings(st.session_state.get("technical_settings"))
    cur = market.prefs(S, kind)
    op = market.OPCIONES[kind]
    host = col or st
    with host.popover("⚙️ Personalizar", width="stretch"):
        st.markdown("**Rendimiento**")
        perf = st.pills("Rendimiento", op["perf"], selection_mode="multi", default=cur["perf"], key=f"{key}_perf",
                        label_visibility="collapsed")
        st.markdown("**Métricas**")
        met = st.pills("Métricas", op["metricas"], selection_mode="multi", default=cur["metricas"], key=f"{key}_met",
                       label_visibility="collapsed")
        tec = cur["tecnicas"]
        if tecnicas:
            st.markdown("**Indicadores y niveles**")
            tec = st.pills("Indicadores", op["tecnicas"], selection_mode="multi", default=cur["tecnicas"],
                           key=f"{key}_tec", label_visibility="collapsed")
        st.markdown("**Mini gráfico**")
        gr = st.segmented_control("Mini gráfico", op["grafico"], default=cur["grafico"], key=f"{key}_gr",
                                  label_visibility="collapsed") or cur["grafico"]
        st.markdown("**Filas**")
        filas = st.segmented_control("Filas", market.FILAS, default=cur["filas"], key=f"{key}_filas",
                                     label_visibility="collapsed") or cur["filas"]
    new = {"perf": [x for x in op["perf"] if x in (perf or [])], "metricas": [x for x in op["metricas"] if x in (met or [])],
           "tecnicas": [x for x in op["tecnicas"] if x in (tec or [])], "grafico": gr, "filas": int(filas)}
    if new != cur:
        try:
            profiles.save_user_view(settings=market.with_prefs(S, kind, new))
        except Exception:
            st.session_state.technical_settings = market.with_prefs(S, kind, new)
    return new


# ---------------------------------------------------------------- columnas
_TEC_COL = {"Fuerza relativa": "Fuerza relativa 3m"}
_CR_PERF_FALLBACK = {"24h": "Ret 1D", "7d": "Ret 7D", "30d": "Ret 1M", "1a": "Ret 1A"}


def columnas(df: pd.DataFrame, kind: str, p: dict, cm: dict | None = None) -> tuple[pd.DataFrame, dict, dict]:
    """Columnas de mercado para las filas de `df` (debe traer "Ticker" y, si viene del escáner, las
    columnas "Ret …" y "Spark"). Devuelve (columnas, column_config, formatos para el Styler).
    Las claves de los formatos: "perf", "money", "price", "ratio"."""
    cm = cm or {}
    t = df["Ticker"]
    out = pd.DataFrame(index=df.index)
    fm = {"perf": [], "money": [], "price": [], "ratio": []}
    cfg: dict = {}
    if kind == "cripto":
        g = lambda k: t.map(lambda x: (cm.get(x) or {}).get(k))  # noqa: E731
        out["Logo"] = g("logo").fillna("")
        out["Moneda"] = g("nombre").fillna(df.get("Nombre", t)).fillna(t)
        precio = g("precio")
        out["Precio"] = precio.fillna(df["Precio"]) if "Precio" in df else precio
        fm["price"].append("Precio")
        for k in p["perf"]:
            col = g(k)
            fb = _CR_PERF_FALLBACK.get(k)
            if fb and fb in df:
                col = col.fillna(df[fb])
            out[k] = col
            fm["perf"].append(k)
        for k in p["metricas"]:
            if k == "Volumen 24h":
                out[k] = g("volumen"); fm["money"].append(k)
            elif k == "Market cap":
                out[k] = g("cap"); fm["money"].append(k)
            elif k == "FDV":
                out[k] = g("fdv"); fm["money"].append(k)
            elif k == "Market cap / FDV":
                out[k] = g("cap_fdv"); fm["ratio"].append(k)
            elif k == "Ranking":
                out[k] = g("ranking")
                cfg[k] = st.column_config.NumberColumn("Rank", format="%d", width="small")
        if p["grafico"] != "Ninguno":
            sp = g("spark")
            if "Spark" in df:
                sp = [s if isinstance(s, list) and len(s) > 1 else market.spark_tail(fb_, "7D", "X-USD")
                      for s, fb_ in zip(sp, df["Spark"])]
            out["Últimos 7 días"] = list(sp)
            cfg["Últimos 7 días"] = st.column_config.LineChartColumn("Últimos 7 días", color="auto", width="medium")
    else:
        out["Logo"] = t.map(market.logo).fillna("")
        if "Precio" in df:
            out["Precio"] = df["Precio"]
            fm["price"].append("Precio")
        for k in p["perf"]:
            out[k] = df.get(f"Ret {k}")
            fm["perf"].append(k)
        for k in p["metricas"]:
            if k == "Volumen $" and "Vol. $ prom (M)" in df:
                out["Volumen $ (20d)"] = df["Vol. $ prom (M)"] * 1e6; fm["money"].append("Volumen $ (20d)")
            elif k == "Market cap" and "Market cap" in df and df["Market cap"].notna().any():
                out["Market cap"] = df["Market cap"]; fm["money"].append("Market cap")
            elif k == "Sector" and "Sector" in df:
                out["Sector"] = df["Sector"]
        if p["grafico"] != "Ninguno" and "Spark" in df:
            name = f"Últimos {p['grafico']}"
            out[name] = [market.spark_tail(s, p["grafico"], x) if s is not None else [] for s, x in zip(df["Spark"], t)]
            cfg[name] = st.column_config.LineChartColumn(name, color="auto", width="medium")
    for k in p.get("tecnicas", []):
        src = _TEC_COL.get(k, k)
        if src in df:
            out[k] = df[src]
    cfg["Logo"] = st.column_config.ImageColumn("", width=40)
    return out, cfg, fm


def aplicar_formatos(sty, fm: dict, cols, extra: dict | None = None) -> "pd.io.formats.style.Styler":
    perf = [c for c in fm["perf"] if c in cols]
    fmt = {c: perf_fmt for c in perf}
    fmt.update({c: money_compact for c in fm["money"] if c in cols})
    fmt.update({c: price_fmt for c in fm["price"] if c in cols})
    fmt.update({c: (lambda v: "—" if v is None or pd.isna(v) else f"{v:.2f}") for c in fm["ratio"] if c in cols})
    for c, f in (("Score técnico", "{:+.0f}"), ("Fuerza relativa", "{:.0f}"), ("RSI", "{:.0f}"), ("ADX", "{:.0f}"),
                 ("Vol. relativo", "{:.1f}x"), ("ATR %", "{:.1f}%"), ("Objetivo 2", "${:,.2f}")):
        if c in cols:
            fmt[c] = f
    fmt.update({k: v for k, v in (extra or {}).items() if k in cols})
    sty = sty.format(fmt, na_rep="—", subset=list(fmt))  # un solo formato por columna (llamadas sucesivas se pisan)
    if perf:
        sty = sty.map(perf_css, subset=perf)
    return sty


def es_cripto_scan(meta: dict, res: pd.DataFrame) -> bool:
    return str(meta.get("universo", "")).startswith("Cripto") or (
        len(res) > 0 and res["Ticker"].astype(str).str.endswith("-USD").mean() > 0.8)
