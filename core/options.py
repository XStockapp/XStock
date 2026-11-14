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


def _demo_chain(ticker: str, spot: float, hoy: date, dias: int = DIAS_MAX) -> pd.DataFrame:
    """Cadena sintética coherente (Black-Scholes con sonrisa de volatilidad) para el modo demo."""
    rng = np.random.default_rng(sum(map(ord, ticker)))
    paso = 0.5 if spot < 60 else 1 if spot < 150 else 2.5 if spot < 400 else 5
    ks = np.arange(math.floor(spot * (1 - RANGO_STRIKE) / paso) * paso, spot * (1 + RANGO_STRIKE) + paso, paso)
    base_iv = 0.22 + (sum(map(ord, ticker)) % 20) / 100
    filas = []
    muro_c = ks[np.argmin(abs(ks - spot * 1.04))]
    muro_p = ks[np.argmin(abs(ks - spot * 0.96))]
    exps = _fridays(hoy, dias)
    # vencimientos diarios de la primera semana (0–3 días) como en los ETF y acciones con 0DTE
    exps = sorted(set(exps) | {date.fromordinal(hoy.toordinal() + k) for k in (1, 2, 3)
                               if date.fromordinal(hoy.toordinal() + k).weekday() < 5})
    for ex in exps:
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
def chain(ticker: str, spot: float, dias: int = DIAS_MAX) -> tuple[pd.DataFrame, dict]:
    """Cadena filtrada (≤ 45 días, ±15 % del spot) con griegas, IV, volumen e interés abierto.
    Devuelve (df, info) con info = {fuente, feed, oi_disponible, timestamp_utc}."""
    from zoneinfo import ZoneInfo
    hoy = datetime.now(ZoneInfo("America/New_York")).date()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    kmin, kmax = spot * (1 - RANGO_STRIKE), spot * (1 + RANGO_STRIKE)
    if _demo():
        df = _demo_chain(ticker, spot, hoy, dias)
        info = {"fuente": "demo (sintética)", "feed": "demo", "oi_disponible": True, "timestamp_utc": ts}
    else:
        from . import alpaca
        if not alpaca.available():
            raise RuntimeError("Faltan las claves de Alpaca (ALPACA_API_KEY / ALPACA_SECRET_KEY).")
        lte = date.fromordinal(hoy.toordinal() + dias)
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


def candidatos(df: pd.DataFrame, spot: float, sesgo: str, n: int = 4, walls: dict | None = None,
               gex: pd.Series | None = None) -> list[dict]:
    """Contratos líquidos para el sesgo: delta 0.30–0.60, 14–45 días (o el mayor disponible), spread ≤ 15 %,
    ordenados por valor esperado (ver `evaluar`) o, sin muros, por cercanía a delta 0.45 y liquidez."""
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
    if walls is not None:
        d["ve"] = [(evaluar(r, spot, df, walls, gex) or {}).get("ve", -1e9) for _, r in d.iterrows()]
        d = d.sort_values("ve", ascending=False).head(n)
    else:
        d = d.sort_values("score", ascending=False).head(n)
    return [{"target_expiration_tab": etiqueta_venc(r["exp"]), "exp": r["exp"].isoformat(), "dte": int(r["dte"]),
             "option_type": tp.upper(), "strike": float(r["strike"]), "bid": float(r["bid"]), "ask": float(r["ask"]),
             "delta": round(float(r["delta"]), 3), "iv": round(float(r["iv"]) * 100, 1) if pd.notna(r["iv"]) else None,
             "open_interest": None if pd.isna(r["oi"]) else int(r["oi"]), "volume": int(r["volume"]),
             "spread_pct": round(float(r["spread"]) * 100, 1),
             **({"valor_esperado_pct": round(float(r["ve"]), 1)} if "ve" in d else {})} for _, r in d.iterrows()]


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


