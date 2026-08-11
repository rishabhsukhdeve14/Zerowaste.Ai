# ============================================================
# ZERO WASTE SOLUTIONS
# INDIA LANDFILL METHANE MONITOR
#
# DATA ENGINE
#   Sentinel-5P / TROPOMI CH4
#   ERA5 hourly 10m wind
#   India-wide landfill CSV
#
# FEATURES
#   1. Latest available S5P observation
#   2. Recent methane mean
#   3. Historical baseline
#   4. Methane anomaly
#   5. Uncertainty filtering
#   6. Landfill buffer analysis
#   7. Wind speed + direction
#   8. National ranking
#   9. Interactive India map
#  10. Automatic dashboard refresh
#
# IMPORTANT:
# This is a methane SCREENING / ATTRIBUTION system.
# It does NOT claim that a landfill is the sole source of
# every methane enhancement detected by TROPOMI.
# ============================================================

import json
import math
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
ERA5_DATASET = "ECMWF/ERA5/HOURLY"

CH4_BAND = (
    "CH4_column_volume_mixing_ratio_dry_air_bias_corrected"
)

CH4_UNCERTAINTY_BAND = (
    "CH4_column_volume_mixing_ratio_dry_air_uncertainty"
)

DEFAULT_REFRESH_MINUTES = 10

INDIA_MIN_LAT = 6.0
INDIA_MAX_LAT = 38.0
INDIA_MIN_LON = 68.0
INDIA_MAX_LON = 98.0


# ============================================================
# STREAMLIT PAGE
# ============================================================

