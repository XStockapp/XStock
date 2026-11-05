import plotly.express as px
import streamlit as st

from core import data, store
from core.scanner import scan
from core.ui import BG, BORDER, DISCLAIMER, GREEN, RED, AMBER, MUTED, SIGNAL_COLORS, kpi

cfg = st.session_state.cfg

st.markdown("## Escáner de mercado")
st.markdown("<div class='muted'>Ranking por <b>valor esperado</b> y <b>probabilidad histórica</b> de alcanzar el "
            "objetivo antes que el stop, con 12 indicadores técnicos profesionales.</div>", unsafe_allow_html=True)


@st.cache_data(ttl=3600, show_spinner=False)
def _universe(name, custom, av_key):
    return data.get_universe(name, custom, av_key)


def _prices(tickers: tuple):
    """Caché de precios en la sesión (1 hora) con barra de progreso."""
    import time
    cache = st.session_state.setdefault("_price_cache", {})
    hit = cache.get(tickers)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    bar = st.progress(0.0, "Descargando precios…")
    out = data.batch_history(list(tickers), "2y", progress=lambda p, m: bar.progress(min(p, 1.0), m))
    bar.empty()
    cache.clear()
    cache[tickers] = (time.time(), out)
    return out


with st.container(border=True):
    c1, c2, c3, c4 = st.columns([2.2, 1, 1, 1])
    uni = c1.selectbox("Universo", data.UNIVERSOS, index=0)
    min_px = c2.number_input("Precio mínimo ($)", 0.0, 1000.0, 5.0, 1.0)
    min_dv = c3.number_input("Volumen $ diario mín. (M)", 0.0, 5000.0, 20.0, 5.0)
    only_up = c4.toggle("Solo sobre SMA200", value=False)
    custom = ""
    if uni == "Lista personalizada":
        custom = st.text_area("Tickers separados por coma", "AAPL, MSFT, NVDA, AMZN, META, GOOGL, TSLA, AMD")
    if uni.startswith("Finviz"):
        st.caption("Lista generada por el screener de Finviz (volumen promedio > 500K, precio > $5, empresas de EE.UU.); "
                   "luego QuantDesk calcula indicadores y probabilidades para cada una.")
    if uni.startswith("Todo"):
        st.info("El mercado completo tiene ~6.000 acciones: la primera descarga tarda varios minutos "
                "(luego queda en caché 1 hora). El filtro de liquidez descarta las acciones poco negociadas.")
    if uni.startswith("Movers") and not cfg["alphavantage_key"]:
        st.warning("Este universo usa Alpha Vantage: agrega tu API key gratuita en ⚙️ Configuración.")
    run = st.button("🔍  Escanear mercado", type="primary", use_container_width=True)

if run:
    tickers = _universe(uni, custom, cfg["alphavantage_key"])
    with st.status(f"Escaneando {len(tickers)} acciones de «{uni}»…", expanded=True) as status:
        prices = _prices(tuple(tickers))
        st.write(f"Precios recibidos: {len(prices)} acciones")
        bar = st.progress(0.0)
        res = scan(prices, min_px, min_dv * 1e6, cfg["tp_atr"], cfg["sl_atr"], int(cfg["horizonte"]),
                   progress=lambda p, m: bar.progress(min(p, 1.0), m))
        bar.empty()
        if res.empty:
            status.update(label="Ninguna acción pasó los filtros", state="error")
        else:
            store.save_scan(res, {"universo": uni, "n_universo": len(tickers), "n_validas": len(res)})
            status.update(label=f"Escaneo completo: {len(res)} acciones evaluadas", state="complete", expanded=False)

res, meta = store.load_scan()
if res is None or res.empty:
    st.info("Elige un universo y pulsa **Escanear mercado** para generar el ranking.")
    st.markdown(DISCLAIMER, unsafe_allow_html=True)
    st.stop()

view = res.copy()
if only_up:
    view = view[view["Sobre SMA200"]]

# ---------------- KPIs ----------------
k = st.columns(5)
buys = view[view["Señal"].isin(["COMPRA FUERTE", "COMPRA"])]
kpi(k[0], "Acciones evaluadas", f"{len(res):,}", f"{meta.get('universo', '')} · {meta.get('fecha', '')}")
kpi(k[1], "Señales de compra", f"{len(buys)}", f"{len(view[view['Señal'] == 'COMPRA FUERTE'])} fuertes", GREEN)
kpi(k[2], "Prob. media (top 20)", f"{view.head(20)['Prob. ganancia'].mean() * 100:.1f}%",
    f"Universo: {res['Prob. ganancia'].mean() * 100:.1f}%")
pct_up = res["Sobre SMA200"].mean() * 100
kpi(k[3], "Amplitud de mercado", f"{pct_up:.0f}%", "acciones sobre su SMA200",
    GREEN if pct_up > 55 else RED if pct_up < 40 else AMBER)
top = view.iloc[0] if len(view) else None
kpi(k[4], "Mejor oportunidad", top["Ticker"] if top is not None else "—",
    f"{top['Prob. ganancia'] * 100:.0f}% · EV {top['Valor esperado (R)']:+.2f}R" if top is not None else "", GREEN)