# ------------------------------------------------------------------ simulador de decisión
def _p_toque(s, t_price, iv, dias):
    """Probabilidad aproximada de que el precio toque `t_price` en `dias` (principio de reflexión, sin deriva)."""
    if dias <= 0 or iv <= 0 or s <= 0:
        return 0.0
    z = abs(math.log(t_price / s)) / (iv * math.sqrt(dias / 365))
    return float(min(1.0, 2 * (1 - _ncdf(z))))


def objetivo(spot, tipo: str, em: float | None, walls: dict) -> float:
    """Precio objetivo del escenario: el primer muro a favor que esté al menos a medio movimiento esperado
    (un muro pegado al precio no es un objetivo útil), acotado por el movimiento esperado del vencimiento."""
    em = em or spot * 0.03
    if tipo == "CALL":
        ws = sorted(w["strike"] for w in walls.get("call_walls", []) if w["strike"] >= spot + 0.5 * em)
        return min(ws[0], spot + em) if ws else spot + em
    ws = sorted((w["strike"] for w in walls.get("put_walls", []) if w["strike"] <= spot - 0.5 * em), reverse=True)
    return max(ws[0], spot - em) if ws else spot - em


def evaluar(r: pd.Series, spot: float, df: pd.DataFrame, walls: dict, gex: pd.Series | None = None) -> dict | None:
    """Métricas de rentabilidad y riesgo de un contrato.
    Horizonte h = min(DTE/2, 10) días. Objetivo T = muro a favor acotado por el movimiento esperado del vencimiento.
    ROI_T = valor BS en T tras h días / prima − 1 · ROI_0 = valor si el precio no se mueve (coste de theta).
    VE (valor esperado) = P(toca T) · ROI_T + (1 − P) · ROI_0 − spread/2."""
    call = r["type"] == "call"
    tipo = "CALL" if call else "PUT"
    prima = r["mid"]
    iv = r["iv"]
    if not (pd.notna(prima) and prima > 0 and pd.notna(iv) and iv > 0):
        return None
    dte = max(int(r["dte"]), 1)
    h = max(1.0, min(dte / 2, 10))
    resto = max(dte - h, 0.25) / 365
    em = expected_move(df[df["exp"] == r["exp"]], spot)
    t_px = objetivo(spot, tipo, em, walls)
    v_t = bs_price(t_px, r["strike"], resto, iv, call)
    v_0 = bs_price(spot, r["strike"], resto, iv, call)
    roi_t, roi_0 = v_t / prima - 1, v_0 / prima - 1
    p = _p_toque(spot, t_px, iv, h)
    spread = (r["ask"] - r["bid"]) / prima if pd.notna(r["bid"]) and pd.notna(r["ask"]) and r["bid"] > 0 else 0.25
    ve = p * roi_t + (1 - p) * roi_0 - spread / 2
    be = r["strike"] + prima if call else r["strike"] - prima
    tt = dte / 365
    d2 = (math.log(spot / be) + (TASA - iv * iv / 2) * tt) / (iv * math.sqrt(tt)) if be > 0 else 0
    pop = _ncdf(d2) if call else _ncdf(-d2)  # probabilidad de terminar con ganancia al vencimiento
    cw = sorted(w["strike"] for w in walls.get("call_walls", []))
    pw = sorted(w["strike"] for w in walls.get("put_walls", []))
    return {"contrato": f"{tipo} {r['strike']:g}", "tipo": tipo, "strike": float(r["strike"]), "exp": r["exp"],
            "vencimiento": etiqueta_venc(r["exp"]), "dte": dte, "prima": float(prima),
            "bid": None if pd.isna(r["bid"]) else float(r["bid"]), "ask": None if pd.isna(r["ask"]) else float(r["ask"]),
            "breakeven": float(be), "dist_breakeven_pct": float((be / spot - 1) * 100),
            "mov_esperado": em, "dentro_mov_esperado": None if not em else abs(be - spot) <= em,
            "delta": None if pd.isna(r["delta"]) else float(r["delta"]), "iv": float(iv) * 100,
            "theta_dia_pct": None if pd.isna(r["theta"]) else float(abs(r["theta"]) / prima * 100),
            "objetivo": float(t_px), "horizonte_dias": h, "roi_objetivo": float(roi_t * 100),
            "roi_sin_movimiento": float(roi_0 * 100), "p_toque": float(p * 100), "ve": float(ve * 100),
            "pop": float(pop * 100), "rr": float(max(roi_t, 0)), "gamma": None if pd.isna(r["gamma"]) else float(r["gamma"]),
            "theta": None if pd.isna(r["theta"]) else float(r["theta"]),
            "vega": None if pd.isna(r.get("vega", np.nan)) else float(r["vega"]),
            "costo": float((r["ask"] if pd.notna(r["ask"]) and r["ask"] > 0 else prima) * MULT),
            "spread_pct": float(spread * 100), "oi": None if pd.isna(r["oi"]) else int(r["oi"]),
            "volumen": int(r["volume"] or 0),
            "gex_strike": None if gex is None or r["strike"] not in gex.index else float(gex.loc[r["strike"]]),
            "sobre_muro_calls": bool(call and cw and r["strike"] > max(cw)),
            "bajo_muro_puts": bool((not call) and pw and r["strike"] < min(pw))}


