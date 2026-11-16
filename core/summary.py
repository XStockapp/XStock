"""Resumen Ejecutivo adaptativo: elige qué métricas destacar según el perfil de trader."""
from __future__ import annotations

import math

NEUTRAL = "#8B949E"


def _ok(x):
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def _m(x):
    return f"${float(x):,.2f}" if _ok(x) else "—"


def _pct(x):
    return f"{float(x) * 100:.1f}%" if _ok(x) else "—"


def html(cards_: list[dict], title: str) -> str:
    """Resumen ejecutivo: tarjetas compactas (11–15 px), números en monoespaciada tabular. La primera tarjeta
    (estado de la entrada) ocupa dos columnas porque su valor es texto."""
    cells = []
    for i, c in enumerate(cards_):
        first = i == 0
        val_css = ("font-family:Inter,sans-serif;font-size:14px;line-height:1.35" if first else
                   "font-family:&quot;JetBrains Mono&quot;,monospace;font-variant-numeric:tabular-nums;font-size:15px;line-height:1.3")
        cells.append(
            f"<div style='background:#161B22;border:1px solid #30363D;border-radius:6px;padding:8px 10px;min-width:0;"
            f"{'grid-column:span 2;' if first else ''}'>"
            f"<div style='font-size:11.5px;color:#8B949E;line-height:1.3'>{c['t']}</div>"
            f"<div style='{val_css};font-weight:600;color:{c['c']};margin-top:3px'>{c['v']}</div>"
            f"<div style='font-size:11px;color:#8B949E;margin-top:2px;line-height:1.35'>{c['s']}</div></div>")
    return (f"<div class='sec' style='margin-top:6px'>{title}</div>"
            f"<div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(132px,1fr));gap:8px;margin:6px 0 10px'>"
            f"{''.join(cells)}</div>")
