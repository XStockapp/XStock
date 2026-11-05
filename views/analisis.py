import math

import pandas as pd
import streamlit as st

from core import ai, store
from core.analysis import full_analysis
from core.ui import (AMBER, BORDER, DISCLAIMER, GREEN, MUTED, RED, SIGNAL_COLORS, color_for, equity_chart,
                     kpi, pill, price_chart)

cfg = st.session_state.cfg


@st.cache_data(ttl=900, show_spinner=False)
def _run(ticker, tp, sl, hz, acct, risk, av, prov):
    return full_analysis(ticker, tp, sl, hz, acct, risk, av or None, prov)


def money(x):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"${x:,.2f}"


def fmt(v, kind):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    if kind == "pct":
        return f"{v * 100:.1f}%"
    if kind == "big":
        return f"${v / 1e9:,.1f} B" if v >= 1e9 else f"${v / 1e6:,.0f} M"
    if kind == "money":
        return f"${v:,.2f}"
    return f"{v:,.2f}"


top = st.columns([3, 1, 1])
ticker = top[0].text_input("Ticker (NYSE / NASDAQ)", st.session_state.get("ticker", "AAPL"),
                           label_visibility="collapsed", placeholder="Ticker, p. ej. NVDA").strip().upper()
go_btn = top[1].button("Analizar", type="primary", use_container_width=True)
if not ticker:
    st.stop()
st.session_state.ticker = ticker

try:
    with st.spinner(f"Analizando {ticker}: precios, 12 indicadores, fundamentales, probabilidad histórica…"):
        A = _run(ticker, cfg["tp_atr"], cfg["sl_atr"], int(cfg["horizonte"]), cfg["capital"], cfg["riesgo_pct"],
                 cfg["alphavantage_key"], "alphavantage" if cfg.get("proveedor", "").startswith("Alpha") else "yahoo")
except Exception as e:
    st.error(f"No se pudo analizar {ticker}: {e}")
    st.stop()

d, tech, prob, plan, m, fs = A["df"], A["tech"], A["prob"], A["plan"], A["metrics"], A["fscore"]
last, prev = d.iloc[-1], d.iloc[-2]
chg = last["Close"] / prev["Close"] - 1

if top[2].button("⭐ A watchlist", use_container_width=True):
    store.add_to_watchlist([{"Ticker": ticker, "Precio": float(last["Close"]), "Señal": None,
                             "Prob. ganancia": prob["probabilidad"], "Entrada": plan["entrada"], "Stop": plan["stop"],
                             "Objetivo 1": plan["objetivo_1"], "Objetivo 2": plan["objetivo_2"]}])
    st.toast(f"{ticker} agregado a la watchlist", icon="⭐")

st.markdown(
    f"## {ticker} <span class='muted' style='font-size:1rem'>{m.get('Nombre', '')} · {m.get('Sector', '')} · "
    f"{m.get('Industria', '')}</span>", unsafe_allow_html=True)
st.markdown(f"<span class='bigpx'>${last['Close']:,.2f}</span> "
            f"<span style='color:{GREEN if chg >= 0 else RED};font-size:1.1rem'>&nbsp;{chg * 100:+.2f}%</span> "
            f"<span class='muted'>&nbsp;cierre {d.index[-1]:%d-%b-%Y}</span>", unsafe_allow_html=True)

# ---------------- KPIs ----------------
k = st.columns(6)
ts = tech["score"]
fsc = fs["score"]
kpi(k[0], "Score técnico", f"{ts:+.0f}", "−100 bajista · +100 alcista", color_for(ts, 15, -15))
kpi(k[1], "Score fundamental", "—" if fsc is None else f"{fsc:+.0f}", "valoración · calidad · crecimiento",
    MUTED if fsc is None else color_for(fsc, 15, -15))
kpi(k[2], "Score combinado", f"{A['combinado']:+.0f}", "60% técnico · 40% fundamental", color_for(A["combinado"], 15, -15))
p = prob["probabilidad"]
be = 1 / (1 + cfg["tp_atr"] / cfg["sl_atr"])
kpi(k[3], "Prob. de ganancia", f"{p * 100:.1f}%", f"{prob['casos_similares']} casos similares · equilibrio {be * 100:.0f}%",
    color_for(p, be + 0.05, be))
