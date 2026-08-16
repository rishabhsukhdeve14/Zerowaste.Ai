
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
#   engineering report, fire prediction, or emergency instruction.
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
    """
    <style>
    .stApp {
        background: #030712;
        color: #f8fafc;
    }
    [data-testid="stSidebar"] {
        background: #050b14;
    }
    .hero {
        font-size: 2.45rem;
        line-height: 1.05;
        font-weight: 900;
        background: linear-gradient(90deg,#38bdf8,#00ff99,#f43f5e);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.15rem;
    }
    .subhero {
        color: #94a3b8;
        font-size: 0.95rem;
        margin-bottom: 1rem;
    }
    .card {
        background: rgba(15,23,42,.86);
        border: 1px solid rgba(148,163,184,.15);
        border-radius: 16px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .green {
        color: #00ff99;
        font-weight: 800;
    }
    .amber {
        color: #fbbf24;
        font-weight: 800;
    }
    .red {
        color: #fb7185;
        font-weight: 800;
    }
    .muted {
        color: #94a3b8;
    }
    .tiny {
        color: #64748b;
        font-size: .75rem;
    }
    .section-title {
        font-size: 1.35rem;
        font-weight: 800;
        margin-top: .4rem;
        margin-bottom: .35rem;
    }
    .action {
        background: rgba(127,29,29,.18);
        border-left: 4px solid #fb7185;
        padding: 12px 14px;
        border-radius: 10px;
        margin: 8px 0;
    }
    </style>
    """,
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

DEMO_ROWS = [
    ["Ghazipur", "Delhi", 28.6231, 77.3288, 1928, 68, 58, 5.2, 1.8, 20, 62, 8.5, 2.1],
    ["Bhalswa", "Delhi", 28.7410, 77.1517, 1916, 42, 51, 3.8, 1.3, 17, 55, 6.8, 1.7],
    ["Okhla", "Delhi", 28.5303, 77.2789, 1909, 31, 45, 2.5, 1.0, 14, 49, 5.4, 1.2],
    ["Deonar", "Maharashtra", 19.0573, 72.9304, 1932, 75, 63, 6.1, 2.6, 24, 70, 10.1, 2.8],
    ["Mulund", "Maharashtra", 19.1678, 72.9567, 1888, 18, 28, 2.0, 0.8, 11, 37, 4.2, 1.1],
    ["Pirana", "Gujarat", 22.9831, 72.5802, 1945, 55, 72, 5.5, 2.0, 22, 64, 9.0, 2.3],
    ["Jawaharnagar", "Telangana", 17.5147, 78.5852, 1896, 36, 40, 3.1, 1.4, 18, 44, 5.8, 1.5],
    ["Kodungaiyur", "Tamil Nadu", 13.1360, 80.2640, 1912, 49, 54, 4.0, 1.7, 20, 52, 7.0, 1.8],
    ["Bidadi", "Karnataka", 12.7980, 77.3850, 1865, 11, 25, 1.7, 0.5, 9, 31, 3.5, 0.8],
    ["Kanjikode", "Kerala", 10.7867, 76.6547, 1879, 16, 33, 2.2, 0.7, 12, 36, 4.8, 1.0],
]

DEMO_COLUMNS = [
    "name", "state", "lat", "lon",
    "methane_ppb", "methane_anomaly_ppb",
    "thermal_anomaly_c", "deformation_mm_yr",
    "moisture_pct", "pressure_psi",
    "wind_mps", "wind_deg",
]


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
        return pd.DataFrame(DEMO_ROWS, columns=DEMO_COLUMNS), "DEMO DATA"

    try:
        df = pd.read_csv(uploaded)
    except Exception as exc:
        st.error(f"CSV could not be read: {exc}")
        return pd.DataFrame(DEMO_ROWS, columns=DEMO_COLUMNS), "DEMO FALLBACK"

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
        return pd.DataFrame(DEMO_ROWS, columns=DEMO_COLUMNS), "DEMO FALLBACK"

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
        return pd.DataFrame(DEMO_ROWS, columns=DEMO_COLUMNS), "DEMO FALLBACK"

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


latest_s5p = ee_s5p_latest_info()


# ============================================================
# OPTIONAL S5P SITE SCORING
# ============================================================

def run_s5p_site_scoring(df, radius_km, days_recent, days_baseline):
    """
    Uses Earth Engine only when the user explicitly requests it.
    The result is a concentration-screening layer, not an emission-rate inversion.
    """
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
            lambda x: anomaly_map.get(str(x), {}).get("ee_anomaly_max")
        )

        return out, None

    except Exception as exc:
        return None, str(exc)


if "ee_scored" not in st.session_state:
    st.session_state.ee_scored = None
if "ee_error" not in st.session_state:
    st.session_state.ee_error = None


st.sidebar.markdown("---")
if mode == "EARTH ENGINE + UPLOAD" and EE_OK:
    if st.sidebar.button("🛰️ Run S5P site scoring", use_container_width=True):
        with st.spinner("Running Sentinel-5P site screening in Earth Engine..."):
            scored, err = run_s5p_site_scoring(
                sites,
                buffer_km,
                analysis_days,
                baseline_days,
            )
            st.session_state.ee_scored = scored
            st.session_state.ee_error = err

if st.session_state.ee_error:
    st.sidebar.error(st.session_state.ee_error)

if st.session_state.ee_scored is not None:
    sites = st.session_state.ee_scored.copy()


# ============================================================
# CREATE SAFE DERIVED FEATURES
# ============================================================

# If Earth Engine values exist, prefer them where available.
if "ee_ch4_mean" in sites.columns:
    sites["methane_ppb"] = sites["ee_ch4_mean"].combine_first(sites["methane_ppb"])

if "ee_anomaly_mean" in sites.columns:
    sites["methane_anomaly_ppb"] = sites["ee_anomaly_mean"].combine_first(
        sites["methane_anomaly_ppb"]
    )


# Demo/proxy values for missing columns.
# These are explicitly labelled as proxies below.
sites["methane_ppb"] = sites["methane_ppb"].fillna(1850)
sites["methane_anomaly_ppb"] = sites["methane_anomaly_ppb"].fillna(
    (sites["methane_ppb"] - 1850).clip(lower=0)
)
sites["thermal_anomaly_c"] = sites["thermal_anomaly_c"].fillna(2.0)
sites["deformation_mm_yr"] = sites["deformation_mm_yr"].fillna(0.5)
sites["moisture_pct"] = sites["moisture_pct"].fillna(15)
sites["pressure_psi"] = sites["pressure_psi"].fillna(5)
sites["wind_mps"] = sites["wind_mps"].fillna(3)
sites["wind_deg"] = sites["wind_deg"].fillna(0)


# ============================================================
# MULTI-PHYSICS CALCULATION