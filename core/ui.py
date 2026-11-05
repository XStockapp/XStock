"""Estilo visual (tema terminal profesional) y gráficos."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

BG, PANEL, BORDER = "#0b0f17", "#111827", "#1f2937"
TXT, MUTED = "#e5e7eb", "#8b95a7"
GREEN, RED, AMBER, BLUE, VIOLET = "#22c55e", "#ef4444", "#f59e0b", "#3b82f6", "#a78bfa"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');
html, body, [class*="css"], .stMarkdown, .stText {{ font-family: 'Inter', sans-serif; }}
.block-container {{ padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1500px; }}
h1, h2, h3 {{ letter-spacing: -0.02em; }}
[data-testid="stSidebar"] {{ background: #0d1320; border-right: 1px solid {BORDER}; }}
.kpi {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 10px; padding: 14px 16px; height: 100%; }}
.kpi .lbl {{ color: {MUTED}; font-size: 0.72rem; text-transform: uppercase; letter-spacing: .08em; }}
.kpi .val {{ font-family: 'JetBrains Mono', monospace; font-size: 1.45rem; font-weight: 600; margin-top: 4px; }}
.kpi .sub {{ color: {MUTED}; font-size: 0.78rem; margin-top: 2px; }}
.pill {{ display:inline-block; padding: 3px 10px; border-radius: 999px; font-size: .75rem; font-weight: 600; }}
.bigpx {{ font-family: 'JetBrains Mono', monospace; font-size: 1.8rem; font-weight: 600; }}
.brand {{ font-weight: 700; font-size: 1.15rem; letter-spacing: -.01em; }}
.brand span {{ color: {GREEN}; }}
.muted {{ color: {MUTED}; font-size: .85rem; }}
.verdict {{ border-radius: 12px; padding: 18px 20px; border: 1px solid {BORDER}; background: {PANEL}; }}
.verdict h2 {{ margin: 0 0 4px 0; font-size: 1.6rem; }}
.disclaimer {{ color: {MUTED}; font-size: .72rem; border-top: 1px solid {BORDER}; padding-top: 8px; margin-top: 24px; }}
div[data-testid="stDataFrame"] {{ border: 1px solid {BORDER}; border-radius: 10px; }}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def color_for(v: float, good=0, bad=0) -> str:
    return GREEN if v > good else (RED if v < bad else AMBER)


def kpi(col, label: str, value: str, sub: str = "", color: str = TXT):
    col.markdown(f"<div class='kpi'><div class='lbl'>{label}</div>"
                 f"<div class='val' style='color:{color}'>{value}</div>"
                 f"<div class='sub'>{sub}</div></div>", unsafe_allow_html=True)


def pill(text: str, color: str) -> str:
    return f"<span class='pill' style='background:{color}22;color:{color};border:1px solid {color}55'>{text}</span>"


SIGNAL_COLORS = {"COMPRA FUERTE": GREEN, "COMPRA": "#4ade80", "REBOTE (contratendencia)": AMBER,
                 "NEUTRAL": MUTED, "EVITAR / VENTA": RED, "COMPRAR": GREEN, "ESPERAR": AMBER,
                 "EVITAR": RED, "VENDER EN CORTO": RED}


def price_chart(d: pd.DataFrame, plan: dict | None = None, bars: int = 180) -> go.Figure:
    d = d.tail(bars)
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.02,
                        row_heights=[0.56, 0.12, 0.16, 0.16])
    fig.add_trace(go.Candlestick(x=d.index, open=d["Open"], high=d["High"], low=d["Low"], close=d["Close"],
                                 name="Precio", increasing_line_color=GREEN, decreasing_line_color=RED,
                                 increasing_fillcolor=GREEN, decreasing_fillcolor=RED), 1, 1)
    for col, c, w in (("EMA21", AMBER, 1.2), ("SMA50", BLUE, 1.4), ("SMA200", VIOLET, 1.6)):
        fig.add_trace(go.Scatter(x=d.index, y=d[col], name=col, line=dict(color=c, width=w)), 1, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d["BB_up"], name="Bollinger", line=dict(color="#64748b", width=0.8, dash="dot")), 1, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d["BB_low"], showlegend=False, line=dict(color="#64748b", width=0.8, dash="dot"),
                             fill="tonexty", fillcolor="rgba(100,116,139,0.06)"), 1, 1)
    if plan:
        for key, lbl, c, dash in (("entrada", "Entrada", BLUE, "solid"), ("stop", "Stop", RED, "dash"),
                                  ("objetivo_1", "Obj. 1", GREEN, "dash"), ("objetivo_2", "Obj. 2", GREEN, "dot")):
            y = plan.get(key)
            if y:
                fig.add_hline(y=y, line=dict(color=c, width=1.4, dash=dash), row=1, col=1,
                              annotation_text=f"{lbl} {y:,.2f}", annotation_position="right",
                              annotation_font=dict(color=c, size=11))
        for lv, n in plan.get("soportes", [])[:3] + plan.get("resistencias", [])[:3]:
            fig.add_hline(y=lv, line=dict(color="rgba(148,163,184,0.25)", width=1), row=1, col=1)
    lo, hi = float(d["Low"].min()), float(d["High"].max())
    if plan:
        lv = [plan.get(k) for k in ("entrada", "stop", "objetivo_1", "objetivo_2") if plan.get(k)]
        lo, hi = min([lo] + lv), max([hi] + lv)
    pad = (hi - lo) * 0.04
    fig.update_yaxes(range=[lo - pad, hi + pad], row=1, col=1)
    vc = [GREEN if c >= o else RED for o, c in zip(d["Open"], d["Close"])]
    fig.add_trace(go.Bar(x=d.index, y=d["Volume"], marker_color=vc, opacity=0.6, name="Volumen", showlegend=False), 2, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d["VOL_SMA20"], line=dict(color=AMBER, width=1), showlegend=False), 2, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d["RSI"], name="RSI", line=dict(color=VIOLET, width=1.3), showlegend=False), 3, 1)
    for y, c in ((70, RED), (30, GREEN)):
        fig.add_hline(y=y, line=dict(color=c, width=0.8, dash="dot"), row=3, col=1)
    hc = [GREEN if v >= 0 else RED for v in d["MACD_hist"]]
    fig.add_trace(go.Bar(x=d.index, y=d["MACD_hist"], marker_color=hc, opacity=0.6, showlegend=False), 4, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d["MACD"], line=dict(color=BLUE, width=1.2), name="MACD", showlegend=False), 4, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d["MACD_signal"], line=dict(color=AMBER, width=1.2), name="Señal", showlegend=False), 4, 1)
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG, height=760,
                      margin=dict(l=10, r=90, t=10, b=10), xaxis_rangeslider_visible=False,
                      legend=dict(orientation="h", y=1.02, x=0, font=dict(size=11)),
                      font=dict(family="Inter", color=TXT))
    fig.update_xaxes(gridcolor=BORDER, rangebreaks=[dict(bounds=["sat", "mon"])])
    fig.update_yaxes(gridcolor=BORDER)
    for i, t in enumerate(["", "Vol", "RSI", "MACD"], start=1):
        if t:
            fig.update_yaxes(title_text=t, title_font=dict(size=10, color=MUTED), row=i, col=1)
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
