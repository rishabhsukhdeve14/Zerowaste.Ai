
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
# MULTI-PHYSICS CALCULATIONS
# ============================================================

# 1) Methane signal.
methane_score = (
    0.55 * normalize_0_100(sites["methane_ppb"], low=1800, high=2000)
    + 0.45 * normalize_0_100(sites["methane_anomaly_ppb"], low=0, high=100)
).clip(0, 100)

# 2) Thermal signal.
thermal_score = normalize_0_100(
    sites["thermal_anomaly_c"],
    low=0,
    high=15,
)

# 3) Deformation signal.
deformation_score = normalize_0_100(
    sites["deformation_mm_yr"].abs(),
    low=0,
    high=10,
)

# 4) Moisture signal.
# Moisture is not inherently "bad"; this is only a model input.
moisture_score = normalize_0_100(
    sites["moisture_pct"],
    low=0,
    high=100,
)

# 5) Pressure proxy.
pressure_score = normalize_0_100(
    sites["pressure_psi"],
    low=0,
    high=50,
)

# Multi-physics fusion.
sites["methane_score"] = methane_score.fillna(0)
sites["thermal_score"] = thermal_score.fillna(0)
sites["deformation_score"] = deformation_score.fillna(0)
sites["moisture_score"] = moisture_score.fillna(0)
sites["pressure_score"] = pressure_score.fillna(0)

sites["risk_score"] = (
    0.38 * sites["methane_score"]
    + 0.20 * sites["thermal_score"]
    + 0.18 * sites["deformation_score"]
    + 0.10 * sites["pressure_score"]
    + 0.08 * sites["moisture_score"]
    + 0.06 * normalize_0_100(sites["wind_mps"], 0, 15)
).clip(0, 100)

sites["risk"] = sites["risk_score"].apply(risk_label)


# ============================================================
# PHYSICS FUNCTIONS
# ============================================================

def darcy_velocity(permeability_m2, viscosity_pa_s, pressure_gradient_pa_m):
    """
    Darcy's law:
        u = -(k/mu) grad(P)
    """
    if viscosity_pa_s <= 0:
        return np.nan
    return -(permeability_m2 / viscosity_pa_s) * pressure_gradient_pa_m


def fourier_heat_flux(conductivity_w_mk, temperature_gradient_k_m):
    """
    Fourier's law:
        q = -k grad(T)
    """
    return -conductivity_w_mk * temperature_gradient_k_m


def terzaghi_effective_stress(total_stress_kpa, pore_pressure_kpa):
    """
    Effective stress:
        sigma' = sigma - u
    """
    return total_stress_kpa - pore_pressure_kpa


def mohr_coulomb_shear_strength(cohesion_kpa, effective_stress_kpa, friction_angle_deg):
    """
    Mohr-Coulomb:
        tau = c + sigma' tan(phi)
    """
    return cohesion_kpa + effective_stress_kpa * math.tan(
        math.radians(friction_angle_deg)
    )


def first_order_decay(c0, decay_constant_per_year, years):
    return c0 * math.exp(-decay_constant_per_year * years)


def beer_lambert_transmission(i0, sigma, number_density, path_length):
    return i0 * math.exp(-sigma * number_density * path_length)


def gaussian_plume_centerline(q_kg_s, wind_m_s, sigma_y_m, sigma_z_m):
    """
    Simplified Gaussian plume centerline concentration factor.
    Not a regulatory atmospheric model.
    """
    denom = 2 * math.pi * max(wind_m_s, 0.1) * max(sigma_y_m, 1) * max(sigma_z_m, 1)
    return q_kg_s / denom


def wind_destination(lat, lon, bearing_deg, distance_km):
    """
    Approximate destination point for a map visualization.
    """
    radius_km = 6371.0
    brng = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    d = distance_km / radius_km

    lat2 = math.asin(
        math.sin(lat1) * math.cos(d)
        + math.cos(lat1) * math.sin(d) * math.cos(brng)
    )
    lon2 = lon1 + math.atan2(
        math.sin(brng) * math.sin(d) * math.cos(lat1),
        math.cos(d) - math.sin(lat1) * math.sin(lat2),
    )

    return math.degrees(lat2), math.degrees(lon2)


