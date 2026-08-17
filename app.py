# ZeroWaste.AI DEPLOYMENT: FULL_INTEGRATED_V4
import math
import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Optional geospatial/satellite engines
try:
    import ee
except Exception:
    ee = None

try:
    import pydeck as pdk
except Exception:
    pdk = None

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None


# ============================================================
# APP CONFIG & STYLES
# ============================================================

APP_TITLE = "ZeroWaste.AI"
PROJECT_ID = "stalwart-fx-490910-e3"
S5P_COLLECTION = "COPERNICUS/S5P/OFFL/L3_CH4"

st.set_page_config(
    page_title="ZeroWaste.AI - Multi-Physics Landfill Intelligence",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """ <style> 
    .stApp { background: #030712; color: #f8fafc; } 
    [data-testid="stSidebar"] { background: #050b14; } 
    .hero { font-size: 2.45rem; line-height: 1.05; font-weight: 900; background: linear-gradient(90deg,#38bdf8,#00ff99,#f43f5e); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 0.15rem; } 
    .subhero { color: #94a3b8; font-size: 0.95rem; margin-bottom: 1rem; } 
    .card { background: rgba(15,23,42,.86); border: 1px solid rgba(148,163,184,.15); border-radius: 16px; padding: 16px; margin-bottom: 12px; } 
    .green { color: #00ff99; font-weight: 800; } 
    .amber { color: #fbbf24; font-weight: 800; } 
    .red { color: #fb7185; font-weight: 800; } 
    .muted { color: #94a3b8; } 
    .section-title { font-size: 1.35rem; font-weight: 800; margin-top: .8rem; margin-bottom: .5rem; } 
    </style> """,
    unsafe_allow_html=True,
)


# ============================================================
# MATHEMATICAL & PHYSICAL PROXIES (UPGRADE 2, 4, 5, 7)
# ============================================================

def clamp(x, lo=0.0, hi=100.0):
    try:
        return float(np.clip(float(x), lo, hi))
    except Exception:
        return float(lo)

def safe_num(v, default=0.0):
    try:
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default

# Upgrade 2: Plume Transport Cross-Sectional Inversion (Flux kg/hr)
def calculate_methane_flux(ch4_anomaly_ppb, wind_mps, buffer_radius_km):
    M_ch4 = 16.04   # g/mol
    V_m = 22.414    # L/mol
    area_m2 = math.pi * ((buffer_radius_km * 1000) ** 2)
    
    delta_c_mg_m3 = (max(0, ch4_anomaly_ppb) * M_ch4) / (V_m * 1000)
    total_ime_kg = (delta_c_mg_m3 * area_m2 * 100) / 1e6
    
    u_eff = max(safe_num(wind_mps, 3.0), 0.5)
    residence_time_sec = (buffer_radius_km * 1000) / u_eff
    flux_kg_hr = (total_ime_kg / max(residence_time_sec, 1.0)) * 3600
    return round(flux_kg_hr, 2)

# Upgrade 4: Subsurface Pressure Proxy (Psi)
def calculate_subsurface_gas_pressure(temp_c, moisture_pct, deformation_mm_yr):
    p_base = 14.7  # baseline atmospheric psi
    temp_k = safe_num(temp_c, 25.0) + 273.15
    moisture_factor = 1.0 + (safe_num(moisture_pct, 1.0) / 100.0)
    subsidence_relief = 1.0 + (max(0, safe_num(deformation_mm_yr, 2.0)) / 50.0)
    
    internal_psi = p_base * (temp_k / 298.15) * moisture_factor / subsidence_relief
    return round(internal_psi, 2)

# Upgrade 5: Composite Multi-Sensor Risk Index Score (0-100)
def compute_composite_risk_score(row):
    w_ch4, w_temp, w_insar, w_press = 0.35, 0.30, 0.20, 0.15
    
    ch4_norm = clamp((safe_num(row.get("methane_anomaly_ppb", 0)) / 100.0) * 100)
    temp_norm = clamp((safe_num(row.get("thermal_anomaly_c", 0)) / 80.0) * 100)
    insar_norm = clamp((safe_num(row.get("deformation_mm_yr", 0)) / 10.0) * 100)
    press_norm = clamp(((safe_num(row.get("pressure_psi", 14.7)) - 14.7) / 15.0) * 100)
    
    total = (w_ch4 * ch4_norm) + (w_temp * temp_norm) + (w_insar * insar_norm) + (w_press * press_norm)
    return round(clamp(total), 1)

