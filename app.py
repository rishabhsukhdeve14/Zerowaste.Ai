# ============================================================
# ZERO WASTE SOLUTIONS
# INDIA METHANE INTELLIGENCE PLATFORM
#
# Sentinel-5P/TROPOMI CH4
# Sentinel-2 Surface Intelligence
# ERA5 Wind Transport Context
#
# Features:
# - Latest available satellite observation
# - CH4 quality filtering
# - Recent median CH4
# - Historical baseline
# - CH4 anomaly
# - Z-score
# - Temporal persistence
# - Spatial contrast
# - Wind speed/direction
# - Evidence score
# - Confidence score
# - India-wide landfill ranking
# - Interactive methane map
# - Sentinel-2 deep scan
# - CSV export
# - Auto refresh
#
# IMPORTANT:
# This is a methane screening/source-attribution system.
# It does NOT claim exact tonnes/hour from TROPOMI alone.
# ============================================================

import json
from datetime import datetime, timedelta, timezone

import ee
import folium
import numpy as np
import pandas as pd
import streamlit as st

from folium import plugins
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh


# ============================================================
# CONFIG
# ============================================================

PROJECT_ID = "stalwart-fx-490910-e3"

S5P_DATASET = "COPERNICUS/S5P/OFFL/L3_CH4"
S2_DATASET = "COPERNICUS/S2_SR_HARMONIZED"
S2_CLOUD_DATASET = "COPERNICUS/S2_CLOUD_PROBABILITY"
ERA5_DATASET = "ECMWF/ERA5/HOURLY"

CH4_BAND = (
    "CH4_column_volume_mixing_ratio_dry_air_bias_corrected"
)

CH4_UNCERTAINTY = (
    "CH4_column_volume_mixing_ratio_dry_air_uncertainty"
)

S5P_SCALE = 1113
S2_SCALE = 10
ERA5_SCALE = 27830

INDIA_MIN_LAT = 6
INDIA_MAX_LAT = 38
INDIA_MIN_LON = 68
INDIA_MAX_LON = 98

DEFAULT_REFRESH = 15


# ============================================================
# STREAMLIT
# ============================================================

