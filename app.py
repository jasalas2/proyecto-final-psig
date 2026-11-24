# Proyecto final GF-0657 Programación en SIG (II ciclo 2026)
# Observaciones de la rana de ojos rojos (Agalychnis callidryas) en Costa Rica (iNaturalist)
# Autor: Jarod Salas
# Ejecución: streamlit run app.py
import copy

import folium
import geopandas as gpd
import pandas as pd
import plotly.express as px
import streamlit as st
from branca.colormap import StepColormap
from streamlit_folium import st_folium

# ---------- Configuración de la página (primera llamada a streamlit) ----------
st.set_page_config(page_title="Rana de ojos rojos en Costa Rica", page_icon="🐸", layout="wide")

# ---------- Constantes ----------
URL_OBSERVACIONES = (
    "https://raw.githubusercontent.com/jasalas2/tarea2_psig/main/"
    "agalychnis_callidryas_costa_rica_inaturalist.csv"
)
URL_IGN = "https://raw.githubusercontent.com/gf0657-programacionsig/2026-ii/main/datos/ign"
SRC_CRTM05 = 8908  # proyectado, en metros: uniones espaciales y áreas
SRC_WGS84 = 4326   # geográfico: el que usan los mapas web

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
EPOCAS = {
    "Todo el año": list(range(1, 13)),
    "Época seca (diciembre-abril)": [12, 1, 2, 3, 4],
    "Época lluviosa (mayo-noviembre)": [5, 6, 7, 8, 9, 10, 11],
}

# Clases fijas del mapa de coropletas: se mantienen iguales con cualquier filtro,
# de modo que los colores de dos selecciones distintas se pueden comparar
CORTES = [1, 11, 51, 201, 501]
COLORES = ["#ffffcc", "#c2e699", "#78c679", "#31a354", "#006837"]
COLOR_SIN_DATOS = "#e0e0e0"


# ---------- Datos, en caché ----------
@st.cache_data
def cargar_cantones():
    """Cantones del IGN con su área (km²), simplificados y en WGS84."""
    cantones = gpd.read_file(f"{URL_IGN}/cantones.gpkg")  # CRTM05
    cantones["area_km2"] = cantones.area / 1e6
    cantones["geometry"] = cantones.geometry.simplify(50)  # tolerancia en metros
    return cantones.to_crs(SRC_WGS84)


@st.cache_data
def cargar_provincias():
    """Provincias del IGN, simplificadas y en WGS84."""
    provincias = gpd.read_file(f"{URL_IGN}/provincias.gpkg")
    provincias["geometry"] = provincias.geometry.simplify(50)
    return provincias.to_crs(SRC_WGS84)


@st.cache_data
def cargar_observaciones(precision_max=1000, distancia_max=2000):
    """Observaciones confiables de iNaturalist como puntos en WGS84, con la provincia y el cantón
    asignados por unión espacial (funciones preparar_observaciones y asignar_canton de la tarea 3)."""
    obs = pd.read_csv(URL_OBSERVACIONES, low_memory=False)
    filtro = (
        (obs["quality_grade"] == "research")
        & (obs["coordinates_obscured"].astype(str).str.lower() == "false")
        & ((obs["positional_accuracy"] <= precision_max) | obs["positional_accuracy"].isna())
    )
    obs = obs.loc[filtro].copy()
    obs["fecha"] = pd.to_datetime(obs["observed_on"], errors="coerce")
    obs = obs[obs["fecha"].dt.year >= 2000]  # descarta fechas vacías o erróneas, como en las tareas 2 y 3
    obs["anio"] = obs["fecha"].dt.year.astype(int)
    obs["mes"] = obs["fecha"].dt.month.astype(int)

    puntos = gpd.GeoDataFrame(
        obs[["id", "fecha", "anio", "mes", "place_guess", "user_login", "positional_accuracy", "uri"]],
        geometry=gpd.points_from_xy(obs["longitude"], obs["latitude"]),
        crs=SRC_WGS84,
    ).to_crs(SRC_CRTM05)

    # Unión espacial en CRTM05 con los límites sin simplificar
    cantones = gpd.read_file(f"{URL_IGN}/cantones.gpkg")[["provincia", "codigo_canton", "canton", "geometry"]]
    unidos = gpd.sjoin(puntos, cantones, how="left", predicate="within")
    fuera = unidos["canton"].isna()
    cercanos = gpd.sjoin_nearest(puntos.loc[fuera], cantones, how="left", max_distance=distancia_max)
    cercanos = cercanos[~cercanos.index.duplicated()]  # por si un punto equidista de dos cantones
    unidos.loc[fuera, ["provincia", "codigo_canton", "canton"]] = cercanos[["provincia", "codigo_canton", "canton"]]
    unidos = unidos.drop(columns="index_right").dropna(subset=["canton"])

    unidos = unidos.rename(columns={"place_guess": "lugar", "user_login": "observador",
                                    "positional_accuracy": "precision_m"})
    unidos["lugar"] = unidos["lugar"].fillna("Sin descripción")
    return unidos.to_crs(SRC_WGS84)


