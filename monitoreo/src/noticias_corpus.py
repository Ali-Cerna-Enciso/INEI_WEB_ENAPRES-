"""Corpus mensual de noticias temáticas: JSON que solo crece."""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from zoneinfo import ZoneInfo

from filtro import norm, parse_fecha
from rutas import datos as datos_dir
from rutas import web

LIMA = ZoneInfo("America/Lima")
ANIO = 2026
AREAS = ("inseguridad", "servicios")
DROP_QS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
           "fbclid", "gclid", "oc", "hl", "gl", "ceid"}

DEPTOS = (
    "Amazonas", "Áncash", "Ancash", "Apurímac", "Apurimac", "Arequipa",
    "Ayacucho", "Cajamarca", "Callao", "Cusco", "Cuzco", "Huancavelica",
    "Huánuco", "Huanuco", "Ica", "Junín", "Junin", "La Libertad",
    "Lambayeque", "Lima", "Loreto", "Madre de Dios", "Moquegua", "Pasco",
    "Piura", "Puno", "San Martín", "San Martin", "Tacna", "Tumbes", "Ucayali",
)
DISTRITOS = (
    "Comas", "San Juan de Lurigancho", "Villa El Salvador", "San Martín de Porres",
    "Ate", "San Juan de Miraflores", "Villa María del Triunfo", "Los Olivos",
    "Santiago de Surco", "Chorrillos", "Puente Piedra", "Carabayllo",
    "Independencia", "Rímac", "Rimac", "La Victoria", "El Agustino",
    "San Miguel", "Miraflores", "Surquillo", "Barranco", "Breña",
    "Trujillo", "Chiclayo", "Piura", "Arequipa", "Cusco", "Iquitos",
    "Huancayo", "Pucallpa", "Chimbote", "Tacna", "Ica", "Juliaca",
)


def ahora_lima() -> datetime:
    return datetime.now(LIMA)


def raiz_noticias() -> Path:
    return datos_dir() / "noticias"


def dir_area(area: str) -> Path:
    return raiz_noticias() / area


def indice_path() -> Path:
    return raiz_noticias() / "indice.json"


def snapshot_path(area: str) -> Path:
    return web() / "datos_publicos" / f"noticias_{area}.json"


def write_json(path: Path, obj, indent=2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        __import__("json").dumps(obj, ensure_ascii=False, indent=indent),
        encoding="utf-8",
    )
    tmp.replace(path)


def read_json(path: Path, default=None):
    import json
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def canon_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    try:
        p = urlparse(u)
        qs = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
              if k.lower() not in DROP_QS]
        host = (p.netloc or "").lower()
        path = (p.path or "").rstrip("/") or "/"
        return urlunparse((p.scheme or "https", host, path, "", urlencode(qs), ""))
    except Exception:
        return u.rstrip("/").lower()


def item_id(url: str) -> str:
    return hashlib.sha1(canon_url(url).encode("utf-8", "replace")).hexdigest()[:16]


def titulo_clave(titulo: str, fuente: str) -> str:
    t = re.sub(r"\s*[-–|]\s*(x\.com|instagram\.com|facebook\.com|tiktok|youtube)\s*$",
               "", titulo or "", flags=re.I)
    return f"{norm(t)[:110]}|{norm(fuente)}"


def ubigeo_hint(titulo: str, snippet: str = "") -> list[str]:
    blob = norm(f"{titulo} {snippet}")
    hits = []
    for nombre in list(DISTRITOS) + list(DEPTOS):
        n = norm(nombre)
        if n and n in blob and nombre not in hits:
            hits.append(nombre)
        if len(hits) >= 3:
            break
    return hits


def load_mes(area: str, mes: str) -> dict:
    path = dir_area(area) / f"{mes}.json"
    data = read_json(path, None)
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return data
    return {"mes": mes, "actualizado": "", "items": []}


def save_mes(area: str, data: dict) -> None:
    mes = data["mes"]
    data["n"] = len(data.get("items") or [])
    write_json(dir_area(area) / f"{mes}.json", data)


def meses_guardados(area: str) -> list[str]:
    d = dir_area(area)
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("2026-*.json"))


def load_indice() -> dict:
    data = read_json(indice_path(), None)
    if isinstance(data, dict):
        return data
    return {
        "actualizado": "",
        "backfill_2026": False,
        "last_run": "",
        "last_modo": "",
        "areas": {},
    }


def reconstruir_indice(extra: dict | None = None) -> dict:
    areas = {}
    for area in AREAS:
        meses = {}
        n = 0
        for mes in meses_guardados(area):
            bloque = load_mes(area, mes)
            k = len(bloque.get("items") or [])
            meses[mes] = k
            n += k
        areas[area] = {"n": n, "meses": meses}
    ind = load_indice()
    ind["actualizado"] = ahora_lima().strftime("%Y-%m-%d %H:%M")
    ind["areas"] = areas
    if extra:
        ind.update(extra)
    write_json(indice_path(), ind)
    return ind


def necesita_backfill() -> bool:
    ind = load_indice()
    if ind.get("backfill_2026"):
        return False
    return not any(meses_guardados(a) for a in AREAS)


