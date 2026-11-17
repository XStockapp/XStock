"""Prueba de espaciado y tamaño de textos sobre la app en MODO DEMO, con sesión iniciada.

Uso (con la app corriendo así:  TRADING_DEMO=1 streamlit run app.py --server.port 8600):
    TRADING_DEMO=1 python tools/check_textos_demo.py [url]

Recorre, en 1366×768 y 1920×1080: Análisis (proyección, gráfico avanzado, acordeones, informe y sus pestañas),
Escáner (tabla y filtro tipo Excel abierto), Opciones (ventana del primer análisis, página, cadena y editor del
perfil táctico) y Portafolio. Usa tools/check_textos.py: con una ventana abierta solo revisa la ventana, no compara
capas fijas (cabeceras sticky) con lo que pasa por debajo y aparta el ratón antes de medir.
Termina con código 1 si encontró algún problema.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("TRADING_DEMO", "1")

from playwright.sync_api import sync_playwright  # noqa: E402

import check_textos as C  # noqa: E402

U = next((a for a in sys.argv[1:] if not a.startswith("--")), "http://localhost:8600")
EMAIL = os.environ.get("DEMO_EMAIL", "edwin@demo.xstock")
CLAVE = os.environ.get("DEMO_PASS", "Demo12345!")


def sin_perfil_opciones():
    """Borra el perfil táctico del usuario demo para que aparezca la ventana del primer análisis."""
    from core import db, profiles
    p = db.get_profile(EMAIL) or {}
    S = profiles.merge_settings(p.get("technical_settings"))
    S["opciones_perfil"] = {}
    db.update_profile(EMAIL, technical_settings=json.dumps(S))


def entrar(b, w, h):
    pg = b.new_page(viewport={"width": w, "height": h})
    pg.goto(U); pg.wait_for_timeout(5000)
    pg.get_by_placeholder("Correo electrónico").fill(EMAIL); pg.get_by_placeholder("Contraseña").fill(CLAVE)
    pg.get_by_role("button", name="Entrar").click(); pg.wait_for_timeout(9000)
    d = "[class*=st-key-usr_sec_ind] > div > details"
    if pg.evaluate(f"()=>{{const e=document.querySelector('{d}');return e&&e.open}}"):
        pg.locator(d + " > summary").click(); pg.wait_for_timeout(600)
    return pg


def analisis(pg, w):
    n = 0
    pg.goto(U + "/analisis"); pg.wait_for_timeout(14000)
    n += C.check(pg, f"{w} análisis proyección")
    pg.get_by_text("Gráfico avanzado", exact=True).last.click(); pg.wait_for_timeout(5000)
    n += C.check(pg, f"{w} análisis TV")
    for ex in ("Score multivariable", "Métricas atractivas", "Factores de riesgo", "Métricas neutrales"):
        pg.locator("summary", has_text=ex).first.click(); pg.wait_for_timeout(500)
    n += C.check(pg, f"{w} análisis acordeones")
    pg.get_by_text("XStock", exact=True).last.click(); pg.wait_for_timeout(8000)
    n += C.check(pg, f"{w} análisis XStock")
    pg.get_by_role("button", name="Informe del analista IA", exact=False).first.click(); pg.wait_for_timeout(7000)
    n += C.check(pg, f"{w} informe técnico")
    for tab in ("Fundamental", "Estrategia", "Empírica"):
        pg.get_by_role("tab", name=tab, exact=False).first.click(); pg.wait_for_timeout(700)
        n += C.check(pg, f"{w} pestaña {tab}")
    return n


def escaner(pg, w):
    n = 0
    pg.goto(U + "/"); pg.wait_for_timeout(6000)  # el escáner es la página principal
    pg.get_by_role("button", name="Escanear mercado").click(); pg.wait_for_timeout(45000)
    n += C.check(pg, f"{w} escáner")
    pop = pg.get_by_role("button", name="Patrón vigente")
    if pop.count():
        pop.first.click(); pg.wait_for_timeout(1500)
        n += C.check(pg, f"{w} escáner › filtro Patrón vigente")
        pg.keyboard.press("Escape"); pg.wait_for_timeout(800)
    else:
        print(f"  [{w} escáner] (sin filtro «Patrón vigente»: ¿no hubo patrones?)")
    return n


def opciones(pg, w):
    n = 0
    sin_perfil_opciones()
    pg.goto(U + "/opciones"); pg.wait_for_timeout(5000)
    i_ = pg.get_by_label("Símbolo").first; i_.fill("TSLA"); i_.press("Enter"); pg.wait_for_timeout(9000)
    dlg = pg.locator("[data-testid=stDialog]")
    if dlg.count():
        n += C.check(pg, f"{w} opciones › primer análisis")
        dlg.get_by_role("button", name="OTM", exact=True).click(); pg.wait_for_timeout(1200)
        n += C.check(pg, f"{w} opciones › primer análisis (OTM)")
        pg.get_by_role("button", name="Analizar con valores por defecto").click()
    else:
        print(f"  [{w} opciones] (no apareció la ventana del primer análisis)")
    pg.wait_for_timeout(20000)
    n += C.check(pg, f"{w} opciones")
    for fr in pg.frames[1:]:
        try:
            n += C.check(fr, f"{w} cadena (iframe)")
        except Exception:
            pass
    pg.get_by_role("button", name="Editar perfil").click(); pg.wait_for_timeout(12000)
    n += C.check(pg, f"{w} opciones › editor del perfil")
    pg.keyboard.press("Escape"); pg.wait_for_timeout(1500)
    return n


def admin_motor(pg, w):
    """Página «Datos y Motor A» (solo si el usuario demo es administrador: ADMIN_EMAILS al arrancar la app)."""
    pg.goto(U + "/admin_motor"); pg.wait_for_timeout(7000)
    if pg.get_by_text("Solo el administrador", exact=False).count() or not pg.get_by_text("Datos y Motor A").count():
        print(f"  [{w} motor A] (omitido: el usuario demo no es administrador)")
        return 0
    b = pg.get_by_role("button", name="Ejecutar diagnóstico")
    if b.count():
        b.first.click(); pg.wait_for_timeout(4000)
    return C.check(pg, f"{w} datos y motor A")


def main():
    tot = 0
    with sync_playwright() as p:
        for (w, h) in ((1366, 768), (1920, 1080)):
            b = p.chromium.launch()
            pg = entrar(b, w, h)
            tot += analisis(pg, w)
            tot += escaner(pg, w)
            tot += opciones(pg, w)
            pg.goto(U + "/portafolio"); pg.wait_for_timeout(9000)
            tot += C.check(pg, f"{w} portafolio")
            tot += admin_motor(pg, w)
            b.close()
    print(f"\n{tot} problema(s) de texto")
    return 1 if tot else 0


if __name__ == "__main__":
    sys.exit(main())
