"""
Acceso a QuantDesk.

Modos (se elige solo según los Secrets):
  1. Auth0 (producción): botón único → pantalla de Auth0 con "Continuar con Google" y "Continuar con correo"
     (código de verificación enviado al email). Requiere la sección [auth] en Secrets.
  2. Login de prueba (DEV_LOGIN=1 o modo demo): se escribe un correo, sin verificación. Solo para probar.
  3. Sin autenticación: uso personal (el dueño es administrador). Si existe APP_PASSWORD, se pide la contraseña.

Nadie entra sin invitación, salvo los correos listados en ADMIN_EMAILS.
"""
from __future__ import annotations

import html
import os

import streamlit as st

from . import db
from .store import secret

E = html.escape


# ---------------------------------------------------------------- configuración
def auth_provider_name() -> str | None:
    """Nombre del proveedor OIDC configurado en [auth] (None = sin Auth0)."""
    try:
        a = st.secrets.get("auth")
    except Exception:
        return None
    if not a:
        return None
    subs = [k for k, v in a.items() if hasattr(v, "keys")]
    return subs[0] if subs else ""


def dev_login_enabled() -> bool:
    return os.environ.get("TRADING_DEMO") == "1" or secret("DEV_LOGIN") == "1"


def app_base_url() -> str:
    u = secret("APP_URL")
    if u:
        return u.rstrip("/")
    try:
        from urllib.parse import urlparse
        p = urlparse(st.context.url)
        return f"{p.scheme}://{p.netloc}"
    except Exception:
        return ""


def invite_link(code: str) -> str:
    return f"{app_base_url()}/?invite={code}"


# ---------------------------------------------------------------- cookie de invitación
def _remember_invite(code: str) -> None:
    """Guarda el código en una cookie para recuperarlo al volver del login de Google/correo."""
    import streamlit.components.v1 as components
    safe = "".join(ch for ch in code if ch.isalnum())
    components.html(f"<script>try{{window.parent.document.cookie='qd_invite={safe}; path=/; max-age=3600; SameSite=Lax';}}"
                    f"catch(e){{document.cookie='qd_invite={safe}; path=/; max-age=3600; SameSite=Lax';}}</script>",
                    height=0)


def _pending_invite_code() -> str | None:
    q = st.query_params.get("invite")
    if q:
        return q
    if st.session_state.get("pending_invite"):
        return st.session_state["pending_invite"]
    try:
        return st.context.cookies.get("qd_invite")
    except Exception:
        return None


# ---------------------------------------------------------------- pantallas
LANDING_CSS = """
<style>
section[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none !important; }
.block-container { max-width: 460px !important; padding-top: 7vh !important; }
.qd-card { background: #111827; border: 1px solid #1f2937; border-radius: 14px; padding: 26px 24px 8px; }
.qd-logo { font-weight: 700; font-size: 1.7rem; letter-spacing: -.02em; }
.qd-logo span { color: #22c55e; }
.qd-tag { color: #8b95a7; font-family: 'JetBrains Mono', monospace; font-size: .74rem; margin-top: 2px; }
.qd-inv { border: 1px solid #2563eb; background: rgba(37,99,235,.08); border-radius: 10px; padding: 12px; text-align: center;
          margin: 18px 0 6px; font-size: .9rem; }
.qd-inv small { display: block; color: #8b95a7; font-family: 'JetBrains Mono', monospace; font-size: .72rem; margin-top: 4px; }
.qd-h { font-size: 1.35rem; font-weight: 600; margin: 18px 0 2px; }
.qd-sub { color: #8b95a7; font-size: .85rem; margin-bottom: 8px; }
.qd-foot { color: #8b95a7; font-size: .76rem; text-align: center; margin: 10px 0 2px; line-height: 1.5; }
.qd-err { border: 1px solid #ef4444; background: rgba(239,68,68,.08); border-radius: 10px; padding: 12px; font-size: .88rem; }
</style>
"""


def _card_head(inv: dict | None, title: str, sub: str) -> None:
    box = ""
    if inv and db.invite_status(inv) == "Activa":
        who = E(inv.get("inviter_name") or "El administrador")
        box = (f"<div class='qd-inv'><b>{who}</b> te invitó a QuantDesk."
               f"<small>Acceso beta · incluye {int(inv.get('ai_quota') or 0)} informes de IA · regístrate para reclamar tu lugar.</small></div>")
    elif inv:
        box = f"<div class='qd-err'>Esta invitación está {E(db.invite_status(inv).lower())}. Pide un nuevo enlace.</div>"
    st.markdown(LANDING_CSS + f"<div class='qd-card'><div class='qd-logo'>Quant<span>Desk</span></div>"
                f"<div class='qd-tag'>Escáner · análisis técnico y fundamental · IA</div>{box}"
                f"<div class='qd-h'>{title}</div><div class='qd-sub'>{sub}</div></div>", unsafe_allow_html=True)


