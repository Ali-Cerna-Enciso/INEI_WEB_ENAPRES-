"""Escribe datos_publicos/noticias_*.json para Streamlit Cloud."""
from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import noticias_corpus as nc  # noqa: E402


def exportar_area(area: str) -> int:
    items = nc.load_area(area, desde="2026-01-01")
    dest = nc.snapshot_path(area)
    dest.parent.mkdir(parents=True, exist_ok=True)
    ind = nc.load_indice()
    nc.write_json(dest, {
        "actualizado": ind.get("actualizado") or "",
        "area": area,
        "n": len(items),
        "items": items,
    }, indent=None)
    print(f"snapshot {area}: {len(items)} -> {dest}")
    return len(items)


def main() -> None:
    for area in nc.AREAS:
        exportar_area(area)


if __name__ == "__main__":
    main()
