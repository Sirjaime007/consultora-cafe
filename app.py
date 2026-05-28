import streamlit as st
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
import requests

# --- 1. CONFIGURACIÓN Y SEGURIDAD ---
st.set_page_config(page_title="Consultora Café B2B", layout="wide")
st.sidebar.title("🔐 Acceso Privado")
password = st.sidebar.text_input("Contraseña", type="password")

if password != "AdminCafe2026": 
    st.warning("✋ Ingresá la contraseña para acceder al panel de inteligencia.")
    st.stop()

st.title("🔥 Inteligencia B2B: Oferta vs Demanda")
st.markdown("Cruce de competencia (tu base de datos) contra tráfico peatonal y análisis demográfico (PEA).")

# --- 2. FUENTE DE DATOS 1: CAFETERÍAS (Tu Google Sheet) ---
SHEET_ID = "10vUOhRr7IAXlRrkBphxEP4ApXYBgrnuxJq6G83GnfHI"
GIDS = {
    "Mar del Plata": "0", "Buenos Aires": "1296176686", "La Plata": "208452991",
    "Córdoba": "1250014567", "Rosario": "1691979590", "Mendoza": "2031963266", "Bahía Blanca": "1634818534"
}

@st.cache_data(ttl=3600)
def cargar_cafeterias():
    locales = []
    for ciudad, gid in GIDS.items():
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&gid={gid}"
        try:
            df = pd.read_csv(url)
            df.columns = [str(c).upper().strip() for c in df.columns]
            lat_col = next((col for col in df.columns if col in ['LAT', 'LATITUD']), None)
            lon_col = next((col for col in df.columns if col in ['LONG', 'LONGITUD', 'LNG']), None)
            
            if lat_col and lon_col:
                df[lat_col] = df[lat_col].astype(str).str.replace(',', '.')
                df[lon_col] = df[lon_col].astype(str).str.replace(',', '.')
                df['LAT_CLEAN'] = pd.to_numeric(df[lat_col], errors='coerce')
                df['LON_CLEAN'] = pd.to_numeric(df[lon_col], errors='coerce')
                df_valid = df.dropna(subset=['LAT_CLEAN', 'LON_CLEAN'])
                for _, row in df_valid.iterrows():
                    locales.append({'ciudad': ciudad, 'lat': row['LAT_CLEAN'], 'lon': row['LON_CLEAN']})
        except Exception:
            pass
    return pd.DataFrame(locales)

# --- 3. FUENTE DE DATOS 2: TRÁFICO PEATONAL (Overpass API) ---
@st.cache_data(ttl=86400)
def obtener_trafico(ciudad):
    # Ajustamos el nombre para que OpenStreetMap lo entienda perfecto
    ciudad_query = "Ciudad Autónoma de Buenos Aires" if ciudad == "Buenos Aires" else ciudad
    
    query = f"""
    [out:json][timeout:90];
    area["name"="{ciudad_query}"]->.searchArea;
    (
      node["amenity"~"bank|hospital|clinic|school|university"](area.searchArea);
      node["highway"="bus_stop"](area.searchArea);
    );
    out center;
    """
    url = "http://overpass-api.de/api/interpreter"
    headers = {'User-Agent': 'ConsultoraCafeB2B/1.0'}
    
    try:
        res = requests.post(url, data={'data': query}, headers=headers, timeout=100)
        if res.status_code != 200:
            return pd.DataFrame()
        data = res.json()
        puntos = []
        for e in data.get('elements', []):
            if 'lat' in e and 'lon' in e:
                tipo = e.get('tags', {}).get('amenity', 'bus_stop')
                peso = 3.0 if tipo in ['hospital', 'university'] else 2.0 if tipo in ['bank', 'clinic', 'school'] else 1.0
                puntos.append({'lat': e['lat'], 'lon': e['lon'], 'peso': peso})
        return pd.DataFrame(puntos)
    except:
        return pd.DataFrame()

# Carga base de cafés
with st.spinner("Conectando con base de datos privada..."):
    df_cafes = cargar_cafeterias()

