import json
import numpy as np
import pandas as pd
import scipy.spatial as spatial
from scipy.interpolate import Rbf
from scipy.linalg import svd, pinv
import torch
import torch.nn as nn

import ee
import folium
import streamlit as st
import streamlit_folium as st_folium

# -----------------------------------------------------------------------------
# 1. PAGE CONFIGURATION & INITIALIZATION
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Zero Waste Solutions — Subsurface Gas Extraction Engine",
    page_icon="⚛️",
    layout="wide",
)

PROJECT_ID = "stalwart-fx-490910-e3"

@st.cache_resource
def init_earth_engine():
    try:
        if "GCP_SERVICE_ACCOUNT" in st.secrets:
            key_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
            credentials = ee.ServiceAccountCredentials(
                key_dict["client_email"], key_data=st.secrets["GCP_SERVICE_ACCOUNT"]
            )
            ee.Initialize(credentials, project=PROJECT_ID)
            return True, "GEE Connected via Service Account Key"
        else:
            ee.Initialize(project=PROJECT_ID)
            return True, f"GEE Connected via GCP Project: {PROJECT_ID}"
    except Exception as e:
        return False, str(e)

gee_connected, gee_msg = init_earth_engine()

# -----------------------------------------------------------------------------
# 2. ALL-INDIA LANDFILL GEOTECHNICAL DATABASE
# -----------------------------------------------------------------------------
INDIA_LANDFILLS = {
    "Ghazipur (Delhi)": {"lat": 28.6231, "lon": 77.3288, "waste_mass_mt": 14.0, "height_m": 65.0, "area_ha": 29.0},
    "Bhalswa (Delhi)": {"lat": 28.7410, "lon": 77.1517, "waste_mass_mt": 8.0, "height_m": 62.0, "area_ha": 21.0},
    "Okhla (Delhi)": {"lat": 28.5303, "lon": 77.2789, "waste_mass_mt": 6.0, "height_m": 55.0, "area_ha": 16.0},
    "Deonar (Mumbai)": {"lat": 19.0573, "lon": 72.9304, "waste_mass_mt": 16.0, "height_m": 38.0, "area_ha": 120.0},
    "Mulund (Mumbai)": {"lat": 19.1678, "lon": 72.9567, "waste_mass_mt": 7.0, "height_m": 30.0, "area_ha": 24.0},
    "Pirana (Ahmedabad)": {"lat": 22.9831, "lon": 72.5802, "waste_mass_mt": 10.0, "height_m": 50.0, "area_ha": 34.0},
    "Jawaharnagar (Hyderabad)": {"lat": 17.5147, "lon": 78.5852, "waste_mass_mt": 12.0, "height_m": 45.0, "area_ha": 137.0},
    "Kodungaiyur (Chennai)": {"lat": 13.1360, "lon": 80.2640, "waste_mass_mt": 11.0, "height_m": 35.0, "area_ha": 108.0},
}

# -----------------------------------------------------------------------------
# 3. SUBSURFACE DRILLING & METHANE CHAMBER CALCULATOR
# -----------------------------------------------------------------------------
def calculate_subsurface_drilling_plan(lat, lon, height_m, waste_mass_mt):
    # Core gas pocket depth: ~65-75% of landfill height
    optimal_hole_depth = round(height_m * 0.72, 1)
    
    # Subsurface Methane Volume Estimate (m^3 in anaerobic core)
    core_gas_volume_m3 = round(waste_mass_mt * 1e6 * 0.45 * 0.52, 2)
    
    # Recommended Vacuum Extraction Rate (m3/hr)
    extraction_rate_m3h = round(core_gas_volume_m3 / (365 * 24 * 5), 1) # 5-yr extraction cycle
    
    # Drilling Offset Boreholes (Triangle Matrix around core)
    boreholes = [
        {"id": "Borehole-1 (Core Peak)", "lat": lat, "lon": lon, "depth_m": optimal_hole_depth, "dia_mm": 300},
        {"id": "Borehole-2 (North Flank)", "lat": lat + 0.0008, "lon": lon + 0.0005, "depth_m": round(optimal_hole_depth * 0.85, 1), "dia_mm": 250},
        {"id": "Borehole-3 (South Flank)", "lat": lat - 0.0008, "lon": lon - 0.0005, "depth_m": round(optimal_hole_depth * 0.85, 1), "dia_mm": 250},
    ]
    
    return optimal_hole_depth, core_gas_volume_m3, extraction_rate_m3h, boreholes

