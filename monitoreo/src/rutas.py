"""Raíz del proyecto: carpeta padre de monitoreo/."""
from pathlib import Path

MONITOREO = Path(__file__).resolve().parents[1]


def raiz() -> Path:
    return MONITOREO.parent


def web() -> Path:
    r = raiz()
    if (r / "app.py").is_file():
        return r
    return r / "webapp"


def datos() -> Path:
    return raiz() / "datos"
