"""Prueba de espaciado y tamaño de textos: busca textos encimados, recortados o demasiado pequeños.

Uso: python tools/check_textos.py [url] [--reset]   (con la app corriendo; por defecto http://localhost:8599)
--reset borra datos/config.json (modo local) antes de cada pasada para empezar en la configuración inicial.
Recorre la configuración inicial, el menú USER (secciones, indicadores, sus pestañas) y las páginas,
en 1366×768, 1920×1080 y celular. Imprime cada problema y termina con código 1 si encontró alguno."""
import sys

from playwright.sync_api import sync_playwright

import os

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
URL = ARGS[0] if ARGS else "http://localhost:8599"
RESET = "--reset" in sys.argv
MIN_PX = 10.5

JS = r"""(minPx) => {
  const vis = e => {
    if (e.checkVisibility && !e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true, contentVisibilityAuto: true})) return false;
    for (let d = e.closest('details'); d; d = d.parentElement && d.parentElement.closest('details')) {
      if (!d.open && !e.closest('summary')) return false;
    }
    if (e.closest('[hidden], [aria-hidden=true], .sr-only, [data-testid=stSkipLink], #skip-link')) return false;
    const ecs = getComputedStyle(e);  // texto solo para lectores de pantalla (1×1 px recortado)
    if (ecs.position === 'absolute' && parseFloat(ecs.width) <= 1 && parseFloat(ecs.height) <= 1) return false;
    const sb = e.closest('section[data-testid=stSidebar]');
    if (sb && sb.getAttribute('aria-expanded') === 'false') return false;
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.right > 0 && r.left < innerWidth;
  };
  // recorta el rectángulo por los contenedores con desplazamiento (lo que queda fuera no se ve)
  const clip = (el, r) => {
    let o = {left: r.left, right: r.right, top: r.top, bottom: r.bottom};
    for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
      const cs = getComputedStyle(a);
      if (/(auto|scroll|hidden)/.test(cs.overflowY + cs.overflowX)) {
        const b = a.getBoundingClientRect();
        o = {left: Math.max(o.left, b.left), right: Math.min(o.right, b.right), top: Math.max(o.top, b.top), bottom: Math.min(o.bottom, b.bottom)};
      }
    }
    return (o.right > o.left && o.bottom > o.top) ? o : null;
  };
  // capas fijas (pie del panel de indicadores): tapan lo que pasa por debajo, no es un choque de textos
  const layer = e => e.closest('[data-testid=stLayoutWrapper]:has(> .st-key-usr_ind_footer)');
  const leaves = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const t = walker.currentNode; const txt = t.textContent.trim();
    if (!txt || !t.parentElement || !vis(t.parentElement)) continue;
    const el = t.parentElement;
    if (el.closest('[data-testid=stIconMaterial], svg, script, style, .js-plotly-plot, [aria-hidden=true]')) continue;
    const rg = document.createRange(); rg.selectNodeContents(t);
    const rects = [...rg.getClientRects()].map(r => clip(el, r)).filter(r => r && r.right - r.left > 1 && r.bottom - r.top > 1);
    if (rects.length) leaves.push({el, txt: txt.slice(0, 40), rects});
  }
  // valores escritos en campos de texto y de número (recortado = el texto no cabe en el campo)
  const cv = document.createElement('canvas').getContext('2d');
  const inputs = [];
  for (const inp of document.querySelectorAll('input[type=text], input[type=number], input:not([type]), textarea')) {
    if (!vis(inp) || !inp.value) continue;
    const ics = getComputedStyle(inp); cv.font = ics.font;
    const avail = inp.clientWidth - parseFloat(ics.paddingLeft) - parseFloat(ics.paddingRight);
    if (cv.measureText(inp.value).width > avail + 1) inputs.push(`campo recortado: "${inp.value.slice(0, 30)}"`);
    const r = inp.getBoundingClientRect(), cs = getComputedStyle(inp);
    leaves.push({el: inp, txt: 'campo:' + inp.value.slice(0, 30),
                 rects: [{left: r.left + parseFloat(cs.paddingLeft), right: r.right - parseFloat(cs.paddingRight),
                          top: r.top + 4, bottom: r.bottom - 4}]});
  }
  const out = [...inputs];
  // 1) tamaño mínimo
  for (const l of leaves) {
    const fs = parseFloat(getComputedStyle(l.el).fontSize);
    if (fs < minPx) out.push(`pequeño ${fs}px: "${l.txt}"`);
  }
  // 2) recortado (desborda su caja con overflow oculto)
  for (const l of leaves) {
    if (l.txt.startsWith('campo:')) continue;
    let e = l.el;
    for (let i = 0; i < 4 && e; i++, e = e.parentElement) {
      const cs = getComputedStyle(e);
      if ((cs.overflowX === 'hidden' || cs.textOverflow === 'ellipsis') && e.scrollWidth > e.clientWidth + 2
          && !e.closest('[data-baseweb=tab-list]')) { out.push(`recortado: "${l.txt}"`); break; }
    }
  }
  // 3) encimados: rectángulos de texto de elementos distintos que se cruzan
  const inter = (a, b) => Math.min(a.right, b.right) - Math.max(a.left, b.left) > 2 &&
                          Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 2;
  for (let i = 0; i < leaves.length; i++) for (let j = i + 1; j < leaves.length; j++) {
    const A = leaves[i], B = leaves[j];
    if (A.el === B.el || A.el.contains(B.el) || B.el.contains(A.el)) continue;
    if (layer(A.el) !== layer(B.el)) continue;
    if (A.rects.some(a => B.rects.some(b => inter(a, b)))) out.push(`encimado: "${A.txt}" ↔ "${B.txt}"`);
  }
  return [...new Set(out)];
}"""


def check(pg, where):
    pg.wait_for_timeout(700)
    probs = pg.evaluate(JS, MIN_PX)
    for p_ in probs:
        print(f"  [{where}] {p_}")
    return len(probs)


def run(w, h, mobile=False):
    n = 0
    if RESET and os.path.exists("datos/config.json"):
        os.remove("datos/config.json")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": w, "height": h},
                        user_agent="Mozilla/5.0 (iPhone; Mobile)" if mobile else None)
        tag = f"{w}x{h}"
        pg.goto(URL); pg.wait_for_timeout(5000)
        n += check(pg, f"{tag} perfiles")
        pg.get_by_role("button", name="Elegir").nth(1).click(); pg.wait_for_timeout(7000)
        n += check(pg, f"{tag} configuración inicial")
        sb = pg.locator('section[data-testid="stSidebar"]')
        if not mobile:
            sb.locator('[class*=st-key-usr_ind_footer] input').fill("Nombre de prueba largo")
            n += check(pg, f"{tag} nombre de configuración")
            row = sb.locator("[class*=st-key-indrow_ma] details > summary").first
            row.click(); pg.wait_for_timeout(600)
            for tab in ("Entradas", "Estilo", "Visibilidad"):
                sb.locator("[class*=st-key-indrow_ma]").get_by_role("tab", name=tab).click(); pg.wait_for_timeout(400)
                n += check(pg, f"{tag} medias › {tab}")
            row.click()
            sb.locator(".st-key-usr_otros > div > details > summary").click(); pg.wait_for_timeout(5000)
            n += check(pg, f"{tag} otros indicadores")
            sb.locator(".st-key-usr_otros > div > details > summary").click(); pg.wait_for_timeout(1500)
        # entrar con «default» y revisar páginas y secciones
        sb.locator('[class*=st-key-usr_ind_footer] input').fill("")
        btn = pg.get_by_role("button", name="Descartar")
        if btn.count() and btn.is_enabled():
            btn.click(); pg.wait_for_timeout(4000)
        ent = pg.get_by_role("button", name="Entrar a la plataforma")
        if not ent.is_enabled():
            print(f"  [{tag}] (Entrar deshabilitado: {pg.locator('section[data-testid=stSidebar]').inner_text()[-300:]!r})")
        for _ in range(3):  # el botón puede quedar obsoleto si la página aún se está recargando
            ent.click(); pg.wait_for_timeout(5000)
            if pg.locator('[data-testid=stSidebarNav]').count():
                break
        n += check(pg, f"{tag} escáner")
        for path, name in (("analisis", "análisis"), ("admin_invitaciones", "invitaciones"), ("admin_usuarios", "usuarios"),
                           ("watchlist", "watchlist")):
            pg.goto(f"{URL}/{path}"); pg.wait_for_timeout(9000)
            n += check(pg, f"{tag} {name}")
        if not mobile:
            sbx = pg.locator('section[data-testid="stSidebar"]')
            d = "[class*=st-key-usr_sec_ind] > div > details"
            if pg.evaluate(f"()=>{{const e=document.querySelector('{d}');return e&&e.open}}"):
                sbx.locator(d + " > summary").click(); pg.wait_for_timeout(500)
            if not pg.evaluate("()=>{const e=document.querySelector('.st-key-usr_hdr > div > details');return !e || e.open}"):
                sbx.locator(".st-key-usr_hdr > div > details > summary").click(); pg.wait_for_timeout(500)
            for sec in ("cf", "pr", "wl", "est"):
                sm = sbx.locator(f".st-key-usr_sec_{sec} > div > details > summary")
                if not sm.is_visible():
                    print(f"  [{tag}] (sección {sec} no visible)"); continue
                sm.click(); pg.wait_for_timeout(900)
                n += check(pg, f"{tag} USER › {sec}")
                sm.click(); pg.wait_for_timeout(300)
        b.close()
    return n


if __name__ == "__main__":
    total = run(1366, 768) + run(1920, 1080) + run(400, 860, mobile=True)
    print(f"\n{total} problema(s) de texto")
    sys.exit(1 if total else 0)
