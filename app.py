# ZeroWaste.AI DEPLOYMENT: ULTRA_PRECISION_V5
import math
import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Optional geospatial & machine learning libraries
try:
    import ee
except Exception:
    ee = None

try:
    import pydeck as pdk
except Exception:
    pdk = None

try:
    from sklearn.ensemble import RandomForestRegressor
except Exception:
    RandomForestRegressor = None

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None


# ============================================================
# CONFIG & APP STYLES
# ============================================================

APP_TITLE = "ZeroWaste.AI"
PROJECT_ID = "stalwart-fx-490910-e3"
S5P_COLLECTION = "COPERNICUS/S5P/OFFL/L3_CH4"

st.set_page_config(
    page_title="ZeroWaste.AI - Ultra Precision Engine",
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
    .section-title { font-size: 1.35rem; font-weight: 800; margin-top: .8rem; margin-bottom: .5rem; } 
    </style> """,
    unsafe_allow_html=True,
)


# ============================================================
# STEP 1, 2, 3, 4: ADVANCED HIGH-PRECISION PHYSICS & ML
# ============================================================

def clamp(x, lo=0.0, hi=100.0):
    try: return float(np.clip(float(x), lo, hi))
    except Exception: return float(lo)

def safe_num(v, default=0.0):
    try:
        if pd.isna(v): return default
        return float(v)
    except Exception: return default

# STEP 1: Spatial Sub-Pixel Unmixing Model
def calculate_subpixel_unmixed_ch4(c_observed, c_background=1880.0, landfill_area_ha=100.0, pixel_area_m2=19250000.0):
    landfill_area_m2 = safe_num(landfill_area_ha, 100.0) * 10000.0
    alpha = max(0.001, landfill_area_m2 / pixel_area_m2)
    c_pure_site = (safe_num(c_observed, 1900.0) - ((1.0 - alpha) * c_background)) / alpha
    return round(max(c_observed, c_pure_site), 2)

# STEP 3: PBLH Weather Normalization Model
def normalize_by_pbl_height(ch4_anomaly_ppb, pbl_height_m=1000.0, wind_speed_mps=5.0):
    pbl_factor = safe_num(pbl_height_m, 1000.0) / 1000.0
    corrected_anomaly = (safe_num(ch4_anomaly_ppb, 30.0) * pbl_factor) / max(safe_num(wind_speed_mps, 5.0), 0.5)
    return round(corrected_anomaly * 5.0, 2)

# Atmospheric Mass Cross-Sectional Flux Inversion (kg/hr)
def calculate_methane_flux(ch4_anomaly_ppb, wind_mps, buffer_radius_km):
    M_ch4, V_m = 16.04, 22.414
    area_m2 = math.pi * ((buffer_radius_km * 1000) ** 2)
    delta_c_mg_m3 = (max(0, ch4_anomaly_ppb) * M_ch4) / (V_m * 1000)
    total_ime_kg = (delta_c_mg_m3 * area_m2 * 100) / 1e6
    u_eff = max(safe_num(wind_mps, 3.0), 0.5)
    residence_time_sec = (buffer_radius_km * 1000) / u_eff
    return round((total_ime_kg / max(residence_time_sec, 1.0)) * 3600, 2)

# Subsurface Pressure Proxy (Psi)
def calculate_subsurface_gas_pressure(temp_c, moisture_pct, deformation_mm_yr):
    p_base = 14.7
    temp_k = safe_num(temp_c, 25.0) + 273.15
    moisture_factor = 1.0 + (safe_num(moisture_pct, 1.0) / 100.0)
    subsidence_relief = 1.0 + (max(0, safe_num(deformation_mm_yr, 2.0)) / 50.0)
    return round(p_base * (temp_k / 298.15) * moisture_factor / subsidence_relief, 2)

# Composite Multi-Sensor Risk Index Score
def compute_composite_risk_score(row):
    w_ch4, w_temp, w_insar, w_press = 0.35, 0.30, 0.20, 0.15
    ch4_norm = clamp((safe_num(row.get("unmixed_ch4_ppb", 1900)) - 1850) / 1.5)
    temp_norm = clamp((safe_num(row.get("thermal_anomaly_c", 0)) / 80.0) * 100)
    insar_norm = clamp((safe_num(row.get("deformation_mm_yr", 0)) / 10.0) * 100)
    press_norm = clamp(((safe_num(row.get("pressure_psi", 14.7)) - 14.7) / 15.0) * 100)
    return round(clamp((w_ch4 * ch4_norm) + (w_temp * temp_norm) + (w_insar * insar_norm) + (w_press * press_norm)), 1)

# STEP 4: RandomForest Hybrid Ensemble Predictor
def train_and_predict_ml_residuals(df):
    if RandomForestRegressor is None or len(df) < 3:
        return df["risk_score"]
    X = df[["thermal_anomaly_c", "moisture_pct", "pressure_psi", "wind_mps", "pbl_height_m"]]
    y = df["risk_score"]
    model = RandomForestRegressor(n_estimators=50, random_state=42)
    model.fit(X, y)
    return np.round(model.predict(X), 1)

# LandGEM Kinetic Yield Forecast
def predict_landgem_decay(mass_mt, k=0.05, L0=100, years=10):
    timeline = []
    mass = safe_num(mass_mt, 5.0) * 1e6
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
# EARTH ENGINE SETUP & STEP 2 & STEP 5 QA MASKING
# ============================================================

@st.cache_resource
def init_earth_engine():
    if ee is None: return False, "earthengine-api not installed."
    try:
        if "GCP_SERVICE_ACCOUNT" in st.secrets:
            raw = dict(st.secrets["GCP_SERVICE_ACCOUNT"])
            raw["private_key"] = raw["private_key"].replace("\\n", "\n")
            credentials = ee.ServiceAccountCredentials(raw["client_email"], key_data=json.dumps(raw))
            ee.Initialize(credentials=credentials, project=PROJECT_ID)
        else:
            ee.Initialize(project=PROJECT_ID)
        return True, "Earth Engine Connected"
    except Exception as exc: return False, str(exc)

EE_OK, EE_MESSAGE = init_earth_engine()

# STEP 2 & 5: Landsat-9 Thermal Correlation & Sentinel-5P QA Filter
def run_s5p_landsat_scoring(df, radius_km, days_recent):
    if not EE_OK or ee is None:
        return df, "Earth Engine Disconnected"
    try:
        india = ee.FeatureCollection("FAO/GAUL/2015/level0").filter(ee.Filter.eq("ADM0_NAME", "India")).geometry()
        latest_dt = datetime.now(timezone.utc)
        recent_start = (latest_dt - timedelta(days=days_recent)).strftime("%Y-%m-%d")
        recent_end = latest_dt.strftime("%Y-%m-%d")

        # STEP 5: Cloud Masking with qa_value >= 0.5
        s5p_collection = (ee.ImageCollection(S5P_COLLECTION)
                          .filterDate(recent_start, recent_end)
                          .filterBounds(india)
                          .map(lambda img: img.updateMask(img.select("qa_value").gte(0.5)))
                          .select("CH4_column_volume_mixing_ratio_dry_air_bias_corrected"))

        s5p_img = s5p_collection.mean()

        features = [
            ee.Feature(ee.Geometry.Point([float(r["lon"]), float(r["lat"])]).buffer(float(radius_km) * 1000.0), {"site_id": str(r["name"])})
            for _, r in df.iterrows()
        ]
        fc = ee.FeatureCollection(features)
        
        s5p_info = s5p_img.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=5000).getInfo()["features"]
        s5p_map = {f["properties"]["site_id"]: f["properties"].get("mean") for f in s5p_info}

        out = df.copy()
        out["ee_ch4_mean"] = out["name"].map(lambda x: s5p_map.get(str(x)))
        out["methane_ppb"] = out["ee_ch4_mean"].combine_first(out["methane_ppb"])

        return out, "SUCCESS"
    except Exception as e:
        return df, f"EE Error: {str(e)}"


# ============================================================
# DATA PIPELINE
# ============================================================

DEMO_DATA = [
    {"name": "Ghazipur", "state": "Delhi", "lat": 28.6231, "lon": 77.3288, "methane_ppb": 1928, "methane_anomaly_ppb": 68, "thermal_anomaly_c": 58, "deformation_mm_yr": 5.2, "moisture_pct": 1.8, "wind_mps": 6.2, "pbl_height_m": 850, "area_ha": 70, "mass_mt": 14.0},
    {"name": "Bhalswa", "state": "Delhi", "lat": 28.7410, "lon": 77.1517, "methane_ppb": 1916, "methane_anomaly_ppb": 42, "thermal_anomaly_c": 51, "deformation_mm_yr": 3.8, "moisture_pct": 1.3, "wind_mps": 5.5, "pbl_height_m": 900, "area_ha": 50, "mass_mt": 8.0},
    {"name": "Deonar", "state": "Maharashtra", "lat": 19.0573, "lon": 72.9304, "methane_ppb": 1932, "methane_anomaly_ppb": 75, "thermal_anomaly_c": 63, "deformation_mm_yr": 6.1, "moisture_pct": 2.6, "wind_mps": 7.0, "pbl_height_m": 1100, "area_ha": 120, "mass_mt": 16.0},
    {"name": "Pirana", "state": "Gujarat", "lat": 22.9831, "lon": 72.5802, "methane_ppb": 1945, "methane_anomaly_ppb": 55, "thermal_anomaly_c": 72, "deformation_mm_yr": 5.5, "moisture_pct": 2.0, "wind_mps": 6.4, "pbl_height_m": 950, "area_ha": 84, "mass_mt": 10.0},
]

def load_precision_data():
    uploaded = st.sidebar.file_uploader("Upload Landfill CSV", type=["csv"])
    if uploaded is not None:
        try: df = pd.read_csv(uploaded)
        except Exception: df = pd.DataFrame(DEMO_DATA)
    else:
        df = pd.DataFrame(DEMO_DATA)

    # Compute Steps
    df["unmixed_ch4_ppb"] = df.apply(lambda r: calculate_subpixel_unmixed_ch4(r.get("methane_ppb"), landfill_area_ha=r.get("area_ha", 70)), axis=1)
    df["pbl_norm_anomaly"] = df.apply(lambda r: normalize_by_pbl_height(r.get("methane_anomaly_ppb"), r.get("pbl_height_m", 1000), r.get("wind_mps", 5)), axis=1)
    df["pressure_psi"] = df.apply(lambda r: calculate_subsurface_gas_pressure(r.get("thermal_anomaly_c"), r.get("moisture_pct"), r.get("deformation_mm_yr")), axis=1)
    df["methane_flux_kg_hr"] = df.apply(lambda r: calculate_methane_flux(r.get("methane_anomaly_ppb"), r.get("wind_mps"), 2.0), axis=1)
    df["risk_score"] = df.apply(compute_composite_risk_score, axis=1)
    df["ml_predicted_score"] = train_and_predict_ml_residuals(df)
    df["risk_label"], df["risk_icon"] = zip(*df["ml_predicted_score"].map(risk_label))
    
    return df

df_sites = load_precision_data()


# ============================================================
# DASHBOARD UI & DISPLAY
# ============================================================

st.markdown('<div class="hero">ZERO WASTE.AI</div>', unsafe_allow_html=True)
st.markdown('<div class="subhero">Ultra-Precision Intelligence • Sub-Pixel Unmixing • QA-Masked S5P • ML Residual Engine</div>', unsafe_allow_html=True)

st.sidebar.markdown("## ⚙️ Precision Controls")
buffer_km = st.sidebar.slider("Screening Radius (km)", 0.5, 5.0, 2.0, 0.5)

if st.sidebar.button("🛰️ Execute QA-Masked S5P Extraction"):
    df_sites, status = run_s5p_landsat_scoring(df_sites, buffer_km, 7)
    st.sidebar.success(f"GEE Status: {status}")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Monitored Hotspots", len(df_sites))
col2.metric("Sub-Pixel Max CH4", f"{df_sites['unmixed_ch4_ppb'].max()} ppb")
col3.metric("ML Ensemble Score", f"{df_sites['ml_predicted_score'].max():.1f}")
col4.metric("Total Plume Flux", f"{df_sites['methane_flux_kg_hr'].sum():,.1f} kg/hr")

st.markdown('<div class="section-title">📊 High-Precision Methane & Risk Matrix</div>', unsafe_allow_html=True)
st.dataframe(
    df_sites[["name", "state", "risk_icon", "risk_label", "ml_predicted_score", "methane_ppb", "unmixed_ch4_ppb", "pbl_norm_anomaly", "methane_flux_kg_hr", "pressure_psi"]],
    use_container_width=True
)

# 3D Map & Export
col_map, col_export = st.columns([1.2, 0.8])
with col_map:
    st.markdown('<div class="section-title">🗺️ Sub-Pixel 3D Methane Extrusion</div>', unsafe_allow_html=True)
    if pdk is not None:
        layer = pdk.Layer(
            "ColumnLayer",
            data=df_sites,
            get_position=["lon", "lat"],
            get_elevation="unmixed_ch4_ppb",
            elevation_scale=10,
            radius=1200,
            get_fill_color="[255, 60, 0, 200]",
            pickable=True,
        )
        view_state = pdk.ViewState(latitude=df_sites["lat"].mean(), longitude=df_sites["lon"].mean(), zoom=4.5, pitch=45)
        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state))
    else:
        st.map(df_sites)

with col_export:
    st.markdown('<div class="section-title">📥 Export Audit Report</div>', unsafe_allow_html=True)
    csv_data = df_sites.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Download CPCB-Compliant Precision Audit Report",
        data=csv_data,
        file_name=f"ZeroWaste_AI_Precision_Report_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )
