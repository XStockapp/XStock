"""Datos fundamentales y corporativos con fecha de publicación (point-in-time) desde SEC EDGAR.

Regla de oro: cada dato entra al modelo a partir del día hábil SIGUIENTE a su presentación en la SEC (filed), y se
usa la PRIMERA cifra publicada (no las corregidas después). Así el backtest no «ve el futuro».

Fuentes (gratuitas, sin clave; la SEC exige identificarse con un User-Agent con contacto → secret SEC_USER_AGENT):
  · https://www.sec.gov/files/company_tickers.json          ticker → CIK
  · https://data.sec.gov/submissions/CIK##########.json     historial de presentaciones (formularios, ítems 8-K)
  · https://data.sec.gov/api/xbrl/companyfacts/CIK##.json   cifras XBRL con su fecha de presentación
Ítems 8-K usados: 2.02 resultados · 2.01 adquisición/venta completada · 1.01 acuerdo material.
"""
from __future__ import annotations

import gzip
import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .dataset import CACHE_DIR

UA_ENV = "SEC_USER_AGENT"
_ULTIMA = [0.0]
INGRESOS = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
            "RevenueFromContractWithCustomerIncludingAssessedTax"]


# ------------------------------------------------------------------ descarga (con caché en disco)
def _ua() -> str:
    ua = os.environ.get(UA_ENV, "").strip()
    if not ua:
        raise RuntimeError("Falta SEC_USER_AGENT (nombre y correo de contacto que exige la SEC).")
    return ua


def _get_json(url: str, cache: Path | None):
    if cache and cache.exists() and time.time() - cache.stat().st_mtime < 6 * 86400:
        return json.loads(gzip.decompress(cache.read_bytes()))
    import requests
    espera = 0.12 - (time.time() - _ULTIMA[0])  # ≤ 10 consultas por segundo (política de la SEC)
    if espera > 0:
        time.sleep(espera)
    r = requests.get(url, headers={"User-Agent": _ua(), "Accept-Encoding": "gzip, deflate"}, timeout=60)
    _ULTIMA[0] = time.time()
    if r.status_code == 404:
        return None
    r.raise_for_status()
    js = r.json()
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(gzip.compress(json.dumps(js).encode()))
    return js


def mapa_cik() -> dict[str, int]:
    js = _get_json("https://www.sec.gov/files/company_tickers.json", CACHE_DIR / "sec" / "tickers.json.gz") or {}
    return {v["ticker"].upper().replace(".", "-"): int(v["cik_str"]) for v in js.values()}


def presentaciones(cik: int) -> pd.DataFrame:
    base = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
    js = _get_json(base, CACHE_DIR / "sec" / f"sub_{cik}.json.gz")
    if not js:
        return pd.DataFrame(columns=["form", "fecha", "items"])
    bloques = [js.get("filings", {}).get("recent", {})]
    for f in js.get("filings", {}).get("files", []):
        extra = _get_json("https://data.sec.gov/submissions/" + f["name"], CACHE_DIR / "sec" / f"{f['name']}.gz")
        if extra:
            bloques.append(extra)
    return tabla_presentaciones(bloques)


def tabla_presentaciones(bloques: list[dict]) -> pd.DataFrame:
    filas = []
    for b in bloques:
        for form, fd, it in zip(b.get("form", []), b.get("filingDate", []), b.get("items", [""] * len(b.get("form", [])))):
            filas.append({"form": form, "fecha": pd.Timestamp(fd), "items": it or ""})
    return pd.DataFrame(filas, columns=["form", "fecha", "items"]).sort_values("fecha").reset_index(drop=True)


def hechos(cik: int) -> dict:
    return _get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
                     CACHE_DIR / "sec" / f"facts_{cik}.json.gz") or {}


# ------------------------------------------------------------------ series point-in-time
def _efectivo(filed: pd.Series) -> pd.Series:
    """Día desde el que el dato es utilizable: el hábil siguiente a la presentación."""
    return pd.to_datetime(filed) + pd.offsets.BDay(1)


def _serie(facts: dict, ns: str, concepto: str, unidad: str) -> pd.DataFrame:
    try:
        rows = facts["facts"][ns][concepto]["units"][unidad]
    except (KeyError, TypeError):
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if df.empty or "filed" not in df:
        return pd.DataFrame()
    df = df[df.get("form", pd.Series("", index=df.index)).astype(str).str.match(r"^(10-Q|10-K)")]
    df["end"] = pd.to_datetime(df["end"])
    df["filed"] = pd.to_datetime(df["filed"])
    if "start" in df:
        df["start"] = pd.to_datetime(df["start"])
        df["dur"] = (df["end"] - df["start"]).dt.days
    return df.sort_values("filed")


def _trimestral(facts: dict, conceptos: list[str], unidad: str = "USD", ns: str = "us-gaap") -> pd.DataFrame:
    """Valores trimestrales (duración 80-100 días), primera publicación de cada periodo."""
    for c in conceptos:
        df = _serie(facts, ns, c, unidad)
        if df.empty or "dur" not in df:
            continue
        q = df[(df["dur"] >= 80) & (df["dur"] <= 100)].drop_duplicates("end", keep="first")
        if len(q) >= 4:
            return q[["end", "filed", "val"]].sort_values("end").reset_index(drop=True)
    return pd.DataFrame(columns=["end", "filed", "val"])


def _instantaneo(facts: dict, ns: str, concepto: str, unidad: str) -> pd.DataFrame:
    df = _serie(facts, ns, concepto, unidad)
    if df.empty:
        return df
    return df.drop_duplicates("end", keep="first")[["end", "filed", "val"]].sort_values("filed")


