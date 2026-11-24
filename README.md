# La Rana de Árbol de Ojos Rojos (*Agalychnis callidryas*) en Costa Rica

**Autor:** Jarod Salas Díaz

**Curso:** GF-0657 Programación en SIG, II ciclo 2026. Proyecto final (aplicación web)

**Aplicación publicada:** https://proyecto-final-psig-jasalas.streamlit.app/

## Descripción

Aplicación web desarrollada con streamlit que muestra dónde y cuándo se ha observado la rana de ojos rojos
(*Agalychnis callidryas*) en Costa Rica, a partir de los registros de ciencia ciudadana de iNaturalist.
Usa los mismos datos y el mismo código de las tareas 2 y 3: se conservan solo las observaciones con grado de
investigación, coordenadas no oscurecidas, precisión de 1 km o mejor y fecha a partir del 2000, y cada observación
se asigna a su cantón mediante una unión espacial (`sjoin` y `sjoin_nearest`, en CRTM05) con los límites del IGN.

La barra lateral tiene tres controles (provincia, rango de años y época del año) que filtran todos los elementos
de la página:

- **Indicadores:** número de observaciones, cantones con observaciones, número de observadores y promedio anual.
- **¿Sabía que…?:** cuatro datos curiosos calculados para la selección (proporción de observaciones nocturnas,
  año récord, concentración en pocos cantones y proporción de observadores ocasionales).
- **Mapa web (folium y streamlit-folium):** coropletas del número de observaciones por cantón, límites de provincias
  puntos de observación con su foto y una capa de puntos de calor, con control de capas, etiquetas emergentes y leyenda.
- **Gráficos (plotly):** observaciones por año, por hora del día (gráfico polar), por mes (estacionalidad),
  carrera animada de los 10 cantones con más observaciones y los 15 cantones con más observaciones.
- **Galería:** fotos recientes de la selección con licencia Creative Commons, con su crédito y enlace al registro.
- **Tablas:** resumen por cantón y registros individuales con foto, descargables en CSV.

La aplicación también incluye una ficha breve de la especie y un tema de colores propio (`.streamlit/config.toml`).

Ejecución local, en el ambiente conda del curso:

```bash
streamlit run app.py
```

## Fuentes de los datos

- iNaturalist. (2026). *Observaciones de* Agalychnis callidryas *en Costa Rica* [Conjunto de datos].
  https://www.inaturalist.org/observations?place_id=6924&taxon_id=23702. Se carga desde el repositorio de la tarea 2:
  https://github.com/jasalas2/tarea2_psig
- Animal Diversity Web y The Embryo Project (ASU), para la ficha de la especie:
  https://animaldiversity.org/accounts/Agalychnis_callidryas/ y
  https://embryo.asu.edu/pages/how-do-embryos-assess-risk-vibrational-cues-predator-induced-hatching-red-eyed-treefrogs-2005
- Instituto Geográfico Nacional. (2026). *Límites cantonales y provinciales de Costa Rica* [Conjunto de datos,
  distribuido en el repositorio del curso]. https://github.com/gf0657-programacionsig/2026-ii/tree/main/datos/ign

## Declaración de uso de inteligencia artificial

Se usó **Claude (Anthropic)** como asistente de programación:

- **Propósito:** generar una primera versión de `app.py` a partir de las funciones de las tareas 2 y 3 y de la
  aplicación de ejemplo del curso, explicar el código, y verificar que la aplicación corriera sin errores
  (`streamlit run` y `AppTest`, incluida una selección sin datos).
- **Partes:** estructura general de `app.py`, adaptación de las funciones de carga y de unión espacial a funciones con
  `@st.cache_data`, construcción del mapa en una función con `@st.cache_resource`, configuración de las tablas
  (`column_config`) y de los gráficos de plotly, cálculo de los datos curiosos, galería de fotos, tema de colores, y redacción de este README.

Todo el código fue revisado y comprendido por el autor, quien verificó los resultados (conteos por cantón y por año)
contra los obtenidos en las tareas 2 y 3.
