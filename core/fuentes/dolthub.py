"""Cliente de las bases públicas de DoltHub (SQL por HTTP, sin cuenta ni clave).

post-no-preference/options  → option_chain (bid, ask, IV, griegas por contrato y día), volatility_history
post-no-preference/earnings → calendario de resultados, estimaciones de BPA, estados financieros
"""
from __future__ import annotations

import threading
import time

import pandas as pd
import requests

API = "https://www.dolthub.com/api/v1alpha1/post-no-preference/{repo}/master"
_ULT = [0.0]
_CERROJO = threading.Lock()


def consulta(repo: str, sql: str, reintentos: int = 3) -> pd.DataFrame:
    """Ejecuta una consulta SQL de solo lectura. Devuelve un DataFrame (vacío si no hay filas)."""
    for i in range(reintentos):
        with _CERROJO:  # como mucho ~4 consultas nuevas por segundo, aunque haya varios hilos
            espera = 0.25 - (time.time() - _ULT[0])
            if espera > 0:
                time.sleep(espera)
            _ULT[0] = time.time()
        try:
            r = requests.get(API.format(repo=repo), params={"q": sql}, timeout=120)
            js = r.json()
        except Exception as e:
            if i == reintentos - 1:
                raise RuntimeError(f"DoltHub no respondió: {e}")
            time.sleep(3 * (i + 1))
            continue
        st = js.get("query_execution_status")
        if st not in ("Success", "RowLimit"):
            if i == reintentos - 1:
                raise RuntimeError(f"DoltHub: {st} · {js.get('query_execution_message', '')[:200]}")
            time.sleep(3 * (i + 1))
            continue
        df = pd.DataFrame(js.get("rows") or [])
        df.attrs["estado"] = st
        return df
    return pd.DataFrame()


def paginado(repo: str, sql: str, por_pagina: int = 1000, max_paginas: int = 200) -> pd.DataFrame:
    """Consulta con LIMIT/OFFSET (la API devuelve un máximo de filas por respuesta)."""
    partes = []
    for p in range(max_paginas):
        d = consulta(repo, f"{sql} LIMIT {por_pagina} OFFSET {p * por_pagina}")
        if d.empty:
            break
        partes.append(d)
        if len(d) < por_pagina:
            break
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
