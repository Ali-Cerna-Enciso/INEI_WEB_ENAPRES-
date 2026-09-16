"""Bing News RSS."""
import os
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from filtro import (alerta_titulo, clave_dedup, es_fresco, guardar_csv,
                    load_taxonomy, norm, parse_gnews_items, request, score)

QUERIES = (
    "ENAPRES INEI",
    '"Encuesta Nacional de Programas Presupuestales"',
)


def fetch_bing(query):
    url = ("https://www.bing.com/news/search?q="
           + urllib.parse.quote_plus(query) + "&format=rss")
    return parse_gnews_items(request(url, timeout=20))


def recolectar():
    ancla, temas, excl = load_taxonomy()
    seen, rows = set(), []
    for i, q in enumerate(QUERIES):
        if i:
            time.sleep(2)
        try:
            items = fetch_bing(q)
        except Exception as e:
            print(f"[AVISO] bing ({q}): {e}")
            continue
        for it in items:
            if not es_fresco(it["fecha_pub"]):
                continue
            url = it["url"]
            key = clave_dedup(it["titulo"], it["fuente"], url)
            if key in seen:
                continue
            seen.add(key)
            nt, nd = norm(it["titulo"]), norm(it["desc"])
            r = score(nt, nd, ancla, temas, excl)
            if r is None:
                continue
            s, cats, veto = r
            alert = ";".join(x for x in (veto, alerta_titulo(nt)) if x)
            rows.append({"fecha_pub": it["fecha_pub"], "fuente": it["fuente"] or "Bing",
                         "titulo": it["titulo"], "snippet": (it["desc"] or "")[:220],
                         "url": url, "query": f"bing:{q}", "score": s,
                         "temas": ";".join(cats), "alerta_ruido": alert})
    rows.sort(key=lambda r: -r["score"])
    print(f"[RESUMEN bing] final={len(rows)}")
    return rows


def main():
    rows = recolectar()
    out = guardar_csv("bing", rows)
    print(f"OK {len(rows)} -> {out}")


if __name__ == "__main__":
    main()
