"""ENAPRES — catálogo de productos y menciones en prensa (Streamlit)."""
from __future__ import annotations

import html
import hmac
import json
import os
import sys
from datetime import date, timedelta
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
    # Copia sin monitoreo/ (p. ej. Streamlit Cloud desde este repo):
    # la app abre igual; solo el catálogo tiene contenido.
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


def dia_humano(iso: str) -> str:
    try:
        y, m, d = iso.split("-")
        return f"{int(d)} {MESES[int(m) - 1]} {y}"
    except (ValueError, IndexError):
        return iso


def fecha_catalogo() -> str:
    try:
        texto = CATALOGO.read_text(encoding="utf-8")
        return texto.split(MARCAS[0], 1)[1].split(MARCAS[1], 1)[0].strip()
    except (OSError, IndexError):
        return "sin fecha"


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

if SIN_MONITOREO:
    tab_mon, tab_cat = st.tabs(["Menciones", "Catálogo"])
    tab_cargar = None
else:
    tab_mon, tab_cat, tab_cargar = st.tabs(["Menciones", "Catálogo", "Cargar"])

with tab_mon:
    top1, top2 = st.columns([3, 1])
    with top1:
        st.markdown("### Menciones de ENAPRES")
        st.caption(
            "Notas de gob.pe/INEI, prensa y redes institucionales que nombran la encuesta. "
            f"Catálogo actualizado: {fecha_catalogo()}."
        )
    with top2:
        if not SIN_MONITOREO:
            actualizar_click = st.button("Actualizar hoy", type="primary",
                                         use_container_width=True)
        else:
            actualizar_click = False

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
        f"Última escritura: {indice.get('actualizado', '—')} · "
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
    if not items and SIN_MONITOREO:
        st.info("Sin menciones en esta vista. La versión web muestra la última "
                "instantánea incluida en el repositorio (ver «Última escritura»).")
    elif not items:
        st.info(
            f"Nada en «{ventana}». Pulsa **Actualizar hoy** para buscar en gob.pe/INEI "
            "(entra a cada noticia) y en Google News con #ENAPRES. "
            "Los posts de Facebook institucional no se leen solos: van en Difusión OTD."
        )
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
        with st.expander(f"Archivo interno ({len(arch)} días compactos en datos/archivo)"):
            st.write(
                "Cuando hay más de 31 días en vivo, el más antiguo sale de las carpetas "
                "y queda aquí como `.jsonl.gz` (compacto, archivo interno)."
            )
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
        components.html(CATALOGO.read_text(encoding="utf-8"), height=1600, scrolling=True)


TEMAS_CATALOGO = ["Servicios básicos", "Agua y saneamiento", "Electrificación",
                  "Seguridad ciudadana", "Seguridad vial", "Dengue",
                  "Rabia canina", "Uso de videojuegos", "Libros digitales",
                  "Visita a museos", "General"]

if tab_cargar is not None:
    with tab_cargar:
        st.markdown("### Cargar producto al catálogo")
        st.caption("Registro interno: escribe en el catálogo y regenera el HTML.")
        token_cfg = ""
        try:
            token_cfg = st.secrets.get("ADMIN_TOKEN", "")
        except Exception:
            token_cfg = ""
        token_cfg = token_cfg or os.environ.get("ADMIN_TOKEN", "")
        if not token_cfg:
            st.info("Alta deshabilitada: configura ADMIN_TOKEN en "
                    "webapp/.streamlit/secrets.toml o como variable de entorno.")
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
                            st.success(f"Guardado {item['id']}: HTML regenerado.")