# ---------- Filtros (pandas) ----------
def filtrar(provincia, anios, epoca):
    """Observaciones que cumplen los tres controles."""
    obs = cargar_observaciones()
    seleccion = obs[obs["anio"].between(anios[0], anios[1]) & obs["mes"].isin(EPOCAS[epoca])]
    if provincia != "Todas":
        seleccion = seleccion[seleccion["provincia"] == provincia]
    return seleccion


def resumir_cantones(seleccion, provincia):
    """Capa de cantones (de la provincia elegida o de todo el país) con las observaciones de la selección."""
    cantones = cargar_cantones()
    if provincia != "Todas":
        cantones = cantones[cantones["provincia"] == provincia]
    conteo = seleccion.groupby("codigo_canton").size().rename("observaciones")
    capa = cantones.merge(conteo, left_on="codigo_canton", right_index=True, how="left")
    capa["observaciones"] = capa["observaciones"].fillna(0).astype(int)
    capa["densidad"] = (capa["observaciones"] / capa["area_km2"] * 100).round(2)
    return capa


# ---------- Mapa, en caché por combinación de filtros ----------
@st.cache_resource
def crear_mapa(provincia, anios, epoca):
    """Mapa web: coropletas por cantón, provincias de referencia y puntos de observación (WGS84)."""
    seleccion = filtrar(provincia, anios, epoca)
    capa = resumir_cantones(seleccion, provincia)
    provincias = cargar_provincias()

    mapa = folium.Map(location=[9.8, -84.1], zoom_start=8, tiles=None, control_scale=True)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(mapa)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri, Maxar, Earthstar Geographics", name="Esri satelital", show=False,
    ).add_to(mapa)

    # Capa 1: coropletas del número de observaciones por cantón
    escala = StepColormap(COLORES, index=CORTES, vmin=1, vmax=1000,
                          caption="Observaciones por cantón (número de registros)")

    def estilo(feature):
        n = feature["properties"]["observaciones"]
        return {"fillColor": escala(n) if n > 0 else COLOR_SIN_DATOS,
                "color": "white", "weight": 0.6, "fillOpacity": 0.75}

    folium.GeoJson(
        capa[["canton", "provincia", "observaciones", "densidad", "geometry"]],
        name="Observaciones por cantón",
        style_function=estilo,
        highlight_function=lambda f: {"weight": 2.5, "color": "#333333"},
        tooltip=folium.GeoJsonTooltip(
            fields=["canton", "provincia", "observaciones", "densidad"],
            aliases=["Cantón:", "Provincia:", "Observaciones:", "Densidad (obs/100 km²):"],
            localize=True,
        ),
    ).add_to(mapa)
    escala.add_to(mapa)

    # Capa 2: provincias (referencia)
    folium.GeoJson(
        provincias[["provincia", "geometry"]], name="Provincias",
        style_function=lambda f: {"fill": False, "color": "#444444", "weight": 1.5},
        tooltip=folium.GeoJsonTooltip(fields=["provincia"], aliases=["Provincia:"]),
    ).add_to(mapa)

    # Capa 3: puntos, en un panel propio para que queden siempre encima de los polígonos
    folium.map.CustomPane("puntos", z_index=650).add_to(mapa)
    marcador = folium.CircleMarker(radius=3, color="#7f0000", weight=0.5,
                                   fill=True, fill_color="#e34a33", fill_opacity=0.85)
    marcador.options["pane"] = "puntos"
    puntos = seleccion.assign(fecha_texto=seleccion["fecha"].dt.strftime("%Y-%m-%d"))
    folium.GeoJson(
        puntos[["fecha_texto", "lugar", "canton", "observador", "uri", "geometry"]],
        name="Observaciones (iNaturalist)",
        marker=marcador,
        tooltip=folium.GeoJsonTooltip(fields=["canton", "fecha_texto"], aliases=["Cantón:", "Fecha:"]),
        popup=folium.GeoJsonPopup(
            fields=["fecha_texto", "lugar", "canton", "observador", "uri"],
            aliases=["Fecha:", "Lugar:", "Cantón:", "Observador:", "Registro:"],
        ),
    ).add_to(mapa)

    folium.LayerControl(collapsed=False).add_to(mapa)

    # Encuadre: la provincia elegida o el territorio continental (sin la isla del Coco)
    if provincia != "Todas":
        oeste, sur, este, norte = capa.total_bounds
        mapa.fit_bounds([[sur, oeste], [norte, este]])
    else:
        mapa.fit_bounds([[8.0, -86.0], [11.25, -82.5]])
    return mapa


