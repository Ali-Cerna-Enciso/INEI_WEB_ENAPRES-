"""Búsqueda YouTube (página de resultados)."""
import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from filtro import alerta_titulo, guardar_csv, load_taxonomy, norm, request, score

QUERIES = ["ENAPRES", "ENAPRES INEI encuesta", "Encuesta Nacional de Programas Presupuestales"]


def u(s):
    try:
        s2 = s.encode().decode("unicode_escape")
    except Exception:
        return s
    try:
        return s2.encode("latin1").decode("utf-8")
    except Exception:
        return s2


def search(query):
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
    return request(url).decode("utf-8", "replace")


def parse(html):
    out = []
    for chunk in html.split('"videoRenderer":')[1:]:
        m = re.search(r'"videoId":"([A-Za-z0-9_-]{11})"', chunk)
        t = re.search(r'"title":\{"runs":\[\{"text":"(.*?)"', chunk)
        c = re.search(r'"longBylineText":\{"runs":\[\{"text":"(.*?)"', chunk)
        if m and t:
            title = u(t.group(1))
            chan = u(c.group(1)) if c else ""
            out.append({"id": m.group(1), "titulo": title, "canal": chan})
    return out


def recolectar():
    ancla, temas, excl = load_taxonomy()
    seen, rows = set(), []
    for i, q in enumerate(QUERIES):
        if i:
            time.sleep(2)
        try:
            videos = parse(search(q))
        except Exception as e:
            print(f"[AVISO] youtube falló ({q}): {e}")
            continue
        for v in videos:
            if v["id"] in seen:
                continue
            seen.add(v["id"])
            nt = norm(v["titulo"] + " " + v["canal"])
            res = score(nt, "", ancla, temas, excl)
            if res is None:
                continue
            s, cats, veto = res
            alert = ";".join(x for x in (veto, alerta_titulo(nt)) if x)
            rows.append({"fecha_pub": "", "fuente": "YouTube/" + (v["canal"] or "?"),
                         "titulo": v["titulo"], "snippet": v["canal"],
                         "url": "https://www.youtube.com/watch?v=" + v["id"],
                         "query": f"yt:{q}", "score": s,
                         "temas": ";".join(cats), "alerta_ruido": alert})
    rows.sort(key=lambda r: -r["score"])
    return rows


def main():
    rows = recolectar()
    out = guardar_csv("yt", rows)
    print(f"OK {len(rows)} menciones en YouTube -> {out}")
    for r in rows[:12]:
        print(f"  [{r['score']}] {r['fuente']} | {r['titulo'][:85]} | {r['temas']}")


if __name__ == "__main__":
    main()
