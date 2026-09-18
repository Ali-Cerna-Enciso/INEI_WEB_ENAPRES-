"""Orquestador: backfill 2026 una vez; luego el JSON solo crece."""
from __future__ import annotations

import argparse
import sys
import traceback
from datetime import date
from pathlib import Path

SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import noticias_corpus as nc  # noqa: E402
import noticias_fetch as nf  # noqa: E402

AREAS = nc.AREAS


def correr(modo: str | None = None, areas: list[str] | None = None, on_paso=None,
           sin_gdelt: bool = False) -> dict:
    """modo=backfill | incremental | auto."""
    areas = [a for a in (areas or AREAS) if a in AREAS]
    if not areas:
        areas = list(AREAS)
    auto = modo in (None, "auto")
    if auto:
        modo = "backfill" if nc.necesita_backfill() else "incremental"
    if modo == "backfill":
        inicio, fin = date(nc.ANIO, 1, 1), nc.ahora_lima().date()
    else:
        inicio, fin = nc.ventana_incremental()
    print(f"NOTICIAS modo={modo} {inicio}..{fin} areas={areas} sin_gdelt={sin_gdelt}",
          flush=True)
    resumen = {"modo": modo, "inicio": inicio.isoformat(), "fin": fin.isoformat(),
               "areas": {}}
    for area in areas:
        if on_paso:
            on_paso(f"noticias-{area}", "inicio")
        nuevos = 0
        seen: set = set()
        try:
            tramos = nf.meses_entre(inicio, fin) if modo == "backfill" else [(inicio, fin)]
            for a, b in tramos:
                filas = nf.recolectar_gnews(area, a, b, seen, resolver=(modo == "incremental"))
                r = nc.incorporar(area, filas, "gnews")
                nuevos += r["nuevos"]
                print(f"  {area}/{a.strftime('%Y-%m')} gnews: crudo={r['crudo']} "
                      f"ok={r['ok']} nuevos={r['nuevos']}", flush=True)
                nc.reconstruir_indice({
                    "last_run": nc.ahora_lima().strftime("%Y-%m-%d %H:%M"),
                    "last_modo": modo,
                })
            for colector, fn in (
                ("bing", lambda: nf.recolectar_bing(area, seen)),
                ("feeds", lambda: nf.recolectar_feeds(area, seen)),
            ):
                filas = fn()
                r = nc.incorporar(area, filas, colector)
                nuevos += r["nuevos"]
                print(f"  {area}/{colector}: crudo={r['crudo']} ok={r['ok']} nuevos={r['nuevos']}",
                      flush=True)
            if not sin_gdelt:
                for a, b in tramos:
                    mes = a.strftime("%Y-%m")
                    filas = nf.recolectar_gdelt(area, a, b, seen)
                    r = nc.incorporar(area, filas, "gdelt")
                    nuevos += r["nuevos"]
                    print(f"  {area}/{mes} gdelt: crudo={r['crudo']} ok={r['ok']} "
                          f"nuevos={r['nuevos']}", flush=True)
                    nc.reconstruir_indice({
                        "last_run": nc.ahora_lima().strftime("%Y-%m-%d %H:%M"),
                        "last_modo": modo,
                    })
            if on_paso:
                on_paso(f"noticias-{area}", "ok", n=nuevos)
        except Exception as e:
            traceback.print_exc()
            if on_paso:
                on_paso(f"noticias-{area}", "error", error=str(e))
            resumen["areas"][area] = {"error": str(e), "nuevos": nuevos}
            continue
        resumen["areas"][area] = {"nuevos": nuevos}
    extra = {
        "last_run": nc.ahora_lima().strftime("%Y-%m-%d %H:%M"),
        "last_modo": modo,
    }
    if modo == "backfill":
        extra["backfill_2026"] = True
    nc.reconstruir_indice(extra)
    print(f"NOTICIAS listo modo={modo} -> {nc.indice_path()}", flush=True)
    return resumen


def main(argv=None):
    p = argparse.ArgumentParser(description="Actualiza noticias inseguridad/servicios")
    p.add_argument("--modo", choices=["auto", "backfill", "incremental"], default="auto")
    p.add_argument("--area", choices=list(AREAS), help="una sola pestaña")
    p.add_argument("--sin-gdelt", action="store_true",
                   help="solo Google News, Bing y RSS (si GDELT está en 429)")
    args = p.parse_args(argv)
    areas = [args.area] if args.area else None
    correr(modo=args.modo, areas=areas, sin_gdelt=args.sin_gdelt)


if __name__ == "__main__":
    main()