def load_area(area: str, desde: str | None = None, hasta: str | None = None) -> list[dict]:
    out = []
    for mes in meses_guardados(area):
        if desde and mes < desde[:7]:
            continue
        if hasta and mes > hasta[:7]:
            continue
        for it in load_mes(area, mes).get("items") or []:
            f = (it.get("fecha_pub") or "")[:10]
            if desde and f < desde:
                continue
            if hasta and f > hasta:
                continue
            out.append(it)
    out.sort(key=lambda r: (r.get("fecha_pub") or "", r.get("titulo") or ""), reverse=True)
    return out


def urls_area(area: str) -> set[str]:
    return {canon_url(it.get("url", "")) for it in load_area(area)} - {""}


def item_desde_fila(row: dict, area: str, colector: str) -> dict | None:
    url = (row.get("url") or "").strip()
    titulo = (row.get("titulo") or "").strip()
    if not url or not titulo:
        return None
    fecha = parse_fecha(row.get("fecha_pub"))
    if not fecha or fecha.year != ANIO:
        return None
    hoy = ahora_lima().date()
    if fecha > hoy:
        return None
    temas = row.get("temas")
    if isinstance(temas, str):
        temas = [t for t in temas.split(";") if t]
    elif not isinstance(temas, list):
        temas = []
    snip = (row.get("snippet") or "")[:280]
    try:
        score = int(row.get("score") or 1)
    except (TypeError, ValueError):
        score = 1
    return {
        "id": item_id(url),
        "url": url,
        "url_canon": canon_url(url),
        "titulo": titulo,
        "fuente": (row.get("fuente") or "").strip(),
        "colector": colector,
        "fecha_pub": fecha.isoformat(),
        "fecha_hecho": None,
        "snippet": snip,
        "temas": temas,
        "ubigeo": ubigeo_hint(titulo, snip),
        "score": score,
        "query": row.get("query") or "",
        "area": area,
        "cluster_id": None,
    }


def merge_items(existentes: list[dict], nuevos: list[dict]) -> tuple[list[dict], int]:
    """Une por URL canónica / título+fuente. Nunca borra lo ya guardado."""
    best: dict[str, dict] = {}
    orden: list[str] = []

    def clave(it: dict) -> str:
        return (it.get("url_canon") or canon_url(it.get("url", ""))
                or titulo_clave(it.get("titulo", ""), it.get("fuente", ""))
                or it.get("id") or "")

    for it in existentes:
        k = clave(it)
        if not k:
            continue
        best[k] = it
        orden.append(k)
    n_nuevo = 0
    ahora = ahora_lima().strftime("%Y-%m-%d %H:%M")
    for it in nuevos:
        k = clave(it)
        if not k:
            continue
        prev = best.get(k)
        if prev is None:
            it = dict(it)
            it["agregado"] = ahora
            best[k] = it
            orden.append(k)
            n_nuevo += 1
        else:
            # Conserva el registro viejo; solo rellena huecos.
            if not prev.get("snippet") and it.get("snippet"):
                prev["snippet"] = it["snippet"]
            if not prev.get("temas") and it.get("temas"):
                prev["temas"] = it["temas"]
            if not prev.get("ubigeo") and it.get("ubigeo"):
                prev["ubigeo"] = it["ubigeo"]
            best[k] = prev
    seen, out = set(), []
    for k in orden:
        if k in seen or k not in best:
            continue
        seen.add(k)
        out.append(best[k])
    out.sort(key=lambda r: (r.get("fecha_pub") or "", r.get("titulo") or ""), reverse=True)
    return out, n_nuevo


def incorporar(area: str, filas: list[dict], colector: str) -> dict:
    por_mes: dict[str, list] = {}
    n_ok = 0
    for row in filas:
        it = item_desde_fila(row, area, colector)
        if not it:
            continue
        por_mes.setdefault(it["fecha_pub"][:7], []).append(it)
        n_ok += 1
    n_nuevo = 0
    for mes, nuevos in sorted(por_mes.items()):
        bloque = load_mes(area, mes)
        mezclados, added = merge_items(bloque.get("items") or [], nuevos)
        bloque["items"] = mezclados
        bloque["mes"] = mes
        bloque["actualizado"] = ahora_lima().strftime("%Y-%m-%d %H:%M")
        save_mes(area, bloque)
        n_nuevo += added
    return {"area": area, "colector": colector, "crudo": len(filas),
            "ok": n_ok, "nuevos": n_nuevo, "meses": sorted(por_mes)}


def ventana_incremental(lookback_dias: int = 7) -> tuple[date, date]:
    """Si se saltan días, la siguiente corrida cubre el hueco (mín. 7 días)."""
    hoy = ahora_lima().date()
    ind = load_indice()
    last = None
    raw = (ind.get("last_run") or "")[:10]
    if raw:
        try:
            last = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            last = None
    inicio = hoy - timedelta(days=lookback_dias)
    if last:
        hueco = last - timedelta(days=1)
        if hueco < inicio:
            inicio = hueco
    if inicio.year < ANIO:
        inicio = date(ANIO, 1, 1)
    return inicio, hoy
