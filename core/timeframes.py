"""
Temporalidades permitidas en XStock.

Regla obligatoria: la temporalidad mínima es 10 minutos (velas para day trading). Nunca se ofrecen
velas de 1m, 2m, 5m o 15m (evita saturar la API de datos y la memoria del servidor). Con Yahoo de
respaldo, las velas de 10m se arman agregando barras de 5m.
"""
from __future__ import annotations

import pandas as pd

# yf = intervalo de yfinance · period = historial máximo útil que entrega Yahoo para ese intervalo
# resample = agregación propia (Yahoo no entrega 4h) · bars_day = velas por sesión bursátil (6.5 h)
TIMEFRAMES: dict[str, dict] = {
    "10m": {"yf": "5m", "period": "60d", "resample": "10min", "bars_day": 39, "nombre": "10 minutos",
            "horizonte": 39, "marco": "Intradía / Day trading · minutos a 1 sesión (≈39 velas)"},
    "30m": {"yf": "30m", "period": "60d", "resample": None, "bars_day": 13, "nombre": "30 minutos",
            "horizonte": 26, "marco": "Intradía / Day trading · horas a 2–3 días (≈26 velas)"},
    "1h": {"yf": "60m", "period": "730d", "resample": None, "bars_day": 7, "nombre": "1 hora",
           "horizonte": 35, "marco": "Corto plazo · días a 2 semanas (≈35 velas)"},
    "4h": {"yf": "60m", "period": "730d", "resample": "4h", "bars_day": 2, "nombre": "4 horas",
           "horizonte": 30, "marco": "Swing · 1 a 4 semanas (≈30 velas)"},
    "1D": {"yf": "1d", "period": "5y", "resample": None, "bars_day": 1, "nombre": "Diario",
           "horizonte": 35, "marco": "Mediano-Largo plazo · 1 a 3 meses (24–50 sesiones)"},
    "1W": {"yf": "1wk", "period": "10y", "resample": None, "bars_day": 0.2, "nombre": "Semanal",
           "horizonte": 26, "marco": "Largo plazo · 3 a 12 meses (≈26 semanas)"},
    "1M": {"yf": "1mo", "period": "max", "resample": None, "bars_day": 0.05, "nombre": "Mensual",
           "horizonte": 18, "marco": "Muy largo plazo · 1 a 3 años (≈18 meses)"},
}
INTRADAY = {"10m", "30m", "1h", "4h"}
PROHIBIDAS = {"1m", "2m", "5m", "15m", "90m"}  # nunca se ofrecen (mínimo 10m)
MIN_TF = "10m"


def validate(tf: str) -> str:
    """Devuelve la temporalidad normalizada o lanza error si no está permitida (mínimo 10m)."""
    if tf in PROHIBIDAS or tf not in TIMEFRAMES:
        raise ValueError(f"Temporalidad no permitida: {tf}. La mínima es {MIN_TF}; "
                         f"permitidas: {', '.join(TIMEFRAMES)}.")
    return tf


def marco(tf: str) -> str:
    """Texto del marco temporal para mostrar en widgets e informes."""
    t = TIMEFRAMES[validate(tf)]
    return f"Velas {tf} ({t['nombre']}) · {t['marco']}"


def marco_corto(tf: str) -> str:
    return f"{tf} · {TIMEFRAMES[validate(tf)]['marco']}"


def unidad(tf: str, n: int | float | None = None) -> str:
    """'sesiones' en diario, 'velas' en el resto."""
    word = "sesiones" if tf == "1D" else ("semanas" if tf == "1W" else ("meses" if tf == "1M" else "velas"))
    return word if n is None else f"{int(n)} {word}"


def is_crypto(ticker: str) -> bool:
    return ticker.upper().endswith(("-USD", "-USDT", "-EUR"))


