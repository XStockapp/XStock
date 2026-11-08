import time

import pandas as pd
import streamlit as st

from core import data, market, store, tables
from core.scanner import scan
from core.ui import DISCLAIMER, GREEN, NEUTRAL, RED, kpi_row, prob_css, signal_css, signed_css

cfg = st.session_state.cfg
st.markdown("## Watchlist")
st.markdown("<div class='muted'>Seguimiento de tus acciones: señal actualizada, probabilidad vigente y estado frente "
            "a los niveles de entrada, stop y objetivos guardados.</div>", unsafe_allow_html=True)

wl = store.watchlist()

with st.container(border=True):
    a, b = st.columns([4, 1], vertical_alignment="bottom")
    new = a.text_input("Agregar tickers manualmente", placeholder="p. ej. NVDA, AMD, PLTR", label_visibility="collapsed")
    if b.button("➕ Agregar", width="stretch") and new.strip():
        tick = [t.strip().upper() for t in new.replace(";", ",").split(",") if t.strip()]
        n = store.add_to_watchlist([{"Ticker": t} for t in tick])
        st.toast(f"{n} agregadas", icon="⭐")
        st.rerun()

if not wl:
    st.info("Tu watchlist está vacía. Desde el **Escáner** selecciona filas y pulsa **Agregar a watchlist**.")
    st.stop()


@st.cache_data(ttl=900, show_spinner=False)
def _live(tickers: tuple, tp, sl, hz, stamp):
    prices = data.batch_history(list(tickers), "2y")
    return scan(prices, 0, 0, tp, sl, hz), prices


if st.button("🔄 Actualizar datos"):
    st.session_state.wl_stamp = time.time()
with st.spinner("Actualizando señales…"):
    live, prices = _live(tuple(sorted(wl)), cfg["tp_atr"], cfg["sl_atr"], int(cfg["horizonte"]),
                 st.session_state.get("wl_stamp", 0))
live = live.set_index("Ticker") if not live.empty else pd.DataFrame()

rows = []
for t, w in wl.items():
    L = live.loc[t] if t in live.index else None
    px = float(L["Precio"]) if L is not None else None
    entry = w.get("entrada") or (float(L["Entrada"]) if L is not None else None)
    stop = w.get("stop") or (float(L["Stop"]) if L is not None else None)
    t1 = w.get("objetivo_1") or (float(L["Objetivo 1"]) if L is not None else None)
    t2 = w.get("objetivo_2") or (float(L["Objetivo 2"]) if L is not None else None)
    estado = "Sin datos"
    sg = int(w.get("dir") or 1)  # 1 = compra (long), -1 = venta en corto
    if px and entry and stop and t1 and t in prices:
        h = prices[t]
        since = h[h.index >= pd.Timestamp(str(w.get("agregado", "1900-01-01"))[:10])]
        if since.empty:
            since = h.tail(1)
        p_add = w.get("precio_agregado") or px
        touched = (since["Low"] <= entry * 1.002) if sg > 0 else (since["High"] >= entry * 0.998)
        filled = ((p_add - entry * (1.005 if sg > 0 else 0.995)) * sg <= 0) or touched.any()
        if not filled:
            estado = "🎯 En zona de entrada" if abs(px / entry - 1) <= 0.01 else "⏳ Esperando retroceso a la entrada"
        else:
            after = since.loc[touched.idxmax():] if touched.any() else since
            hit_stop = ((after["Low"] <= stop).any() if sg > 0 else (after["High"] >= stop).any()) or (px - stop) * sg <= 0
            hit_t2 = t2 and ((after["High"] >= t2).any() if sg > 0 else (after["Low"] <= t2).any())
            hit_t1 = (after["High"] >= t1).any() if sg > 0 else (after["Low"] <= t1).any()
            if hit_stop:
                estado = "⛔ Stop alcanzado"
            elif hit_t2:
                estado = "🏁 Objetivo 2 alcanzado"
            elif hit_t1:
                estado = "✅ Objetivo 1 alcanzado"
            elif abs(px / entry - 1) <= 0.01:
                estado = "🎯 En zona de entrada"
            else:
                estado = "🟢 Operación en curso"
    p0 = w.get("precio_agregado")
    rows.append({
        "Ticker": t,
        "Lado": "▲ Long" if sg > 0 else "▼ Short",
        "Estado": estado,
        "Señal actual": L["Señal"] if L is not None else "—",
        "Prob. ganancia": float(L["Prob. ganancia"]) if L is not None else None,
        "EV (R)": float(L["Valor esperado (R)"]) if L is not None else None,
        "Score técnico": float(L["Score técnico"]) if L is not None else None,
        "Precio": px,
        "Var. 1d %": float(L["Var. 1d %"]) if L is not None else None,
        "Desde que se agregó %": (px / p0 - 1) * 100 * sg if px and p0 else None,
        "Entrada": entry, "Stop": stop, "Objetivo 1": t1, "Objetivo 2": t2,
        "Señal al agregar": w.get("señal_agregado") or "—",
        "Agregado": w.get("agregado"),
        "Notas": w.get("notas", ""),
        **({k: L[k] for k in L.index if k.startswith("Ret ") or k in ("Spark", "Vol. $ prom (M)", "Market cap", "Sector",
                                                                        "Nombre", "RSI", "ADX", "ATR %",
                                                                        "Vol. relativo", "Fuerza relativa 3m",
                                                                        "Casos similares")}
           if L is not None else {}),
    })
df = pd.DataFrame(rows)
for _c in ("Prob. ganancia", "EV (R)", "Score técnico", "Precio", "Var. 1d %", "Desde que se agregó %", "Entrada", "Stop",
           "Objetivo 1", "Objetivo 2"):
    df[_c] = pd.to_numeric(df[_c], errors="coerce")