def _liquido(d: pd.DataFrame) -> pd.DataFrame:
    return d[(d["bid"] > 0) & (d["ask"] > 0) & ((d["oi"].fillna(0) > 0) | (d["volume"] > 0))]


def mejor_strike(df, spot, exp, tipo: str, walls, gex=None) -> dict | None:
    """Escenario A (fecha manual, strike auto): el strike de mayor valor esperado en ese vencimiento."""
    d = _liquido(df[(df["exp"] == exp) & (df["type"] == tipo.lower())])
    evs = [e for _, r in d.iterrows() if (e := evaluar(r, spot, df, walls, gex)) and e["delta"] is not None
           and 0.15 <= abs(e["delta"]) <= 0.75]
    return max(evs, key=lambda e: e["ve"]) if evs else None


def mejor_vencimiento(df, spot, strike, tipo: str, walls, gex=None) -> dict | None:
    """Escenario B (strike manual, fecha auto): el vencimiento de mayor valor esperado para ese strike
    (equilibrio entre el desgaste por theta, la IV y el movimiento esperado de cada fecha)."""
    d = _liquido(df[(df["strike"] == strike) & (df["type"] == tipo.lower()) & (df["dte"] >= 2)])
    evs = [e for _, r in d.iterrows() if (e := evaluar(r, spot, df, walls, gex))]
    return max(evs, key=lambda e: e["ve"]) if evs else None


def contrato(df, exp, strike, tipo: str) -> pd.Series | None:
    d = df[(df["exp"] == exp) & (df["strike"] == strike) & (df["type"] == tipo.lower())]
    return None if d.empty else d.iloc[0]


