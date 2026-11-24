# Proyecto final GF-0657 Programación en SIG (II ciclo 2026)
# Observaciones de la rana de árbol de ojos rojos (Agalychnis callidryas) en Costa Rica (iNaturalist)
# Autor: Jarod Salas
# Ejecución: streamlit run app.py
import copy

import folium
import geopandas as gpd
import pandas as pd
import plotly.express as px
import streamlit as st
from branca.element import MacroElement, Template
from streamlit_folium import st_folium

# ---------- Configuración de la página (primera llamada a streamlit) ----------
st.set_page_config(page_title="Rana de Árbol de Ojos Rojos en Costa Rica", layout="wide")

# ---------- Constantes ----------
URL_OBSERVACIONES = (
    "https://raw.githubusercontent.com/jasalas2/tarea2_psig/main/"
    "agalychnis_callidryas_costa_rica_inaturalist.csv"
)
URL_IGN = "https://raw.githubusercontent.com/gf0657-programacionsig/2026-ii/main/datos/ign"
URL_ESPECIE = "https://www.inaturalist.org/taxa/23702"
# Foto de portada: observación de iNaturalist con licencia CC0 (dominio público)
FOTO_PORTADA = "https://static.inaturalist.org/photos/173688685/large.jpg"
CREDITO_PORTADA = ("Foto: Mason Maron (kiwikiu), Alajuela, diciembre de 2021. iNaturalist, CC0. "
                   "[Ver observación](https://www.inaturalist.org/observations/103735520)")
SRC_CRTM05 = 8908  # proyectado, en metros: uniones espaciales y áreas
SRC_WGS84 = 4326   # geográfico: el que usan los mapas web

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
EPOCAS = {
    "Todo el año": list(range(1, 13)),
    "Época seca (diciembre-abril)": [12, 1, 2, 3, 4],
    "Época lluviosa (mayo-noviembre)": [5, 6, 7, 8, 9, 10, 11],
}
HORAS_NOCHE = list(range(18, 24)) + list(range(0, 6))  # de 6:00 p.m. a 5:59 a.m.

# Colores de la aplicación: verde de la piel y rojo de los ojos de la rana
VERDE, VERDE_OSCURO, ROJO, NARANJA, AZUL_NOCHE = "#3a9b3a", "#1f5f2a", "#d7301f", "#f28c28", "#2c3e70"

# Clases fijas del mapa de coropletas: se mantienen iguales con cualquier filtro,
# de modo que los colores de dos selecciones distintas se pueden comparar
CORTES = [1, 11, 51, 201, 501]
COLORES = ["#ffffcc", "#c2e699", "#78c679", "#31a354", "#006837"]
COLOR_SIN_DATOS = "#e0e0e0"
ETIQUETAS_CLASES = ["1-10", "11-50", "51-200", "201-500", "Más de 500"]

LICENCIAS = {"cc0": "CC0", "cc-by": "CC BY", "cc-by-nc": "CC BY-NC", "cc-by-sa": "CC BY-SA",
             "cc-by-nc-sa": "CC BY-NC-SA", "cc-by-nd": "CC BY-ND", "cc-by-nc-nd": "CC BY-NC-ND"}


def color_clase(n):
    """Color de la clase a la que pertenece un número de observaciones."""
    if n <= 0:
        return COLOR_SIN_DATOS
    return COLORES[sum(n >= corte for corte in CORTES) - 1]