def landing(provider: str | None) -> None:
    code = _pending_invite_code()
    inv = db.get_invite(code) if code else None
    if code:
        st.session_state["pending_invite"] = code
        _remember_invite(code)
    _card_head(inv, "Crea tu cuenta" if inv else "Inicia sesión",
               "Gratis durante la beta." if inv else "Acceso solo por invitación.")
    if provider is not None:
        if st.button("Continuar con Google o correo", type="primary", use_container_width=True):
            st.login(provider) if provider else st.login()
        st.markdown("<div class='qd-foot'>En la siguiente pantalla elige <b>Google</b> o escribe tu <b>correo</b>: "
                    "te enviaremos un código de verificación de 6 dígitos.<br>¿Ya tienes cuenta? Usa el mismo botón.</div>",
                    unsafe_allow_html=True)
    else:  # login de prueba
        with st.form("dev_login"):
            name = st.text_input("Nombre completo")
            email = st.text_input("Correo electrónico")
            ok = st.form_submit_button("Continuar (modo prueba)", type="primary", use_container_width=True)
        st.caption("Modo de prueba: no se verifica el correo. En producción se usa Auth0 (Google + código por correo).")
        if ok and "@" in email:
            st.session_state["dev_user"] = {"email": email.strip().lower(), "name": name.strip() or email.split("@")[0],
                                            "provider": "dev"}
            st.rerun()


def _no_access(email: str, msg: str) -> None:
    _card_head(None, "Necesitas una invitación", f"Entraste como <b>{E(email)}</b>.")
    st.markdown(f"<div class='qd-err'>{E(msg)}</div>", unsafe_allow_html=True)
    code = st.text_input("Código de invitación", placeholder="Pega aquí el código o abre de nuevo tu enlace")
    c1, c2 = st.columns(2)
    if c1.button("Usar código", type="primary", use_container_width=True) and code.strip():
        st.session_state["pending_invite"] = code.strip().split("invite=")[-1]
        st.rerun()
    if c2.button("Salir", use_container_width=True):
        logout()


def logout() -> None:
    for k in ("profile", "dev_user", "pending_invite", "_login_logged", "auth_ok"):
        st.session_state.pop(k, None)
    if auth_provider_name() is not None:
        st.logout()
    st.rerun()


# ---------------------------------------------------------------- puerta de acceso
def _identity() -> dict | None:
    prov = auth_provider_name()
    if prov is not None:
        if not st.user.is_logged_in:
            return None
        sub = str(st.user.get("sub") or "")
        return {"email": str(st.user.get("email") or "").lower(), "name": st.user.get("name") or "",
                "provider": sub.split("|")[0] if "|" in sub else "oidc"}
    if dev_login_enabled():
        return st.session_state.get("dev_user")
    return {"email": "owner@local", "name": "Administrador", "provider": "local"}  # uso personal


def gate() -> dict:
    """Devuelve el perfil del usuario con acceso. Si no tiene, muestra la pantalla correspondiente y detiene la app."""
    prov = auth_provider_name()
    # Modo personal con contraseña (versión anterior)
    if prov is None and not dev_login_enabled():
        pwd = secret("APP_PASSWORD")
        if pwd and not st.session_state.get("auth_ok"):
            st.markdown(LANDING_CSS, unsafe_allow_html=True)
            _card_head(None, "Acceso privado", "Ingresa tu contraseña.")
            with st.form("pwd"):
                p = st.text_input("Contraseña", type="password")
                if st.form_submit_button("Entrar", type="primary", use_container_width=True):
                    if p == pwd:
                        st.session_state.auth_ok = True
                        st.rerun()
                    st.error("Contraseña incorrecta")
            st.stop()

    ident = _identity()
    if not ident or not ident.get("email"):
        landing(prov if prov is not None else None)
        st.stop()
    email = ident["email"]
    is_admin = email in db.admin_emails() or ident["provider"] == "local"

    try:
        p = db.get_profile(email)
    except Exception as e:
        st.error(f"No se pudo conectar con la base de datos de usuarios: {e}")
        st.stop()

    if is_admin:
        if not p:
            p = db.create_profile(email, ident.get("name") or "Administrador", "admin", 0, None, ident["provider"])
        elif p.get("role") != "admin" or p.get("status") != "active":
            db.update_profile(email, role="admin", status="active")
            p = db.get_profile(email)
    else:
        code = _pending_invite_code()
        if not p or p.get("status") == "deleted":
            inv, err = (db.check_invite(code, email) if code else (db.find_invite_for_email(email), ""))
            if not inv:
                _no_access(email, err or "No encontramos una invitación para tu cuenta. Abre el enlace que te enviaron "
                                         "o pega el código de invitación.")
                st.stop()
            p = db.redeem_invite(inv, email, ident.get("name") or "", ident["provider"])
            st.session_state["_login_logged"] = True
            st.session_state.pop("pending_invite", None)
            st.toast("¡Bienvenido a QuantDesk! Tu cuenta quedó activada.", icon="🎉")
        elif p.get("status") == "suspended":
            _card_head(None, "Acceso suspendido", f"Cuenta: <b>{E(email)}</b>")
            st.markdown("<div class='qd-err'>Tu acceso a QuantDesk fue suspendido por el administrador.</div>",
                        unsafe_allow_html=True)
            if st.button("Salir", use_container_width=True):
                logout()
            st.stop()
    if "invite" in st.query_params:
        del st.query_params["invite"]
    if not st.session_state.get("_login_logged"):
        db.touch_login(p)
        st.session_state["_login_logged"] = True
        p = db.get_profile(email) or p
    st.session_state["profile"] = p
    return p


def current_profile() -> dict | None:
    return st.session_state.get("profile")


def refresh_profile() -> dict | None:
    p = current_profile()
    if p:
        p = db.get_profile(p["email"]) or p
        st.session_state["profile"] = p
    return p


def is_admin() -> bool:
    p = current_profile()
    return bool(p and p.get("role") == "admin")