# -----------------------------------------------------------------------------
# 4. SIDEBAR & CONTROLS
# -----------------------------------------------------------------------------
st.sidebar.title("🎮 Multi-Site & Physics Controls")

selected_site_name = st.sidebar.selectbox("Select Target Indian Landfill", list(INDIA_LANDFILLS.keys()))
site_info = INDIA_LANDFILLS[selected_site_name]

lat = site_info["lat"]
lon = site_info["lon"]
height_m = site_info["height_m"]
waste_mass = site_info["waste_mass_mt"]

depth_m, gas_vol_m3, flow_rate, boreholes = calculate_subsurface_drilling_plan(lat, lon, height_m, waste_mass)

# -----------------------------------------------------------------------------
# 5. DASHBOARD METRICS
# -----------------------------------------------------------------------------
st.title("🛰️ Zero Waste Solutions — Subsurface Gas Extraction & All-India Monitor")
st.caption("Subsurface Volumetric Chambering | Borehole Drilling Plan | Multi-Site Geotechnical Mapping")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Selected Landfill Height", f"{height_m} meters", selected_site_name)
c2.metric("Subsurface CH₄ Core Vol.", f"{gas_vol_m3/1e6:.2f} M-m³", "Trapped Gas Mass")
c3.metric("Optimum Drilling Depth", f"{depth_m} meters", "72% Core Depth")
c4.metric("Recommended Extraction", f"{flow_rate} m³/hr", "Active Suction Rate")

st.markdown("---")

# -----------------------------------------------------------------------------
# 6. ALL-INDIA LANDFILL MAP WITH DRILLING BOREHOLES
# -----------------------------------------------------------------------------
st.subheader("📍 Interactive All-India Landfills & Active Target Drilling Matrix")

# Base Map centered around active landfill
m = folium.Map(location=[lat, lon], zoom_start=13, tiles="OpenStreetMap")

# Render ALL Indian Landfill Sites on Map
for site_name, data in INDIA_LANDFILLS.items():
    is_target = (site_name == selected_site_name)
    color = "red" if is_target else "blue"
    
    folium.Marker(
        [data["lat"], data["lon"]],
        popup=f"<b>{site_name}</b><br>Mass: {data['waste_mass_mt']} MT<br>Height: {data['height_m']}m",
        tooltip=site_name,
        icon=folium.Icon(color=color, icon="star" if is_target else "info-sign")
    ).add_to(m)

# Render Specific Drilling Boreholes for Active Target Site
for hole in boreholes:
    folium.Marker(
        [hole["lat"], hole["lon"]],
        popup=f"<b>{hole['id']}</b><br>Depth: {hole['depth_m']}m<br>Diameter: {hole['dia_mm']}mm",
        tooltip=f"Drill Pinpoint: {hole['id']}",
        icon=folium.Icon(color="green", icon="wrench")
    ).add_to(m)

# Perimeter circle around selected site
folium.Circle([lat, lon], radius=1000, color="red", fill=True, fill_opacity=0.15, popup="Core Hazard Zone").add_to(m)

st_folium.st_folium(m, width=1200, height=520)

st.markdown("---")

# -----------------------------------------------------------------------------
# 7. EXACT DRILLING PINPOINT TABLE
# -----------------------------------------------------------------------------
st.subheader("🛠️ Geotechnical Borehole Extraction Schedule")
df_holes = pd.DataFrame(boreholes)
st.dataframe(df_holes, use_container_width=True)