st.write("")
f1, f2, f3 = st.columns([2, 1, 1])
sig_filter = f1.multiselect("Filtrar señal", list(SIGNAL_COLORS)[:5], default=["COMPRA FUERTE", "COMPRA"])
min_prob = f2.slider("Prob. mínima", 0, 90, 0, 5) / 100
top_n = f3.selectbox("Mostrar", [25, 50, 100, 250, 1000], index=1)
if sig_filter:
    view = view[view["Señal"].isin(sig_filter)]
view = view[view["Prob. ganancia"] >= min_prob].head(top_n)

cols = ["#", "Ticker", "Señal", "Prob. ganancia", "Valor esperado (R)", "Score técnico", "Fuerza relativa 3m",
        "Precio", "Var. 1d %", "Ret. 3m %", "RSI", "ADX", "Vol. relativo", "ATR %", "Entrada", "Stop",
        "Objetivo 1", "Objetivo 2", "Casos similares"]

st.markdown("##### Ranking · selecciona filas para enviarlas a tu watchlist o analizarlas")
sel = st.dataframe(
    view[cols], hide_index=True, use_container_width=True, height=560,
    on_select="rerun", selection_mode="multi-row", key="scan_table",
    column_config={
        "#": st.column_config.NumberColumn(width="small"),
        "Prob. ganancia": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1, width="medium"),
        "Valor esperado (R)": st.column_config.NumberColumn(format="%+.2f R"),
        "Score técnico": st.column_config.NumberColumn(format="%+.0f"),
        "Fuerza relativa 3m": st.column_config.ProgressColumn("RS 3m", format="%.0f", min_value=0, max_value=100),
        "Precio": st.column_config.NumberColumn(format="$%.2f"),
        "Var. 1d %": st.column_config.NumberColumn(format="%+.2f%%"),
        "Ret. 3m %": st.column_config.NumberColumn(format="%+.1f%%"),
        "RSI": st.column_config.NumberColumn(format="%.0f"),
        "ADX": st.column_config.NumberColumn(format="%.0f"),
        "Vol. relativo": st.column_config.NumberColumn(format="%.1fx"),
        "ATR %": st.column_config.NumberColumn(format="%.1f%%"),
        "Entrada": st.column_config.NumberColumn(format="$%.2f"),
        "Stop": st.column_config.NumberColumn(format="$%.2f"),
        "Objetivo 1": st.column_config.NumberColumn(format="$%.2f"),
        "Objetivo 2": st.column_config.NumberColumn(format="$%.2f"),
    },
)
picked = view.iloc[sel.selection.rows] if sel and sel.selection.rows else view.iloc[0:0]

b1, b2, b3 = st.columns([1.3, 1.3, 3])
if b1.button(f"⭐ Agregar a watchlist ({len(picked)})", disabled=picked.empty, type="primary", use_container_width=True):
    n = store.add_to_watchlist(picked.to_dict("records"))
    st.toast(f"{n} acción(es) agregadas a tu watchlist", icon="⭐")
if b2.button("📊 Analizar selección", disabled=len(picked) != 1, use_container_width=True,
             help="Selecciona una sola fila"):
    st.session_state.ticker = picked.iloc[0]["Ticker"]
    st.switch_page("views/analisis.py")
b3.download_button("⬇️ Exportar ranking (CSV)", view[cols].to_csv(index=False).encode("utf-8"),
                   "ranking_quantdesk.csv", "text/csv")

with st.expander("Mapa de oportunidades: probabilidad vs. puntaje técnico"):
    fig = px.scatter(res, x="Score técnico", y="Prob. ganancia", color="Señal", hover_name="Ticker",
                     size=res["Vol. $ prom (M)"].clip(upper=res["Vol. $ prom (M)"].quantile(0.95)),
                     color_discrete_map=SIGNAL_COLORS, template="plotly_dark", height=460)
    fig.update_layout(paper_bgcolor=BG, plot_bgcolor=BG, margin=dict(l=10, r=10, t=10, b=10))
    fig.update_xaxes(gridcolor=BORDER)
    fig.update_yaxes(gridcolor=BORDER, tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True)

with st.expander("¿Cómo se calcula la probabilidad?"):
    st.markdown(f"""
- Para cada día de los últimos 2 años se simula una compra al cierre con **objetivo = +{cfg['tp_atr']}×ATR** y
  **stop = −{cfg['sl_atr']}×ATR**, máximo **{cfg['horizonte']} sesiones** (método de triple barrera).
- Se toman los días cuyo **puntaje técnico era similar al de hoy (±15 puntos)** y se mide qué porcentaje tocó el objetivo antes que el stop.
- Ese porcentaje se **ajusta (bayesiano)** hacia la tasa del universo completo con el mismo puntaje, para no sobreconfiar en pocas muestras.
- **Valor esperado (R)** = p × {cfg['tp_atr'] / cfg['sl_atr']:.1f} − (1 − p). Con esta relación, el punto de equilibrio es
  {1 / (1 + cfg['tp_atr'] / cfg['sl_atr']) * 100:.0f}% de acierto.
""")
st.markdown(DISCLAIMER, unsafe_allow_html=True)
