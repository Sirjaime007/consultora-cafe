import streamlit as st
import pandas as pd
import folium
from folium.plugins import HeatMap
import streamlit.components.v1 as components
import requests

# --- 1. CONFIGURACIÓN Y SEGURIDAD ---
st.set_page_config(page_title="Consultora Café B2B", layout="wide")
st.sidebar.title("🔐 Acceso Privado")
password = st.sidebar.text_input("Contraseña", type="password")

if password != "AdminCafe2026": 
    st.warning("✋ Ingresá la contraseña para acceder al panel de inteligencia.")
    st.stop()

st.title("🔥 Inteligencia B2B: Oferta vs Demanda")
st.markdown("Cruce de competencia contra tráfico peatonal, polos comerciales e instituciones clave.")

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
            nombre_col = next((col for col in df.columns if col in ['CAFE', 'NOMBRE', 'LOCAL']), None)
            
            if lat_col and lon_col:
                df[lat_col] = df[lat_col].astype(str).str.replace(',', '.')
                df[lon_col] = df[lon_col].astype(str).str.replace(',', '.')
                df['LAT_CLEAN'] = pd.to_numeric(df[lat_col], errors='coerce')
                df['LON_CLEAN'] = pd.to_numeric(df[lon_col], errors='coerce')
                df_valid = df.dropna(subset=['LAT_CLEAN', 'LON_CLEAN'])
                
                for _, row in df_valid.iterrows():
                    nombre_cafe = row[nombre_col] if nombre_col and pd.notna(row[nombre_col]) else "Café"
                    locales.append({
                        'ciudad': ciudad, 
                        'lat': row['LAT_CLEAN'], 
                        'lon': row['LON_CLEAN'],
                        'nombre': nombre_cafe
                    })
        except Exception:
            pass
    return pd.DataFrame(locales)

# --- 3. FUENTE DE DATOS 2: TRÁFICO Y MEDIOS DE TRANSPORTE (AHORA POR BARRIO) ---
@st.cache_data(ttl=86400)
def obtener_trafico(ciudad, barrio=None):
    # Lógica inteligente para subdividir CABA
    if ciudad == "Buenos Aires":
        if barrio and barrio != "Todo CABA (Lento)":
            # Le decimos a la API que busque el barrio DENTRO de CABA para no confundirse con otras ciudades
            area_query = f'''
            area["name"="Ciudad Autónoma de Buenos Aires"]->.caba;
            area(area.caba)["name"="{barrio}"]->.searchArea;
            '''
        else:
            area_query = 'area["name"="Ciudad Autónoma de Buenos Aires"]->.searchArea;'
    else:
        area_query = f'area["name"="{ciudad}"]->.searchArea;'
        
    query = f"""
    [out:json][timeout:180];
    {area_query}
    (
      nwr["amenity"~"bank|hospital|clinic|school|university|restaurant|bar|fast_food"](area.searchArea);
      nwr["shop"~"supermarket|mall|department_store|clothes|bakery|convenience"](area.searchArea);
      nwr["tourism"~"hotel|museum"](area.searchArea);
      nwr["railway"~"station|subway_entrance"](area.searchArea);
      node["highway"="bus_stop"](area.searchArea);
    );
    out center;
    """
    url = "http://overpass-api.de/api/interpreter"
    headers = {'User-Agent': 'ConsultoraCafeB2B/4.0'}
    
    traducciones = {
        'hospital': 'Hospital', 'university': 'Universidad', 'bank': 'Banco',
        'clinic': 'Clínica', 'school': 'Escuela', 'bus_stop': 'Parada de Colectivo',
        'restaurant': 'Restaurante', 'bar': 'Bar/Cervecería', 'fast_food': 'Comida Rápida',
        'hotel': 'Hotel', 'marketplace': 'Mercado/Feria', 
        'station': 'Estación (Tren/Subte)', 'subway_entrance': 'Boca de Subte'
    }
    
    try:
        res = requests.post(url, data={'data': query}, headers=headers, timeout=180)
        if res.status_code != 200:
            return pd.DataFrame()
        data = res.json()
        puntos = []
        for e in data.get('elements', []):
            lat = e.get('lat') or e.get('center', {}).get('lat')
            lon = e.get('lon') or e.get('center', {}).get('lon')
            
            if lat and lon:
                tags = e.get('tags', {})
                if 'shop' in tags:
                    tipo_raw = 'shop'
                    tipo_es = f"Comercio ({tags['shop'].capitalize()})"
                elif 'railway' in tags:
                    tipo_raw = tags['railway']
                    tipo_es = traducciones.get(tipo_raw, 'Estación Ferroviaria')
                elif 'tourism' in tags:
                    tipo_raw = tags['tourism']
                    tipo_es = traducciones.get(tipo_raw, tipo_raw.capitalize())
                else:
                    tipo_raw = tags.get('amenity', 'bus_stop')
                    if tipo_raw == 'bus_stop':
                        tipo_raw = tags.get('highway', 'bus_stop')
                    tipo_es = traducciones.get(tipo_raw, tipo_raw.capitalize())
                
                nombre = tags.get('name', 'Sin nombre')
                
                if tipo_raw in ['hospital', 'university', 'mall', 'station', 'subway_entrance']: peso = 3.0
                elif tipo_raw in ['bank', 'school', 'hotel', 'restaurant', 'bar']: peso = 2.0
                else: peso = 1.0 
                
                puntos.append({
                    'lat': lat, 'lon': lon, 'peso': peso,
                    'tipo_raw': tipo_raw,
                    'tipo_es': tipo_es, 'nombre': nombre
                })
        return pd.DataFrame(puntos)
    except Exception as ex:
        return pd.DataFrame()