def formato_numero(valor, decimales=0):
    """Número con espacio como separador de miles."""
    return f"{valor:,.{decimales}f}".replace(",", " ")


# ---------- Carga inicial ----------
observaciones = cargar_observaciones()
anio_min, anio_max = int(observaciones["anio"].min()), int(observaciones["anio"].max())

# ---------- Controles ----------
st.sidebar.title("Filtros")
provincia = st.sidebar.selectbox("Provincia", ["Todas"] + sorted(observaciones["provincia"].unique()))
anios = st.sidebar.slider("Años de observación", anio_min, anio_max, (anio_min, anio_max))
epoca = st.sidebar.radio("Época del año", list(EPOCAS))
st.sidebar.caption("Todos los indicadores, tablas, gráficos y el mapa responden a estos filtros.")

seleccion = filtrar(provincia, anios, epoca)
resumen = resumir_cantones(seleccion, provincia)

# ---------- Encabezado ----------
st.title("🐸 La rana de ojos rojos (*Agalychnis callidryas*) en Costa Rica")
st.markdown(
    "Esta aplicación muestra dónde y cuándo se ha observado la rana de ojos rojos, un anfibio de las tierras bajas "
    "húmedas, según los registros de ciencia ciudadana de **iNaturalist** con grado de investigación, coordenadas "
    "no oscurecidas y una precisión de 1 km o mejor (2000-2026). Cada observación se asignó a su cantón mediante una "
    "unión espacial con los límites del **Instituto Geográfico Nacional (IGN)**. Use los filtros de la barra lateral "
    "para elegir una provincia, un rango de años y una época del año; las cifras, la tabla, los gráficos y el mapa "
    "se actualizan con la selección."
)

texto_provincia = "todas las provincias" if provincia == "Todas" else f"provincia de {provincia}"
st.markdown(f"**Selección:** {texto_provincia} · {anios[0]}-{anios[1]} · {epoca.lower()}")

# ---------- Indicadores ----------
n_anios = anios[1] - anios[0] + 1
cantones_con_obs = int((resumen["observaciones"] > 0).sum())
col1, col2, col3, col4 = st.columns(4)
col1.metric("Observaciones", f"{formato_numero(len(seleccion))} registros")
col2.metric("Cantones con observaciones", f"{cantones_con_obs} de {len(resumen)}")
col3.metric("Observadores", f"{formato_numero(seleccion['observador'].nunique())} personas")
col4.metric("Promedio anual", f"{formato_numero(len(seleccion) / n_anios, 1)} obs/año")

if seleccion.empty:
    st.warning("Ninguna observación cumple los filtros seleccionados. Amplíe el rango de años o cambie la provincia "
               "o la época del año.")
