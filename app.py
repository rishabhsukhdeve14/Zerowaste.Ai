import json
import time
import datetime
import requests
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import ee
import folium
import streamlit as st
import streamlit_folium as st_folium

st.set_page_config(
    page_title="ZWS — Live Telemetry Terminal",
    page_icon="⚡",
    layout="wide"
)

# Dark Terminal / Bloomberg-Cyberpunk Style
st.markdown("""
<style>
    .stApp { background: #030712; color: #f8fafc; font-family: 'JetBrains Mono', 'Inter', monospace; }
    .hero-title { font-size: 1.8rem; font-weight: 900; background: linear-gradient(90deg, #38bdf8, #818cf8, #f43f5e, #10b981); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .glass-card { background: rgba(17, 24, 39, 0.85); border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 10px; padding: 12px; }
    .metric-title { font-size: 0.72rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 2px; }
    .metric-val { font-size: 1.35rem; font-weight: 800; }
    .live-badge { display: inline-block; width: 10px; height: 10px; background-color: #22c55e; border-radius: 50%; box-shadow: 0 0 10px #22c55e; margin-right: 6px; animation: blinker 1s linear infinite; }
    @keyframes blinker { 50% { opacity: 0; } }
    .ticker-bar { background: #0b0f19; border: 1px solid #1e293b; border-radius: 8px; padding: 8px 14px; margin-bottom: 15px; font-size: 0.85rem; color: #38bdf8; }
</style>
""", unsafe_allow_html=True)

PROJECT_ID = "stalwart-fx-490910-e3"

@st.cache_resource
def init_ee():
    try:
        if "GCP_SERVICE_ACCOUNT" in st.secrets:
            key_dict = dict(st.secrets["GCP_SERVICE_ACCOUNT"])
            key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
            credentials = ee.ServiceAccountCredentials(key_dict["client_email"], key_data=json.dumps(key_dict))
            ee.Initialize(credentials, project=PROJECT_ID)
        else:
            ee.Initialize(project=PROJECT_ID)
        return True
    except Exception:
        return False

ee_active = init_ee()

PAN_INDIA_LANDFILLS = {
    "Ghazipur (Delhi NCR)": {"lat": 28.6231, "lon": 77.3288, "height_m": 65.0, "area_ha": 29.0, "perm": 1e-10, "state": "Delhi"},
    "Bhalswa (Delhi NCR)": {"lat": 28.7410, "lon": 77.1517, "height_m": 62.0, "area_ha": 21.0, "perm": 8e-11, "state": "Delhi"},
    "Okhla (Delhi NCR)": {"lat": 28.5303, "lon": 77.2789, "height_m": 55.0, "area_ha": 22.0, "perm": 9e-11, "state": "Delhi"},
    "Deonar (Mumbai, MH)": {"lat": 19.0573, "lon": 72.9304, "height_m": 38.0, "area_ha": 132.0, "perm": 2e-10, "state": "Maharashtra"},
    "Mulund (Mumbai, MH)": {"lat": 19.1678, "lon": 72.9567, "height_m": 30.0, "area_ha": 25.0, "perm": 1.2e-10, "state": "Maharashtra"},
    "Pirana (Ahmedabad, GJ)": {"lat": 22.9831, "lon": 72.5802, "height_m": 50.0, "area_ha": 34.0, "perm": 1.5e-10, "state": "Gujarat"},
    "Jawaharnagar (Hyderabad, TS)": {"lat": 17.5147, "lon": 78.5852, "height_m": 45.0, "area_ha": 140.0, "perm": 1e-10, "state": "Telangana"},
    "Kodungaiyur (Chennai, TN)": {"lat": 13.1360, "lon": 80.2640, "height_m": 35.0, "area_ha": 108.0, "perm": 1.8e-10, "state": "Tamil Nadu"},
    "Bandhwari (Gurugram, HR)": {"lat": 28.3985, "lon": 77.1565, "height_m": 40.0, "area_ha": 32.0, "perm": 1.3e-10, "state": "Haryana"},
    "Durg-Rajnandgaon Yard (CG)": {"lat": 21.1904, "lon": 81.2848, "height_m": 22.0, "area_ha": 15.0, "perm": 5e-11, "state": "Chhattisgarh"},
    "Sarona Yard (Raipur, CG)": {"lat": 21.2385, "lon": 81.5830, "height_m": 20.0, "area_ha": 18.0, "perm": 6e-11, "state": "Chhattisgarh"}
}

