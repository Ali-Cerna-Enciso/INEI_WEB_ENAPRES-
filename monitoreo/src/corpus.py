"""Corpus diario: datos/live (máx. 31 días) y archivo jsonl.gz."""
from __future__ import annotations

import gzip
import json
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from filtro import guardar_csv, norm, parse_fecha
from rutas import datos as datos_dir
from rutas import web

DATOS = datos_dir()
LIVE = DATOS / "live"
ARCHIVO = DATOS / "archivo"
INDICE = DATOS / "indice.json"
ARCHIVO_INDICE = ARCHIVO / "indice.json"
DIARIO_VIEJO = web() / "datos" / "diario.json"
MAX_LIVE = 31
HORIZONTE = None
INSTITUCIONAL = {"oficial", "gobpe"}


def norm_url(u: str) -> str:
    return (u or "").strip().lower().rstrip("/")


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def urls_en_live(excepto: str | None = None) -> set[str]:
    seen: set[str] = set()
    if not LIVE.exists():
        return seen
    for carpeta in LIVE.iterdir():
        if not carpeta.is_dir() or carpeta.name == excepto:
            continue
        data = read_json(carpeta / "menciones.json", [])
        for it in data:
            seen.add(norm_url(it.get("url", "")))
    seen.discard("")
    return seen


def titulo_clave(titulo: str, fuente: str) -> str:
    t = re.sub(r"\s*[-–|]\s*(x\.com|instagram\.com|facebook\.com|tiktok|youtube)\s*$",
               "", titulo or "", flags=re.I)
    return f"{norm(t)[:110]}|{norm(fuente)}"


def item_desde_fila(row: dict, colector: str, _corrida: str, urls_previos: set[str],
                    hoy: date | None = None) -> dict | None:
    url = (row.get("url") or "").strip()
    titulo = (row.get("titulo") or "").strip()
    if not url or not titulo:
        return None
    try:
        sc = int(row.get("score") or 0)
    except (TypeError, ValueError):
        return None
    if sc < 1:
        return None
    fecha = parse_fecha(row.get("fecha_pub"))
    if not fecha:
        return None
    hoy = hoy or date.today()
    if fecha > hoy:
        return None
    if fecha.year < hoy.year:
        return None
    temas = [t for t in (row.get("temas") or "").split(";") if t]
    return {
        "titulo": titulo,
        "url": url,
        "fuente": (row.get("fuente") or "").strip(),
        "colector": colector,
        "fecha_pub": fecha.isoformat(),
        "fecha_pub_raw": row.get("fecha_pub") or "",
        "snippet": (row.get("snippet") or "")[:280],
        "score": sc,
        "temas": temas,
        "alerta": (row.get("alerta_ruido") or "").strip(),
        "del_dia": True,
        "nuevo": norm_url(url) not in urls_previos,
        "query": row.get("query") or "",
    }