st.set_page_config(
    page_title="Zero Waste Solutions — Methane Intelligence",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
    <style>

    .stApp {
        background:
        radial-gradient(
            circle at 90% 0%,
            rgba(14,165,233,0.12),
            transparent 30%
        ),
        radial-gradient(
            circle at 10% 20%,
            rgba(16,185,129,0.08),
            transparent 25%
        ),
        #020617;

        color:#f8fafc;
    }

    .hero {
        font-size:2.25rem;
        font-weight:950;
        letter-spacing:-0.8px;

        background:
        linear-gradient(
            90deg,
            #38bdf8,
            #22c55e,
            #f43f5e
        );

        -webkit-background-clip:text;
        -webkit-text-fill-color:transparent;
    }

    .subtitle {
        color:#94a3b8;
        margin-bottom:18px;
    }

    .card {
        background:rgba(15,23,42,0.86);
        border:1px solid rgba(148,163,184,0.13);
        border-radius:16px;
        padding:16px;
        box-shadow:0 10px 35px rgba(0,0,0,0.25);
    }

    .info {
        background:rgba(14,116,144,0.14);
        border-left:5px solid #38bdf8;
        border-radius:9px;
        padding:14px;
        margin:12px 0;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# EARTH ENGINE INITIALIZATION
# ============================================================

@st.cache_resource
def init_earth_engine():

    try:

        if "GCP_SERVICE_ACCOUNT" in st.secrets:

            key = dict(
                st.secrets["GCP_SERVICE_ACCOUNT"]
            )

            if "private_key" in key:

                key["private_key"] = (
                    key["private_key"]
                    .replace("\\n", "\n")
                )

            credentials = ee.ServiceAccountCredentials(
                key["client_email"],
                key_data=json.dumps(key),
            )

            ee.Initialize(
                credentials=credentials,
                project=PROJECT_ID,
            )

            return True, "Service account connected."

        ee.Initialize(
            project=PROJECT_ID
        )

        return True, "Earth Engine connected."

    except Exception as e:

        return False, str(e)


EE_ACTIVE, EE_MESSAGE = (
    init_earth_engine()
)

if not EE_ACTIVE:

    st.error(
        "Earth Engine connection failed:\n\n"
        + EE_MESSAGE
    )

    st.stop()


# ============================================================
# AUTO REFRESH
# ============================================================

refresh = st.sidebar.slider(
    "Automatic refresh",
    5,
    60,
    DEFAULT_REFRESH,
    5,
)

st_autorefresh(
    interval=refresh * 60 * 1000,
    key="methane_refresh",
)


# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<div class="hero">'
    'ZERO WASTE SOLUTIONS — METHANE INTELLIGENCE'
    '</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="subtitle">'
    'India-wide methane screening + landfill intelligence'
    '</div>',
    unsafe_allow_html=True,
)

st.success(
    f"🛰️ {EE_MESSAGE} | Project: {PROJECT_ID}"
)


# ============================================================
# INDIA GEOMETRY
# ============================================================

@st.cache_resource
def get_india():

    return (
        ee.FeatureCollection(
            "FAO/GAUL/2015/level0"
        )
        .filter(
            ee.Filter.eq(
                "ADM0_NAME",
                "India",
            )
        )
        .geometry()
    )


INDIA = get_india()


# ============================================================
# LANDFILL DATABASE
# ============================================================

def load_landfills():

    st.sidebar.markdown(
        "## 📍 Landfill Database"
    )

    uploaded = st.sidebar.file_uploader(
        "Upload India landfill CSV",
        type=["csv"],
    )

    if uploaded:

        df = pd.read_csv(
            uploaded
        )

        source = "USER DATABASE"

    else:

        # Demo fallback.
        # Upload your complete landfill CSV.
        df = pd.DataFrame(
            [
                [
                    "Ghazipur",
                    "Delhi",
                    "Delhi",
                    28.6231,
                    77.3288,
                ],
                [
                    "Bhalswa",
                    "Delhi",
                    "Delhi",
                    28.7410,
                    77.1517,
                ],
                [
                    "Okhla",
                    "Delhi",
                    "Delhi",
                    28.5303,
                    77.2789,
                ],
                [
                    "Deonar",
                    "Maharashtra",
                    "Mumbai",
                    19.0573,
                    72.9304,
                ],
                [
                    "Mulund",
                    "Maharashtra",
                    "Mumbai",
                    19.1678,
                    72.9567,
                ],
                [
                    "Pirana",
                    "Gujarat",
                    "Ahmedabad",
                    22.9831,
                    72.5802,
                ],
                [
                    "Jawaharnagar",
                    "Telangana",
                    "Hyderabad",
                    17.5147,
                    78.5852,
                ],
                [
                    "Kodungaiyur",
                    "Tamil Nadu",
                    "Chennai",
                    13.1360,
                    80.2640,
                ],
                [
                    "Durg-Rajnandgaon",
                    "Chhattisgarh",
                    "Durg",
                    21.1904,
                    81.2848,
                ],
            ],
            columns=[
                "name",
                "state",
                "city",
                "lat",
                "lon",
            ],
        )

        source = "DEMO DATABASE"

    df.columns = [
        str(c).strip().lower()
        for c in df.columns
    ]

    required = {
        "name",
        "lat",
        "lon",
    }

    missing = (
        required
        - set(df.columns)
    )

    if missing:

        st.error(
            "Missing columns: "
            + ", ".join(
                sorted(missing)
            )
        )

        st.stop()

    df["name"] = (
        df["name"]
        .astype(str)
        .str.strip()
    )

    df["lat"] = pd.to_numeric(
        df["lat"],
        errors="coerce",
    )

    df["lon"] = pd.to_numeric(
        df["lon"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "lat",
            "lon",
        ]
    )

    df = df[
        (df["lat"] >= INDIA_MIN_LAT)
        & (df["lat"] <= INDIA_MAX_LAT)
        & (df["lon"] >= INDIA_MIN_LON)
        & (df["lon"] <= INDIA_MAX_LON)
    ]

    df = df.drop_duplicates(
        subset=[
            "lat",
            "lon",
        ]
    ).reset_index(
        drop=True
    )

    df["site_id"] = (
        np.arange(
            len(df)
        ).astype(str)
    )

    return df, source


landfills, database_source = (
    load_landfills()
)


# ============================================================
# CONTROLS
# ============================================================

st.sidebar.markdown(
    "## 🧠 Detection Engine"
)

recent_days = st.sidebar.slider(
    "Recent CH4 window",
    2,
    14,
    7,
)

baseline_days = st.sidebar.slider(
    "Historical baseline",
    30,
    180,
    90,
)

buffer_km = st.sidebar.slider(
    "Landfill radius",
    1,
    5,
    2,
)

max_uncertainty = st.sidebar.slider(
    "Max CH4 uncertainty",
    1.0,
    10.0,
    5.0,
    0.5,
)

min_qa = st.sidebar.slider(
    "Minimum QA",
    0.40,
    1.00,
    0.50,
    0.05,
)

st.sidebar.markdown(
    "## 🛰️ Sentinel-2"
)

s2_days = st.sidebar.slider(
    "S2 lookback",
    10,
    90,
    30,
)

cloud_probability = st.sidebar.slider(
    "Max cloud probability",
    5,
    50,
    20,
)

show_alerts = st.sidebar.checkbox(
    "Only HIGH/ELEVATED",
    False,
)


# ============================================================
# LATEST SATELLITE OBSERVATION
# ============================================================

@st.cache_data(ttl=600)
def latest_s5p():

    collection = (
        ee.ImageCollection(
            S5P_DATASET
        )
        .filterBounds(
            INDIA
        )
        .select(
            CH4_BAND
        )
        .sort(
            "system:time_start",
            False,
        )
    )

    if collection.size().getInfo() == 0:

        return None

    image = ee.Image(
        collection.first()
    )

    ts = image.get(
        "system:time_start"
    ).getInfo()

    if ts is None:

        return None

    return datetime.fromtimestamp(
        ts / 1000,
        tz=timezone.utc,
    )


latest = latest_s5p()

if latest is None:

    st.error(
        "No Sentinel-5P CH4 observation found."
    )

    st.stop()


latest_text = latest.strftime(
    "%Y-%m-%d %H:%M UTC"
)


# ============================================================
# DATE WINDOWS
# ============================================================

recent_start_dt = (
    latest
    - timedelta(
        days=recent_days
    )
)

recent_end_dt = (
    latest
    + timedelta(
        days=1
    )
)

baseline_start_dt = (
    recent_start_dt
    - timedelta(
        days=baseline_days
    )
)


def date_str(dt):

    return dt.strftime(
        "%Y-%m-%d"
    )


recent_start = date_str(
    recent_start_dt
)

recent_end = date_str(
    recent_end_dt
)

baseline_start = date_str(
    baseline_start_dt
)

baseline_end = date_str(
    recent_start_dt
)


# ============================================================
# QUALITY FILTER
# ============================================================

@st.cache_resource(ttl=600)
def build_collections():

    def quality_mask(image):

        qa = image.select(
            "qa_value"
        )

        uncertainty = image.select(
            CH4_UNCERTAINTY
        )

        mask = (
            qa.gte(
                min_qa
            )
            .And(
                uncertainty.lte(
                    max_uncertainty
                )
            )
        )

        return image.updateMask(
            mask
        )

    recent = (
        ee.ImageCollection(
            S5P_DATASET
        )
        .filterDate(
            recent_start,
            recent_end,
        )
        .filterBounds(
            INDIA
        )
        .select(
            [
                CH4_BAND,
                CH4_UNCERTAINTY,
                "qa_value",
            ]
        )
        .map(
            quality_mask
        )
    )

    baseline = (
        ee.ImageCollection(
            S5P_DATASET
        )
        .filterDate(
            baseline_start,
            baseline_end,
        )
        .filterBounds(
            INDIA
        )
        .select(
            [
                CH4_BAND,
                CH4_UNCERTAINTY,
                "qa_value",
            ]
        )
        .map(
            quality_mask
        )
    )

    return recent, baseline


recent_collection, baseline_collection = (
    build_collections()
)


# ============================================================
# CH4 PRODUCTS
# ============================================================

@st.cache_resource(ttl=600)
def build_products():

    recent_median = (
        recent_collection
        .select(
            CH4_BAND
        )
        .median()
        .clip(
            INDIA
        )
        .rename(
            "recent"
        )
    )

    recent_mean = (
        recent_collection
        .select(
            CH4_BAND
        )
        .mean()
        .clip(
            INDIA
        )
        .rename(
            "recent_mean"
        )
    )

    baseline_median = (
        baseline_collection
        .select(
            CH4_BAND
        )
        .median()
        .clip(
            INDIA
        )
        .rename(
            "baseline"
        )
    )

    baseline_std = (
        baseline_collection
        .select(
            CH4_BAND
        )
        .reduce(
            ee.Reducer.stdDev()
        )
        .clip(
            INDIA
        )
        .rename(
            "baseline_std"
        )
    )

    anomaly = (
        recent_median
        .subtract(
            baseline_median
        )
        .rename(
            "anomaly"
        )
    )

    zscore = (
        anomaly
        .divide(
            baseline_std.max(
                ee.Image.constant(
                    2
                )
            )
        )
        .rename(
            "zscore"
        )
    )

    return (
        recent_median,
        recent_mean,
        baseline_median,
        baseline_std,
        anomaly,
        zscore,
    )


(
    recent_median,
    recent_mean,
    baseline_median,
    baseline_std,
    anomaly,
    zscore,
) = build_products()


# ============================================================
# PERSISTENCE
# ============================================================

@st.cache_resource(ttl=600)
def build_persistence():

    def flag(image):

        return (
            image
            .select(
                CH4_BAND
            )
            .gt(
                baseline_median.add(
                    20
                )
            )
            .rename(
                "persistent"
            )
        )

    return (
        recent_collection
        .map(
            flag
        )
        .sum()
        .rename(
            "persistence"
        )
        .clip(
            INDIA
        )
    )


persistence = (
    build_persistence()
)


# ============================================================
# ERA5 WIND
# ============================================================

@st.cache_resource(ttl=1800)
def get_wind():

    start = (
        latest
        - timedelta(
            hours=12
        )
    )

    end = (
        latest
        + timedelta(
            hours=12
        )
    )

    collection = (
        ee.ImageCollection(
            ERA5_DATASET
        )
        .filterDate(
            start.strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),
            end.strftime(
                "%Y-%m-%dT%H:%M:%S"
            ),
        )
        .select(
            [
                "u_component_of_wind_10m",
                "v_component_of_wind_10m",
            ]
        )
        .sort(
            "system:time_start",
            False,
        )
    )

    return ee.Image(
        collection.first()
    )


