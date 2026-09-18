"""Orquestador: corre los colectores y escribe datos/live."""
from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import bing_fetch  # noqa: E402
import corpus  # noqa: E402
import feed_poll  # noqa: E402
import gdelt_fetch  # noqa: E402
import gobpe_fetch  # noqa: E402
import medios_fetch  # noqa: E402
import noticias_actualizar  # noqa: E402
import oficial_fetch  # noqa: E402
import rss_fetch  # noqa: E402
import yt_search  # noqa: E402

COLECTORES = (
    ("oficial", oficial_fetch.recolectar),
    ("gobpe", gobpe_fetch.recolectar),
    ("medios", medios_fetch.recolectar),
    ("gnews", rss_fetch.recolectar),
    ("feeds", feed_poll.recolectar),
    ("youtube", yt_search.recolectar),
    ("gdelt", gdelt_fetch.recolectar),
    ("bing", bing_fetch.recolectar),
)


def correr(dia: str | None = None, solo: list[str] | None = None, on_paso=None) -> dict:
    dia_iso = dia or datetime.now(ZoneInfo("America/Lima")).strftime("%Y-%m-%d")
    elegidos = {s.strip().lower() for s in (solo or []) if s.strip()}
    por_colector = {}
    for nombre, fn in COLECTORES:
        if elegidos and nombre not in elegidos:
            continue
        if on_paso:
            on_paso(nombre, "inicio")
        try:
            rows = fn() or []
            por_colector[nombre] = {"rows": rows, "error": ""}
            print(f"OK {nombre}: {len(rows)} filas")
            if on_paso:
                on_paso(nombre, "ok", n=len(rows))
        except Exception as e:
            por_colector[nombre] = {"rows": [], "error": str(e)}
            print(f"[ERROR] {nombre}: {e}")
            traceback.print_exc()
            if on_paso:
                on_paso(nombre, "error", error=str(e))
    resultado = corpus.incorporar(por_colector, corrida_iso=dia_iso)
    meta = resultado["meta"]
    print(f"LIVE: {meta['n']} menciones en {len(meta.get('dias_tocados') or [])} días "
          f"-> {corpus.LIVE}")
    try:
        resultado["noticias"] = noticias_actualizar.correr(on_paso=on_paso)
    except Exception as e:
        print(f"[ERROR] noticias: {e}")
        traceback.print_exc()
        resultado["noticias"] = {"error": str(e)}
    return resultado


def main(argv=None):
    p = argparse.ArgumentParser(description="Actualiza el corpus diario ENAPRES")
    p.add_argument("--dia", help="YYYY-MM-DD (por defecto: hoy)")
    p.add_argument("--solo", help="colectores separados por coma (ej. gobpe,medios)")
    args = p.parse_args(argv)
    solo = args.solo.split(",") if args.solo else None
    correr(dia=args.dia, solo=solo)


if __name__ == "__main__":
    main()
