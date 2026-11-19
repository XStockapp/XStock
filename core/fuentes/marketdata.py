"""Cliente de MarketData.app: cadenas históricas de opciones (fin de día) con interés abierto, volumen y bid/ask.

Autenticación: variable de entorno MARKETDATA_TOKEN (cabecera Authorization: Bearer).
Endpoint: GET https://api.marketdata.app/v1/options/chain/{symbol}/?date=AAAA-MM-DD&dte=1-45

Limitaciones del histórico (documentación oficial):
  · La IV y las griegas NO se guardan: con `date` vuelven nulas → aquí se calculan con Black-Scholes a partir del
    precio medio (bid/ask), el precio del subyacente y los días al vencimiento (vectorizado).
  · El filtro `delta` no se puede combinar con `date` (error 400) → el filtro 0.10 ≤ |Δ| ≤ 0.90 se aplica aquí,
    después de calcular la delta y antes de guardar.
  · Costo: 1 crédito por cada 1000 contratos históricos (en la práctica ~1 crédito por cadena).
  · Un solo dispositivo: si la IP cambia (cada ejecución de GitHub Actions sale por otra), la API bloquea la cuenta
    5 minutos (HTTP 403). El cliente espera y reintenta; `preparar()` lo resuelve antes de abrir los hilos.
    Mientras corre el backfill no conviene usar el mismo token desde otro equipo.
"""
from __future__ import annotations

import math
import os
import threading
import time

import numpy as np
import pandas as pd
import requests

BASE = "https://api.marketdata.app/v1/options/chain/{symbol}/"
TASA = 0.045
COLUMNAS = "optionSymbol,expiration,side,strike,dte,bid,ask,last,volume,openInterest,underlyingPrice"
DELTA_MIN, DELTA_MAX = 0.10, 0.90
BLOQUEO_IP = 330  # segundos: la API bloquea 5 min al detectar una IP nueva


class SinCreditos(RuntimeError):
    """El saldo diario de créditos está por agotarse: hay que parar limpiamente."""


class SinAcceso(RuntimeError):
    """El plan no da acceso a ese símbolo o fecha (402 sin relación con los créditos): se salta y se sigue."""


class Cliente:
    def __init__(self, token: str | None = None, limite_creditos: int = 95_000, reserva: int = 3_000):
        self.token = (token or os.environ.get("MARKETDATA_TOKEN", "")).strip()
        if not self.token:
            raise RuntimeError("Falta MARKETDATA_TOKEN.")
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {self.token}"
        self.limite = limite_creditos
        self.reserva = reserva
        self.consumidos = 0          # créditos contados por este proceso
        self.restantes: int | None = None  # según la cabecera de la API, si la envía
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ control de créditos
    def _anotar(self, r: requests.Response, filas: int):
        h = {k.lower(): v for k, v in r.headers.items()}
        with self._lock:
            usados = h.get("x-api-ratelimit-consumed")
            self.consumidos += int(usados) if usados and usados.isdigit() else max(1, math.ceil(filas / 1000))
            rest = h.get("x-api-ratelimit-remaining")
            if rest and rest.lstrip("-").isdigit():
                self.restantes = int(rest)

    def queda_saldo(self) -> bool:
        with self._lock:
            if self.restantes is not None and self.restantes <= self.reserva:
                return False
            return self.consumidos < self.limite

    # ------------------------------------------------------------------ consulta
    def preparar(self, symbol: str = "SPY", fecha: str | None = None, log=print):
        """Una consulta sola antes de abrir hilos: si la IP es nueva, espera aquí el bloqueo de 5 minutos una vez."""
        fecha = fecha or (pd.Timestamp.today() - pd.offsets.BDay(3)).date().isoformat()
        for i in range(3):
            r = self.s.get(BASE.format(symbol=symbol), params={"date": fecha, "dte": "30", "strikeLimit": 2,
                                                                "columns": "optionSymbol"}, timeout=60)
            if r.status_code == 403 and "IP address" in r.text:
                log(f"MarketData: IP nueva, la cuenta queda bloqueada 5 min; espero ({i + 1}/3)…")
                time.sleep(BLOQUEO_IP)
                continue
            self._anotar(r, 0)
            if r.status_code >= 400:
                raise RuntimeError(f"MarketData {r.status_code}: {r.text[:200]}")
            return
        raise RuntimeError("MarketData sigue bloqueando por cambio de IP")

    def cadena(self, symbol: str, fecha: str, dte: str = "1-45", reintentos: int = 5) -> pd.DataFrame | None:
        """Cadena de fin de día de `symbol` en `fecha` (AAAA-MM-DD), vencimientos a 1-45 días.
        Devuelve un DataFrame ligero (float32/int32); vacío si ese día no hay datos (feriado); None si la sesión aún no
        está disponible en el plan (el día anterior aparece a las 9:30 ET del día siguiente)."""
        if not self.queda_saldo():
            raise SinCreditos("límite diario de créditos alcanzado")
        params = {"date": fecha, "dte": dte, "columns": COLUMNAS}
        for i in range(reintentos):
            try:
                r = self.s.get(BASE.format(symbol=symbol), params=params, timeout=60)
            except requests.RequestException:
                time.sleep(2 * (i + 1))
                continue
            if r.status_code == 429:
                time.sleep(float(r.headers.get("Retry-After", 5 * (i + 1))))
                continue
            if r.status_code == 403 and "IP address" in r.text:
                time.sleep(BLOQUEO_IP)
                continue
            if r.status_code == 402:
                self._anotar(r, 0)
                txt = r.text[:200]
                if "fully-closed" in txt:
                    return None  # la sesión aún no está disponible en el plan: no se marca, se pide otro día
                if "credit" in txt.lower() or (self.restantes is not None and self.restantes <= self.reserva):
                    raise SinCreditos(f"402: {txt}")
                raise SinAcceso(f"{symbol}: 402 {txt}")
            if r.status_code in (200, 203):
                js = r.json()
                if js.get("s") not in (None, "ok") or not js.get("optionSymbol"):
                    self._anotar(r, 0)
                    return vacia()
                df = a_tabla(js, fecha)
                self._anotar(r, len(df))
                return df
            if r.status_code == 404:  # sin datos para ese símbolo/fecha
                self._anotar(r, 0)
                return vacia()
            if r.status_code >= 500:
                time.sleep(3 * (i + 1))
                continue
            raise RuntimeError(f"MarketData {r.status_code}: {r.text[:200]}")
        raise RuntimeError(f"MarketData no respondió tras {reintentos} intentos ({symbol} {fecha})")


