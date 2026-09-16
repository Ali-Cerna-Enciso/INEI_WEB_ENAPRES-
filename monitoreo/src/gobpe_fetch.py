"""Noticias INEI en gob.pe."""
from __future__ import annotations

import html as htmlmod
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from filtro import (alerta_titulo, clean_html, guardar_csv, load_taxonomy, norm,
                    parse_fecha, request, score)

GOB = "https://www.gob.pe"
TERMS = ["ENAPRES"]
HREF = re.compile(r'href="([^"]+)"', re.I)
PAUSA = 0.35


def _json_array(html: str, key: str = '"results":'):
    i = html.find(key)
    if i < 0:
        return []
    i = html.find("[", i)
    if i < 0:
        return []
    depth = 0
    for j, c in enumerate(html[i:], i):
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[i:j + 1])
                except json.JSONDecodeError:
                    return []
    return []


def _total(html: str) -> int:
    m = re.search(r'"total_count":(\d+)', html)
    return int(m.group(1)) if m else 0


def _href(item: dict) -> str:
    if not isinstance(item, dict):
        return ""
    au = (item.get("action_url") or "").strip()
    if au.startswith("http"):
        return au
    if au.startswith("/"):
        return GOB + au
    raw = item.get("url") or ""
    m = HREF.search(raw)
    if not m:
        return ""
    h = htmlmod.unescape(m.group(1))
    if h.startswith("http"):
        return h
    if h.startswith("/"):
        return GOB + h
    return ""


def buscar_listado(term: str):
    """Pagina el buscador gob.pe: institución INEI + noticias + término."""
    vistos, out = set(), []
    sheet, total = 1, None
    while sheet <= 12:
        url = (GOB + "/busquedas?contenido[]=noticias&institucion[]=inei&term="
               + urllib.parse.quote_plus(term))
        if sheet > 1:
            url += f"&sheet={sheet}"
        try:
            html = request(url, timeout=30).decode("utf-8", "replace")
        except Exception as e:
            print(f"[AVISO] gob.pe listado falló ({term} p.{sheet}): {e}")
            break
        if total is None:
            total = _total(html)
        filas = [x for x in _json_array(html) if isinstance(x, dict)]
        nuevos = 0
        for item in filas:
            href = _href(item)
            if not href or href in vistos:
                continue
            vistos.add(href)
            out.append(item)
            nuevos += 1
        print(f"  gob.pe «{term}» hoja {sheet}: +{nuevos} (acum {len(out)}/{total or '?'})")
        if not filas or nuevos == 0:
            break
        if total and len(out) >= min(total, 80):
            break
        if total and total > 80 and sheet >= 2:
            print(f"  gob.pe «{term}»: {total} hits, recorto a {len(out)} (consulta demasiado amplia)")
            break
        sheet += 1
        time.sleep(PAUSA)
    return out


def leer_nota(url: str) -> tuple[str, str]:
    """Abre la nota: snippet (og:description) + cuerpo (data-contents)."""
    html = request(url, timeout=25).decode("utf-8", "replace")
    desc = ""
    m = re.search(r'property="og:description"\s+content="([^"]*)"', html, re.I)
    if not m:
        m = re.search(r'name="description"\s+content="([^"]*)"', html, re.I)
    if m:
        desc = htmlmod.unescape(m.group(1))
    cuerpo = ""
    m2 = re.search(r'data-contents="([^"]{40,})"', html)
    if m2:
        cuerpo = htmlmod.unescape(m2.group(1))
    texto = clean_html(cuerpo or desc)
    return (clean_html(desc)[:220] if desc else texto[:220]), texto


def _snip_con_ancla(texto: str, ancla) -> str:
    m = re.search(r".{0,50}ENAPRES.{0,160}", texto or "", re.I)
    if m:
        return m.group(0).strip()
    m = re.search(r".{0,40}Encuesta Nacional de Programas Presupuestales.{0,120}",
                  texto or "", re.I)
    if m:
        return m.group(0).strip()
    return (texto or "")[:220]


def recolectar():
    ancla, temas, excl = load_taxonomy()
    anio = date.today().year
    seen, rows = set(), []
    listados = []
    for term in TERMS:
        listados.extend(buscar_listado(term))

    por_url = {}
    for item in listados:
        href = _href(item)
        if href and href not in por_url:
            por_url[href] = item

    for url, item in por_url.items():
        fecha = parse_fecha(item.get("publication") or "")
        if not fecha or fecha.year < anio:
            continue
        tit = (item.get("name_with_parent") or "").strip()
        desc_lista = clean_html(item.get("content") or "")
        cuerpo = desc_lista
        snippet = desc_lista[:220]
        try:
            snippet_p, cuerpo_p = leer_nota(url)
            if cuerpo_p:
                cuerpo = cuerpo_p
            if snippet_p:
                snippet = snippet_p
            time.sleep(PAUSA)
        except Exception as e:
            print(f"[AVISO] no se abrió {url}: {e}")
        nt, nd = norm(tit), norm(cuerpo)
        r = score(nt, nd, ancla, temas, excl)
        if r is None:
            continue
        s, cats, veto = r
        key = norm(url)
        if key in seen:
            continue
        seen.add(key)
        alert = ";".join(x for x in (veto, alerta_titulo(nt)) if x)
        rows.append({
            "fecha_pub": fecha.isoformat(),
            "fuente": "gob.pe/INEI",
            "titulo": tit,
            "snippet": _snip_con_ancla(cuerpo or snippet, ancla)[:220],
            "url": url,
            "query": "gob.pe:noticias-inei",
            "score": s,
            "temas": ";".join(cats),
            "alerta_ruido": alert,
        })
    rows.sort(key=lambda r: (r["fecha_pub"], r["score"]), reverse=True)
    return rows


def main():
    rows = recolectar()
    out = guardar_csv("gobpe", rows)
    print(f"OK {len(rows)} notas INEI con ENAPRES -> {out}")
    for r in rows:
        print(f"  [{r['score']}] {r['fecha_pub']} | {r['titulo'][:85]}")


if __name__ == "__main__":
    main()
