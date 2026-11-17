"""Datos y Motor A (solo administrador): diagnóstico en vivo del plan de Alpaca y reporte del último entrenamiento."""
import html

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from core import alpaca, auth
from core.motor_a import artefactos as AR
from core.ui import AMBER, GREEN, MUTED, RED

if not auth.is_admin():
    st.error("Solo el administrador puede ver esta página.")
    st.stop()

E = html.escape
MONO = "'JetBrains Mono','Fira Code',monospace"
st.markdown(f"""<style>
.ma-t{{width:100%;border-collapse:collapse;font-size:12px;margin:4px 0 10px}}
.ma-t th{{text-align:right;color:#8B949E;font-weight:600;border-bottom:1px solid #30363D;padding:5px 8px;white-space:nowrap}}
.ma-t th:first-child,.ma-t th.l,.ma-t td.l{{text-align:left}}
.ma-t td{{padding:5px 8px;border-bottom:1px solid #21262D;color:#E6EDF3;text-align:right;font-family:{MONO};
  font-variant-numeric:tabular-nums;white-space:nowrap}}
.ma-t td.l{{font-family:Inter,system-ui,sans-serif;white-space:normal}}
.ma-box{{background:#161B22;border:1px solid #30363D;border-radius:8px;padding:10px 12px;margin-bottom:10px;font-size:12.5px;
  line-height:1.55;color:#E6EDF3;overflow-x:auto}}
.ma-box h4{{margin:0 0 6px;font-size:11px;color:#8B949E;text-transform:uppercase;letter-spacing:.05em;font-weight:600}}
.ma-g{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-bottom:10px}}
.ma-g div{{background:#161B22;border:1px solid #30363D;border-radius:8px;padding:8px 10px}}
.ma-g span{{display:block;font-size:11px;color:#8B949E}}
.ma-g b{{font-family:{MONO};font-variant-numeric:tabular-nums;font-size:14px;color:#E6EDF3}}
.ma-v{{display:inline-block;font-size:11px;font-weight:700;padding:2px 8px;border-radius:4px;border:1px solid}}
</style>""", unsafe_allow_html=True)

st.markdown("### Datos y Motor A")

# ------------------------------------------------------------------ diagnóstico de Alpaca
st.markdown("<div class='ma-box'><h4>Diagnóstico del plan de Alpaca</h4><div class='muted small'>Prueba en vivo qué permite "
            "la cuenta configurada en el servidor (las claves no se muestran).</div></div>", unsafe_allow_html=True)
if st.button("Ejecutar diagnóstico", key="ma_diag", type="primary"):
    with st.spinner("Consultando Alpaca…"):
        st.session_state["ma_diag_res"] = alpaca.diagnostico()
res = st.session_state.get("ma_diag_res")
if res:
    filas = []
    for r in res:
        col, txt = (GREEN, "Sí") if r["ok"] is True else (RED, "No") if r["ok"] is False else (MUTED, "Info")
        filas.append(f"<tr><td class='l'>{E(r['prueba'])}</td><td style='color:{col}'>{txt}</td>"
                     f"<td class='l'>{E(r['detalle'])}</td></tr>")
    st.markdown("<div class='ma-box'><table class='ma-t'><tr><th>Prueba</th><th>Resultado</th><th class='l'>Detalle</th></tr>"
                + "".join(filas) + "</table></div>", unsafe_allow_html=True)

# ------------------------------------------------------------------ reporte del Motor A
REP = AR.leer_reporte()
if not REP:
    st.markdown("<div class='ma-box'><h4>Motor A · acción del precio</h4>Todavía no hay entrenamientos. Se entrena en "
                "GitHub Actions (flujo «Motor A», los domingos o a mano) y el reporte aparece aquí.</div>",
                unsafe_allow_html=True)
    st.stop()

R = REP["resumen"]
vcol = GREEN if R["veredicto"].startswith("VENTAJA") else AMBER if R["veredicto"].startswith("SEÑAL") else RED


def _f(v, fmt="{:.3f}"):
    return "—" if v is None or not np.isfinite(v) else fmt.format(v)


