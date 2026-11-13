"""Módulo de opciones: cadena de Alpaca + métricas cuantitativas (PCR, movimiento esperado, muros, GEX, max pain).

Fuentes (Alpaca):
* Cadena:  GET data.alpaca.markets/v1beta1/options/snapshots/{subyacente}  → cotización, último trade, barra diaria
  (volumen), griegas e IV. Feed «indicative» (gratis) salvo que la cuenta tenga OPRA.
* Interés abierto: GET {api|paper-api}.alpaca.markets/v2/options/contracts → open_interest (del cierre anterior).
Si Alpaca no entrega griegas o IV para un contrato, se calculan con Black-Scholes a partir del precio medio.
Ventana: vencimientos de hoy a +45 días y strikes a ±15 % del spot. Caché de 3 minutos por ticker.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import streamlit as st

DIAS_MAX = 45
RANGO_STRIKE = 0.15
TASA = 0.04
MULT = 100
_OCC = re.compile(r"^([A-Z.]+)(\d{6})([CP])(\d{8})$")
_TRADING = ("https://api.alpaca.markets", "https://paper-api.alpaca.markets")


# ------------------------------------------------------------------ Black-Scholes
def _ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _npdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def bs_price(s, k, t, iv, call: bool, r=TASA):
    if t <= 0 or iv <= 0:
        return max(0.0, (s - k) if call else (k - s))
    d1 = (math.log(s / k) + (r + 0.5 * iv * iv) * t) / (iv * math.sqrt(t))
    d2 = d1 - iv * math.sqrt(t)
    if call:
        return s * _ncdf(d1) - k * math.exp(-r * t) * _ncdf(d2)
    return k * math.exp(-r * t) * _ncdf(-d2) - s * _ncdf(-d1)


def bs_greeks(s, k, t, iv, call: bool, r=TASA) -> dict:
    t = max(t, 1 / 365 / 4)
    if iv <= 0 or s <= 0 or k <= 0:
        return {"delta": np.nan, "gamma": np.nan, "theta": np.nan, "vega": np.nan}
    sq = iv * math.sqrt(t)
    d1 = (math.log(s / k) + (r + 0.5 * iv * iv) * t) / sq
    d2 = d1 - sq
    gamma = _npdf(d1) / (s * sq)
    vega = s * _npdf(d1) * math.sqrt(t) / 100
    if call:
        delta = _ncdf(d1)
        theta = (-s * _npdf(d1) * iv / (2 * math.sqrt(t)) - r * k * math.exp(-r * t) * _ncdf(d2)) / 365
    else:
        delta = _ncdf(d1) - 1
        theta = (-s * _npdf(d1) * iv / (2 * math.sqrt(t)) + r * k * math.exp(-r * t) * _ncdf(-d2)) / 365
    return {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega}


def implied_vol(price, s, k, t, call: bool, r=TASA):
    """IV por bisección (robusta). NaN si el precio no es coherente."""
    if not (price and price > 0 and t > 0):
        return np.nan
    intr = max(0.0, (s - k) if call else (k - s))
    if price < intr - 1e-6:
        return np.nan
    lo, hi = 1e-3, 5.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if bs_price(s, k, t, mid, call, r) > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


# ------------------------------------------------------------------ datos
def parse_occ(sym: str):
    m = _OCC.match(sym)
    if not m:
        return None
    root, ymd, cp, k = m.groups()
    return root, datetime.strptime(ymd, "%y%m%d").date(), "call" if cp == "C" else "put", int(k) / 1000


def _demo() -> bool:
    import os
    return os.environ.get("TRADING_DEMO") == "1"


def _fridays(hoy: date, dias: int) -> list[date]:
    out, d = [], hoy
    while (d - hoy).days <= dias:
        if d.weekday() == 4 and d > hoy:
            out.append(d)
        d = date.fromordinal(d.toordinal() + 1)
    return out


def _demo_chain(ticker: str, spot: float, hoy: date) -> pd.DataFrame:
    """Cadena sintética coherente (Black-Scholes con sonrisa de volatilidad) para el modo demo."""
    rng = np.random.default_rng(sum(map(ord, ticker)))
    paso = 0.5 if spot < 60 else 1 if spot < 150 else 2.5 if spot < 400 else 5
    ks = np.arange(math.floor(spot * (1 - RANGO_STRIKE) / paso) * paso, spot * (1 + RANGO_STRIKE) + paso, paso)
    base_iv = 0.22 + (sum(map(ord, ticker)) % 20) / 100
    filas = []
    muro_c = ks[np.argmin(abs(ks - spot * 1.04))]
    muro_p = ks[np.argmin(abs(ks - spot * 0.96))]
    for ex in _fridays(hoy, DIAS_MAX):
        t = max((ex - hoy).days, 1) / 365
        for k in ks:
            m = math.log(k / spot)
            iv = base_iv * (1 + 1.4 * m * m - 0.35 * m)
            for call in (True, False):
                px = bs_price(spot, k, t, iv, call)
                spr = max(0.01, px * 0.04)
                dist = abs(k - spot) / spot
                oi = int(rng.integers(200, 3000) * math.exp(-dist * 18) * (1 + 6 * ((k == muro_c) if call else (k == muro_p))))
                vol = int(oi * rng.uniform(0.05, 0.6))
                g = bs_greeks(spot, k, t, iv, call)
                filas.append({"symbol": f"{ticker}{ex:%y%m%d}{'C' if call else 'P'}{int(k * 1000):08d}",
                              "type": "call" if call else "put", "exp": ex, "strike": float(k),
                              "bid": round(max(0.0, px - spr / 2), 2), "ask": round(px + spr / 2, 2),
                              "last": round(px, 2), "volume": vol, "oi": oi, "iv": iv, **g})
    return pd.DataFrame(filas)


def _open_interest(ticker: str, gte: date, lte: date, kmin: float, kmax: float) -> dict:
    """{símbolo OCC: interés abierto} desde la API de trading (cuenta real o paper, la que acepte las claves)."""
    import requests
    from . import alpaca
    params = {"underlying_symbols": ticker, "expiration_date_gte": gte.isoformat(),
              "expiration_date_lte": lte.isoformat(), "strike_price_gte": f"{kmin:.2f}",
              "strike_price_lte": f"{kmax:.2f}", "limit": 10000, "status": "active"}
    for base in _TRADING:
        out, p = {}, dict(params)
        try:
            for _ in range(20):
                r = requests.get(base + "/v2/options/contracts", params=p, headers=alpaca._headers(), timeout=20)
                if r.status_code in (401, 403):
                    raise PermissionError
                r.raise_for_status()
                js = r.json()
                for c in js.get("option_contracts") or []:
                    if c.get("open_interest") not in (None, ""):
                        out[c["symbol"]] = int(float(c["open_interest"]))
                tok = js.get("next_page_token")
                if not tok:
                    break
                p["page_token"] = tok
            return out
        except PermissionError:
            continue
        except Exception:
            return out
    return {}


@st.cache_data(ttl=180, show_spinner=False)
def chain(ticker: str, spot: float) -> tuple[pd.DataFrame, dict]:
    """Cadena filtrada (≤ 45 días, ±15 % del spot) con griegas, IV, volumen e interés abierto.
    Devuelve (df, info) con info = {fuente, feed, oi_disponible, timestamp_utc}."""
    from zoneinfo import ZoneInfo
    hoy = datetime.now(ZoneInfo("America/New_York")).date()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    kmin, kmax = spot * (1 - RANGO_STRIKE), spot * (1 + RANGO_STRIKE)
    if _demo():
        df = _demo_chain(ticker, spot, hoy)
        info = {"fuente": "demo (sintética)", "feed": "demo", "oi_disponible": True, "timestamp_utc": ts}
    else:
        from . import alpaca
        if not alpaca.available():
            raise RuntimeError("Faltan las claves de Alpaca (ALPACA_API_KEY / ALPACA_SECRET_KEY).")
        lte = date.fromordinal(hoy.toordinal() + DIAS_MAX)
        params = {"expiration_date_gte": hoy.isoformat(), "expiration_date_lte": lte.isoformat(),
                  "strike_price_gte": f"{kmin:.2f}", "strike_price_lte": f"{kmax:.2f}", "limit": 1000}
        snaps, feed = {}, "opra"
        for fd in ("opra", "indicative"):
            try:
                p = dict(params, feed=fd)
                snaps = {}
                for _ in range(30):
                    js = alpaca._get(f"/v1beta1/options/snapshots/{ticker.upper()}", p)
                    snaps.update(js.get("snapshots") or {})
                    tok = js.get("next_page_token")
                    if not tok:
                        break
                    p["page_token"] = tok
                feed = fd
                break
            except Exception as e:
                if fd == "indicative":
                    raise RuntimeError(f"Alpaca no entregó la cadena de opciones: {e}")
        oi = _open_interest(ticker.upper(), hoy, lte, kmin, kmax)
        filas = []
        for sym, sn in snaps.items():
            occ = parse_occ(sym)
            if not occ:
                continue
            _, ex, tp, k = occ
            q, tr, bar, gk = (sn.get("latestQuote") or {}), (sn.get("latestTrade") or {}), \
                (sn.get("dailyBar") or {}), (sn.get("greeks") or {})
            filas.append({"symbol": sym, "type": tp, "exp": ex, "strike": k,
                          "bid": q.get("bp"), "ask": q.get("ap"), "last": tr.get("p"),
                          "volume": bar.get("v") or 0, "oi": oi.get(sym, np.nan),
                          "iv": sn.get("impliedVolatility"), "delta": gk.get("delta"), "gamma": gk.get("gamma"),
                          "theta": gk.get("theta"), "vega": gk.get("vega")})
        df = pd.DataFrame(filas)
        info = {"fuente": "Alpaca", "feed": feed, "oi_disponible": bool(oi), "timestamp_utc": ts}
    if df.empty:
        return df, info
    df = df.sort_values(["exp", "strike", "type"]).reset_index(drop=True)
    for c in ("bid", "ask", "last", "volume", "oi", "iv", "delta", "gamma", "theta", "vega"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["dte"] = [(e - hoy).days for e in df["exp"]]
    df["mid"] = np.where((df["bid"] > 0) & (df["ask"] > 0), (df["bid"] + df["ask"]) / 2, df["last"])
    # completar IV y griegas faltantes con Black-Scholes
    for i in df.index[df["iv"].isna() | df["gamma"].isna() | df["delta"].isna()]:
        r = df.loc[i]
        t = max(r["dte"], 0.25) / 365
        iv = r["iv"] if pd.notna(r["iv"]) else implied_vol(r["mid"], spot, r["strike"], t, r["type"] == "call")
        if pd.isna(iv):
            continue
        g = bs_greeks(spot, r["strike"], t, iv, r["type"] == "call")
        df.loc[i, "iv"] = iv
        for kk, vv in g.items():
            if pd.isna(df.loc[i, kk]):
                df.loc[i, kk] = vv
    df["volume"] = df["volume"].fillna(0)
    return df, info


# ------------------------------------------------------------------ métricas
def etiqueta_venc(ex: date) -> str:
    meses = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]
    return f"{meses[ex.month - 1]} {ex.day} '{ex:%y}"


def _atm(df: pd.DataFrame, spot: float) -> float:
    ks = df["strike"].unique()
    return float(ks[np.argmin(abs(ks - spot))])


def expected_move(df_exp: pd.DataFrame, spot: float) -> float | None:
    """(Call ATM + Put ATM) × 0.85 con precios medios."""
    if df_exp.empty:
        return None
    k = _atm(df_exp, spot)
    c = df_exp[(df_exp["strike"] == k) & (df_exp["type"] == "call")]["mid"]
    p = df_exp[(df_exp["strike"] == k) & (df_exp["type"] == "put")]["mid"]
    if c.empty or p.empty or pd.isna(c.iloc[0]) or pd.isna(p.iloc[0]):
        return None
    return float((c.iloc[0] + p.iloc[0]) * 0.85)


def max_pain(df_exp: pd.DataFrame) -> float | None:
    """Strike donde el valor intrínseco total pagado a los compradores (por interés abierto) es mínimo."""
    d = df_exp.dropna(subset=["oi"])
    if d.empty or d["oi"].sum() == 0:
        return None
    ks = np.sort(d["strike"].unique())
    calls, puts = d[d["type"] == "call"], d[d["type"] == "put"]
    dolor = [float((np.maximum(0, s - calls["strike"]) * calls["oi"]).sum()
                   + (np.maximum(0, puts["strike"] - s) * puts["oi"]).sum()) for s in ks]
    return float(ks[int(np.argmin(dolor))])


def gex_por_strike(df: pd.DataFrame, spot: float) -> pd.Series:
    """GEX neto por strike: Γ × OI × 100 × S² × 0.01 (calls +, puts −), en dólares por 1 % de movimiento."""
    d = df.dropna(subset=["gamma", "oi"])
    sg = np.where(d["type"] == "call", 1.0, -1.0)
    g = d["gamma"] * d["oi"] * MULT * spot ** 2 * 0.01 * sg
    return g.groupby(d["strike"]).sum().sort_index()


def gamma_flip(df: pd.DataFrame, spot: float) -> float | None:
    """Precio del subyacente donde el GEX total cambia de signo (recalculando gamma con la IV de cada contrato)."""
    d = df.dropna(subset=["iv", "oi"])
    d = d[(d["oi"] > 0) & (d["iv"] > 0)]
    if d.empty:
        return None
    ks, ivs, ois = d["strike"].to_numpy(float), d["iv"].to_numpy(float), d["oi"].to_numpy(float)
    ts = np.maximum(d["dte"].to_numpy(float), 0.25) / 365
    sg = np.where(d["type"].to_numpy() == "call", 1.0, -1.0)
    grid = np.linspace(spot * 0.85, spot * 1.15, 121)
    tot = []
    for s in grid:
        sq = ivs * np.sqrt(ts)
        d1 = (np.log(s / ks) + (TASA + 0.5 * ivs ** 2) * ts) / sq
        gam = np.exp(-0.5 * d1 ** 2) / np.sqrt(2 * np.pi) / (s * sq)
        tot.append(float((gam * ois * MULT * s ** 2 * 0.01 * sg).sum()))
    tot = np.array(tot)
    cruces = np.where(np.sign(tot[:-1]) != np.sign(tot[1:]))[0]
    if not len(cruces):
        return None
    i = cruces[np.argmin(abs(grid[cruces] - spot))]
    x0, x1, y0, y1 = grid[i], grid[i + 1], tot[i], tot[i + 1]
    return float(x0 - y0 * (x1 - x0) / (y1 - y0))


def muros(df: pd.DataFrame, n: int = 2) -> dict:
    """Top-n strikes por interés abierto en calls (resistencias) y puts (soportes); sin OI se usa el volumen."""
    col = "oi" if df["oi"].notna().any() and df["oi"].fillna(0).sum() > 0 else "volume"
    out = {}
    for tp, key in (("call", "call_walls"), ("put", "put_walls")):
        g = df[df["type"] == tp].groupby("strike").agg(open_interest=("oi", "sum"), volume=("volume", "sum"))
        g = g.sort_values("open_interest" if col == "oi" else "volume", ascending=False).head(n)
        out[key] = [{"strike": float(k), "open_interest": int(r["open_interest"]) if pd.notna(r["open_interest"]) else None,
                     "volume": int(r["volume"])} for k, r in g.iterrows()]
    out["criterio"] = "interés abierto" if col == "oi" else "volumen (interés abierto no disponible)"
    return out


def _fmt_m(v: float) -> str:
    a = abs(v)
    s = f"{a / 1e9:.2f}B" if a >= 1e9 else f"{a / 1e6:.0f}M" if a >= 1e6 else f"{a / 1e3:.0f}K"
    return ("+" if v >= 0 else "−") + "$" + s


def resumen(df: pd.DataFrame, spot: float) -> dict:
    """Métricas del conjunto (≤ 45 días) y del vencimiento más próximo."""
    cv, pv = df[df["type"] == "call"]["volume"].sum(), df[df["type"] == "put"]["volume"].sum()
    co, po = df[df["type"] == "call"]["oi"].sum(), df[df["type"] == "put"]["oi"].sum()
    exps = sorted(df["exp"].unique())
    near = exps[0]
    dn = df[df["exp"] == near]
    if dn["dte"].iloc[0] == 0 and len(exps) > 1:  # el mismo día: usar el siguiente para el movimiento esperado
        near = exps[1]
        dn = df[df["exp"] == near]
    gex = gex_por_strike(df, spot)
    tot = float(gex.sum()) if len(gex) else 0.0
    atm = _atm(dn, spot)
    iv_atm = dn[dn["strike"] == atm]["iv"].mean()
    return {
        "nearest_expiration": etiqueta_venc(near), "dte": int(dn["dte"].iloc[0]),
        "iv_rank_or_avg_iv": None if pd.isna(iv_atm) else round(float(iv_atm) * 100, 1),
        "expected_move_usd": None if (em := expected_move(dn, spot)) is None else round(em, 2),
        "max_pain": max_pain(dn),
        "net_gamma_exposure_gex": f"{'Positivo' if tot >= 0 else 'Negativo'} ({_fmt_m(tot)})",
        "gex_total": tot, "gamma_flip_level": None if (gf := gamma_flip(df, spot)) is None else round(gf, 2),
        "pcr_volumen": round(float(pv / cv), 2) if cv else None,
        "pcr_open_interest": round(float(po / co), 2) if co else None,
    }


def candidatos(df: pd.DataFrame, spot: float, sesgo: str, n: int = 4) -> list[dict]:
    """Contratos líquidos para el sesgo dado: delta 0.30–0.60, 14–45 días (o el mayor disponible), spread ≤ 15 %."""
    tp = "call" if sesgo == "alcista" else "put"
    d = df[(df["type"] == tp) & (df["bid"] > 0) & (df["ask"] > 0)].copy()
    if d.empty:
        return []
    d = d[d["dte"] >= min(14, d["dte"].max())]
    d["spread"] = (d["ask"] - d["bid"]) / d["mid"]
    d["ad"] = d["delta"].abs()
    d = d[(d["ad"] >= 0.30) & (d["ad"] <= 0.60) & (d["spread"] <= 0.15)]
    if d.empty:
        return []
    liq = np.log1p(d["oi"].fillna(0) + d["volume"])
    d["score"] = -abs(d["ad"] - 0.45) * 4 + liq / max(liq.max(), 1) - d["spread"] * 2 - abs(d["dte"] - 30) / 60
    d = d.sort_values("score", ascending=False).head(n)
    return [{"target_expiration_tab": etiqueta_venc(r["exp"]), "exp": r["exp"].isoformat(), "dte": int(r["dte"]),
             "option_type": tp.upper(), "strike": float(r["strike"]), "bid": float(r["bid"]), "ask": float(r["ask"]),
             "delta": round(float(r["delta"]), 3), "iv": round(float(r["iv"]) * 100, 1) if pd.notna(r["iv"]) else None,
             "open_interest": None if pd.isna(r["oi"]) else int(r["oi"]), "volume": int(r["volume"]),
             "spread_pct": round(float(r["spread"]) * 100, 1)} for _, r in d.iterrows()]


def confluencias(walls: dict, vp: dict | None, spot: float, tol: float = 0.01) -> list[dict]:
    """Muros de opciones que coinciden (±1 %) con nodos del VRVP (POC / VAH / VAL)."""
    out = []
    if not vp:
        return out
    nodos = {k.upper(): float(vp[k]) for k in ("poc", "vah", "val") if vp.get(k) is not None}
    for key, tipo in (("call_walls", "Muro de calls"), ("put_walls", "Muro de puts")):
        for w in walls.get(key, []):
            for nom, lv in nodos.items():
                if abs(w["strike"] - lv) / spot <= tol:
                    out.append({"strike": w["strike"], "tipo": tipo, "nodo_vrvp": nom, "nivel_vrvp": round(lv, 2),
                                "efecto": "freno" if (key == "call_walls") == (w["strike"] > spot) else "aceleración al romper"})
    return out


def destacar(cands: dict, escenario: str, adx: dict, walls: dict, conf: list, spot: float) -> dict | None:
    """Contrato destacado por reglas: sigue al escenario cuantitativo (70 %); el flujo de opciones lo valida (30 %)."""
    if escenario not in ("Alcista", "Bajista"):
        return None
    lst = cands.get("alcista" if escenario == "Alcista" else "bajista") or []
    if not lst:
        return None
    c = dict(lst[0])
    muro = (walls.get("call_walls") or [{}])[0].get("strike") if escenario == "Alcista" else \
        (walls.get("put_walls") or [{}])[0].get("strike")
    partes = [f"Escenario {escenario.lower()} del motor cuantitativo",
              f"ADX {adx.get('adx', '—')} {'sobre' if adx.get('regimen') == 'tendencia' else 'bajo'} el nivel clave 23"]
    if muro:
        partes.append(f"{'muro de calls' if escenario == 'Alcista' else 'muro de puts'} en {muro:g} como objetivo / freno")
    if conf:
        partes.append("confluencia " + ", ".join(f"{x['tipo'].lower()} {x['strike']:g} = {x['nodo_vrvp']}" for x in conf[:2]))
    c.update({"action_trigger": "pulse_glow_animation", "rationale": "; ".join(partes) + "."})
    return c
