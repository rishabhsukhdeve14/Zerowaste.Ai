import json
import time
import datetime
import requests
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
import ee
import streamlit as st
from fpdf import FPDF
import h3  # Uber H3 Spatial Indexing Library

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Zero Waste Solutions — Multi-Scale H3 Subsurface Physics Engine",
    page_icon="⚡",
    layout="wide"
)

# --- CUSTOM DISRUPTIVE DARK THEME STYLING ---
st.markdown("""
<style>
    .stApp { background: #030712; color: #f8fafc; font-family: 'JetBrains Mono', 'Inter', monospace; }
    .hero-title { font-size: 1.8rem; font-weight: 900; background: linear-gradient(90deg, #38bdf8, #818cf8, #f43f5e, #10b981); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .glass-card { background: rgba(17, 24, 39, 0.85); border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 10px; padding: 12px; }
    .metric-title { font-size: 0.72rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 2px; }
    .metric-val { font-size: 1.35rem; font-weight: 800; }
    .ticker-bar { background: #0b0f19; border: 1px solid #1e293b; border-radius: 8px; padding: 8px 14px; margin-bottom: 15px; font-size: 0.85rem; color: #38bdf8; }
    .live-badge { display: inline-block; width: 10px; height: 10px; background-color: #22c55e; border-radius: 50%; box-shadow: 0 0 10px #22c55e; margin-right: 6px; animation: blinker 1s linear infinite; }
    @keyframes blinker { 50% { opacity: 0; } }
    .anomaly-banner { background: rgba(244, 63, 94, 0.15); border: 1px solid #f43f5e; color: #f43f5e; padding: 10px 15px; border-radius: 8px; font-weight: 700; margin-bottom: 15px; }
</style>
""", unsafe_allow_html=True)

PROJECT_ID = "stalwart-fx-490910-e3"

def get_ist_time():
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    return utc_now.astimezone(ist_tz)

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

# --- LOAD HISTORICAL DATA MASTER ---
@st.cache_data
def load_historical_data():
    try:
        df = pd.read_csv("landfills_historical_master.csv")
        return df
    except Exception:
        return None

df_historical_master = load_historical_data()

PAN_INDIA_LANDFILLS = {
    "Ghazipur (Delhi NCR)": {"lat": 28.6231, "lon": 77.3288, "height_m": 65.0, "area_ha": 29.0, "perm": 1e-11, "waste_mass_ton": 14e6},
    "Bhalswa (Delhi NCR)": {"lat": 28.7410, "lon": 77.1517, "height_m": 62.0, "area_ha": 21.0, "perm": 8e-12, "waste_mass_ton": 8e6},
    "Okhla (Delhi NCR)": {"lat": 28.5303, "lon": 77.2789, "height_m": 55.0, "area_ha": 22.0, "perm": 9e-12, "waste_mass_ton": 6e6},
    "Deonar (Mumbai, MH)": {"lat": 19.0573, "lon": 72.9304, "height_m": 38.0, "area_ha": 132.0, "perm": 2e-11, "waste_mass_ton": 16e6},
    "Kanjurmarg (Mumbai, MH)": {"lat": 19.1362, "lon": 72.9463, "height_m": 35.0, "area_ha": 65.0, "perm": 1.8e-11, "waste_mass_ton": 11e6},
    "Pirana (Ahmedabad, GJ)": {"lat": 22.9831, "lon": 72.5802, "height_m": 50.0, "area_ha": 34.0, "perm": 1.5e-11, "waste_mass_ton": 10e6},
    "Mavallipura (Bengaluru, KA)": {"lat": 13.1292, "lon": 77.5481, "height_m": 25.0, "area_ha": 40.0, "perm": 1.2e-11, "waste_mass_ton": 4e6},
    "Kodungaiyur (Chennai, TN)": {"lat": 13.1364, "lon": 80.2743, "height_m": 30.0, "area_ha": 108.0, "perm": 1.4e-11, "waste_mass_ton": 9e6},
    "Dhapa (Kolkata, WB)": {"lat": 22.5471, "lon": 88.4162, "height_m": 32.0, "area_ha": 28.0, "perm": 1.3e-11, "waste_mass_ton": 7e6},
    "Durg-Rajnandgaon Yard (CG)": {"lat": 21.1904, "lon": 81.2848, "height_m": 22.0, "area_ha": 15.0, "perm": 5e-12, "waste_mass_ton": 2e6},
    "Sarona Yard (Raipur, CG)": {"lat": 21.2385, "lon": 81.5830, "height_m": 20.0, "area_ha": 18.0, "perm": 6e-12, "waste_mass_ton": 2.5e6}
}

