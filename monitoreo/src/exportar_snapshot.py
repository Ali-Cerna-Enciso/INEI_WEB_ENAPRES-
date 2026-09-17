"""Escribe datos_publicos/menciones.json (live + aportes en web_extra.json)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import corpus  # noqa: E402
from rutas import datos, web  # noqa: E402

DEST = web() / "datos_publicos" / "menciones.json"
WEB_EXTRA = datos() / "web_extra.json"


def _temas(val):
    if isinstance(val, list):
        return [str(t) for t in val if t]
    return [t for t in str(val or "").split(";") if t]


def load_web_extra():
    try:
        rows = json.loads(WEB_EXTRA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for x in rows:
        if not isinstance(x, dict):
            continue
        url = x.get("u") or x.get("url") or ""
        titulo = x.get("t") or x.get("titulo") or ""
        if not url or not titulo:
            continue
        try:
            score = int(x.get("s") or x.get("score") or 0)
        except (TypeError, ValueError):
            score = 0
        fecha = x.get("f") or x.get("fecha_pub") or ""
        out.append({
            "titulo": titulo,
            "url": url,
            "fuente": x.get("src") or x.get("fuente") or "aporte",
            "colector": "extra",
            "fecha_pub": fecha,
            "fecha_pub_raw": fecha,
            "snippet": (x.get("d") or x.get("snippet") or "")[:220],
            "score": score,
            "temas": _temas(x.get("temas")),
            "alerta": "",
            "del_dia": False,
            "nuevo": False,
            "query": "web_extra",
        })
    return out


def mezclar(items, extra):
    seen, out = set(), []
    for it in list(items) + extra:
        url = it.get("url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(it)
    return out


def main() -> None:
    items = corpus.load_rango(desde="2026-01-01")
    for it in items:
        it.pop("_carpeta", None)
    items = mezclar(items, load_web_extra())
    indice = corpus.load_indice()
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps({
        "actualizado": indice.get("actualizado", ""),
        "max_live": indice.get("max_live", 31),
        "items": items,
    }, ensure_ascii=False), encoding="utf-8")
    print(f"snapshot: {len(items)} menciones -> {DEST}")


if __name__ == "__main__":
    main()