wind_image = get_wind()


# ============================================================
# EE LANDFILL FC
# ============================================================

def make_fc(df):

    features = []

    for _, row in df.iterrows():

        props = {
            "site_id": str(
                row["site_id"]
            ),
            "name": str(
                row["name"]
            ),
        }

        if "state" in df.columns:

            props["state"] = str(
                row.get(
                    "state",
                    ""
                )
            )

        if "city" in df.columns:

            props["city"] = str(
                row.get(
                    "city",
                    ""
                )
            )

        point = ee.Geometry.Point(
            [
                float(row["lon"]),
                float(row["lat"]),
            ]
        )

        features.append(
            ee.Feature(
                point,
                props,
            )
        )

    return ee.FeatureCollection(
        features
    )


# ============================================================
# NATIONAL ANALYSIS
# ============================================================

@st.cache_data(ttl=1800)
def analyze_sites(
    dataframe_json,
    radius,
):

    df = pd.read_json(
        dataframe_json
    )

    fc = make_fc(
        df
    )

    inner = fc.map(
        lambda f: f.buffer(
            radius * 1000
        )
    )

    outer = fc.map(
        lambda f: f.buffer(
            radius * 3000
        )
    )

    # --------------------------------------------------------
    # Recent CH4
    # --------------------------------------------------------

    recent_stats = (
        recent_median
        .reduceRegions(
            collection=inner,
            reducer=ee.Reducer.mean(),
            scale=S5P_SCALE,
            tileScale=8,
        )
    )

    # --------------------------------------------------------
    # Baseline
    # --------------------------------------------------------

    baseline_stats = (
        baseline_median
        .reduceRegions(
            collection=inner,
            reducer=ee.Reducer.mean(),
            scale=S5P_SCALE,
            tileScale=8,
        )
    )

    # --------------------------------------------------------
    # Anomaly
    # --------------------------------------------------------

    anomaly_stats = (
        anomaly
        .reduceRegions(
            collection=inner,
            reducer=ee.Reducer.mean(),
            scale=S5P_SCALE,
            tileScale=8,
        )
    )

    # --------------------------------------------------------
    # Z-score
    # --------------------------------------------------------

    z_stats = (
        zscore
        .reduceRegions(
            collection=inner,
            reducer=ee.Reducer.mean(),
            scale=S5P_SCALE,
            tileScale=8,
        )
    )

    # ----------------