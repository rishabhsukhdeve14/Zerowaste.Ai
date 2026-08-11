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


# ============================================================
# ZERO WASTE.AI
# INDIA METHANE INTELLIGENCE PLATFORM
# ============================================================

PROJECT_ID = "stalwart-fx-490910-e3"

S5P_DATASET = "COPERNICUS/S5P/OFFL/L3_CH4"

CH4_BAND = (
    "CH4_column_volume_mixing_ratio_dry_air_bias_corrected"
)

CH4_UNCERTAINTY_BAND = (
    "CH4_column_volume_mixing_ratio_dry_air_uncertainty"
)

TROPOMI_SCALE = 1113.2


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="ZeroWaste.AI",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# UI
# ============================================================

st.markdown(
    """
    <style>

    .stApp {
        background:
        radial-gradient(
            circle at 90% 0%,
            rgba(56,189,248,0.12),
            transparent 30%
        ),
        radial-gradient(
            circle at 5% 20%,
            rgba(34,197,94,0.08),
            transparent 28%
        ),
        #020617;
        color: #f8fafc;
    }

    .hero {
        font-size: 3.1rem;
        font-weight: 950;
        letter-spacing: -2px;
        line-height: 1;
        background:
        linear-gradient(
            90deg,
            #38bdf8,
            #22c55e,
            #f43f5e
        );
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }

    .subtitle {
        color: #94a3b8;
        font-size: 1.05rem;
        margin-top: 10px;
        margin-bottom: 20px;
    }

    .card {
        background: rgba(15,23,42,0.88);
        border: 1px solid rgba(148,163,184,0.16);
        border-radius: 15px;
        padding: 16px;
        margin: 10px 0;
    }

    .small {
        color: #94a3b8;
        font-size: 0.85rem;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# EARTH ENGINE CONNECTION
# ============================================================

@st.cache_resource
def initialize_earth_engine():

    try:

        if "GCP_SERVICE_ACCOUNT" in st.secrets:

            service_account = dict(
                st.secrets["GCP_SERVICE_ACCOUNT"]
            )

            if "private_key" in service_account:

                service_account["private_key"] = (
                    service_account["private_key"]
                    .replace("\\n", "\n")
                )

            credentials = ee.ServiceAccountCredentials(
                service_account["client_email"],
                key_data=json.dumps(service_account),
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

    except Exception as error:

        return False, str(error)


EE_CONNECTED, EE_MESSAGE = (
    initialize_earth_engine()
)


if not EE_CONNECTED:

    st.error(
        "❌ Google Earth Engine connection failed"
    )

    st.code(
        EE_MESSAGE
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
    """
    <div class="subtitle">
    🇮🇳 India-wide methane intelligence •
    Sentinel-5P/TROPOMI • Landfill screening
    </div>
    """,
    unsafe_allow_html=True,
)

st.success(
    f"🛰️ {EE_MESSAGE} • Project: {PROJECT_ID}"
)


# ============================================================
# SIDEBAR CONTROLS
# ============================================================

st.sidebar.header(
    "⚙️ Satellite Engine"
)

recent_days = st.sidebar.slider(
    "Recent observation window",
    min_value=3,
    max_value=14,
    value=7,
)

baseline_days = st.sidebar.slider(
    "Historical baseline",
    min_value=30,
    max_value=180,
    value=90,
)

radius_km = st.sidebar.slider(
    "Landfill analysis radius",
    min_value=1,
    max_value=5,
    value=2,
)

uncertainty_limit = st.sidebar.slider(
    "Maximum CH₄ uncertainty",
    min_value=1.0,
    max_value=10.0,
    value=5.0,
    step=0.5,
)

st.sidebar.markdown("---")

st.sidebar.header(
    "🗺️ Map Layers"
)

show_ch4 = st.sidebar.checkbox(
    "CH₄ concentration",
    value=True,
)

show_anomaly = st.sidebar.checkbox(
    "CH₄ anomaly",
    value=True,
)

show_landfills = st.sidebar.checkbox(
    "Landfill locations",
    value=True,
)


# ============================================================
# INDIA GE