def riesgos(e: dict, sesgo: str, adx: dict, gex_total: float, flip: float | None, spot: float) -> list[str]:
    """Cuidados a tener en cuenta para un contrato evaluado."""
    out = []
    if (e["tipo"] == "CALL" and sesgo == "Bajista") or (e["tipo"] == "PUT" and sesgo == "Alcista"):
        out.append(f"Va en contra del escenario cuantitativo ({sesgo.lower()}): el motor principal (70 %) no lo respalda.")
    if sesgo == "Neutral":
        out.append("Escenario cuantitativo neutral: una opción direccional depende de una ruptura aún no confirmada.")
    if e["dentro_mov_esperado"] is False:
        out.append(f"El breakeven ({e['breakeven']:,.2f}) está fuera del movimiento esperado del vencimiento: "
                   "el mercado no descuenta un recorrido suficiente.")
    if e["theta_dia_pct"] and e["theta_dia_pct"] >= 3:
        out.append(f"Desgaste temporal alto: la prima pierde ≈ {e['theta_dia_pct']:.1f} % por día (theta).")
    if e["spread_pct"] >= 10:
        out.append(f"Spread amplio ({e['spread_pct']:.0f} % de la prima): usa órdenes límite; entrar y salir cuesta caro.")
    if (e["oi"] or 0) < 100:
        out.append("Interés abierto bajo: poca liquidez para cerrar la posición.")
    if e["sobre_muro_calls"]:
        out.append("El strike está por encima del muro de calls: el precio debe romper una resistencia institucional.")
    if e["bajo_muro_puts"]:
        out.append("El strike está por debajo del muro de puts: el precio debe romper un soporte institucional.")
    if gex_total < 0:
        out.append("GEX negativo: movimientos amplificados en ambos sentidos; el riesgo de la prima es mayor.")
    elif flip and ((e["tipo"] == "CALL" and spot < flip) or (e["tipo"] == "PUT" and spot > flip)):
        out.append(f"El precio está del lado opuesto del gamma flip ({flip:,.2f}) para esta dirección.")
    if adx.get("regimen") == "rango":
        out.append("ADX bajo 23 (rango): sin tendencia, el tiempo juega en contra del comprador de opciones.")
    if e["iv"] >= 60:
        out.append(f"IV elevada ({e['iv']:.0f} %): primas caras; una caída de volatilidad resta valor aunque acierte la dirección.")
    if e["roi_sin_movimiento"] < -15:
        out.append(f"Si el precio no se mueve en {e['horizonte_dias']:.0f} días, la prima perdería "
                   f"≈ {abs(e['roi_sin_movimiento']):.0f} %.")
    return out


# ------------------------------------------------------------------ P&L por trayectoria (time-to-target)
def pnl_trayectoria(strike: float, tipo: str, iv: float, prima: float, dte: int, spot: float, t_px: float,
                    dias: float) -> dict:
    """P&L de 1 contrato si el subyacente llega a `t_px` en `dias` (revaluación Black-Scholes con la IV actual).
    Descompone el resultado en efecto precio (≈ Δ × ΔS) y quema de theta (≈ Θ × días)."""
    call = tipo.upper() == "CALL"
    dias = max(0.0, min(float(dias), float(dte)))
    resto = max(dte - dias, 0.0) / 365
    v_obj = bs_price(t_px, strike, resto, iv, call)
    v_spot_hoy = bs_price(spot, strike, dte / 365, iv, call)
    v_spot_t = bs_price(spot, strike, resto, iv, call)
    g = bs_greeks(spot, strike, dte / 365, iv, call)
    return {"valor_objetivo": v_obj, "utilidad_usd": (v_obj - prima) * MULT,
            "retorno_pct": (v_obj / prima - 1) * 100 if prima > 0 else None,
            "quema_theta_usd": (v_spot_hoy - v_spot_t) * MULT,
            "aprox_delta_usd": g["delta"] * (t_px - spot) * MULT,
            "aprox_theta_usd": g["theta"] * dias * MULT}



# ------------------------------------------------------------------ terminal de opciones: OPT1 / OPT2 / OPT3
RANGOS = {"2S": 14, "1M": 31, "3M": 92, "6M": 183}
MONEY = {"ITM": (0.55, 0.85), "ATM": (0.40, 0.60), "OTM": (0.15, 0.45)}
TIERS = {1: ("Óptimo", "equilibrio entre strike y vencimiento", None),
         2: ("Agresivo", "vencimiento de 4 a 10 días", (4, 10)),
         3: ("Ultra riesgo", "vencimiento de 0 a 3 días", (0, 3))}


def _money_ok(e: dict, money: str, spot: float) -> bool:
    lo, hi = MONEY.get(money, (0.15, 0.85))
    if e["delta"] is None or not (lo <= abs(e["delta"]) <= hi):
        return False
    k, call = e["strike"], e["tipo"] == "CALL"
    if money == "OTM":
        return k > spot if call else k < spot
    if money == "ITM":
        return k < spot if call else k > spot
    return abs(k / spot - 1) <= 0.025


