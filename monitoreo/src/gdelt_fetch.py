"""GDELT DOC 2.1."""
import json
import os
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from datetime import date

from filtro import alerta_titulo, guardar_csv, load_taxonomy, norm, request, score

QUERY = '(ENAPRES OR "Encuesta Nacional de Programas Presupuestales") sourcelang:spanish'
MAXREC = 75


def fetch():
    q = urllib.parse.quote_plus(QUERY)
    ini = f"{date.today().year}0101000000"
    url = (f"https://api.gdeltproject.org/api/v2/doc/doc?query={q}&mode=artlist"
           f"&maxrecords={MAXREC}&format=json&startdatetime={ini}&sort=datedesc")
    return json.loads(request(url, timeout=40).decode("utf-8", "replace"))


def recolectar():
    ancla, temas, excl = load_taxonomy()
    data = None
    for intento in range(2):
        try:
            data = fetch()
            break
        except Exception as e:
            if "429" in str(e) and intento == 0:
                print("[AVISO] gdelt 429: espera 8 s y reintenta")
                time.sleep(8)
                continue
            print(f"[AVISO] gdelt: {e}")
    arts = (data or {}).get("articles", [])
    seen, rows = set(), []
    for a in arts:
        url, tit = a.get("url", ""), a.get("title", "")
        key = norm(url or tit)
        if not url or key in seen:
            continue
        seen.add(key)
        nt = norm(tit)
        res = score(nt, "", ancla, temas, excl)
        if res is None:
            continue
        s, cats, veto = res
        alert = ";".join(x for x in (veto, alerta_titulo(nt)) if x)
        rows.append({"fecha_pub": a.get("seendate", ""), "fuente": a.get("domain", "") or "gdelt",
                     "titulo": tit, "snippet": "", "url": url, "query": "gdelt:ENAPRES",
                     "score": s, "temas": ";".join(cats), "alerta_ruido": alert})
    rows.sort(key=lambda r: -r["score"])
    return rows


def main():
    rows = recolectar()
    out = guardar_csv("gdelt", rows)
    print(f"OK {len(rows)} menciones en GDELT -> {out}")
    for r in rows[:12]:
        print(f"  [{r['score']}] {r['fuente']} | {r['titulo'][:85]} | {r['temas']}")


if __name__ == "__main__":
    main()
