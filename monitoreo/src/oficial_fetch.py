"""Difusión OTD desde fuentes/oficial.csv."""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from filtro import BASE, COLS

OFILE = os.path.join(BASE, "fuentes", "oficial.csv")


def recolectar():
    rows = []
    if not os.path.isfile(OFILE):
        print("[AVISO] no existe fuentes/oficial.csv")
        return rows
    with open(OFILE, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            item = {k: (row.get(k) or "").strip() for k in COLS}
            if item.get("url") and item.get("titulo"):
                rows.append(item)
    print(f"OK oficial: {len(rows)} difusiones OTD")
    return rows


if __name__ == "__main__":
    for r in recolectar():
        print(f"  {r['fecha_pub']} | {r['titulo'][:70]}")
