# ZeroWaste.AI DEPLOYMENT: FIXED_DATA_SCHEMA_V3

import math
import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Optional packages. The app stays usable in DEMO/UPLOAD mode if these are missing.
try:
    import ee
except Exception:
    ee = None

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None


# ============================================================
# ZERO WASTE.AI
# Multi-Physics + Multi-Sensor Landfill Intelligence Dashboard
# ============================================================

APP_TITLE = "ZeroWaste.AI"
PROJECT_ID = "stalwart-fx-490910-e3"

# Earth Engine Sentinel-5P methane collection.
S5P_COLLECTION = "COPERNICUS/S5P/OFFL/L3_CH4"

st.set_page_config(
    page_title="ZeroWaste.AI",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# STYLE (FIXED UNTERMINATED STRINGS)
# ============================================================

st.markdown(
    """<style> 
    .stApp { background: #030712; color: #f8fafc; } 
    [data-testid="stSidebar"] { background: #050b14; } 
    .hero { font-size: 2.45rem; line-height: 1.05; font-weight: 900; background: linear-gradient(90deg,#38bdf8,#00ff99,#f43f5e); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 0.15rem; } 
    .subhero { color: #94a3b8; font-size: 0.95rem; margin-bottom: 1rem; } 
    .card { background: rgba(15,23,42,.86); border: 1px solid rgba(148,163,184,.15); border-radius: 16px; padding: 16px; margin-bottom: 12px; } 
    .green { color: #00ff99; font-weight: 800; } 
    .amber { color: #fbbf24; font-weight: 800; } 
    .red { color: #fb7185; font-weight: 800; } 
    .muted { color: #94a3b8; } 
    .tiny { color: #64748b; font-size: .75rem; } 
    .section-title { font-size: 1.35rem; font-weight: 800; margin-top: .4rem; margin-bottom: .35rem; } 
    .action { background: rgba(127,29,29,.18); border-left: 4px solid #fb7185; padding: 12px 14px; border-radius: 10px; margin: 8px 0; } 
    </style>""",
    unsafe_allow_html=True,
)


# ============================================================
# HELPERS
# ============================================================

def clamp(x, lo=0.0, hi=100.0):
    try:
        return float(np.clip(float(x), lo, hi))
    except Exception:
        return float(lo)


def safe_num(v, default=np.nan):
    try:
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def normalize_0_100(series, low=None, high=None):
    s = pd.to_numeric(series, errors="coerce")
    if low is None:
        low = float(s.quantile(0.05)) if s.notna().any() else 0.0
    if high is None:
        high = float(s.quantile(0.95)) if s.notna().any() else 1.0
    if not np.isfinite(low):
        low = 0.0
    if not np.isfinite(high) or high <= low:
        high = low + 1.0
    return ((s - low) / (high - low) * 100.0).clip(0, 100)


def risk_label(score):
    if not np.isfinite(score):
        return "NO DATA"
    if score >= 80:
        return "CRITICAL"
    if score >= 65:
        return "HIGH"
    if score >= 45:
        return "ELEVATED"
    return "LOW"


def risk_symbol(label):
    return {
        "CRITICAL": "🔴",
        "HIGH": "🟠",
        "ELEVATED": "🟡",
        "LOW": "🟢",
        "NO DATA": "⚪",
    }.get(label, "⚪")


def finite_or_zero(x):
    return float(x) if np.isfinite(x) else 0.0


# ============================================================
# EARTH ENGINE
# ============================================================

@st.cache_resource
def init_earth_engine():
    if ee is None:
        return False, "earthengine-api is not installed."

    try:
        if "GCP_SERVICE_ACCOUNT" in st.secrets:
            raw = dict(st.secrets["GCP_SERVICE_ACCOUNT"])
            raw["private_key"] = raw["private_key"].replace("\\n", "\n")
            credentials = ee.ServiceAccountCredentials(
                raw["client_email"],
                key_data=json.dumps(raw),
            )
            ee.Initialize(credentials=credentials, project=PROJECT_ID)
        else:
            ee.Initialize(project=PROJECT_ID)

        return True, "Earth Engine connected."
    except Exception as exc:
        return False, str(exc)


EE_OK, EE_MESSAGE = init_earth_engine()


# ============================================================
# OPTIONAL AUTO REFRESH
# ============================================================

if st_autorefresh is not None:
    st_autorefresh(interval=10 * 60 * 1000, key="zerowaste_ui_refresh")


# ============================================================
# HEADER
# ============================================================

st.markdown('<div class="hero">ZERO WASTE.AI</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="subhero">Multi-sensor landfill intelligence • methane • thermal • subsurface pressure proxies • deformation • plume transport • risk screening</div>',
    unsafe_allow_html=True,
)

st.info(
    "Scientific status: this dashboard separates measured/ingested observations from derived physics and screening proxies. It must not be treated as a certified emission-rate, fire, slope-failure or emergency-response system."
)

st.markdown(
    '<div class="card"><b>🟢 ZeroWaste.AI engine online</b><br><span class="muted">Dashboard analytics are loaded from the built-in demonstration dataset until you upload your landfill CSV. Earth Engine satellite metadata is checked only when you press the S5P button in the sidebar.</span></div>',
    unsafe_allow_html=True,
)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.markdown("## ⚙️ ZeroWaste.AI Controls")

mode = st.sidebar.radio(
    "Data mode",
    ["UPLOAD / DEMO", "EARTH ENGINE + UPLOAD"],
    index=0 if not EE_OK else 1,
)

analysis_days = st.sidebar.slider("S5P recent window (days)", 3, 30, 7)
baseline_days = st.sidebar.slider("Methane baseline (days)", 30, 180, 60)
buffer_km = st.sidebar.slider("Landfill screening radius (km)", 0.5, 5.0, 2.0, 0.5)
forecast_years = st.sidebar.slider("Long-horizon scenario (years)", 1, 50, 10)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🛰️ Sensor stack")

sensor_status = {
    "Sentinel-5P / TROPOMI": EE_OK,
    "Sentinel-1 InSAR": False,
    "Sentinel-2 MSI": False,
    "NASA EMIT": False,
    "ECOSTRESS": False,
    "GHGSat": False,
}

for sensor_name, connected in sensor_status.items():
    st.sidebar.write(("🟢 " if connected else "⚪ ") + sensor_name)

st.sidebar.caption("Grey sensors can be activated through uploaded data or future connector modules.")


# ============================================================
# DEMO DATA
# ============================================================

DEMO_DATA = [
    {"name": "Ghazipur", "state": "Delhi", "lat": 28.6231, "lon": 77.3288, "methane_ppb": 1928, "methane_anomaly_ppb": 68, "thermal_anomaly_c": 58, "deformation_mm_yr": 5.2, "moisture_pct": 1.8, "pressure_psi": 20, "wind_mps": 62, "wind_deg": 8.5},
    {"name": "Bhalswa", "state": "Delhi", "lat": 28.7410, "lon": 77.1517, "methane_ppb": 1916, "methane_anomaly_ppb": 42, "thermal_anomaly_c": 51, "deformation_mm_yr": 3.8, "moisture_pct": 1.3, "pressure_psi": 17, "wind_mps": 55, "wind_deg": 6.8},
    {"name": "Okhla", "state": "Delhi", "lat": 28.5303, "lon": 77.2789, "methane_ppb": 1909, "methane_anomaly_ppb": 31, "thermal_anomaly_c": 45, "deformation_mm_yr": 2.5, "moisture_pct": 1.0, "pressure_psi": 14, "wind_mps": 49, "wind_deg": 5.4},
    {"name": "Deonar", "state": "Maharashtra", "lat": 19.0573, "lon": 72.9304, "methane_ppb": 1932, "methane_anomaly_ppb": 75, "thermal_anomaly_c": 63, "deformation_mm_yr": 6.1, "moisture_pct": 2.6, "pressure_psi": 24, "wind_mps": 70, "wind_deg": 10.1},
    {"name": "Mulund", "state": "Maharashtra", "lat": 19.1678, "lon": 72.9567, "methane_ppb": 1888, "methane_anomaly_ppb": 18, "thermal_anomaly_c": 28, "deformation_mm_yr": 2.0, "moisture_pct": 0.8, "pressure_psi": 11, "wind_mps": 37, "wind_deg": 4.2},
    {"name": "Pirana", "state": "Gujarat", "lat": 22.9831, "lon": 72.5802, "methane_ppb": 1945, "methane_anomaly_ppb": 55, "thermal_anomaly_c": 72, "deformation_mm_yr": 5.5, "moisture_pct": 2.0, "pressure_psi": 22, "wind_mps": 64, "wind_deg": 9.0},
    {"name": "Jawaharnagar", "state": "Telangana", "lat": 17.5147, "lon": 78.5852, "methane_ppb": 1896, "methane_anomaly_ppb": 36, "thermal_anomaly_c": 40, "deformation_mm_yr": 3.1, "moisture_pct": 1.4, "pressure_psi": 18, "wind_mps": 44, "wind_deg": 5.8},
    {"name": "Kodungaiyur", "state": "Tamil Nadu", "lat": 13.1360, "lon": 80.2640, "methane_ppb": 1912, "methane_anomaly_ppb": 49, "thermal_anomaly_c": 54, "deformation_mm_yr": 4.0, "moisture_pct": 1.7, "pressure_psi": 20, "wind_mps": 52, "wind_deg": 7.0},
    {"name": "Bidadi", "state": "Karnataka", "lat": 12.7980, "lon": 77.3850, "methane_ppb": 1865, "methane_anomaly_ppb": 11, "thermal_anomaly_c": 25, "deformation_mm_yr": 1.7, "moisture_pct": 0.5, "pressure_psi": 9, "wind_mps": 31, "wind_deg": 3.5},
    {"name": "Kanjikode", "state": "Kerala", "lat": 10.7867, "lon": 76.6547, "methane_ppb": 1879, "methane_anomaly_ppb": 16, "thermal_anomaly_c": 33, "deformation_mm_yr": 2.2, "moisture_pct": 0.7, "pressure_psi": 12, "wind_mps": 36, "wind_deg": 4.8},
]

DEMO_COLUMNS = ["name", "state", "lat", "lon", "methane_ppb", "methane_anomaly_ppb", "thermal_anomaly_c", "deformation_mm_yr", "moisture_pct", "pressure_psi", "wind_mps", "wind_deg"]

def demo_dataframe():
    return pd.DataFrame.from_records(DEMO_DATA, columns=DEMO_COLUMNS)

def load_site_data():
    uploaded = st.sidebar.file_uploader("Upload landfill / sensor CSV", type=["csv"])
    if uploaded is None:
        return demo_dataframe(), "DEMO DATA"
    try:
        df = pd.read_csv(uploaded)
        df.columns = [str(c).strip().lower().replace(" ", "_").replace("-", "_") for c in df.columns]
        aliases = {"longitude": "lon", "lng": "lon", "latitude": "lat", "site": "name", "landfill": "name", "ch4": "methane_ppb", "ch4_ppb": "methane_ppb"}
        for old, new in aliases.items():
            if old in df.columns and new not in df.columns:
                df[new] = df[old]
        for col in ["lat", "lon", "methane_ppb", "thermal_anomaly_c", "deformation_mm_yr", "pressure_psi", "wind_mps"]:
            if col not in df.columns:
                df[col] = np.nan
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["name"] = df["name"].astype(str)
        return df.dropna(subset=["lat", "lon"]).reset_index(drop=True), "UPLOADED CSV"
    except Exception:
        return demo_dataframe(), "DEMO FALLBACK"

sites, data_source = load_site_data()

# ============================================================
# MULTI-PHYSICS INFERENCE & METRIC CALCULATIONS
# ============================================================

def calculate_physics_and_risk(df):
    data = df.copy()
    data["wind_mps_clean"] = data["wind_mps"].apply(lambda x: safe_num(x, default=5.0))
    data["advection_distance_30m_km"] = (data["wind_mps_clean"] * 1800.0) / 1000.0
    data["effective_ch4"] = data["methane_ppb"].apply(lambda x: safe_num(x, default=1850.0))
    data["subsurface_pressure_proxy_psi"] = data["pressure_psi"].fillna(data["effective_ch4"] * 0.01)

    ch4_norm = normalize_0_100(data["effective_ch4"], 1800, 2200)
    thermal_norm = normalize_0_100(data["thermal_anomaly_c"].fillna(20), 10, 80)
    insar_norm = normalize_0_100(data["deformation_mm_yr"].fillna(1.0), 0, 10)
    pressure_norm = normalize_0_100(data["subsurface_pressure_proxy_psi"], 5, 40)

    data["composite_risk_score"] = (ch4_norm * 0.35 + thermal_norm * 0.25 + insar_norm * 0.20 + pressure_norm * 0.20).apply(clamp)
    data["risk_level"] = data["composite_risk_score"].apply(risk_label)
    data["risk_badge"] = data["composite_risk_score"].apply(risk_symbol)
    return data

processed_sites = calculate_physics_and_risk(sites)

# ============================================================
# DASHBOARD LAYOUT & METRICS
# ============================================================

st.markdown("<div class='section-title'>📊 Regional Screening Overview</div>", unsafe_allow_html=True)
k1, k2, k3, k4 = st.columns(4)
k1.metric("Ingested Sites", f"{len(processed_sites)}")
k2.metric("Data Provenance", data_source)
k3.metric("Critical Risk Sites", f"{len(processed_sites[processed_sites['risk_level'] == 'CRITICAL'])}")
k4.metric("Earth Engine Status", "ONLINE" if EE_OK else "OFFLINE")

st.markdown("---")
st.markdown("<div class='section-title'>🗺️ Spatial Map & Dynamic Vector</div>", unsafe_allow_html=True)

fig_map = px.scatter_mapbox(
    processed_sites,
    lat="lat",
    lon="lon",
    hover_name="name",
    hover_data=["methane_ppb", "thermal_anomaly_c", "composite_risk_score"],
    color="composite_risk_score",
    color_continuous_scale="Reds",
    size="composite_risk_score",
    size_max=18,
    zoom=4,
    mapbox_style="carto-darkmatter",
)
fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
st.plotly_chart(fig_map, use_container_width=True)

st.dataframe(processed_sites[["name", "lat", "lon", "methane_ppb", "thermal_anomaly_c", "composite_risk_score", "risk_level"]])
