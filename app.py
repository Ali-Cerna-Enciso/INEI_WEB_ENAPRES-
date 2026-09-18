"""Catálogo ENAPRES y menciones en prensa."""
from __future__ import annotations

import base64
import html
import hmac
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

DIR = Path(__file__).resolve().parent
ROOT = DIR.parent if (DIR.parent / "monitoreo").exists() else DIR
CATALOGO = DIR / "catalogo" / "index.html"
SRC = ROOT / "monitoreo" / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    import actualizar  # noqa: E402
    import corpus  # noqa: E402
    import a_catalogo  # noqa: E402
    import exportar_snapshot  # noqa: E402
except ImportError:
    actualizar = corpus = a_catalogo = exportar_snapshot = None  # noqa: E402
    SIN_MONITOREO = True
else:
    SIN_MONITOREO = False

try:
    import noticias_actualizar  # noqa: E402
    import noticias_corpus  # noqa: E402
    import exportar_noticias  # noqa: E402
except ImportError:
    noticias_actualizar = noticias_corpus = exportar_noticias = None  # noqa: E402

MARCAS = ("<!--ACTUALIZADO-->", "<!--/ACTUALIZADO-->")
MESES = "ene feb mar abr may jun jul ago set oct nov dic".split()
NOMBRE_COLECTOR = {
    "oficial": "Difusión OTD",
    "gobpe": "gob.pe / INEI",
    "medios": "Prensa y redes",
    "gnews": "Google News",
    "feeds": "Feeds RSS",
    "youtube": "YouTube",
    "gdelt": "GDELT",
    "bing": "Bing News",
    "legacy": "Corrida anterior",
    "monitoreo": "Google News",
    "yt": "YouTube",
    "noticias-inseguridad": "Noticias inseguridad",
    "noticias-servicios": "Noticias servicios",
}


def _en_nube() -> bool:
    return Path("/mount/src").is_dir() or str(DIR).startswith("/mount/src")


def _secreto(nombre: str, default: str = "") -> str:
    try:
        v = st.secrets.get(nombre, default)
    except Exception:
        v = default
    return str(v or os.environ.get(nombre, default) or default)


def _puede_rastrear_aqui() -> bool:
    return (not SIN_MONITOREO) and os.name == "nt" and not _en_nube()


def _lanzar_gha() -> tuple[bool, str]:
    token = _secreto("GH_TOKEN")
    repo = _secreto("GH_REPO", "Ali-Cerna-Enciso/INEI_WEB_ENAPRES-")
    wf = _secreto("GH_WORKFLOW", "monitoreo.yml")
    if not token:
        return False, "Falta GH_TOKEN en secretos de Streamlit."
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{wf}/dispatches"
    body = json.dumps({"ref": "main"}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "enapres-webapp",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            if r.status in (204, 200):
                return True, "Pedido enviado. En 1–3 minutos GitHub Actions actualiza y Streamlit redespliega."
            return False, f"GitHub respondió {r.status}"
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "replace")[:240]
        return False, f"GitHub {e.code}: {detalle or e.reason}"
    except urllib.error.URLError as e:
        return False, str(e.reason or e)


_REDES_HOSTS = (
    "facebook.com", "fb.com", "instagram.com", "x.com", "twitter.com",
    "tiktok.com", "youtube.com", "youtu.be", "t.me", "telegram.me",
    "whatsapp.com", "threads.net",
)
TIPO_NOTICIAS = "Noticias/reportes"
TIPO_REDES = "Redes sociales"
TIPOS_FUENTE = [TIPO_NOTICIAS, TIPO_REDES]


def _tipo_fuente(it: dict) -> str:
    if it.get("tipo_fuente") in TIPOS_FUENTE:
        return it["tipo_fuente"]
    blob = f"{it.get('fuente') or ''} {it.get('url') or ''}".lower()
    if any(h in blob for h in _REDES_HOSTS):
        return TIPO_REDES
    return TIPO_NOTICIAS


def dia_humano(iso: str) -> str:
    try:
        y, m, d = iso.split("-")
        return f"{int(d)} {MESES[int(m) - 1]} {y}"
    except (ValueError, IndexError):
        return iso


