"""Mini gráficos didácticos para explicar cada señal técnica y cada bloque fundamental.

Cada indicador se dibuja sobre el precio simplificado (en línea) o en su propio panel, con sus zonas de lectura,
para que el usuario vea *por qué* el motor lo lee como alcista, bajista o neutral.
"""
import html

import plotly.graph_objects as go

from .ui import AMBER, BORDER, GREEN, MUTED, NEUTRAL, RED

E = html.escape
PRICE = "#8B949E"
C = {"EMA9": "#FFEB3B", "EMA21": "#FF9800", "SMA50": "#E91E63", "SMA200": "#B2B5BE", "MACD": "#2962FF",
     "SIG": "#FF9800", "RSI": "#7E57C2", "ADX": "#E6EDF3", "+DI": GREEN, "-DI": RED, "BB": "#2962FF", "K": "#2962FF",
     "D": "#FF9800", "OBV": "#26C6DA", "OBVE": "#FF9800", "MFI": "#AB47BC", "VWAP": "#F0B90B", "TK": "#2962FF",
     "KJ": "#EF5350"}

# Qué muestra cada mini gráfico (texto didáctico corto)
QUE_MIRA = {
    "Tendencia SMA50/200": "Precio frente a las medias de 50 y 200: arriba de ambas = tendencia de fondo alcista.",
    "Tendencia SMA50/EMA21": "Tendencia intermedia: precio y EMA21 sobre la SMA50 suman a favor.",
    "Cruce EMA9/EMA21": "Impulso de corto plazo: EMA9 sobre EMA21 = impulso alcista.",
    "MACD (12,26,9)": "MACD sobre su señal y sobre cero = impulso alcista; histograma creciente = acelera.",
    "RSI (14)": "Sobre 70 sobrecompra, bajo 30 sobreventa; sobre 50 favorece al alza.",
    "ADX/DMI (14)": "ADX sobre 20–25 = hay tendencia; +DI sobre −DI = la domina el alza.",
    "Bollinger %B": "Cerca de la banda inferior suele rebotar; en la superior, se estira.",
    "Estocástico (14,3,3)": "%K cruzando %D desde abajo de 20 = giro alcista; desde arriba de 80 = bajista.",
    "Volumen / OBV": "OBV sobre su media = el volumen acompaña a las subidas (acumulación).",
    "Money Flow Index": "RSI con volumen: sobre 80 sobrecompra, bajo 20 sobreventa.",
    "VWAP 20 días": "Precio sobre el VWAP = los compradores del periodo van ganando.",
    "Ichimoku": "Precio sobre la nube y Tenkan sobre Kijun = estructura alcista.",
}


def _base(h: int = 132) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(height=h, margin=dict(l=2, r=40, t=4, b=4), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", showlegend=False, hovermode="x unified",
                      font=dict(family="JetBrains Mono, ui-monospace, monospace", size=11, color=MUTED))
    fig.update_xaxes(visible=False, showgrid=False)
    fig.update_yaxes(side="right", showgrid=True, gridcolor="rgba(48,54,61,.45)", zeroline=False, nticks=4,
                     tickfont=dict(size=11))
    return fig


def _ln(fig, x, y, color, name, width=1.4, dash=None, fill=None, fillcolor=None):
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name=name, line=dict(color=color, width=width, dash=dash),
                             fill=fill, fillcolor=fillcolor, hovertemplate=f"{name} %{{y:,.2f}}<extra></extra>"))


def _band(fig, lo, hi, color):
    fig.add_hrect(y0=lo, y1=hi, fillcolor=color, opacity=.08, line_width=0)
    for v in (lo, hi):
        fig.add_hline(y=v, line=dict(color=MUTED, width=1, dash="dot"), opacity=.6)


