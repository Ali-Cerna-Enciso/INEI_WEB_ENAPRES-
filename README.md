# ENAPRES — catálogo de productos y menciones

Consulta de productos públicos de ENAPRES y menciones en prensa, gob.pe y redes.

Repositorio: [Ali-Cerna-Enciso/INEI_WEB_ENAPRES-](https://github.com/Ali-Cerna-Enciso/INEI_WEB_ENAPRES-).

Solo enlaces y textos ya públicos. Sin microdatos ni credenciales.

## Contenido

| Ruta | Uso |
|---|---|
| `app.py` | Aplicación Streamlit |
| `catalogo/index.html` | Plantilla (el estilo no se reescribe) |
| `catalogo/data.json` | Productos INEI (alta o `datos/catalogo.json`) |
| `datos_publicos/menciones.json` | Instantánea de la pestaña Menciones |
| `datos/web_extra.json` | Aportes manuales de menciones |
| `monitoreo/` | Colectores (GitHub Actions) |
| `datos/live/` | Corpus por día |
| `.github/workflows/monitoreo.yml` | 07:17 y 16:17 hora Lima + botón en Actions |

## Nota

Catálogo interno de consulta. El servicio se suspende tras 12 horas sin
visitas; el primer acceso lo reanuda.
