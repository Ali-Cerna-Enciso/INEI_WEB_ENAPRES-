"""Feeds RSS/Atom de fuentes.txt."""
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from filtro import (BASE, alerta_titulo, clean_html, guardar_csv, load_taxonomy,
                    norm, request, score)

FFEEDS = os.path.join(BASE, "fuentes", "feeds.txt")
ATOM = "{http://www.w3.org/2005/Atom}"


def text(el):
    return (el.text or "").strip() if el is not None else ""


def parse_feed(xml):
    if isinstance(xml, bytes):
        xml = xml.lstrip(b"\xef\xbb\xbf \t\r\n")
        xml = xml.decode("utf-8", "replace")
    else:
        xml = str(xml).lstrip("\ufeff \t\r\n")
    root = ET.fromstring(xml)
    items = []
    if root.tag == "rss":
        for it in root.iter("item"):
            desc = text(it.find("description"))
            items.append({"titulo": text(it.find("title")), "url": text(it.find("link")),
                          "fecha_pub": text(it.find("pubDate")), "desc": clean_html(desc)})
    elif root.tag.endswith("feed"):
        for e in root.findall(f"{ATOM}entry"):
            link = ""
            for l in e.findall(f"{ATOM}link"):
                if l.get("rel", "alternate") == "alternate" and l.get("href"):
                    link = l.get("href")
                    break
            fecha = text(e.find(f"{ATOM}published")) or text(e.find(f"{ATOM}updated"))
            desc = text(e.find(f"{ATOM}summary")) + " " + text(e.find(f"{ATOM}content"))
            items.append({"titulo": text(e.find(f"{ATOM}title")), "url": link,
                          "fecha_pub": fecha, "desc": clean_html(desc)})
    return items


def recolectar():
    ancla, temas, excl = load_taxonomy()
    feeds = []
    with open(FFEEDS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                nombre, url = line.split("|", 1)
                feeds.append((nombre.strip(), url.strip()))
    seen, rows = set(), []
    for nombre, url in feeds:
        try:
            items = parse_feed(request(url))
        except Exception as e:
            print(f"[AVISO] feed fallido ({nombre}): {e}")
            continue
        for it in items:
            key = norm(it["url"] or it["titulo"])
            if key in seen:
                continue
            seen.add(key)
            nt, nd = norm(it["titulo"]), norm(it["desc"])
            res = score(nt, nd, ancla, temas, excl)
            if res is None:
                continue
            s, cats, veto = res
            alert = ";".join(x for x in (veto, alerta_titulo(nt)) if x)
            rows.append({"fecha_pub": it["fecha_pub"], "fuente": nombre,
                         "titulo": it["titulo"], "snippet": it["desc"][:220],
                         "url": it["url"], "query": f"feed:{nombre}",
                         "score": s, "temas": ";".join(cats), "alerta_ruido": alert})
    rows.sort(key=lambda r: -r["score"])
    return rows


def main():
    rows = recolectar()
    out = guardar_csv("feeds", rows)
    print(f"OK {len(rows)} menciones en feeds -> {out}")
    for r in rows[:12]:
        print(f"  [{r['score']}] {r['fuente']} | {r['titulo'][:85]} | {r['temas']}")


if __name__ == "__main__":
    main()