st.markdown(
    f"<div class='ma-box'><h4>Motor A · acción del precio</h4>"
    f"<span class='ma-v' style='color:{vcol};border-color:{vcol}'>{E(R['veredicto'])}</span> "
    f"<span class='muted small'>Entrenado {E(REP['generado_utc'])} UTC · {REP['acciones']} acciones · "
    f"{REP['filas']:,} filas · {E(REP['desde'])} → {E(REP['hasta'])} · {E(REP['fuente'])}</span>"
    f"<div class='muted small' style='margin-top:6px'>Predice la probabilidad de que el precio toque +{REP['k']:g}σ·√H "
    f"antes que −{REP['k']:g}σ·√H en H = {REP['H']} sesiones. Todo se mide fuera de muestra: cada año se predice con un "
    f"modelo entrenado solo con los años anteriores. {E(R['criterio'])}</div></div>", unsafe_allow_html=True)

st.markdown(
    "<div class='ma-g'>"
    f"<div><span>AUC modelo · momentum · azar</span><b>{_f(R['auc'])} · {_f(R['auc_momentum'])} · 0.500</b></div>"
    f"<div><span>Brier skill vs tasa base</span><b>{_f(R['bss'], '{:+.4f}')}</b></div>"
    f"<div><span>IC de rango (t-estadístico)</span><b>{_f(R['ic_medio'], '{:+.3f}')} (t={_f(R['ic_t'], '{:.1f}')})</b></div>"
    f"<div><span>Acierto decil alto · bajo · real</span><b>{R['decil_alto']['real'] * 100:.1f}% · "
    f"{R['decil_bajo']['real'] * 100:.1f}% · {R['tasa_real'] * 100:.1f}%</b></div></div>", unsafe_allow_html=True)

c1, c2 = st.columns(2)
with c1:
    fia = R["fiabilidad"]
    fig = go.Figure()
    fig.add_scatter(x=[0.3, 0.7], y=[0.3, 0.7], mode="lines", line=dict(color=MUTED, dash="dot", width=1),
                    name="Calibración perfecta", hoverinfo="skip")
    fig.add_scatter(x=[f["p_media"] for f in fia], y=[f["real"] for f in fia], mode="lines+markers",
                    line=dict(color=GREEN, width=2), name="Modelo (fuera de muestra)",
                    hovertemplate="predicho %{x:.1%} · real %{y:.1%}<extra></extra>")
    fig.update_layout(height=280, margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="#161B22", font=dict(color="#E6EDF3", size=11),
                      title=dict(text="Fiabilidad: probabilidad predicha vs frecuencia real", font=dict(size=12)),
                      xaxis=dict(tickformat=".0%", gridcolor="#21262D"), yaxis=dict(tickformat=".0%", gridcolor="#21262D"),
                      legend=dict(orientation="h", y=-0.2, font=dict(size=11)))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
with c2:
    imp = REP.get("importancia") or []
    st.markdown("<div class='ma-box'><h4>Variables que más pesan</h4><table class='ma-t'><tr><th>Variable</th><th>Peso</th></tr>"
                + "".join(f"<tr><td class='l'>{E(i['variable'])}</td><td>{i['peso'] * 100:.1f}%</td></tr>" for i in imp[:10])
                + "</table></div>", unsafe_allow_html=True)

filas = "".join(
    f"<tr><td class='l'>{d['anio']}</td><td>{d['n_test']:,}</td><td>{d['tasa_base'] * 100:.1f}%</td>"
    f"<td style='color:{GREEN if d['auc'] > max(0.5, d['auc_momentum']) else RED if d['auc'] < 0.5 else '#E6EDF3'}'>{_f(d['auc'])}</td>"
    f"<td>{_f(d['auc_momentum'])}</td><td>{_f(d['bss'], '{:+.4f}')}</td></tr>" for d in REP["pliegues"])
st.markdown("<div class='ma-box'><h4>Resultado por año (fuera de muestra)</h4><table class='ma-t'><tr><th>Año</th>"
            "<th>Muestras</th><th>Tasa base</th><th>AUC modelo</th><th>AUC momentum</th><th>Brier skill</th></tr>"
            + filas + "</table></div>", unsafe_allow_html=True)
st.markdown("<div class='ma-box'><h4>Limitaciones conocidas</h4>" + "<br>".join(f"· {E(x)}" for x in REP.get("limitaciones", []))
            + "</div>", unsafe_allow_html=True)