# Upgrade 7: US EPA LandGEM Kinetic Decay Projection
def predict_landgem_decay(mass_mt, k=0.05, L0=100, years=10):
    timeline = []
    mass = safe_num(mass_mt, 5.0) * 1e6 # convert MT to metric tons
    for yr in range(1, years + 1):
        yield_m3_yr = k * mass * L0 * math.exp(-k * yr)
        timeline.append({"Year": yr, "CH4_Yield_m3_yr": round(yield_m3_yr, 2)})
    return pd.DataFrame(timeline)

def risk_label(score):
    if score >= 80: return "CRITICAL", "🔴"
    if score >= 65: return "HIGH", "🟠"
    if score >= 45: return "ELEVATED", "🟡"
    return "LOW", "🟢"


# ============================================================
# EARTH ENGINE SETUP (UPGRADE 1 & 8)
# ============================================================

@st.cache_resource
def init_earth_engine():
    if ee is None:
        return False, "earthengine-api not installed."
    try:
        if "GCP_SERVICE_ACCOUNT" in st.secrets:
            raw = dict(st.secrets["GCP_SERVICE_ACCOUNT"])
            raw["private_key"] = raw["private_key"].replace("\\n", "\n")
            credentials = ee.ServiceAccountCredentials(raw["client_email"], key_data=json.dumps(raw))
            ee.Initialize(credentials=credentials, project=PROJECT_ID)
        else:
            ee.Initialize(project=PROJECT_ID)
        return True, "Earth Engine connected."
    except Exception as exc:
        return False, str(exc)

EE_OK, EE_MESSAGE = init_earth_engine()


# Upgrade 1 & 8: Robust Multi-Landfill Earth Engine Zonal Scoring with Fallback
def run_s5p_site_scoring(df, radius_km, days_recent, days_baseline):
    if not EE_OK or ee is None:
        return df, "Earth Engine Disconnected"

    try:
        india = ee.FeatureCollection("FAO/GAUL/2015/level0").filter(ee.Filter.eq("ADM0_NAME", "India")).geometry()
        
        latest_dt = datetime.now(timezone.utc)
        recent_start = (latest_dt - timedelta(days=days_recent)).strftime("%Y-%m-%d")
        recent_end = latest_dt.strftime("%Y-%m-%d")
        baseline_start = (latest_dt - timedelta(days=days_recent + days_baseline)).strftime("%Y-%m-%d")

        recent = ee.ImageCollection(S5P_COLLECTION).filterDate(recent_start, recent_end).filterBounds(india).select("CH4_column_volume_mixing_ratio_dry_air_bias_corrected")
        baseline = ee.ImageCollection(S5P_COLLECTION).filterDate(baseline_start, recent_start).filterBounds(india).select("CH4_column_volume_mixing_ratio_dry_air_bias_corrected")

        recent_img = recent.mean()
        baseline_img = baseline.mean()
        anomaly_img = recent_img.subtract(baseline_img)

        features = [
            ee.Feature(ee.Geometry.Point([float(r["lon"]), float(r["lat"])]).buffer(float(radius_km) * 1000.0), {"site_id": str(r["name"])})
            for _, r in df.iterrows()
        ]
        fc = ee.FeatureCollection(features)
        
        recent_info = recent_img.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=5000).getInfo()["features"]
        anomaly_info = anomaly_img.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=5000).getInfo()["features"]

        recent_map = {f["properties"]["site_id"]: f["properties"].get("mean") for f in recent_info}
        anomaly_map = {f["properties"]["site_id"]: f["properties"].get("mean") for f in anomaly_info}

        out = df.copy()
        out["ee_ch4_mean"] = out["name"].map(lambda x: recent_map.get(str(x)))
        out["ee_anomaly_mean"] = out["name"].map(lambda x: anomaly_map.get(str(x)))

        # Fallback merging
        out["methane_ppb"] = out["ee_ch4_mean"].combine_first(out["methane_ppb"])
        out["methane_anomaly_ppb"] = out["ee_anomaly_mean"].combine_first(out["methane_anomaly_ppb"])

        return out, "SUCCESS"
    except Exception as e:
        return df, f"EE Error: {str(e)}"


