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
#
# IMPORTANT:
# - Satellite observations are NOT continuous live sensors.
# - Physics equations below are screening / modelling components.
# - They do not constitute a certified emission rate, structural
# engineering report, fire prediction, or emergency instruction.
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
# STYLE
# ============================================================

st.markdown(
    """ <style> .stApp { background: #030712; color: #f8fafc; } [data-testid="stSidebar"] { background: #050b14; } .hero { font-size: 2.45rem; line-height: 1.05; font-weight: 900; background: linear-gradient(90deg,#38bdf8,#00ff99,#f43f5e); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 0.15rem; } .subhero { color: #94a3b8; font-size: 0.95rem; margin-bottom: 1rem; } .card { background: rgba(15,23,42,.86); border: 1px solid rgba(148,163,184,.15); border-radius: 16px; padding: 16px; margin-bottom: 12px; } .green { color: #00ff99; font-weight: 800; } .amber { color: #fbbf24; font-weight: 800; } .red { color: #fb7185; font-weight: 800; } .muted { color: #94a3b8; } .tiny { color: #64748b; font-size: .75rem; } .section-title { font-size: 1.35rem; font-weight: 800; margin-top: .4rem; margin-bottom: .35rem; } .action { background: rgba(127,29,29,.18); border-left: 4px solid #fb7185; padding: 12px 14px; border-radius: 10px; margin: 8px 0; } </style> """,
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
        # Streamlit secrets format:
        # [GCP_SERVICE_ACCOUNT]
        # type = "service_account"
        # project_id = "..."
        # private_key_id = "..."
        # private_key = "-----BEGIN PRIVATE KEY-----\\n..."
        # client_email = "..."
        # client_id = "..."
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
    # UI refresh only. It does NOT create new satellite observations.
    st_autorefresh(interval=10 * 60 * 1000, key="zerowaste_ui_refresh")


# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<div class="hero">ZERO WASTE.AI</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="subhero">Multi-sensor landfill intelligence • methane • thermal • '
    'subsurface pressure proxies • deformation • plume transport • risk screening</div>',
    unsafe_allow_html=True,
)

st.info(
    "Scientific status: this dashboard separates measured/ingested observations from "
    "derived physics and screening proxies. It must not be treated as a certified "
    "emission-rate, fire, slope-failure or emergency-response system."
)