def evaluar_todos(df, spot, tipo: str, walls, gex=None) -> list[dict]:
    d = _liquido(df[df["type"] == tipo.lower()])
    return [e for _, r in d.iterrows() if (e := evaluar(r, spot, df, walls, gex))]


def opciones_tier(evs: list[dict], spot, money: str, ventana: int, tier: int) -> list[dict]:
    """Contratos elegibles de un nivel de riesgo, ordenados por valor esperado."""
    rng = TIERS[tier][2]
    if rng is None:  # OPT1: más de 10 días dentro de la ventana visible (o toda la ventana si es corta)
        lo = 11 if ventana > 14 else 4
        rng = (lo, ventana)
    out = [e for e in evs if rng[0] <= e["dte"] <= rng[1] and _money_ok(e, money, spot) and e["spread_pct"] <= 25]
    return sorted(out, key=lambda e: e["ve"], reverse=True)


def niveles(evs, spot, money: str, ventana: int, presupuesto: float | None = None) -> dict:
    """{1: OPT1, 2: OPT2, 3: OPT3}. Cada uno: el mejor por valor esperado, número de contratos que permite el
    presupuesto y, si no alcanza, la alternativa más cercana dentro del presupuesto y el capital sugerido."""
    out = {}
    for t in (1, 2, 3):
        lst = opciones_tier(evs, spot, money, ventana, t)
        if not lst:
            out[t] = None
            continue
        best = dict(lst[0])
        best["tier"] = t
        best["contratos"] = int(presupuesto // best["costo"]) if presupuesto else None
        if presupuesto is not None and best["contratos"] == 0:
            asequibles = [e for e in lst if e["costo"] <= presupuesto]
            alt = asequibles[0] if asequibles else None
            cerca = next((e for e in sorted(lst, key=lambda e: e["costo"])
                          if e["ve"] >= best["ve"] - abs(best["ve"]) * 0.15), best)
            best["ajuste"] = {
                "alcanzable": alt,
                "impacto_ve": None if not alt else alt["ve"] - best["ve"],
                "impacto_pop": None if not alt else alt["pop"] - best["pop"],
                "capital_optimo": math.ceil(best["costo"] / 5) * 5,
                "capital_cercano": math.ceil(cerca["costo"] / 5) * 5,
                "contrato_cercano": cerca["contrato"] + " · " + cerca["vencimiento"],
            }
        out[t] = best
    return out


def flujo_neto(df: pd.DataFrame) -> float:
    """Prima neta negociada hoy: Σ volumen × precio medio × 100 (calls − puts)."""
    v = df["volume"].fillna(0) * df["mid"].fillna(0) * MULT
    return float(v[df["type"] == "call"].sum() - v[df["type"] == "put"].sum())


def porcentaje_calls(df: pd.DataFrame) -> float | None:
    c, p = df[df["type"] == "call"]["volume"].sum(), df[df["type"] == "put"]["volume"].sum()
    return None if (c + p) == 0 else float(c / (c + p) * 100)


def contraria(evs_op, spot, money, ventana, disparo: float, tipo_op: str) -> dict | None:
    """Mejor opción del lado contrario y su precio límite estimado si el subyacente llega al nivel de disparo."""
    lst = opciones_tier(evs_op, spot, money, ventana, 1) or opciones_tier(evs_op, spot, "OTM", ventana, 1)
    if not lst:
        return None
    e = dict(lst[0])
    resto = max(e["dte"] - 2, 0.25) / 365  # llegada al disparo en ~2 sesiones
    e["disparo"] = float(disparo)
    e["limite"] = float(bs_price(disparo, e["strike"], resto, e["iv"] / 100, tipo_op == "CALL"))
    return e