ev = prob["valor_esperado_R"]
kpi(k[4], "Valor esperado", f"{ev:+.2f} R", "por unidad de riesgo", color_for(ev, 0.1, 0))
pio = A["piotroski"]
kpi(k[5], "Piotroski F-Score", f"{pio['score']}/{pio['max']}" if pio else "—", "salud contable (≥7 fuerte)",
    (GREEN if pio["score"] >= 7 else RED if pio["score"] <= 3 else AMBER) if pio else MUTED)

st.write("")
left, right = st.columns([1.35, 1])

# ---------------- Veredicto IA ----------------
with left:
    with st.container(border=True):
        st.markdown("#### 🤖 Veredicto con IA")
        payload = ai.build_payload(ticker, tech, m, fs, pio, prob, A["bt"], plan, A["news"], A.get("finviz"))
        key = f"ai_{ticker}_{d.index[-1]:%Y%m%d}_{cfg['tp_atr']}_{cfg['sl_atr']}"
        has_key = bool(cfg["anthropic_key"])
        c_a, c_b = st.columns([1.2, 2])
        if c_a.button("Generar análisis IA" if has_key else "Generar síntesis", type="primary", use_container_width=True):
            try:
                with st.spinner("Claude está evaluando la evidencia…"):
                    st.session_state[key] = (ai.analyze(payload, cfg["anthropic_key"], ai.MODELOS[cfg["modelo"]])
                                             if has_key else ai.rule_based(payload))
            except Exception as e:
                st.error(f"Error con la IA: {e}. Se usa la síntesis por reglas.")
                st.session_state[key] = ai.rule_based(payload)
        if not has_key:
            c_b.caption("Agrega tu Anthropic API key en ⚙️ Configuración para el análisis con Claude. "
                        "Sin clave se usa una síntesis cuantitativa por reglas.")
        V = st.session_state.get(key)
        if V:
            col = SIGNAL_COLORS.get(V.get("veredicto"), AMBER)
            st.markdown(
                f"<div class='verdict' style='border-color:{col}66'>"
                f"<div class='muted'>Veredicto · {V.get('_modelo', '')}</div>"
                f"<h2 style='color:{col}'>{V.get('veredicto', '')}</h2>"
                f"{pill('Confianza ' + str(V.get('confianza', '—')) + '%', col)} &nbsp;"
                f"{pill('Prob. ajustada ' + format(float(V.get('probabilidad_ajustada') or 0) * 100, '.0f') + '%', col)} &nbsp;"
                f"{pill('Horizonte ' + str(V.get('horizonte', '')), MUTED)}"
                f"<p style='margin-top:12px'>{V.get('tesis', '')}</p></div>", unsafe_allow_html=True)
            a1, a2 = st.columns(2)
            a1.markdown("**A favor**\n" + "\n".join(f"- {x}" for x in V.get("factores_a_favor", [])))
            a2.markdown("**Riesgos**\n" + "\n".join(f"- {x}" for x in V.get("riesgos", [])))
            st.markdown(f"**Invalidación:** {V.get('invalidacion', '')}")
            if V.get("catalizadores"):
                st.markdown("**Catalizadores:** " + " · ".join(V["catalizadores"]))
            if V.get("entrada") and abs(float(V["entrada"]) - plan["entrada"]) / plan["entrada"] > 0.002:
                st.info(f"La IA propone ajustar niveles → entrada {money(float(V['entrada']))}, stop "
                        f"{money(float(V['stop']))}, obj. 1 {money(float(V['objetivo_1']))}, obj. 2 "
                        f"{money(float(V['objetivo_2']))}")

# ---------------- Plan de operación ----------------
with right:
    with st.container(border=True):
        st.markdown(f"#### 🎯 Plan de operación · {plan['direccion']}")
        g = st.columns(2)
        kpi(g[0], "Entrada", money(plan["entrada"]), plan["tipo_entrada"], "#60a5fa")
        kpi(g[1], "Stop-loss", money(plan["stop"]),
            f"{plan['tipo_stop']} · −{abs(plan['entrada'] - plan['stop']) / plan['entrada'] * 100:.1f}%", RED)
        st.write("")
        g = st.columns(2)
        kpi(g[0], "Objetivo 1", money(plan["objetivo_1"]),
            f"{plan['tipo_obj1']} · R/B {plan['rr_1']:.1f} · +{abs(plan['objetivo_1'] / plan['entrada'] - 1) * 100:.1f}%", GREEN)
        kpi(g[1], "Objetivo 2", money(plan["objetivo_2"]),
            f"R/B {plan['rr_2']:.1f} · +{abs(plan['objetivo_2'] / plan['entrada'] - 1) * 100:.1f}%", GREEN)
        st.write("")
        st.markdown(
            f"<div class='muted'>Tamaño sugerido (riesgo {cfg['riesgo_pct']}% de ${cfg['capital']:,.0f}): "
            f"<b style='color:#e5e7eb'>{plan['acciones']} acciones</b> · capital {money(plan['capital_requerido'])} · "
            f"pérdida máx. {money(plan['riesgo_monetario'])}<br>Gestión: tomar 50% en Obj. 1 y mover el stop a la "
            f"entrada; el resto hacia Obj. 2. ATR(14) = {money(plan['atr'])}</div>", unsafe_allow_html=True)

