"""
Paneles de la página inicial: "Tendencias" y "Mayores alzas", para acciones y cripto.

Acciones (Alpaca, plan gratuito):
  * Mayores alzas: screener de movers (/v1beta1/screener/stocks/movers), filtrando precios < $2
    y warrants/derechos/unidades.
  * Tendencias: las más operadas (/v1beta1/screener/stocks/most-actives por número de operaciones),
    ordenadas por volumen en dólares del día con snapshots IEX.
  * Nombres de las empresas: API de activos de Alpaca, con caché de 24 h.
  * Respaldo si Alpaca falla: screener de Finviz ("Top Gainers" y "Most Active").
Cripto (CoinGecko, sin clave): /search/trending y las mayores subidas 24 h entre las 250 más grandes.

Cada función devuelve una lista de filas {ticker, nombre, precio, var, logo}.
"""
from __future__ import annotations

import re
import time

import requests

from . import alpaca
from .crypto import EXCLUIR, _get as _cg

LOGO_ACCION = "https://financialmodelingprep.com/image-stock/{}.png"
TRADING_HOSTS = ["https://paper-api.alpaca.markets", "https://api.alpaca.markets"]
_NOMBRES: dict[str, tuple[float, str]] = {}


def _accion_valida(sym: str, precio: float | None) -> bool:
    """Descarta precios < $2 y warrants, derechos y unidades (p. ej. ABCDW, ABCDR, ABCDU, ABC.WS)."""
    if not sym or precio is None or precio < 2:
        return False
    if not re.fullmatch(r"[A-Z]{1,5}(\.[A-Z])?", sym):
        return False
    return not (len(sym) == 5 and sym[-1] in "WRU")


def nombres(symbols: list[str]) -> dict[str, str]:
    """Nombre de cada empresa desde la API de activos de Alpaca (caché de 24 h)."""
    out, now = {}, time.time()
    for s in symbols:
        hit = _NOMBRES.get(s)
        if hit and hit[0] > now:
            out[s] = hit[1]
            continue
        name = None
        for host in TRADING_HOSTS:
            try:
                r = requests.get(f"{host}/v2/assets/{s}", headers=alpaca._headers(), timeout=8)
                if r.status_code == 200:
                    name = _limpiar_nombre(r.json().get("name") or "")
                    break
            except Exception:
                continue
        out[s] = name or s
        _NOMBRES[s] = (now + 86400, out[s])
    return out


def _limpiar_nombre(n: str) -> str:
    n = re.sub(r"\s+(Common Stock|Class [A-C] Common Stock|Ordinary Shares|American Depositary Shares).*$", "", n,
               flags=re.I)
    return n.replace(", Inc.", " Inc.").strip()


def _row(t, nombre, precio, var, logo):
    return {"ticker": t, "nombre": nombre or t, "precio": float(precio) if precio is not None else None,
            "var": float(var) if var is not None else None, "logo": logo}


# ---------------------------------------------------------------- acciones
def acciones_alzas(n: int = 5) -> list[dict]:
    try:
        js = alpaca._get("/v1beta1/screener/stocks/movers", {"top": 50})
        rows = [g for g in js.get("gainers") or [] if _accion_valida(g.get("symbol"), g.get("price"))][:n]
        if not rows:
            raise alpaca.AlpacaError("sin movers")
        nm = nombres([g["symbol"] for g in rows])
        return [_row(g["symbol"], nm.get(g["symbol"]), g.get("price"), g.get("percent_change"),
                     LOGO_ACCION.format(g["symbol"])) for g in rows]
    except Exception:
        return _finviz("Top Gainers", n)


