"""Compila datos/catalogo.json → catalogo/data.json (alta manual)."""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rutas import datos, web

CAT = str(web() / "catalogo")
CAT_JSON = str(datos() / "catalogo.json")
TIPO_C = {"difusion": "redes", "boletin": "informes",
          "publicacion": "pub", "microdato": "micro"}
MESES_ES = {"01": "ene", "02": "feb", "03": "mar", "04": "abr",
             "05": "may", "06": "jun", "07": "jul", "08": "ago",
             "09": "set", "10": "oct", "11": "nov", "12": "dic"}


def fecha_display(f):
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", f or "")
    if m:
        return f"{m.group(3)} {MESES_ES.get(m.group(2), m.group(2))} {m.group(1)}"
    if re.match(r"^\d{4}$", (f or "").strip()):
        return (f or "").strip()
    return f or ""


def load_catalogo():
    try:
        with open(CAT_JSON, encoding="utf-8") as fh:
            items = json.load(fh)
        return [x for x in items
                if isinstance(x, dict) and x.get("url") and x.get("titulo")]
    except (OSError, ValueError):
        return []


def datos_desde_json(items):
    cards = []
    for x in items:
        temas = x.get("temas")
        if not isinstance(temas, list) or not temas:
            temas = [x.get("tema") or ""]
        cards.append({"c": TIPO_C.get(x.get("tipo", ""), "redes"),
                      "t": x.get("titulo", ""),
                      "f": fecha_display(x.get("fecha", "")),
                      "u": x.get("url", ""),
                      "g": x.get("tema", ""),
                      "gs": "|".join(t for t in temas if t),
                      "d": x.get("descripcion", ""),
                      **({"libro": x["libro"]} if x.get("libro") else {})})
    return cards


def escribir_data():
    items = load_catalogo()
    data = datos_desde_json(items)
    dest = Path(CAT) / "data.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"OK {len(data)} productos -> {dest}")
    return data


def guardar_catalogo(items):
    os.makedirs(os.path.dirname(CAT_JSON), exist_ok=True)
    tmp = CAT_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    os.replace(tmp, CAT_JSON)
    return CAT_JSON


def siguiente_id(items, tipo):
    pref = {"difusion": "dif", "boletin": "bol",
            "publicacion": "pub", "microdato": "mic"}.get(tipo, "gen")
    nums = []
    for x in items:
        m = re.match(r"^[a-z]+-(\d+)$", x.get("id") or "")
        if m and (x.get("id") or "").startswith(pref + "-"):
            nums.append(int(m.group(1)))
    return f"{pref}-{max(nums + [0]) + 1:02d}"


def agregar_item(nuevo):
    items = load_catalogo()
    if (nuevo.get("url") or "") in {x.get("url") for x in items}:
        return None, "esa URL ya está en el catálogo"
    nuevo["id"] = siguiente_id(items, nuevo.get("tipo", ""))
    items.append(nuevo)
    guardar_catalogo(items)
    return nuevo, ""


def main():
    escribir_data()


if __name__ == "__main__":
    main()
