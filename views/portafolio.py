import pandas as pd
import streamlit as st

from core import data, portfolio
from core.ui import DISCLAIMER, GREEN, MUTED, NEUTRAL, RED, kpi_row

st.markdown("## Portafolio simulado")
st.markdown("<div class='muted'>Operaciones de práctica registradas desde el <b>Plan de ejecución</b> del análisis. "
            "No se envían órdenes reales: el estado se calcula con velas diarias desde el registro (una entrada Limit se "
            "llena al tocar el precio; luego cuenta el primer nivel tocado: stop o TP2).</div>", unsafe_allow_html=True)

OPS = portfolio.ops()
if not OPS:
    st.info("Aún no registras operaciones. En **Análisis de acción** pulsa **Registrar en portafolio simulado** en el "
            "panel Plan de ejecución.")
    st.stop()


@st.cache_data(ttl=600, show_spinner=False)
def _precios(tickers: tuple) -> dict:
    return data.batch_history(list(tickers), "1y")


with st.spinner("Actualizando precios…"):
    PX = _precios(tuple(sorted({o["ticker"] for o in OPS})))
EV = [portfolio.evaluar(o, PX.get(o["ticker"])) for o in OPS][::-1]

abiertas = [o for o in EV if o["abierta"]]
cerradas = [o for o in EV if not o["abierta"]]
res_ab = sum(o["resultado"] or 0 for o in abiertas)
res_ce = sum(o["resultado"] or 0 for o in cerradas)
gan = [o for o in cerradas if (o["resultado"] or 0) > 0]
st.markdown(kpi_row([
    ("Operaciones", f"{len(EV)}", f"{len(abiertas)} abiertas o pendientes", "#E6EDF3"),
    ("Resultado abierto", f"{'+' if res_ab >= 0 else '−'}${abs(res_ab):,.2f}", "a precio de cierre",
     GREEN if res_ab > 0 else RED if res_ab < 0 else NEUTRAL),
    ("Resultado realizado", f"{'+' if res_ce >= 0 else '−'}${abs(res_ce):,.2f}", f"{len(cerradas)} cerradas",
     GREEN if res_ce > 0 else RED if res_ce < 0 else NEUTRAL),
    ("Acierto", f"{len(gan) / len(cerradas) * 100:.0f}%" if cerradas else "—", "operaciones cerradas con ganancia",
     MUTED if not cerradas else (GREEN if len(gan) / len(cerradas) >= 0.5 else RED)),
]), unsafe_allow_html=True)

df = pd.DataFrame([{
    "id": o["id"], "Ticker": o["ticker"], "Registro": o["fecha"][:10], "Velas": o["tf"],
    "Lado": "Compra" if o["largo"] else "Venta", "Modo": "Limit" if o["modo"] == "limit" else "Mercado",
    "Entrada": o["entrada"], "Stop": o["stop"], "TP1": o["tp1"], "TP2": o["tp2"], "Acciones": o["acciones"],
    "Último": o["ultimo"], "Estado": o["estado"], "Resultado $": float("nan") if o["resultado"] is None else round(o["resultado"], 2),
    "R": float("nan") if o["resultado_R"] is None else o["resultado_R"],
} for o in EV])


def _col(v):
    if v is None or pd.isna(v):
        return f"color: {MUTED}"
    return f"color: {GREEN if v > 0 else RED if v < 0 else NEUTRAL}; font-weight: 600"


sty = (df.drop(columns=["id"]).style
       .format({c: "${:,.2f}" for c in ("Entrada", "Stop", "TP1", "TP2", "Último")} |
               {"Acciones": "{:,.0f}", "Resultado $": lambda v: f"{v + 0.0:+,.2f}", "R": lambda v: f"{v + 0.0:+.2f} R"},
               na_rep="—")
       .map(_col, subset=["Resultado $", "R"]))
sel = st.dataframe(sty, hide_index=True, width="stretch", on_select="rerun", selection_mode="multi-row",
                   key="pf_table")
picked = df.iloc[sel.selection.rows] if sel and sel.selection.rows else df.iloc[0:0]

b1, b2, b3 = st.columns(3)
if b1.button("Analizar", icon=":material/candlestick_chart:", width="stretch", disabled=len(picked) != 1):
    st.session_state.ticker = picked.iloc[0]["Ticker"]
    st.switch_page("views/analisis.py")
if b2.button(f"Cerrar al último precio ({len(picked)})", icon=":material/check_circle:", width="stretch",
             disabled=picked.empty, help="Cierra manualmente las operaciones seleccionadas al último precio de cierre."):
    for _, r in picked.iterrows():
        portfolio.cerrar(r["id"], float(r["Último"]))
    st.rerun()
with b3.popover(f"Eliminar ({len(picked)})", icon=":material/delete:", width="stretch", disabled=picked.empty):
    st.caption("Se eliminan del historial las operaciones seleccionadas. No se puede deshacer.")
    if st.button("Eliminar", key="pf_del", width="stretch"):
        for _, r in picked.iterrows():
            portfolio.eliminar(r["id"])
        st.rerun()

st.markdown(DISCLAIMER, unsafe_allow_html=True)
