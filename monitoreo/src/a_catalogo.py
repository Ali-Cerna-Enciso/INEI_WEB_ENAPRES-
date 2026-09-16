"""Escribe catalogo/data.json y catalogo/prensa.json (el HTML no se toca)."""
import csv
import glob
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corpus
from rutas import MONITOREO, datos, web

BASE = str(MONITOREO)
OUT = os.path.join(BASE, "salidas")
CAT = str(web() / "catalogo")
CAT_JSON = str(datos() / "catalogo.json")
WEB_EXTRA = str(datos() / "web_extra.json")
EMOJI_TEMA = {"Servicios básicos": "🏠", "Agua y saneamiento": "💧",
              "Electrificación": "⚡", "Seguridad ciudadana": "🛡️",
              "Seguridad vial": "🚗", "Dengue": "🦟",
              "Rabia canina": "🐕", "Uso de videojuegos": "🎮",
              "Libros digitales": "📚", "Visita a museos": "🏛️",
              "General": "📊"}
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


def load_web_extra():
    try:
        with open(WEB_EXTRA, encoding="utf-8") as fh:
            rows = json.load(fh)
        return [x for x in rows if isinstance(x, dict) and x.get("u") and x.get("t")]
    except (OSError, ValueError):
        return []


def mezclar_prensa(pub):
    seen, out = set(), []
    for x in list(pub) + load_web_extra():
        u = x.get("u") or ""
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(x)
    out.sort(key=lambda r: r.get("f") or "", reverse=True)
    return out


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
                      "d": x.get("descripcion", "")})
    return cards


def escribir_data():
    items = load_catalogo()
    data = datos_desde_json(items)
    dest = Path(CAT) / "data.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"OK {len(data)} productos -> {dest}")
    return data


def latest_per_prefix():
    groups = {}
    for path in glob.glob(os.path.join(OUT, "*.csv")):
        m = re.match(r"^(.+)_(\d{8})\.csv$", os.path.basename(path))
        if m:
            groups.setdefault(m.group(1), []).append(path)
    return {k: sorted(v)[-1] for k, v in groups.items()}


def _pub_desde_items(items):
    seen, pub = set(), []
    for it in items:
        if (it.get("alerta") or "").strip():
            continue
        try:
            s = int(it.get("score") or 0)
        except (TypeError, ValueError):
            continue
        url = it.get("url") or ""
        if s < 2 or not url or url in seen:
            continue
        seen.add(url)
        pub.append({"t": it.get("titulo", ""), "f": it.get("fecha_pub") or it.get("fecha_pub_raw", ""),
                    "u": url, "d": (it.get("snippet") or "")[:220], "s": s,
                    "src": it.get("fuente", ""),
                    "temas": ";".join(it.get("temas") or []) if isinstance(it.get("temas"), list)
                    else (it.get("temas") or "")})
    pub.sort(key=lambda r: -r["s"])
    return pub


def desde_live():
    items = corpus.load_rango(desde="2026-01-01")
    if not items:
        return publicar([])
    return publicar(_pub_desde_items(items))


def desde_csv():
    seen, pub = set(), []
    for pref, f in sorted(latest_per_prefix().items()):
        n0 = len(pub)
        with open(f, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if (row.get("alerta_ruido") or "").strip():
                    continue
                try:
                    s = int(row.get("score") or 0)
                except ValueError:
                    continue
                if s < 2 or row["url"] in seen:
                    continue
                seen.add(row["url"])
                pub.append({"t": row["titulo"], "f": row["fecha_pub"], "u": row["url"],
                            "d": (row.get("snippet") or "")[:220], "s": s,
                            "src": row.get("fuente", ""), "temas": row.get("temas", "")})
        print(f"  {pref}: +{len(pub) - n0}")
    pub.sort(key=lambda r: -r["s"])
    return publicar(pub)


def publicar(pub):
    os.makedirs(CAT, exist_ok=True)
    escribir_data()
    pub = mezclar_prensa(pub)
    hoy = datetime.now().strftime("%Y-%m-%d %H:%M")
    Path(CAT, "prensa.json").write_text(
        json.dumps(pub, ensure_ascii=False), encoding="utf-8")
    Path(CAT, "meta.json").write_text(
        json.dumps({"actualizado": hoy}, ensure_ascii=False), encoding="utf-8")
    print(f"OK {len(pub)} menciones -> {CAT}/prensa.json ({hoy})")
    return pub


def main():
    indice = corpus.load_indice()
    if indice.get("dias"):
        desde_live()
    else:
        desde_csv()


if __name__ == "__main__":
    main()


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
