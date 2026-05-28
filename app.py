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

st.title("🔥 Inteligencia B2B: Oferta vs Demanda vs Costos")
st.markdown("Cruce de competencia, tráfico peatonal, demografía y viabilidad inmobiliaria.")

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

# --- 3. FUENTE DE DATOS 2: TRÁFICO PEATONAL ---
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

with st.spinner("Conectando con base de datos privada..."):
    df_cafes = cargar_cafeterias()

# --- 4. PANEL LATERAL: FILTROS, PEA E INMOBILIARIA ---
st.sidebar.subheader("📍 1. Filtro de Zona")
ciudades_disponibles = ["Seleccionar Ciudad..."] + list(GIDS.keys())
ciudad_seleccionada = st.sidebar.selectbox("Ciudad a analizar", options=ciudades_disponibles)

st.sidebar.markdown("---")
st.sidebar.subheader("🧮 2. Demanda (PEA)")
poblacion = st.sidebar.number_input("Población de la zona", value=15000, step=1000)
tasa_pea = st.sidebar.slider("% Población Activa (PEA)", 30, 60, 47)
captacion = st.sidebar.slider("% Captación de clientes", 1, 30, 10)

pea_total = int(poblacion * (tasa_pea / 100))
clientes_diarios = int(pea_total * (captacion / 100))
clientes_mensuales = clientes_diarios * 30

st.sidebar.info(f"☕ **Demanda Estimada:** {clientes_diarios} clientes/día")

st.sidebar.markdown("---")
st.sidebar.subheader("🏠 3. Filtro Inmobiliario (Realidad)")
alquiler_mensual = st.sidebar.number_input("Alquiler Mensual Estimado ($ARS)", value=1000000, step=100000)
superficie_m2 = st.sidebar.number_input("Superficie del local (m²)", value=50, step=10)

# Cálculos Inmobiliarios
costo_m2 = alquiler_mensual / superficie_m2 if superficie_m2 > 0 else 0
# ¿Cuánto del alquiler se paga por cada cliente potencial al mes?
costo_alquiler_por_cliente = alquiler_mensual / clientes_mensuales if clientes_mensuales > 0 else 0

st.sidebar.write(f"**Costo por m²:** ${costo_m2:,.0f} ARS")

if costo_alquiler_por_cliente > 1500:
    st.sidebar.error(f"⚠️ **Riesgo Alto:** Estás pagando ${costo_alquiler_por_cliente:,.0f} de alquiler por cada cliente potencial. El margen de ganancia por taza no lo soporta.")
elif costo_alquiler_por_cliente > 800:
    st.sidebar.warning(f"⚖️ **Riesgo Medio:** ${costo_alquiler_por_cliente:,.0f} de costo de alquiler por cliente. Vas a depender mucho de la venta cruzada (pastelería).")
else:
    st.sidebar.success(f"✅ **Viable:** Costo de alquiler sano (${costo_alquiler_por_cliente:,.0f} por cliente). Buen balance entre tráfico y costo fijo.")

# --- 5. RENDERIZADO DEL MAPA ---
if ciudad_seleccionada != "Seleccionar Ciudad...":
    col1, col2 = st.columns([3, 1])
    
    with col2:
        st.subheader("Métricas del Mapa")
        df_cafes_ciudad = df_cafes[df_cafes['ciudad'] == ciudad_seleccionada]
        st.metric("Cafeterías (Competencia)", len(df_cafes_ciudad))
        
        with st.spinner("Descargando tráfico peatonal..."):
            df_trafico_ciudad = obtener_trafico(ciudad_seleccionada)
        st.metric("Nodos de Tráfico", len(df_trafico_ciudad))
        
        st.markdown("### Guía de Consultoría")
        st.markdown("🔴 **Rojo/Naranja (Oferta):** Polos gastronómicos saturados.")
        st.markdown("🔵 **Azul/Celeste (Demanda):** Zonas de alto tránsito (Hospitales, Bancos, Escuelas).")
        st.markdown("💡 **Tip:** Buscá las zonas azules sin rojo cerca y validá el precio del m² en el panel lateral.")

    with col1:
        centro_lat = df_cafes_ciudad['lat'].mean() if not df_cafes_ciudad.empty else -38.0
        centro_lon = df_cafes_ciudad['lon'].mean() if not df_cafes_ciudad.empty else -57.5
        
        mapa = folium.Map(location=[centro_lat, centro_lon], zoom_start=14, tiles="CartoDB dark_matter")
        
        if not df_trafico_ciudad.empty:
            capa_trafico = folium.FeatureGroup(name="🚶‍♂️ Tráfico Peatonal (Demanda)")
            HeatMap(
                df_trafico_ciudad[['lat', 'lon', 'peso']].values.tolist(),
                radius=15, blur=15, min_opacity=0.4,
                gradient={0.4: 'navy', 0.6: 'blue', 1: 'cyan'} 
            ).add_to(capa_trafico)
            capa_trafico.add_to(mapa)
            
        if not df_cafes_ciudad.empty:
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
