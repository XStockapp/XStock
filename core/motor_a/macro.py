"""Bloque macro del Motor A: ciclo de la Reserva Federal (FOMC) y tasas.

Las fechas de las reuniones programadas se publican con meses de antelación, así que «días hasta la próxima reunión»
no mira el futuro. Fechas = día del anuncio (2.º día de la reunión, 2:00 p.m. ET), verificadas en federalreserve.gov
(calendarios 2021-2027 e históricos 2016-2020). * = reunión con proyecciones económicas (SEP / dot plot).
Marzo 2020: la reunión programada del 17-18 se canceló; hubo anuncios no programados el 3 y el 15 de marzo.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

_FOMC = """
2016-01-27 2016-03-16* 2016-04-27 2016-06-15* 2016-07-27 2016-09-21* 2016-11-02 2016-12-14*
2017-02-01 2017-03-15* 2017-05-03 2017-06-14* 2017-07-26 2017-09-20* 2017-11-01 2017-12-13*
2018-01-31 2018-03-21* 2018-05-02 2018-06-13* 2018-08-01 2018-09-26* 2018-11-08 2018-12-19*
2019-01-30 2019-03-20* 2019-05-01 2019-06-19* 2019-07-31 2019-09-18* 2019-10-30 2019-12-11*
2020-01-29 2020-03-18 2020-04-29 2020-06-10* 2020-07-29 2020-09-16* 2020-11-05 2020-12-16*
2021-01-27 2021-03-17* 2021-04-28 2021-06-16* 2021-07-28 2021-09-22* 2021-11-03 2021-12-15*
2022-01-26 2022-03-16* 2022-05-04 2022-06-15* 2022-07-27 2022-09-21* 2022-11-02 2022-12-14*
2023-02-01 2023-03-22* 2023-05-03 2023-06-14* 2023-07-26 2023-09-20* 2023-11-01 2023-12-13*
2024-01-31 2024-03-20* 2024-05-01 2024-06-12* 2024-07-31 2024-09-18* 2024-11-07 2024-12-18*
2025-01-29 2025-03-19* 2025-05-07 2025-06-18* 2025-07-30 2025-09-17* 2025-10-29 2025-12-10*
2026-01-28 2026-03-18* 2026-04-29 2026-06-17* 2026-07-29 2026-09-16* 2026-10-28 2026-12-09*
2027-01-27 2027-03-17 2027-04-28 2027-06-09 2027-07-28 2027-09-15 2027-10-27 2027-11-17
"""
PROGRAMADAS = [(pd.Timestamp(x.rstrip("*")), x.endswith("*")) for x in _FOMC.split()]
NO_PROGRAMADAS = [pd.Timestamp("2020-03-03"), pd.Timestamp("2020-03-15")]  # recortes de emergencia
FRED_DGS2 = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2"


def anuncios() -> pd.DatetimeIndex:
    """Días con anuncio de política monetaria (programados realizados + no programados)."""
    hechos = [d for d, _ in PROGRAMADAS if d != pd.Timestamp("2020-03-18")]
    return pd.DatetimeIndex(sorted(hechos + NO_PROGRAMADAS))


def _dias_habiles(a: pd.Timestamp, b: pd.Timestamp) -> int:
    return int(np.busday_count(a.date(), b.date()))


def descargar_dgs2() -> pd.Series | None:
    """Rendimiento del bono del Tesoro a 2 años (FRED, diario, sin clave)."""
    try:
        import io

        import requests
        t = requests.get(FRED_DGS2, timeout=30).text
        df = pd.read_csv(io.StringIO(t))
        df.columns = ["fecha", "dgs2"]
        df["fecha"] = pd.to_datetime(df["fecha"])
        return pd.to_numeric(df.set_index("fecha")["dgs2"], errors="coerce").dropna()
    except Exception:
        return None


def variables(spy: pd.DataFrame, dgs2: pd.Series | None = None) -> pd.DataFrame:
    """Variables macro por fecha (comunes a todas las acciones). Solo usan información disponible al cierre."""
    idx = spy.index
    c = spy["Close"].astype(float)
    r = np.log(c / c.shift())
    s = r.rolling(20, min_periods=20).std()
    prog = [(d, sep) for d, sep in PROGRAMADAS]
    an = anuncios()
    M = pd.DataFrame(index=idx)
    hasta, sep_prox, desde = [], [], []
    for t in idx:
        nxt = next(((d, sep) for d, sep in prog if d >= t), None)
        hasta.append(min(_dias_habiles(t, nxt[0]), 40) if nxt else np.nan)
        sep_prox.append(float(nxt[1]) if nxt else np.nan)
        prev = an[an <= t]
        desde.append(min(_dias_habiles(prev[-1], t), 40) if len(prev) else np.nan)
    M["mac_dias_hasta_fomc"] = hasta
    M["mac_fomc_con_proyecciones"] = sep_prox
    M["mac_dias_desde_fomc"] = desde
    # reacción del mercado al último anuncio (en σ de SPY), conocida al cierre del día del anuncio
    reac = pd.Series(np.nan, index=idx)
    dias = [d for d in an if d in idx]
    for d in dias:
        reac.loc[d] = r.loc[d] / s.loc[d] if s.loc[d] and np.isfinite(s.loc[d]) else np.nan
    M["mac_reaccion_ultimo_fomc"] = reac.ffill()
    if dgs2 is not None and len(dgs2):
        y = dgs2.reindex(idx).ffill()
        M["mac_tasa_2a"] = y
        M["mac_tasa_2a_chg20"] = y - y.shift(20)
        sorpresa = pd.Series(np.nan, index=idx)
        for d in dias:
            i = idx.get_loc(d)
            if i > 0:
                sorpresa.iloc[i] = (y.iloc[i] - y.iloc[i - 1]) * 100  # puntos básicos el día del anuncio
        M["mac_sorpresa_tasa_fomc"] = sorpresa.ffill()
    return M


def sensibilidad_fomc(r_sigma: pd.Series, spy_r_sigma: pd.Series, n: int = 16) -> pd.DataFrame:
    """Cómo reaccionó ESTA acción en los últimos n anuncios (solo pasados): tamaño medio del movimiento en σ y
    si suele moverse con o contra el mercado ese día."""
    an = [d for d in anuncios() if d in r_sigma.index]
    mov = pd.Series(np.nan, index=r_sigma.index)
    con = pd.Series(np.nan, index=r_sigma.index)
    hist_m, hist_c = [], []
    for d in an:
        x, m = r_sigma.get(d), spy_r_sigma.get(d)
        if x is None or not np.isfinite(x):
            continue
        hist_m.append(abs(x))
        if m is not None and np.isfinite(m) and m != 0:
            hist_c.append(x * np.sign(m))
        mov.loc[d] = np.mean(hist_m[-n:])
        con.loc[d] = np.mean(hist_c[-n:]) if hist_c else np.nan
    return pd.DataFrame({"fomc_mov_medio": mov.ffill(), "fomc_con_mercado": con.ffill()})