else:
    pestana_tabla, pestana_graficos, pestana_mapa = st.tabs(["📋 Tablas", "📊 Gráficos", "🗺️ Mapa"])

    # ---------- Tablas ----------
    with pestana_tabla:
        st.subheader("Observaciones por cantón")
        tabla_cantones = (resumen[resumen["observaciones"] > 0]
                          .drop(columns="geometry")
                          .sort_values("observaciones", ascending=False)
                          [["provincia", "canton", "observaciones", "area_km2", "densidad"]])
        tabla_cantones["porcentaje"] = tabla_cantones["observaciones"] / len(seleccion) * 100
        st.dataframe(
            tabla_cantones, hide_index=True, width="stretch",
            column_config={
                "provincia": "Provincia", "canton": "Cantón",
                "observaciones": st.column_config.NumberColumn("Observaciones (registros)", format="%d"),
                "porcentaje": st.column_config.NumberColumn("Porcentaje de la selección (%)", format="%.1f"),
                "area_km2": st.column_config.NumberColumn("Área (km²)", format="%.1f"),
                "densidad": st.column_config.NumberColumn("Densidad (obs/100 km²)", format="%.2f"),
            },
        )

        st.subheader("Registros de observación")
        tabla_obs = (seleccion.drop(columns="geometry")
                     .sort_values("fecha", ascending=False)
                     [["fecha", "provincia", "canton", "lugar", "observador", "precision_m", "uri"]])
        st.dataframe(
            tabla_obs, hide_index=True, width="stretch", height=400,
            column_config={
                "fecha": st.column_config.DateColumn("Fecha", format="YYYY-MM-DD"),
                "provincia": "Provincia", "canton": "Cantón", "lugar": "Lugar (iNaturalist)",
                "observador": "Observador",
                "precision_m": st.column_config.NumberColumn("Precisión (m)", format="%.0f"),
                "uri": st.column_config.LinkColumn("Registro", display_text="Ver en iNaturalist"),
            },
        )
        st.download_button("Descargar registros (CSV)", tabla_obs.to_csv(index=False).encode("utf-8"),
                           "observaciones_agalychnis_callidryas.csv", "text/csv")

    # ---------- Gráficos ----------
    with pestana_graficos:
        por_anio = (seleccion.groupby("anio").size()
                    .reindex(range(anios[0], anios[1] + 1), fill_value=0)
                    .rename_axis("anio").reset_index(name="observaciones"))
        grafico_anio = px.bar(
            por_anio, x="anio", y="observaciones",
            title=f"Observaciones por año, {anios[0]}-{anios[1]} ({texto_provincia})",
            labels={"anio": "Año", "observaciones": "Observaciones (registros)"},
            color_discrete_sequence=["#31a354"],
        )
        st.plotly_chart(grafico_anio, width="stretch")

        col_mes, col_canton = st.columns(2)
        with col_mes:
            por_mes = (seleccion.groupby("mes").size().reindex(range(1, 13), fill_value=0)
                       .rename_axis("mes").reset_index(name="observaciones"))
            por_mes["nombre_mes"] = [MESES[m - 1] for m in por_mes["mes"]]
            por_mes["epoca"] = ["Seca" if m in EPOCAS["Época seca (diciembre-abril)"] else "Lluviosa"
                                for m in por_mes["mes"]]
            grafico_mes = px.bar(
                por_mes, x="nombre_mes", y="observaciones", color="epoca",
                title="Estacionalidad: observaciones por mes",
                labels={"nombre_mes": "Mes", "observaciones": "Observaciones (registros)", "epoca": "Época"},
                color_discrete_map={"Seca": "#d8b365", "Lluviosa": "#5ab4ac"},
                category_orders={"nombre_mes": MESES},
            )
            st.plotly_chart(grafico_mes, width="stretch")

        with col_canton:
            top = tabla_cantones.head(15).sort_values("observaciones")
            grafico_canton = px.bar(
                top, x="observaciones", y="canton", orientation="h",
                title=f"Cantones con más observaciones (hasta 15, {texto_provincia})",
                labels={"observaciones": "Observaciones (registros)", "canton": "Cantón", "provincia": "Provincia"},
                hover_data={"provincia": True},
                color_discrete_sequence=["#006837"],
            )
            st.plotly_chart(grafico_canton, width="stretch")

    # ---------- Mapa ----------
    with pestana_mapa:
        st.subheader(f"Observaciones por cantón ({texto_provincia}, {anios[0]}-{anios[1]}, {epoca.lower()})")
        st.caption("Pase el cursor sobre un cantón para ver su conteo y densidad; haga clic en un punto para ver "
                   "el registro. Los cantones en gris no tienen observaciones en la selección.")
        mapa = copy.deepcopy(crear_mapa(provincia, anios, epoca))
        st_folium(mapa, height=600, use_container_width=True, returned_objects=[])

# ---------- Fuentes ----------
st.divider()
st.caption(
    "**Fuentes:** iNaturalist (2026). *Observaciones de* Agalychnis callidryas *en Costa Rica* "
    "[conjunto de datos]. https://www.inaturalist.org/observations?place_id=6924&taxon_id=23702 · "
    "Instituto Geográfico Nacional (2026). *Límites cantonales y provinciales de Costa Rica*, distribuidos en el "
    "[repositorio del curso GF-0657](https://github.com/gf0657-programacionsig/2026-ii/tree/main/datos/ign). "
    "Autor: Jarod Salas Díaz."
)