# ============================================================
# DATA INGESTION & DEMO PIPELINE
# ============================================================

DEMO_DATA = [
    {"name": "Ghazipur", "state": "Delhi", "lat": 28.6231, "lon": 77.3288, "methane_ppb": 1928, "methane_anomaly_ppb": 68, "thermal_anomaly_c": 58, "deformation_mm_yr": 5.2, "moisture_pct": 1.8, "wind_mps": 6.2, "mass_mt": 14.0},
    {"name": "Bhalswa", "state": "Delhi", "lat": 28.7410, "lon": 77.1517, "methane_ppb": 1916, "methane_anomaly_ppb": 42, "thermal_anomaly_c": 51, "deformation_mm_yr": 3.8, "moisture_pct": 1.3, "wind_mps": 5.5, "mass_mt": 8.0},
    {"name": "Okhla", "state": "Delhi", "lat": 28.5303, "lon": 77.2789, "methane_ppb": 1909, "methane_anomaly_ppb": 31, "thermal_anomaly_c": 45, "deformation_mm_yr": 2.5, "moisture_pct": 1.0, "wind_mps": 4.9, "mass_mt": 6.0},
    {"name": "Deonar", "state": "Maharashtra", "lat": 19.0573, "lon": 72.9304, "methane_ppb": 1932, "methane_anomaly_ppb": 75, "thermal_anomaly_c": 63, "deformation_mm_yr": 6.1, "moisture_pct": 2.6, "wind_mps": 7.0, "mass_mt": 16.0},
    {"name": "Mulund", "state": "Maharashtra", "lat": 19.1678, "lon": 72.9567, "methane_ppb": 1888, "methane_anomaly_ppb": 18, "thermal_anomaly_c": 28, "deformation_mm_yr": 2.0, "moisture_pct": 0.8, "wind_mps": 3.7, "mass_mt": 7.0},
    {"name": "Pirana", "state": "Gujarat", "lat": 22.9831, "lon": 72.5802, "methane_ppb": 1945, "methane_anomaly_ppb": 55, "thermal_anomaly_c": 72, "deformation_mm_yr": 5.5, "moisture_pct": 2.0, "wind_mps": 6.4, "mass_mt": 10.0},
    {"name": "Jawaharnagar", "state": "Telangana", "lat": 17.5147, "lon": 78.5852, "methane_ppb": 1896, "methane_anomaly_ppb": 36, "thermal_anomaly_c": 40, "deformation_mm_yr": 3.1, "moisture_pct": 1.4, "wind_mps": 4.4, "mass_mt": 12.0},
    {"name": "Kodungaiyur", "state": "Tamil Nadu", "lat": 13.1360, "lon": 80.2640, "methane_ppb": 1912, "methane_anomaly_ppb": 49, "thermal_anomaly_c": 54, "deformation_mm_yr": 4.0, "moisture_pct": 1.7, "wind_mps": 5.2, "mass_mt": 9.0},
]

def load_processed_data():
    uploaded = st.sidebar.file_uploader("Upload Landfill CSV", type=["csv"])
    if uploaded is not None:
        try:
            df = pd.read_csv(uploaded)
        except Exception:
            df = pd.DataFrame(DEMO_DATA)
    else:
        df = pd.DataFrame(DEMO_DATA)

    # Calculate Multi-Physics Derived Features
    df["pressure_psi"] = df.apply(lambda r: calculate_subsurface_gas_pressure(r.get("thermal_anomaly_c"), r.get("moisture_pct"), r.get("deformation_mm_yr")), axis=1)
    df["methane_flux_kg_hr"] = df.apply(lambda r: calculate_methane_flux(r.get("methane_anomaly_ppb"), r.get("wind_mps"), 2.0), axis=1)
    df["risk_score"] = df.apply(compute_composite_risk_score, axis=1)
    df["risk_label"], df["risk_icon"] = zip(*df["risk_score"].map(risk_label))
    
    return df

df_sites = load_processed_data()


# ============================================================
# HEADER & SIDEBAR UI
# ============================================================

st.markdown('<div class="hero">ZERO WASTE.AI</div>', unsafe_allow_html=True)
st.markdown('<div class="subhero">Multi-Sensor Landfill Intelligence • TROPOMI • Subsurface Pressure • Plume Flux Inversion</div>', unsafe_allow_html=True)