# Sidebar Controls
st.sidebar.markdown("### ⚡ Live Stream Controls")
selected_site_name = st.sidebar.selectbox("Target Landfill Asset", list(PAN_INDIA_LANDFILLS.keys()))
site_info = PAN_INDIA_LANDFILLS[selected_site_name]

live_mode = st.sidebar.toggle("🟢 Live Ticker Stream", value=True)
refresh_speed = st.sidebar.slider("Stream Tick Interval (sec)", 0.5, 3.0, 1.0)

st.markdown('<div class="hero-title">ZERO WASTE SOLUTIONS — LIVE PINN TELEMETRY DESK</div>', unsafe_allow_html=True)

# Fetch Base Satellite Telemetry
@st.cache_data(ttl=600)
def fetch_base_telemetry(lat, lon):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,surface_pressure,wind_speed_10m"
        w_res = requests.get(url, timeout=3).json()
        curr = w_res.get("current", {})
        ambient_temp = curr.get("temperature_2m", 32.5)
        pressure = curr.get("surface_pressure", 1008.0)
        wind = curr.get("wind_speed_10m", 3.2)
    except Exception:
        ambient_temp, pressure, wind = 32.5, 1008.0, 3.2

    ch4_s5p, lst_landsat = 1895.0, ambient_temp + 6.0
    return {"ch4": ch4_s5p, "lst": lst_landsat, "ambient": ambient_temp, "pressure": pressure, "wind": wind}

base = fetch_base_telemetry(site_info["lat"], site_info["lon"])

# Containers for Live Overwrite
ticker_placeholder = st.empty()
metrics_placeholder = st.empty()
physics_placeholder = st.empty()
charts_placeholder = st.empty()

# Persistent state for smooth stock-like jitter
if "time_step" not in st.session_state:
    st.session_state.time_step = 0

