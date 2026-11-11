"""Estilo visual (tema terminal profesional) y gráficos."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

# Paleta del sistema de diseño (igual que .streamlit/config.toml)
BG, PANEL, BORDER = "#0D1117", "#161B22", "#30363D"
TXT, MUTED = "#E6EDF3", "#8B949E"
GREEN, RED, AMBER, BLUE, VIOLET = "#26A69A", "#EF5350", "#D29922", "#2962FF", "#A371F7"
ACCENT = "#2962FF"  # cobalto: solo estados activos, foco y acción principal
NEUTRAL = "#58A6FF"  # azul claro: mercado indeciso / pronóstico neutro

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');
html, body, [class*="css"], .stMarkdown, .stText {{ font-family: 'Inter', sans-serif; }}
.block-container {{ padding: 2.4rem 1.6rem 1.5rem 1.6rem; max-width: 100%; }}
h1, h2, h3 {{ letter-spacing: -0.01em; line-height: 1.3; }}
.stMarkdown p, .stCaption, [data-testid="stCaptionContainer"] {{ line-height: 1.5; }}
[data-testid="stSidebar"] {{ border-right: 1px solid {BORDER}; }}
code, .mono {{ font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; }}
.kpi {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px; padding: 8px 10px; height: 100%; }}
.kpi .lbl {{ color: {MUTED}; font-size: max(11px, 0.66rem); text-transform: uppercase; letter-spacing: .07em; }}
.kpi .val {{ font-family: 'JetBrains Mono', monospace; font-size: 1.1rem; font-weight: 600; margin-top: 2px; }}
.kpi .sub {{ color: {MUTED}; font-size: max(11px, 0.7rem); margin-top: 1px; }}
.pill {{ display:inline-block; padding: 2px 9px; border-radius: 999px; font-size: max(11px, .72rem); font-weight: 600; margin-right: 4px; }}
.brand {{ font-weight: 700; font-size: 1.1rem; letter-spacing: -.01em; }}
.brand span {{ color: {GREEN}; }}
.muted {{ color: {MUTED}; font-size: max(11px, .8rem); }}
.small {{ font-size: max(11px, .78rem); }}
.bigpx {{ font-family: 'JetBrains Mono', monospace; font-size: 1.4rem; font-weight: 600; }}
/* encabezado de la acción */
.qhead {{ display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; margin: 2px 0 4px; }}
.qhead .qt {{ font-size: 1.45rem; font-weight: 700; letter-spacing: -.02em; }}
.qhead .qpx {{ font-family: 'JetBrains Mono', monospace; font-size: 1.3rem; font-weight: 600; }}
.qhead .qch {{ font-family: 'JetBrains Mono', monospace; font-size: .95rem; }}
/* panel vertical de métricas */
.mp {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px 10px 8px; }}
.mp-h {{ color: {MUTED}; font-size: max(11px, .64rem); text-transform: uppercase; letter-spacing: .08em; margin: 8px 0 2px;
         border-bottom: 1px solid {BORDER}; padding-bottom: 2px; }}
.mp-h:first-child {{ margin-top: 2px; }}
.mp-r {{ display:flex; justify-content:space-between; align-items:baseline; gap:8px; font-size: max(11px, .8rem); padding: 2px 0; }}
.mp-r b {{ font-family: 'JetBrains Mono', monospace; font-size: .88rem; white-space: nowrap; }}
.mp-s {{ color: {MUTED}; font-size: max(11px, .68rem); margin: -2px 0 3px; line-height: 1.25; }}
/* informe IA */
.sec {{ font-size: max(11px, .72rem); text-transform: uppercase; letter-spacing: .08em; color: {MUTED}; font-weight: 600; padding-top: 6px; }}
.sec2 {{ font-size: max(11px, .7rem); text-transform: uppercase; letter-spacing: .07em; color: {MUTED}; font-weight: 600; margin: 8px 0 3px; }}
.rep p.lead {{ font-size: .92rem; margin: 6px 0 4px; line-height: 1.45; }}
.rep-b {{ background: #0D1117; border: 1px solid {BORDER}; border-radius: 6px; padding: 7px 9px; font-size: max(11px, .8rem); line-height: 1.45; height: 100%; }}
ul.tl {{ margin: 0; padding-left: 16px; font-size: max(11px, .8rem); line-height: 1.45; }}
ul.tl li {{ margin: 2px 0; }}
table.qt-tab {{ width: 100%; border-collapse: collapse; font-size: max(11px, .78rem); }}
table.qt-tab th {{ text-align: left; color: {MUTED}; font-weight: 500; font-size: max(11px, .66rem); text-transform: uppercase; letter-spacing: .05em;
                  border-bottom: 1px solid {BORDER}; padding: 4px 6px; }}
table.qt-tab td {{ border-bottom: 1px solid {BORDER}; padding: 4px 6px; vertical-align: top; }}
table.qt-tab td.n {{ font-family: 'JetBrains Mono', monospace; white-space: nowrap; }}
/* fundamentales clave */
.fr {{ display:grid; grid-template-columns: 10px 1fr auto; gap: 0 8px; align-items: baseline; padding: 3px 0; border-bottom: 1px dashed {BORDER}; }}
.fr .dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; }}
.fr .fm {{ font-size: max(11px, .8rem); font-weight: 600; }}
.fr .fv {{ font-family: 'JetBrains Mono', monospace; font-size: max(11px, .8rem); }}
.fr .fl {{ grid-column: 2 / 4; color: {MUTED}; font-size: max(11px, .7rem); line-height: 1.3; }}
.fr .fb {{ opacity: .7; }}
.verdict {{ border-radius: 10px; padding: 12px 14px; border: 1px solid {BORDER}; background: {PANEL}; }}
.verdict h2 {{ margin: 0 0 4px 0; font-size: 1.3rem; }}
.disclaimer {{ color: {MUTED}; font-size: max(11px, .68rem); border-top: 1px solid {BORDER}; padding-top: 6px; margin-top: 16px; }}
div[data-testid="stDataFrame"] {{ border: 1px solid {BORDER}; border-radius: 8px; }}
/* ocultar barra de Streamlit (Deploy, menú, íconos de GitHub) */
[data-testid="stToolbarActions"], [data-testid="stAppDeployButton"], [data-testid="stMainMenu"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], #MainMenu, footer, .viewerBadge_container__1QSob, [class*="viewerBadge"] {{ display: none !important; }}
header[data-testid="stHeader"] {{ background: transparent; height: 2.6rem; }}
.kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; }}
/* ---------- celular ---------- */
@media (max-width: 700px) {{
  html {{ font-size: 13px; }}
  .block-container {{ padding: 3.2rem 0.55rem 1rem 0.55rem !important; }}
  .qhead {{ gap: 6px; }}
  .qhead .qt {{ font-size: 1.2rem; }}
  .qhead .qpx {{ font-size: 1.1rem; }}
  .qhead .muted {{ width: 100%; font-size: max(11px, .72rem); }}
  .kpi {{ padding: 6px 8px; }}
  .kpi .val {{ font-size: .98rem; }}
  .mp {{ padding: 4px 8px 6px; }}
  .mp-cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0 14px; }}
  .mp-cols .mp-h {{ grid-column: 1 / -1; }}
  .rep p.lead {{ font-size: .88rem; }}
  table.qt-tab {{ display: block; overflow-x: auto; white-space: nowrap; }}
  div[data-testid="stHorizontalBlock"] {{ gap: .45rem !important; }}
  .stTabs [data-baseweb="tab-list"] {{ overflow-x: auto; flex-wrap: nowrap; }}
  .bias-top {{ flex-wrap: wrap; gap: 2px 10px; }}
}}
/* Campos: sin el aviso "Press Enter to apply · n/m" de Streamlit, que se encima con el texto en campos angostos */
[data-testid="InputInstructions"] {{ display: none !important; }}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{ font-size: max(11px, .8rem) !important; }}
/* ---------- análisis estilo terminal ---------- */
.num {{ font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }}
.x-chips {{ display: flex; gap: 6px; justify-content: flex-end; flex-wrap: wrap; padding-bottom: 2px; }}
.x-chip {{ display: inline-flex; align-items: center; gap: 6px; border: 1px solid {BORDER}; background: {PANEL};
  border-radius: 5px; padding: 3px 8px; font-size: 11px; font-weight: 600; letter-spacing: .04em; color: {TXT}; white-space: nowrap; }}
.x-chip i {{ width: 7px; height: 7px; border-radius: 50%; display: inline-block; }}
.x-delta {{ font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; font-size: 12.5px; font-weight: 600;
  border: 1px solid; border-radius: 4px; padding: 1px 6px; }}
.x-meta {{ font-size: 12px; }}
.x-strip {{ display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; border: 1px solid {BORDER}; background: {PANEL};
  border-radius: 6px; padding: 6px 10px; font-size: 12px; margin: 2px 0 8px; }}
.x-strip b {{ font-weight: 600; }}
.x-k {{ color: {MUTED}; text-transform: uppercase; letter-spacing: .06em; font-size: 11px; font-weight: 600; }}
.x-g {{ display: inline-flex; align-items: baseline; gap: 6px; white-space: nowrap; padding-right: 10px;
  margin-right: 2px; border-right: 1px solid {BORDER}; }}
.x-g:last-child {{ border-right: none; }}
.x-tb {{ display: flex; align-items: center; gap: 8px; font-size: 13px; flex-wrap: wrap; }}
.st-key-x_chartcard, .st-key-x_ai {{ background: {PANEL}; }}
.x-plan {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px; padding: 9px 11px 10px; margin-bottom: 8px; }}
.x-ph {{ display: flex; justify-content: space-between; align-items: center; gap: 6px; margin-bottom: 8px; font-size: 11px;
  white-space: nowrap;
  font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: {TXT}; }}
.x-badge {{ border: 1px solid; border-radius: 4px; padding: 2px 6px; font-size: 11px; letter-spacing: .04em; white-space: nowrap; }}
.x-state {{ border: 1px solid; border-radius: 6px; padding: 6px 8px; margin-bottom: 9px; font-size: 13px; background: {BG}; }}
.x-entry {{ display: grid; grid-template-columns: 1fr; gap: 6px; border: 1px solid {BORDER}; border-radius: 6px; padding: 8px;
  background: {BG}; }}
.x-big {{ font-size: 21px; font-weight: 700; color: {TXT}; line-height: 1.2; }}
.x-lvls {{ display: grid; gap: 3px; border-top: 1px solid {BORDER}; padding-top: 6px; }}
.x-lv {{ display: grid; grid-template-columns: 1fr auto; gap: 0 8px; font-size: 12px; align-items: baseline; }}
.x-lv b {{ font-size: 13px; }}
.x-lvs {{ grid-column: 1 / 3; color: {MUTED}; font-size: 11px; text-align: right; margin-top: -2px; }}
.x-size {{ display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; font-size: 12px; color: {MUTED};
  margin-top: 8px; }}
.x-size b {{ color: {TXT}; }}
/* pestañas tipo carpeta (informe del analista) */
.st-key-x_ai [role="tablist"] {{ gap: 3px; border-bottom: 1px solid {BORDER}; padding: 0 2px; }}
.st-key-x_ai [data-testid="stTab"] {{ border: 1px solid {BORDER}; border-bottom: none; border-radius: 6px 6px 0 0;
  padding: 6px 14px; background: {BG}; margin-bottom: -1px; color: {MUTED}; }}
.st-key-x_ai [data-testid="stTab"][aria-selected="true"] {{ background: {PANEL}; color: {TXT};
  box-shadow: inset 0 2px 0 {ACCENT}; border-bottom: 1px solid {PANEL}; }}
.st-key-x_ai [data-testid="stTab"] p {{ font-size: 12.5px; font-weight: 600; }}
.st-key-x_ai [data-testid="stTab"] > div[data-rac] {{ display: none; }}
/* pantalla del informe: entra desde la derecha */
.st-key-x_report_screen {{ animation: xslide .22s ease-out; border-left: 1px solid {BORDER}; padding-left: 12px; }}
@keyframes xslide {{ from {{ transform: translateX(48px); opacity: 0; }} to {{ transform: none; opacity: 1; }} }}
/* tarjetas didácticas */
.dd-intro {{ color: {MUTED}; font-size: 12px; margin: 6px 0 8px; }}
.dd-h {{ display: flex; align-items: center; gap: 6px; font-size: 12.5px; flex-wrap: wrap; }}
.dd-p {{ border: 1px solid; border-radius: 4px; padding: 0 5px; font-size: 11px; font-weight: 600; white-space: nowrap; }}
.dd-a {{ margin-left: auto; font-size: 12px; font-weight: 600; }}
.dd-q {{ color: {MUTED}; font-size: 11px; line-height: 1.35; margin: 3px 0 0; }}
.dd-l {{ font-size: 11.5px; line-height: 1.35; color: {TXT}; }}
.dd-card {{ border: 1px solid {BORDER}; border-radius: 8px; padding: 8px 10px; background: {BG}; margin-bottom: 8px; }}
.dd-bar {{ position: relative; height: 6px; border-radius: 3px; background: #21262D; margin: 6px 0 4px; }}
.dd-mid {{ position: absolute; left: 50%; top: -2px; width: 1px; height: 10px; background: {MUTED}; }}
.dd-fill {{ position: absolute; top: 0; height: 6px; border-radius: 3px; }}
.dd-ms {{ margin-top: 6px; display: grid; gap: 6px; }}
.dd-m {{ display: grid; grid-template-columns: 1fr auto; gap: 0 8px; font-size: 11.5px; }}
.dd-m .dd-bar {{ grid-column: 1 / 3; margin: 2px 0 0; height: 4px; }}
.dd-m .dd-fill {{ height: 4px; }}
.dd-mn {{ font-weight: 600; }}
.dd-ml {{ grid-column: 1 / 3; color: {MUTED}; font-size: 11px; line-height: 1.3; }}
/* Navegación lateral (estilo terminal): elementos planos, el activo resaltado; títulos de sección en versalitas */
[data-testid="stSidebarNav"] li:has(a[href$="/watchlist"]), [data-testid="stSidebarNav"] li:has(a[href$="/portafolio"]) {{ display: none; }}
[data-testid="stSidebarNavItems"] li {{ margin-bottom: 2px; }}
[data-testid="stSidebarNavLink"] {{ border: 1px solid transparent; border-radius: 6px; padding: 6px 10px; min-height: 34px;
  background: transparent; margin: 0; }}
[data-testid="stSidebarNavLink"]:hover {{ background: {PANEL}; }}
[data-testid="stSidebarNavLink"][aria-current="page"] {{ border-color: {BORDER}; background: {PANEL};
  box-shadow: inset 2px 0 0 {ACCENT}; }}
[data-testid="stSidebarNavLink"] span {{ font-size: 13px !important; font-weight: 500; color: {TXT} !important; }}
[data-testid="stSidebarNavLink"][aria-current="page"] span {{ font-weight: 600; }}
[data-testid="stNavSectionHeader"] {{ border: none; padding-left: 10px; font-size: 11px; color: {MUTED};
  text-transform: uppercase; letter-spacing: .08em; font-weight: 600; margin-top: 6px; }}
.x-status {{ display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: center; border-top: 1px solid {BORDER};
  padding: 8px 2px 2px; margin-top: 10px; font-size: 11px; color: {MUTED}; font-family: 'JetBrains Mono', monospace; }}
.x-status i {{ width: 7px; height: 7px; border-radius: 50%; display: inline-block; margin-right: 4px; }}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def color_for(v: float, good=0, bad=0) -> str:
    return GREEN if v > good else (RED if v < bad else NEUTRAL)


def kpi(col, label: str, value: str, sub: str = "", color: str = TXT):
    col.markdown(f"<div class='kpi'><div class='lbl'>{label}</div>"
                 f"<div class='val' style='color:{color}'>{value}</div>"
                 f"<div class='sub'>{sub}</div></div>", unsafe_allow_html=True)


def pill(text: str, color: str) -> str:
    return f"<span class='pill' style='background:{color}22;color:{color};border:1px solid {color}55'>{text}</span>"


SIGNAL_COLORS = {"COMPRA FUERTE": GREEN, "COMPRA": "#4ade80", "REBOTE (contratendencia)": AMBER,
                 "NEUTRAL": NEUTRAL, "EVITAR / VENTA": RED, "COMPRAR": GREEN, "ESPERAR": NEUTRAL,
                 "VENTA FUERTE": RED, "VENTA": "#f87171",
                 "EVITAR": RED, "VENDER EN CORTO": RED}


def _tag(fig, y, text, color, row=1, size=10.5):
    """Etiqueta de precio estilo TradingView en el eje derecho."""
    fig.add_annotation(xref="paper", x=1.0, xanchor="left", yref="y" if row == 1 else f"y{row}", y=y,
                       text=f"<b>{text}</b>", showarrow=False, font=dict(color="#0D1117", size=size),
                       bgcolor=color, borderpad=2, opacity=0.95)


BY_DRAW: dict[str, str] = {}


def _rgba_hex(c: str, o: float) -> str:
    c = c.lstrip("#")
    if len(c) != 6:
        return c
    return f"rgba({int(c[0:2], 16)},{int(c[2:4], 16)},{int(c[4:6], 16)},{max(0, min(1, o)):.2f})"


_DASH = {"solid": None, "dashed": "dash", "dotted": "dot"}


def _ln(st_: dict, w_extra: float = 0) -> dict:
    return dict(color=_rgba_hex(st_["c"], st_["o"] / 100), width=float(st_["w"]) + w_extra, dash=_DASH.get(st_["s"]))


def price_chart(d: pd.DataFrame, plan: dict | None = None, vp: dict | None = None, verdict: dict | None = None,
                bars: int = 180, times: dict | None = None, show_bb: bool = False, show_vp: bool = True,
                mobile: bool = False, tf: str = "1D", crypto: bool = False, settings: dict | None = None,
                ind: dict | None = None) -> go.Figure:
    """Gráfico de precio con el plan de operación y los indicadores activos del panel del usuario
    (menú USER › Indicadores): cada uno con su color, opacidad, grosor y tipo de línea; un panel
    inferior por cada oscilador activo."""
    import numpy as np

    from . import indicators as I
    from .timeframes import future_index, rangebreaks
    if not BY_DRAW:
        BY_DRAW.update({c["id"]: c.get("draw") for c in I.CATALOGO})
    settings = settings or d.attrs.get("settings") or {}
    if ind is None:
        ind = I.merge_config((settings or {}).get("indicadores"), None, settings or None)
        if show_bb:
            ind["bb"]["on"] = True
        if not show_vp:
            ind["vrvp"]["on"] = False
    act = I.activos(ind, tf)
    full = d
    d = d.tail(bars)
    x = d.index
    fx = lambda n: future_index(x[-1], n, tf, crypto)  # fecha de la vela n en el futuro

    # paneles inferiores: un oscilador por panel, en el orden del catálogo
    panes = []
    for iid in act:
        if BY_DRAW.get(iid) == "pane" and iid != "vol":
            pn = I.pane(full, iid, ind[iid]["in"])
            if pn:
                panes.append((iid, pn))
    n_rows = 1 + len(panes)
    pane_h = 0.15 if len(panes) <= 3 else 0.11
    price_h = max(0.42, 1 - pane_h * len(panes))
    heights = [price_h] + [(1 - price_h) / len(panes)] * len(panes) if panes else [1.0]
    fig = make_subplots(rows=n_rows, cols=1, shared_xaxes=True, vertical_spacing=0.018, row_heights=heights,
                        specs=[[{"secondary_y": True}]] + [[{}] for _ in panes])

    # --- Volumen superpuesto en la parte baja del precio (como TradingView) ---
    if "vol" in act:
        sv = ind["vol"]["st"]
        p_vol = ind["vol"]["in"]
        up_ = (d["Close"] >= d["Close"].shift()) if p_vol.get("col") else (d["Close"] >= d["Open"])
        vc = np.where(up_, _rgba_hex(sv["up"]["c"], sv["up"]["o"] / 100 * 0.6), _rgba_hex(sv["dn"]["c"], sv["dn"]["o"] / 100 * 0.6))
        if sv["up"]["v"] or sv["dn"]["v"]:
            fig.add_trace(go.Bar(x=x, y=d["Volume"], marker_color=vc, name="Volumen", showlegend=False,
                                 hovertemplate="Vol %{y:,.0f}<extra></extra>"), 1, 1, secondary_y=True)
        if sv["ma"]["v"]:
            fig.add_trace(go.Scatter(x=x, y=d["Volume"].rolling(int(I._num(p_vol.get("mal"), 20))).mean(), line=_ln(sv["ma"]),
                                     showlegend=False, hoverinfo="skip"), 1, 1, secondary_y=True)
    fig.add_trace(go.Candlestick(x=x, open=d["Open"], high=d["High"], low=d["Low"], close=d["Close"], name="Precio",
                                 increasing=dict(line=dict(color=GREEN, width=1), fillcolor=GREEN),
                                 decreasing=dict(line=dict(color=RED, width=1), fillcolor=RED)), 1, 1)

    # --- Indicadores sobre el precio ---
    ov_vals = []
    for iid in act:
        if BY_DRAW.get(iid) != "ov" or iid in ("vrvp", "fib"):
            continue
        st_all = ind[iid]["st"]
        for e in I.overlay(full, iid, ind[iid]["in"], tf):
            sty = st_all.get(e["plot"])
            if not sty or not sty["v"]:
                continue
            k = e["kind"]
            if k in ("line", "step"):
                y = e["y"].reindex(x)
                fig.add_trace(go.Scatter(x=x, y=y, name=e.get("label") or I.BYID[iid]["name"], line=_ln(sty),
                                         line_shape="hv" if k == "step" else "linear", connectgaps=False,
                                         showlegend=bool(e.get("label")), hovertemplate="%{y:.2f}<extra>" + (e.get("label") or "") + "</extra>"), 1, 1)
                ov_vals.append(y)
            elif k == "band":
                up, dn = e["up"].reindex(x), e["dn"].reindex(x)
                fig.add_trace(go.Scatter(x=x, y=up, line=dict(width=0), showlegend=False, hoverinfo="skip"), 1, 1)
                fig.add_trace(go.Scatter(x=x, y=dn, line=dict(width=0), fill="tonexty", showlegend=False, hoverinfo="skip",
                                         fillcolor=_rgba_hex(sty["c"], sty["o"] / 100)), 1, 1)
            elif k == "cloud":
                a, b = e["a"].reindex(x), e["b"].reindex(x)
                m = (a >= b) if e["up"] else (a < b)
                top, bot = np.where(m, np.maximum(a, b), np.nan), np.where(m, np.minimum(a, b), np.nan)
                fig.add_trace(go.Scatter(x=x, y=top, line=dict(width=0), showlegend=False, hoverinfo="skip", connectgaps=False), 1, 1)
                fig.add_trace(go.Scatter(x=x, y=bot, line=dict(width=0), fill="tonexty", showlegend=False, hoverinfo="skip",
                                         connectgaps=False, fillcolor=_rgba_hex(sty["c"], sty["o"] / 100)), 1, 1)
                ov_vals += [pd.Series(top, index=x), pd.Series(bot, index=x)]
            elif k == "marks":
                y = e["y"].reindex(x)
                fig.add_trace(go.Scatter(x=x, y=y, mode="markers", name=e.get("label"), showlegend=bool(e.get("label")),
                                         marker=dict(size=2 + 1.5 * float(sty["w"]), color=_rgba_hex(sty["c"], sty["o"] / 100)),
                                         hovertemplate="SAR %{y:.2f}<extra></extra>"), 1, 1)
                ov_vals.append(y)
    if "fib" in act:
        fv = I.fib_levels(full, ind["fib"]["in"])
        sl_, sg_ = ind["fib"]["st"]["lv"], ind["fib"]["st"]["golden"]
        x0f = x[0] if ind["fib"]["in"].get("ext") or fv["x0"] < x[0] else fv["x0"]
        lv = dict(fv["levels"])
        if sg_["v"]:
            fig.add_shape(type="rect", x0=x0f, x1=x[-1], y0=lv[0.5], y1=lv[0.618], line_width=0,
                          fillcolor=_rgba_hex(sg_["c"], sg_["o"] / 100), row=1, col=1)
        if sl_["v"]:
            for k_, y_ in fv["levels"]:
                fig.add_shape(type="line", x0=x0f, x1=x[-1], y0=y_, y1=y_, line=_ln(sl_), row=1, col=1)
                if ind["fib"]["in"].get("lbl", True) and not mobile:
                    fig.add_annotation(x=x0f, y=y_, xanchor="left", yanchor="bottom", showarrow=False,
                                       text=f"{k_:.3g} ({y_:,.2f})", font=dict(size=9, color=_rgba_hex(sl_["c"], 0.9)), row=1, col=1)

    last_x, last_px = x[-1], float(d["Close"].iloc[-1])
    lo, hi = float(d["Low"].min()), float(d["High"].max())
    x_end = last_x
    if plan:
        e, sl, t1, t2, atr = plan["entrada"], plan["stop"], plan["objetivo_1"], plan["objetivo_2"], plan["atr"]
        s1 = (times or {}).get("sesiones_a_objetivo_1") or 10
        s2 = (times or {}).get("sesiones_a_objetivo_2") or max(s1 + 5, 18)
        x_end = fx(int(s2) + 3)
        limit = plan.get("modo_entrada") == "limit"
        # Entrada a mercado: la caja nace en el cierre actual. Entrada proyectada (Limit): la caja se desplaza
        # al futuro, a partir de la sesión en que se espera el retroceso al soporte.
        x0 = fx(2) if limit else x[max(0, len(x) - 6)]
        # zonas sombreadas: beneficio (verde) y riesgo (rojo)
        fig.add_shape(type="rect", x0=x0, x1=x_end, y0=e, y1=t2, fillcolor="rgba(34,197,94,0.10)", line_width=0, row=1, col=1)
        fig.add_shape(type="rect", x0=x0, x1=x_end, y0=e, y1=t1, fillcolor="rgba(34,197,94,0.12)", line_width=0, row=1, col=1)
        fig.add_shape(type="rect", x0=x0, x1=x_end, y0=sl, y1=e, fillcolor="rgba(239,68,68,0.16)", line_width=0, row=1, col=1)
        # zona de compra (±0.3 ATR alrededor de la entrada)
        fig.add_shape(type="rect", x0=x0, x1=x_end, y0=e - 0.3 * atr, y1=e + 0.3 * atr,
                      fillcolor="rgba(96,165,250,0.18)", line=dict(color="rgba(96,165,250,0.5)", width=1), row=1, col=1)
        fig.add_annotation(x=x0, y=e + 0.3 * atr, xanchor="left", yanchor="bottom",
                           text="" if mobile else ("ZONA DE ENTRADA PROYECTADA (LIMIT)" if limit else "ZONA DE ENTRADA (A MERCADO)"),
                           showarrow=False, font=dict(size=10, color="#93c5fd"), row=1, col=1)
        if limit:
            # retroceso esperado: del cierre actual hasta la zona de entrada
            fig.add_annotation(x=x0, y=e, ax=last_x, ay=last_px, xref="x", yref="y", axref="x", ayref="y",
                               showarrow=True, arrowhead=2, arrowsize=1.1, arrowwidth=1.4, arrowcolor="#fbbf24",
                               text="")
        if plan.get("estado"):
            wait = plan.get("estado_tipo") == "esperar"
            fig.add_annotation(xref="paper", yref="paper", x=0.005, y=0.995, xanchor="left", yanchor="top",
                               text=("⏳ " if wait else "✅ ") + plan["estado"] + ("" if mobile else "  ·  " + plan.get("marco_corto", "")),
                               showarrow=False, font=dict(size=11 if mobile else 12, color="#0D1117"),
                               bgcolor="#fbbf24" if wait else "#22c55e", borderpad=4)
        # trayectoria proyectada
        px_path = [last_px] + ([e] if abs(e - last_px) > 0.15 * atr else []) + [t1, t2]
        xs = [last_x] + ([fx(2)] if len(px_path) == 4 else [])
        xs += [fx(int(s1)), fx(int(s2))]
        fig.add_trace(go.Scatter(x=xs, y=px_path, mode="lines+markers", name="Proyección",
                                 line=dict(color="#93c5fd", width=2, dash="dot"),
                                 marker=dict(size=[4] * (len(xs) - 1) + [9], symbol=["circle"] * (len(xs) - 1) + ["triangle-up" if t2 > e else "triangle-down"]),
                                 hovertemplate="%{x|%d-%b}: %{y:.2f}<extra>Proyección</extra>"), 1, 1)
        fig.add_annotation(x=xs[-2], y=t1, text=f"TP1 ~{int(s1)} ses.", showarrow=False, yshift=12,
                           font=dict(size=10, color="#86efac"), row=1, col=1)
        fig.add_annotation(x=xs[-1], y=t2, text=f"TP2 ~{int(s2)} ses.", showarrow=False, yshift=12,
                           font=dict(size=10, color="#86efac"), row=1, col=1)
        # líneas horizontales + etiquetas de precio
        for y, lbl, c, dash, wdt in ((e, ("E" if mobile else ("LIMIT" if limit else "ENTRADA")), "#60a5fa", "dash" if limit else "solid", 1.6),
                                     (sl, "SL" if mobile else "STOP", "#ef4444", "solid", 1.6),
                                     (t1, "TP1", "#22c55e", "dash", 1.3), (t2, "TP2", "#22c55e", "dash", 1.3)):
            fig.add_hline(y=y, line=dict(color=c, width=wdt, dash=dash), row=1, col=1)
            _tag(fig, y, f"{lbl} {y:,.2f}", c, size=9 if mobile else 10.5)
        for lv, n in plan.get("soportes", [])[:3]:
            fig.add_hline(y=lv, line=dict(color="rgba(38,166,154,0.45)", width=1, dash="dot"), row=1, col=1)
        for lv, n in plan.get("resistencias", [])[:3]:
            fig.add_hline(y=lv, line=dict(color="rgba(239,83,80,0.45)", width=1, dash="dot"), row=1, col=1)
        # niveles de la IA si difieren
        if verdict and verdict.get("entrada") and abs(float(verdict["entrada"]) / e - 1) > 0.003:
            for key, lbl, c in (("entrada", "IA E", "#60a5fa"), ("stop", "IA SL", "#ef4444"), ("objetivo_1", "IA TP1", "#22c55e")):
                if verdict.get(key):
                    fig.add_hline(y=float(verdict[key]), line=dict(color=c, width=1, dash="dashdot"), row=1, col=1)
        lv_all = [e, sl, t1, t2]
        lo, hi = min([lo] + lv_all), max([hi] + lv_all)
    # --- Perfil de volumen (VRVP) con POC y área de valor ---
    vp_axis, wpct, pv = None, 100.0, {}
    if "vrvp" in act and vp and len(vp.get("precios", [])):
        sv, pv = ind["vrvp"]["st"], ind["vrvp"]["in"]
        pr = np.asarray(vp["precios"], float)
        in_va = (pr >= vp["val"]) & (pr <= vp["vah"])
        mode = pv.get("volm", "Arriba/Abajo")
        up_v, dn_v = np.asarray(vp["up"], float), np.asarray(vp["down"], float)
        tot = up_v + dn_v
        col = lambda k_va, k_out: [_rgba_hex(sv[k_va if va else k_out]["c"], sv[k_va if va else k_out]["o"] / 100) for va in in_va]  # noqa: E731
        if mode == "Total":
            fig.add_trace(go.Bar(y=pr, x=tot, orientation="h", width=vp["alto_bin"] * 0.92, xaxis="x20", yaxis="y",
                                 marker_color=col("vaup", "upv"), name="VRVP", hovertemplate="%{y:.2f}: %{x:,.0f}<extra>Volumen</extra>"))
            ref = tot
        elif mode == "Delta":
            dl = up_v - dn_v
            colors = [_rgba_hex(sv[("vaup" if va else "upv") if v >= 0 else ("vadn" if va else "dnv")]["c"],
                                sv[("vaup" if va else "upv") if v >= 0 else ("vadn" if va else "dnv")]["o"] / 100)
                      for v, va in zip(dl, in_va)]
            fig.add_trace(go.Bar(y=pr, x=np.abs(dl), orientation="h", width=vp["alto_bin"] * 0.92, xaxis="x20", yaxis="y",
                                 marker_color=colors, name="VRVP", hovertemplate="%{y:.2f}: %{x:,.0f}<extra>Delta</extra>"))
            ref = np.abs(dl)
        else:  # Arriba/Abajo: barra total (abajo) con la parte compradora encima
            fig.add_trace(go.Bar(y=pr, x=tot, orientation="h", width=vp["alto_bin"] * 0.92, xaxis="x20", yaxis="y",
                                 marker_color=col("vadn", "dnv"), name="VRVP", hovertemplate="%{y:.2f}: %{x:,.0f}<extra>Vol. total</extra>"))
            fig.add_trace(go.Bar(y=pr, x=up_v, orientation="h", width=vp["alto_bin"] * 0.92, xaxis="x20", yaxis="y",
                                 marker_color=col("vaup", "upv"), showlegend=False, hovertemplate="%{y:.2f}: %{x:,.0f}<extra>Vol. comprador</extra>"))
            ref = tot
        wpct = max(5.0, min(100.0, I._num(pv.get("width"), 30)))
        span = float(np.nanmax(ref) or 1) * 100 / wpct
        vp_axis = dict(overlaying="x", anchor="y", range=[span, 0] if pv.get("place", "Derecha") != "Izquierda" else [0, span],
                       autorange=False, visible=False, fixedrange=True, showgrid=False)
        if sv["poc"]["v"]:
            fig.add_hline(y=vp["poc"], line=_ln(sv["poc"]), row=1, col=1)
            fig.add_annotation(xref="paper", x=0.775, xanchor="right", yref="y", y=vp["poc"], text=f"<b>POC {vp['poc']:,.2f}</b>",
                               showarrow=False, font=dict(size=10, color="#0D1117"), bgcolor=sv["poc"]["c"], borderpad=2)
        for k in ("vah", "val"):
            fig.add_hline(y=vp[k], line=dict(color=_rgba_hex(sv["vaup"]["c"], 0.55), width=1, dash="dash"), row=1, col=1)
            fig.add_annotation(xref="paper", x=0.775, xanchor="right", yref="y", y=vp[k], text=k.upper(), showarrow=False,
                               font=dict(size=9, color=MUTED), yshift=7)
    if not plan or abs(plan["entrada"] - last_px) > 0.25 * plan["atr"]:
        _tag(fig, last_px, f"{last_px:,.2f}", TXT)

    # --- Paneles inferiores ---
    for r_, (iid, pn) in enumerate(panes, start=2):
        st_all = ind[iid]["st"]
        first = next((st_all[k] for k, _ in pn["lines"] if st_all.get(k, {}).get("v")), None)
        if pn.get("zone"):
            fs = st_all.get(pn.get("fill") or "")
            if fs is None:
                zc = first["c"] if first else MUTED
                fig.add_hrect(y0=pn["zone"][0], y1=pn["zone"][1], fillcolor=_rgba_hex(zc, 0.08), line_width=0, row=r_, col=1, exclude_empty_subplots=False)
            elif fs["v"]:
                fig.add_hrect(y0=pn["zone"][0], y1=pn["zone"][1], fillcolor=_rgba_hex(fs["c"], fs["o"] / 100), line_width=0,
                              row=r_, col=1, exclude_empty_subplots=False)
        bs = st_all.get(pn.get("bands") or "")
        if bs is None or bs["v"]:
            bl = _ln(bs) if bs else dict(color="rgba(139,148,158,.45)", width=1, dash="dot")
            for lvl in pn.get("refs", []):
                fig.add_hline(y=lvl, line=bl, row=r_, col=1, exclude_empty_subplots=False)
        if pn.get("dots") is not None:
            keys = pn["dots"].reindex(x).fillna("")
            for k_ in ("sqon", "sqoff"):
                sd_ = st_all.get(k_)
                m_ = keys == k_
                if sd_ and sd_["v"] and m_.any():
                    fig.add_trace(go.Scatter(x=x[m_.to_numpy()], y=[0] * int(m_.sum()), mode="markers", showlegend=False,
                                             marker=dict(size=3 + float(sd_["w"]), color=_rgba_hex(sd_["c"], sd_["o"] / 100),
                                                         symbol="x" if k_ == "sqon" else "circle"),
                                             hoverinfo="skip"), r_, 1)
        for kind in ("bull", "bear"):
            sk = st_all.get(kind)
            segs = [s_ for s_ in pn.get("divs", []) if s_[4] == kind and s_[0] >= x[0]]
            if sk and sk["v"] and segs:
                xs, ys = [], []
                for t1, v1, t2, v2, _ in segs:
                    xs += [t1, t2, None]
                    ys += [v1, v2, None]
                fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=_ln(sk), showlegend=False, hoverinfo="skip",
                                         connectgaps=False), r_, 1)
        if pn.get("hist"):
            hk, hs = pn["hist"]
            sth = st_all.get(hk)
            hv = hs.reindex(x)
            if pn.get("hcols") is not None:  # histograma de varios colores (cada barra indica su estilo)
                keys = pn["hcols"].reindex(x).fillna("")
                hc = [(_rgba_hex(st_all[k_]["c"], st_all[k_]["o"] / 100) if k_ in st_all and st_all[k_]["v"]
                       else "rgba(0,0,0,0)") for k_ in keys]
                fig.add_trace(go.Bar(x=x, y=hv, marker_color=hc, marker_line_width=0, showlegend=False,
                                     hovertemplate="%{y:.2f}<extra></extra>"), r_, 1)
            elif sth and sth["v"]:
                hc = np.where(hv >= 0, _rgba_hex(sth["c"], sth["o"] / 100), _rgba_hex(RED, sth["o"] / 100))
                fig.add_trace(go.Bar(x=x, y=hv, marker_color=hc, showlegend=False, hovertemplate="%{y:.2f}<extra></extra>"), r_, 1)
        for k, ser in pn["lines"]:
            sty = st_all.get(k)
            if sty and sty["v"]:
                fig.add_trace(go.Scatter(x=x, y=ser.reindex(x), line=_ln(sty), showlegend=False, name=k,
                                         hovertemplate="%{y:.2f}<extra>" + k.upper() + "</extra>"), r_, 1)
        if pn.get("range"):
            fig.update_yaxes(range=list(pn["range"]), row=r_, col=1)
        fig.add_annotation(xref="paper", x=0.002, xanchor="left", yref=f"y{r_ + 1} domain", y=0.97, text=pn["title"],
                           showarrow=False, font=dict(size=10, color=MUTED))

    vals = [v for v in ov_vals if v is not None]
    if vals:
        allv = pd.concat(vals, axis=1)
        lo, hi = min(lo, float(np.nanmin(allv.values))), max(hi, float(np.nanmax(allv.values)))
    pad = (hi - lo) * 0.05
    n_leg = sum(1 for t in fig.data if t.showlegend is not False and t.name)
    leg_rows = max(1, -(-n_leg // 7))  # ~7 entradas por línea de leyenda
    top = 6 if mobile else 10 + 20 * leg_rows
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
                      height=(560 if mobile else 600) + (110 if mobile else 140) * len(panes) + top,
                      margin=dict(l=2, r=86 if mobile else 92, t=top, b=6 if mobile else 26), xaxis_rangeslider_visible=False, barmode="overlay",
                      showlegend=not mobile,
                      hovermode="x unified", dragmode=False if mobile else "pan", bargap=0.15,
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, font=dict(size=10), bgcolor="rgba(0,0,0,0)",
                                  traceorder="normal"),
                      font=dict(family="Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif", color=TXT, size=11))
    x_right = max(x_end, fx(max(2, int(len(x) * 0.03))))
    if plan and vp_axis and pv.get("place", "Derecha") != "Izquierda" and wpct <= 60:
        # deja libre la franja del VRVP: el pronóstico termina antes de que empiece el perfil
        fut = int((times or {}).get("sesiones_a_objetivo_2") or 18) + 3
        total = (len(x) + fut) / max(0.3, 1 - wpct / 100 - 0.03)
        x_right = max(x_right, fx(int(np.ceil(total - len(x)))))
    for r_ in range(1, n_rows + 1):
        fig.update_xaxes(gridcolor="#1C2128", rangebreaks=rangebreaks(tf, crypto), showspikes=True, spikecolor="#484F58",
                         spikethickness=1, range=[x[0], x_right], row=r_, col=1)
    if vp_axis:
        fig.update_layout(xaxis20=vp_axis)
    fig.update_yaxes(gridcolor="#1C2128", side="right", tickfont=dict(size=10, family="JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"))
    fig.update_yaxes(range=[lo - pad, hi + pad], row=1, col=1, secondary_y=False)
    fig.update_yaxes(range=[0, float(d["Volume"].max()) * 4], visible=False, fixedrange=True, row=1, col=1, secondary_y=True)
    return fig


def projection_chart(d: pd.DataFrame, plan: dict, times: dict | None, vpa: dict | None, bars: int = 120,
                     tf: str = "1D", crypto: bool = False, mobile: bool = False) -> go.Figure:
    """Gráfico simplificado de proyección: precio en línea, niveles clave y la trayectoria esperada
    (precio actual → entrada → TP1 → TP2) con las zonas de riesgo y beneficio."""
    from .timeframes import future_index, rangebreaks
    t = d.tail(max(30, bars))
    x = t.index
    fx = lambda n: future_index(x[-1], n, tf, crypto)
    last = float(t["Close"].iloc[-1])
    long = "COMPRA" in str(plan.get("direccion", "")).upper()
    ent, stp, tp1, tp2 = (float(plan[k]) for k in ("entrada", "stop", "objetivo_1", "objetivo_2"))
    limit = plan.get("modo_entrada") == "limit"
    n1 = int((times or {}).get("sesiones_a_objetivo_1") or 10)
    n2 = max(n1 + 2, int((times or {}).get("sesiones_a_objetivo_2") or 18))
    ne = max(2, round(n1 * 0.3)) if limit else 0
    xe, x1, x2 = (fx(ne) if ne else x[-1]), fx(ne + n1), fx(ne + n2)
    x_end = fx(ne + n2 + max(6, int(len(x) * 0.14)))

    fig = go.Figure()
    smooth = t["Close"].ewm(span=3, adjust=False).mean()
    lo = float(min(t["Low"].min(), stp, tp2 if not long else stp, ent))
    hi = float(max(t["High"].max(), tp2 if long else stp, ent))
    pad = (hi - lo) * 0.12
    # área bajo el precio (degradado sutil) y línea suavizada
    fig.add_trace(go.Scatter(x=x, y=[lo - pad] * len(x), mode="lines", line=dict(width=0), hoverinfo="skip",
                             showlegend=False))
    fig.add_trace(go.Scatter(x=x, y=smooth, mode="lines", line=dict(color="#C9D1D9", width=2.2, shape="spline", smoothing=0.8),
                             fill="tonexty", fillgradient=dict(type="vertical", colorscale=[[0, "rgba(41,98,255,0)"],
                                                                                            [1, "rgba(41,98,255,.16)"]]),
                             name="Precio", hovertemplate="%{y:$,.2f}<extra></extra>"))
    if "EMA21" in t:
        fig.add_trace(go.Scatter(x=x, y=t["EMA21"], mode="lines", line=dict(color="rgba(255,152,0,.55)", width=1, dash="dot"),
                                 name="EMA21", hovertemplate="EMA21 %{y:$,.2f}<extra></extra>"))
    # zonas de riesgo y beneficio en el tramo proyectado
    zs = xe
    fig.add_shape(type="rect", x0=zs, x1=x2, y0=ent, y1=tp2, fillcolor="rgba(38,166,154,.08)", line_width=0, layer="below")
    fig.add_shape(type="rect", x0=zs, x1=x2, y0=ent, y1=stp, fillcolor="rgba(239,83,80,.10)", line_width=0, layer="below")
    # niveles
    for y, c, dash in ((tp2, GREEN, "dot"), (tp1, GREEN, "dot"), (ent, ACCENT, "dash"), (stp, RED, "dot")):
        fig.add_shape(type="line", x0=x[0], x1=x_end, y0=y, y1=y, line=dict(color=_rgba_hex(c, .75), width=1, dash=dash))
    poc = (vpa or {}).get("poc")
    if poc and lo - pad < poc < hi + pad:
        fig.add_shape(type="line", x0=x[0], x1=x_end, y0=poc, y1=poc, line=dict(color=_rgba_hex(RED, .45), width=1, dash="dash"))
        fig.add_annotation(x=x[min(3, len(x) - 1)], y=poc, text=f"POC ${poc:,.2f}", showarrow=False, xanchor="left",
                           yanchor="bottom", font=dict(size=11, color=_rgba_hex(RED, .9)), bgcolor="rgba(13,17,23,.85)",
                           bordercolor=_rgba_hex(RED, .5), borderwidth=1, borderpad=2)
    # rechazo / soporte reciente (extremo de la ventana opuesto a la dirección)
    ext_i = t["High"].idxmax() if long else t["Low"].idxmin()
    ext_v = float(t["High"].max() if long else t["Low"].min())
    if abs(ext_v / last - 1) > 0.004:
        near_left = list(x).index(ext_i) < len(x) * 0.15
        fig.add_annotation(x=ext_i, y=ext_v, text=f"{'Rechazo' if long else 'Soporte'} ${ext_v:,.2f}", showarrow=True,
                           arrowhead=0, arrowcolor=MUTED, ax=40 if near_left else 0, ay=-22 if long else 22,
                           xanchor="left" if near_left else "center", font=dict(size=11, color=TXT),
                           bgcolor="rgba(13,17,23,.9)", bordercolor=_rgba_hex(RED if long else GREEN, .7), borderwidth=1,
                           borderpad=3)
    # trayectoria proyectada
    px_ = [x[-1]] + ([xe] if limit else []) + [x1, x2]
    py_ = [last] + ([ent] if limit else []) + [tp1, tp2]
    fig.add_trace(go.Scatter(x=px_, y=py_, mode="lines+markers", line=dict(color=_rgba_hex(GREEN, .9), width=1.6, dash="dash"),
                             marker=dict(size=[8] + ([9] if limit else []) + [7, 7], color=[TXT] + ([ACCENT] if limit else [])
                                         + [GREEN, GREEN], line=dict(width=0)),
                             name="Trayectoria proyectada", hovertemplate="%{y:$,.2f}<extra></extra>"))
    if limit:
        fig.add_annotation(x=x[-1], y=last, text=f"Precio actual ${last:,.2f}", showarrow=True, arrowhead=0, ax=-40,
                           ay=-30 if long else 30, arrowcolor=MUTED, font=dict(size=11, color=TXT),
                           bgcolor="rgba(13,17,23,.9)", bordercolor=BORDER, borderwidth=1, borderpad=3, xanchor="right")
    fig.add_annotation(x=xe, y=ent, text=(f"ENTRADA LMT ${ent:,.2f}" if limit else f"ENTRADA MKT ${ent:,.2f} · precio actual"),
                       showarrow=False, xanchor="right", xshift=-10, yshift=14 if long else -14, font=dict(size=11, color=TXT),
                       bgcolor="rgba(41,98,255,.25)", bordercolor=ACCENT, borderwidth=1, borderpad=3)
    # TP1 a la derecha de su punto; TP2 a la izquierda (así no choca con las etiquetas del eje derecho)
    for y, lbl, xx, side in ((tp1, "TP1", x1, "left"), (tp2, "TP2", x2, "right")):
        fig.add_annotation(x=xx, y=y, text=f"{lbl} · ${y:,.2f}", showarrow=False, xanchor=side,
                           xshift=10 if side == "left" else -10, yshift=(12 if y > ent else -12) if side == "right" else 0,
                           font=dict(size=11, color=GREEN), bgcolor="rgba(13,17,23,.9)", bordercolor=_rgba_hex(GREEN, .6),
                           borderwidth=1, borderpad=3)
    fig.add_annotation(x=x2, y=stp, text=f"STP · ${stp:,.2f}", showarrow=False, xanchor="right", xshift=-4,
                       yshift=-12 if long else 12, font=dict(size=11, color=RED), bgcolor="rgba(13,17,23,.9)",
                       bordercolor=_rgba_hex(RED, .6), borderwidth=1, borderpad=3)
    # etiquetas del eje derecho
    tags = [(tp2, f"TP2 {tp2:,.2f}", GREEN), (tp1, f"TP1 {tp1:,.2f}", GREEN),
            (ent, f"{'LMT' if limit else 'ENT'} {ent:,.2f}", ACCENT), (stp, f"STP {stp:,.2f}", RED)]
    if limit:
        tags.insert(2, (last, f"{last:,.2f}", "#C9D1D9"))
    for y, txt, c in tags:
        _tag(fig, y, txt, c, size=11)
    # estado del plan (franja superior)
    wait = plan.get("estado_tipo") == "esperar"
    sc = AMBER if wait else GREEN
    fig.add_annotation(xref="paper", yref="paper", x=0, y=1.0, xanchor="left", yanchor="bottom",
                       text=f"<b>{plan.get('estado', '')}</b> · {plan.get('marco_corto', '')}", showarrow=False,
                       font=dict(size=12, color=sc), bgcolor=_rgba_hex(sc, .10), bordercolor=_rgba_hex(sc, .45),
                       borderwidth=1, borderpad=5)
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, height=440 if mobile else 520,
                      margin=dict(l=2, r=86 if mobile else 92, t=38, b=6 if mobile else 26), showlegend=False,
                      hovermode="x unified", dragmode=False if mobile else "pan",
                      font=dict(family="Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif", color=TXT, size=11))
    fig.update_xaxes(gridcolor="#161B22", rangebreaks=rangebreaks(tf, crypto), range=[x[0], x_end], showspikes=True,
                     spikecolor="#484F58", spikethickness=1)
    fig.update_yaxes(gridcolor="#1C2128", side="right", range=[lo - pad, hi + pad], tickformat="$,.2f",
                     tickfont=dict(size=11, family="JetBrains Mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"))
    return fig


def equity_chart(trades: pd.DataFrame) -> go.Figure:
    eq = trades["R"].cumsum()
    fig = go.Figure(go.Scatter(x=trades["fecha"], y=eq, mode="lines+markers",
                               line=dict(color=GREEN if eq.iloc[-1] >= 0 else RED, width=2), marker=dict(size=5)))
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, height=260,
                      margin=dict(l=10, r=10, t=10, b=10), yaxis_title="R acumulado")
    fig.update_xaxes(gridcolor=BORDER)
    fig.update_yaxes(gridcolor=BORDER, zeroline=True, zerolinecolor=MUTED)
    return fig


DISCLAIMER = ("<div class='disclaimer'>Herramienta de apoyo al análisis. Las probabilidades son frecuencias históricas "
              "y no garantizan resultados futuros. No es asesoría financiera. Datos: Yahoo Finance (gratuito, puede tener "
              "retraso de ~15 min), Finviz y Alpha Vantage.</div>")


# --------------------------------------------------------------------------
# Mapa de calor de oportunidades (treemap por sector) y barra de sesgo
# --------------------------------------------------------------------------
def opportunity_treemap(df: pd.DataFrame, side: str, height: int = 560) -> go.Figure:  # noqa: C901
    """df con columnas Ticker, Sector, prob, ev, chg, size. side: 'LONG' | 'SHORT'."""
    import numpy as np
    total = float(df["size"].sum()) or 1.0
    ids, labels, parents, values, colors, texts, custom = [], [], [], [], [], [], []
    root = "LONG" if side == "LONG" else "SHORT"
    ids.append(root); labels.append(root); parents.append(""); values.append(total)
    w_ev = float(np.average(df["ev"], weights=df["size"])) if total else 0.0
    colors.append(w_ev); texts.append(""); custom.append([np.nan, w_ev, np.nan, len(df)])
    for sec, g in df.groupby("Sector"):
        sid = f"{root}/{sec}"
        sv = float(g["size"].sum())
        sev = float(np.average(g["ev"], weights=g["size"])) if sv else 0.0
        ids.append(sid); labels.append(sec); parents.append(root); values.append(sv)
        colors.append(sev); texts.append(f"{sec}"); custom.append([np.nan, sev, np.nan, len(g)])
        for r in g.itertuples(index=False):
            ids.append(f"{sid}/{r.Ticker}"); labels.append(r.Ticker); parents.append(sid); values.append(float(r.size))
            colors.append(float(r.ev))
            texts.append(f"<b>{r.Ticker}</b><br>{r.prob * 100:.0f}% · {r.ev:+.2f}R<br>{r.chg:+.2f}%")
            custom.append([r.prob, r.ev, r.chg, 1])
    if side == "LONG":
        scale = [[0, "#3b1d24"], [0.33, "#1c2c4a"], [0.6, "#15803d"], [1, "#22c55e"]]
    else:
        scale = [[0, "#173326"], [0.33, "#1c2c4a"], [0.6, "#b91c1c"], [1, "#ef4444"]]
    fig = go.Figure(go.Treemap(
        ids=ids, labels=labels, parents=parents, values=values, branchvalues="total",
        text=texts, texttemplate="%{text}", textposition="middle center",
        customdata=custom, marker=dict(colors=colors, colorscale=scale, cmin=-0.6, cmax=1.2, line=dict(width=1, color="#0D1117"),
                                       pad=dict(t=18, l=2, r=2, b=2)),
        hovertemplate="<b>%{label}</b><br>Prob.: %{customdata[0]:.0%}<br>Valor esperado: %{customdata[1]:+.2f} R"
                      "<br>Var. día: %{customdata[2]:+.2f}%<extra></extra>",
        pathbar=dict(visible=False), tiling=dict(pad=2), insidetextfont=dict(color="#f8fafc", size=12),
        outsidetextfont=dict(color=MUTED, size=11), root=dict(color=BG)))
    fig.update_layout(paper_bgcolor=BG, margin=dict(l=0, r=0, t=0, b=0), height=height, font=dict(family="Inter"))
    return fig


def bias_bar(n_long: int, n_short: int, strong_long: int = 0, strong_short: int = 0) -> str:
    tot = max(1, n_long + n_short)
    pl = n_long / tot * 100
    if pl >= 60:
        lab, c = "ALCISTA", GREEN
    elif pl >= 52:
        lab, c = "LIGERAMENTE ALCISTA", "#4ade80"
    elif pl > 48:
        lab, c = "NEUTRAL / INDECISO", NEUTRAL
    elif pl > 40:
        lab, c = "LIGERAMENTE BAJISTA", "#f87171"
    else:
        lab, c = "BAJISTA", RED
    return (f"<div style='margin:2px 0 6px'>"
            f"<div class='bias-top' style='display:flex;justify-content:space-between;font-size:max(11px, .78rem);margin-bottom:3px'>"
            f"<span style='color:{GREEN}'><b>▲ LONG {pl:.0f}%</b> · {n_long} acciones · {strong_long} fuertes</span>"
            f"<span>Sesgo del mercado: <b style='color:{c}'>{lab}</b></span>"
            f"<span style='color:{RED}'>{strong_short} fuertes · {n_short} acciones · <b>SHORT {100 - pl:.0f}% ▼</b></span></div>"
            f"<div style='display:flex;height:9px;border-radius:5px;overflow:hidden;background:{BORDER}'>"
            f"<div style='width:{pl:.1f}%;background:linear-gradient(90deg,#15803d,{GREEN})'></div>"
            f"<div style='width:{100 - pl:.1f}%;background:linear-gradient(90deg,{RED},#b91c1c)'></div></div></div>")


# --------------------------------------------------------------------------
# Estilo de tablas: verde = compra/alcista, rojo = venta/bajista, azul = indeciso.
# La intensidad del fondo crece con la probabilidad.
# --------------------------------------------------------------------------
def _rgba(hex_, a):
    h = hex_.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a:.2f})"


def prob_css(p, p_opp, side: int) -> str:
    """Fondo de la celda de probabilidad. side 1 = long (verde), -1 = short (rojo)."""
    try:
        p = float(p)
    except (TypeError, ValueError):
        return ""
    if p_opp is not None and abs(p - float(p_opp)) <= 0.05:
        base = NEUTRAL
    else:
        base = GREEN if side > 0 else RED
    a = max(0.06, min(0.9, (p - 0.33) / 0.32 * 0.9))
    return f"background-color: {_rgba(base, a)}; color: #f8fafc; font-weight: 600"


def signed_css(v, good=0.1, bad=0.0, invert=False) -> str:
    """Color de texto: verde si favorable, rojo si desfavorable, azul si cerca de cero."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ""
    if invert:
        v = -v
    c = GREEN if v > good else (RED if v < bad else NEUTRAL)
    return f"color: {c}; font-weight: 600"


