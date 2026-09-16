"""Consolida salidas/*.csv a webapp/datos/diario.json (legado)."""
import csv
import glob
import json
import os
import re
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "salidas")
DEST = os.path.join(os.path.dirname(BASE), "webapp", "datos", "diario.json")
DIAS = 30
TOPE_DIA = 400


def main():
    por_dia = {}
    for path in sorted(glob.glob(os.path.join(OUT, "*.csv"))):
        m = re.match(r"^(.+)_(\d{8})\.csv$", os.path.basename(path))
        if not m:
            continue
        colector, dia = m.group(1), m.group(2)
        with open(path, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    sc = int(row.get("score") or 0)
                except ValueError:
                    continue
                if sc < 1 or not (row.get("url") or "").strip():
                    continue
                por_dia.setdefault(dia, {}).setdefault(norm_url(row["url"]), row | {
                    "colector": colector, "dia": dia, "_sc": sc})
                actual = por_dia[dia][norm_url(row["url"])]
                if sc > actual["_sc"]:
                    por_dia[dia][norm_url(row["url"])] = row | {
                        "colector": colector, "dia": dia, "_sc": sc}
    dias = []
    for dia in sorted(por_dia)[-DIAS:][::-1]:
        items, cols = [], {}
        for row in por_dia[dia].values():
            cols[row["colector"]] = cols.get(row["colector"], 0) + 1
            it = {"t": row.get("titulo", ""), "f": row.get("fecha_pub", ""),
                  "u": row.get("url", ""), "s": row.get("fuente", ""),
                  "d": (row.get("snippet") or "")[:160], "sc": row["_sc"],
                  "tm": row.get("temas", ""), "q": row["colector"]}
            if (row.get("alerta_ruido") or "").strip():
                it["a"] = row["alerta_ruido"].strip()
            items.append(it)
        items.sort(key=lambda r: -r["sc"])
        dias.append({"dia": dia, "n": len(items), "colectores": cols,
                     "items": items[:TOPE_DIA]})
    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    with open(DEST, "w", encoding="utf-8") as fh:
        json.dump({"actualizado": datetime.now().strftime("%Y-%m-%d %H:%M"),
                   "dias": dias}, fh, ensure_ascii=False)
    print(f"OK {sum(d['n'] for d in dias)} ítems, {len(dias)} días -> {DEST}")
    for d in dias:
        print(f"  {d['dia']}: {d['n']} ({', '.join(f'{k}={v}' for k, v in sorted(d['colectores'].items()))})")


def norm_url(u):
    return (u or "").strip().lower().rstrip("/")


if __name__ == "__main__":
    main()