def acciones_tendencias(n: int = 5) -> list[dict]:
    try:
        js = alpaca._get("/v1beta1/screener/stocks/most-actives", {"by": "trades", "top": 40})
        syms = [a["symbol"] for a in js.get("most_actives") or [] if a.get("symbol")]
        if not syms:
            raise alpaca.AlpacaError("sin most-actives")
        snap = alpaca._get("/v2/stocks/snapshots", {"symbols": ",".join(syms), "feed": "iex"})
        cand = []
        for s in syms:
            sn = snap.get(s) or {}
            day, prev = sn.get("dailyBar") or {}, sn.get("prevDailyBar") or {}
            px = (sn.get("latestTrade") or {}).get("p") or day.get("c")
            if not _accion_valida(s, px) or not prev.get("c"):
                continue
            # volumen en dólares del día (IEX); si el día aún no abre, el de la sesión anterior
            dv = (day.get("v") or 0) * (day.get("vw") or px) or (prev.get("v") or 0) * (prev.get("vw") or px)
            cand.append((dv, s, px, (px / prev["c"] - 1) * 100))
        cand.sort(reverse=True)
        cand = cand[:n]
        if not cand:
            raise alpaca.AlpacaError("sin snapshots")
        nm = nombres([c[1] for c in cand])
        return [_row(s, nm.get(s), px, var, LOGO_ACCION.format(s)) for _, s, px, var in cand]
    except Exception:
        return _finviz("Most Active", n)


def _finviz(signal: str, n: int) -> list[dict]:
    from .finviz import screener_df
    df = screener_df(signal, {"Price": "Over $2"}, limit=n * 4)
    if df is None or df.empty:
        return []
    if signal == "Top Gainers":
        df = df.sort_values("Change", ascending=False)
    out = []
    for _, r in df.iterrows():
        t = str(r["Ticker"])
        if not _accion_valida(t, r.get("Price")):
            continue
        ch = r.get("Change")
        out.append(_row(t, r.get("Company"), r.get("Price"), ch * 100 if ch is not None and abs(ch) < 5 else ch,
                        LOGO_ACCION.format(t)))
        if len(out) >= n:
            break
    return out


# ---------------------------------------------------------------- cripto
def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace("$", "").replace(",", "").strip())
    except Exception:
        return None


def cripto_tendencias(n: int = 5) -> list[dict]:
    js = _cg("/search/trending", {})
    out = []
    for c in js.get("coins") or []:
        it = c.get("item") or {}
        sym = (it.get("symbol") or "").upper()
        if not sym or sym in EXCLUIR:
            continue
        d = it.get("data") or {}
        var = d.get("price_change_percentage_24h")
        var = var.get("usd") if isinstance(var, dict) else var
        out.append(_row(f"{sym}-USD", it.get("name"), _num(d.get("price")), _num(var), it.get("small") or it.get("thumb")))
        if len(out) >= n:
            break
    return out


def cripto_alzas(n: int = 5) -> list[dict]:
    rows = _cg("/coins/markets", {"vs_currency": "usd", "order": "market_cap_desc", "per_page": 250, "page": 1,
                                  "price_change_percentage": "24h"})
    rows = [r for r in rows if (r.get("symbol") or "").upper() not in EXCLUIR
            and (r.get("total_volume") or 0) >= 5e6 and r.get("price_change_percentage_24h") is not None]
    rows.sort(key=lambda r: -r["price_change_percentage_24h"])
    return [_row(f"{r['symbol'].upper()}-USD", r.get("name"), r.get("current_price"), r.get("price_change_percentage_24h"),
                 r.get("image")) for r in rows[:n]]


# ---------------------------------------------------------------- modo demo
def demo(tipo: str, mercado: str) -> list[dict]:
    if mercado == "Cripto":
        base = [("BTC-USD", "Bitcoin", 68420.5, 2.1), ("ETH-USD", "Ethereum", 3550.2, 3.4), ("SOL-USD", "Solana", 182.3, 6.8),
                ("XRP-USD", "XRP", 0.62, -1.2), ("DOGE-USD", "Dogecoin", 0.165, 9.5)]
    else:
        base = [("NVDA", "NVIDIA Corp.", 188.72, 2.7), ("TSLA", "Tesla Inc.", 251.4, -1.9), ("AAPL", "Apple Inc.", 229.87, 1.2),
                ("AMD", "Advanced Micro Devices", 162.1, 4.4), ("PLTR", "Palantir Technologies", 41.3, 7.9)]
    if tipo == "alzas":
        base = sorted(base, key=lambda r: -r[3])
    return [_row(t, nm, px, v, None) for t, nm, px, v in base]