st.sidebar.markdown("## ⚙️ Dashboard Controls")
buffer_km = st.sidebar.slider("Screening Radius (km)", 0.5, 5.0, 2.0, 0.5)
forecast_years = st.sidebar.slider("LandGEM Projection (Years)", 1, 30, 10)

if st.sidebar.button("🛰️ Trigger Sentinel-5P GEE Extraction"):
    df_sites, status = run_s5p_site_scoring(df_sites, buffer_km, 7, 60)
    st.sidebar.success(f"GEE Fetch Status: {status}")


# ============================================================
# MAIN METRICS & RISK MATRIX
# ============================================================

col1, col2, col3, col4 = st.columns(4)
col1.metric("Monitored Sites", len(df_sites))
col2.metric("Critical Sites", len(df_sites[df_sites["risk_label"] == "CRITICAL"]))
col3.metric("Peak CH4 Anomaly", f"{df_sites['methane_anomaly_ppb'].max()} ppb")
col4.metric("Total Plume Flux", f"{df_sites['methane_flux_kg_hr'].sum():,.1f} kg/hr")

st.markdown('<div class="section-title">📍 High-Risk Landfill Intelligence Matrix</div>', unsafe_allow_html=True)
st.dataframe(
    df_sites[["name", "state", "risk_icon", "risk_label", "risk_score", "methane_ppb", "methane_anomaly_ppb", "methane_flux_kg_hr", "thermal_anomaly_c", "pressure_psi"]],
    use_container_width=True
)


# ============================================================
# VISUALIZATIONS (UPGRADE 6 & 9)
# ============================================================

col_left, col_right = st.columns([1.2, 0.8])

with col_left:
    st.markdown('<div class="section-title">🗺️ 3D Geospatial Methane Volumetric Extrusion</div>', unsafe_allow_html=True)
    # Upgrade 6: PyDeck 3D Visualizer
    if pdk is not None:
        layer = pdk.Layer(
            "ColumnLayer",
            data=df_sites,
            get_position=["lon", "lat"],
            get_elevation="methane_anomaly_ppb",
            elevation_scale=50,
            radius=1500,
            get_fill_color="[255, 100, 50, 200]",
            pickable=True,
            auto_highlight=True,
        )
        view_state = pdk.ViewState(latitude=df_sites["lat"].mean(), longitude=df_sites["lon"].mean(), zoom=4.5, pitch=45)
        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state))
    else:
        st.map(df_sites)

with col_right:
    st.markdown('<div class="section-title">⚠️ Operational Action Triggers</div>', unsafe_allow_html=True)
    # Upgrade 9: Emergency Action Matrix
    for _, site in df_sites[df_sites["risk_score"] >= 60].iterrows():
        st.error(f"**{site['name']} ({site['state']})** - Score: {site['risk_score']}\n"
                 f"• Gas Pressure: {site['pressure_psi']} psi | Flux: {site['methane_flux_kg_hr']} kg/hr\n"
                 f"• **Action:** Initiate methane flare extraction & apply soil cap sealing.")


# ============================================================
# LANDGEM DECAY FORECAST & CSV REPORT EXPORT (UPGRADE 7 & 10)
# ============================================================

st.markdown('<div class="section-title">📉 Long-Horizon LandGEM Kinetics & Export</div>', unsafe_allow_html=True)

selected_site = st.selectbox("Select Landfill Site for 10-Year Kinetic Model", df_sites["name"].tolist())
site_row = df_sites[df_sites["name"] == selected_site].iloc[0]

df_landgem = predict_landgem_decay(site_row.get("mass_mt", 10.0), years=forecast_years)
fig = px.line(df_landgem, x="Year", y="CH4_Yield_m3_yr", title=f"Predicted Methane Generation Curve for {selected_site}", markers=True)
st.plotly_chart(fig, use_container_width=True)

# Upgrade 10: Standardized CSV Audit Report Download
csv_data = df_sites.to_csv(index=False).encode('utf-8')
st.download_button(
    label="📥 Download Official CPCB Landfill Intelligence Audit Report (CSV)",
    data=csv_data,
    file_name=f"ZeroWaste_AI_Audit_Report_{datetime.now().strftime('%Y%m%d')}.csv",
    mime="text/csv",
)