def _dedup(items: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for it in items:
        key = titulo_clave(it.get("titulo", ""), it.get("fuente", "")) or norm_url(it["url"])
        prev = best.get(key)
        if prev is None or it["score"] > prev["score"]:
            best[key] = it
    out = list(best.values())
    out.sort(key=lambda r: (not r.get("nuevo"), -r["score"], r.get("fuente") or ""))
    return out


def merge_dia(dia_iso: str, nuevos: list[dict], colectores_extra: dict | None = None) -> dict:
    existentes, meta = load_dia(dia_iso)
    best: dict[str, dict] = {}
    for it in existentes + nuevos:
        key = titulo_clave(it.get("titulo", ""), it.get("fuente", "")) or norm_url(it.get("url", ""))
        prev = best.get(key)
        if prev is None or int(it.get("score") or 0) > int(prev.get("score") or 0):
            best[key] = it
    items = _dedup(list(best.values()))
    cols = dict(meta.get("colectores") or {})
    if colectores_extra:
        for k, v in colectores_extra.items():
            cols[k] = v
    meta = {
        "dia": dia_iso,
        "actualizado": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "n": len(items),
        "n_del_dia": len(items),
        "n_nuevo": sum(1 for i in items if i.get("nuevo")),
        "colectores": cols,
    }
    carpeta = LIVE / dia_iso
    carpeta.mkdir(parents=True, exist_ok=True)
    write_json(carpeta / "menciones.json", items)
    write_json(carpeta / "meta.json", meta)
    return meta


def incorporar(por_colector: dict, corrida_iso: str | None = None) -> dict:
    """Reparte hallazgos a la carpeta de SU fecha de publicación y fusiona."""
    corrida_iso = corrida_iso or date.today().isoformat()
    crudo = LIVE / corrida_iso / "crudo"
    crudo.mkdir(parents=True, exist_ok=True)
    previos = urls_en_live()
    por_fecha: dict[str, list] = {}
    colectores: dict[str, dict] = {}
    hoy = date.today()
    for nombre, payload in por_colector.items():
        rows = payload.get("rows") or []
        error = payload.get("error") or ""
        if rows:
            guardar_csv(nombre, rows, outdir=str(crudo))
        n_ok = 0
        for row in rows:
            it = item_desde_fila(row, nombre, corrida_iso, previos, hoy=hoy)
            if not it:
                continue
            por_fecha.setdefault(it["fecha_pub"], []).append(it)
            n_ok += 1
        colectores[nombre] = {"n": n_ok, "crudo": len(rows), "error": error, "ok": not error}
    metas = []
    for dia_iso, nuevos in sorted(por_fecha.items(), reverse=True):
        metas.append(merge_dia(dia_iso, nuevos, colectores_extra=colectores))
    rotar()
    indice = reconstruir_indice()
    n_total = sum(m["n"] for m in metas) if metas else 0
    resumen = {"meta": {"n": n_total, "n_nuevo": sum(m.get("n_nuevo", 0) for m in metas),
                        "colectores": colectores, "dias_tocados": list(por_fecha.keys())},
               "indice": indice}
    return resumen


def guardar_dia(dia_iso: str, por_colector: dict, meta_extra: dict | None = None) -> dict:
    return incorporar(por_colector, corrida_iso=dia_iso)


def rotar(max_live: int = MAX_LIVE) -> list[str]:
    if not LIVE.exists():
        return []
    dias = sorted(p.name for p in LIVE.iterdir() if p.is_dir() and _es_dia(p.name))
    movidos = []
    while len(dias) > max_live:
        viejo = dias.pop(0)
        _archivar(viejo)
        movidos.append(viejo)
    return movidos


def _es_dia(nombre: str) -> bool:
    try:
        datetime.strptime(nombre, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _archivar(dia_iso: str) -> Path:
    carpeta = LIVE / dia_iso
    items = read_json(carpeta / "menciones.json", [])
    ARCHIVO.mkdir(parents=True, exist_ok=True)
    dest = ARCHIVO / f"{dia_iso}.jsonl.gz"
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        for it in items:
            compacto = {
                "dia": dia_iso,
                "titulo": it.get("titulo", ""),
                "url": it.get("url", ""),
                "fuente": it.get("fuente", ""),
                "colector": it.get("colector", ""),
                "fecha_pub": it.get("fecha_pub", ""),
                "score": it.get("score", 0),
                "temas": it.get("temas") or [],
                "snippet": (it.get("snippet") or "")[:200],
                "alerta": it.get("alerta") or "",
            }
            fh.write(json.dumps(compacto, ensure_ascii=False) + "\n")
    tmp.replace(dest)
    shutil.rmtree(carpeta, ignore_errors=True)
    inv = read_json(ARCHIVO_INDICE, {"dias": []})
    inv.setdefault("dias", [])
    inv["dias"] = [d for d in inv["dias"] if d.get("dia") != dia_iso]
    inv["dias"].append({
        "dia": dia_iso,
        "n": len(items),
        "archivo": dest.name,
        "bytes": dest.stat().st_size,
        "archivado": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    inv["dias"].sort(key=lambda d: d["dia"], reverse=True)
    write_json(ARCHIVO_INDICE, inv)
    return dest


def reconstruir_indice() -> dict:
    dias = []
    if LIVE.exists():
        for carpeta in sorted(LIVE.iterdir(), reverse=True):
            if not carpeta.is_dir() or not _es_dia(carpeta.name):
                continue
            meta = read_json(carpeta / "meta.json") or {}
            items = read_json(carpeta / "menciones.json", [])
            cols = {}
            for it in items:
                q = it.get("colector") or "?"
                cols[q] = cols.get(q, 0) + 1
            dias.append({
                "dia": carpeta.name,
                "n": meta.get("n", len(items)),
                "n_del_dia": meta.get("n_del_dia", meta.get("n", len(items))),
                "n_nuevo": meta.get("n_nuevo", sum(1 for i in items if i.get("nuevo"))),
                "actualizado": meta.get("actualizado", ""),
                "colectores": meta.get("colectores") or cols,
            })
    arch = read_json(ARCHIVO_INDICE, {"dias": []})
    indice = {
        "actualizado": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "max_live": MAX_LIVE,
        "dias": dias,
        "archivo": arch.get("dias") or [],
    }
    write_json(INDICE, indice)
    return indice


def load_indice() -> dict:
    data = read_json(INDICE)
    if data and data.get("dias"):
        return data
    return reconstruir_indice()


def load_dia(dia_iso: str) -> tuple[list[dict], dict]:
    carpeta = LIVE / dia_iso
    return read_json(carpeta / "menciones.json", []) or [], read_json(carpeta / "meta.json") or {}


def load_rango(dias: int | None = None, desde: str | None = None) -> list[dict]:
    hoy = date.today()
    corte = None
    if desde:
        try:
            corte = datetime.strptime(desde, "%Y-%m-%d").date()
        except ValueError:
            corte = None
    elif dias is not None:
        corte = hoy - timedelta(days=dias - 1)
    out = []
    if not LIVE.exists():
        return out
    for carpeta in sorted(LIVE.iterdir(), reverse=True):
        if not carpeta.is_dir() or not _es_dia(carpeta.name):
            continue
        d = datetime.strptime(carpeta.name, "%Y-%m-%d").date()
        if corte and d < corte:
            continue
        items, _ = load_dia(carpeta.name)
        for it in items:
            it = dict(it)
            it["_carpeta"] = carpeta.name
            out.append(it)
    out.sort(key=lambda r: (r.get("fecha_pub") or "", -int(r.get("score") or 0)), reverse=True)
    return out


def load_archivo_dia(dia_iso: str) -> list[dict]:
    path = ARCHIVO / f"{dia_iso}.jsonl.gz"
    if not path.exists():
        return []
    out = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def migrar_diario_viejo() -> bool:
    if any(LIVE.glob("*/menciones.json")):
        return False
    viejo = read_json(DIARIO_VIEJO)
    if not viejo or not viejo.get("dias"):
        return False
    for bloque in viejo["dias"]:
        raw = bloque.get("dia") or ""
        if len(raw) == 8:
            dia_iso = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
        else:
            continue
        urls_prev = urls_en_live(excepto=dia_iso)
        items = []
        for it in bloque.get("items") or []:
            fila = {
                "titulo": it.get("t", ""),
                "fecha_pub": it.get("f", ""),
                "url": it.get("u", ""),
                "fuente": it.get("s", ""),
                "snippet": it.get("d", ""),
                "score": it.get("sc", 0),
                "temas": it.get("tm", ""),
                "alerta_ruido": it.get("a", ""),
                "query": it.get("q", ""),
            }
            conv = item_desde_fila(fila, it.get("q") or "legacy", dia_iso, urls_prev)
            if conv:
                items.append(conv)
        items = _dedup(items)
        cols = {}
        for it in items:
            cols[it["colector"]] = cols.get(it["colector"], 0) + 1
        carpeta = LIVE / dia_iso
        carpeta.mkdir(parents=True, exist_ok=True)
        write_json(carpeta / "menciones.json", items)
        write_json(carpeta / "meta.json", {
            "dia": dia_iso,
            "actualizado": viejo.get("actualizado") or "",
            "n": len(items),
            "n_del_dia": len(items),
            "n_nuevo": sum(1 for i in items if i.get("nuevo")),
            "colectores": {k: {"n": v, "crudo": v, "error": "", "ok": True} for k, v in cols.items()},
            "origen": "migracion-diario.json",
        })
    rotar()
    reconstruir_indice()
    return True


def refiltrar_live() -> None:
    if not LIVE.exists():
        return
    for carpeta in LIVE.iterdir():
        if not carpeta.is_dir() or not _es_dia(carpeta.name):
            continue
        items = read_json(carpeta / "menciones.json", []) or []
        keep = []
        for it in items:
            fecha = parse_fecha(it.get("fecha_pub") or it.get("fecha_pub_raw"))
            if not es_del_dia(fecha, carpeta.name):
                continue
            it["del_dia"] = True
            it.pop("fresco", None)
            keep.append(it)
        keep = _dedup(keep)
        meta = read_json(carpeta / "meta.json") or {}
        meta["n"] = len(keep)
        meta["n_del_dia"] = len(keep)
        meta["n_nuevo"] = sum(1 for i in keep if i.get("nuevo"))
        write_json(carpeta / "menciones.json", keep)
        write_json(carpeta / "meta.json", meta)
    reconstruir_indice()