def _anual_yoy(q: pd.DataFrame) -> pd.DataFrame:
    """Para cada trimestre, el mismo trimestre del año anterior (fin a 365 ± 20 días)."""
    out = []
    for _, r in q.iterrows():
        prev = q[(q["end"] - (r["end"] - pd.Timedelta(days=365))).abs() <= pd.Timedelta(days=20)]
        out.append(prev["val"].iloc[0] if len(prev) else np.nan)
    q = q.copy()
    q["prev"] = out
    return q


def _a_diario(idx: pd.DatetimeIndex, fechas: pd.Series, valores) -> pd.Series:
    s = pd.Series(np.asarray(valores, float), index=_efectivo(fechas)).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s.reindex(idx.union(s.index)).ffill().reindex(idx)


def variables(df: pd.DataFrame, sigma_d: pd.Series, pres: pd.DataFrame | None, facts: dict | None) -> pd.DataFrame:
    """Variables diarias de UNA acción (índice = fechas de sus barras)."""
    idx = df.index
    c = df["Close"].astype(float)
    V = pd.DataFrame(index=idx)
    pos = pd.Series(np.arange(len(idx)), index=idx)
    # ---- eventos 8-K
    if pres is not None and len(pres):
        def _ultimos(item):
            f = pres[(pres["form"].str.startswith("8-K")) & (pres["items"].str.contains(item, regex=False))]["fecha"]
            return _efectivo(f).sort_values()
        res, adq, acu = _ultimos("2.02"), _ultimos("2.01"), _ultimos("1.01")

        def _dias_desde(ev, tope):
            s = pd.Series(np.nan, index=idx)
            ult = None
            evs = list(ev)
            j = 0
            for t in idx:
                while j < len(evs) and evs[j] <= t:
                    ult = evs[j]
                    j += 1
                s[t] = min(np.busday_count(ult.date(), t.date()), tope) if ult is not None else tope
            return s
        V["res_dias_desde"] = _dias_desde(res, 90)
        V["res_dias_hasta_est"] = (63 - V["res_dias_desde"]).clip(lower=0)  # ~ un trimestre de sesiones
        # reacción al último resultado: cierre del día previo → cierre del día siguiente a la presentación, en σ
        reac = pd.Series(np.nan, index=idx)
        for e in res:
            d0 = e - pd.offsets.BDay(1)  # día de la presentación
            if d0 not in pos.index:
                continue
            i = pos[d0]
            if i < 1 or i + 1 >= len(idx):
                continue
            sg = sigma_d.iloc[i - 1]
            if np.isfinite(sg) and sg > 0:
                reac.iloc[i + 1] = np.log(c.iloc[i + 1] / c.iloc[i - 1]) / (sg * np.sqrt(2))
        V["res_reaccion_sigma"] = reac.ffill()
        V["corp_dias_desde_adquisicion"] = _dias_desde(adq, 250)
        V["corp_dias_desde_acuerdo"] = _dias_desde(acu, 250)
    # ---- cifras XBRL
    if facts:
        sh = _instantaneo(facts, "dei", "EntityCommonStockSharesOutstanding", "shares")
        if len(sh):
            acc = _a_diario(idx, sh["filed"], sh["val"])
            V["tam_log_cap"] = np.log((acc * c).where(acc > 0))
            V["tam_cambio_acciones_1a"] = np.log(acc / acc.shift(252))  # recompras (−) o dilución (+)
        rev = _trimestral(facts, INGRESOS)
        if len(rev) >= 5:
            r2 = _anual_yoy(rev)
            V["fund_crec_ingresos"] = _a_diario(idx, r2["filed"], np.log(r2["val"] / r2["prev"]).clip(-2, 2))
            ni = _trimestral(facts, ["NetIncomeLoss"])
            if len(ni):
                m = rev.merge(ni, on="end", suffixes=("", "_ni"))
                m = m[m["val"] > 0]
                V["fund_margen_neto"] = _a_diario(idx, m[["filed", "filed_ni"]].max(axis=1),
                                                  (m["val_ni"] / m["val"]).clip(-2, 1))
        eps = _trimestral(facts, ["EarningsPerShareDiluted", "EarningsPerShareBasic"], "USD/shares")
        if len(eps) >= 8:
            e2 = _anual_yoy(eps)
            d = e2["val"] - e2["prev"]
            sd = d.rolling(8, min_periods=4).std().shift(1)  # dispersión de sorpresas PASADAS
            V["res_sorpresa_bpa"] = _a_diario(idx, e2["filed"], (d / sd.replace(0, np.nan)).clip(-5, 5))
        li, ac = _instantaneo(facts, "us-gaap", "Liabilities", "USD"), _instantaneo(facts, "us-gaap", "Assets", "USD")
        if len(li) and len(ac):
            m = li.merge(ac, on="end", suffixes=("_l", "_a"))
            m = m[m["val_a"] > 0]
            V["fund_pasivo_activo"] = _a_diario(idx, m[["filed_l", "filed_a"]].max(axis=1), m["val_l"] / m["val_a"])
    return V.replace([np.inf, -np.inf], np.nan)


def descargar(tickers: list[str], log=print) -> dict[str, tuple]:
    """{ticker: (presentaciones, hechos)}. Las acciones sin CIK (ADR de emisores extranjeros) quedan fuera."""
    cik = mapa_cik()
    out = {}
    for i, t in enumerate(tickers):
        k = cik.get(t.upper())
        if not k:
            continue
        try:
            out[t] = (presentaciones(k), hechos(k))
        except Exception as e:
            log(f"  SEC {t}: {str(e)[:60]}")
        if (i + 1) % 50 == 0:
            log(f"  SEC {i + 1}/{len(tickers)}")
    return out