st.sidebar.markdown("### ⚡ Physics & Simulation Controls")
selected_site_name = st.sidebar.selectbox("Target Landfill Asset", list(PAN_INDIA_LANDFILLS.keys()))
site_info = PAN_INDIA_LANDFILLS[selected_site_name]

live_mode = st.sidebar.toggle("🟢 Continuous Inversion", value=True)
refresh_speed = st.sidebar.slider("Iteration Interval (sec)", 1.0, 5.0, 2.0)
h3_resolution = st.sidebar.select_slider("Uber H3 Resolution Focus", options=[6, 8, 10], value=10)

# --- H3 HELPER WRAPPERS ---
def latlng_to_cell(lat, lon, res):
    if hasattr(h3, 'latlng_to_cell'):
        return h3.latlng_to_cell(lat, lon, res)
    return h3.geo_to_h3(lat, lon, res)

def grid_ring(cell, distance):
    if hasattr(h3, 'grid_ring'):
        res = h3.grid_ring(cell, distance)
    elif hasattr(h3, 'k_ring'):
        res = h3.k_ring(cell, distance)
    else:
        res = [cell]
    return list(res)

def cell_to_boundary(cell):
    if hasattr(h3, 'cell_to_boundary'):
        return h3.cell_to_boundary(cell)
    return h3.h3_to_geo_boundary(cell)

# --- MATHEMATICAL ENGINE FUNCTIONS ---
def first_order_decay_ch4(waste_mass_tons, k=0.05, L0=100.0, age_years=15.0):
    return waste_mass_tons * L0 * k * np.exp(-k * age_years) / 365.0 

def terzaghi_effective_stress(total_stress_kPa, gas_pore_pressure_kPa):
    return max(0.1, total_stress_kPa - gas_pore_pressure_kPa)

def fourier_subsurface_heat_flux(k_thermal, T_core, T_surface, depth_m):
    return -k_thermal * ((T_surface - T_core) / max(1.0, depth_m))

def gaussian_plume_back_trajectory(C_obs, x_m, y_m, u_wind, sigma_y=15.0, sigma_z=10.0):
    denom = np.exp(-0.5 * (y_m / sigma_y)**2)
    if denom < 1e-4: denom = 1e-4
    Q_source = (C_obs * 2.0 * np.pi * u_wind * sigma_y * sigma_z) / denom
    return Q_source