# ============================================================
# PLUME BACK-TRAJECTORY PROXY
# ============================================================

def add_plume_columns(df):
    out = df.copy()
    out["wind_speed_mps"] = out["wind_mps"].clip(lower=0)
    out["wind_to_deg"] = out["wind_deg"].fillna(0) % 360

    # 30-minute advection distance.
    out["plume_distance_km"] = (
        out["wind_speed_mps"] * 1800.0 / 1000.0
    ).clip(0, 30)

    return out


sites = add_plume_columns(sites)


# ============================================================
# SIMPLE SPATIAL CLUSTERING / MORAN-LIKE SCREEN
# ============================================================

def spatial_cluster_index(df, k=6):
    """
    Lightweight inverse-distance clustering index.
    It is a screening statistic, not a full GIS Moran's I implementation.
    """
    if len(df) < 3:
        return pd.Series(np.zeros(len(df)), index=df.index)

    coords = df[["lat", "lon"]].to_numpy(dtype=float)
    score = df["methane_score"].to_numpy(dtype=float)

    result = np.zeros(len(df))

    for i in range(len(df)):
        d = np.sqrt(
            (coords[:, 0] - coords[i, 0]) ** 2
            + ((coords[:, 1] - coords[i, 1]) * np.cos(np.radians(coords[i, 0]))) ** 2
        )

        order = np.argsort(d)
        neighbors = [j for j in order if j != i][:k]

        if not neighbors:
            continue

        weights = 1.0 / np.maximum(d[neighbors], 0.0001)
        local_mean = np.average(score[neighbors], weights=weights)
        result[i] = max(0.0, local_mean - np.mean(score))

    return pd.Series(result, index=df.index)


sites["spatial_cluster_signal"] = spatial_cluster_index(sites)
sites["spatial_cluster_score"] = normalize_0_100(
    sites["spatial_cluster_signal"],
    low=0,
    high=max(float(sites["spatial_cluster_signal"].max()), 1.0),
)

# Add a small spatial term to the final risk.
sites["risk_score"] = (
    0.94 * sites["risk_score"]
    + 0.06 * sites["spatial_cluster_score"]
).clip(0, 100)
sites["risk"] = sites["risk_score"].apply(risk_label)


# ============================================================
# LONG-HORIZON SCENARIO
# ============================================================

def scenario_forecast(row, years, climate_multiplier=1.0):
    base = float(row["risk_score"])
    methane = float(row["methane_score"])
    thermal = float(row["thermal_score"])
    deform = float(row["deformation_score"])

    # Scenario model:
    # - methane persistence
    # - thermal persistence
    # - deformation trend
    # - a user-selectable climate multiplier
    methane_future = methane * math.exp(-0.018 * years) * climate_multiplier
    thermal_future = thermal * math.exp(0.010 * years) * climate_multiplier
    deformation_future = deform * math.exp(0.012 * years)

    future = (
        0.42 * methane_future
        + 0.25 * thermal_future
        + 0.20 * deformation_future
        + 0.13 * base
    )

    return float(np.clip(future, 0, 100))


sites["forecast_score"] = sites.apply(
    lambda r: scenario_forecast(r, forecast_years, climate_multiplier=1.0),
    axis=1,
)
sites["forecast_risk"] = sites["forecast_score"].apply(risk_label)


# ============================================================
# SIMPLE MASS / VOLUME ESTIMATES
# ============================================================

if "area_ha" not in sites.columns:
    sites["area_ha"] = np.nan
if "height_m" not in sites.columns:
    sites["height_m"] = np.nan
if "mass_mt" not in sites.columns:
    sites["mass_mt"] = np.nan

sites["area_ha"] = sites["area_ha"].fillna(10.0)
sites["height_m"] = sites["height_m"].fillna(20.0)

sites["volume_m3_proxy"] = sites["area_ha"] * 10_000.0 * sites["height_m"]

# Density is deliberately a user-editable engineering proxy.
DEFAULT_DENSITY_T_M3 = 0.65
sites["mass_mt_proxy"] = (
    sites["volume_m3_proxy"] * DEFAULT_DENSITY_T_M3 / 1000.0
)