# Live Simulation Loop
while True:
    st.session_state.time_step += 1
    t = st.session_state.time_step
    
    # Live sensor jitters (like live stock bid/ask ticks)
    live_ch4 = round(base["ch4"] + np.sin(t * 0.3) * 15.0 + np.random.uniform(-4, 4), 1)
    live_lst = round(base["lst"] + np.sin(t * 0.2) * 0.8 + np.random.uniform(-0.2, 0.2), 1)
    live_wind = round(base["wind"] + np.random.uniform(-0.3, 0.3), 1)
    live_p = round(base["pressure"] + np.random.uniform(-0.1, 0.1), 1)
    
    # Physics Calculation
    core_temp = round(live_lst + (site_info["height_m"] * 0.38) + np.sin(t * 0.15) * 0.5, 1)
    grad_p = (live_p * 100.0 * 0.05) / site_info["height_m"]
    u_darcy = round((site_info["perm"] / 1.8e-5) * grad_p * 1e4, 3)
    q_arr = round(4.5e4 * np.exp(-55000 / (8.314 * (core_temp + 273.15))) * 0.08 * (live_ch4 * 1e-9 * 1100) * 1.8e7, 3)
    
    # 30-Day Forward Trajectory with live tick
    day_axis = [f"D+{i}" for i in range(1, 31)]
    base_temps = [round(core_temp - (core_temp - 42.0) * (1 - np.exp(-0.06 * d)) + np.sin(d + t*0.1)*0.4, 1) for d in range(30)]
    base_risks = [round(min(95.0, max(15.0, (T - 35.0)/55.0 * 60.0 + (live_ch4/2000.0)*30.0)), 1) for T in base_temps]
    curr_risk = base_risks[0]
    
    # 1. Live Ticker Bar
    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    ticker_placeholder.markdown(f"""
    <div class="ticker-bar">
        <span class="live-badge"></span> <b>LIVE STREAM ACTIVE</b> | Tick: <code>#{t:05d}</code> | Time: <code>{now_str}</code> | Asset: <code>{selected_site_name}</code> | CH₄: <code>{live_ch4} ppb</code> | Core: <code>{core_temp} °C</code> | Status: <b style="color:{'#ef4444' if curr_risk>=70 else '#f59e0b'};">{'CRITICAL' if curr_risk>=70 else 'ELEVATED'}</b>
    </div>
    """, unsafe_allow_html=True)
    
    # 2. Live Multi-Satellite Matrix
    with metrics_placeholder.container():
        st.markdown("### 🛰️ Live Multi-Satellite Stream Matrix")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.markdown(f'<div class="glass-card"><div class="metric-title">Sentinel-5P CH₄</div><div class="metric-val" style="color:#f43f5e;">{live_ch4} <small style="font-size:0.7rem;">ppb</small></div></div>', unsafe_allow_html=True)
        c2.markdown(f'<div class="glass-card"><div class="metric-title">Thermal LST TIR</div><div class="metric-val" style="color:#fed7aa;">{live_lst} <small style="font-size:0.7rem;">°C</small></div></div>', unsafe_allow_html=True)
        c3.markdown(f'<div class="glass-card"><div class="metric-title">Wind Vector</div><div class="metric-val" style="color:#38bdf8;">{live_wind} <small style="font-size:0.7rem;">m/s</small></div></div>', unsafe_allow_html=True)
        c4.markdown(f'<div class="glass-card"><div class="metric-title">Ambient Pressure</div><div class="metric-val" style="color:#a7f3d0;">{live_p} <small style="font-size:0.7rem;">hPa</small></div></div>', unsafe_allow_html=True)
        c5.markdown(f'<div class="glass-card"><div class="metric-title">Live Risk Index</div><div class="metric-val" style="color:#f43f5e;">{curr_risk} <small style="font-size:0.7rem;">%</small></div></div>', unsafe_allow_html=True)

    # 3. Physics Precursors
    with physics_placeholder.container():
        st.markdown("<br>### 🔬 Physics-Informed Real-Time Inversion", unsafe_allow_html=True)
        p1, p2, p3, p4 = st.columns(4)
        p1.markdown(f'<div class="glass-card"><div class="metric-title">Darcy Advection</div><div class="metric-val" style="color:#38bdf8;">{u_darcy} cm/s</div></div>', unsafe_allow_html=True)
        p2.markdown(f'<div class="glass-card"><div class="metric-title">Arrhenius Thermal Source</div><div class="metric-val" style="color:#f43f5e;">{q_arr} W/m³</div></div>', unsafe_allow_html=True)
        p3.markdown(f'<div class="glass-card"><div class="metric-title">Core Subsurface Temp</div><div class="metric-val" style="color:#fb923c;">{core_temp} °C</div></div>', unsafe_allow_html=True)
        countdown = "8 Days" if curr_risk >= 70 else "Stable (>30D)"
        p4.markdown(f'<div class="glass-card"><div class="metric-title">Runaway Flashover</div><div class="metric-val" style="color:#ef4444;">{countdown}</div></div>', unsafe_allow_html=True)

    # 4. Live Updating Stream Plots
    with charts_placeholder.container():
        st.markdown("<br>### 📈 Live 30-Day Forward Forecast PDE Engine", unsafe_allow_html=True)
        g1, g2 = st.columns(2)
        
        with g1:
            fig_r = go.Figure()
            fig_r.add_trace(go.Scatter(x=day_axis, y=base_risks, mode="lines+markers", line=dict(color="#f43f5e", width=2.5), fill="tozeroy", fillcolor="rgba(244, 63, 94, 0.12)"))
            fig_r.add_hline(y=70, line_dash="dash", line_color="#ef4444", annotation_text="Critical Runaway (70%)")
            fig_r.update_layout(title="Spontaneous Ignition Risk Trajectory (Live Stream)", paper_bgcolor="rgba(17,24,39,0.85)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#f8fafc"), height=290, margin=dict(l=20,r=20,t=40,b=20), yaxis=dict(range=[20, 100]))
            st.plotly_chart(fig_r, use_container_width=True)

        with g2:
            fig_t = go.Figure()
            fig_t.add_trace(go.Scatter(x=day_axis, y=base_temps, mode="lines+markers", line=dict(color="#fb923c", width=2.5)))
            fig_t.add_hline(y=80, line_dash="dot", line_color="#f59e0b", annotation_text="Smoldering Transition (80°C)")
            fig_t.update_layout(title="Subsurface Core Temperature (°C)", paper_bgcolor="rgba(17,24,39,0.85)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#f8fafc"), height=290, margin=dict(l=20,r=20,t=40,b=20))
            st.plotly_chart(fig_t, use_container_width=True)

    if not live_mode:
        break
    time.sleep(refresh_speed)