df = df.sort_values("Prob. ganancia", ascending=False, na_position="last").reset_index(drop=True)

avg = df["Desde que se agregó %"].mean()
st.markdown(kpi_row([
    ("Activos en seguimiento", f"{len(df)}", "", "#E6EDF3"),
    ("Con señal de compra", f"{df['Señal actual'].isin(['COMPRA FUERTE', 'COMPRA']).sum()}", "", GREEN),
    ("En zona de entrada", f"{(df['Estado'] == '🎯 En zona de entrada').sum()}", "", NEUTRAL),
    ("Rendimiento medio", "—" if pd.isna(avg) else f"{avg:+.1f}%", "desde que se agregaron", GREEN if (avg or 0) >= 0 else RED),
]), unsafe_allow_html=True)
st.write("")


@st.cache_data(ttl=300, show_spinner=False)
def _cg_market(tickers: tuple) -> dict:
    try:
        return market.cripto_mercado(list(tickers))
    except Exception:
        return {}


picked: list[str] = []


def _tabla(sub: pd.DataFrame, kind: str):
    """Tabla de la watchlist para acciones o cripto, con sus propias métricas y preferencias."""
    h1, h2 = st.columns([4, 1], vertical_alignment="bottom")
    h1.markdown(f"#### {'Cripto' if kind == 'cripto' else 'Acciones'} · {len(sub)}")
    pref = tables.personalizar(kind, f"wlpref_{kind}", h2)
    sub = sub.head(pref["filas"])
    cm = _cg_market(tuple(sub["Ticker"])) if kind == "cripto" and not data._demo() else {}
    mk, mcfg, fm = tables.columnas(sub, kind, pref, cm)
    spark = [c for c in mk.columns if c.startswith("Últimos")]
    met = [c for c in mk.columns if c in fm["money"] + fm["ratio"] + ["Sector", "Ranking"]]
    tec = [c for c in pref["tecnicas"] if c in mk.columns]
    ident = ["Moneda", "Ticker"] if kind == "cripto" else ["Ticker"]
    base_cols = ["Ticker", "Lado", "Estado", "Señal actual", "Prob. ganancia", "EV (R)", "Desde que se agregó %",
                 "Entrada", "Stop", "Objetivo 1", "Objetivo 2", "Notas"]
    vt = pd.concat([sub[base_cols], mk.drop(columns=[c for c in ("Objetivo 2",) if c in mk.columns])], axis=1)
    order = (["Logo"] + ident + ["Precio"] + fm["perf"] + spark + met + ["Estado", "Señal actual", "Prob. ganancia",
             "EV (R)", "Desde que se agregó %", "Entrada", "Stop", "Objetivo 1", "Objetivo 2"] + tec + ["Lado", "Notas"])
    vt = vt[[c for c in order if c in vt.columns]]
    sty = tables.aplicar_formatos(vt.style, fm, vt.columns, {
        "Prob. ganancia": "{:.1%}", "EV (R)": "{:+.2f} R", "Desde que se agregó %": "{:+.1f}%",
        "Entrada": "${:,.2f}", "Stop": "${:,.2f}", "Objetivo 1": "${:,.2f}", "Objetivo 2": "${:,.2f}"})
    sty = (sty.map(signal_css, subset=["Señal actual"])
           .map(lambda v: signed_css(v, 0.1, 0.0), subset=["EV (R)"])
           .map(lambda v: signed_css(v, 0.0, 0.0), subset=["Desde que se agregó %"])
           .map(lambda v: f"color: {NEUTRAL}", subset=["Entrada"])
           .map(lambda v: f"color: {RED}", subset=["Stop"])
           .map(lambda v: f"color: {GREEN}", subset=["Objetivo 1", "Objetivo 2"])
           .apply(lambda col: [prob_css(v, None, 1) for v in col], subset=["Prob. ganancia"]))
    ev = st.dataframe(sty, hide_index=True, width="stretch", on_select="rerun", selection_mode="multi-row",
                      key=f"wl_table_{kind}", height=min(38 + 35 * len(vt), 640),
                      column_config={**mcfg, "Notas": st.column_config.TextColumn(width="medium")})
    rows_sel = ev.selection.rows if ev and ev.selection else []
    picked.extend(vt.iloc[rows_sel]["Ticker"].tolist())


es_cr = df["Ticker"].str.endswith(("-USD", "-USDT", "-EUR"))
if (~es_cr).any():
    _tabla(df[~es_cr], "acciones")
if es_cr.any():
    _tabla(df[es_cr], "cripto")

c2, c3, _ = st.columns([1, 1.2, 3], vertical_alignment="bottom")
if c2.button("📊 Analizar", disabled=len(picked) != 1, width="stretch", help="Selecciona una sola fila"):
    st.session_state.ticker = picked[0]
    st.switch_page("views/analisis.py")
if c3.button(f"🗑️ Quitar ({len(picked)})", disabled=not picked, width="stretch"):
    store.remove_from_watchlist(picked)
    st.rerun()

with st.expander("📝 Notas"):
    ed = st.data_editor(df[["Ticker", "Notas"]], hide_index=True, width="stretch", key="wl_notas",
                        disabled=["Ticker"], column_config={"Notas": st.column_config.TextColumn(width="large")})
    for _, r in ed.iterrows():
        if r["Notas"] != wl[r["Ticker"]].get("notas", ""):
            store.update_watch(r["Ticker"], notas=r["Notas"])

st.caption("Selecciona filas en las tablas para analizar o quitar. Los niveles de entrada, stop y objetivos son los del "
           "momento en que agregaste el activo; para recalcularlos, quítalo y vuelve a agregarlo desde el escáner o el análisis.")
st.markdown(DISCLAIMER, unsafe_allow_html=True)
