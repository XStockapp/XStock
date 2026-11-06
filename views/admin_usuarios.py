from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.express as px
import streamlit as st

from core import auth, db
from core.ui import BG, BORDER, DISCLAIMER, GREEN, MUTED, NEUTRAL, RED, kpi_row

if not auth.is_admin():
    st.error("Solo el administrador puede ver esta página.")
    st.stop()

me = auth.current_profile()
st.markdown("## Usuarios y uso")
st.markdown("<div class='muted'>Último ingreso y actividad de cada usuario. Marca usuarios para expulsarlos (suspender), "
            "eliminarlos o restablecer su contraseña.</div>", unsafe_allow_html=True)

profiles = db.list_profiles()
events = pd.DataFrame(db.events_since(90))
now = datetime.now(timezone.utc)
if not events.empty:
    events["at"] = pd.to_datetime(events["at"], utc=True, format="mixed")


def count(email, kind, days):
    if events.empty:
        return 0
    e = events[(events["email"] == email) & (events["kind"] == kind) & (events["at"] >= now - timedelta(days=days))]
    return int(len(e))


def last(email, kind):
    if events.empty:
        return None
    e = events[(events["email"] == email) & (events["kind"] == kind)]
    return e["at"].max() if len(e) else None


def fmt_dt(x):
    if x is None or x == "" or (isinstance(x, float) and pd.isna(x)):
        return "—"
    try:
        t = pd.to_datetime(x, utc=True)
        d = (now - t).days
        rel = "hoy" if d == 0 else ("ayer" if d == 1 else f"hace {d} días")
        return f"{t.tz_convert('America/Lima'):%d-%b %H:%M} ({rel})"
    except Exception:
        return str(x)[:16]


rows = []
for p in profiles:
    em = p["email"]
    rows.append({
        "Marcar": False,
        "Nombre": p.get("name") or "",
        "Correo": em,
        "Rol": "Admin" if p.get("role") == "admin" else "Usuario",
        "Estado": {"active": "Activo", "suspended": "Suspendido", "deleted": "Eliminado"}.get(p.get("status"), p.get("status")),
        "Último ingreso": fmt_dt(p.get("last_login")),
        "Ingresos": int(p.get("login_count") or 0),
        "Análisis 30d": count(em, "analysis", 30),
        "Escaneos 30d": count(em, "scan", 30),
        "Registrado": str(p.get("created_at") or "")[:10],
        "Acceso con": {"password": "Correo", "google": "Google", "local": "Local"}.get(p.get("auth_provider"), p.get("auth_provider") or ""),
        "Invitación": p.get("invite_code") or "",
    })
df = pd.DataFrame(rows)

act7 = 0 if events.empty else events[(events["kind"].isin(["login", "signup"])) & (events["at"] >= now - timedelta(days=7))]["email"].nunique()
st.markdown(kpi_row([
    ("Usuarios activos", f"{sum(1 for p in profiles if p.get('status') == 'active')}", f"de {len(profiles)} registrados", GREEN),
    ("Ingresaron (7 días)", f"{act7}", "usuarios distintos", NEUTRAL),
    ("Suspendidos", f"{sum(1 for p in profiles if p.get('status') == 'suspended')}", "", RED),
]), unsafe_allow_html=True)
st.write("")

if df.empty:
    st.info("Aún no hay usuarios registrados.")
    st.stop()

ed = st.data_editor(
    df, hide_index=True, use_container_width=True, height=min(90 + 36 * len(df), 520), key="users_editor",
    disabled=[c for c in df.columns if c != "Marcar"],
    column_config={"Marcar": st.column_config.CheckboxColumn(width="small")})
marked = ed[ed["Marcar"]]
marked_users = marked[(marked["Rol"] != "Admin") & (marked["Correo"] != me["email"])]

c1, c2, c3, c4 = st.columns(4)
if c1.button(f"⛔ Expulsar / suspender ({len(marked_users)})", disabled=marked_users.empty, use_container_width=True):
    for em in marked_users["Correo"]:
        db.update_profile(em, status="suspended")
        db.log_event(me["email"], "admin_suspend", em)
    st.toast("Usuarios suspendidos: ya no pueden entrar")
    st.rerun()
