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
st.markdown("Cruce de competencia contra tráfico peatonal e instituciones clave.")

# --- 2. FUENTE DE DATOS 1: CAFETERÍAS ---
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

# --- 3. FUENTE DE DATOS 2: TRÁFICO PEATONAL DETALLADO ---
@st.cache_data(ttl=86400)
def obtener_trafico(ciudad):
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
    headers = {'User-Agent': 'ConsultoraCafeB2B/1.1'}
    
    traducciones = {
        'hospital': 'Hospital', 'university': 'Universidad', 'bank': 'Banco',
        'clinic': 'Clínica', 'school': 'Escuela', 'bus_stop': 'Parada de Colectivo'
    }
    
    try:
        res = requests.post(url, data={'data': query}, headers=headers, timeout=100)
        if res.status_code != 200:
            return pd.DataFrame()
        data = res.json()
        puntos = []
        for e in data.get('elements', []):
            if 'lat' in e and 'lon' in e:
                tags = e.get('tags', {})
                tipo_raw = tags.get('amenity', 'bus_stop')
                tipo_es = traducciones.get(tipo_raw, tipo_raw.capitalize())
                
                # Intentamos sacar el nombre exacto de la institución, si no tiene, usamos el tipo
                nombre = tags.get('name', 'Sin nombre registrado')
                
                peso = 3.0 if tipo_raw in ['hospital', 'university'] else 2.0 if tipo_raw in ['bank', 'clinic', 'school'] else 1.0
                
                puntos.append({
                    'lat': e['lat'], 'lon': e['lon'], 'peso': peso,
                    'tipo_es': tipo_es, 'nombre': nombre
                })
        return pd.DataFrame(puntos)
    except:
        return pd.DataFrame()

with st.spinner("Conectando con base de datos privada..."):
    df_cafes = cargar_cafeterias()

# --- 4. PANEL LATERAL: FILTROS Y PEA ---
st.sidebar.subheader("📍 Filtro de Zona")
ciudades_disponibles = ["Seleccionar Ciudad..."] + list(GIDS.keys())
ciudad_seleccionada = st.sidebar.selectbox("Ciudad a analizar", options=ciudades_disponibles)

st.sidebar.markdown("---")
st.sidebar.subheader("🧮 Demanda (PEA)")
poblacion = st.sidebar.number_input("Población de la zona", value=15000, step=1000)
tasa_pea = st.sidebar.slider("% Población Activa (PEA)", 30, 60, 47)
captacion = st.sidebar.slider("% Captación de clientes", 1, 30, 10)

pea_total = int(poblacion * (tasa_pea / 100))
clientes_diarios = int(pea_total * (captacion / 100))

st.sidebar.info(f"☕ **Demanda Estimada:** {clientes_diarios} clientes/día")

# --- 5. RENDERIZADO DEL MAPA ---
if ciudad_seleccionada != "Seleccionar Ciudad...":
    col1, col2 = st.columns([3, 1])
    
    with col2:
        st.subheader("Métricas del Mapa")
        df_cafes_ciudad = df_cafes[df_cafes['ciudad'] == ciudad_seleccionada]
        st.metric("Cafeterías (Competencia)", len(df_cafes_ciudad))
        
        with st.spinner("Descargando tráfico peatonal detallado..."):
            df_trafico_ciudad = obtener_trafico(ciudad_seleccionada)
        st.metric("Nodos de Tráfico", len(df_trafico_ciudad))
        
        st.markdown("### Guía de Capas")
        st.markdown("🔴 **Calor Oferta:** Polos saturados.")
        st.markdown("🔵 **Calor Demanda:** Concentración de paso peatonal.")
        st.markdown("📍 **Detalle de Nodos:** Puntos exactos con el nombre de cada institución (Prender desde el menú del mapa).")

    with col1:
        centro_lat = df_cafes_ciudad['lat'].mean() if not df_cafes_ciudad.empty else -38.0
        centro_lon = df_cafes_ciudad['lon'].mean() if not df_cafes_ciudad.empty else -57.5
        
        mapa = folium.Map(location=[centro_lat, centro_lon], zoom_start=14, tiles="CartoDB dark_matter")
        
        if not df_trafico_ciudad.empty:
            # Capa 1: Calor del tráfico (Mancha)
            capa_calor_trafico = folium.FeatureGroup(name="🚶‍♂️ Densidad Peatonal (Calor)")
            HeatMap(
                df_trafico_ciudad[['lat', 'lon', 'peso']].values.tolist(),
                radius=15, blur=15, min_opacity=0.4,
                gradient={0.4: 'navy', 0.6: 'blue', 1: 'cyan'} 
            ).add_to(capa_calor_trafico)
            capa_calor_trafico.add_to(mapa)
            
            # Capa 2: Puntos exactos del tráfico con Popups (Nodos)
            capa_nodos = folium.FeatureGroup(name="📍 Detalle de Instituciones", show=False)
            for _, row in df_trafico_ciudad.iterrows():
                tooltip_text = f"<b>{row['tipo_es']}</b><br>{row['nombre']}"
                folium.CircleMarker(
                    location=[row['lat'], row['lon']],
                    radius=4,
                    color='cyan',
                    fill=True,
                    fill_opacity=0.7,
                    tooltip=tooltip_text
                ).add_to(capa_nodos)
            capa_nodos.add_to(mapa)
            
        if not df_cafes_ciudad.empty:
            # Capa 3: Calor de Cafeterías
            capa_cafes = folium.FeatureGroup(name="☕ Cafeterías (Oferta)")
            HeatMap(
                df_cafes_ciudad[['lat', 'lon']].values.tolist(),
                radius=20, blur=15, min_opacity=0.5,
                gradient={0.4: 'orange', 0.6: 'red', 1: 'darkred'} 
            ).add_to(capa_cafes)
            capa_cafes.add_to(mapa)
            
        folium.LayerControl(collapsed=False).add_to(mapa)
        
        st_folium(mapa, width=800, height=600, returned_objects=[])

else:
    st.info("👈 Seleccioná una ciudad en el menú lateral para iniciar el análisis.")