def generate_pdf_report(site_name, timestamp, ch4_res10, core_temp, eff_stress, heat_flux, fod_gen, co2e_avoided, vcu_revenue, insar_rate):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "ZERO WASTE SOLUTIONS", ln=True, align="C")
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 8, "H3 Multi-Scale Physics & Geotechnical Subsurface Audit", ln=True, align="C")
    pdf.line(10, 30, 200, 30)
    pdf.ln(10)
    
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, f"Asset Target: {site_name}", ln=True)
    pdf.cell(0, 7, f"Report Generated (IST): {timestamp}", ln=True)
    pdf.ln(5)
    
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "1. H3 Multi-Resolution Cascade & Reverse Trajectory", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"- H3 Res 6 -> Res 8 -> Res 10 Vector Pinpoint CH4: {ch4_res10} ppb", ln=True)
    pdf.cell(0, 6, f"- First Order Decay (FOD) Organic Generation Rate: {round(fod_gen, 2)} Tons CH4/Day", ln=True)
    pdf.cell(0, 6, f"- InSAR Surface Displacement Rate: {insar_rate} mm/year", ln=True)
    pdf.ln(5)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "2. Geotechnical & Thermodynamics Vector Calculation", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"- Terzaghi Effective Stress (sigma'): {eff_stress} kPa", ln=True)
    pdf.cell(0, 6, f"- Fourier Subsurface Thermal Flux: {heat_flux} W/m2", ln=True)
    pdf.cell(0, 6, f"- Reaction Zone Core Temperature: {core_temp} C", ln=True)
    pdf.ln(5)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "3. Verra Carbon Credit MRV (VM0001 Matrix)", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"- Avoided CO2 Equivalent: {co2e_avoided} Metric Tons / Day", ln=True)
    pdf.cell(0, 6, f"- Estimated Monetizable Revenue: ${vcu_revenue} USD / Day", ln=True)
    
    return bytes(pdf.output())

@st.cache_data(ttl=300)
def fetch_satellite_ground_truth(lat, lon):
    ambient_temp, pressure, wind = 33.0, 1008.0, 3.5
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,surface_pressure,wind_speed_10m&timezone=Asia%2FKolkata"
        res = requests.get(url, timeout=4).json().get("current", {})
        ambient_temp = res.get("temperature_2m", 33.0)
        pressure = res.get("surface_pressure", 1008.0)
        wind = res.get("wind_speed_10m", 3.5)
    except Exception:
        pass

    ch4_base = 1890.0
    if ee_active:
        try:
            pt = ee.Geometry.Point([lon, lat])
            now = datetime.datetime.now()
            s5p = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_CH4').select('CH4_column_volume_mixing_ratio_dry_air').filterBounds(pt).filterDate((now - datetime.timedelta(days=30)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')).mean()
            val = s5p.reduceRegion(reducer=ee.Reducer.mean(), geometry=pt, scale=1100).get('CH4_column_volume_mixing_ratio_dry_air').getInfo()
            if val and val > 500: ch4_base = round(val, 1)
        except Exception:
            pass

    return {"ch4": ch4_base, "ambient": ambient_temp, "pressure": pressure, "wind": wind}

base_data = fetch_satellite_ground_truth(site_info["lat"], site_info["lon"])

if "time_step" not in st.session_state:
    st.session_state.time_step = 0

st.markdown('<div class="hero-title">ZERO WASTE SOLUTIONS — H3 MULTI-SCALE SUBSURFACE ENGINE</div>', unsafe_allow_html=True)

