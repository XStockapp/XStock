"""
Análisis fundamental: valoración, rentabilidad, crecimiento, salud financiera,
consenso de analistas y Piotroski F-Score.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _f(x):
    try:
        x = float(x)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def extract_metrics(info: dict) -> dict:
    """Normaliza el diccionario de yfinance (o Alpha Vantage ya mapeado)."""
    g = lambda k: _f(info.get(k))
    fcf, mcap = g("freeCashflow"), g("marketCap")
    de = g("debtToEquity")
    if de is not None and de > 10:  # yfinance lo entrega en %
        de = de / 100
    return {
        "Nombre": info.get("longName") or info.get("shortName") or "",
        "Sector": info.get("sector") or "",
        "Industria": info.get("industry") or "",
        "Market cap": mcap,
        "P/E (TTM)": g("trailingPE"),
        "P/E forward": g("forwardPE"),
        "PEG": g("pegRatio") or g("trailingPegRatio"),
        "P/B": g("priceToBook"),
        "P/S": g("priceToSalesTrailing12Months"),
        "EV/EBITDA": g("enterpriseToEbitda"),
        "FCF yield": (fcf / mcap) if fcf and mcap else None,
        "ROE": g("returnOnEquity"),
        "ROA": g("returnOnAssets"),
        "Margen bruto": g("grossMargins"),
        "Margen operativo": g("operatingMargins"),
        "Margen neto": g("profitMargins"),
        "Crec. ingresos (YoY)": g("revenueGrowth"),
        "Crec. utilidades (YoY)": g("earningsGrowth"),
        "Deuda/Patrimonio": de,
        "Ratio corriente": g("currentRatio"),
        "Beta": g("beta"),
        "Dividend yield": g("dividendYield") / 100 if g("dividendYield") and g("dividendYield") > 1 else g("dividendYield"),
        "Precio objetivo analistas": g("targetMeanPrice"),
        "Recomendación (1=Compra fuerte, 5=Venta)": g("recommendationMean"),
        "N° analistas": g("numberOfAnalystOpinions"),
        "Precio actual": g("currentPrice") or g("regularMarketPrice"),
    }


def _band(v, good, bad, reverse=False):
    """Mapea v a [-1,1]: good→+1, bad→-1, interpolación lineal."""
    if v is None:
        return None
    if reverse:
        v, good, bad = -v, -good, -bad
    if good == bad:
        return 0.0
    x = (v - bad) / (good - bad) * 2 - 1
    return float(max(-1, min(1, x)))


def _fmt(v, kind):
    if v is None:
        return "—"
    if kind == "pct":
        return f"{v * 100:.1f}%"
    if kind == "x":
        return f"{v:.2f}x"
    return f"{v:,.2f}"


# (bloque, métrica, clave, formato, bueno, malo, invertido, por qué es atractivo, por qué es riesgo)
RULES = [
    ("Valoración", "P/E", "_pe", "num", 12, 40, True,
     "Valoración barata frente al mercado (P/E bajo)", "Valoración exigente: el precio descuenta mucho crecimiento"),
    ("Valoración", "PEG", "PEG", "num", 1.0, 3.0, True,
     "Crecimiento a precio razonable (PEG ≤ 1)", "Paga caro el crecimiento esperado (PEG alto)"),
    ("Valoración", "EV/EBITDA", "EV/EBITDA", "num", 8, 30, True,
     "Múltiplo operativo atractivo", "Múltiplo operativo elevado"),
    ("Valoración", "FCF yield", "FCF yield", "pct", 0.06, -0.01, False,
     "Genera mucha caja libre respecto a su valor", "Flujo de caja libre débil o negativo"),
    ("Rentabilidad", "ROE", "ROE", "pct", 0.20, 0.0, False,
     "Alta rentabilidad sobre el patrimonio", "Rentabilidad sobre patrimonio baja o negativa"),
    ("Rentabilidad", "ROA", "ROA", "pct", 0.10, 0.0, False,
     "Usa sus activos con eficiencia", "Baja eficiencia de los activos"),
    ("Rentabilidad", "Margen operativo", "Margen operativo", "pct", 0.25, 0.0, False,
     "Márgenes operativos de calidad (poder de precio)", "Márgenes operativos estrechos o negativos"),
    ("Rentabilidad", "Margen neto", "Margen neto", "pct", 0.20, -0.05, False,
     "Convierte bien las ventas en utilidad", "Margen neto débil"),
    ("Crecimiento", "Crec. ingresos", "Crec. ingresos (YoY)", "pct", 0.20, -0.05, False,
     "Ventas creciendo con fuerza", "Ventas estancadas o cayendo"),
    ("Crecimiento", "Crec. utilidades", "Crec. utilidades (YoY)", "pct", 0.25, -0.10, False,
     "Utilidades creciendo con fuerza", "Utilidades cayendo"),
    ("Salud financiera", "Deuda/Patrimonio", "Deuda/Patrimonio", "num", 0.3, 2.0, True,
     "Balance poco endeudado", "Apalancamiento alto: sensible a tasas y a una recesión"),
    ("Salud financiera", "Ratio corriente", "Ratio corriente", "num", 2.0, 0.8, False,
     "Liquidez holgada para el corto plazo", "Liquidez ajustada (ratio corriente < 1)"),
    ("Consenso", "Recomendación analistas", "Recomendación (1=Compra fuerte, 5=Venta)", "num", 1.5, 3.5, True,
     "Consenso de analistas en compra", "Consenso de analistas débil"),
    ("Consenso", "Upside a precio objetivo", "_upside", "pct", 0.25, -0.10, False,
     "Los analistas ven bastante recorrido al alza", "El precio ya supera el objetivo de los analistas"),
]
BLOCK_W = {"Valoración": 1.2, "Rentabilidad": 1.2, "Crecimiento": 1.0, "Salud financiera": 0.8, "Consenso": 0.6,
           "Posicionamiento (Finviz)": 0.8}


def score_fundamentals(m: dict, finviz_items: list | None = None) -> dict:
    """
    Puntaje fundamental -100..+100 por bloques y detalle por métrica con su lectura
    (atractivo / neutral / riesgo). Umbrales generales de mercado (no por sector).
    `finviz_items`: salida de finviz.score_items() → bloque de posicionamiento.
    """
    pe = m.get("P/E forward") or m.get("P/E (TTM)")
    tgt, px = m.get("Precio objetivo analistas"), m.get("Precio actual")
    vals = {**m, "_pe": pe, "_upside": (tgt / px - 1) if tgt and px else None}
    items = []
    for blk, name, key, kind, good, bad, rev, why_good, why_bad in RULES:
        v = vals.get(key)
        if key in ("_pe", "PEG", "EV/EBITDA") and v is not None and v <= 0:
            sc = -1.0  # utilidades o EBITDA negativos
            why_bad_ = "Utilidades/EBITDA negativos: no se puede valorar por múltiplos"
        else:
            sc = _band(v, good, bad, reverse=rev)
            why_bad_ = why_bad
        if sc is None:
            continue
        items.append({"bloque": blk, "metrica": name, "valor": _fmt(v, kind), "score": round(100 * sc),
                      "peso": BLOCK_W[blk],
                      "lectura": why_good if sc >= 0.35 else (why_bad_ if sc <= -0.35 else "Nivel neutral")})
    for it in finviz_items or []:
        items.append({"bloque": "Posicionamiento (Finviz)", "metrica": it["metrica"], "valor": it["valor"],
                      "score": round(100 * it["impacto"]), "peso": BLOCK_W["Posicionamiento (Finviz)"],
                      "lectura": it["lectura"]})
    detail, tot, wsum = {}, 0.0, 0.0
    for blk in BLOCK_W:
        bl = [i["score"] / 100 for i in items if i["bloque"] == blk]
        bs = float(np.mean(bl)) if bl else None
        detail[blk] = {"score": None if bs is None else round(100 * bs, 1),
                       "items": {i["metrica"]: i["score"] for i in items if i["bloque"] == blk}}
        if bs is not None:
            tot += bs * BLOCK_W[blk]
            wsum += BLOCK_W[blk]
    return {"score": round(100 * tot / wsum, 1) if wsum else None, "bloques": detail, "items": items}


def piotroski(fin: pd.DataFrame | None, bs: pd.DataFrame | None, cf: pd.DataFrame | None) -> dict | None:
    """Piotroski F-Score (0-9) con estados anuales de yfinance (columnas = años)."""
    try:
        if fin is None or bs is None or cf is None or fin.shape[1] < 2 or bs.shape[1] < 2:
            return None

        def row(df, *names):
            for n in names:
                if n in df.index:
                    return df.loc[n]
            return None

        ni = row(fin, "Net Income", "Net Income Common Stockholders")
        rev = row(fin, "Total Revenue")
        gp = row(fin, "Gross Profit")
        ta = row(bs, "Total Assets")
        ca = row(bs, "Current Assets")
        cl = row(bs, "Current Liabilities")
        ltd = row(bs, "Long Term Debt", "Long Term Debt And Capital Lease Obligation")
        sh = row(bs, "Ordinary Shares Number", "Share Issued")
        cfo = row(cf, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
        if any(x is None for x in (ni, ta, cfo)):
            return None
        y0, y1 = fin.columns[0], fin.columns[1]
        b0, b1 = bs.columns[0], bs.columns[1]
        roa0, roa1 = ni[y0] / ta[b0], ni[y1] / ta[b1]
        tests = {
            "Utilidad neta positiva": ni[y0] > 0,
            "Flujo operativo positivo": cfo[cf.columns[0]] > 0,
            "ROA creciente": roa0 > roa1,
            "Flujo operativo > utilidad (calidad)": cfo[cf.columns[0]] > ni[y0],
        }
        if ltd is not None:
            tests["Menor apalancamiento"] = (ltd[b0] / ta[b0]) <= (ltd[b1] / ta[b1])
        if ca is not None and cl is not None:
            tests["Mejor liquidez corriente"] = (ca[b0] / cl[b0]) > (ca[b1] / cl[b1])
        if sh is not None:
            tests["Sin dilución de acciones"] = sh[b0] <= sh[b1] * 1.01
        if gp is not None and rev is not None:
            tests["Margen bruto creciente"] = gp[y0] / rev[y0] > gp[y1] / rev[y1]
        if rev is not None:
            tests["Rotación de activos creciente"] = rev[y0] / ta[b0] > rev[y1] / ta[b1]
        tests = {k: bool(v) for k, v in tests.items() if pd.notna(v)}
        return {"score": sum(tests.values()), "max": len(tests), "tests": tests}
    except Exception:
        return None


def alpha_vantage_overview_to_info(ov: dict) -> dict:
    """Mapea OVERVIEW de Alpha Vantage al formato de yfinance."""
    f = lambda k: _f(ov.get(k))
    return {
        "longName": ov.get("Name"), "sector": ov.get("Sector"), "industry": ov.get("Industry"),
        "marketCap": f("MarketCapitalization"), "trailingPE": f("TrailingPE"), "forwardPE": f("ForwardPE"),
        "pegRatio": f("PEGRatio"), "priceToBook": f("PriceToBookRatio"),
        "priceToSalesTrailing12Months": f("PriceToSalesRatioTTM"), "enterpriseToEbitda": f("EVToEBITDA"),
        "returnOnEquity": f("ReturnOnEquityTTM"), "returnOnAssets": f("ReturnOnAssetsTTM"),
        "operatingMargins": f("OperatingMarginTTM"), "profitMargins": f("ProfitMargin"),
        "revenueGrowth": f("QuarterlyRevenueGrowthYOY"), "earningsGrowth": f("QuarterlyEarningsGrowthYOY"),
        "beta": f("Beta"), "dividendYield": f("DividendYield"), "targetMeanPrice": f("AnalystTargetPrice"),
    }
