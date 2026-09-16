"""Escribe datos_publicos/menciones.json desde el corpus live."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import corpus  # noqa: E402
from rutas import web  # noqa: E402

DEST = web() / "datos_publicos" / "menciones.json"


def main() -> None:
    items = corpus.load_rango(desde="2026-01-01")
    for it in items:
        it.pop("_carpeta", None)
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