# ============================================================
# ACTION PROTOCOL
# ============================================================

def action_protocol(row):
    risk = row["risk"]
    actions = []

    if risk == "CRITICAL":
        actions.extend([
            "Independent field verification required.",
            "Review methane/thermal/deformation observations together.",
            "Escalate to qualified site-safety / engineering personnel.",
        ])
    elif risk == "HIGH":
        actions.extend([
            "Prioritise this site for field inspection.",
            "Check gas collection / venting and thermal observations.",
            "Review recent deformation trend before site work.",
        ])
    elif risk == "ELEVATED":
        actions.extend([
            "Increase observation frequency.",
            "Check for persistent methane anomaly and thermal persistence.",
        ])
    else:
        actions.append("Continue routine monitoring.")

    if row["methane_score"] >= 70:
        actions.append("Methane signal is a major contributor to the score.")

    if row["thermal_score"] >= 60:
        actions.append("Thermal anomaly is elevated; verify with appropriate ground data.")

    if row["deformation_score"] >= 60:
        actions.append("Deformation signal is elevated; consult a qualified geotechnical team.")

    return actions


sites["action_protocol"] = sites.apply(action_protocol, axis=1)


# ============================================================
# KPIs
# ============================================================

critical_count = int((sites["risk"] == "CRITICAL").sum())
high_count = int((sites["risk"] == "HIGH").sum())
elevated_count = int((sites["risk"] == "ELEVATED").sum())

latest_label = (
    latest_s5p["text"]
    if latest_s5p is not None
    else "No EE observation connected"
)

c1, c2, c3, c4, c5, c6 = st.columns(6)

c1.metric("Landfill nodes", f"{len(sites):,}")
c2.metric("Critical", f"{critical_count:,}")
c3.metric("High", f"{high_count:,}")
c4.metric("Elevated", f"{elevated_count:,}")
c5.metric("Max CH₄", f"{sites['methane_ppb'].max():.0f} ppb")
c6.metric("Latest S5P", latest_label)


