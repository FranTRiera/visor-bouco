# Visor del BOUCO

Consulta el Boletín Oficial de la Universidad de Córdoba filtrando por tipo de
convocatoria, área de conocimiento, fase, sección, departamento y fecha.

## Uso

- **Abrir el visor:** doble clic en `index.html` (no necesita servidor).
- **Actualizar datos:** doble clic en `actualizar_y_abrir.bat`, o `python scraper.py`.
  Solo descarga los anuncios nuevos (unos segundos).
- **Rehacer todo el histórico (desde 2014):** `python scraper.py --full` (≈40 min).

## Versión web (GitHub Pages)

El visor está publicado en GitHub Pages. El workflow `.github/workflows/actualizar.yml`
ejecuta `scraper.py` de lunes a viernes (8:30, 13:30 y 19:30) y sube `data/bouco.json`
si hay anuncios nuevos; Pages se republica solo. Para forzar una actualización:
pestaña *Actions* del repositorio → *Actualizar BOUCO* → *Run workflow*.

GitHub desactiva los workflows programados si el repositorio pasa 60 días sin actividad;
si ocurre, se reactiva desde la pestaña *Actions*.

## Ficheros

- `scraper.py` — descarga la bandeja de https://sede.uco.es/bouco/ recorriendo cada
  sección (tema/subtema) para etiquetar los anuncios. Solo librería estándar.
- `classify.py` — clasifica por palabras clave: tipo de convocatoria, fase,
  área de conocimiento y departamento. Ajusta aquí las reglas si algo se clasifica mal.
- `data/bouco.json` y `data/bouco-data.js` — datos descargados.
- `index.html` — el visor. Los filtros quedan en la URL, así que puedes guardar
  búsquedas como marcadores. Botón "Exportar CSV" para Excel.

## Limitaciones

- Tipo de convocatoria, fase y área se deducen del título y la descripción:
  pueden fallar en anuncios redactados de forma atípica.
- Los PDF adjuntos no se descargan; cada anuncio enlaza a su página oficial.