if c2.button(f"✅ Reactivar ({len(marked_users)})", disabled=marked_users.empty, use_container_width=True):
    for em in marked_users["Correo"]:
        db.update_profile(em, status="active")
    st.rerun()
if c3.button("🔑 Restablecer contraseña", disabled=len(marked_users) != 1, use_container_width=True,
             help="Marca un solo usuario"):
    em = marked_users["Correo"].iloc[0]
    st.session_state["tmp_pw"] = (em, auth.admin_reset_password(em))
with c4.popover(f"🗑️ Eliminar ({len(marked_users)})", disabled=marked_users.empty, use_container_width=True):
    st.markdown("**Eliminar usuarios marcados:**<br>" + "<br>".join(marked_users["Correo"]), unsafe_allow_html=True)
    hard = st.checkbox("Borrar también su historial y watchlist (definitivo)")
    st.caption("Sin borrar el historial, la cuenta queda como «Eliminado»: no puede entrar y necesitaría una nueva invitación.")
    if st.button("Confirmar eliminación", type="primary", use_container_width=True):
        for em in marked_users["Correo"]:
            if hard:
                db.delete_profile(em, purge_events=True)
                for t in list(db.watchlist_get(em)):
                    db.watchlist_del(em, t)
            else:
                db.update_profile(em, status="deleted")
            db.log_event(me["email"], "admin_delete", em)
        st.rerun()
if st.session_state.get("tmp_pw"):
    em, pw = st.session_state["tmp_pw"]
    st.success(f"Contraseña temporal para **{em}** (envíasela; podrá cambiarla con «Olvidé mi contraseña» si el correo está configurado):")
    st.code(pw, language=None)
st.caption("Los administradores (ADMIN_EMAILS) no se pueden suspender ni eliminar desde aquí.")

# ---------------- actividad
st.write("")
st.markdown("<div class='sec'>Actividad de los últimos 30 días</div>", unsafe_allow_html=True)
if events.empty:
    st.info("Sin actividad registrada.")
else:
    ev = events[events["at"] >= now - timedelta(days=30)].copy()
    kinds = {"analysis": "Análisis", "scan": "Escaneos", "login": "Ingresos", "signup": "Registros"}
    ev = ev[ev["kind"].isin(kinds)]
    ev["Tipo"] = ev["kind"].map(kinds)
    ev["Día"] = ev["at"].dt.tz_convert("America/Lima").dt.date
    c1, c2 = st.columns([1.6, 1])
    with c1:
        g = ev.groupby(["Día", "Tipo"]).size().reset_index(name="Eventos")
        g["Día"] = pd.to_datetime(g["Día"]).dt.strftime("%d-%b")
        fig = px.bar(g, x="Día", y="Eventos", color="Tipo", template="plotly_dark", height=300,
                     color_discrete_map={"Registros": "#a855f7", "Análisis": NEUTRAL, "Escaneos": GREEN, "Ingresos": MUTED})
        fig.update_layout(paper_bgcolor=BG, plot_bgcolor=BG, margin=dict(l=4, r=4, t=4, b=4),
                          legend=dict(orientation="h", y=1.1), bargap=0.2)
        fig.update_xaxes(gridcolor=BORDER, type="category", title=None)
        fig.update_yaxes(gridcolor=BORDER, dtick=1 if g["Eventos"].max() < 10 else None)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    with c2:
        top = ev[ev["kind"] == "analysis"].groupby("email").size().sort_values(ascending=False).head(10)
        st.markdown("**Más activos (análisis, 30 días)**")
        st.dataframe(top.rename("Análisis").reset_index().rename(columns={"email": "Usuario"}), hide_index=True,
                     use_container_width=True)
    who = st.selectbox("Ver historial de un usuario", ["—"] + df["Correo"].tolist())
    if who != "—":
        h = events[events["email"] == who].head(100).copy()
        h["Fecha"] = h["at"].dt.tz_convert("America/Lima").dt.strftime("%d-%b-%Y %H:%M")
        h["Evento"] = h["kind"].map({**kinds, "ai_report": "Informe IA"}).fillna(h["kind"])
        st.dataframe(h[["Fecha", "Evento", "detail"]].rename(columns={"detail": "Detalle"}), hide_index=True,
                     use_container_width=True, height=280)

st.markdown(DISCLAIMER, unsafe_allow_html=True)