with st.spinner("Conectando con base de datos privada..."):
    df_cafes = cargar_cafeterias()

# --- 4. PANEL LATERAL ---
st.sidebar.subheader("📍 Filtro de Zona")
ciudades_disponibles = ["Seleccionar Ciudad..."] + list(GIDS.keys())
ciudad_seleccionada = st.sidebar.selectbox("Ciudad a analizar", options=ciudades_disponibles)

barrio_seleccionado = None
if ciudad_seleccionada == "Buenos Aires":
    barrios_caba = [
        "Palermo", "Belgrano", "Recoleta", "Caballito", "Villa Crespo",
        "Colegiales", "San Telmo", "Puerto Madero", "Núñez", "Almagro",
        "Balvanera", "San Nicolás", "Retiro", "Todo CABA (Lento)"
    ]
    barrio_seleccionado = st.sidebar.selectbox("Seleccionar Barrio (CABA)", options=barrios_caba)

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
    col1, col2 = st.columns([4, 1])
    
    with col2:
        st.subheader("Métricas")
        df_cafes_ciudad = df_cafes[df_cafes['ciudad'] == ciudad_seleccionada]
        st.metric("Cafeterías Globales (Ciudad)", len(df_cafes_ciudad))
        
        zona_msj = f"{barrio_seleccionado}, {ciudad_seleccionada}" if barrio_seleccionado else ciudad_seleccionada
        with st.spinner(f"Analizando tráfico en {zona_msj}..."):
            df_trafico_ciudad = obtener_trafico(ciudad_seleccionada, barrio_seleccionado)
            
        st.metric("Puntos de Interés (Zona)", len(df_trafico_ciudad))
        
        st.markdown("### Guía de Capas")
        st.markdown("🔴 **Oferta:** Polos saturados.")
        st.markdown("🔵 **Demanda:** Subtes, trenes, comercios.")
        st.markdown("📍 **Anclas:** Bancos, Hospitales.")
        st.markdown("🚌 **Colectivos:** Paradas (Prender manual).")
        st.markdown("🏷️ **Nombres:** Identifica tu base de datos.")

    with col1:
        # Centramos el mapa inteligentemente: Si filtramos un barrio, que se centre en el tráfico de ese barrio.
        if not df_trafico_ciudad.empty:
            centro_lat = df_trafico_ciudad['lat'].mean()
            centro_lon = df_trafico_ciudad['lon'].mean()
        else:
            centro_lat = df_cafes_ciudad['lat'].mean() if not df_cafes_ciudad.empty else -34.6
            centro_lon = df_cafes_ciudad['lon'].mean() if not df_cafes_ciudad.empty else -58.4
        
        mapa = folium.Map(location=[centro_lat, centro_lon], zoom_start=15 if barrio_seleccionado else 13, tiles="CartoDB dark_matter")
        
        if not df_trafico_ciudad.empty:
            df_calor_trafico = df_trafico_ciudad
            if len(df_calor_trafico) > 8000:
                df_calor_trafico = df_calor_trafico.sample(n=8000, random_state=42)

            capa_calor_trafico = folium.FeatureGroup(name="🚶‍♂️ Densidad Comercial/Peatonal")
            HeatMap(
                df_calor_trafico[['lat', 'lon', 'peso']].values.tolist(),
                radius=15, blur=15, min_opacity=0.4,
                gradient={0.4: 'navy', 0.6: 'blue', 1: 'cyan'} 
            ).add_to(capa_calor_trafico)
            capa_calor_trafico.add_to(mapa)
            
            df_nodos_importantes = df_trafico_ciudad[(df_trafico_ciudad['peso'] >= 2.0) & (df_trafico_ciudad['tipo_raw'] != 'bus_stop')]
            if len(df_nodos_importantes) > 1500:
                df_nodos_importantes = df_nodos_importantes.sample(n=1500, random_state=42)

            capa_nodos = folium.FeatureGroup(name="📍 Detalle Anclas Principales", show=False)
            for _, row in df_nodos_importantes.iterrows():
                tooltip_text = f"<b>{row['tipo_es']}</b><br>{row['nombre']}"
                folium.CircleMarker(
                    location=[row['lat'], row['lon']], radius=4, color='cyan', fill=True, fill_opacity=0.7, tooltip=tooltip_text
                ).add_to(capa_nodos)
            capa_nodos.add_to(mapa)
            
            df_colectivos = df_trafico_ciudad[df_trafico_ciudad['tipo_raw'] == 'bus_stop']
            if len(df_colectivos) > 1000: 
                df_colectivos = df_colectivos.sample(n=1000, random_state=42)
                
            capa_colectivos = folium.FeatureGroup(name="🚌 Paradas de Colectivo", show=False)
            for _, row in df_colectivos.iterrows():
                folium.CircleMarker(
                    location=[row['lat'], row['lon']], radius=3, color='gray', fill=True, fill_opacity=0.8, tooltip="Parada de Colectivo"
                ).add_to(capa_colectivos)
            capa_colectivos.add_to(mapa)
            
        if not df_cafes_ciudad.empty:
            capa_cafes = folium.FeatureGroup(name="☕ Calor Cafeterías (Competencia)")
            HeatMap(
                df_cafes_ciudad[['lat', 'lon']].values.tolist(),
                radius=20, blur=15, min_opacity=0.5,
                gradient={0.4: 'orange', 0.6: 'red', 1: 'darkred'} 
            ).add_to(capa_cafes)
            capa_cafes.add_to(mapa)

            capa_nombres_cafes = folium.FeatureGroup(name="🏷️ Nombres de Cafeterías", show=False)
            for _, row in df_cafes_ciudad.iterrows():
                folium.CircleMarker(
                    location=[row['lat'], row['lon']], radius=5, color='orange', fill=True, fill_opacity=0.9, tooltip=f"<b>{row['nombre']}</b>"
                ).add_to(capa_nombres_cafes)
            capa_nombres_cafes.add_to(mapa)
            
        folium.LayerControl(collapsed=False).add_to(mapa)
        components.html(mapa._repr_html_(), height=750)

else:
    st.info("👈 Seleccioná una ciudad en el menú lateral para iniciar el análisis.")