def fecha_catalogo() -> str:
    for p in (
        DIR / "datos_publicos" / "menciones.json",
        ROOT / "datos" / "indice.json",
        DIR / "datos" / "indice.json",
    ):
        try:
            act = json.loads(p.read_text(encoding="utf-8")).get("actualizado")
            if act:
                return str(act)
        except (OSError, ValueError):
            pass
    try:
        texto = CATALOGO.read_text(encoding="utf-8")
        return texto.split(MARCAS[0], 1)[1].split(MARCAS[1], 1)[0].strip()
    except (OSError, IndexError):
        return "sin fecha"


@st.cache_data(ttl=600, show_spinner=False)
def fecha_catalogo_humana(mt_men: float = 0.0, mt_ind: float = 0.0, mt_cat: float = 0.0) -> str:
    raw = fecha_catalogo()
    try:
        dt = datetime.strptime(raw[:16], "%Y-%m-%d %H:%M")
        return f"{dt.day} {MESES[dt.month - 1]} {dt.year} · {dt.strftime('%H:%M')}"
    except (ValueError, IndexError):
        return raw


def _cargar_libros() -> dict:
    try:
        d = json.loads((DIR / "catalogo" / "libros.json").read_text(encoding="utf-8"))
        if isinstance(d, dict) and d.get("libros"):
            return d
    except (OSError, ValueError):
        pass
    return {}


def _embeber_js(h: str, ini: str, fin: str, cuerpo: str) -> str:
    return re.sub(
        re.escape(ini) + r".*?" + re.escape(fin),
        ini + "\n" + cuerpo + "\n" + fin,
        h, count=1, flags=re.S,
    )


def _portadas_en_iframe(h: str, carpeta: Path) -> str:
    img = carpeta / "img"
    if not img.is_dir():
        return h
    for p in sorted(img.glob("*.png"), key=lambda x: -len(x.name)):
        uri = "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode("ascii")
        h = h.replace("img/" + p.name, uri)
    return h


