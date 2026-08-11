import json
import os
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
# ZERO WASTE.AI
# INDIA METHANE INTELLIGENCE ENGINE
# ============================================================

APP_NAME = "ZeroWaste.AI"
PROJECT_ID = "stalwart-fx-490910-e3"

S5P = "COPERNICUS/S5P/OFFL/L3_CH4"
S2 = "COPERNICUS/S2_SR_HARMONIZED"
S2_CLOUD = "COPERNICUS/S2_CLOUD_PROBABILITY"
ERA5 = "ECMWF/ERA5/HOURLY"

CH4 = "CH4_column_volume_mixing_ratio_dry_air_bias_corrected"
CH4_ERR = "CH4_column_volume_mixing_ratio_dry_air_uncertainty"

S5P_SCALE = 1113.2
ERA5_SCALE = 27830


# ============================================================
# PAGE
# ============================================================

st.set_page_config(
    page_title="ZeroWaste.AI — Methane Intelligence",
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
        background:
        radial-gradient(
            circle at 90% 0%,
            rgba(14,165,233,.13),
            transparent 30%
        ),
        radial-gradient(
            circle at 10% 20%,
            rgba(16,185,129,.08),
            transparent 25%
        ),
        #020617;
        color:#f8fafc;
    }

    .hero {
        font-size:2.5rem;
        font-weight:950;
        line-height:1.05;
        letter-spacing:-1px;
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
        font-size:1rem;
        margin:8px 0 18px;
    }

    .card {
        background:rgba(15,23,42,.86);
        border:1px solid rgba(148,163,184,.14);
        border-radius:16px;
        padding:15px;
    }

    .info {
        background:rgba(14,116,144,.13);
        border-left:5px solid #38bdf8;
        border-radius:10px;
        padding:13px;
        margin:12px 0;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# EARTH ENGINE
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

            credentials = (
                ee.ServiceAccountCredentials(
                    key["client_email"],
                    key_data=json.dumps(key),
                )
            )

            ee.Initialize(
                credentials=credentials,
                project=PROJECT_ID,
            )

        else:

            ee.Initialize(
                project=PROJECT_ID
            )

        return True, "Earth Engine connected"

    except Exception as e:

        return False, str(e)


EE_OK, EE_MESSAGE = init_earth_engine()

if not EE_OK:

    st.error(
        "Earth Engine connection failed:\n\n"
        + EE_MESSAGE
    )

    st.stop()


# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<div class="hero">ZERO WASTE.AI</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="subtitle">'
    'India Methane Intelligence • Satellite Evidence • Landfill Monitoring'
    '</div>',
    unsafe_allow_html=True,
)

st.success(
    f"🛰️ {EE_MESSAGE} • Project: {PROJECT_ID}"
)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.markdown(
    "## ⚙️ Monitoring Engine"
)

refresh_minutes = st.sidebar.slider(
    "Auto refresh",
    5,
    60,
    15,
    5,
)

st_autorefresh(
    interval=refresh_minutes * 60 * 1000,
    key="zero_waste_refresh",
)

recent_days = st.sidebar.slider(
    "Recent CH₄ window",
    3,
    14,
    7,
)

baseline_days = st.sidebar.slider(
    "Historical baseline",
    30,
    180,
    90,
)

radius_km = st.sidebar.slider(
    "Landfill radius",
    1,
    5,
    2,
)

qa_min = st.sidebar.slider(
    "Minimum TROPOMI QA",
    0.40,
    0.90,
    0.50,
    0.05,
)

uncertainty_max = st.sidebar.slider(
    "Maximum CH₄ uncertainty",
    1.0,
    10.0,
    5.0,
    0.5,
)

st.sidebar.markdown(
    "## 🗺️ Map Layers"
)

show_ch4 = st.sidebar.checkbox(
    "CH₄ concentration",
    True,
)

show_anomaly = st.sidebar.checkbox(
    "CH₄ anomaly",
    True,
)

show_markers = st.sidebar.checkbox(
    "Landfill locations",
    True,
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

cloud_limit = st.sidebar.slider(
    "Cloud probability",
    5,
    50,
    20,
)


# ============================================================
# INDIA
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
# LANDFILLS
# ============================================================

def load_landfills():

    uploaded = st.sidebar.file_uploader(
        "Upload India landfill CSV",
        type=["csv"],
    )

    if uploaded is not None:

        df = pd.read_csv(
            uploaded
        )

        source = "Uploaded landfill CSV"

    elif os.path.exists(
        "landfills.csv"
    ):

        df = pd.read_csv(
            "landfills.csv"
        )

        source = "Repository landfill CSV"

    else:

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
                    "