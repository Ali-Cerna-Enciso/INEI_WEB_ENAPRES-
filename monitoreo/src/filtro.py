"""Utilidades HTTP y filtro de menciones ENAPRES."""
import csv
import html as htmlmod
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

LIMA = ZoneInfo("America/Lima")

COLS = ["fecha_pub", "fuente", "titulo", "snippet", "url", "query", "score", "temas", "alerta_ruido"]
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TFILE = os.path.join(BASE, "keywords", "taxonomia.csv")
OUTDIR = os.path.join(BASE, "salidas")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "setiembre": 9, "septiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def sin_proxy():
    for v in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(v, None)
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def norm(s):
    s = (s or "").lower()
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def clean_html(s):
    s = htmlmod.unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_taxonomy():
    ancla, temas, excl = [], [], []
    with open(TFILE, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            t = norm(row["termino"])
            if row["nivel"] == "ancla":
                ancla.append(t)
            elif row["nivel"] == "exclusion":
                excl.append(t)
            else:
                temas.append((t, row["categoria"]))
    return ancla, temas, excl


def es_farmaco(n_title, n_desc):
    blob = f"{n_title} {n_desc}"
    if "comprimido" in blob or "enalapril" in blob or re.search(r"\d+\s*mg\b", blob):
        if "inei" not in blob and "encuesta" not in blob:
            return True
    return False


def score(n_title, n_desc, ancla, temas, excl):
    if es_farmaco(n_title, n_desc):
        return None
    if not any(a in n_title or a in n_desc for a in ancla):
        return None
    cats, s = set(), 1
    for t, c in temas:
        if t in n_title:
            s += 2
            cats.add(c)
        elif t in n_desc:
            s += 1
            cats.add(c)
    veto = [e for e in excl if e in n_title or e in n_desc]
    if veto and not cats:
        return None
    return s, sorted(cats), ";".join(veto)


def alerta_titulo(n_title):
    if "encuesta nacional de hogares" in n_title and "enapres" not in n_title:
        return "posible-ENAHO"
    if ("encuesta demografica" in n_title or "endes" in n_title) and "enapres" not in n_title:
        return "posible-ENDES"
    return ""


def parse_fecha(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(LIMA).date()
    except (TypeError, ValueError, OverflowError):
        pass
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            pass
    m = re.match(r"^(\d{8})(?:T|$)", s)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d").date()
        except ValueError:
            pass
    m = re.search(r"(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})", s, re.I)
    if m:
        mes = MESES.get(norm(m.group(2)))
        if mes:
            try:
                return date(int(m.group(3)), mes, int(m.group(1)))
            except ValueError:
                pass
    return None


def es_del_dia(fecha, dia_iso):
    try:
        return fecha == datetime.strptime(dia_iso, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return False


def gnews_rss_url(query, when=None):
    """RSS de Google News (PE). `when=1d` = últimas 24 h (como el filtro del buscador)."""
    q = query
    if when and "when:" not in query.lower():
        q = f"{query} when:{when}"
    return ("https://news.google.com/rss/search?q=" + urllib.parse.quote_plus(q)
            + "&hl=es-419&gl=PE&ceid=PE:es-419")


def parse_gnews_items(xml_bytes):
    root = ET.fromstring(xml_bytes)
    out = []
    for it in root.iter("item"):
        src = it.find("source")
        out.append({
            "titulo": (it.findtext("title") or "").strip(),
            "url": (it.findtext("link") or "").strip(),
            "fecha_pub": (it.findtext("pubDate") or "").strip(),
            "desc": clean_html(it.findtext("description")),
            "fuente": (src.text.strip() if src is not None and src.text else ""),
        })
    return out


def fetch_gnews_items(query, when="1y", retries=1):
    """RSS del último año (when:1y). Si viene vacío, reintenta sin recorte."""
    url = gnews_rss_url(query, when=when)
    ultimo = []
    for intento in range(retries + 1):
        if intento:
            time.sleep(4 * intento)
        ultimo = parse_gnews_items(request(url))
        if ultimo:
            return ultimo
    if when:
        amplio = parse_gnews_items(request(gnews_rss_url(query, when=None)))
        if amplio:
            print(f"[AVISO] when:{when} vacío; amplio {len(amplio)} (se filtra por fecha) ({query[:60]})")
            return amplio
    return ultimo


def request(url, timeout=30, headers=None):
    h = {"User-Agent": UA, "Accept-Language": "es-PE,es;q=0.9"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with sin_proxy().open(req, timeout=timeout) as r:
        return r.read()


HORIZONTE = None


def es_url_gnews(url):
    """True si es el redirect intermedio news.google.com/rss/articles/CBMi..."""
    return "news.google.com/rss/articles/" in (url or "")


def _cache_resueltos_path():
    return os.path.join(OUTDIR, "_resueltos.json")


def _cargar_resueltos():
    import json
    try:
        with open(_cache_resueltos_path(), encoding="utf-8") as fh:
            d = json.load(fh)
            return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _guardar_resueltos(mapa):
    import json
    try:
        os.makedirs(OUTDIR, exist_ok=True)
        tmp = _cache_resueltos_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(mapa, fh, ensure_ascii=False)
        os.replace(tmp, _cache_resueltos_path())
    except OSError:
        pass


def resolver_gnews(url, timeout=20, usar_cache=True):
    """Sigue el redirect CBMi -> URL final. Con caché en salidas/_resueltos.json.

    Si falla (429/login/timeout), devuelve la URL original sin romper.
    Solo stdlib.
    """
    if not es_url_gnews(url):
        return url
    if usar_cache:
        mapa = _cargar_resueltos()
        if url in mapa and mapa[url]:
            return mapa[url]
    else:
        mapa = {}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with sin_proxy().open(req, timeout=timeout) as r:
            final = r.geturl() or url
    except Exception:
        return url
    if final and final != url and usar_cache:
        try:
            mapa[url] = final
            if len(mapa) > 5000:
                mapa = dict(list(mapa.items())[-5000:])
            _guardar_resueltos(mapa)
        except Exception:
            pass
    return final if final else url


UA_FB = "facebookexternalhit/1.1"


def _fb_cache_path():
    return os.path.join(OUTDIR, "_fb.json")


def _cargar_fb():
    import json
    try:
        with open(_fb_cache_path(), encoding="utf-8") as fh:
            d = json.load(fh)
            return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _og(html, prop):
    m = re.search(r'<meta[^>]+property=["\']og:' + prop +
                  r'["\'][^>]+content=["\'](.*?)["\']', html, re.S)
    if not m:
        m = re.search(r'<meta[^>]+content=["\'](.*?)["\'][^>]+property=["\']og:' +
                      prop + r'["\']', html, re.S)
    return htmlmod.unescape(m.group(1)).strip()[:2000] if m else ""


def resolver_facebook(url, timeout=25, usar_cache=True):
    """Resuelve share/pfbid -> (canonica, og:title, og:description) sin login.

    Verificado 2026-09-15: con UA facebookexternalhit FB responde 200 con los
    og:tags del post publico (titulo = pagina, descripcion = texto del post).
    Con UA de navegador devuelve 400. Solo stdlib; cache en salidas/_fb.json.
    Si falla, devuelve (url, "", "") sin romper.
    """
    import json
    if "facebook.com" not in (url or ""):
        return url, "", ""
    mapa = _cargar_fb() if usar_cache else {}
    if url in mapa and isinstance(mapa[url], dict):
        m = mapa[url]
        return m.get("u") or url, m.get("t", ""), m.get("d", "")
    final, titulo, desc = url, "", ""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA_FB, "Accept-Language": "es-PE,es;q=0.9",
            "Accept": "text/html,application/xhtml+xml"})
        with sin_proxy().open(req, timeout=timeout) as r:
            final = r.geturl() or url
            html = r.read(1_000_000).decode("utf-8", "replace")
        titulo = _og(html, "title")
        desc = _og(html, "description")
    except Exception:
        return url, "", ""
    if usar_cache:
        try:
            mapa[url] = {"u": final, "t": titulo, "d": desc}
            if len(mapa) > 2000:
                mapa = dict(list(mapa.items())[-2000:])
            tmp = _fb_cache_path() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(mapa, fh, ensure_ascii=False)
            os.replace(tmp, _fb_cache_path())
        except (OSError, ValueError):
            pass
    return final, titulo, desc


def es_fresco(fecha_raw, horizonte=HORIZONTE):
    """True si la nota es de este año (Lima) y no futura.

    Si `horizonte` es un int, recorta a esos días. None = 1-ene del año en curso.
    """
    f = parse_fecha(fecha_raw)
    if not f:
        return False
    hoy = date.today()
    if f > hoy:
        return False
    if horizonte is None:
        return f.year == hoy.year
    return (hoy - f).days <= horizonte


def clave_dedup(titulo, fuente="", url=""):
    """Clave anti-CBMi: título normalizado + fuente; fallback URL normalizada.

    Replica corpus.titulo_clave para que salidas/*.csv y datos/live/* dedupen igual:
    mismo post con distinto CBMi...?oc=5 colapsa en una sola clave.
    """
    t = re.sub(r"\s*[-–|]\s*(x\.com|instagram\.com|facebook\.com|tiktok|youtube)\s*$",
               "", titulo or "", flags=re.I)
    clave = f"{norm(t)[:110]}|{norm(fuente)}".strip("|")
    return clave or norm(url)


def guardar_csv(prefix, rows, outdir=None):
    dest = outdir or OUTDIR
    os.makedirs(dest, exist_ok=True)
    out = os.path.join(dest, f"{prefix}_{datetime.now():%Y%m%d}.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    return out
