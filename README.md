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

## Actualización

GitHub Actions rastrea dos veces al día, escribe los JSON y hace commit. El HTML no cambia. Streamlit Cloud redespliega con el push.

Pedido manual: GitHub → Actions → monitoreo → Run workflow.

En Streamlit, «Actualizar ahora» pide `ADMIN_TOKEN` y dispara el mismo workflow (`GH_TOKEN` en secretos de la nube).

Aportes que el rastreador no vio: editar `datos/web_extra.json` (menciones) o `datos/catalogo.json` (productos).

Tras 12 horas sin visitas el servicio se suspende; el primer acceso lo reanuda.

## Local

```bash
python -m streamlit run app.py
```

`http://localhost:8501`
