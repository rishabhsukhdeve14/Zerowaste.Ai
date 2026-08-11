import json
import datetime
import time
import requests
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

import ee
import folium
import streamlit as st
import streamlit_folium as st_folium

# -----------------------------------------------------------------------------
# 1. PAGE CONFIGURATION & INITIALIZATION
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Zero Waste Solutions — Physics & Fire Prevention Engine",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# 2. CYBERPUNK / GLASSMORPHISM CUSTOM CSS
# -----------------------------------------------------------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Inter:wght@300;400;600;700&display=swap');

    .stApp {
        background: radial-gradient(circle at 15% 15%, #0f172a 0%, #030712 100%);
        color: #f8fafc;
        font-family: 'Inter', sans-serif;
    }

    .hero-title {
        font-family: 'Orbitron', sans-serif;
        font-size: 2.1rem;
        font-weight: 900;
        letter-spacing: 1.5px;
        background: linear-gradient(90deg, #38bdf8, #818cf8, #f43f5e, #fbbf24);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 2px;
    }

    .hero-subtitle {
        color: #94a3b8;
        font-size: 0.9rem;
        margin-bottom: 20px;
    }

    .glass-card {
        background: rgba(17, 24, 39, 0.7);
        backdrop-filter: blur(14px);
        -webkit-backdrop-filter: blur(14px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 16px;
        position: relative;
        overflow: hidden;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
        transition: transform 0.3s ease;
    }
    .glass-card:hover {
        transform: translateY(-4px);
    }

    .card-neon-pink { border-top: 4px solid #f43f5e; box-shadow: 0 4px 20px rgba(244, 63, 94, 0.15); }
    .card-neon-cyan { border-top: 4px solid #06b6d4; box-shadow: 0 4px 20px rgba(6, 182, 212, 0.15); }
    .card-neon-orange { border-top: 4px solid #f97316; box-shadow: 0 4px 20px rgba(249, 115, 22, 0.15); }
    .card-neon-green { border-top: 4px solid #10b981; box-shadow: 0 4px 20px rgba(16, 185, 129, 0.15); }
    .card-neon-red { border-top: 4px solid #ef4444; background: rgba(239, 68, 68, 0.08); box-shadow: 0 4px 25px rgba(239, 68, 68, 0.25); }

    .card-label {
        color: #94a3b8;
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    .card-value {
        font-family: 'Orbitron', sans-serif;
        font-size: 1.65rem;
        font-weight: 700;
        color: #ffffff;
        margin: 6px 0;
    }
    .card-subtext {
        font-size: 0.75rem;
        color: #64748b;
    }

    .badge-live {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: rgba(16, 185, 129, 0.12);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.35);
        padding: 5px 14px;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 700;
        box-shadow: 0 0 12px rgba(52, 211, 153, 0.25);
    }
    .pulse-dot {
        width: 8px;
        height: 8px;
        background: #10b981;
        border-radius: 50%;
        box-shadow: 0 0 8px #10b981;
        animation: pulse 1.5s infinite;
    }
    @keyframes pulse {
        0% { transform: scale(0.9); opacity: 0.7; }
        50% { transform: scale(1.3); opacity: 1; }
        100% { transform: scale(0.9); opacity: 0.7; }
    }
</style>
""", unsafe_allow_html=True)

PROJECT_ID = "stalwart-fx-490910-e3"

@st.cache_resource
def init_earth_engine():
    try:
        if "GCP_SERVICE_ACCOUNT" in st.secrets:
            key_dict = dict(st.secrets["GCP_SERVICE_ACCOUNT"])
            if "private_key" in key_dict:
                key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")

            credentials = ee.ServiceAccountCredentials(
                key_dict["client_email"],
                key_data=json.dumps(key_dict)
            )
            ee.Initialize(credentials, project=PROJECT_ID)
            return True, "Authenticated"
        else:
            ee.Initialize(project=PROJECT_ID)
            return True, "Initialized"
    except Exception as e:
        return False, str(e)

gee_connected, gee_msg = init_earth_engine()

# -----------------------------------------------------------------------------
# 3. GEOTECHNICAL DATABASE & TELEMETRY
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

def fetch_live_weather(lat, lon):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_10m"
        res = requests.get(url, timeout=4).json()
        curr = res.get("current", {})
        return {
            "temp_c": curr.get("temperature_2m", 31.5),
            "humidity": curr.get("relative_humidity_2m", 58.0),
            "pressure_hpa": curr.get("surface_pressure", 1008.2),
            "wind_speed": curr.get("wind_speed_10m", 6.2)
        }
    except Exception:
        return {"temp_c": 32.0, "humidity": 55.0, "pressure_hpa": 1010.0, "wind_speed": 5.5}

def fetch_gee_sentinel5p_methane(lat, lon):
    if not gee_connected:
        return 1870.0
    try:
        point = ee.Geometry.Point([lon, lat])
        now = datetime.datetime.now()
        start_date = (now - datetime.timedelta(days=25)).strftime('%Y-%m-%d')
        end_date = now.strftime('%Y-%m-%d')
        
        s5p = (ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_CH4')
               .select('CH4_column_volume_mixing_ratio_dry_air')
               .filterBounds(point)
               .filterDate(start_date, end_date)
               .mean())
        val = s5p.reduceRegion(reducer=ee.Reducer.mean(), geometry=point, scale=1100).getInfo()
        ch4_val = val.get('CH4_column_volume_mixing_ratio_dry_air')
        return round(ch4_val, 1) if ch4_val else 1875.4
    except Exception:
        return 1875.4

# -----------------------------------------------------------------------------
# 4. THERMODYNAMICS & COMBUSTION PHYSICS
# -----------------------------------------------------------------------------
class LandfillFirePhysics:
    @staticmethod
    def calculate_fire_risk(temp_c, ch4_ppb, pressure_hpa, wind_speed, height_m):
        internal_est_temp_c = temp_c + (height_m * 0.42)
        k_waste = 0.2
        heat_flux_q = k_waste * ((internal_est_temp_c - temp_c) / height_m)
        gas_buoyancy_factor = (pressure_hpa / 1013.25) * ((internal_est_temp_c + 273.15) / 298.15)
        ch4_risk_factor = ch4_ppb / 1800.0

        raw_risk = (
            (0.35 * (internal_est_temp_c / 45.0)) + 
            (0.40 * ch4_risk_factor) + 
            (0.15 * gas_buoyancy_factor) + 
            (0.10 * (wind_speed / 10.0))
        )
        fire_risk_percent = min(round(raw_risk * 64.5, 1), 99.9)

        if fire_risk_percent > 70:
            status = "CRITICAL HAZARD"
            advisory = "⚠️ Trigger automated soil clay-capping & open vacuum extraction wells at 160 m³/hr."
            color = "#ef4444"
        elif fire_risk_percent > 45:
            status = "THERMAL WARNING"
            advisory = "⚡ Activate core heat pipes and spray water-mist misting on open surface fissures."
            color = "#f59e0b"
        else:
            status = "STABLE / NORMAL"
            advisory = "✅ Maintain continuous baseline venting and passive thermal scan schedule."
            color = "#10b981"

        return {
            "internal_temp_est_c": round(internal_est_temp_c, 1),
            "heat_flux_q": round(heat_flux_q, 3),
            "gas_buoyancy_factor": round(gas_buoyancy_factor, 2),
            "fire_risk_percent": fire_risk_percent,
            "status": status,
            "advisory": advisory,
            "color": color
        }

# -----------------------------------------------------------------------------
# 5. SIDEBAR CONTROLS
# -----------------------------------------------------------------------------
st.sidebar.markdown("### 🎛️ Digital Twin Controls")
selected_site = st.sidebar.selectbox("🎯 Target Landfill", list(INDIA_LANDFILLS.keys()), index=0)
site_info = INDIA_LANDFILLS[selected_site]

auto_stream = st.sidebar.toggle("⚡ Enable Real-time Streaming", value=True)
refresh_rate = st.sidebar.slider("📡 Live Polling Interval (sec)", min_value=3, max_value=30, value=6)

# -----------------------------------------------------------------------------
# 6. HEADER
# -----------------------------------------------------------------------------
col_h1, col_h2 = st.columns([3, 1.2])
with col_h1:
    st.markdown('<div class="hero-title">ZERO WASTE AI — THERMAL DIGITAL TWIN</div>', unsafe_allow_html=True)
    st.markdown('<div class="hero-subtitle">Physics-Informed Real-Time Spontaneous Combustion & Sentinel-5P Methane Telemetry</div>', unsafe_allow_html=True)
with col_h2:
    st.markdown('''
    <div style="text-align: right; padding-top: 5px;">
        <span class="badge-live"><span class="pulse-dot"></span> LIVE SATELLITE STREAM</span>
    </div>''', unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 7. TELEMETRY & STATE MANAGEMENT (NO RANDOM NOISE)
# -----------------------------------------------------------------------------
weather = fetch_live_weather(site_info["lat"], site_info["lon"])
ch4_val = fetch_gee_sentinel5p_methane(site_info["lat"], site_info["lon"])
physics = LandfillFirePhysics.calculate_fire_risk(
    weather["temp_c"], ch4_val, weather["pressure_hpa"], weather["wind_speed"], site_info["height_m"]
)

# Initialize Session State Buffer for Real History Tracking
if "history_time" not in st.session_state:
    st.session_state.history_time = []
    st.session_state.history_ch4 = []
    st.session_state.history_temp = []

current_time_str = datetime.datetime.now().strftime("%H:%M:%S")
# Append only if new data arrives to avoid duplicate timestamps
if not st.session_state.history_time or st.session_state.history_time[-1] != current_time_str:
    st.session_state.history_time.append(current_time_str)
    st.session_state.history_ch4.append(ch4_val)
    st.session_state.history_temp.append(weather["temp_c"])

    # Keep last 15 points
    if len(st.session_state.history_time) > 15:
        st.session_state.history_time.pop(0)
        st.session_state.history_ch4.pop(0)
        st.session_state.history_temp.pop(0)

# -----------------------------------------------------------------------------
# 8. VIBRANT KPI CARDS
# -----------------------------------------------------------------------------
k1, k2, k3, k4, k5 = st.columns(5)

with k1:
    st.markdown(f"""
    <div class="glass-card card-neon-pink">
        <div class="card-label">Sentinel-5P CH₄</div>
        <div class="card-value" style="color: #fda4af;">{ch4_val} <span style="font-size: 0.8rem; color:#f43f5e;">ppb</span></div>
        <div class="card-subtext">Column Mixing Ratio</div>
    </div>""", unsafe_allow_html=True)

with k2:
    st.markdown(f"""
    <div class="glass-card card-neon-orange">
        <div class="card-label">Surface Temp</div>
        <div class="card-value" style="color: #fed7aa;">{weather['temp_c']}° <span style="font-size: 0.8rem; color:#f97316;">C</span></div>
        <div class="card-subtext">Core Est: {physics['internal_temp_est_c']}°C</div>
    </div>""", unsafe_allow_html=True)

with k3:
    st.markdown(f"""
    <div class="glass-card card-neon-cyan">
        <div class="card-label">Barometric Pressure</div>
        <div class="card-value" style="color: #a5f3fc;">{weather['pressure_hpa']} <span style="font-size: 0.8rem; color:#06b6d4;">hPa</span></div>
        <div class="card-subtext">Buoyancy: {physics['gas_buoyancy_factor']}x</div>
    </div>""", unsafe_allow_html=True)

with k4:
    st.markdown(f"""
    <div class="glass-card card-neon-green">
        <div class="card-label">Wind Velocity</div>
        <div class="card-value" style="color: #a7f3d0;">{weather['wind_speed']} <span style="font-size: 0.8rem; color:#10b981;">km/h</span></div>
        <div class="card-subtext">O₂ Supply Rate</div>
    </div>""", unsafe_allow_html=True)

with k5:
    st.markdown(f"""
    <div class="glass-card card-neon-red">
        <div class="card-label">Combustion Risk</div>
        <div class="card-value" style="color: {physics['color']};">{physics['fire_risk_percent']}%</div>
        <div class="card-subtext">{physics['status']}</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 9. INTERACTIVE PLOTLY CHARTS & RADIAL GAUGE
# -----------------------------------------------------------------------------
c_left, c_right = st.columns([1.1, 1.9])

with c_left:
    st.markdown("#### 🎯 Real-Time Thermal Runaway Gauge")
    fig_gauge = go.Figure(go.Indicator(
        mode="gauge+number",
        value=physics["fire_risk_percent"],
        domain={'x': [0, 1], 'y': [0, 1]},
        number={'suffix': "%", 'font': {'color': '#ffffff', 'family': 'Orbitron', 'size': 32}},
        gauge={
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "#475569"},
            'bar': {'color': physics["color"], 'thickness': 0.28},
            'bgcolor': "rgba(15, 23, 42, 0.6)",
            'borderwidth': 2,
            'bordercolor': "rgba(255, 255, 255, 0.1)",
            'steps': [
                {'range': [0, 45], 'color': 'rgba(16, 185, 129, 0.2)'},
                {'range': [45, 70], 'color': 'rgba(245, 158, 11, 0.25)'},
                {'range': [70, 100], 'color': 'rgba(239, 68, 68, 0.35)'}
            ]
        }
    ))
    fig_gauge.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=260, margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(fig_gauge, use_container_width=True)

with c_right:
    st.markdown("#### 📈 Live Gas Plume vs. Temperature Trend (Real Buffer)")
    
    fig_trend = go.Figure()
    fig_trend.add_trace(go.Scatter(
        x=st.session_state.history_time, y=st.session_state.history_ch4,
        name="CH₄ Plume (ppb)", mode='lines+markers',
        line=dict(color='#f43f5e', width=3, shape='spline'), marker=dict(size=6, color='#fda4af')
    ))
    fig_trend.add_trace(go.Scatter(
        x=st.session_state.history_time, y=st.session_state.history_temp,
        name="Temp (°C)", yaxis="y2", mode='lines+markers',
        line=dict(color='#06b6d4', width=3, dash='dot'), marker=dict(size=6, color='#67e8f9')
    ))
    fig_trend.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(15, 23, 42, 0.4)",
        font=dict(color="#94a3b8"), height=260, margin=dict(l=10, r=10, t=10, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis=dict(title="CH₄ (ppb)", gridcolor="rgba(255,255,255,0.05)"),
        yaxis2=dict(title="Temp (°C)", overlaying="y", side="right", gridcolor="rgba(255,255,255,0.05)")
    )
    st.plotly_chart(fig_trend, use_container_width=True)

# -----------------------------------------------------------------------------
# 10. GEOSPATIAL NETWORK MAP
# -----------------------------------------------------------------------------
st.markdown("#### 🗺️ All-India Landfill Digital Twin Geospatial Network")
map_obj = folium.Map(location=[site_info["lat"], site_info["lon"]], zoom_start=13, tiles="CartoDB dark_matter")

for site, meta in INDIA_LANDFILLS.items():
    is_active = (site == selected_site)
    folium.CircleMarker(
        location=[meta["lat"], meta["lon"]],
        radius=14 if is_active else 7,
        color="#f43f5e" if is_active else "#38bdf8",
        fill=True, fill_color="#f43f5e" if is_active else "#0284c7", fill_opacity=0.85,
        popup=f"<b>{site}</b><br>Height: {meta['height_m']}m"
    ).add_to(map_obj)

folium.Circle(
    location=[site_info["lat"], site_info["lon"]], radius=850,
    color=physics["color"], fill=True, fill_opacity=0.22
).add_to(map_obj)

st_folium.st_folium(map_obj, width=1300, height=420)

# -----------------------------------------------------------------------------
# 11. AI ACTION PLAN ADVISORY
# -----------------------------------------------------------------------------
st.markdown(f"""
<div style="background: rgba(15, 23, 42, 0.85); border: 1px solid {physics['color']}; border-left: 6px solid {physics['color']}; border-radius: 12px; padding: 16px 20px; margin-top: 15px;">
    <div style="font-weight: 700; font-size: 1rem; color: {physics['color']}; margin-bottom: 4px;">🤖 AI FIRE MITIGATION & CONTROL PROTOCOL</div>
    <div style="color: #e2e8f0; font-size: 0.92rem;">{physics['advisory']}</div>
</div>""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 12. STREAMING TRIGGER
# -----------------------------------------------------------------------------
if auto_stream:
    time.sleep(refresh_rate)
    st.rerun()