st.plotly_chart(price_chart(d, plan), use_container_width=True)

t1, t2, t6, t3, t4, t5 = st.tabs(["📈 Técnico", "🏦 Fundamental", "🔎 Finviz", "🎲 Probabilidad y backtest",
                                   "📐 Niveles", "📰 Noticias"])

with t1:
    sig = pd.DataFrame(tech["señales"])
    sig["Aporte"] = sig["Señal"] * sig["Peso"]
    sig["Sesgo"] = sig["Señal"].map(lambda v: "▲ Alcista" if v > 0.15 else ("▼ Bajista" if v < -0.15 else "● Neutral"))
    sig = sig[["Indicador", "Sesgo", "Señal", "Peso", "Aporte", "Lectura"]]
    colr = lambda v: f"color: {GREEN if v > 0.15 else RED if v < -0.15 else AMBER}; font-weight: 600"
    sty = (sig.style.format({"Señal": "{:+.2f}", "Aporte": "{:+.2f}", "Peso": "{:.1f}"})
           .map(colr, subset=["Señal", "Aporte"])
           .map(lambda s: colr(1 if s.startswith("▲") else -1 if s.startswith("▼") else 0), subset=["Sesgo"]))
    st.dataframe(sty, hide_index=True, use_container_width=True)
    st.caption("Cada indicador emite una señal de −1 (bajista) a +1 (alcista), ponderada por su fiabilidad. "
               "El puntaje técnico es el promedio ponderado × 100.")

with t2:
    c1, c2 = st.columns([1.1, 1])
    with c1:
        groups = {
            "Valoración": [("P/E (TTM)", "num"), ("P/E forward", "num"), ("PEG", "num"), ("P/B", "num"),
                           ("P/S", "num"), ("EV/EBITDA", "num"), ("FCF yield", "pct")],
            "Rentabilidad": [("ROE", "pct"), ("ROA", "pct"), ("Margen bruto", "pct"), ("Margen operativo", "pct"),
                             ("Margen neto", "pct")],
            "Crecimiento y salud": [("Crec. ingresos (YoY)", "pct"), ("Crec. utilidades (YoY)", "pct"),
                                    ("Deuda/Patrimonio", "num"), ("Ratio corriente", "num"), ("Beta", "num"),
                                    ("Dividend yield", "pct")],
            "Mercado y consenso": [("Market cap", "big"), ("Precio objetivo analistas", "money"),
                                   ("Recomendación (1=Compra fuerte, 5=Venta)", "num"), ("N° analistas", "num")],
        }
        gc = st.columns(2)
        for i, (gname, items) in enumerate(groups.items()):
            with gc[i % 2]:
                st.markdown(f"**{gname}**")
                st.dataframe(pd.DataFrame([{"Métrica": a, "Valor": fmt(m.get(a), k_)} for a, k_ in items]),
                             hide_index=True, use_container_width=True)
    with c2:
        st.markdown("**Puntaje por bloque**")
        rows = [{"Bloque": b, "Puntaje": v["score"]} for b, v in fs["bloques"].items()]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True, column_config={
            "Puntaje": st.column_config.ProgressColumn(format="%+.0f", min_value=-100, max_value=100)})
        if pio:
            st.markdown(f"**Piotroski F-Score: {pio['score']}/{pio['max']}**")
            st.dataframe(pd.DataFrame([{"Prueba": k_, "Cumple": "✅" if v else "❌"} for k_, v in pio["tests"].items()]),
                         hide_index=True, use_container_width=True)
        st.caption("Umbrales generales de mercado; compara siempre con el promedio de su sector.")