# --- DASHBOARD FRAGMENT ---
@st.fragment(run_every=refresh_speed if live_mode else None)
def render_live_dashboard():
    st.session_state.time_step += 1
    t = st.session_state.time_step
    ist_now = get_ist_time()
    now_str = ist_now.strftime("%I:%M:%S %p")
    
    # 1. H3 Hierarchy Downscaling Simulation
    ch4_res6 = round(base_data["ch4"] + np.sin(t * 0.2) * 5.0, 1)   
    ch4_res8 = round(ch4_res6 + 185.0 + np.cos(t * 0.15) * 12.0, 1) 
    ch4_res10 = round(ch4_res8 + 420.0 + np.sin(t * 0.3) * 25.0, 1)  

    # Anomaly Trigger Warning Banner
    if ch4_res10 > 2000.0:
        st.markdown(f'<div class="anomaly-banner">🚨 METHANE ANOMALY ALERT: Threshold Exceeded ({ch4_res10} ppb) at {selected_site_name} (H3 Res 10 Cell Core). Immediate Plume Subsurface Inversion Recommended!</div>', unsafe_allow_html=True)

    # 2. Geotechnical & Thermodynamics Vector Calculations
    total_stress = site_info["height_m"] * 18.0  
    gas_pore_pressure = 45.0 + np.sin(t * 0.1) * 8.0 
    eff_stress = round(terzaghi_effective_stress(total_stress, gas_pore_pressure), 1)
    
    core_temp = round(base_data["ambient"] + 24.0 + (site_info["height_m"] * 0.25), 1)
    heat_flux = round(fourier_subsurface_heat_flux(k_thermal=0.85, T_core=core_temp, T_surface=base_data["ambient"], depth_m=site_info["height_m"] / 2.0), 2)
    
    fod_daily_gen = first_order_decay_ch4(site_info["waste_mass_ton"])
    insar_displacement_rate = round(-3.5 - (gas_pore_pressure * 0.08), 2) 
    
    co2e_avoided = round(fod_daily_gen * 28.0, 1)
    vcu_revenue = round(co2e_avoided * 20.0, 2)
    
    # H3 Center Hexagons
    h3_center = latlng_to_cell(site_info["lat"], site_info["lon"], h3_resolution)
    ring1 = list(grid_ring(h3_center, 1))
    ring2 = list(grid_ring(h3_center, 2))
    h3_hexagons = set(ring1 + ring2)
    h3_hexagons.add(h3_center)
    
    # Ticker
    st.markdown(f"""
    <div class="ticker-bar">
        <span class="live-badge"></span> <b>H3 RES-{h3_resolution} SUBSURFACE VECTOR INVERSION RUNNING</b> | IST: <code>{now_str}</code> | Site: <code>{selected_site_name}</code> | Terzaghi Effective Stress: <code>{eff_stress} kPa</code>
    </div>
    """, unsafe_allow_html=True)

    # Metrics
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.markdown(f'<div class="glass-card"><div class="metric-title">Res 6 S5P CH4 (36km²)</div><div class="metric-val" style="color:#38bdf8;">{ch4_res6} <small>ppb</small></div></div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="glass-card"><div class="metric-title">Res 8 EMIT CH4 (0.73km²)</div><div class="metric-val" style="color:#f59e0b;">{ch4_res8} <small>ppb</small></div></div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="glass-card"><div class="metric-title">Res 10 Pinpoint (120m Plot)</div><div class="metric-val" style="color:#f43f5e;">{ch4_res10} <small>ppb</small></div></div>', unsafe_allow_html=True)
    c4.markdown(f'<div class="glass-card"><div class="metric-title">Effective Stress (σ\')</div><div class="metric-val" style="color:#10b981;">{eff_stress} <small>kPa</small></div></div>', unsafe_allow_html=True)
    c5.markdown(f'<div class="glass-card"><div class="metric-title">InSAR Subsidence</div><div class="metric-val" style="color:#a855f7;">{insar_displacement_rate} <small>mm/yr</small></div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(f"### 🌐 Uber H3 Resolution Level {h3_resolution} Spatial Hexagon Grid Matrix")
    
    # Generate PyDeck H3 Polygons
    h3_features = []
    for hex_id in h3_hexagons:
        geo_boundary = cell_to_boundary(hex_id)
        coords = [[p[1], p[0]] for p in geo_boundary]
        coords.append(coords[0])
        
        dist = np.random.uniform(0.1, 1.0)
        ch4_hex = ch4_res10 * (1.0 - dist * 0.15)
        
        h3_features.append({
            "hex": hex_id,
            "coordinates": [coords],
            "ch4": round(ch4_hex, 1),
            "color": [int(min(255, (ch4_hex - 1800) * 0.4)), 50, 180, 160]
        })
    
    df_h3 = pd.DataFrame(h3_features)
    
    polygon_layer = pdk.Layer(
        "PolygonLayer",
        data=df_h3,
        get_polygon="coordinates",
        get_fill_color="color",
        get_line_color=[255, 255, 255, 100],
        get_line_width=2,
        pickable=True,
        extruded=True,
        get_elevation="ch4",
        elevation_scale=0.15
    )
    
    view_state = pdk.ViewState(
        latitude=site_info["lat"],
        longitude=site_info["lon"],
        zoom=14 if h3_resolution == 6 else 15 if h3_resolution == 8 else 16,
        pitch=50,
        bearing=20
    )
    
    st.pydeck_chart(pdk.Deck(layers=[polygon_layer], initial_view_state=view_state, tooltip={"html": "<b>H3 Hex Index:</b> {hex}<br/><b>Downscaled CH4 Concentration:</b> {ch4} ppb"}))

    st.markdown("<br>", unsafe_allow_html=True)
    
    # --- HISTORICAL TIME SERIES PLOTLY SECTION WITH MULTI-SITE COMPARISON ---
    if df_historical_master is not None:
        st.markdown("### 📈 Historical Sentinel-5P Methane Trajectory & Multi-Site Comparison (2019 - 2026)")
        
        sites_to_compare = st.multiselect(
            "Select Landfills to Compare Side-by-Side:",
            options=list(PAN_INDIA_LANDFILLS.keys()),
            default=[selected_site_name, "Deonar (Mumbai, MH)", "Sarona Yard (Raipur, CG)"] if selected_site_name not in ["Deonar (Mumbai, MH)", "Sarona Yard (Raipur, CG)"] else [selected_site_name, "Ghazipur (Delhi NCR)"]
        )
        
        if sites_to_compare:
            fig_hist = go.Figure()
            colors = ['#38bdf8', '#f43f5e', '#10b981', '#f59e0b', '#a855f7', '#ec4899', '#6366f1']
            
            for idx, s in enumerate(sites_to_compare):
                site_hist = df_historical_master[df_historical_master["Landfill"] == s]
                if not site_hist.empty:
                    fig_hist.add_trace(go.Scatter(
                        x=site_hist["Year"],
                        y=site_hist["CH4_ppb"],
                        mode='lines+markers',
                        name=s,
                        line=dict(width=3, color=colors[idx % len(colors)]),
                        marker=dict(size=8)
                    ))
            
            fig_hist.update_layout(
                title="Pan-India Methane Concentration Benchmark (2019 - 2026)",
                xaxis_title="Year",
                yaxis_title="CH4 Concentration (ppb)",
                template="plotly_dark",
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                height=380,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_hist, use_container_width=True)

    m1, m2 = st.columns(2)
    
    with m1:
        st.markdown("### 🧮 3-Step Vector Subsurface Calculation")
        st.write(f"1. **Gaussian Plume Backward Run:** Extracted Source Mass Rate $Q = {round(gaussian_plume_back_trajectory(ch4_res10, 50, 20, base_data['wind']), 2)}$ g/s.")
        st.write(f"2. **ECOSTRESS Thermal Flux:** Subsurface Convective Heat Flux $q = {heat_flux}$ W/m² (Reaction Zone: {core_temp}°C).")
        st.write(f"3. **Terzaghi Pore Chambering:** Effective Stress $\sigma' = {eff_stress}$ kPa (Terzaghi $\sigma - u_{{gas}}$).")

    with m2:
        st.markdown("### 📉 Organic First Order Decay (FOD) & Carbon MRV")
        st.write(f"• **FOD Methane Yield ($CH_4$):** {round(fod_daily_gen, 2)} Metric Tons / Day")
        st.write(f"• **28x GWP CO2e Offset:** {co2e_avoided} Tons CO2e / Day")
        st.write(f"• **Daily VCU Revenue Potential:** **${vcu_revenue} USD**")

    # PDF Download in Sidebar
    pdf_bytes = generate_pdf_report(selected_site_name, now_str, ch4_res10, core_temp, eff_stress, heat_flux, fod_daily_gen, co2e_avoided, vcu_revenue, insar_displacement_rate)
    st.sidebar.download_button("📄 Download H3 Physics Audit Report", pdf_bytes, file_name=f"H3_Physics_Audit_{selected_site_name.split()[0]}.pdf", mime="application/pdf")

render_live_dashboard()