def leyenda_html():
    """Leyenda del mapa de coropletas como control de Leaflet: una fila por clase, con título y unidades."""
    cuadro = ('display:inline-block;width:14px;height:14px;margin-right:6px;'
              'vertical-align:middle;border:1px solid #999;background:')
    filas = "".join(
        f'<div><span style="{cuadro}{color};"></span>{etiqueta}</div>'
        for color, etiqueta in zip(COLORES + [COLOR_SIN_DATOS], ETIQUETAS_CLASES + ["Sin observaciones"])
    )
    contenido = ("<b>Observaciones por cantón</b><br><i>(número de registros)</i>" + filas).replace("'", "&#39;")
    plantilla = """
    {% macro script(this, kwargs) %}
    var leyenda = L.control({position: "bottomright"});
    leyenda.onAdd = function () {
        var div = L.DomUtil.create("div");
        div.style.cssText = "background:white;padding:8px 10px;border-radius:4px;"
            + "box-shadow:0 0 4px rgba(0,0,0,0.3);font:12px sans-serif;color:#333;line-height:18px;";
        div.innerHTML = 'CONTENIDO';
        return div;
    };
    leyenda.addTo({{ this._parent.get_name() }});
    {% endmacro %}
    """.replace("CONTENIDO", contenido)
    leyenda = MacroElement()
    leyenda._template = Template(plantilla)
    return leyenda


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
    # Hora local de la observación (iNaturalist la guarda con distintos husos horarios)
    hora = pd.to_datetime(obs["time_observed_at"], errors="coerce", utc=True).dt.tz_convert("America/Costa_Rica")
    obs["hora"] = hora.dt.hour.astype("Int64")
    # Fotos: la versión mediana para la galería y la pequeña para el mapa
    obs["foto"] = obs["photo_url"].str.replace("/square.", "/medium.", regex=False)
    obs["foto_mini"] = obs["photo_url"].str.replace("/square.", "/small.", regex=False)
    obs["licencia"] = obs["license_code"].map(LICENCIAS)

    puntos = gpd.GeoDataFrame(
        obs[["id", "fecha", "anio", "mes", "hora", "place_guess", "user_login", "positional_accuracy", "uri",
             "foto", "foto_mini", "licencia", "num_identification_agreements"]],
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
                                    "positional_accuracy": "precision_m",
                                    "num_identification_agreements": "confirmaciones"})
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


def formato_numero(valor, decimales=0):
    """Número con espacio como separador de miles."""
    return f"{valor:,.{decimales}f}".replace(",", " ")


def datos_curiosos(seleccion, resumen):
    """Cuatro hallazgos de la selección, como (cifra, texto)."""
    datos = []
    con_hora = seleccion.dropna(subset=["hora"])
    if len(con_hora):
        noche = con_hora["hora"].isin(HORAS_NOCHE).mean() * 100
        hora_pico = int(con_hora["hora"].mode().iloc[0])
        datos.append((f"{noche:.0f} %",
                      f"de las observaciones se hicieron de noche (6 p.m.-6 a.m.): es una especie nocturna. "
                      f"Hora más frecuente: {hora_pico % 12 or 12}:00 {'p.m.' if hora_pico >= 12 else 'a.m.'}"))

    por_anio = seleccion.groupby("anio").size()
    anio_record, n_record = int(por_anio.idxmax()), int(por_anio.max())
    acumulado = por_anio[por_anio.index < anio_record].cumsum()
    previos = acumulado[acumulado < n_record]
    if len(previos) >= 3:
        texto = (f"registros en {anio_record}: más que en todos los años de {int(previos.index[0])} a "
                 f"{int(previos.index[-1])} juntos ({formato_numero(int(previos.iloc[-1]))}).")
    else:
        texto = f"registros en {anio_record}, el año con más observaciones de la selección."
    datos.append((formato_numero(n_record), texto))

    top = resumen.sort_values("observaciones", ascending=False)
    top2 = top.head(2)
    sin_obs = int((resumen["observaciones"] == 0).sum())
    if len(top2) == 2 and top2["observaciones"].iloc[1] > 0:
        cuota = top2["observaciones"].sum() / len(seleccion) * 100
        datos.append((f"{cuota:.0f} %",
                      f"de los registros están en solo 2 cantones: {top2['canton'].iloc[0]} y "
                      f"{top2['canton'].iloc[1]}. En cambio, {sin_obs} de {len(resumen)} cantones no tienen ninguno."))
    else:
        datos.append((f"{sin_obs} de {len(resumen)}", "cantones de la selección no tienen ningún registro."))

    por_persona = seleccion["observador"].value_counts()
    una_vez = (por_persona == 1).mean() * 100
    datos.append((f"{una_vez:.0f} %",
                  f"de las {formato_numero(len(por_persona))} personas que la observaron la registraron una sola "
                  f"vez: la mayoría de los datos los aportan visitantes ocasionales."))
    return datos


