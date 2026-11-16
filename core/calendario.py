"""Calendario de la bolsa de Nueva York (NYSE/Nasdaq): feriados y cierres anticipados, calculados por sus reglas.

Por qué importa: la theta de una opción se descuenta por días de CALENDARIO (fines de semana y feriados incluidos),
pero el precio solo puede moverse en SESIONES hábiles. Un feriado dentro de la vida de la opción le quita una sesión
para llegar al objetivo sin quitarle desgaste temporal. Por eso la probabilidad de alcanzar el objetivo se calcula con
la varianza de las sesiones hábiles (σ·√(sesiones/252)) y el precio Black-Scholes sigue con días de calendario/365.

Feriados (regla de observancia: sábado → viernes anterior, domingo → lunes siguiente):
Año Nuevo, Martin Luther King (3.er lunes de enero), Presidentes (3.er lunes de febrero), Viernes Santo,
Memorial Day (último lunes de mayo), Juneteenth (19-jun, desde 2022), Independencia (4-jul), Trabajo (1.er lunes de
septiembre), Acción de Gracias (4.º jueves de noviembre) y Navidad. Cierre a las 13:00: 3-jul (si es hábil), el día
siguiente a Acción de Gracias y el 24-dic (si es hábil).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache

NOMBRES = {"anio_nuevo": "Año Nuevo", "mlk": "Día de Martin Luther King", "presidentes": "Día de los Presidentes",
           "viernes_santo": "Viernes Santo", "memorial": "Memorial Day", "juneteenth": "Juneteenth",
           "independencia": "Día de la Independencia", "trabajo": "Día del Trabajo",
           "accion_gracias": "Acción de Gracias", "navidad": "Navidad"}


def _pascua(y: int) -> date:
    """Domingo de Pascua (algoritmo anónimo gregoriano)."""
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    mes = (h + l_ - 7 * m + 114) // 31
    dia = ((h + l_ - 7 * m + 114) % 31) + 1
    return date(y, mes, dia)


def _n_esimo(y, mes, dow, n):
    d = date(y, mes, 1)
    d += timedelta(days=(dow - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _ultimo(y, mes, dow):
    d = date(y, mes + 1, 1) - timedelta(days=1) if mes < 12 else date(y, 12, 31)
    return d - timedelta(days=(d.weekday() - dow) % 7)


def _observado(d: date) -> date:
    return d - timedelta(days=1) if d.weekday() == 5 else d + timedelta(days=1) if d.weekday() == 6 else d


@lru_cache(maxsize=64)
def feriados(y: int) -> dict[date, str]:
    out = {}
    an = date(y, 1, 1)
    if an.weekday() != 5:  # Año Nuevo en sábado no se observa el viernes anterior (cae en el año anterior)
        out[_observado(an)] = NOMBRES["anio_nuevo"]
    out[_n_esimo(y, 1, 0, 3)] = NOMBRES["mlk"]
    out[_n_esimo(y, 2, 0, 3)] = NOMBRES["presidentes"]
    out[_pascua(y) - timedelta(days=2)] = NOMBRES["viernes_santo"]
    out[_ultimo(y, 5, 0)] = NOMBRES["memorial"]
    if y >= 2022:
        out[_observado(date(y, 6, 19))] = NOMBRES["juneteenth"]
    out[_observado(date(y, 7, 4))] = NOMBRES["independencia"]
    out[_n_esimo(y, 9, 0, 1)] = NOMBRES["trabajo"]
    out[_n_esimo(y, 11, 3, 4)] = NOMBRES["accion_gracias"]
    out[_observado(date(y, 12, 25))] = NOMBRES["navidad"]
    return out


@lru_cache(maxsize=64)
def cierres_anticipados(y: int) -> dict[date, str]:
    out = {}
    j3 = date(y, 7, 3)
    if j3.weekday() < 5 and j3 not in feriados(y):
        out[j3] = "Víspera de la Independencia (cierre 13:00)"
    out[_n_esimo(y, 11, 3, 4) + timedelta(days=1)] = "Día siguiente a Acción de Gracias (cierre 13:00)"
    d24 = date(y, 12, 24)
    if d24.weekday() < 5 and d24 not in feriados(y):
        out[d24] = "Nochebuena (cierre 13:00)"
    return out


def es_feriado(d: date) -> str | None:
    return feriados(d.year).get(d)


def es_habil(d: date) -> bool:
    return d.weekday() < 5 and d not in feriados(d.year)


def cierre_anticipado(d: date) -> str | None:
    return cierres_anticipados(d.year).get(d)


@lru_cache(maxsize=4096)
def sesiones(desde: date, hasta: date) -> int:
    """Sesiones hábiles en (desde, hasta]: las que quedan para que el precio se mueva hasta `hasta`."""
    n, d = 0, desde
    while d < hasta:
        d += timedelta(days=1)
        if es_habil(d):
            n += 1
    return n


@lru_cache(maxsize=4096)
def feriados_entre(desde: date, hasta: date) -> tuple[tuple[date, str], ...]:
    out = []
    for y in range(desde.year, hasta.year + 1):
        out += [(d, n) for d, n in feriados(y).items() if desde < d <= hasta and d.weekday() < 5]
    return tuple(sorted(out))


def proximos(desde: date, n: int = 3) -> list[tuple[date, str]]:
    out = []
    for y in (desde.year, desde.year + 1):
        out += [(d, nm) for d, nm in sorted(feriados(y).items()) if d >= desde]
        out += [(d, nm) for d, nm in sorted(cierres_anticipados(y).items()) if d >= desde]
    return sorted(out)[:n]


def hoy_ny() -> date:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/New_York")).date()
