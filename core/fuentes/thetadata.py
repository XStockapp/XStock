"""Cliente de ThetaData (plan gratuito: EOD de opciones, ~1 año). Requiere el Theta Terminal v3 corriendo en la
misma máquina (programa Java oficial que se autentica con la cuenta y expone http://127.0.0.1:25503/v3)."""
from __future__ import annotations

import io
import time

import pandas as pd
import requests

BASE = "http://127.0.0.1:25503/v3"


def esperar(segundos: int = 120) -> bool:
    fin = time.time() + segundos
    while time.time() < fin:
        try:
            requests.get(f"{BASE}/option/list/symbols", timeout=5)
            return True
        except Exception:
            time.sleep(3)
    return False


def get(ruta: str, **params) -> tuple[int, pd.DataFrame, str]:
    """(código HTTP, tabla, texto de error). ThetaData responde CSV por defecto."""
    r = requests.get(f"{BASE}/{ruta}", params=params, timeout=180)
    if r.status_code != 200:
        return r.status_code, pd.DataFrame(), r.text[:300]
    t = r.text
    try:
        return 200, pd.read_csv(io.StringIO(t)), ""
    except Exception:
        return 200, pd.DataFrame(), t[:300]


def eod(symbol: str, expiration: str, inicio: str, fin: str) -> pd.DataFrame:
    """EOD de todos los contratos de un vencimiento (`expiration`='*' para todos) entre dos fechas AAAAMMDD."""
    _, d, _ = get("option/history/eod", symbol=symbol, expiration=expiration, start_date=inicio, end_date=fin)
    return d


def interes_abierto(symbol: str, expiration: str, fecha: str) -> pd.DataFrame:
    _, d, _ = get("option/history/open_interest", symbol=symbol, expiration=expiration, date=fecha)
    return d
