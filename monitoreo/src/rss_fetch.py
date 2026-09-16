"""Google News RSS."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from filtro import (alerta_titulo, clave_dedup, es_fresco, fetch_gnews_items,
                    guardar_csv, load_taxonomy, norm, resolver_gnews, score)

QFILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "queries", "query_pack.txt")
PAUSA = 2


def load_queries():
    qs = []
    with open(QFILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("##") or line.startswith("# "):
                continue
            qs.append(line)
    return qs


def recolectar(resolver_urls=True):
    ancla, temas, excl = load_taxonomy()
    queries = load_queries()
    seen, rows = set(), []
    n_crudo = n_viejo = n_dup = 0
    for i, q in enumerate(queries):
        if i:
            time.sleep(PAUSA)
        try:
            items = fetch_gnews_items(q)
            if not items:
                print(f"[AVISO] gnews vacío ({q})")
        except Exception as e:
            print(f"[AVISO] query fallida ({q}): {e}")
            continue
        for it in items:
            n_crudo += 1
            if not es_fresco(it["fecha_pub"]):
                n_viejo += 1
                continue
            url = it["url"]
            if resolver_urls:
                try:
                    url = resolver_gnews(it["url"])
                except Exception:
                    url = it["url"]
            key = clave_dedup(it["titulo"], it["fuente"], url)
            if key in seen:
                n_dup += 1
                continue
            seen.add(key)
            nt, nd = norm(it["titulo"]), norm(it["desc"])
            r = score(nt, nd, ancla, temas, excl)
            if r is None:
                continue
            s, cats, veto = r
            alert = ";".join(x for x in (veto, alerta_titulo(nt)) if x)
            rows.append({"fecha_pub": it["fecha_pub"], "fuente": it["fuente"],
                         "titulo": it["titulo"], "snippet": it["desc"][:220],
                         "url": url, "query": q, "score": s,
                         "temas": ";".join(cats), "alerta_ruido": alert})
    rows.sort(key=lambda r: -r["score"])
    print(f"[RESUMEN gnews] crudo={n_crudo} frescos={len(rows) + 0} "
          f"viejos_filtrados={n_viejo} dup_cbmi={n_dup} final={len(rows)}")
    return rows


def main():
    rows = recolectar()
    out = guardar_csv("monitoreo", rows)
    print(f"OK {len(rows)} menciones -> {out}")
    for r in rows[:10]:
        print(f"  [{r['score']}] {r['fuente']} | {r['titulo'][:90]} | {r['temas']}")


if __name__ == "__main__":
    main()