with t3:
    bt = A["bt"]
    c = st.columns(4)
    kpi(c[0], "Tasa base de la acción", f"{(prob['tasa_base_accion'] or 0) * 100:.1f}%", "todos los días históricos")
    kpi(c[1], "Casos similares al actual", f"{prob['casos_similares']}", "puntaje técnico ±15")
    kpi(c[2], "R medio en casos similares",
        "—" if prob["R_promedio_similares"] is None or math.isnan(prob["R_promedio_similares"])
        else f"{prob['R_promedio_similares']:+.2f} R", "resultado realizado")
    kpi(c[3], "Días medios a la salida",
        "—" if prob["dias_promedio_salida"] is None or math.isnan(prob["dias_promedio_salida"])
        else f"{prob['dias_promedio_salida']:.0f}", prob["parametros"])
    st.write("")
    if bt.get("n"):
        st.markdown(f"**Backtest de la señal** (entrada cuando el puntaje cruza ±40, 5 años, sin solapamiento): "
                    f"{bt['n']} operaciones · acierto {bt['win_rate'] * 100:.0f}% · R medio {bt['avg_R']:+.2f} · "
                    f"profit factor {bt['profit_factor']:.2f} · total {bt['total_R']:+.1f} R · drawdown máx {bt['max_dd_R']:.1f} R")
        st.plotly_chart(equity_chart(bt["trades"]), use_container_width=True)
    else:
        st.info("La señal no generó operaciones en el periodo analizado.")

with t4:
    c1, c2, c3 = st.columns(3)
    c1.markdown("**Soportes**")
    c1.dataframe(pd.DataFrame([{"Nivel": f"${lv:,.2f}", "Toques": n, "Distancia": f"{(lv / last['Close'] - 1) * 100:+.1f}%"}
                               for lv, n in plan["soportes"]]), hide_index=True, use_container_width=True)
    c2.markdown("**Resistencias**")
    c2.dataframe(pd.DataFrame([{"Nivel": f"${lv:,.2f}", "Toques": n, "Distancia": f"{(lv / last['Close'] - 1) * 100:+.1f}%"}
                               for lv, n in plan["resistencias"]]), hide_index=True, use_container_width=True)
    fib = plan["fibonacci"]
    c3.markdown(f"**Fibonacci** (tramo {fib['tramo']} 6 meses)")
    c3.dataframe(pd.DataFrame([{"Retroceso": k_, "Precio": f"${v:,.2f}"} for k_, v in fib["niveles"].items()]),
                 hide_index=True, use_container_width=True)

with t6:
    fv = A.get("finviz") or {}
    if not fv.get("snapshot"):
        st.info("Finviz no respondió para este ticker (o estás en modo demo).")
    else:
        c1, c2 = st.columns([1, 1.2])
        with c1:
            st.markdown("**Posicionamiento y momento**")
            ex = fv["extras"]
            kinds = dict(__import__("core.finviz", fromlist=["EXTRA_KEYS"]).EXTRA_KEYS)
            st.dataframe(pd.DataFrame([{"Métrica": k_, "Valor": (v if kinds.get(k_) == "txt" else
                                         fmt(v, "pct" if kinds.get(k_) == "pct" else "num"))} for k_, v in ex.items()]),
                         hide_index=True, use_container_width=True, height=560)
        with c2:
            if fv.get("signals"):
                st.markdown("**Señales de Finviz:** " + " · ".join(fv["signals"]))
            st.markdown("**Cambios de rating de analistas**")
            if fv.get("ratings"):
                st.dataframe(pd.DataFrame(fv["ratings"]), hide_index=True, use_container_width=True)
            else:
                st.caption("Sin cambios recientes.")
            with st.expander("Ficha completa de Finviz"):
                st.dataframe(pd.DataFrame([{"Campo": k_, "Valor": v} for k_, v in fv["snapshot"].items()]),
                             hide_index=True, use_container_width=True)
        st.markdown(f"[Ver {ticker} en Finviz ↗](https://finviz.com/quote.ashx?t={ticker.replace('-', '.')})")

with t5:
    if A["news"]:
        for n in A["news"]:
            s_ = f" · sentimiento: {n['sentimiento']}" if n.get("sentimiento") else ""
            st.markdown(f"- [{n['titulo']}]({n['link']}) <span class='muted'>· {n['fuente'] or ''}{s_}</span>",
                        unsafe_allow_html=True)
    else:
        st.info("Sin noticias recientes disponibles.")

st.markdown(DISCLAIMER, unsafe_allow_html=True)