def mini(d, name: str, n: int = 90) -> go.Figure | None:
    """Mini gráfico del indicador `name` con las últimas `n` velas."""
    t = d.tail(n)
    x = t.index
    fig = _base()
    price = lambda: _ln(fig, x, t["Close"], PRICE, "Precio", 1.6)
    try:
        if name == "Tendencia SMA50/200":
            t = d.tail(max(n, 160)); x = t.index
            price(); _ln(fig, x, t["SMA50"], C["SMA50"], "SMA50"); _ln(fig, x, t["SMA200"], C["SMA200"], "SMA200")
        elif name == "Tendencia SMA50/EMA21":
            price(); _ln(fig, x, t["EMA21"], C["EMA21"], "EMA21"); _ln(fig, x, t["SMA50"], C["SMA50"], "SMA50")
        elif name == "Cruce EMA9/EMA21":
            t = d.tail(min(n, 60)); x = t.index
            price(); _ln(fig, x, t["EMA9"], C["EMA9"], "EMA9"); _ln(fig, x, t["EMA21"], C["EMA21"], "EMA21")
        elif name == "MACD (12,26,9)":
            h = t["MACD_hist"]
            fig.add_trace(go.Bar(x=x, y=h, marker_color=[GREEN if v >= 0 else RED for v in h.fillna(0)],
                                 marker_line_width=0, opacity=.55, hovertemplate="Hist %{y:,.2f}<extra></extra>"))
            _ln(fig, x, t["MACD"], C["MACD"], "MACD"); _ln(fig, x, t["MACD_signal"], C["SIG"], "Señal")
            fig.add_hline(y=0, line=dict(color=MUTED, width=1), opacity=.6)
        elif name == "RSI (14)":
            _band(fig, 30, 70, C["RSI"]); _ln(fig, x, t["RSI"], C["RSI"], "RSI", 1.6)
            fig.update_yaxes(range=[0, 100], tickvals=[30, 50, 70])
        elif name == "ADX/DMI (14)":
            _ln(fig, x, t["ADX"], C["ADX"], "ADX", 1.8); _ln(fig, x, t["+DI"], C["+DI"], "+DI")
            _ln(fig, x, t["-DI"], C["-DI"], "−DI")
            fig.add_hline(y=20, line=dict(color=MUTED, width=1, dash="dot"), opacity=.6)
        elif name == "Bollinger %B":
            _ln(fig, x, t["BB_up"], C["BB"], "Banda sup.", 1)
            _ln(fig, x, t["BB_low"], C["BB"], "Banda inf.", 1, fill="tonexty", fillcolor="rgba(41,98,255,.08)")
            _ln(fig, x, t["BB_mid"], MUTED, "Media", 1, dash="dot"); price()
        elif name == "Estocástico (14,3,3)":
            _band(fig, 20, 80, C["K"]); _ln(fig, x, t["STOCH_K"], C["K"], "%K"); _ln(fig, x, t["STOCH_D"], C["D"], "%D")
            fig.update_yaxes(range=[0, 100], tickvals=[20, 50, 80])
        elif name == "Volumen / OBV":
            _ln(fig, x, t["OBV"], C["OBV"], "OBV", 1.6); _ln(fig, x, t["OBV_EMA"], C["OBVE"], "Media OBV")
            fig.update_yaxes(showticklabels=False)
        elif name == "Money Flow Index":
            _band(fig, 20, 80, C["MFI"]); _ln(fig, x, t["MFI"], C["MFI"], "MFI", 1.6)
            fig.update_yaxes(range=[0, 100], tickvals=[20, 50, 80])
        elif name == "VWAP 20 días":
            price(); _ln(fig, x, t["VWAP20"], C["VWAP"], "VWAP 20")
        elif name == "Ichimoku":
            _ln(fig, x, t["SPAN_A"], "rgba(38,166,154,.6)", "Span A", 1)
            _ln(fig, x, t["SPAN_B"], "rgba(239,83,80,.6)", "Span B", 1, fill="tonexty", fillcolor="rgba(139,148,158,.10)")
            _ln(fig, x, t["TENKAN"], C["TK"], "Tenkan", 1); _ln(fig, x, t["KIJUN"], C["KJ"], "Kijun", 1); price()
        else:
            return None
    except KeyError:
        return None
    return fig


def sesgo(v: float) -> tuple[str, str]:
    return ("▲ Alcista", GREEN) if v > 0.15 else (("▼ Bajista", RED) if v < -0.15 else ("● Neutral", NEUTRAL))


def card_head(name: str, v: float, aporte: float) -> str:
    lbl, c = sesgo(v)
    return (f"<div class='dd-h'><b>{E(name)}</b><span class='dd-p' style='color:{c};border-color:{c}55;"
            f"background:{c}14'>{lbl}</span><span class='dd-a num' style='color:{c}'>{aporte:+.2f}</span></div>"
            f"<div class='dd-q'>{E(QUE_MIRA.get(name, ''))}</div>")


def bar(score: float | None, w: int = 100) -> str:
    """Barra divergente de −100 a +100 (centro = 0)."""
    if score is None:
        return f"<div class='dd-bar' style='width:{w}%'><span class='dd-mid'></span></div>"
    s = max(-100.0, min(100.0, float(score)))
    c = GREEN if s > 15 else RED if s < -15 else NEUTRAL
    left, width = (50, s / 2) if s >= 0 else (50 + s / 2, -s / 2)
    return (f"<div class='dd-bar' style='width:{w}%'><span class='dd-mid'></span>"
            f"<span class='dd-fill' style='left:{left}%;width:{width}%;background:{c}'></span></div>")


def block_card(nombre: str, score: float | None, peso: float, items: list[dict]) -> str:
    c = MUTED if score is None else (GREEN if score > 15 else RED if score < -15 else NEUTRAL)
    rows = "".join(
        f"<div class='dd-m'><span class='dd-mn'>{E(i['metrica'])}</span><span class='dd-mv num'>{E(i['valor'])}</span>"
        f"{bar(i['score'])}<div class='dd-ml'>{E(i['lectura'])}</div></div>"
        for i in sorted(items, key=lambda i: -abs(i["score"]))[:4])
    return (f"<div class='dd-card'><div class='dd-h'><b>{E(nombre)}</b><span class='muted'>× {peso}</span>"
            f"<span class='dd-a num' style='color:{c}'>{'—' if score is None else f'{score:+.0f}'}</span></div>"
            f"{bar(score)}<div class='dd-ms'>{rows or '<span class=muted>Sin datos</span>'}</div></div>")


CSS_COLORS = {"AMBER": AMBER, "BORDER": BORDER}