def future_index(last: pd.Timestamp, n: int, tf: str, crypto: bool = False) -> pd.Timestamp:
    """Fecha aproximada de la vela n en el futuro (para dibujar proyecciones)."""
    n = max(1, int(n))
    if tf == "1W":
        return last + pd.Timedelta(weeks=n)
    if tf == "1M":
        return last + pd.DateOffset(months=n)
    if tf == "1D":
        return last + pd.Timedelta(days=n) if crypto else pd.bdate_range(last, periods=n + 1)[-1]
    hours = {"10m": 1 / 6, "30m": 0.5, "1h": 1, "4h": 4}[tf]
    if crypto:
        return last + pd.Timedelta(hours=hours * n)
    # acciones: sesión regular de 9:30 a 16:00 (390 min) → avanzar sin salir del horario de mercado
    step = int(round(hours * 60))
    since_open = (last.hour * 60 + last.minute) - 570
    total = max(0, since_open) + n * step
    days, rem = divmod(total, 390)
    base = pd.bdate_range(last.normalize(), periods=int(days) + 1)[-1]
    return base + pd.Timedelta(minutes=570 + rem)


def rangebreaks(tf: str, crypto: bool = False) -> list[dict]:
    """Huecos del eje X en Plotly (fines de semana y horas sin mercado)."""
    if crypto or tf in ("1W", "1M"):
        return []
    rb = [dict(bounds=["sat", "mon"])]
    if tf in INTRADAY:
        rb.append(dict(bounds=[16, 9.5], pattern="hour"))
    return rb


# ---------------------------------------------------------------- rango visible del gráfico
# Opciones de rango (periodo) por temporalidad de velas y el rango por defecto de cada una.
RANGOS: dict[str, list[str]] = {
    "10m": ["Hoy", "3D", "1S", "2S", "1M"],
    "30m": ["1S", "2S", "1M", "3M"],
    "1h": ["2S", "1M", "3M", "6M"],
    "4h": ["1M", "3M", "6M", "1A"],
    "1D": ["3M", "6M", "1A", "2A", "5A"],
    "1W": ["1A", "2A", "5A", "10A"],
    "1M": ["5A", "10A", "Máx"],
}
RANGO_DEFAULT = {"10m": "3D", "30m": "2S", "1h": "1M", "4h": "3M", "1D": "6M", "1W": "2A", "1M": "10A"}
RANGO_NOMBRE = {"Hoy": "la última sesión", "3D": "3 días", "1S": "1 semana", "2S": "2 semanas", "1M": "1 mes", "3M": "3 meses", "6M": "6 meses", "1A": "1 año",
                "2A": "2 años", "5A": "5 años", "10A": "10 años", "Máx": "Todo el historial"}
_DIAS_BURSATILES = {"Hoy": 1, "3D": 3, "1S": 5, "2S": 10, "1M": 21, "3M": 63, "6M": 126, "1A": 252, "2A": 504, "5A": 1260, "10A": 2520}
_VELAS_DIA_CRIPTO = {"10m": 144, "30m": 48, "1h": 24, "4h": 6, "1D": 1, "1W": 1 / 7, "1M": 1 / 30.4}


def rango_valido(tf: str, rango: str | None) -> str:
    """El rango si existe para esa temporalidad; si no, el rango por defecto."""
    return rango if rango in RANGOS.get(tf, []) else RANGO_DEFAULT.get(tf, "6M")


def rango_velas(tf: str, rango: str, crypto: bool = False, disponibles: int | None = None) -> int:
    """Cantidad de velas que cubre un rango (p. ej. 6M en 1D = 126 velas; en cripto, días corridos)."""
    rango = rango_valido(tf, rango)
    if rango == "Máx":
        n = disponibles or 10_000
    else:
        dias = _DIAS_BURSATILES[rango]
        if crypto:
            n = dias * 365 / 252 * _VELAS_DIA_CRIPTO[tf]
        else:
            n = dias * TIMEFRAMES[tf]["bars_day"]
    n = max(20, int(round(n)))
    return min(n, disponibles) if disponibles else n
