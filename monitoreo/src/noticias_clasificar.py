"""Clasificador de noticias temáticas (inseguridad / servicios).

No usa el score() de menciones ENAPRES. Aquí el ancla ES el delito o el
servicio; si calza, también se etiqueta (el molde viejo dejaba temas=[]).

Inseguridad sigue P424 del diccionario ENAPRES 2026 y los boletines de
victimización / seguridad ciudadana: solo hechos CONSUMADOS. Fuera:
intentos/tentativas y percepción de inseguridad.

Servicios sigue «Acceso a los servicios básicos en el Perú»: agua por red,
alcantarillado, electricidad, residuos sólidos.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from filtro import norm

REDES_HOSTS = (
    "facebook.com", "fb.com", "instagram.com", "x.com", "twitter.com",
    "tiktok.com", "youtube.com", "youtu.be", "t.me", "telegram.me",
    "whatsapp.com", "threads.net",
)

TIPO_NOTICIAS = "Noticias/reportes"
TIPO_REDES = "Redes sociales"

# Prefijos que convierten un delito en tentativa (P424 ítems pares).
_INTENTO = re.compile(
    r"(?:intento|intentos|tentativa|tentativas|intencion)\s+de\s+$"
)

# Percepción / encuestas de sensación — no son un hecho delictivo.
_PERCEPCION = (
    "percepcion de inseguridad",
    "sensacion de inseguridad",
    "miedo a ser victima",
    "miedo a la delincuencia",
    "se siente inseguro",
    "caminar solo de noche",
    "caminar de noche por su barrio",
    "encuesta de victimizacion",
    "indice de inseguridad",
)

# Inseguridad: etiqueta ENAPRES → variantes (sin tildes; se compara con norm()).
# Orden: frases largas primero dentro de cada delito.
INSEGURIDAD = (
    ("Extorsión", (
        "extorsion telefonica", "extorsion virtual", "carta de extorsion",
        "cobro de cupo", "cobran cupo", "cobrar cupo",
        "gota a gota", "vacuna criminal", "extorsionador", "extorsionaron",
        "extorsionar", "extorsion",
    )),
    ("Secuestro", (
        "secuestro al paso", "secuestro express", "secuestro de un",
        "secuestro de una", "secuestro del", "secuestraron", "secuestrado",
        "secuestrada", "plagio de persona", "levanton", "secuestro",
    )),
    ("Homicidio / sicariato", (
        "ajuste de cuentas", "sicariato", "sicario", "feminicidio",
        "asesinaron", "asesinado", "asesinada", "asesinato", "homicidio",
        "masacre", "acribillado", "acribillaron",
    )),
    ("Estafa", (
        "estafa telefonica", "estafa virtual", "estafa piramidal",
        "estafaron", "estafado", "estafador", "estafa",
    )),
    ("Fraude bancario", (
        "fraude bancario", "clonacion de tarjeta", "clonaron tarjeta",
        "phishing bancario", "suplantacion bancaria",
    )),
    ("Suplantación de identidad", (
        "suplantacion de identidad", "robo de identidad", "clonacion de dni",
    )),
    ("Ciberacoso", (
        "ciberacoso", "acoso virtual", "grooming",
    )),
    ("Delito informático", (
        "delito informatico", "delitos informaticos", "ciberataque",
        "ransomware", "hackeo de cuenta", "phishing",
    )),
    ("Robo de vehículo", (
        "robo de vehiculo", "robo de auto", "robo de camioneta",
        "robo de un auto", "robo de una camioneta", "robaron el auto",
        "robaron la camioneta", "huayco de autos",
    )),
    ("Robo de autopartes", (
        "robo de autopartes", "robo de llantas", "robo de aros",
        "robaron las llantas",
    )),
    ("Robo de motocicleta/mototaxi", (
        "robo de motocicleta", "robo de mototaxi", "robo de moto",
        "robaron la moto", "robaron una moto",
    )),
    ("Robo de bicicleta", (
        "robo de bicicleta", "robaron la bicicleta",
    )),
    ("Robo de dinero, cartera, celular", (
        "robo de celular", "robo de celular", "robo del celular",
        "robo de cartera", "robo de dinero", "robo al paso",
        "carterista", "lanzero", "robaron el celular",
        "robaron su celular", "hurto de celular",
    )),
    ("Robo de negocio", (
        "robo de negocio", "robo a negocio", "asaltaron el negocio",
        "asaltaron una tienda", "asaltaron el grifo", "robo a grifo",
    )),
    ("Robo en la vivienda", (
        "robo en la vivienda", "robo a vivienda", "robo en casa",
        "robo a casa", "asalto a vivienda", "entraron a la casa",
        "marcado de vivienda", "marcaje de vivienda",
    )),
    ("Amenazas e intimidaciones", (
        "amenazas de muerte", "amenaza de muerte", "amenazas e intimidaciones",
        "intimidaciones", "amenazo de muerte",
    )),
    ("Maltrato físico y/o psicológico", (
        "maltrato fisico", "maltrato psicologico", "violencia familiar",
        "violencia contra la mujer",
    )),
    ("Ofensas sexuales", (
        "ofensas sexuales", "acoso sexual", "abuso sexual", "violacion sexual",
        "violacion a una", "tocamiento indebido",
    )),
    ("Asalto a mano armada", (
        "asalto a mano armada", "robo a mano armada", "mano armada",
        "asaltaron", "asalto armado",
    )),
)

# Anclas extra: meten la nota si el título/URL habla del hecho, y se mapean
# a un tema ENAPRES cuando no hubo etiqueta más precisa.
ANCLAS_INSEG = (
    ("Extorsión", ("cupo", "vacuna criminal",)),
    ("Homicidio / sicariato", (
        "balacera", "arma de fuego", "disparos", "disparo", "acribillar",
    )),
    ("Asalto a mano armada", ("los pulpos", "la jauria",)),
)

SERVICIOS = (
    ("Agua por red pública", (
        "corte de agua", "cortes de agua", "sin agua potable", "sin agua",
        "desabastecimiento de agua", "falta de agua", "racionamiento de agua",
        "no hay agua", "agua potable", "sedapal", "sedalib", "sedacusco",
        "sedapar", "sedalib", "eps ", "cisternas de agua", "red de agua",
        "servicio de agua",
    )),
    ("Alcantarillado", (
        "colapso de desague", "desborde de desague", "red de desague",
        "alcantarillado", "aniego", "desague", "desagues",
        "disposicion sanitaria",
    )),
    ("Energía eléctrica", (
        "corte de luz", "cortes de luz", "corte electrico", "sin energia electrica",
        "sin luz", "apagon", "apagones", "hidrandina", "electrocentro",
        "electro oriente", "electro sur", "electroperu", "enel", "seal",
        "luz del sur", "electrificacion", "alumbrado electrico",
        "servicio electrico",
    )),
    ("Residuos sólidos", (
        "recoleccion de basura", "recoleccion domiciliaria", "no recogen la basura",
        "relleno sanitario", "residuos solidos", "camion de basura",
        "botadero", "basura en las calles",
    )),
)

EXCLUSION_INSEG = (
    "liga 1", "partido de futbol", "videojuego", "receta",
    "encuesta electoral", "intencion de voto", "enalapril", "comprimido",
)
EXCLUSION_SERV = (
    "luz verde", "agua de coco", "agua de mar", "luz de esperanza",
    "encuesta electoral", "intencion de voto", "enapres",
    "encuesta nacional de programas presupuestales",
)


def tipo_fuente(fuente: str = "", url: str = "") -> str:
    blob = f"{fuente or ''} {url or ''}".lower()
    host = ""
    try:
        host = (urlparse(url or "").netloc or "").lower()
    except Exception:
        host = ""
    texto = f"{blob} {host}"
    if any(h in texto for h in REDES_HOSTS):
        return TIPO_REDES
    return TIPO_NOTICIAS


def _blob(titulo: str, snippet: str = "", url: str = "") -> str:
    path = ""
    try:
        path = urlparse(url or "").path.replace("-", " ").replace("/", " ")
    except Exception:
        path = url or ""
    return norm(f"{titulo} {snippet} {path}")


def _es_intento(blob: str, pos: int) -> bool:
    prev = blob[max(0, pos - 28):pos]
    return bool(_INTENTO.search(prev))


def _posiciones(blob: str, termino: str) -> list[int]:
    t = termino.strip()
    if not t:
        return []
    esc = re.escape(t)
    if " " in t or len(t) >= 6:
        pat = esc
    else:
        pat = rf"(?<![a-z0-9]){esc}(?![a-z0-9])"
    return [m.start() for m in re.finditer(pat, blob)]


def _hits(blob: str, terminos: tuple[str, ...], ignorar_intento: bool) -> list[tuple[str, int]]:
    out = []
    for term in terminos:
        for pos in _posiciones(blob, term):
            if ignorar_intento and _es_intento(blob, pos):
                continue
            out.append((term, pos))
    return out


def _solo_percepcion(blob: str) -> bool:
    return any(p in blob for p in _PERCEPCION)


def clasificar(area: str, titulo: str, snippet: str = "", url: str = ""):
    """Devuelve (score, [etiquetas]) o None si no entra al corpus."""
    blob = _blob(titulo, snippet, url)
    if not blob.strip():
        return None
    if area == "inseguridad":
        return _clasificar_inseguridad(blob)
    if area == "servicios":
        return _clasificar_servicios(blob)
    return None


def _clasificar_inseguridad(blob: str):
    if any(e in blob for e in EXCLUSION_INSEG):
        return None
    cats = []
    score = 1
    for etiqueta, terminos in INSEGURIDAD:
        hits = _hits(blob, terminos, ignorar_intento=True)
        if hits:
            cats.append(etiqueta)
            # Título (el blob empieza por el título) puntúa más.
            score += 2 if hits[0][1] < 180 else 1
    if not cats:
        for etiqueta, terminos in ANCLAS_INSEG:
            hits = _hits(blob, terminos, ignorar_intento=True)
            if hits:
                cats.append(etiqueta)
                score += 1
    if not cats:
        return None
    if _solo_percepcion(blob) and not cats:
        return None
    # Si SOLO hay percepción y el único ancla débil es genérico, fuera.
    # Con delito concreto (extorsión, secuestro…) se conserva.
    if _solo_percepcion(blob) and set(cats) <= {"Asalto a mano armada"}:
        return None
    # Dedup conservando orden.
    seen, ordered = set(), []
    for c in cats:
        if c not in seen:
            seen.add(c)
            ordered.append(c)
    return score, ordered


def _clasificar_servicios(blob: str):
    if any(e in blob for e in EXCLUSION_SERV):
        return None
    cats = []
    score = 1
    for etiqueta, terminos in SERVICIOS:
        hits = _hits(blob, terminos, ignorar_intento=False)
        if hits:
            cats.append(etiqueta)
            score += 2 if hits[0][1] < 180 else 1
    if not cats:
        return None
    return score, cats


def temas_catalogo(area: str) -> list[str]:
    if area == "inseguridad":
        return [e for e, _ in INSEGURIDAD]
    if area == "servicios":
        return [e for e, _ in SERVICIOS]
    return []