@st.cache_data(ttl=600, show_spinner=False)
def _html_catalogo(mt: float = 0.0) -> str:
    h = CATALOGO.read_text(encoding="utf-8")
    carpeta = DIR / "catalogo"

    def carga(nombre):
        try:
            return json.loads((carpeta / nombre).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    data = carga("data.json")
    libros = carga("libros.json")
    if isinstance(data, list):
        h = _embeber_js(
            h, "//<!--DATOS-INI-->", "//<!--DATOS-FIN-->",
            "const DATA=" + json.dumps(data, ensure_ascii=False) + ";",
        )
    if isinstance(libros, dict) and libros.get("libros"):
        h = _embeber_js(
            h, "//<!--LIBROS-INI-->", "//<!--LIBROS-FIN-->",
            "var LIBROS=" + json.dumps(libros, ensure_ascii=False) + ";",
        )
    act = fecha_catalogo()
    if act and act != "sin fecha":
        h = re.sub(
            r"<!--ACTUALIZADO-->.*?<!--/ACTUALIZADO-->",
            "<!--ACTUALIZADO-->" + str(act) + "<!--/ACTUALIZADO-->",
            h, count=1, flags=re.S,
        )
    return _portadas_en_iframe(h, carpeta)


st.set_page_config(
    page_title="ENAPRES — catálogo, menciones y noticias",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      header[data-testid="stHeader"] {display: none}
      .block-container {padding: 12px 18px 28px !important; max-width: 1100px}
      footer, [data-testid="stStatusWidget"] {display: none}
      #MainMenu {visibility: hidden}
      [data-testid="stToolbar"] {visibility: hidden}
      [data-testid="stDecoration"] {visibility: hidden}
      .stAppDeployButton {display: none}
      [data-testid="manage-app-button"] {display: none}
      .en-card {background:#fff;border-radius:12px;padding:14px 16px;margin:8px 0;
        box-shadow:0 1px 3px rgba(0,0,0,.12)}
      .en-card h4 {margin:0 0 6px;font-size:16px;line-height:1.35}
      .en-meta {font-size:12px;color:#555;margin-bottom:6px}
      .en-snip {font-size:14px;color:#333;margin:0 0 8px}
      .en-badge {display:inline-block;font-size:11px;font-weight:700;border-radius:6px;
        padding:2px 8px;margin-right:6px;color:#fff}
      .b-nuevo {background:#0e7c4b}
      .b-fresco {background:#145da0}
      .b-hist {background:#6b7280}
      .b-alerta {background:#b45309}
      .stTabs [role="tablist"] {gap:14px}
      .stTabs [role="tab"] {padding:14px 20px !important}
      .stTabs [role="tab"] p {font-size:19px !important; font-weight:700}
      .en-mes-label {font-size:17px !important; font-weight:800 !important;
        color:#0b3d91 !important; margin: 0 0 4px !important}
      div[data-testid="stSelectbox"] label p {font-size:15px !important; font-weight:700}
      div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
        min-height: 48px; border: 2px solid #1d4ed8 !important;
        background: #fff !important; box-shadow: 0 1px 4px rgba(29,78,216,.18)
      }
      [data-testid="stExpander"] details {border: 2px solid #1d4ed8 !important;
        background: #e8f1fb !important; border-radius: 12px}
    </style>
    """,
    unsafe_allow_html=True,
)

def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _catalogo_mtime() -> float:
    cands = [CATALOGO, DIR / "catalogo" / "data.json", DIR / "catalogo" / "libros.json"]
    try:
        cands += sorted((DIR / "catalogo" / "img").glob("*.png"))
    except OSError:
        pass
    return max([_mtime(p) for p in cands] or [0.0])


@st.cache_data(ttl=600, show_spinner=False)
def _cargar_snapshot(mt: float = 0.0):
    try:
        snap = json.loads((DIR / "datos_publicos" / "menciones.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, []
    items = list(snap.get("items") or [])
    items.sort(key=lambda r: (r.get("fecha_pub") or "", -int(r.get("score") or 0)), reverse=True)
    return snap, items


def _filtrar_snapshot(items, ventana):
    hoy = date.today()
    if ventana == "Hoy":
        corte, col = hoy.isoformat(), None
    elif ventana == "Semana":
        corte, col = (hoy - timedelta(days=6)).isoformat(), None
    elif ventana == "Mes":
        corte, col = (hoy - timedelta(days=29)).isoformat(), None
    elif ventana == "Difusión OTD 2026":
        corte, col = "2026-01-01", "oficial"
    else:
        corte, col = "2026-01-01", None
    return [it for it in items
            if (it.get("fecha_pub") or "")[:10] >= corte
            and (col is None or it.get("colector") == col)]


@st.cache_data(ttl=600, show_spinner=False)
def _cargar_noticias_snap(area: str, mt: float = 0.0) -> tuple[dict, list]:
    try:
        snap = json.loads(
            (DIR / "datos_publicos" / f"noticias_{area}.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return {}, []
    items = list(snap.get("items") or [])
    items.sort(key=lambda r: (r.get("fecha_pub") or "", r.get("titulo") or ""), reverse=True)
    return snap, items


def _filtrar_noticias(items, ventana, mes=""):
    hoy = date.today()
    out = []
    for it in items:
        if it.get("descartar"):
            continue
        f = (it.get("fecha_pub") or "")[:10]
        if mes:
            if f[:7] == mes:
                out.append(it)
            continue
        if ventana == "Hoy":
            corte = hoy.isoformat()
        elif ventana == "Semana":
            corte = (hoy - timedelta(days=6)).isoformat()
        elif ventana == "Mes":
            corte = (hoy - timedelta(days=29)).isoformat()
        else:
            corte = "2026-01-01"
        if f >= corte:
            out.append(it)
    return out


@st.cache_data(ttl=600, show_spinner=False)
def _corpus_noticias(area: str, ventana: str, mes: str, hoy: str) -> list:
    if mes:
        return noticias_corpus.load_area(area, desde=f"{mes}-01", hasta=f"{mes}-31")
    if ventana == "Hoy":
        return noticias_corpus.load_area(area, desde=hoy)
    if ventana == "Semana":
        return noticias_corpus.load_area(area, desde=str(date.fromisoformat(hoy) - timedelta(days=6)))
    if ventana == "Mes":
        return noticias_corpus.load_area(area, desde=str(date.fromisoformat(hoy) - timedelta(days=29)))
    return noticias_corpus.load_area(area, desde="2026-01-01")


    if (not SIN_MONITOREO) and noticias_corpus is not None:
        return _corpus_noticias(area, ventana, mes, date.today().isoformat())
    _, items = _cargar_noticias_snap(area, _mtime(DIR / "datos_publicos" / f"noticias_{area}.json"))
    return _filtrar_noticias(items, ventana, mes)


def _barra_actualizar(clave: str) -> bool:
    """Botón de corrida. En la nube dispara GitHub Actions; en PC corre aquí."""
    local_click = False
    admin = _secreto("ADMIN_TOKEN")
    if _en_nube() and admin and _secreto("GH_TOKEN"):
        pin = st.text_input("Clave", type="password", key=f"pin_{clave}",
                            label_visibility="collapsed", placeholder="Clave")
        if st.button("Actualizar ahora", type="primary",
                     use_container_width=True, key=f"btn_{clave}"):
            if not pin or not hmac.compare_digest(pin, admin):
                st.error("Clave incorrecta.")
            else:
                ok, msg = _lanzar_gha()
                (st.success if ok else st.error)(msg)
    elif _puede_rastrear_aqui():
        local_click = st.button("Actualizar hoy", type="primary",
                                use_container_width=True, key=f"btn_{clave}")
    else:
        st.caption("Auto: 07:17, 16:17 y 23:50 Lima")
    st.caption(f"Última actualización: {fecha_catalogo_humana(_mtime(DIR / 'datos_publicos' / 'menciones.json'), _mtime(ROOT / 'datos' / 'indice.json'), _mtime(DIR / 'datos' / 'indice.json'))} (hora Lima)")
    return local_click


def _correr_rastreo():
    bitacora = []
    caja = st.empty()

    def on_paso(nombre, estado, **kw):
        etiqueta = NOMBRE_COLECTOR.get(nombre, nombre)
        if estado == "inicio":
            bitacora.append(f"⏳ {etiqueta}…")
        elif estado == "ok":
            bitacora[-1] = f"✓ {etiqueta}: {kw.get('n', 0)} hallazgos"
        else:
            bitacora[-1] = f"⚠ {etiqueta}: {kw.get('error', 'error')}"
        caja.markdown("\n\n".join(bitacora))

    with st.spinner("Rastreando menciones y noticias 2026 (puede tardar)…"):
        try:
            actualizar.correr(on_paso=on_paso)
        except Exception as e:
            st.error(f"La actualización falló: {e}")
            return
        try:
            if exportar_snapshot:
                exportar_snapshot.main()
            bitacora.append("✓ Instantánea de menciones")
        except Exception as e:
            bitacora.append(f"⚠ Instantánea menciones: {e}")
        try:
            if exportar_noticias:
                exportar_noticias.main()
            bitacora.append("✓ Instantánea de noticias")
        except Exception as e:
            bitacora.append(f"⚠ Instantánea noticias: {e}")
        caja.markdown("\n\n".join(bitacora))
        st.success("Corpus actualizado. Lo ya guardado no se borra; solo entra lo nuevo.")
        st.rerun()


_POR_PAGINA = 30


def _html_tarjeta(it: dict) -> str:
    badges = []
    if it.get("fecha_pub"):
        badges.append(f'<span class="en-badge b-fresco">{html.escape(it["fecha_pub"])}</span>')
    for t in (it.get("temas") or [])[:3]:
        badges.append(f'<span class="en-badge b-nuevo">{html.escape(str(t))}</span>')
    ubi = ", ".join(it.get("ubigeo") or [])
    temas = ", ".join(it.get("temas") or []) or "sin clasificar"
    titulo = html.escape(it.get("titulo") or "")
    snip = html.escape(it.get("snippet") or "")
    fuente = html.escape(it.get("fuente") or "?")
    url = html.escape(it.get("url") or "#", quote=True)
    via = html.escape(NOMBRE_COLECTOR.get(it.get("colector") or "", it.get("colector") or ""))
    canal = html.escape(_tipo_fuente(it))
    meta = f"{''.join(badges)} {canal} · {fuente} · {temas} · {via}"
    if ubi:
        meta += f" · {html.escape(ubi)}"
    return (
        f"<div class='en-card'><h4>{titulo}</h4>"
        f"<div class='en-meta'>{meta}</div>"
        + (f"<p class='en-snip'>{snip}</p>" if snip else "")
        + f"<a href='{url}' target='_blank' rel='noopener'>Abrir ↗</a></div>"
    )


def _tarjeta_noticia(it: dict, extra_meta: str = "") -> None:
    if extra_meta:
        it = dict(it)
        ubi = ", ".join(it.get("ubigeo") or [])
        it["ubigeo"] = (ubi + ", " + extra_meta) if ubi else extra_meta
    st.markdown(_html_tarjeta(it), unsafe_allow_html=True)


@st.fragment
def _panel_noticias(area: str, titulo: str, caption: str, clave: str) -> bool:
    top1, top2 = st.columns([3, 1])
    with top1:
        st.markdown(f"### {titulo}")
        st.caption(caption)
    with top2:
        click = _barra_actualizar(clave)
    meses = []
    if (not SIN_MONITOREO) and noticias_corpus is not None:
        meses = noticias_corpus.meses_guardados(area)
    else:
        _, crudos = _cargar_noticias_snap(area, _mtime(DIR / "datos_publicos" / f"noticias_{area}.json"))
        meses = sorted({(it.get("fecha_pub") or "")[:7] for it in crudos if it.get("fecha_pub")})
    ventana = st.radio(
        "Periodo (fecha de publicación)",
        ["Hoy", "Semana", "Mes", "Año 2026"],
        index=3,
        horizontal=True,
        key=f"per_{clave}",
        help="Hoy/semana/mes recortan por fecha de publicación. "
             "Año 2026 lee el JSON acumulado. Un día sin botón no se pierde: "
             "la corrida de las 23:50 o la siguiente mira al menos 7 días atrás. "
             "Si eliges un mes archivado, ese mes manda sobre el periodo.",
    )
    mes_sel = ""
    if meses:
        st.markdown(
            '<p class="en-mes-label">Mes archivado — elige el mes del archivo 2026</p>',
            unsafe_allow_html=True,
        )
        try:
            caja_mes = st.container(border=True)
        except TypeError:
            caja_mes = st.container()
        with caja_mes:
            mes_sel = st.selectbox(
                "Mes archivado",
                ["Todos"] + meses,
                format_func=lambda m: (
                    "Todos los meses (usa el periodo de arriba)" if m == "Todos"
                    else f"{m}  ·  {MESES[int(m[5:7]) - 1].upper()} 2026"
                ),
                key=f"mes_{clave}",
                help="Mes calendario guardado en el JSON. Es independiente "
                     "del recorte Hoy/Semana/Mes (últimos 30 días).",
            )
        if mes_sel == "Todos":
            mes_sel = ""
        else:
            st.info(f"Viendo el mes calendario **{mes_sel}**. "
                    "El periodo Hoy/Semana/Mes no se aplica.")
    items = _items_noticias(area, ventana, mes_sel)
    c1, c2, c3 = st.columns(3)
    c1.metric("Noticias", len(items))
    c2.metric("Días con hallazgo",
              len({(i.get("fecha_pub") or "")[:10] for i in items if i.get("fecha_pub")}))
    c3.metric("Sin clasificar",
              sum(1 for i in items if not (i.get("temas") or [])))
    q = st.text_input("Buscar", placeholder="extorsión, Sedapal, Comas…",
                      key=f"q_{clave}").strip().lower()
    temas_disp = sorted({t for i in items for t in (i.get("temas") or [])})
    f1, f2 = st.columns(2)
    with f1:
        f_sel = st.selectbox(
            "Fuente",
            ["Todas", TIPO_NOTICIAS, TIPO_REDES],
            key=f"fu_{clave}",
            help="Solo dos grupos: medios/reportes vs redes sociales. "
                 "El diario concreto sigue en cada tarjeta.",
        )
    with f2:
        t_sel = st.selectbox(
            "Tema",
            ["Todos"] + temas_disp,
            key=f"te_{clave}",
            help="Delitos consumados ENAPRES (P424) o servicios básicos. "
                 "Sin intentos ni percepción de inseguridad.",
        )
    firma = (ventana, mes_sel, f_sel, t_sel, q)
    if st.session_state.get(f"firma_{clave}") != firma:
        st.session_state[f"firma_{clave}"] = firma
        st.session_state[f"pag_{clave}"] = 1
    filtradas = []
    for it in items:
        if f_sel != "Todas" and _tipo_fuente(it) != f_sel:
            continue
        if t_sel != "Todos" and t_sel not in (it.get("temas") or []):
            continue
        if q:
            blob = " ".join([
                it.get("titulo") or "", it.get("snippet") or "",
                it.get("fuente") or "", " ".join(it.get("temas") or []),
                " ".join(it.get("ubigeo") or []), _tipo_fuente(it),
            ]).lower()
            if q not in blob:
                continue
        filtradas.append(it)
    n = len(filtradas)
    if not items:
        st.info(f"Sin noticias en «{mes_sel or ventana}». "
                "La primera corrida llena 2026; las siguientes solo agregan.")
        return click
    paginas = max(1, (n + _POR_PAGINA - 1) // _POR_PAGINA)
    pag = st.session_state.get(f"pag_{clave}", 1)
    try:
        pag = int(pag)
    except (TypeError, ValueError):
        pag = 1
    pag = min(max(1, pag), paginas)
    st.session_state[f"pag_{clave}"] = pag
    if paginas > 1:
        p1, p2, p3 = st.columns([1, 2, 1])
        with p1:
            if st.button("◀ Anteriores", key=f"prev_{clave}", disabled=pag <= 1,
                         use_container_width=True):
                st.session_state[f"pag_{clave}"] = pag - 1
        with p2:
            st.caption(f"Página {pag} de {paginas} · {n} noticias")
        with p3:
            if st.button("Siguientes ▶", key=f"next_{clave}", disabled=pag >= paginas,
                         use_container_width=True):
                st.session_state[f"pag_{clave}"] = pag + 1
    st.markdown(
        "".join(_html_tarjeta(it) for it in filtradas[(pag - 1) * _POR_PAGINA:pag * _POR_PAGINA]),
        unsafe_allow_html=True,
    )
    st.caption(f"{min(n, pag * _POR_PAGINA)} de {n} ({mes_sel or ventana}).")
    if click:
        _correr_rastreo()
        return False
    return click


_SNAP_ITEMS: list = []
if SIN_MONITOREO:
    _snap, _SNAP_ITEMS = _cargar_snapshot(_mtime(DIR / "datos_publicos" / "menciones.json"))
    indice = {"actualizado": _snap.get("actualizado") or "—", "dias": [],
              "max_live": _snap.get("max_live", 31)}
else:
    corpus.migrar_diario_viejo()
    indice = corpus.load_indice()

if SIN_MONITOREO or _en_nube():
    tab_cat, tab_mon, tab_ins, tab_ser = st.tabs(
        ["Catálogo", "Menciones", "Noticias inseguridad", "Noticias servicios básicos"]
    )
    tab_cargar = None
else:
    tab_cat, tab_mon, tab_ins, tab_ser, tab_cargar = st.tabs(
        ["Catálogo", "Menciones", "Noticias inseguridad", "Noticias servicios básicos", "Cargar"]
    )

with tab_cat:
    if not CATALOGO.exists():
        st.error(f"No se encontró el catálogo: {CATALOGO}")
    else:
        components.html(_html_catalogo(_catalogo_mtime()), height=2200, scrolling=True)

with tab_mon:
    top1, top2 = st.columns([3, 1])
    with top1:
        st.markdown("### Menciones de ENAPRES")
        st.caption(
            "Notas de gob.pe/INEI, prensa y redes que nombran la encuesta."
        )
    with top2:
        actualizar_click = _barra_actualizar("menciones")

    if actualizar_click:
        _correr_rastreo()

    st.caption(
        f"Última escritura: {fecha_catalogo_humana(_mtime(DIR / 'datos_publicos' / 'menciones.json'), _mtime(ROOT / 'datos' / 'indice.json'), _mtime(DIR / 'datos' / 'indice.json'))} (hora Lima) · "
        f"{len(indice.get('dias') or [])}/{indice.get('max_live', 31)} días en vivo"
    )
    ventana = st.radio(
        "Periodo",
        ["Hoy", "Semana", "Mes", "Año 2026", "Difusión OTD 2026"],
        index=3,
        horizontal=True,
        help="Hoy, semana y mes recortan por fecha de publicación. "
             "Año 2026 cubre el año calendario. "
             "OTD 2026 corresponde a la difusión en Facebook institucional.",
    )
    if SIN_MONITOREO:
        items = _filtrar_snapshot(_SNAP_ITEMS, ventana)
    elif ventana == "Hoy":
        items = corpus.load_rango(dias=1)
    elif ventana == "Semana":
        items = corpus.load_rango(dias=7)
    elif ventana == "Mes":
        items = corpus.load_rango(dias=30)
    elif ventana == "Año 2026":
        items = corpus.load_rango(desde="2026-01-01")
    else:
        items = [i for i in corpus.load_rango(desde="2026-01-01")
                 if i.get("colector") == "oficial"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Menciones", len(items))
    c2.metric("Días con hallazgo", len({i.get("fecha_pub") for i in items if i.get("fecha_pub")}))
    c3.metric("Difusión OTD", sum(1 for i in items if i.get("colector") == "oficial"))

    q = st.text_input("Buscar", placeholder="videojuegos, dengue, seguridad vial…").strip().lower()
    fuentes = sorted({i.get("fuente") or "?" for i in items})
    temas_disp = sorted({t for i in items for t in (i.get("temas") or [])})
    f1, f2 = st.columns(2)
    with f1:
        f_sel = st.selectbox("Fuente", ["Todas"] + fuentes)
    with f2:
        t_sel = st.selectbox("Tema", ["Todos"] + temas_disp)

    n = 0
    mostrados = 0
    tope = 250
    for it in items:
        if f_sel != "Todas" and (it.get("fuente") or "?") != f_sel:
            continue
        if t_sel != "Todos" and t_sel not in (it.get("temas") or []):
            continue
        blob = " ".join([
            it.get("titulo") or "", it.get("snippet") or "",
            it.get("fuente") or "", " ".join(it.get("temas") or []),
        ]).lower()
        if q and q not in blob:
            continue
        n += 1
        if mostrados >= tope:
            continue
        mostrados += 1
        badges = []
        if it.get("colector") == "oficial":
            badges.append('<span class="en-badge b-nuevo">OTD</span>')
        if it.get("fecha_pub"):
            badges.append(f'<span class="en-badge b-fresco">{it["fecha_pub"]}</span>')
        if it.get("alerta"):
            badges.append(f'<span class="en-badge b-alerta">{html.escape(it["alerta"])}</span>')
        temas = ", ".join(it.get("temas") or []) or "sin tema"
        titulo = html.escape(it.get("titulo") or "")
        snip = html.escape(it.get("snippet") or "")
        fuente = html.escape(it.get("fuente") or "?")
        url = html.escape(it.get("url") or "#", quote=True)
        fecha = html.escape(it.get("fecha_pub") or it.get("fecha_pub_raw") or "sin fecha")
        via = html.escape(NOMBRE_COLECTOR.get(it.get("colector") or "", it.get("colector") or ""))
        st.markdown(
            f"<div class='en-card'><h4>{titulo}</h4>"
            f"<div class='en-meta'>{''.join(badges)} {fuente} · "
            f"{fecha} · {temas} · {via}</div>"
            + (f"<p class='en-snip'>{snip}</p>" if snip else "")
            + f"<a href='{url}' target='_blank' rel='noopener'>Abrir ↗</a></div>",
            unsafe_allow_html=True,
        )
    if not items:
        st.info(f"Sin menciones en «{ventana}».")
    elif n > tope:
        st.warning(f"Mostrando {tope} de {n}. Afina la búsqueda.")
    else:
        st.caption(f"{n} mostradas ({ventana}).")

    dias = indice.get("dias") or []
    if dias:
        st.caption("Días en carpeta: " + " · ".join(
            f"{dia_humano(d['dia'])} ({d['n']})" for d in dias[:12]
        ))

        arch = indice.get("archivo") or []
        with st.expander(f"Archivo interno ({len(arch)} días)"):
            st.caption("Días fuera de los 31 en vivo (jsonl.gz).")
            if not arch:
                st.caption("Todavía no hay días archivados.")
            else:
                nombres = [a["dia"] for a in arch]
                a_sel = st.selectbox("Día archivado", nombres, format_func=dia_humano)
                q_arch = st.text_input("Buscar en ese día archivado", key="qarch").strip().lower()
                guardados = corpus.load_archivo_dia(a_sel)
                hit = 0
                for it in guardados:
                    blob = " ".join([
                        it.get("titulo") or "", it.get("snippet") or "",
                        it.get("fuente") or "",
                    ]).lower()
                    if q_arch and q_arch not in blob:
                        continue
                    hit += 1
                    if hit > 80:
                        st.caption("Más de 80 coincidencias: afina la búsqueda.")
                        break
                    st.markdown(
                        f"- [{it.get('titulo','(sin título)')}]({it.get('url','')}) "
                        f"— {it.get('fuente','')} · {it.get('fecha_pub','')}"
                    )
                st.caption(f"{hit} en archivo {a_sel} ({len(guardados)} en el gzip).")


with tab_ins:
    click_ins = _panel_noticias(
        "inseguridad",
        "Noticias de inseguridad",
        "Delitos consumados de ENAPRES (P424): extorsión, secuestro, estafa, "
        "robos, etc. Sin intentos ni percepción de inseguridad. "
        "El archivo JSON solo crece; los duplicados se unen por URL o título.",
        "inseguridad",
    )
    if click_ins:
        _correr_rastreo()

with tab_ser:
    click_ser = _panel_noticias(
        "servicios",
        "Noticias de servicios básicos",
        "Agua, alcantarillado, electricidad y residuos sólidos en medios "
        "peruanos, 2026. El ubigeo se sugiere si el título nombra departamento "
        "o distrito.",
        "servicios",
    )
    if click_ser:
        _correr_rastreo()


def _opciones_alta():
    libros = _cargar_libros().get("libros") or []
    if not libros:
        return [{"id": "enapres-anual", "label": "General",
                 "alta_tema": "General", "alta_tipo": "publicacion"}]
    return libros


if tab_cargar is not None:
    with tab_cargar:
        st.markdown("### Cargar producto al catálogo")
        token_cfg = _secreto("ADMIN_TOKEN")
        if not token_cfg:
            st.info("Configure ADMIN_TOKEN para habilitar el alta.")
        else:
            pw = st.text_input("Clave de alta", type="password")
            if pw and not hmac.compare_digest(pw, str(token_cfg)):
                st.error("Clave incorrecta: no se escribió nada.")
            elif pw:
                opciones = _opciones_alta()
                etiquetas = [x.get("label") or x.get("id") for x in opciones]
                tipos = ["difusion", "boletin", "publicacion", "microdato"]
                st.caption(
                    "El libro es el recorte visible. Si el mapa de áreas cambia, "
                    "los productos con campo «libro» siguen en su tile; el resto "
                    "se reclasifica con las reglas de catalogo/libros.json."
                )
                with st.form("alta"):
                    f_libro_lab = st.selectbox("Libro", etiquetas)
                    f_tipo = st.selectbox("Tipo", tipos)
                    f_titulo = st.text_input("Título").strip()
                    f_url = st.text_input("URL https").strip()
                    f_fecha = st.date_input("Fecha")
                    f_periodo = st.text_input("Periodo (solo boletines)").strip()
                    f_desc = st.text_area("Descripción").strip()
                    f_img = st.text_input("Imagen (URL, opcional)").strip()
                    enviar = st.form_submit_button("Guardar en catálogo")
                if enviar:
                    if not f_titulo or not f_url:
                        st.error("Título y URL son obligatorios.")
                    elif not f_url.lower().startswith("https://"):
                        st.error("La URL debe empezar con https://")
                    else:
                        libro = next(
                            (x for x in opciones
                             if (x.get("label") or x.get("id")) == f_libro_lab),
                            opciones[0],
                        )
                        nuevo = {"tema": libro.get("alta_tema") or "General",
                                 "tipo": f_tipo,
                                 "libro": libro.get("id"),
                                 "titulo": f_titulo, "url": f_url,
                                 "fecha": f_fecha.isoformat(), "periodo": f_periodo,
                                 "imagen": f_img, "descripcion": f_desc,
                                 "agregado_por": "cargar-app",
                                 "agregado_en": f_fecha.isoformat()}
                        item, err = a_catalogo.agregar_item(nuevo)
                        if err:
                            st.warning(err)
                        else:
                            a_catalogo.escribir_data()
                            st.success(f"Guardado {item['id']}.")
                            st.rerun()
