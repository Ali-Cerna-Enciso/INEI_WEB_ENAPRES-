# ENAPRES — catálogo y monitoreo de menciones

Aplicación en Streamlit con el catálogo de productos de la Encuesta Nacional de
Programas Presupuestales (INEI) y el seguimiento de las menciones que la encuesta
tiene en prensa, gob.pe y redes sociales. Un juego de colectores corre cuatro
veces al día desde GitHub Actions y deja todo listo para consulta.

## Pestañas

| Pestaña | Contenido |
|---|---|
| Catálogo | Boletines, publicaciones, microdatos y difusión, agrupados por libro, con portadas y enlaces al INEI. |
| Menciones | Notas que nombran la encuesta, con filtro por periodo, fuente y tema. |
| Noticias inseguridad | Delitos consumados de la ENAPRES (P424): extorsión, secuestro, estafa, robos, homicidio. |
| Noticias servicios básicos | Agua, alcantarillado, electricidad y residuos sólidos en medios peruanos, con ubigeo sugerido por el título. |
| Cargar | Alta de productos al catálogo desde la propia aplicación, disponible en la instalación local. |

## Cómo funciona

```
colectores (monitoreo/src) --> datos/live/<fecha>/   corpus por día
                                    |
                                    v
                           datos/indice.json  ·  archivo (jsonl.gz)
                                    |
        exportadores ---------------+--> datos_publicos/*.json --> app.py
```

Ocho colectores reúnen difusión OTD, gob.pe, prensa y redes, Google News,
feeds RSS, YouTube, GDELT y Bing News. La clasificación sale de la taxonomía en
`monitoreo/keywords/` y de las consultas por área en `monitoreo/queries/`.
Cada corrida agrega lo nuevo y los duplicados se unen por URL o título.

En la nube la app lee los JSON de `datos_publicos/`; en local usa el corpus
completo (31 días en vivo más el archivo) y puede lanzar el rastreo desde el
mismo botón de la pestaña Menciones.

## Actualización automática

`.github/workflows/monitoreo.yml`, horario de Lima:

| Cron (UTC) | Lima | Corrida |
|---|---|---|
| `17 12 * * *` | 07:17 | menciones |
| `17 15 * * *` | 10:17 | noticias |
| `17 21 * * *` | 16:17 | menciones y noticias |
| `50 4 * * *` | 23:50 | cierre del día |

Las corridas hacen commit de `datos/live`, `datos/indice.json`,
`datos/noticias` y `datos_publicos/`. Desde la pestaña **Actions** del repo el
workflow también arranca a mano, igual que desde el botón de actualización
de la app.

## Desarrollo local

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Streamlit es la única dependencia de `requirements.txt`; los colectores usan
la librería estándar de Python.

## Despliegue

La app corre en Streamlit Community Cloud apuntando a `app.py`. Los valores
configurables (`ADMIN_TOKEN`, `GH_TOKEN`, `GH_REPO`, `GH_WORKFLOW`) viven en
`.streamlit/secrets.toml`, con su plantilla en
`.streamlit/secrets.toml.example`; el archivo real queda fuera del repo.

## Estructura

```
├── app.py                        # Aplicación Streamlit
├── catalogo/
│   ├── index.html                # Plantilla del catálogo
│   ├── data.json                 # Productos INEI
│   ├── libros.json               # Reglas de agrupación por libro
│   └── img/                      # Portadas
├── datos_publicos/               # JSON que consume la app
├── datos/
│   ├── live/<fecha>/             # Capturas por día
│   ├── noticias/<area>/2026-MM.json  # Archivo mensual por área
│   └── indice.json               # Índice de días y colectores
├── monitoreo/
│   ├── src/                      # Colectores, corpus y exportadores
│   ├── keywords/                 # Taxonomía (anclas y temas)
│   ├── queries/                  # Consultas por área
│   └── fuentes/                  # Feeds, medios y fuentes oficiales
├── .github/workflows/monitoreo.yml
├── .streamlit/
└── requirements.txt
```

## Fuentes

Enlaces y titulares de INEI, gob.pe, medios de comunicación peruanos y redes
sociales, enlazados a su origen. Las noticias de inseguridad corresponden a
los delitos consumados de la ENAPRES (P424).
