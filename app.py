import streamlit as st
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
import requests

# --- 1. SISTEMA DE SEGURIDAD BÁSICO ---
st.set_page_config(page_title="Consultora Café", layout="wide")
st.sidebar.title("🔐 Acceso Privado")
password = st.sidebar.text_input("Contraseña", type="password")

if password != "AdminCafe2026": # Cambiá esta contraseña
    st.warning("✋ Ingresá la contraseña de administrador para acceder a la inteligencia de mercado.")
    st.stop()

st.title("📊 Inteligencia Comercial: Mapa B2B")
st.markdown("Cruce de densidad de tráfico peatonal (hospitales, bancos, colegios, paradas) y mercado potencial.")

# --- 2. EXTRACCIÓN AUTOMÁTICA EN LA NUBE ---
# Usamos cache para que solo descargue la info 1 vez por día y no colapse la tablet
@st.cache_data(ttl=86400) 
def obtener_datos_trafico():
    query = """
    [out:json][timeout:25];
    geocodeArea("Mar del Plata, Argentina")->.searchArea;
    (
      node["amenity"~"bank|hospital|clinic|school|university"](area.searchArea);
      node["highway"="bus_stop"](area.searchArea);
    );
    out center;
    """
    url = "http://overpass-api.de/api/interpreter"
    res = requests.post(url, data={'data': query})
    data = res.json()
    
    puntos = []
    for e in data['elements']:
        if 'lat' in e and 'lon' in e:
            tipo = e.get('tags', {}).get('amenity', 'bus_stop')
            # Hospitales y facultades pesan más que un banco o parada
            peso = 3.0 if tipo in ['hospital', 'university'] else 2.0 if tipo in ['bank', 'clinic', 'school'] else 1.0
            puntos.append({'lat': e['lat'], 'lon': e['lon'], 'peso': peso})
    return pd.DataFrame(puntos)

with st.spinner("Escaneando Mar del Plata (esto tarda unos segundos la primera vez)..."):
    df_trafico = obtener_datos_trafico()

# --- 3. FILTROS Y CALCULADORA PEA ---
col1, col2 = st.columns([1, 3])

with col1:
    st.subheader("Filtros de Tráfico")
    peso_minimo = st.slider("Filtro de densidad", 1.0, 3.0, 1.0, help="1=Paradas, 2=Bancos/Escuelas, 3=Hospitales")
    df_filtrado = df_trafico[df_trafico['peso'] >= peso_minimo]
    
    st.subheader("🧮 Calculadora de Mercado (PEA)")
    poblacion = st.number_input("Habitantes del radio", value=20000, step=1000)
    captacion = st.slider("% Captación de clientes", 1, 30, 10)
    
    pea = poblacion * 0.47 # 47% es el promedio de PEA aprox
    mercado = int(pea * (captacion / 100))
    st.success(f"**Mercado Potencial:** {mercado} clientes")
    st.caption("Considerando PEA activa (47%) y el % de captación seleccionado.")

# --- 4. MAPA DE CALOR ---
with col2:
    # Centrado en Mar del Plata
    mapa = folium.Map(location=[-38.0055, -57.5426], zoom_start=13, tiles="CartoDB positron")
    
    datos_calor = df_filtrado[['lat', 'lon', 'peso']].values.tolist()
    
    HeatMap(
        datos_calor,
        radius=15, 
        blur=10, 
        min_opacity=0.3,
        gradient={0.4: 'blue', 0.65: 'orange', 1: 'red'}
    ).add_to(mapa)
    
    st_folium(mapa, width=800, height=500, returned_objects=[])