st.set_page_config(
    page_title="Zero Waste Solutions — India Methane Monitor",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# UI STYLE
# ============================================================

st.markdown(
    """
    <style>

    .stApp {
        background:
            radial-gradient(
                circle at top right,
                rgba(14,165,233,0.10),
                transparent 30%
            ),
            #030712;
        color: #f8fafc;
    }

    .hero {
        font-size: 2.2rem;
        font-weight: 900;
        letter-spacing: -0.5px;

        background:
            linear-gradient(
                90deg,
                #38bdf8,
                #10b981,
                #f43f5e
            );

        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;

        margin-bottom: 5px;
    }

    .subtitle {
        color: #94a3b8;
        font-size: 0.95rem;
        margin-bottom: 20px;
    }

    .glass-card {
        background: rgba(15, 23, 42, 0.82);
        border: 1px solid rgba(255,255,255,0.09);
        border-radius: 14px;
        padding: 15px;
        min-height: 90px;
        box-shadow:
            0 8px 30px rgba(0,0,0,0.28);
    }

    .status-high {
        color: #f87171;
        font-weight: 900;
    }

    .status-elevated {
        color: #fbbf24;
        font-weight: 900;
    }

    .status-low {
        color: #34d399;
        font-weight: 900;
    }

    .status-no-data {
        color: #94a3b8;
        font-weight: 900;
    }

    .warning-box {
        background: rgba(127,29,29,0.20);
        border-left: 5px solid #ef4444;
        padding: 15px;
        border-radius: 8px;
    }

    .info-box {
        background: rgba(14,116,144,0.16);
        border-left: 5px solid #38bdf8;
        padding: 15px;
        border-radius: 8px;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# EARTH ENGINE INITIALIZATION
# ============================================================

@st.cache_resource
def initialize_earth_engine():

    try:

        # ----------------------------------------------------
        # Streamlit Cloud / service account
        # ----------------------------------------------------

        if "GCP_SERVICE_ACCOUNT" in st.secrets:

            key_dict = dict(
                st.secrets["GCP_SERVICE_ACCOUNT"]
            )

            if "private_key" in key_dict:
                key_dict["private_key"] = (
                    key_dict["private_key"]
                    .replace("\\n", "\n")
                )

            credentials = ee.ServiceAccountCredentials(
                key_dict["client_email"],
                key_data=json.dumps(key_dict),
            )

            ee.Initialize(
                credentials=credentials,
                project=PROJECT_ID,
            )

            return True, "Earth Engine connected with service account"

        # ----------------------------------------------------
        # Local / authenticated environment
        # ----------------------------------------------------

        ee.Initialize(
            project=PROJECT_ID
        )

        return True, "Earth Engine connected"

    except Exception as e:

        return False, str(e)


EE_ACTIVE, EE_MESSAGE = initialize_earth_engine()


# ============================================================
# AUTO REFRESH
# ============================================================

refresh_minutes = st.sidebar.slider(
    "Dashboard refresh interval (minutes)",
    min_value=5,
    max_value=60,
    value=DEFAULT_REFRESH_MINUTES,
    step=5,
)

st_autorefresh(
    interval=refresh_minutes * 60 * 1000,
    key="zero_waste_auto_refresh",
)


# ============================================================
# HEADER
# ============================================================

st.markdown(
    """
    <div class="hero">
        ZERO WASTE SOLUTIONS — INDIA METHANE MONITOR
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="subtitle">
        India-wide landfill methane screening using
        Sentinel-5P/TROPOMI + atmospheric transport context.
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# EARTH ENGINE STATUS
# ============================================================

if EE_ACTIVE:

    st.success(
        f"🛰️ {EE_MESSAGE} | Project: {PROJECT_ID}"
    )

else:

    st.error(
        "Earth Engine connection failed.\n\n"
        f"{EE_MESSAGE}"
    )

    st.stop()


# ============================================================
# INDIA GEOMETRY
# ============================================================

@st.cache_resource
def get_india_geometry():

    india = (
        ee.FeatureCollection(
            "FAO/GAUL/2015/level0"
        )
        .filter(
            ee.Filter.eq(
                "ADM0_NAME",
                "India"
            )
        )
        .geometry()
    )

    return india


INDIA = get_india_geometry()


# ============================================================
# LANDfill CSV LOADER
# ============================================================

REQUIRED_COLUMNS = {
    "name",
    "lat",
    "lon",
}


def load_landfill_database():

    st.sidebar.markdown(
        "## 📍 Landfill Database"
    )

    uploaded_file = st.sidebar.file_uploader(
        "Upload India landfill CSV",
        type=["csv"],
        help=(
            "Required: name, lat, lon. "
            "Optional: state, city, area_ha, "
            "height_m, mass_mt, status."
        ),
    )

    if uploaded_file is not None:

        df = pd.read_csv(
            uploaded_file
        )

        source = (
            "Uploaded landfill database"
        )

    else:

        # ----------------------------------------------------
        # DEMO ONLY
        #
        # Replace with your complete landfill CSV.
        # ----------------------------------------------------

        df = pd.DataFrame(
            [
                [
                    "Ghazipur",
                    "Delhi",
                    "Delhi",
                    28.6231,
                    77.3288,
                    65.0,
                ],
                [
                    "Bhalswa",
                    "Delhi",
                    "Delhi",
                    28.7410,
                    77.1517,
                    62.0,
                ],
                [
                    "Okhla",
                    "Delhi",
                    "Delhi",
                    28.5303,
                    77.2789,
                    55.0,
                ],
                [
                    "Deonar",
                    "Maharashtra",
                    "Mumbai",
                    19.0573,
                    72.9304,
                    38.0,
                ],
                [
                    "Mulund",
                    "Maharashtra",
                    "Mumbai",
                    19.1678,
                    72.9567,
                    30.0,
                ],
                [
                    "Pirana",
                    "Gujarat",
                    "Ahmedabad",
                    22.9831,
                    72.5802,
                    50.0,
                ],
                [
                    "Jawaharnagar",
                    "Telangana",
                    "Hyderabad",
                    17.5147,
                    78.5852,
                    45.0,
                ],
                [
                    "Kodungaiyur",
                    "Tamil Nadu",
                    "Chennai",
                    13.1360,
                    80.2640,
                    35.0,
                ],
                [
                    "Durg-Rajnandgaon",
                    "Chhattisgarh",
                    "Durg",
                    21.1904,
                    81.2848,
                    22.0,
                ],
            ],
            columns=[
                "name",
                "state",
                "city",
                "lat",
                "lon",
                "height_m",
            ],
        )

        source = (
            "DEMO DATA — upload your complete "
            "India landfill database"
        )

    # --------------------------------------------------------
    # Normalize column names
    # --------------------------------------------------------

    df.columns = [
        str(c).strip().lower()
        for c in df.columns
    ]

    missing = (
        REQUIRED_COLUMNS
        - set(df.columns)
    )

    if missing:

        st.error(
            "CSV missing required columns: "
            + ", ".join(
                sorted(missing)
            )
        )

        st.stop()

    # --------------------------------------------------------
    # Numeric conversion
    # --------------------------------------------------------

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
    ).copy()

    # --------------------------------------------------------
    # India geographic bounds
    # --------------------------------------------------------

    df = df[
        (df["lat"] >= INDIA_MIN_LAT)
        & (df["lat"] <= INDIA_MAX_LAT)
        & (df["lon"] >= INDIA_MIN_LON)
        & (df["lon"] <= INDIA_MAX_LON)
    ].copy()

    # --------------------------------------------------------
    # Unique IDs
    # --------------------------------------------------------

    df["name"] = (
        df["name"]
        .astype(str)
        .str.strip()
    )

    df["site_id"] = (
        np.arange(len(df))
        .astype(str)
    )

    return df, source


landfills, landfill_source = (
    load_landfill_database()
)


# ============================================================
# SIDEBAR CONTROLS
# ============================================================

st.sidebar.markdown(
    "## 🛰️ Satellite Controls"
)

recent_days = st.sidebar.slider(
    "Recent S5P window (days)",
    min_value=1,
    max_value=14,
    value=7,
)

baseline_days = st.sidebar.slider(
    "Baseline window (days)",
    min_value=30,
    max_value=180,
    value=60,
)

buffer_km = st.sidebar.slider(
    "Landfill analysis radius (km)",
    min_value=1,
    max_value=5,
    value=2,
)

uncertainty_limit = st.sidebar.slider(
    "Maximum CH₄ uncertainty (ppb)",
    min_value=1.0,
    max_value=10.0,
    value=10.0,
)

show_only_alerts = st.sidebar.checkbox(
    "Show only elevated/high sites",
    value=False,
)


# ============================================================
# GET LATEST AVAILABLE S5P OBSERVATION
# ============================================================

@st.cache_data(ttl=600)
def get_latest_s5p_timestamp():

    collection = (
        ee.ImageCollection(
            S5P_DATASET
        )
        .filterBounds(INDIA)
        .select(CH4_BAND)
        .sort(
            "system:time_start",
            False,
        )
    )

    count = collection.size().getInfo()

    if count == 0:
        return None

    first_image = ee.Image(
        collection.first()
    )

    timestamp = (
        first_image
        .get("system:time_start")
        .getInfo()
    )

    return datetime.fromtimestamp(
        timestamp / 1000,
        tz=timezone.utc,
    )


latest_s5p_dt = (
    get_latest_s5p_timestamp()
)


if latest_s5p_dt is None:

    st.error(
        "No Sentinel-5P CH₄ observation found."
    )

    st.stop()


latest_s5p_text = (
    latest_s5p_dt
    .strftime("%Y-%m-%d %H:%M UTC")
)


# ============================================================
# ANALYSIS WINDOWS
# ============================================================

# Use the latest actual satellite observation as the anchor.
recent_end_dt = (
    latest_s5p_dt
    + timedelta(days=1)
)

recent_start_dt = (
    latest_s5p_dt
    - timedelta(days=recent_days)
)

baseline_start_dt = (
    recent_start_dt
    - timedelta(days=baseline_days)
)


def date_string(dt):

    return dt.strftime(
        "%Y-%m-%d"
    )


recent_start = date_string(
    recent_start_dt
)

recent_end = date_string(
    recent_end_dt
)

baseline_start = date_string(
    baseline_start_dt
)

baseline_end = date_string(
    recent_start_dt
)


# ============================================================
# S5P COLLECTION
# ============================================================

@st.cache_resource(ttl=600)
def build_s5p_layers(
    recent_start,
    recent_end,
    baseline_start,
    baseline_end,
    uncertainty_limit,
):

    # --------------------------------------------------------
    # RECENT
    # --------------------------------------------------------

    recent_collection = (
        ee.ImageCollection(
            S5P_DATASET
        )
        .filterDate(
            recent_start,
            recent_end,
        )
        .filterBounds(INDIA)
        .select(
            [
                CH4_BAND,
                CH4_UNCERTAINTY_BAND,
            ]
        )
        .map(
            lambda image:
            image.updateMask(
                image
                .select(
                    CH4_UNCERTAINTY_BAND
                )
                .lte(
                    uncertainty_limit
                )
            )
        )
    )

    # --------------------------------------------------------
    # BASELINE
    # --------------------------------------------------------

    baseline_collection = (
        ee.ImageCollection(
            S5P_DATASET
        )
        .filterDate(
            baseline_start,
            baseline_end,
        )
        .filterBounds(INDIA)
        .select(
            CH4_BAND
        )
    )

    recent_mean = (
        recent_collection
        .mean()
        .clip(INDIA)
        .rename("recent_ch4")
    )

    baseline_mean = (
        baseline_collection
        .mean()
        .clip(INDIA)
        .rename("baseline_ch4")
    )

    anomaly = (
        recent_mean
        .subtract(
            baseline_mean
        )
        .rename(
            "ch4_anomaly"
        )
    )

    return (
        recent_collection,
        baseline_collection,
        recent_mean,
        baseline_mean,
        anomaly,
    )


(
    recent_collection,
    baseline_collection,
    recent_ch4,
    baseline_ch4,
    ch4_anomaly,
) = build_s5p_layers(
    recent_start,
    recent_end,
    baseline_start,
    baseline_end,
    uncertainty_limit,
)


# ============================================================
# COLLECTION COUNTS
# ============================================================

try:

    recent_scene_count = (
        recent_collection
        .size()
        .getInfo()
    )

except Exception:

    recent_scene_count = 0


try:

    baseline_scene_count = (
        baseline_collection
        .size()
        .getInfo()
    )

except Exception:

    baseline_scene_count = 0


# ============================================================
# ERA5 WIND
# ============================================================

@st.cache_resource(ttl=1800)
def get_latest_wind_image(
    latest_dt
):

    start = (
        latest_dt
        - timedelta(hours=12)
    )

    end = (
        latest_dt
        + timedelta(hours=12)
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


wind_image = (
    get_latest_wind_image(
        latest_s5p_dt
    )
)


# ============================================================
# LANDfill FEATURE COLLECTION
# ============================================================

def create_landfill_fc(df):

    features = []

    for _, row in df.iterrows():

        properties = {
            "site_id":
                str(row["site_id"]),

            "name":
                str(row["name"]),
        }

        if "state" in df.columns:

            properties["state"] = str(
                row.get(
                    "state",
                    ""
                )
            )

        if "city" in df.columns:

            properties["city"] = str(
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
                properties,
            )
        )

    return ee.FeatureCollection(
        features
    )


landfill_fc = create_landfill_fc(
    landfills
)


# ============================================================
# NATIONAL LANDfill EXTRACTION
#
# We use reduceRegions rather than one API request per site.
# ============================================================

@st.cache_data(ttl=1800)
def calculate_landfill_results(
    df_json,
    radius_km,
):

    df = pd.read_json(
        df_json
    )

    fc = create_landfill_fc(
        df
    )

    # --------------------------------------------------------
    # Create landfill buffers
    # --------------------------------------------------------

    buffered_fc = fc.map(
        lambda feature:
        feature.buffer(
            radius_km * 1000
        )
    )

    # --------------------------------------------------------
    # Recent CH4 statistics
    # --------------------------------------------------------

    methane_stats = (
        recent_ch4
        .reduceRegions(
        