def rs_css(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ""
    if 45 <= v <= 55:
        return f"background-color: {_rgba(NEUTRAL, 0.25)}"
    base = GREEN if v > 55 else RED
    a = min(0.75, abs(v - 50) / 50 * 0.8 + 0.08)
    return f"background-color: {_rgba(base, a)}"


def signal_css(s) -> str:
    return f"color: {SIGNAL_COLORS.get(str(s), MUTED)}; font-weight: 600"


# --------------------------------------------------------------------------
# Celular (navegador web): se detecta por el User-Agent
# --------------------------------------------------------------------------
def is_mobile() -> bool:
    import re as _re
    try:
        ua = st.context.headers.get("User-Agent", "") or ""
    except Exception:
        ua = ""
    if st.session_state.get("force_mobile") is not None:
        return bool(st.session_state["force_mobile"])
    return bool(_re.search(r"Mobi|Android|iPhone|iPod|Windows Phone", ua))


def plot_config(mobile: bool) -> dict:
    return ({"displayModeBar": False, "scrollZoom": False, "responsive": True} if mobile
            else {"displaylogo": False, "scrollZoom": False})


def kpi_row(items: list[tuple]) -> str:
    """Fila de KPIs en una cuadrícula que se acomoda sola (2 por fila en celular)."""
    cells = "".join(
        f"<div class='kpi'><div class='lbl'>{lbl}</div><div class='val' style='color:{c}'>{val}</div>"
        f"<div class='sub'>{sub}</div></div>" for lbl, val, sub, c in items)
    return f"<div class='kpi-grid'>{cells}</div>"


# ---------------------------------------------------------------- gráfico interactivo (escalas como TradingView)
_STATIC = __import__("pathlib").Path(__file__).resolve().parent.parent / "static" / "plotly.min.js"


def _ensure_plotlyjs() -> bool:
    try:
        if not _STATIC.exists():
            from plotly.offline import get_plotlyjs
            _STATIC.parent.mkdir(exist_ok=True)
            _STATIC.write_text(get_plotlyjs(), encoding="utf-8")
        return True
    except Exception:
        return False


_CHART_JS = r"""
<style>html,body{margin:0;padding:0;background:transparent}</style>
<div id="c" style="width:100%;height:%%H%%px"></div>
<script src="/app/static/plotly.min.js"></script>
<script>
(function(){
const fig = %%FIG%%, KEY = "xs_view_" + %%KEY%%;
const gd = document.getElementById("c");
const cfg = {displaylogo:false, scrollZoom:false, responsive:true,
             modeBarButtonsToRemove:["select2d","lasso2d","autoScale2d"]};
let saved = null;
try { saved = JSON.parse(localStorage.getItem(KEY) || "null"); } catch(e) {}
if (saved && saved.y) { fig.layout.yaxis = Object.assign(fig.layout.yaxis || {}, {range: saved.y}); }
Plotly.newPlot(gd, fig.data, fig.layout, cfg).then(function(){
  // eje de tiempo maestro: los demás paneles lo siguen con "matches"
  const XK = Object.keys(gd._fullLayout).filter(function(k){ return /^xaxis\d*$/.test(k) && k !== "xaxis20"; })
               .find(function(k){ return !gd._fullLayout[k].matches; }) || "xaxis";
  const L = gd._fullLayout, X0 = L[XK].range.slice(), Y0 = L.yaxis.range.slice();
  if (saved && saved.x) Plotly.relayout(gd, {[XK + ".range"]: saved.x});
  const save = function(){ try { localStorage.setItem(KEY, JSON.stringify({x: gd._fullLayout[XK].range, y: gd._fullLayout.yaxis.range})); } catch(e) {} };
  gd.on("plotly_relayout", save);
  // Etiquetas sin amontonarse: las de la escala derecha se apilan con separación mínima (como TradingView)
  // y los textos dentro del gráfico que se pisan se ocultan hasta que vuelva a haber espacio.
  let busy = false;
  function declutter(){
    if (busy) return;
    const L = gd._fullLayout, ya = L.yaxis, anns = (gd.layout.annotations || []);
    if (!anns.length || !ya || !ya.l2p) return;
    const upd = {}, GAP = 17, tags = [], inner = [];
    anns.forEach(function(a, i){
      if (a.yref !== "y" || typeof a.y !== "number") return;
      const py = ya._offset + ya.l2p(a.y);
      if (a.xref === "paper" && a.x >= 1) tags.push({i: i, py: py});
      else {
        const px = a.xref === "paper" ? L._size.l + a.x * L._size.w
                   : (L.xaxis.l2p ? L.xaxis._offset + L.xaxis.l2p(L.xaxis.r2l(a.x)) : 0);
        inner.push({i: i, py: py, px: px, w: String(a.text || "").replace(/<[^>]+>/g, "").length * 6});
      }
    });
    tags.sort(function(a, b){ return a.py - b.py; });
    let last = -1e9;
    tags.forEach(function(t){
      const want = Math.max(t.py, last + GAP), shift = -(want - t.py);
      if (Math.abs((anns[t.i].yshift || 0) - shift) > 0.5) upd["annotations[" + t.i + "].yshift"] = shift;
      last = want;
    });
    inner.sort(function(a, b){ return a.py - b.py; });
    const shown = [];
    inner.forEach(function(t){
      const clash = shown.some(function(o){ return Math.abs(o.py - t.py) < 15 && Math.abs(o.px - t.px) < Math.max(o.w, t.w); });
      const vis = !clash;
      if ((anns[t.i].visible !== false) !== vis) upd["annotations[" + t.i + "].visible"] = vis;
      if (vis) shown.push(t);
    });
    if (Object.keys(upd).length) { busy = true; Plotly.relayout(gd, upd).then(function(){ busy = false; }); }
  }
  gd.on("plotly_relayout", function(){ requestAnimationFrame(declutter); });
  declutter();
  function zone(ev){
    const r = gd.getBoundingClientRect(), s = gd._fullLayout._size, ya = gd._fullLayout.yaxis;
    const px = ev.clientX - r.left, py = ev.clientY - r.top;
    const pTop = s.t + (1 - ya.domain[1]) * s.h, pBot = s.t + (1 - ya.domain[0]) * s.h;
    if (px > s.l + s.w && py >= pTop && py <= pBot) return "y";       // escala de precios
    if (py > s.t + s.h && px >= s.l && px <= s.l + s.w) return "x";    // escala de tiempo
    return null;
  }
  let drag = null, raf = 0;
  gd.addEventListener("mousemove", function(ev){
    if (!drag) gd.style.cursor = ({y:"ns-resize", x:"ew-resize"})[zone(ev)] || "";
  });
  gd.addEventListener("mousedown", function(ev){
    const z = zone(ev); if (!z || ev.button !== 0) return;
    ev.preventDefault(); ev.stopPropagation();
    const L = gd._fullLayout;
    drag = {z: z, x: ev.clientX, y: ev.clientY,
            xr: L[XK].range.map(L[XK].r2l), yr: L.yaxis.range.slice()};
  }, true);
  window.addEventListener("mousemove", function(ev){
    if (!drag) return;
    ev.preventDefault();
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(function(){
      const L = gd._fullLayout;
      if (drag.z === "y") {          // arrastrar hacia abajo comprime, hacia arriba estira
        const f = Math.exp((ev.clientY - drag.y) * 0.006), c = (drag.yr[0] + drag.yr[1]) / 2, h = (drag.yr[1] - drag.yr[0]) / 2 * f;
        Plotly.relayout(gd, {"yaxis.range": [c - h, c + h]});
      } else {                        // hacia la izquierda comprime las velas (más historia), a la derecha las estira
        const f = Math.exp((drag.x - ev.clientX) * 0.006), r1 = drag.xr[1], w = (drag.xr[1] - drag.xr[0]) * f;
        Plotly.relayout(gd, {[XK + ".range"]: [L[XK].l2r(r1 - w), L[XK].l2r(r1)]});
      }
    });
  }, true);
  window.addEventListener("mouseup", function(){ if (drag) { drag = null; save(); } }, true);
  // rueda del ratón como TradingView: sobre el gráfico comprime/estira las velas (borde derecho fijo);
  // sobre la escala de precios, comprime/estira en vertical
  gd.addEventListener("wheel", function(ev){
    const r = gd.getBoundingClientRect(), s = gd._fullLayout._size;
    const px = ev.clientX - r.left, py = ev.clientY - r.top, z = zone(ev);
    const inPlot = px >= s.l && px <= s.l + s.w && py >= s.t && py <= s.t + s.h;
    if (!z && !inPlot) return;
    ev.preventDefault(); ev.stopPropagation();
    const L = gd._fullLayout, f = Math.exp(Math.max(-60, Math.min(60, ev.deltaY)) * 0.004);
    if (z === "y") {
      const yr = L.yaxis.range, c = (yr[0] + yr[1]) / 2, h = (yr[1] - yr[0]) / 2 * f;
      Plotly.relayout(gd, {"yaxis.range": [c - h, c + h]});
    } else {
      const xr = L[XK].range.map(L[XK].r2l), w = (xr[1] - xr[0]) * f;
      Plotly.relayout(gd, {[XK + ".range"]: [L[XK].l2r(xr[1] - w), L[XK].l2r(xr[1])]});
    }
    clearTimeout(gd._svT); gd._svT = setTimeout(save, 300);
  }, {passive: false, capture: true});
  gd.addEventListener("dblclick", function(ev){
    const z = zone(ev); if (!z) return;
    ev.stopPropagation();
    Plotly.relayout(gd, z === "y" ? {"yaxis.range": Y0} : {[XK + ".range"]: X0});
  }, true);
  gd.on("plotly_doubleclick", function(){ Plotly.relayout(gd, {[XK + ".range"]: X0, "yaxis.range": Y0}); try{localStorage.removeItem(KEY);}catch(e){} return false; });
});
})();
</script>
"""


def show_chart(fig: go.Figure, view_key: str, mobile: bool = False, container=None) -> None:
    """Gráfico de precio con escalas de TradingView: arrastrar la escala de precios comprime/estira en vertical,
    arrastrar la de tiempo comprime/estira en horizontal, arrastrar el gráfico desplaza libremente y doble clic
    restablece. La vista se recuerda por símbolo, velas y rango. En celular usa el gráfico nativo."""
    box = container or st
    if mobile or not _ensure_plotlyjs():
        box.plotly_chart(fig, width="stretch", config=plot_config(mobile))
        return
    import json as _json
    import streamlit.components.v1 as components
    h = int(fig.layout.height or 700)
    html = (_CHART_JS.replace("%%H%%", str(h)).replace("%%KEY%%", _json.dumps(view_key))
            .replace("%%FIG%%", fig.to_json()))
    with box.container():
        components.html(html, height=h + 4)
        st.caption("Rueda del ratón: comprime o estira las velas · Arrastrar la escala de precios (derecha): comprime en "
                   "vertical · Arrastrar la escala de fechas (abajo): comprime en horizontal · Arrastrar el gráfico: "
                   "desplaza · Doble clic: restablece.")
