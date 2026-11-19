"""Descarga masiva (backfill) de cadenas históricas de opciones desde MarketData.app, con interés abierto.

Pensado para GitHub Actions (una ejecución diaria):
  · Respeta el saldo diario: se detiene limpiamente antes de agotar los créditos (--limite, por defecto 95 000).
  · Registro de progreso (checkpoint): qué fechas de cada acción ya están descargadas; la siguiente ejecución
    sigue donde quedó sin repetir consultas.
  · Un Parquet por acción: data/options_history/{SIMBOLO}_oi.parquet, con tipos ligeros (float32/int32/int8).
  · Prioridad: primero tus acciones (watchlists de la app), después las más líquidas; de la fecha más reciente
    hacia atrás, hasta --anios años.
  · Persistencia entre ejecuciones: el checkpoint y los Parquet se guardan en Supabase Storage
    (bucket «opciones», carpeta historico_oi/). Nada de esto se sube al repositorio.

Uso:
  python scripts/backfill_marketdata_oi.py --sonda AAPL          # prueba: 3 fechas, muestra créditos y filas
  python scripts/backfill_marketdata_oi.py --max 150 --anios 3   # ejecución normal
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.fuentes import marketdata as MD  # noqa: E402

DIR = Path("data/options_history")
BUCKET = "opciones"
PREFIJO = "historico_oi"
PROGRESO = "progreso.json"


# ------------------------------------------------------------------ almacenamiento (Supabase Storage)
def _sb():
    from core.motor_a import artefactos as AR
    return AR._sb()


def bajar(nombre: str) -> bytes | None:
    url, h = _sb()
    if not url:
        return None
    r = requests.get(f"{url}/storage/v1/object/{BUCKET}/{PREFIJO}/{nombre}", headers=h, timeout=120)
    return r.content if r.status_code == 200 else None


def subir(nombre: str, cuerpo: bytes) -> bool:
    url, h = _sb()
    if not url:
        return False
    requests.post(f"{url}/storage/v1/bucket", headers=h, json={"id": BUCKET, "name": BUCKET, "public": False},
                  timeout=30)
    r = requests.post(f"{url}/storage/v1/object/{BUCKET}/{PREFIJO}/{nombre}", data=cuerpo, timeout=300,
                      headers={**h, "Content-Type": "application/octet-stream", "x-upsert": "true"})
    return r.status_code < 300


# ------------------------------------------------------------------ progreso
def _a_dia(f: str) -> int:
    return (date.fromisoformat(f) - date(1970, 1, 1)).days


def _de_dia(n: int) -> str:
    return (date(1970, 1, 1) + timedelta(days=int(n))).isoformat()


class Progreso:
    """{simbolo: [días descargados (enteros desde 1970)]}. Guarda también los días sin datos (feriados) para no
    volver a pagarlos."""

    def __init__(self, datos: dict | None = None):
        self.hechos: dict[str, set[int]] = {k: set(v) for k, v in (datos or {}).get("hechos", {}).items()}

    @classmethod
    def cargar(cls) -> "Progreso":
        local = DIR / PROGRESO
        crudo = bajar(PROGRESO) or (local.read_bytes() if local.exists() else None)
        return cls(json.loads(crudo) if crudo else None)

    def a_json(self) -> bytes:
        return json.dumps({"actualizado": date.today().isoformat(),
                           "hechos": {k: sorted(v) for k, v in sorted(self.hechos.items())}}).encode()

    def guardar(self):
        DIR.mkdir(parents=True, exist_ok=True)
        cuerpo = self.a_json()
        (DIR / PROGRESO).write_bytes(cuerpo)
        subir(PROGRESO, cuerpo)

    def pendientes(self, simbolo: str, fechas: list[str]) -> list[str]:
        h = self.hechos.get(simbolo, set())
        return [f for f in fechas if _a_dia(f) not in h]

    def marcar(self, simbolo: str, fechas):
        self.hechos.setdefault(simbolo, set()).update(_a_dia(f) for f in fechas)


def fechas_objetivo(anios: float, hoy: date | None = None) -> list[str]:
    """Días hábiles desde ayer hacia atrás (los feriados devuelven vacío y quedan marcados como hechos)."""
    hoy = hoy or date.today()
    fin = pd.Timestamp(hoy) - pd.offsets.BDay(1)
    ini = pd.Timestamp(hoy) - pd.DateOffset(days=int(365.25 * anios))
    return [d.date().isoformat() for d in pd.bdate_range(ini, fin)][::-1]


def watchlist() -> list[str]:
    try:
        from core import db
        return sorted({str(r["ticker"]).upper() for r in db.backend().select("watchlist")
                       if r.get("ticker") and not str(r["ticker"]).upper().endswith(("-USD", "-USDT", "-EUR"))})
    except Exception:
        return []


def prioridad(maximo: int, log=print) -> list[str]:
    """Tus acciones primero; después las más líquidas, sin repetir."""
    from core.motor_a import dataset as DS
    try:
        uni = DS.universo(maximo, log=log)
    except Exception as e:  # sin Alpaca: solo watchlist
        log(f"Universo no disponible ({e}); solo watchlist.")
        uni = []
    mias = watchlist()
    log(f"Watchlist: {len(mias)} acciones · universo líquido: {len(uni)}")
    orden = list(dict.fromkeys([s.upper() for s in mias] + [s.upper() for s in uni]))
    # Clases de acciones: MarketData usa el punto (BRK.B), no el guion
    return [s.replace("-", ".") for s in orden][:max(maximo, len(mias))]


# ------------------------------------------------------------------ parquet por acción
def nombre_parquet(simbolo: str) -> str:
    return f"{simbolo.replace('.', '-')}_oi.parquet"


def cargar_existente(simbolo: str) -> pd.DataFrame:
    p = DIR / nombre_parquet(simbolo)
    crudo = bajar(nombre_parquet(simbolo)) or (p.read_bytes() if p.exists() else None)
    return pd.read_parquet(io.BytesIO(crudo)) if crudo else MD.vacia()


def unir(viejo: pd.DataFrame, nuevo: list[pd.DataFrame]) -> pd.DataFrame:
    partes = [d for d in [viejo, *nuevo] if len(d)]
    if not partes:
        return MD.vacia()
    df = pd.concat(partes, ignore_index=True)
    df = df.drop_duplicates(["fecha", "vencimiento", "tipo", "strike"], keep="last")
    df = df.astype(MD.ESQUEMA).sort_values(["fecha", "vencimiento", "tipo", "strike"]).reset_index(drop=True)
    return df


def guardar_parquet(simbolo: str, df: pd.DataFrame) -> int:
    DIR.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    df.to_parquet(buf, compression="zstd", index=False)
    cuerpo = buf.getvalue()
    (DIR / nombre_parquet(simbolo)).write_bytes(cuerpo)
    subir(nombre_parquet(simbolo), cuerpo)
    return len(cuerpo)


# ------------------------------------------------------------------ ejecución
def procesar(cli: MD.Cliente, prog: Progreso, simbolo: str, fechas: list[str], hilos: int, log=print) -> bool:
    """Descarga las fechas pendientes de una acción. Devuelve False si se agotó el saldo (hay que parar)."""
    pend = prog.pendientes(simbolo, fechas)
    if not pend:
        return True
    nuevos, hechas, sin_saldo = [], [], False

    def una(f):
        return f, cli.cadena(simbolo, f)

    # Por bloques, para guardar el progreso a menudo y parar a tiempo
    for i in range(0, len(pend), 60):
        bloque = pend[i:i + 60]
        try:
            with ThreadPoolExecutor(hilos) as ex:
                for f, df in ex.map(una, bloque):
                    nuevos.append(df)
                    hechas.append(f)
        except MD.SinCreditos:
            sin_saldo = True
        except RuntimeError as e:
            log(f"  {simbolo}: {e}")
        if sin_saldo or not cli.queda_saldo():
            sin_saldo = True
            break
    if hechas:
        df = unir(cargar_existente(simbolo), nuevos)
        kb = guardar_parquet(simbolo, df) / 1024
        prog.marcar(simbolo, hechas)
        prog.guardar()
        log(f"  {simbolo}: +{len(hechas)} días · {sum(len(d) for d in nuevos):,} contratos · "
            f"total {len(df):,} filas ({kb:,.0f} KB) · créditos {cli.consumidos:,}"
            + (f" · saldo API {cli.restantes:,}" if cli.restantes is not None else ""))
    return not sin_saldo


def sonda(simbolo: str):
    cli = MD.Cliente()
    f0 = fechas_objetivo(3)[1]
    for params in ({"date": f0, "dte": "1-45"}, {"date": f0}, {"date": f0, "from": f0, "to": _de_dia(_a_dia(f0) + 45)},
                   {"dte": "1-45"}):
        r = cli.s.get(MD.BASE.format(symbol=simbolo), params={**params, "columns": MD.COLUMNAS}, timeout=60)
        try:
            js = r.json()
        except ValueError:
            js = {}
        print(f"diagnóstico {params}: HTTP {r.status_code} · s={js.get('s')} · contratos {len(js.get('optionSymbol') or [])}"
              f" · {str(js.get('errmsg') or '')[:160]} · cabeceras {[k for k in r.headers if 'ratelimit' in k.lower()]}"
              f" consumidos={r.headers.get('X-Api-Ratelimit-Consumed')}")
    for f in fechas_objetivo(3)[:2] + fechas_objetivo(3)[-1:]:
        antes = cli.consumidos
        t = time.time()
        df = cli.cadena(simbolo, f)
        print(f"{simbolo} {f}: {len(df)} contratos (|Δ| 0.10-0.90, 1-45 días) · créditos {cli.consumidos - antes}"
              f" · saldo {cli.restantes} · {time.time() - t:.1f} s")
        if len(df):
            v = df.groupby("vencimiento").agg(oi=("oi", "sum"), vol=("volumen", "sum"), iv=("iv", "median"))
            v.index = [_de_dia(x) for x in v.index]
            print(v.head(6).to_string())
            print(f"  IV calculada válida: {df['iv'].notna().mean():.0%} · OI>0: {(df['oi'] > 0).mean():.0%}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=150, help="acciones (watchlist + más líquidas)")
    ap.add_argument("--anios", type=float, default=3)
    ap.add_argument("--limite", type=int, default=95_000, help="créditos máximos por ejecución")
    ap.add_argument("--hilos", type=int, default=8)
    ap.add_argument("--minutos", type=float, default=320, help="tiempo máximo de la ejecución")
    ap.add_argument("--sonda", default="")
    a = ap.parse_args()
    if a.sonda:
        return sonda(a.sonda.upper())

    t0 = time.time()
    cli = MD.Cliente(limite_creditos=a.limite)
    prog = Progreso.cargar()
    fechas = fechas_objetivo(a.anios)
    simbolos = prioridad(a.max)
    print(f"{len(simbolos)} acciones · {len(fechas)} días hábiles ({fechas[-1]} → {fechas[0]}) · "
          f"ya descargadas {sum(len(v) for v in prog.hechos.values()):,} acción-días")
    for s in simbolos:
        if (time.time() - t0) / 60 > a.minutos:
            print("Tiempo máximo alcanzado; se sigue en la próxima ejecución.")
            break
        if not procesar(cli, prog, s, fechas, a.hilos):
            print(f"Saldo diario alcanzado ({cli.consumidos:,} créditos); se sigue mañana.")
            break
    faltan = sum(len(prog.pendientes(s, fechas)) for s in simbolos)
    print(f"Fin · créditos usados {cli.consumidos:,} · acción-días pendientes {faltan:,}")


if __name__ == "__main__":
    main()
