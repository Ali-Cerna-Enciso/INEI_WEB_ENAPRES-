"""Prensa peruana y redes indexadas en Google News."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from filtro import (BASE, alerta_titulo, clave_dedup, es_fresco,
                    fetch_gnews_items, guardar_csv, load_taxonomy, norm,
                    resolver_facebook, resolver_gnews, score)

MFILE = os.path.join(BASE, "fuentes", "medios.txt")
LOTE = 5
PAUSA = 2
QUERIES_RED = {
    "facebook.com": (
        "ENAPRES site:facebook.com",
        "#ENAPRES site:facebook.com",
    ),
    "x.com": (
        "ENAPRES site:x.com",
        "#ENAPRES site:x.com",
        'site:x.com "Encuesta Nacional de Programas Presupuestales"',
    ),
    "instagram.com": (
        "ENAPRES site:instagram.com",
        "#ENAPRES site:instagram.com",
    ),
    "tiktok.com": (
        "#ENAPRES site:tiktok.com",
        'site:tiktok.com "Encuesta Nacional de Programas Presupuestales"',
    ),
    "youtube.com": (
        "ENAPRES site:youtube.com",
    ),
}


def load_medios():
    prensa, redes = [], []
    sec = None
    with open(MFILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                sec = line[1:-1].strip().lower()
                continue
            dom = line.split("|", 1)[0].strip().lower()
            if not dom:
                continue
            if sec == "prensa":
                prensa.append(dom)
            elif sec == "redes":
                redes.append(dom)
    return prensa, redes


def lotes(doms, n=LOTE):
    return [doms[i:i + n] for i in range(0, len(doms), n)]


def recolectar(resolver_urls=True):
    ancla, temas, excl = load_taxonomy()
    prensa, redes = load_medios()
    queries = [("prensa-%d" % (i + 1),
                "ENAPRES (" + " OR ".join("site:" + d for d in lote) + ")")
               for i, lote in enumerate(lotes(prensa))]
    for d in redes:
        for j, q in enumerate(QUERIES_RED.get(d, (f"ENAPRES site:{d}",))):
            queries.append((f"redes-{d}-{j + 1}", q))
    seen, rows = set(), []
    n_crudo = n_viejo = n_dup = 0
    for i, (tag, q) in enumerate(queries):
        if i:
            time.sleep(PAUSA)
        try:
            items = fetch_gnews_items(q)
            if not items:
                print(f"[AVISO] gnews vacío ({tag})")
        except Exception as e:
            print(f"[AVISO] medios falló ({tag}): {e}")
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
            if tag == "redes" and "facebook.com" in (url or ""):
                try:
                    u2, _t2, d2 = resolver_facebook(url)
                    url = u2
                    if d2:
                        it["desc"] = d2
                except Exception:
                    pass
            key = clave_dedup(it["titulo"], it["fuente"] or "gnews-sites", url)
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
            rows.append({"fecha_pub": it["fecha_pub"], "fuente": it["fuente"] or "gnews-sites",
                         "titulo": it["titulo"], "snippet": it["desc"][:220], "url": url,
                         "query": "medios:" + tag, "score": s,
                         "temas": ";".join(cats), "alerta_ruido": alert})
    rows.sort(key=lambda r: -r["score"])
    print(f"[RESUMEN medios] crudo={n_crudo} viejos_filtrados={n_viejo} "
          f"dup_cbmi={n_dup} final={len(rows)}")
    return rows


def main():
    rows = recolectar()
    out = guardar_csv("medios", rows)
    print(f"OK {len(rows)} menciones focalizadas -> {out}")
    for r in rows[:12]:
        print(f"  [{r['score']}] {r['fuente']} | {r['titulo'][:85]} | {r['temas']}")


if __name__ == "__main__":
    main()