st.markdown(
    f"""
    <div class="card">
    <b>Data mode:</b> {data_source}
    &nbsp;&nbsp; | &nbsp;&nbsp;
    <b>Earth Engine:</b> {"CONNECTED" if EE_OK else "OFFLINE"}
    &nbsp;&nbsp; | &nbsp;&nbsp;
    <b>S5P latest available:</b> {latest_label}
    <br>
    <span class="muted">
    Dashboard refresh is not the same as satellite acquisition. A refreshed page can show
    the same satellite observation until a new scene becomes available.
    </span>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# TABS
# ============================================================

tabs = st.tabs([
    "🧠 Command Center",
    "🛰️ Methane",
    "🔥 Thermal",
    "📡 Subsurface / InSAR",
    "🌬️ Plume Physics",
    "📐 Physics Engine",
    "🔮 Forecast",
    "⚠️ Action Protocol",
    "🧪 Data QA",
])


# ============================================================
# TAB 1: COMMAND CENTER
# ============================================================

with tabs[0]:
    st.markdown('<div class="section-title">Multi-Physics Fusion Matrix</div>',
                unsafe_allow_html=True)

    top = sites.sort_values("risk_score", ascending=False).head(15).copy()

    fig = px.scatter_map(
        top,
        lat="lat",
        lon="lon",
        size="risk_score",
        color="risk_score",
        hover_name="name",
        hover_data={
            "state": True,
            "methane_ppb": ":.0f",
            "methane_anomaly_ppb": ":.1f",
            "thermal_anomaly_c": ":.1f",
            "deformation_mm_yr": ":.2f",
            "risk_score": ":.1f",
            "lat": False,
            "lon": False,
        },
        zoom=4.4,
        height=560,
        color_continuous_scale="Turbo",
        map_style="open-street-map",
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="#030712",
        plot_bgcolor="#030712",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Top-risk nodes")
    top_display = top[
        [
            "name", "state", "methane_ppb",
            "thermal_anomaly_c", "deformation_mm_yr",
            "pressure_psi", "risk_score", "risk",
        ]
    ].copy()

    st.dataframe(
        top_display.round(2),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown(
        """
        <div class="card">
        <b>Fusion logic:</b> methane + thermal + deformation + pressure proxy +
        moisture + wind + local spatial clustering. The score is an internal
        screening index, not a regulatory risk probability.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# TAB 2: METHANE
# ============================================================

with tabs[1]:
    st.markdown("### 🛰️ Methane field")

    a, b, c = st.columns(3)
    a.metric("Mean CH₄", f"{sites['methane_ppb'].mean():.1f} ppb")
    b.metric("Max CH₄", f"{sites['methane_ppb'].max():.1f} ppb")
    c.metric("Mean anomaly", f"{sites['methane_anomaly_ppb'].mean():.1f} ppb")

    fig_m = px.scatter(
        sites.sort_values("methane_ppb", ascending=False),
        x="methane_ppb",
        y="methane_anomaly_ppb",
        size="risk_score",
        color="risk",
        hover_name="name",
        title="Methane concentration vs anomaly",
        color_discrete_map={
            "CRITICAL": "#fb7185",
            "HIGH": "#f97316",
            "ELEVATED": "#fbbf24",
            "LOW": "#22c55e",
            "NO DATA": "#94a3b8",
        },
    )
    st.plotly_chart(fig_m, use_container_width=True)

    st.markdown(
        """
        <div class="card">
        <b>Interpretation:</b> A high atmospheric CH₄ value near a landfill is a
        screening signal. It does not by itself prove source attribution or provide
        a tonnes/hour emission rate. Atmospheric transport, background methane and
        other sources must be considered.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# TAB 3: THERMAL
# ============================================================

with tabs[2]:
    st.markdown("### 🔥 Subsurface thermal / ignition screening")

    t1, t2, t3 = st.columns(3)
    t1.metric("Mean thermal anomaly", f"{sites['thermal_anomaly_c'].mean():.2f} °C")
    t2.metric("Maximum thermal anomaly", f"{sites['thermal_anomaly_c'].max():.2f} °C")
    t3.metric("Thermal-high nodes", f"{int((sites['thermal_score'] >= 60).sum()):,}")

    thermal = sites.sort_values("thermal_anomaly_c", ascending=False).head(20)

    fig_t = go.Figure()
    fig_t.add_trace(
        go.Bar(
            x=thermal["name"],
            y=thermal["thermal_anomaly_c"],
            name="Thermal anomaly",
        )
    )
    fig_t.update_layout(
        title="Highest thermal-anomaly screening values",
        xaxis_title="Site",
        yaxis_title="Anomaly (°C)",
        template="plotly_dark",
    )
    st.plotly_chart(fig_t, use_container_width=True)

    st.markdown(
        """
        <div class="card">
        <b>Physics used in the notebook concept:</b>
        Fourier heat conduction, thermal transport and first-order reaction/decay
        concepts. In this implementation, satellite/CSV thermal values are treated
        as observations or inputs; the app does not claim to directly measure a
        subsurface fire from surface temperature alone.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# TAB 4: SUBSURFACE / INSAR
# ============================================================

with tabs[3]:
    st.markdown("### 📡 Subsurface pressure & deformation")

    s1, s2, s3 = st.columns(3)
    s1.metric("Mean deformation", f"{sites['deformation_mm_yr'].mean():.2f} mm/yr")
    s2.metric("Max deformation", f"{sites['deformation_mm_yr'].abs().max():.2f} mm/yr")
    s3.metric("Mean pressure proxy", f"{sites['pressure_psi'].mean():.2f} psi")

    fig_d = px.scatter(
        sites,
        x="pressure_psi",
        y="deformation_mm_yr",
        size="risk_score",
        color="risk",
        hover_name="name",
        title="Pressure proxy vs deformation",
        color_discrete_map={
            "CRITICAL": "#fb7185",
            "HIGH": "#f97316",
            "ELEVATED": "#fbbf24",
            "LOW": "#22c55e",
            "NO DATA": "#94a3b8",
        },
    )
    st.plotly_chart(fig_d, use_container_width=True)

    st.markdown("#### Effective-stress sandbox")

    e1, e2, e3 = st.columns(3)
    total_stress = e1.number_input(
        "Total overburden stress (kPa)",
        min_value=0.0,
        value=250.0,
    )
    pore_pressure = e2.number_input(
        "Pore pressure (kPa)",
        min_value=0.0,
        value=50.0,
    )
    friction_angle = e3.number_input(
        "Friction angle φ (degrees)",
        min_value=1.0,
        max_value=60.0,
        value=30.0,
    )

    effective = terzaghi_effective_stress(total_stress, pore_pressure)
    shear = mohr_coulomb_shear_strength(20.0, effective, friction_angle)

    q1, q2 = st.columns(2)
    q1.metric("Effective stress σ′", f"{effective:.2f} kPa")
    q2.metric("Mohr-Coulomb shear strength", f"{shear:.2f} kPa")

    st.caption(
        "This is an educational physics sandbox. Actual geotechnical stability "
        "requires site-specific material properties, geometry, groundwater, loads "
        "and qualified engineering analysis."
    )


# ============================================================
# TAB 5: PLUME PHYSICS
# ============================================================

with tabs[4]:
    st.markdown("### 🌬️ Plume transport / back-trajectory proxy")

    selected_site = st.selectbox(
        "Select landfill",
        sites["name"].tolist(),
        index=0,
    )

    row = sites.loc[sites["name"] == selected_site].iloc[0]

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Wind", f"{row['wind_mps']:.1f} m/s")
    p2.metric("Wind-to", f"{row['wind_deg']:.0f}°")
    p3.metric("30-min travel", f"{row['plume_distance_km']:.1f} km")
    p4.metric("CH₄", f"{row['methane_ppb']:.0f} ppb")

    end_lat, end_lon = wind_destination(
        row["lat"],
        row["lon"],
        row["wind_deg"],
        max(row["plume_distance_km"], 1.0),
    )

    plume_df = pd.DataFrame(
        [
            {"lat": row["lat"], "lon": row["lon"], "type": "Landfill"},
            {"lat": end_lat, "lon": end_lon, "type": "Advection endpoint"},
        ]
    )

    fig_p = px.scatter_map(
        plume_df,
        lat="lat",
        lon="lon",
        color="type",
        zoom=10,
        height=480,
        map_style="open-street-map",
    )

    fig_p.add_trace(
        go.Scattermap(
            lat=[row["lat"], end_lat],
            lon=[row["lon"], end_lon],
            mode="lines",
            line=dict(width=4),
            name="Wind transport path",
        )
    )

    fig_p.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="#030712",
    )
    st.plotly_chart(fig_p, use_container_width=True)

    st.markdown("#### Gaussian plume sandbox")

    g1, g2, g3, g4 = st.columns(4)
    q_kg_s = g1.number_input("Q (kg/s)", min_value=0.001, value=0.1)
    wind = g2.number_input("Wind (m/s)", min_value=0.1, value=5.0)
    sigma_y = g3.number_input("σy (m)", min_value=1.0, value=100.0)
    sigma_z = g4.number_input("σz (m)", min_value=1.0, value=80.0)

    centerline = gaussian_plume_centerline(
        q_kg_s, wind, sigma_y, sigma_z
    )

    st.metric(
        "Simplified centerline concentration factor",
        f"{centerline:.6f} kg/m³",
    )

    st.caption(
        "The Gaussian expression is a simplified transport illustration. "
        "It is not a replacement for a regulatory dispersion model."
    )


# ============================================================
# TAB 6: PHYSICS ENGINE
# ============================================================

with tabs[5]:
    st.markdown("### 📐 Physics engine")

    st.markdown("#### Core equations from the ZeroWaste.AI concept")

    eqs = [
        ("Darcy", r"$\vec{u}= -\frac{k}{\mu}\nabla P$",
         "Porous-media gas/fluid transport."),
        ("Fourier", r"$\vec{q}= -k_{th}\nabla T$",
         "Heat conduction."),
        ("Advection–diffusion", r"$\frac{\partial C}{\partial t}+\vec{u}\cdot\nabla C="
         r"\nabla\cdot(D\nabla C)+S-R$",
         "Methane transport / reaction framing."),
        ("Terzaghi", r"$\sigma'=\sigma-u$",
         "Effective stress."),
        ("Mohr–Coulomb", r"$\tau=c+\sigma'\tan(\phi)$",
         "Shear-strength screening."),
        ("First-order decay", r"$C(t)=C_0e^{-kt}$",
         "Long-horizon decay scenario."),
        ("Beer–Lambert", r"$I=I_0e^{-\sigma nL}$",
         "Spectral absorption framing."),
        ("Gaussian plume", r"$C(x,y)\propto\frac{Q}{u\sigma_y\sigma_z}"
         r"e^{-y^2/(2\sigma_y^2)}$",
         "Atmospheric transport proxy."),
    ]

    for name, formula, meaning in eqs:
        st.markdown(
            f"""
            <div class="card">
            <b>{name}</b><br>
            <div style="font-size:1.25rem">{formula}</div>
            <span class="muted">{meaning}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("#### Live calculator")

    c1, c2, c3 = st.columns(3)
    permeability = c1.number_input(
        "Permeability k (m²)",
        min_value=1e-15,
        value=1e-12,
        format="%.2e",
    )
    viscosity = c2.number_input(
        "Gas viscosity μ (Pa·s)",
        min_value=1e-7,
        value=1.8e-5,
        format="%.2e",
    )
    pressure_gradient = c3.number_input(
        "Pressure gradient ∇P (Pa/m)",
        value=100.0,
    )

    velocity = darcy_velocity(
        permeability,
        viscosity,
        pressure_gradient,
    )

    st.metric("Darcy velocity", f"{velocity:.6e} m/s")

    h1, h2 = st.columns(2)
    thermal_k = h1.number_input(
        "Thermal conductivity k_th (W/m/K)",
        min_value=0.01,
        value=0.5,
    )
    temp_gradient = h2.number_input(
        "Temperature gradient ∇T (K/m)",
        value=0.05,
    )

    heat_flux = fourier_heat_flux(
        thermal_k,
        temp_gradient,
    )

    st.metric("Fourier heat flux", f"{heat_flux:.4f} W/m²")


# ============================================================
# TAB 7: FORECAST
# ============================================================

with tabs[6]:
    st.markdown("### 🔮 Scenario engine")

    scenario = st.selectbox(
        "Scenario",
        [
            "Baseline",
            "Moderate persistence",
            "Higher thermal / climate sensitivity",
        ],
    )

    multiplier = {
        "Baseline": 1.0,
        "Moderate persistence": 1.08,
        "Higher thermal / climate sensitivity": 1.18,
    }[scenario]

    years = np.arange(0, forecast_years + 1)

    selected = sites.sort_values("risk_score", ascending=False).head(5)

    fig_f = go.Figure()

    for _, r in selected.iterrows():
        values = [
            scenario_forecast(r, int(y), climate_multiplier=multiplier)
            for y in years
        ]
        fig_f.add_trace(
            go.Scatter(
                x=years,
                y=values,
                mode="lines+markers",
                name=str(r["name"]),
            )
        )

    fig_f.update_layout(
        template="plotly_dark",
        title=f"Risk-screening scenario: {scenario}",
        xaxis_title="Years",
        yaxis_title="Screening score (0–100)",
        yaxis=dict(range=[0, 100]),
    )

    st.plotly_chart(fig_f, use_container_width=True)

    st.warning(
        "This forecast is a scenario model, not a validated prediction of a specific "
        "future event. Do not present the output as a guaranteed year of failure/fire."
    )


# ============================================================
# TAB 8: ACTION PROTOCOL
# ============================================================

with tabs[7]:
    st.markdown("### ⚠️ One-click operator protocol")

    ranked = sites.sort_values("risk_score", ascending=False).copy()

    for _, r in ranked.head(12).iterrows():
        label = r["risk"]
        cls = "red" if label == "CRITICAL" else (
            "amber" if label in ("HIGH", "ELEVATED") else "green"
        )

        st.markdown(
            f"""
            <div class="card">
            <div style="font-size:1.1rem;font-weight:800">
            {risk_symbol(label)} {r['name']}
            <span class="{cls}" style="float:right">
            {label} — {r['risk_score']:.1f}/100
            </span>
            </div>
            <div class="muted">
            CH₄ {r['methane_ppb']:.0f} ppb •
            thermal ΔT {r['thermal_anomaly_c']:.1f} °C •
            deformation {r['deformation_mm_yr']:.2f} mm/yr •
            pressure proxy {r['pressure_psi']:.1f} psi
            </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        for action in r["action_protocol"]:
            st.write("• " + action)

    st.caption(
        "The action protocol is a prioritisation interface. Any physical intervention "
        "must follow the site's qualified safety, environmental and engineering procedures."
    )


# ============================================================
# TAB 9: DATA QA
# ============================================================

with tabs[8]:
    st.markdown("### 🧪 Data quality / provenance")

    quality_rows = []

    for col in [
        "methane_ppb",
        "methane_anomaly_ppb",
        "thermal_anomaly_c",
        "deformation_mm_yr",
        "moisture_pct",
        "pressure_psi",
        "wind_mps",
        "wind_deg",
    ]:
        if col in sites.columns:
            missing_pct = float(sites[col].isna().mean() * 100)
            quality_rows.append({
                "field": col,
                "missing_%": missing_pct,
                "status": "GOOD" if missing_pct < 10 else (
                    "PARTIAL" if missing_pct < 50 else "LOW COVERAGE"
                ),
            })

    qa = pd.DataFrame(quality_rows)

    st.dataframe(
        qa.round(2),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("#### Sensor provenance")

    provenance = pd.DataFrame([
        ["Sentinel-5P / TROPOMI", "Methane atmospheric column", "Measured/ingested when EE connected"],
        ["Sentinel-1 InSAR", "Surface deformation", "Upload/connector required"],
        ["Sentinel-2 MSI", "Surface/land-cover indices", "Upload/connector required"],
        ["NASA EMIT", "Imaging spectroscopy", "Upload/connector required"],
        ["ECOSTRESS", "Thermal information", "Upload/connector required"],
        ["GHGSat", "High-resolution methane", "External/connector data required"],
        ["Wind / weather", "Transport context", "CSV input in this build"],
    ], columns=["source", "role", "current_status"])

    st.dataframe(
        provenance,
        use_container_width=True,
        hide_index=True,
    )

    st.markdown(
        """
        <div class="card">
        <b>Anti-hallucination rule:</b> ZeroWaste.AI should never label a proxy as a
        satellite measurement. Missing sensor layers stay marked as unavailable.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# DOWNLOADS
# ============================================================

st.markdown("---")
st.markdown("### 📦 Export")

export_cols = [
    "name", "state", "lat", "lon",
    "methane_ppb", "methane_anomaly_ppb",
    "thermal_anomaly_c", "deformation_mm_yr",
    "moisture_pct", "pressure_psi",
    "wind_mps", "wind_deg",
    "methane_score", "thermal_score",
    "deformation_score", "pressure_score",
    "spatial_cluster_score",
    "risk_score", "risk",
    "forecast_score", "forecast_risk",
    "area_ha", "height_m",
    "volume_m3_proxy", "mass_mt_proxy",
]

export_cols = [c for c in export_cols if c in sites.columns]
export_df = sites[export_cols].copy()

st.download_button(
    "⬇️ Download ZeroWaste.AI risk dataset",
    export_df.to_csv(index=False).encode("utf-8"),
    file_name="zerowaste_ai_landfill_risk.csv",
    mime="text/csv",
    use_container_width=True,
)

st.markdown(
    """
    <div class="tiny">
    ZeroWaste.AI concept layers represented in this build include multi-sensor fusion,
    physics-informed calculations, plume transport, thermal screening, deformation /
    effective-stress analysis, spatial clustering, long-horizon scenarios and an
    operator-prioritisation interface. The notebook notes describe these as a
    multi-physics architecture rather than a single satellite product.
    </div>
    """,
    unsafe_allow_html=True,
)