# ---------- Mapa, en caché por combinación de filtros ----------
def vista_inicial(provincia):
    """Centro y zoom del mapa: el territorio continental o la provincia elegida."""
    if provincia == "Todas":
        return [9.65, -84.2], 8
    oeste, sur, este, norte = cargar_provincias().query("provincia == @provincia").total_bounds
    return [(sur + norte) / 2, (oeste + este) / 2], 9


@st.cache_resource
def crear_mapa(provincia, anios, epoca):
    """Mapa web: coropletas por cantón, provincias de referencia y puntos de observación (WGS84)."""
    seleccion = filtrar(provincia, anios, epoca)
    capa = resumir_cantones(seleccion, provincia)
    provincias = cargar_provincias()

    centro, zoom = vista_inicial(provincia)
    mapa = folium.Map(location=centro, zoom_start=zoom, tiles=None, control_scale=True)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(mapa)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri, Maxar, Earthstar Geographics", name="Esri satelital", show=False,
    ).add_to(mapa)

    # Capa 1: coropletas del número de observaciones por cantón
    def estilo(feature):
        n = feature["properties"]["observaciones"]
        return {"fillColor": color_clase(n), "color": "white", "weight": 0.6, "fillOpacity": 0.75}

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
    mapa.add_child(leyenda_html())

    # Capa 2: provincias (referencia)
    folium.GeoJson(
        provincias[["provincia", "geometry"]], name="Provincias",
        style_function=lambda f: {"fill": False, "color": "#444444", "weight": 1.5},
        tooltip=folium.GeoJsonTooltip(fields=["provincia"], aliases=["Provincia:"]),
    ).add_to(mapa)

    # Capa 3: puntos, en un panel propio para que queden siempre encima de los polígonos.
    # La ventana emergente muestra la foto de la observación y un enlace al registro.
    folium.map.CustomPane("puntos", z_index=650).add_to(mapa)
    marcador = folium.CircleMarker(radius=3, color="#7f0000", weight=0.5,
                                   fill=True, fill_color=ROJO, fill_opacity=0.85)
    marcador.options["pane"] = "puntos"
    puntos = seleccion.assign(
        fecha_texto=seleccion["fecha"].dt.strftime("%Y-%m-%d"),
        imagen=('<img src="' + seleccion["foto_mini"].fillna("") + '" width="180">').where(
            seleccion["foto_mini"].notna(), "Sin foto"),
        enlace='<a href="' + seleccion["uri"] + '" target="_blank">Ver en iNaturalist</a>',
    )
    folium.GeoJson(
        puntos[["imagen", "fecha_texto", "lugar", "canton", "observador", "enlace", "geometry"]],
        name="Observaciones (iNaturalist)",
        marker=marcador,
        tooltip=folium.GeoJsonTooltip(fields=["canton", "fecha_texto"], aliases=["Cantón:", "Fecha:"]),
        popup=folium.GeoJsonPopup(
            fields=["imagen", "fecha_texto", "lugar", "canton", "observador", "enlace"],
            aliases=["", "Fecha:", "Lugar:", "Cantón:", "Observador:", "Registro:"],
            max_width=260,
        ),
    ).add_to(mapa)

    folium.LayerControl(collapsed=True).add_to(mapa)
    return mapa


# ---------- Carga inicial ----------
observaciones = cargar_observaciones()
anio_min, anio_max = int(observaciones["anio"].min()), int(observaciones["anio"].max())

# ---------- Controles ----------
st.sidebar.title("Filtros")
provincia = st.sidebar.selectbox("Provincia", ["Todas"] + sorted(observaciones["provincia"].unique()))
anios = st.sidebar.slider("Años de observación", anio_min, anio_max, (anio_min, anio_max))
epoca = st.sidebar.radio("Época del año", list(EPOCAS))
st.sidebar.caption("Todos los indicadores, datos curiosos, tablas, gráficos, fotos y el mapa responden a estos filtros.")

seleccion = filtrar(provincia, anios, epoca)
resumen = resumir_cantones(seleccion, provincia)
texto_provincia = "todas las provincias" if provincia == "Todas" else f"provincia de {provincia}"

# ---------- Encabezado ----------
st.title(f"[Rana de Árbol de Ojos Rojos]({URL_ESPECIE})")
st.markdown("##### *Agalychnis callidryas* · dónde y cuándo se observa en Costa Rica, según la ciencia ciudadana")

col_intro, col_foto, col_ficha = st.columns([5, 4, 4], gap="medium")
with col_intro:
    st.markdown(
        "Esta aplicación explora las observaciones de la rana de árbol de ojos rojos registradas por miles de "
        "personas en **iNaturalist** entre 2000 y 2026. Solo se usan registros con grado de investigación, "
        "coordenadas no oscurecidas y una precisión de 1 km o mejor. Cada observación se asignó a su cantón "
        "mediante una unión espacial con los límites del **Instituto Geográfico Nacional (IGN)**.\n\n"
        "**Cómo se usa:** elija una provincia, un rango de años y una época del año en la barra lateral. "
        "Las cifras, los datos curiosos, los gráficos, el mapa, las fotos y las tablas se actualizan con la selección."
    )
    st.markdown(f"**Selección:** {texto_provincia} · {anios[0]}-{anios[1]} · {epoca.lower()}")
with col_foto:
    st.image(FOTO_PORTADA, width="stretch")
    st.caption(CREDITO_PORTADA)
with col_ficha:
    with st.container(border=True):
        st.markdown(
            "**Ficha de la especie**\n\n"
            "- Mide de 4 a 7 cm; las hembras son más grandes que los machos.\n"
            "- Vive en los árboles de los bosques húmedos de tierras bajas y es activa de noche.\n"
            "- Pone los huevos en hojas sobre charcas; al nacer, los renacuajos caen al agua.\n"
            "- **Dato sorprendente:** si una serpiente ataca la nidada, los embriones detectan la vibración y "
            "pueden eclosionar antes de tiempo, desde el cuarto día, para escapar al agua.\n\n"
            "<small>Fuentes: [Animal Diversity Web](https://animaldiversity.org/accounts/Agalychnis_callidryas/); "
            "[The Embryo Project, ASU](https://embryo.asu.edu/pages/how-do-embryos-assess-risk-vibrational-cues-"
            "predator-induced-hatching-red-eyed-treefrogs-2005).</small>",
            unsafe_allow_html=True,
        )

# ---------- Indicadores ----------
n_anios = anios[1] - anios[0] + 1
cantones_con_obs = int((resumen["observaciones"] > 0).sum())
col1, col2, col3, col4 = st.columns(4)
col1.metric("Observaciones (registros)", formato_numero(len(seleccion)), border=True)
col2.metric("Cantones con observaciones", f"{cantones_con_obs} de {len(resumen)}", border=True)
col3.metric("Observadores (personas)", formato_numero(seleccion["observador"].nunique()), border=True)
col4.metric("Promedio anual (obs/año)", formato_numero(len(seleccion) / n_anios, 1), border=True)

if seleccion.empty:
    st.warning("Ninguna observación cumple los filtros seleccionados. Amplíe el rango de años o cambie la provincia "
               "o la época del año.")
