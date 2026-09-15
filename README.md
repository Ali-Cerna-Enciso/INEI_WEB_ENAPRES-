# ENAPRES — catálogo de productos y menciones

Aplicación Streamlit del Instituto Nacional de Estadística e Informática (INEI) para consulta interna de:

- productos públicos de la Encuesta Nacional de Programas Presupuestales (boletines, publicaciones, microdatos);
- menciones en prensa, gob.pe y redes institucionales.

Repositorio: [Ali-Cerna-Enciso/INEI_WEB_ENAPRES-](https://github.com/Ali-Cerna-Enciso/INEI_WEB_ENAPRES-).

Solo se versionan enlaces y textos ya públicos. No incluir microdatos, bases internas ni credenciales.

## Contenido

| Ruta | Uso |
|---|---|
| `app.py` | Aplicación Streamlit |
| `catalogo/index.html` | Catálogo (HTML autocontenido) |
| `datos_publicos/menciones.json` | Instantánea de menciones (prensa y difusión) |
| `requirements.txt` | Dependencia: Streamlit |

El rastreo de fuentes se ejecuta fuera de este repositorio. Aquí solo se publica el resultado.

## Uso

Aplicación de consulta. La recarga muestra la última instantánea subida a `main`.
Tras 12 horas sin visitas el servicio se suspende y el primer acceso lo reanuda.

## Actualización

En el entorno interno se regeneran `catalogo/index.html` y `datos_publicos/menciones.json`. Luego:

```bash
git add catalogo/index.html datos_publicos/menciones.json
git commit -m "Actualiza catálogo y menciones"
git push
```

Streamlit Cloud redespliega con el push.

## Ejecución local

```bash
python -m streamlit run app.py
```

Dirección: `http://localhost:8501`.