st.markdown(
    ''' <div class="card"> <b>🟢 ZeroWaste.AI engine online</b><br> <span class="muted"> Dashboard analytics are loaded from the built-in demonstration dataset until you upload your landfill CSV. Earth Engine satellite metadata is checked only when you press the S5P button in the sidebar. </span> </div> ''',
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

analysis_days = st.sidebar.slider(
    "S5P recent window (days)",
    min_value=3,
    max_value=30,
    value=7,
)

baseline_days = st.sidebar.slider(
    "Methane baseline (days)",
    min_value=30,
    max_value=180,
    value=60,
)

buffer_km = st.sidebar.slider(
    "Landfill screening radius (km)",
    min_value=0.5,
    max_value=5.0,
    value=2.0,
    step=0.5,
)

forecast_years = st.sidebar.slider(
    "Long-horizon scenario (years)",
    min_value=1,
    max_value=50,
    value=10,
)

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

st.sidebar.caption(
    "Grey sensors can be activated through uploaded data or future connector modules. "
    "The app never fabricates a connected satellite stream."
)


# ============================================================
# DEMO DATA
# ============================================================

DEMO_DATA = [
    {
        "name": "Ghazipur", "state": "Delhi", "lat": 28.6231, "lon": 77.3288,
        "methane_ppb": 1928, "methane_anomaly_ppb": 68, "thermal_anomaly_c": 58,
        "deformation_mm_yr": 5.2, "moisture_pct": 1.8, "pressure_psi": 20,
        "wind_mps": 62, "wind_deg": 8.5
    },
    {
        "name": "Bhalswa", "state": "Delhi", "lat": 28.7410, "lon": 77.1517,
        "methane_ppb": 1916, "methane_anomaly_ppb": 42, "thermal_anomaly_c": 51,
        "deformation_mm_yr": 3.8, "moisture_pct": 1.3, "pressure_psi": 17,
        "wind_mps": 55, "wind_deg": 6.8
    },
    {
        "name": "Okhla", "state": "Delhi", "lat": 28.5303, "lon": 77.2789,
        "methane_ppb": 1909, "methane_anomaly_ppb": 31, "thermal_anomaly_c": 45,
        "deformation_mm_yr": 2.5, "moisture_pct": 1.0, "pressure_psi": 14,
        "wind_mps": 49, "wind_deg": 5.4
    },
    {
        "name": "Deonar", "state": "Maharashtra", "lat": 19.0573, "lon": 72.9304,
        "methane_ppb": 1932, "methane_anomaly_ppb": 75, "thermal_anomaly_c": 63,
        "deformation_mm_yr": 6.1, "moisture_pct": 2.6, "pressure_psi": 24,
        "wind_mps": 70, "wind_deg": 10.1
    },
    {
        "name": "Mulund", "state": "Maharashtra", "lat": 19.1678, "lon": 72.9567,
        "methane_ppb": 1888, "methane_anomaly_ppb": 18, "thermal_anomaly_c": 28,
        "deformation_mm_yr": 2.0, "moisture_pct": 0.8, "pressure_psi": 11,
        "wind_mps": 37, "wind_deg": 4.2
    },
    {
        "name": "Pirana", "state": "Gujarat", "lat": 22.9831, "lon": 72.5802,
        "methane_ppb": 1945, "methane_anomaly_ppb": 55, "thermal_anomaly_c": 72,
        "deformation_mm_yr": 5.5, "moisture_pct": 2.0, "pressure_psi": 22,
        "wind_mps": 64, "wind_deg": 9.0
    },
    {
        "name": "Jawaharnagar", "state": "Telangana", "lat": 17.5147, "lon": 78.5852,
        "methane_ppb": 1896, "methane_anomaly_ppb": 36, "thermal_anomaly_c": 40,
        "deformation_mm_yr": 3.1, "moisture_pct": 1.4, "pressure_psi": 18,
        "wind_mps": 44, "wind_deg": 5.8
    },
    {
        "name": "Kodungaiyur", "state": "Tamil Nadu", "lat": 13.1360, "lon": 80.2640,
        "methane_ppb": 1912, "methane_anomaly_ppb": 49, "thermal_anomaly_c": 54,
        "deformation_mm_yr": 4.0, "moisture_pct": 1.7, "pressure_psi": 20,
        "wind_mps": 52, "wind_deg": 7.0
    },
    {
        "name": "Bidadi", "state": "Karnataka", "lat": 12.7980, "lon": 77.3850,
        "methane_ppb": 1865, "methane_anomaly_ppb": 11, "thermal_anomaly_c": 25,
        "deformation_mm_yr": 1.7, "moisture_pct": 0.5, "pressure_psi": 9,
        "wind_mps": 31, "wind_deg": 3.5
    },
    {
        "name": "Kanjikode", "state": "Kerala", "lat": 10.7867, "lon": 76.6547,
        "methane_ppb": 1879, "methane_anomaly_ppb": 16, "thermal_anomaly_c": 33,
        "deformation_mm_yr": 2.2, "moisture_pct": 0.7, "pressure_psi": 12,
        "wind_mps": 36, "wind_deg": 4.8
    },
]

DEMO_COLUMNS = [
    "name", "state", "lat", "lon",
    "methane_ppb", "methane_anomaly_ppb",
    "thermal_anomaly_c", "deformation_mm_yr",
    "moisture_pct", "pressure_psi",
    "wind_mps", "wind_deg",
]

def demo_dataframe():
    return pd.DataFrame.from_records(DEMO_DATA, columns=DEMO_COLUMNS)


def load_site_data():
    uploaded = st.sidebar.file_uploader(
        "Upload landfill / sensor CSV",
        type=["csv"],
        help=(
            "Recommended columns: name,lat,lon,state,methane_ppb,"
            "methane_anomaly_ppb,thermal_anomaly_c,deformation_mm_yr,"
            "moisture_pct,pressure_psi,wind_mps,wind_deg,area_ha,height_m,mass_mt"
        ),
    )

    if uploaded is None:
        return demo_dataframe(), "DEMO DATA"

    try:
        df = pd.read_csv(uploaded)
    except Exception as exc:
        st.error(f"CSV could not be read: {exc}")
        return demo_dataframe(), "DEMO FALLBACK"

    df.columns = [
        str(c).strip().lower().replace(" ", "_").replace("-", "_")
        for c in df.columns
    ]

    # Flexible aliases.
    aliases = {
        "longitude": "lon",
        "lng": "lon",
        "latitude": "lat",
        "site": "name",
        "landfill": "name",
        "ch4": "methane_ppb",
        "ch4_ppb": "methane_ppb",
        "xch4": "methane_ppb",
        "xch4_ppb": "methane_ppb",
        "ch4_anomaly": "methane_anomaly_ppb",
        "temp_anomaly": "thermal_anomaly_c",
        "temperature_anomaly": "thermal_anomaly_c",
        "insar_mm_yr": "deformation_mm_yr",
        "subsidence_mm_yr": "deformation_mm_yr",
        "moisture": "moisture_pct",
        "pressure": "pressure_psi",
        "wind_speed": "wind_mps",
        "wind_speed_mps": "wind_mps",
    }

    for old, new in aliases.items():
        if old in df.columns and new not in df.columns:
            df[new] = df[old]

    required = {"name", "lat", "lon"}
    missing = required - set(df.columns)
    if missing:
        st.error(
            "CSV is missing required columns: "
            + ", ".join(sorted(missing))
            + ". Using DEMO DATA instead."
        )
        return demo_dataframe(), "DEMO FALLBACK"

    for col in [
        "lat", "lon", "methane_ppb", "methane_anomaly_ppb",
        "thermal_anomaly_c", "deformation_mm_yr", "moisture_pct",
        "pressure_psi", "wind_mps", "wind_deg", "area_ha",
        "height_m", "mass_mt",
    ]:
        if col not in df.columns:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if "state" not in df.columns:
        df["state"] = ""

    df["name"] = df["name"].astype(str)
    df["state"] = df["state"].fillna("").astype(str)

    df = df.dropna(subset=["lat", "lon"]).copy()

    # India bounds.
    df = df[
        df["lat"].between(6, 38)
        & df["lon"].between(68, 98)
    ].copy()

    if df.empty:
        st.error("No valid Indian coordinates found. Using DEMO DATA.")
        return demo_dataframe(), "DEMO FALLBACK"

    return df.reset_index(drop=True), "UPLOADED CSV"


sites, data_source = load_site_data()


# ============================================================
# EARTH ENGINE: LATEST S5P OBSERVATION
# ============================================================

def ee_s5p_latest_info():
    if not EE_OK or ee is None:
        return None

    try:
        india = (
            ee.FeatureCollection("FAO/GAUL/2015/level0")
            .filter(ee.Filter.eq("ADM0_NAME", "India"))
            .geometry()
        )

        collection = (
            ee.ImageCollection(S5P_COLLECTION)
            .filterBounds(india)
            .sort("system:time_start", False)
        )

        image = ee.Image(collection.first())
        millis = image.get("system:time_start").getInfo()
        if millis is None:
            return None

        dt = datetime.fromtimestamp(
            float(millis) / 1000.0,
            tz=timezone.utc,
        )

        bands = image.bandNames().getInfo()
        methane_band = None

        candidates = [
            "CH4_column_volume_mixing_ratio_dry_air_bias_corrected",
            "CH4_column_volume_mixing_ratio_dry_air",
        ]
        for candidate in candidates:
            if candidate in bands:
                methane_band = candidate
                break

        return {
            "datetime": dt,
            "text": dt.strftime("%Y-%m-%d %H:%M UTC"),
            "band": methane_band,
            "bands": bands,
        }
    except Exception:
        return None


# Do not call Earth Engine automatically on every page load.
# The dashboard must render its DEMO/UPLOAD analytics first.
if "latest_s5p" not in st.session_state:
    st.session_state.latest_s5p = None


# ============================================================
# OPTIONAL S5P SITE SCORING
# ============================================================

def run_s5p_site_scoring(df, radius_km, days_recent, days_baseline):
    """ Uses Earth Engine only when the user explicitly requests it. The result is a concentration-screening layer, not an emission-rate inversion. """
    if not EE_OK or ee is None:
        return None, "Earth Engine is not connected."

    if len(df) > 3200:
        return None, "Site count exceeds the configured safety limit of 3,200."

    try:
        india = (
            ee.FeatureCollection("FAO/GAUL/2015/level0")
            .filter(ee.Filter.eq("ADM0_NAME", "India"))
            .geometry()
        )

        base = (
            ee.ImageCollection(S5P_COLLECTION)
            .filterBounds(india)
            .sort("system:time_start", False)
        )

        first = ee.Image(base.first())
        bands = first.bandNames().getInfo()

        methane_band = (
            "CH4_column_volume_mixing_ratio_dry_air_bias_corrected"
            if "CH4_column_volume_mixing_ratio_dry_air_bias_corrected" in bands
            else "CH4_column_volume_mixing_ratio_dry_air"
        )

        uncertainty_band = (
            "CH4_column_volume_mixing_ratio_dry_air_uncertainty"
            if "CH4_column_volume_mixing_ratio_dry_air_uncertainty" in bands
            else None
        )

        latest_ms = first.get("system:time_start").getInfo()
        latest_dt = datetime.fromtimestamp(
            float(latest_ms) / 1000.0,
            tz=timezone.utc,
        )

        recent_start = (latest_dt - timedelta(days=days_recent)).strftime("%Y-%m-%d")
        recent_end = (latest_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        baseline_start = (
            latest_dt - timedelta(days=days_recent + days_baseline)
        ).strftime("%Y-%m-%d")
        baseline_end = recent_start

        recent = (
            ee.ImageCollection(S5P_COLLECTION)
            .filterDate(recent_start, recent_end)
            .filterBounds(india)
            .select(methane_band)
        )

        baseline = (
            ee.ImageCollection(S5P_COLLECTION)
            .filterDate(baseline_start, baseline_end)
            .filterBounds(india)
            .select(methane_band)
        )

        recent_img = recent.mean()
        baseline_img = baseline.mean()
        anomaly_img = recent_img.subtract(baseline_img).rename("ch4_anomaly")

        features = []
        for _, row in df.iterrows():
            props = {"site_id": str(row["name"])}
            features.append(
                ee.Feature(
                    ee.Geometry.Point([float(row["lon"]), float(row["lat"])]).buffer(
                        float(radius_km) * 1000.0
                    ),
                    props,
                )
            )

        fc = ee.FeatureCollection(features)

        reducer = ee.Reducer.mean().combine(
            reducer2=ee.Reducer.max(),
            sharedInputs=True,
        )

        recent_fc = recent_img.reduceRegions(
            collection=fc,
            reducer=reducer,
            scale=1113,
            tileScale=8,
        )

        anomaly_fc = anomaly_img.reduceRegions(
            collection=fc,
            reducer=reducer,
            scale=1113,
            tileScale=8,
        )

        recent_info = recent_fc.getInfo()["features"]
        anomaly_info = anomaly_fc.getInfo()["features"]

        recent_map = {}
        anomaly_map = {}

        for feature in recent_info:
            p = feature.get("properties", {})
            recent_map[str(p.get("site_id"))] = {
                "ee_ch4_mean": p.get("mean"),
                "ee_ch4_max": p.get("max"),
            }

        for feature in anomaly_info:
            p = feature.get("properties", {})
            anomaly_map[str(p.get("site_id"))] = {
                "ee_anomaly_mean": p.get("mean"),
                "ee_anomaly_max": p.get("max"),
            }

        out = df.copy()
        out["ee_ch4_mean"] = out["name"].map(
            lambda x: recent_map.get(str(x), {}).get("ee_ch4_mean")
        )
        out["ee_ch4_max"] = out["name"].map(
            lambda x: recent_map.get(str(x), {}).get("ee_ch4_max")
        )
        out["ee_anomaly_mean"] = out["name"].map(
            lambda x: anomaly_map.get(str(x), {}).get("ee_anomaly_mean")
        )
        out["ee_anomaly_max"] = out["name"].map(
            lambda x: anomaly_map.get(str(x), {}).get("ee_anom