else:
    # ---------- Datos curiosos ----------
    st.subheader("¿Sabía que…?")
    for columna, (cifra, texto) in zip(st.columns(4), datos_curiosos(seleccion, resumen)):
        with columna.container(border=True, height="stretch"):
            st.markdown(f"<div style='font-size:2rem;line-height:1.1;color:#1f5f2a'><b>{cifra}</b></div>"
                        f"<div style='margin-top:0.4rem'>{texto}</div>", unsafe_allow_html=True)

    tabla_cantones = (resumen[resumen["observaciones"] > 0]
                      .drop(columns="geometry")
                      .sort_values("observaciones", ascending=False)
                      [["provincia", "canton", "observaciones", "area_km2", "densidad"]])
    tabla_cantones["porcentaje"] = tabla_cantones["observaciones"] / len(seleccion) * 100

    pestana_mapa, pestana_graficos, pestana_fotos, pestana_tabla = st.tabs(
        ["Mapa", "Gráficos", "Galería", "Tablas"])

    # ---------- Mapa ----------
    with pestana_mapa:
        st.subheader(f"Observaciones por cantón ({texto_provincia}, {anios[0]}-{anios[1]}, {epoca.lower()})")
        st.caption("Pase el cursor sobre un cantón para ver su conteo y densidad; haga clic en un punto para ver la "
                   "foto y el registro. Los cantones en gris no tienen observaciones en la selección.")
        mapa = copy.deepcopy(crear_mapa(provincia, anios, epoca))
        # center y zoom se pasan también a st_folium, porque el mapa se crea dentro de una pestaña
        centro, zoom = vista_inicial(provincia)
        st_folium(mapa, height=620, use_container_width=True, center=centro, zoom=zoom, returned_objects=[])

    # ---------- Gráficos ----------
    with pestana_graficos:
        por_anio = (seleccion.groupby("anio").size()
                    .reindex(range(anios[0], anios[1] + 1), fill_value=0)
                    .rename_axis("anio").reset_index(name="observaciones"))
        grafico_anio = px.bar(
            por_anio, x="anio", y="observaciones",
            title=f"El auge de la ciencia ciudadana: observaciones por año, {anios[0]}-{anios[1]} ({texto_provincia})",
            labels={"anio": "Año", "observaciones": "Observaciones (registros)"},
            color_discrete_sequence=[VERDE],
        )
        st.plotly_chart(grafico_anio, width="stretch")

        col_reloj, col_mes = st.columns(2)
        with col_reloj:
            por_hora = (seleccion.dropna(subset=["hora"]).groupby("hora").size()
                        .reindex(range(24), fill_value=0).rename_axis("hora").reset_index(name="observaciones"))
            por_hora["hora_texto"] = [f"{h}:00" for h in por_hora["hora"]]
            por_hora["periodo"] = ["Noche" if h in HORAS_NOCHE else "Día" for h in por_hora["hora"]]
            grafico_reloj = px.bar_polar(
                por_hora, r="observaciones", theta="hora_texto", color="periodo",
                title="El reloj de la rana: observaciones por hora del día (registros)",
                labels={"observaciones": "Observaciones (registros)", "hora_texto": "Hora", "periodo": "Periodo"},
                color_discrete_map={"Noche": AZUL_NOCHE, "Día": NARANJA},
                category_orders={"hora_texto": list(por_hora["hora_texto"])},
            )
            grafico_reloj.update_layout(polar={"angularaxis": {"direction": "clockwise", "rotation": 90},
                                                "radialaxis": {"showticklabels": False}})
            st.plotly_chart(grafico_reloj, width="stretch")

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

        col_sol, col_canton = st.columns(2)
        with col_sol:
            grafico_sol = px.sunburst(
                tabla_cantones, path=["provincia", "canton"], values="observaciones",
                title="De la provincia al cantón: reparto de las observaciones (registros)",
                color="provincia", color_discrete_sequence=px.colors.qualitative.Safe,
            )
            grafico_sol.update_traces(hovertemplate="<b>%{label}</b><br>Observaciones: %{value} registros"
                                                    "<br>%{percentRoot:.1%} del total<extra></extra>")
            st.plotly_chart(grafico_sol, width="stretch")

        with col_canton:
            top = tabla_cantones.head(15).sort_values("observaciones")
            grafico_canton = px.bar(
                top, x="observaciones", y="canton", orientation="h",
                title=f"Los 15 cantones con más observaciones ({texto_provincia})",
                labels={"observaciones": "Observaciones (registros)", "canton": "Cantón", "provincia": "Provincia"},
                hover_data={"provincia": True},
                color_discrete_sequence=[VERDE_OSCURO],
            )
            st.plotly_chart(grafico_canton, width="stretch")

    # ---------- Galería ----------
    with pestana_fotos:
        st.subheader("Las observaciones más recientes de la selección")
        st.caption("Fotos de las observaciones con licencia Creative Commons; cada foto enlaza a su registro en "
                   "iNaturalist. Los derechos son de cada observador.")
        fotos = (seleccion.dropna(subset=["foto", "licencia"])
                 .sort_values("fecha", ascending=False).head(12))
        if fotos.empty:
            st.info("La selección no tiene fotos con licencia Creative Commons.")
        for inicio in range(0, len(fotos), 4):
            for columna, (_, fila) in zip(st.columns(4), fotos.iloc[inicio:inicio + 4].iterrows()):
                columna.markdown(
                    f"<a href='{fila['uri']}' target='_blank'><img src='{fila['foto']}' "
                    f"style='width:100%;height:220px;object-fit:cover;border-radius:8px'></a>"
                    f"<div style='font-size:0.8rem;margin:0.3rem 0 1rem'><b>{fila['canton']}</b>, "
                    f"{fila['fecha']:%Y-%m-%d}<br>© {fila['observador']} ({fila['licencia']})</div>",
                    unsafe_allow_html=True,
                )

    # ---------- Tablas ----------
    with pestana_tabla:
        st.subheader("Observaciones por cantón")
        st.dataframe(
            tabla_cantones, hide_index=True, width="stretch",
            column_config={
                "provincia": "Provincia", "canton": "Cantón",
                "observaciones": st.column_config.ProgressColumn(
                    "Observaciones (registros)", format="%d", min_value=0,
                    max_value=int(tabla_cantones["observaciones"].max())),
                "porcentaje": st.column_config.NumberColumn("Porcentaje de la selección (%)", format="%.1f"),
                "area_km2": st.column_config.NumberColumn("Área (km²)", format="%.1f"),
                "densidad": st.column_config.NumberColumn("Densidad (obs/100 km²)", format="%.2f"),
            },
        )

        st.subheader("Registros de observación")
        tabla_obs = (seleccion.drop(columns="geometry")
                     .sort_values("fecha", ascending=False)
                     [["foto_mini", "fecha", "provincia", "canton", "lugar", "observador", "precision_m", "uri"]])
        st.dataframe(
            tabla_obs, hide_index=True, width="stretch", height=420,
            column_config={
                "foto_mini": st.column_config.ImageColumn("Foto"),
                "fecha": st.column_config.DateColumn("Fecha", format="YYYY-MM-DD"),
                "provincia": "Provincia", "canton": "Cantón", "lugar": "Lugar (iNaturalist)",
                "observador": "Observador",
                "precision_m": st.column_config.NumberColumn("Precisión (m)", format="%.0f"),
                "uri": st.column_config.LinkColumn("Registro", display_text="Ver en iNaturalist"),
            },
        )
        st.download_button("Descargar registros (CSV)",
                           tabla_obs.drop(columns="foto_mini").to_csv(index=False).encode("utf-8"),
                           "observaciones_agalychnis_callidryas.csv", "text/csv")

# ---------- Fuentes ----------
st.divider()
st.caption(
    "**Fuentes:** iNaturalist (2026). *Observaciones de* Agalychnis callidryas *en Costa Rica* "
    "[conjunto de datos]. https://www.inaturalist.org/observations?place_id=6924&taxon_id=23702 · "
    "Instituto Geográfico Nacional (2026). *Límites cantonales y provinciales de Costa Rica*, distribuidos en el "
    "[repositorio del curso GF-0657](https://github.com/gf0657-programacionsig/2026-ii/tree/main/datos/ign). "
    "Las fotos pertenecen a sus observadores y se muestran según su licencia Creative Commons. "
    "Autor: Jarod Salas Díaz."
)