# --- 4. PANEL LATERAL: FILTROS Y PEA ---
st.sidebar.subheader("📍 Filtro de Zona")
ciudades_disponibles = ["Seleccionar Ciudad..."] + list(GIDS.keys())
ciudad_seleccionada = st.sidebar.selectbox("Ciudad a analizar", options=ciudades_disponibles)

st.sidebar.markdown("---")
st.sidebar.subheader("🧮 Calculadora de PEA por Barrio")
st.sidebar.caption("Ingresá los datos demográficos del barrio objetivo para estimar la demanda de tazas diarias.")
poblacion = st.sidebar.number_input("Población del Barrio/Radio", value=15000, step=1000)
tasa_pea = st.sidebar.slider("% de Población Activa (PEA)", 30, 60, 47, help="Promedio INDEC es ~47%")
captacion = st.sidebar.slider("% de Captación de clientes", 1, 30, 10, help="Porcentaje del mercado que te va a comprar")

# Cálculo
pea_total = int(poblacion * (tasa_pea / 100))
clientes_potenciales = int(pea_total * (captacion / 100))

st.sidebar.info(f"👥 **PEA del barrio:** {pea_total} personas\n\n☕ **Demanda Estimada:** {clientes_potenciales} clientes/día")

# --- 5. RENDERIZADO DEL MAPA DE CAPAS ---
if ciudad_seleccionada != "Seleccionar Ciudad...":
    col1, col2 = st.columns([3, 1])
    
    with col2:
        st.subheader("Métricas de la Zona")
        df_cafes_ciudad = df_cafes[df_cafes['ciudad'] == ciudad_seleccionada]
        st.metric("Cafeterías Existentes", len(df_cafes_ciudad))
        
        with st.spinner("Descargando tráfico peatonal (puede demorar un poco)..."):
            df_trafico_ciudad = obtener_trafico(ciudad_seleccionada)
        st.metric("Puntos de Tráfico Peatonal", len(df_trafico_ciudad))
        
        st.markdown("### Guía de Colores")
        st.markdown("🔴 **Rojo/Naranja:** Mucha competencia.")
        st.markdown("🔵 **Azul/Celeste:** Mucho movimiento de gente (Bancos, Hospitales, Escuelas).")
        st.markdown("💡 **Oportunidad:** Zonas muy azules donde no haya manchas rojas cerca.")

    with col1:
        centro_lat = df_cafes_ciudad['lat'].mean() if not df_cafes_ciudad.empty else -34.6
        centro_lon = df_cafes_ciudad['lon'].mean() if not df_cafes_ciudad.empty else -58.4
        
        # Mapa base oscuro
        mapa = folium.Map(location=[centro_lat, centro_lon], zoom_start=13, tiles="CartoDB dark_matter")
        
        # CAPA 1: Tráfico Peatonal (Manchas azules)
        if not df_trafico_ciudad.empty:
            capa_trafico = folium.FeatureGroup(name="🚶‍♂️ Tráfico Peatonal (Demanda)")
            HeatMap(
                df_trafico_ciudad[['lat', 'lon', 'peso']].values.tolist(),
                radius=15, blur=15, min_opacity=0.4,
                gradient={0.4: 'navy', 0.6: 'blue', 1: 'cyan'} # Tonos fríos para el tráfico
            ).add_to(capa_trafico)
            capa_trafico.add_to(mapa)
            
        # CAPA 2: Cafeterías Existentes (Manchas rojas)
        if not df_cafes_ciudad.empty:
            capa_cafes = folium.FeatureGroup(name="☕ Cafeterías (Oferta)")
            HeatMap(
                df_cafes_ciudad[['lat', 'lon']].values.tolist(),
                radius=20, blur=15, min_opacity=0.5,
                gradient={0.4: 'orange', 0.6: 'red', 1: 'darkred'} # Tonos cálidos para competencia
            ).add_to(capa_cafes)
            capa_cafes.add_to(mapa)
            
        # Control para prender y apagar capas
        folium.LayerControl(collapsed=False).add_to(mapa)
        
        st_folium(mapa, width=800, height=600, returned_objects=[])

else:
    st.info("👈 Seleccioná una ciudad en el menú lateral para iniciar el análisis B2B.")
