"""Identidad visual de XStock (logo A: aspa oro + flecha esmeralda)."""

NAME = "XStock"
TAGLINE = "Trading · Data · Analytics"

INK, PANEL, IVORY, STEEL = "#0B1220", "#111A2C", "#E8ECF2", "#B9C6D8"
EMERALD, GOLD, MUTED = "#1FBF75", "#C9A24B", "#8FA3BF"

FONTS = ("<link rel='preconnect' href='https://fonts.googleapis.com'>"
         "<link href='https://fonts.googleapis.com/css2?family=Sora:wght@400;700&family=IBM+Plex+Mono:wght@400;500&display=swap' rel='stylesheet'>")


def x_mark(size: int = 40, ground: str = INK) -> str:
    """La X completa del logo A (aspa dorada + flecha verde de alza)."""
    return (f"<svg width='{size}' height='{size}' viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg' "
            f"style='display:inline-block;vertical-align:baseline'>"
            f"<polygon points='2,4 24,4 96,98 74,98' fill='{GOLD}'/>"
            f"<polygon points='4,98 26,98 90,14 72,14' fill='{ground}' stroke='{ground}' stroke-width='10' stroke-linejoin='round'/>"
            f"<polygon points='64,2 98,2 98,36' fill='{ground}' stroke='{ground}' stroke-width='10' stroke-linejoin='round'/>"
            f"<polygon points='4,98 26,98 90,14 72,14' fill='{EMERALD}'/>"
            f"<polygon points='64,2 98,2 98,36' fill='{EMERALD}'/></svg>")


def icon_badge(size: int = 34) -> str:
    """Ícono compacto (X simplificada en un cuadro redondeado)."""
    return (f"<span style='display:inline-flex;align-items:center;justify-content:center;width:{size}px;height:{size}px;"
            f"border-radius:{int(size*.26)}px;background:#13203A;border:1px solid #2A3A58;flex:none'>"
            f"<svg width='{int(size*.56)}' height='{int(size*.56)}' viewBox='0 0 100 100' xmlns='http://www.w3.org/2000/svg'>"
            f"<polygon points='0,4 28,4 98,98 70,98' fill='{GOLD}'/>"
            f"<polygon points='2,98 30,98 98,2 70,2' fill='{EMERALD}'/></svg></span>")


def wordmark(font_px: int = 40, ground: str = INK, tagline: bool = True) -> str:
    """Logotipo completo: X gráfica + Stock (700), con lema opcional."""
    x = int(font_px * .79)
    mb = int(font_px * .06)
    html = (f"<div style='font-family:Sora,system-ui,sans-serif;line-height:1;display:inline-flex;align-items:flex-end;"
            f"font-size:{font_px}px;letter-spacing:-.02em'>"
            f"<span style='margin-right:{int(font_px*.08)}px;margin-bottom:{mb}px;line-height:0'>{x_mark(x, ground)}</span>"
            f"<span style='font-weight:700;color:{IVORY}'>Stock</span></div>")
    if tagline:
        html += (f"<div style='font-family:\"IBM Plex Mono\",monospace;color:{MUTED};font-size:{max(10, int(font_px*.26))}px;"
                 f"letter-spacing:.32em;text-transform:uppercase;margin-top:{int(font_px*.3)}px'>{TAGLINE}</div>")
    return html


def sidebar_brand() -> str:
    """Versión compacta para la barra lateral."""
    return (FONTS + "<div style='display:flex;align-items:center;gap:10px;margin:-6px 0 4px'>" + icon_badge(34) +
            "<div><div style='font-family:Sora,system-ui,sans-serif;font-size:20px;font-weight:700;color:#E8ECF2;"
            "letter-spacing:-.02em;line-height:1.05'><span style='color:#1FBF75'>X</span>Stock</div>"
            f"<div style='font-family:\"IBM Plex Mono\",monospace;font-size:11px;letter-spacing:.18em;color:{MUTED};"
            "text-transform:uppercase;margin-top:2px'>Trading · Data · Analytics</div></div></div>")
