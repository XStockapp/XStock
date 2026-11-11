"""Gráfico avanzado de TradingView (widget oficial embebible, gratuito).

Solo se muestra: XStock no lee ni procesa sus datos (los términos de TradingView no lo permiten). El análisis,
los indicadores y el plan salen de los datos y la configuración de XStock. El usuario puede dibujar, agregar
indicadores de TradingView y cambiar de símbolo dentro del widget.
"""
import json

import streamlit as st

from .timeframes import is_crypto

# Velas de XStock → intervalos del widget (el widget gratuito no tiene 10 minutos: se usa 15)
INTERVALOS = {"10m": "15", "30m": "30", "1h": "60", "4h": "240", "1D": "D", "1W": "W", "1M": "M"}
SIN_EQUIVALENTE = {"10m": "15 min"}


def symbol(ticker: str) -> str:
    """Símbolo de XStock → símbolo de TradingView (BRK-B → BRK.B, BTC-USD → CRYPTO:BTCUSD)."""
    t = (ticker or "").upper().strip()
    if is_crypto(t):
        base = t.rsplit("-", 1)[0]
        return f"CRYPTO:{base}USD"
    return t.replace("-", ".")


def html(ticker: str, tf: str, height: int = 640) -> str:
    cfg = {
        "autosize": False,  # altura fija: con autosize el widget se comprimía en una franja dentro de Streamlit
        "width": "100%",
        "height": height - 28,
        "symbol": symbol(ticker),
        "interval": INTERVALOS.get(tf, "D"),
        "timezone": "America/New_York",
        "theme": "dark",
        "style": "1",
        "locale": "es",
        "backgroundColor": "rgba(13, 17, 23, 1)",
        "gridColor": "rgba(48, 54, 61, 0.35)",
        "hide_side_toolbar": False,  # herramientas de dibujo
        "allow_symbol_change": True,
        "withdateranges": True,
        "save_image": True,
        "details": False,
        "calendar": False,
        "support_host": "https://www.tradingview.com",
    }
    return f"""<style>html,body{{margin:0;padding:0;background:#0D1117}}
.tradingview-widget-copyright{{font:11px Inter,system-ui,sans-serif;color:#8B949E;padding:4px 2px}}
.tradingview-widget-copyright a{{color:#8B949E;text-decoration:none}}</style>
<div class="tradingview-widget-container" style="width:100%">
  <div class="tradingview-widget-container__widget" style="height:{height - 28}px;width:100%"></div>
  <div class="tradingview-widget-copyright"><a href="https://www.tradingview.com/" rel="noopener nofollow"
    target="_blank"><span class="blue-text">Track all markets on TradingView</span></a></div>
  <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js"
    async>{json.dumps(cfg)}</script>
</div>"""


def show(ticker: str, tf: str, height: int = 640, container=None) -> None:
    import streamlit.components.v1 as components
    box = container or st
    with box.container():
        components.html(html(ticker, tf, height), height=height + 6)