# ------------------------------------------------------------------ conversión y cálculo
ESQUEMA = {"fecha": "int32", "vencimiento": "int32", "dte": "int16", "tipo": "int8", "strike": "float32",
           "bid": "float32", "ask": "float32", "last": "float32", "volumen": "int32", "oi": "int32",
           "subyacente": "float32", "iv": "float32", "delta": "float32"}


def vacia() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=t) for c, t in ESQUEMA.items()})


def _dias(ts) -> np.ndarray:
    """Fechas → días desde 1970 (int32): ocupa 4 bytes por fila en vez de 8 o un texto."""
    return (pd.to_datetime(ts, unit="s", utc=True).tz_convert("America/New_York").normalize().tz_localize(None)
            .values.astype("datetime64[D]").astype("int64")).astype("int32")


def a_tabla(js: dict, fecha: str) -> pd.DataFrame:
    n = len(js.get("optionSymbol") or [])
    if n == 0:
        return vacia()

    def col(k, default=np.nan):
        v = js.get(k)
        return np.asarray(v if v is not None else [default] * n, dtype="float64")

    side = np.asarray(js.get("side") or [""] * n)
    S, K = col("underlyingPrice"), col("strike")
    bid, ask = col("bid"), col("ask")
    dte = col("dte")
    call = side == "call"
    mid = np.where((bid > 0) & (ask > 0), (bid + ask) / 2, np.nan)
    T = np.maximum(dte, 0.5) / 365
    iv = iv_vectorizada(mid, S, K, T, call)
    delta = delta_bs(S, K, T, iv, call)
    d = pd.DataFrame({
        "fecha": np.full(n, np.datetime64(fecha, "D").astype("int64"), dtype="int32"),
        "vencimiento": _dias(js["expiration"]),
        "dte": dte.astype("int16"),
        "tipo": np.where(call, 1, -1).astype("int8"),
        "strike": K.astype("float32"), "bid": bid.astype("float32"), "ask": ask.astype("float32"),
        "last": col("last").astype("float32"),
        "volumen": np.nan_to_num(col("volume", 0)).astype("int32"),
        "oi": np.nan_to_num(col("openInterest", 0)).astype("int32"),
        "subyacente": S.astype("float32"), "iv": iv.astype("float32"), "delta": delta.astype("float32"),
    })
    ad = np.abs(d["delta"])
    return d[(ad >= DELTA_MIN) & (ad <= DELTA_MAX)].reset_index(drop=True)


def _ncdf(x):
    from scipy.special import ndtr
    return ndtr(x)


def _bs(S, K, T, s, call):
    v = s * np.sqrt(T)
    d1 = (np.log(S / K) + (TASA + 0.5 * s * s) * T) / v
    d2 = d1 - v
    c = S * _ncdf(d1) - K * np.exp(-TASA * T) * _ncdf(d2)
    p = c - S + K * np.exp(-TASA * T)
    return np.where(call, c, p)


def iv_vectorizada(precio, S, K, T, call, iters: int = 60) -> np.ndarray:
    """IV por bisección vectorizada (robusta, sin bucles por contrato). NaN si el precio no es coherente."""
    precio, S, K, T = (np.asarray(x, float) for x in (precio, S, K, T))
    lo, hi = np.full(precio.shape, 0.01), np.full(precio.shape, 5.0)
    intr = np.where(call, np.maximum(S - K * np.exp(-TASA * T), 0), np.maximum(K * np.exp(-TASA * T) - S, 0))
    ok = np.isfinite(precio) & np.isfinite(S) & (precio > intr + 1e-6) & (precio < np.where(call, S, K))
    with np.errstate(all="ignore"):
        for _ in range(iters):
            m = (lo + hi) / 2
            alto = _bs(S, K, T, m, call) > precio
            hi = np.where(alto, m, hi)
            lo = np.where(alto, lo, m)
    iv = (lo + hi) / 2
    return np.where(ok & (iv > 0.011) & (iv < 4.99), iv, np.nan)


def delta_bs(S, K, T, iv, call) -> np.ndarray:
    with np.errstate(all="ignore"):
        d1 = (np.log(S / K) + (TASA + 0.5 * iv * iv) * T) / (iv * np.sqrt(T))
        return np.where(call, _ncdf(d1), _ncdf(d1) - 1)
