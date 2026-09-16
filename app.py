"""Catálogo ENAPRES y menciones en prensa."""
from __future__ import annotations

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
except ImportError:
    actualizar = corpus = a_catalogo = None  # noqa: E402
    SIN_MONITOREO = True
else:
    SIN_MONITOREO = False

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


def dia_humano(iso: str) -> str:
    try:
        y, m, d = iso.split("-")
        return f"{int(d)} {MESES[int(m) - 1]} {y}"
    except (ValueError, IndexError):
        return iso


def fecha_catalogo() -> str:
    meta = DIR / "catalogo" / "meta.json"
    try:
        act = json.loads(meta.read_text(encoding="utf-8")).get("actualizado")
        if act:
            return str(act)
    except (OSError, ValueError):
        pass
    try:
        texto = CATALOGO.read_text(encoding="utf-8")
        return texto.split(MARCAS[0], 1)[1].split(MARCAS[1], 1)[0].strip()
    except (OSError, IndexError):
        return "sin fecha"


def fecha_catalogo_humana() -> str:
    raw = fecha_catalogo()
    try:
        dt = datetime.strptime(raw[:16], "%Y-%m-%d %H:%M")
        return f"{dt.day} {MESES[dt.month - 1]} {dt.year} · {dt.strftime('%H:%M')}"
    except (ValueError, IndexError):
        return raw


def _html_catalogo() -> str:
    h = CATALOGO.read_text(encoding="utf-8")
    carpeta = DIR / "catalogo"

    def carga(nombre):
        try:
            return json.loads((carpeta / nombre).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    data, prensa, meta = carga("data.json"), carga("prensa.json"), carga("meta.json") or {}
    if isinstance(data, list):
        h = re.sub(
            r"//<!--DATOS-INI-->.*?//<!--DATOS-FIN-->",
            "//<!--DATOS-INI-->\nconst DATA="
            + json.dumps(data, ensure_ascii=False)
            + ";\n//<!--DATOS-FIN-->",
            h, count=1, flags=re.S,
        )
    if isinstance(prensa, list):
        h = re.sub(
            r"//<!--PRENSA-INI-->.*?//<!--PRENSA-FIN-->",
            "//<!--PRENSA-INI-->\nconst PRENSA="
            + json.dumps(prensa, ensure_ascii=False)
            + ";\n//<!--PRENSA-FIN-->",
            h, count=1, flags=re.S,
        )
    act = meta.get("actualizado") if isinstance(meta, dict) else None
    if act:
        h = re.sub(
            r"<!--ACTUALIZADO-->.*?<!--/ACTUALIZADO-->",
            "<!--ACTUALIZADO-->" + str(act) + "<!--/ACTUALIZADO-->",
            h, count=1, flags=re.S,
        )
    return h


st.set_page_config(
    page_title="ENAPRES — catálogo y menciones",
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
    </style>
    """,
    unsafe_allow_html=True,
)

def _cargar_snapshot():
    try:
        snap = json.loads((DIR / "datos_publicos" / "menciones.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, []
    items = snap.get("items") or []
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


_SNAP_ITEMS: list = []
if SIN_MONITOREO:
    _snap, _SNAP_ITEMS = _cargar_snapshot()
    indice = {"actualizado": _snap.get("actualizado") or "—", "dias": [],
              "max_live": _snap.get("max_live", 31)}
else:
    corpus.migrar_diario_viejo()
    indice = corpus.load_indice()

if SIN_MONITOREO or _en_nube():
    tab_mon, tab_cat = st.tabs(["Menciones", "Catálogo"])
    tab_cargar = None
else:
    tab_mon, tab_cat, tab_cargar = st.tabs(["Menciones", "Catálogo", "Cargar"])

with tab_mon:
    top1, top2 = st.columns([3, 1])
    with top1:
        st.markdown("### Menciones de ENAPRES")
        st.caption(
            "Notas de gob.pe/INEI, prensa y redes que nombran la encuesta."
        )
    with top2:
        actualizar_click = False
        admin = _secreto("ADMIN_TOKEN")
        if _en_nube() and admin and _secreto("GH_TOKEN"):
            pin = st.text_input("Clave", type="password",
                                label_visibility="collapsed",
                                placeholder="Clave")
            if st.button("Actualizar ahora", type="primary",
                         use_container_width=True):
                if not pin or not hmac.compare_digest(pin, admin):
                    st.error("Clave incorrecta.")
                else:
                    ok, msg = _lanzar_gha()
                    (st.success if ok else st.error)(msg)
        elif _puede_rastrear_aqui():
            actualizar_click = st.button("Actualizar hoy", type="primary",
                                         use_container_width=True)
        else:
            st.caption("Auto: 07:17 y 16:17 Lima")
        st.caption(f"Última actualización: {fecha_catalogo_humana()}")

    if actualizar_click:
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

        with st.spinner("Rastreando menciones de ENAPRES (puede tardar varios minutos)…"):
            try:
                actualizar.correr(on_paso=on_paso)
            except Exception as e:
                st.error(f"La actualización falló: {e}")
            else:
                try:
                    pub = a_catalogo.desde_live() or []
                    bitacora.append(f"✓ Catálogo: {len(pub)} menciones")
                except Exception as e:
                    bitacora.append(f"⚠ Catálogo: no se regeneró ({e})")
                caja.markdown("\n\n".join(bitacora))
                st.success("Corpus del día actualizado.")
                st.rerun()

    st.caption(
        f"Última escritura: {fecha_catalogo_humana()} · "
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

with tab_cat:
    if not CATALOGO.exists():
        st.error(f"No se encontró el catálogo: {CATALOGO}")
    else:
        components.html(_html_catalogo(), height=1600, scrolling=True)


TEMAS_CATALOGO = ["Servicios básicos", "Agua y saneamiento", "Electrificación",
                  "Seguridad ciudadana", "Seguridad vial", "Dengue",
                  "Rabia canina", "Uso de videojuegos", "Libros digitales",
                  "Visita a museos", "General"]

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
                with st.form("alta"):
                    f_tipo = st.selectbox("Tipo", ["difusion", "boletin",
                                                   "publicacion", "microdato"])
                    f_tema = st.selectbox("Tema", TEMAS_CATALOGO)
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
                        nuevo = {"tema": f_tema, "tipo": f_tipo,
                                 "titulo": f_titulo, "url": f_url,
                                 "fecha": f_fecha.isoformat(), "periodo": f_periodo,
                                 "imagen": f_img, "descripcion": f_desc,
                                 "agregado_por": "cargar-app",
                                 "agregado_en": f_fecha.isoformat()}
                        item, err = a_catalogo.agregar_item(nuevo)
                        if err:
                            st.warning(err)
                        else:
                            a_catalogo.main()
                            st.success(f"Guardado {item['id']}.")
                            st.rerun()
