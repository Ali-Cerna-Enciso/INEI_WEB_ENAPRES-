"""Colectores de noticias temáticas (GDELT, Google News, RSS, Bing)."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
from calendar import monthrange
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from filtro import (BASE, clave_dedup, fetch_gnews_items,
                    parse_gnews_items, request)
from noticias_clasificar import clasificar
from feed_poll import parse_feed

PAUSA = 1.5
PAUSA_GDELT = 0.4
QFILE = {
    "inseguridad": os.path.join(BASE, "queries", "inseguridad.txt"),
    "servicios": os.path.join(BASE, "queries", "servicios.txt"),
}
FFEEDS = os.path.join(BASE, "fuentes", "feeds.txt")

GDELT_Q = {
    "inseguridad": (
        '(extorsion OR "gota a gota" OR "cobro de cupo") sourcecountry:PE sourcelang:spanish',
        '(estafa OR phishing OR "fraude bancario") sourcecountry:PE sourcelang:spanish',
        '(sicariato OR sicario OR masacre OR feminicidio) sourcecountry:PE sourcelang:spanish',
        '(homicidio OR asesinato) sourcecountry:PE sourcelang:spanish',
        '(secuestro OR "secuestro al paso" OR "Los Pulpos") sourcecountry:PE sourcelang:spanish',
        '("mano armada" OR "robo al paso" OR "robo de celular") sourcecountry:PE sourcelang:spanish',
        '("robo de vehiculo" OR "robo de moto" OR "robo en vivienda") sourcecountry:PE sourcelang:spanish',
        '("crimen organizado" OR "banda criminal") sourcecountry:PE sourcelang:spanish',
    ),
    "servicios": (
        '("corte de agua" OR Sedapal OR Sedalib OR "sin agua") sourcecountry:PE sourcelang:spanish',
        '("corte de luz" OR apagon OR Hidrandina OR "corte electrico") sourcecountry:PE sourcelang:spanish',
        '(desague OR alcantarillado OR aniego) sourcecountry:PE sourcelang:spanish',
        '("agua potable" OR "recoleccion de basura" OR "relleno sanitario") sourcecountry:PE sourcelang:spanish',
    ),
}


def load_queries(area: str) -> list[str]:
    qs = []
    with open(QFILE[area], encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            qs.append(line)
    return qs


def load_feeds():
    feeds = []
    with open(FFEEDS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            nombre, url = line.split("|", 1)
            feeds.append((nombre.strip(), url.strip()))
    return feeds


def _filas(area: str, items: list[dict], colector: str, query: str,
           seen: set, resolver=False) -> list[dict]:
    from filtro import resolver_gnews
    rows = []
    for it in items:
        url = it.get("url") or ""
        if resolver:
            try:
                url = resolver_gnews(url)
            except Exception:
                pass
        key = clave_dedup(it.get("titulo", ""), it.get("fuente", ""), url)
        if not url or key in seen:
            continue
        r = clasificar(area, it.get("titulo", ""),
                       it.get("desc") or it.get("snippet") or "", url)
        if r is None:
            continue
        seen.add(key)
        s, cats = r
        rows.append({
            "fecha_pub": it.get("fecha_pub") or "",
            "fuente": it.get("fuente") or colector,
            "titulo": (it.get("titulo") or "").strip(),
            "snippet": (it.get("desc") or it.get("snippet") or "")[:220],
            "url": url,
            "query": query,
            "score": s,
            "temas": ";".join(cats),
            "alerta_ruido": "",
            "colector": colector,
        })
    return rows


def _gdelt_url(query: str, start: date, end: date, maxrec: int = 250) -> str:
    q = urllib.parse.quote_plus(query)
    ini = start.strftime("%Y%m%d000000")
    fin = end.strftime("%Y%m%d235959")
    return (f"https://api.gdeltproject.org/api/v2/doc/doc?query={q}&mode=artlist"
            f"&maxrecords={maxrec}&format=json&startdatetime={ini}"
            f"&enddatetime={fin}&sort=datedesc")


def fetch_gdelt_rango(query: str, start: date, end: date) -> list[dict]:
    """Parte el rango si GDELT satura los 250 registros."""
    out = []
    pendientes = [(start, end)]
    while pendientes:
        a, b = pendientes.pop(0)
        url = _gdelt_url(query, a, b)
        data = None
        for intento in range(4):
            try:
                raw = request(url, timeout=40)
                data = json.loads(raw.decode("utf-8", "replace"))
                break
            except Exception as e:
                if "429" in str(e):
                    espera = 25 * (intento + 1)
                    print(f"[AVISO] gdelt 429: espera {espera} s", flush=True)
                    time.sleep(espera)
                    continue
                print(f"[AVISO] gdelt: {e}", flush=True)
                data = None
                break
        arts = (data or {}).get("articles") or []
        if len(arts) >= 250 and a < b and (b - a).days >= 2:
            mid = a + timedelta(days=(b - a).days // 2)
            pendientes.append((a, mid))
            pendientes.append((mid + timedelta(days=1), b))
            time.sleep(5)
            continue
        for art in arts:
            out.append({
                "titulo": art.get("title") or "",
                "url": art.get("url") or "",
                "fecha_pub": art.get("seendate") or "",
                "desc": "",
                "fuente": art.get("domain") or "gdelt",
            })
        time.sleep(5)
    return out


def meses_entre(inicio: date, fin: date) -> list[tuple[date, date]]:
    out = []
    y, m = inicio.year, inicio.month
    while date(y, m, 1) <= fin:
        last = monthrange(y, m)[1]
        a = max(inicio, date(y, m, 1))
        b = min(fin, date(y, m, last))
        if a <= b:
            out.append((a, b))
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return out


def recolectar_gdelt(area: str, inicio: date, fin: date, seen: set | None = None) -> list[dict]:
    seen = seen if seen is not None else set()
    rows = []
    for q in GDELT_Q[area]:
        for a, b in meses_entre(inicio, fin):
            try:
                items = fetch_gdelt_rango(q, a, b)
            except Exception as e:
                print(f"[AVISO] gdelt {area} {a} {e}")
                continue
            rows.extend(_filas(area, items, "gdelt", f"gdelt:{q[:40]}", seen))
    print(f"[RESUMEN gdelt {area}] {inicio}..{fin} final={len(rows)}")
    return rows


def recolectar_gnews(area: str, inicio: date, fin: date, seen: set | None = None,
                     resolver=False) -> list[dict]:
    seen = seen if seen is not None else set()
    rows = []
    queries = load_queries(area)
    tramos = meses_entre(inicio, fin)
    # Incremental corto: un solo tramo. Backfill: un tramo por mes (Google no da el año entero).
    if (fin - inicio).days <= 10:
        tramos = [(inicio, fin)]
    for i, q in enumerate(queries):
        for a, b in tramos:
            extra = f" after:{a.isoformat()} before:{(b + timedelta(days=1)).isoformat()}"
            if i or a != tramos[0][0]:
                time.sleep(PAUSA)
            try:
                items = fetch_gnews_items(q + extra, when=None)
            except Exception as e:
                print(f"[AVISO] gnews ({q}): {e}")
                continue
            rows.extend(_filas(area, items, "gnews", q, seen, resolver=resolver))
    print(f"[RESUMEN gnews {area}] {inicio}..{fin} final={len(rows)}")
    return rows


def recolectar_feeds(area: str, seen: set | None = None) -> list[dict]:
    seen = seen if seen is not None else set()
    rows = []
    for nombre, url in load_feeds():
        try:
            items = parse_feed(request(url))
        except Exception as e:
            print(f"[AVISO] feed ({nombre}): {e}")
            continue
        for it in items:
            it["fuente"] = nombre
        rows.extend(_filas(area, items, "feeds", f"feed:{nombre}", seen))
    print(f"[RESUMEN feeds {area}] final={len(rows)}")
    return rows


def recolectar_bing(area: str, seen: set | None = None) -> list[dict]:
    seen = seen if seen is not None else set()
    rows = []
    for i, q in enumerate(load_queries(area)):
        if i:
            time.sleep(PAUSA)
        url = ("https://www.bing.com/news/search?q="
               + urllib.parse.quote_plus(q) + "&format=rss")
        try:
            items = parse_gnews_items(request(url, timeout=20))
        except Exception as e:
            print(f"[AVISO] bing ({q}): {e}")
            continue
        rows.extend(_filas(area, items, "bing", f"bing:{q}", seen))
    print(f"[RESUMEN bing {area}] final={len(rows)}")
    return rows


def recolectar_area(area: str, inicio: date, fin: date, incluir_feeds=True,
                    resolver_gnews=False) -> dict[str, list]:
    seen: set = set()
    por = {
        "gdelt": recolectar_gdelt(area, inicio, fin, seen),
        "gnews": recolectar_gnews(area, inicio, fin, seen, resolver=resolver_gnews),
        "bing": recolectar_bing(area, seen),
    }
    if incluir_feeds:
        por["feeds"] = recolectar_feeds(area, seen)
    return por
