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
# ZERO WASTE.AI - FAST / LAZY-LOAD VERSION
# ============================================================

PROJECT_ID = "stalwart-fx-490910-e3"

S5P = "COPERNICUS/S5P/OFFL/L3_CH4"

CH4 = "CH4_column_volume_mixing_ratio_dry_air_bias_corrected"
CH4_UNCERTAINTY = "CH4_column_volume_mixing_ratio_dry_air_uncertainty"

SCALE = 1113.2


APP_VERSION = "2026.08.11-fixed-results-v2"
if st.session_state.get("app_version") != APP_VERSION:
    st.session_state["app_version"] = APP_VERSION
    st.session_state.pop("methane_results", None)

# ============================================================
# PAGE
# ============================================================

st.set_page_config(
    page_title="ZeroWaste.AI",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """ <style> .stApp { background: radial-gradient(circle at 90% 0%, rgba(56,189,248,.12), transparent 30%), radial-gradient(circle at 5% 20%, rgba(34,197,94,.08), transparent 28%), #020617; color: #f8fafc; } .hero { font-size: 3rem; font-weight: 950; letter-spacing: -2px; line-height: 1; background: linear-gradient(90deg,#38bdf8,#22c55e,#f43f5e); -webkit-background-clip: text; -webkit-text-fill-color: transparent; } .sub { color: #94a3b8; font-size: 1.05rem; margin: 8px 0 20px; } .card { background: rgba(15,23,42,.88); border: 1px solid rgba(148,163,184,.16); border-radius: 14px; padding: 15px; margin: 10px 0; } </style> """,
    unsafe_allow_html=True,
)


# ============================================================
# EARTH ENGINE
# ============================================================

@st.cache_resource
def init_earth_engine():
    try:
        if "GCP_SERVICE_ACCOUNT" in st.secrets:
            key = dict(st.secrets["GCP_SERVICE_ACCOUNT"])

            if "private_key" in key:
                key["private_key"] = key["private_key"].replace(
                    "\\n", "\n"
                )

            credentials = ee.ServiceAccountCredentials(
                key["client_email"],
                key_data=json.dumps(key),
            )

            ee.Initialize(
                credentials=credentials,
                project=PROJECT_ID,
            )
        else:
            ee.Initialize(project=PROJECT_ID)

        return True, "Earth Engine connected"

    except Exception as exc:
        return False, str(exc)


EE_OK, EE_MESSAGE = init_earth_engine()


# ============================================================
# HEADER FIRST
# ============================================================

st.markdown(
    '<div class="hero">ZERO WASTE.AI</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="sub">🇮🇳 India-wide methane intelligence • '
    'Sentinel-5P/TROPOMI • Landfill screening</div>',
    unsafe_allow_html=True,
)

if EE_OK:
    st.success(
        f"🛰️ {EE_MESSAGE} • Project: {PROJECT_ID}"
    )
else:
    st.error("Earth Engine connection failed.")
    st.code(EE_MESSAGE)
    st.stop()


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header("⚙️ Monitoring")

recent_days = st.sidebar.slider(
    "Recent satellite window",
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
    "Landfill radius (km)",
    1,
    5,
    2,
)

uncertainty_limit = st.sidebar.slider(
    "Max CH₄ uncertainty (ppb)",
    1.0,
    10.0,
    5.0,
    0.5,
)

st.sidebar.markdown("---")
st.sidebar.header("🗺️ Layers")

show_ch4 = st.sidebar.checkbox(
    "CH₄ concentration",
    True,
)

show_anomaly = st.sidebar.checkbox(
    "CH₄ anomaly",
    True,
)

show_sites = st.sidebar.checkbox(
    "Landfill locations",
    True,
)


# ============================================================
# LANDfill DATABASE
# ============================================================

def load_landfills():

    uploaded = st.sidebar.file_uploader(
        "Upload landfill CSV",
        type=["csv"],
        help="Required columns: name, lat, lon",
    )

    if uploaded is not None:
        df = pd.read_csv(uploaded)
        source = "Uploaded CSV"

    elif os.path.exists("landfills.csv"):
        df = pd.read_csv("landfills.csv")
        source = "landfills.csv"

    else:
        df = pd.DataFrame(
            [
                ["Ghazipur", "Delhi", 28.6231, 77.3288],
                ["Bhalswa", "Delhi", 28.7410, 77.1517],
                ["Okhla", "Delhi", 28.5303, 77.2789],
                ["Deonar", "Maharashtra", 19.0573, 72.9304],
                ["Mulund", "Maharashtra", 19.1678, 72.9567],
                ["Pirana", "Gujarat", 22.9831, 72.5802],
                ["Jawaharnagar", "Telangana", 17.5147, 78.5852],
                ["Kodungaiyur", "Tamil Nadu", 13.1360, 80.2640],
                ["Durg-Rajnandgaon", "Chhattisgarh", 21.1904, 81.2848],
            ],
            columns=["name", "state", "lat", "lon"],
        )
        source = "Demo locations"

    df.columns = [
        str(c).strip().lower()
        for c in df.columns
    ]

    needed = {"name", "lat", "lon"}
    missing = needed - set(df.columns)

    if missing:
        st.error(
            "CSV missing columns: "
            + ", ".join(sorted(missing))
        )
        st.stop()

    df["name"] = df["name"].astype(str).str.strip()
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")

    df = df.dropna(subset=["lat", "lon"]).copy()

    df = df[
        (df["lat"] >= 6)
        & (df["lat"] <= 38)
        & (df["lon"] >= 68)
        & (df["lon"] <= 98)
    ].copy()

    df = df.drop_duplicates(
        subset=["lat", "lon"]
    ).reset_index(drop=True)

    df["site_id"] = df.index.astype(str)

    return df, source


landfills, database_source = load_landfills()

st.sidebar.success(
    f"{len(landfills):,} sites loaded"
)


# ============================================================
# FAST INDIA GEOMETRY
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
# IMPORTANT FIX:
# NO getInfo(), NO latest-observation lookup,
# NO national reduceRegions BEFORE PAGE/MAP.
#
# We use a date window around the current UTC date.
# Heavy exact site analysis happens ONLY after the button.
# ============================================================

now_utc = datetime.now(timezone.utc)

recent_end_date = (
    now_utc + timedelta(days=1)
).strftime("%Y-%m-%d")

recent_start_date = (
    now_utc - timedelta(days=recent_days)
).strftime("%Y-%m-%d")

baseline_end_date = recent_start_date

baseline_start_date = (
    now_utc
    - timedelta(
        days=recent_days + baseline_days
    )
).strftime("%Y-%m-%d")


# ============================================================
# LIGHTWEIGHT SATELLITE COLLECTION
# ============================================================

@st.cache_resource
def make_recent_collection( start_date, end_date, uncertainty, ):
    collection = (
        ee.ImageCollection(S5P)
        .filterDate(
            start_date,
            end_date,
        )
        .filterBounds(INDIA)
        .select(
            [
                CH4,
                CH4_UNCERTAINTY,
            ]
        )
    )

    def mask(image):
        return image.select(CH4).updateMask(
            image.select(CH4_UNCERTAINTY).lte(
                uncertainty
            )
        )

    return collection.map(mask)


recent_collection = make_recent_collection(
    recent_start_date,
    recent_end_date,
    uncertainty_limit,
)


# ============================================================
# MAP PRODUCT
# This is intentionally simple so the page can render quickly.
# ============================================================

recent_methane = (
    recent_collection
    .median()
    .rename("CH4")
)

st.markdown(
    f""" <div class="card"> <b>🛰️ Satellite monitoring window</b><br> {recent_start_date} → {recent_end_date} <br><br> <b>Database:</b> {database_source} &nbsp; • &nbsp; <b>Sites:</b> {len(landfills):,} <br><br> <span class="small"> Detailed landfill calculations are deliberately delayed until you press RUN INDIA-WIDE SCAN. </span> </div> """,
    unsafe_allow_html=True,
)


# ============================================================
# MAP
# ============================================================

st.subheader("🗺️ India Methane Map")

india_map = folium.Map(
    location=[22.5, 80.0],
    zoom_start=5,
    tiles="CartoDB dark_matter",
    control_scale=True,
)


if show_ch4:
    try:
        ch4_layer = recent_methane.getMapId(
            {
                "min": 1750,
                "max": 2000,
                "palette": [
                    "050505",
                    "1d4ed8",
                    "06b6d4",
                    "22c55e",
                    "eab308",
                    "f97316",
                    "dc2626",
                ],
            }
        )

        folium.TileLayer(
            tiles=ch4_layer["tile_fetcher"].url_format,
            attr="Copernicus Sentinel-5P/TROPOMI",
            name="🛰️ CH₄ concentration",
            overlay=True,
            control=True,
            opacity=0.60,
        ).add_to(india_map)

    except Exception as exc:
        st.warning(
            "Satellite CH₄ layer is temporarily unavailable: "
            + str(exc)
        )


if show_sites:

    points = [
        [
            float(row["lat"]),
            float(row["lon"]),
            str(row["name"]),
        ]
        for _, row in landfills.iterrows()
    ]

    if points:
        plugins.FastMarkerCluster(
            points
        ).add_to(india_map)


folium.LayerControl(
    collapsed=False
).add_to(india_map)

plugins.Fullscreen().add_to(india_map)

st_folium(
    india_map,
    width=None,
    height=600,
    returned_objects=[],
)


# ============================================================
# NATIONAL SCAN BUTTON
# ============================================================

st.subheader("🇮🇳 India-wide Landfill Analysis")

st.info(
    "The page and map above are lightweight. "
    "The heavy Earth Engine site-by-site analysis starts only "
    "after pressing the button below."
)

run_scan = st.button(
    "🚀 RUN INDIA-WIDE METHANE SCAN",
    type="primary",
    use_container_width=True,
)


# ============================================================
# HEAVY FUNCTIONS - ONLY USED AFTER BUTTON
# ============================================================

def build_fc(df):

    features = []

    for _, row in df.iterrows():

        props = {
            "site_id": str(row["site_id"]),
            "name": str(row["name"]),
        }

        if "state" in df.columns:
            props["state"] = str(row["state"])

        if "city" in df.columns:
            props["city"] = str(row["city"])

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

    return ee.FeatureCollection(features)


def lookup(features, field):

    values = {}

    for feature in features:

        props = feature.get(
            "properties",
            {},
        )

        site_id = str(
            props.get(
                "site_id",
                "",
            )
        )

        values[site_id] = props.get(field)

    return values


def analyse_chunk(df):

    recent = recent_collection

    baseline_collection = (
        ee.ImageCollection(S5P)
        .filterDate(
            baseline_start_date,
            baseline_end_date,
        )
        .filterBounds(INDIA)
        .select(
            [
                CH4,
                CH4_UNCERTAINTY,
            ]
        )
    )

    def mask_baseline(image):
        return image.select(CH4).updateMask(
            image.select(
                CH4_UNCERTAINTY
            ).lte(
                uncertainty_limit
            )
        )

    baseline = baseline_collection.map(
        mask_baseline
    )

    recent_image = (
        recent.median()
        .rename("recent")
    )

    baseline_image = (
        baseline.median()
        .rename("baseline")
    )

    anomaly_image = (
        recent_image
        .subtract(baseline_image)
        .rename("anomaly")
    )

    std_image = (
        baseline
        .reduce(
            ee.Reducer.stdDev()
        )
        .rename("std")
    )

    z_image = (
        anomaly_image
        .divide(
            std_image.max(
                ee.Image.constant(2)
            )
        )
        .rename("zscore")
    )

    fc = build_fc(df)

    inner = fc.map(
        lambda feature:
        feature.buffer(
            radius_km * 1000
        )
    )

    background = fc.map(
        lambda feature:
        feature.buffer(
            radius_km * 3000
        )
    )

    stack = ee.Image.cat(
        [
            recent_image,
            baseline_image,
            anomaly_image,
            z_image,
        ]
    )

    inner_data = (
        stack
        .reduceRegions(
            collection=inner,
            reducer=ee.Reducer.mean(),
            scale=SCALE,
            tileScale=8,
        )
        .getInfo()
        .get(
            "features",
            [],
        )
    )

    background_data = (
        anomaly_image
        .rename("background")
        .reduceRegions(
            collection=background,
            reducer=ee.Reducer.mean(),
            scale=SCALE,
            tileScale=8,
        )
        .getInfo()
        .get(
            "features",
            [],
        )
    )

    recent_lookup = lookup(
        inner_data,
        "recent",
    )

    baseline_lookup = lookup(
        inner_data,
        "baseline",
    )

    anomaly_lookup = lookup(
        inner_data,
        "anomaly",
    )

    z_lookup = lookup(
        inner_data,
        "zscore",
    )

    background_lookup = lookup(
        background_data,
        "background",
    )

    result = df.copy()

    result["recent_ch4_ppb"] = (
        result["site_id"].map(
            lambda x:
            recent_lookup.get(str(x))
        )
    )

    result["baseline_ch4_ppb"] = (
        result["site_id"].map(
            lambda x:
            baseline_lookup.get(str(x))
        )
    )

    result["anomaly_ppb"] = (
        result["site_id"].map(
            lambda x:
            anomaly_lookup.get(str(x))
        )
    )

    result["zscore"] = (
        result["site_id"].map(
            lambda x:
            z_lookup.get(str(x))
        )
    )

    result["background_anomaly_ppb"] = (
        result["site_id"].map(
            lambda x:
            background_lookup.get(str(x))
        )
    )

    result["spatial_contrast_ppb"] = (
        pd.to_numeric(
            result["anomaly_ppb"],
            errors="coerce",
        )
        -
        pd.to_numeric(
            result["background_anomaly_ppb"],
            errors="coerce",
        )
    )

    current = pd.to_numeric(
        result["recent_ch4_ppb"],
        errors="coerce",
    )

    baseline_values = pd.to_numeric(
        result["baseline_ch4_ppb"],
        errors="coerce",
    )

    anomaly_values = pd.to_numeric(
        result["anomaly_ppb"],
        errors="coerce",
    )

    z_values = pd.to_numeric(
        result["zscore"],
        errors="coerce",
    )

    spatial_values = pd.to_numeric(
        result["spatial_contrast_ppb"],
        errors="coerce",
    )

    result["anomaly_percent"] = np.where(
        baseline_values > 0,
        (
            (
                current
                - baseline_values
            )
            / baseline_values
        )
        * 100,
        np.nan,
    )

    anomaly_component = (
        anomaly_values
        .fillna(0)
        .clip(0, 150)
        / 150
    )

    z_component = (
        z_values
        .fillna(0)
        .clip(0, 5)
        / 5
    )

    spatial_component = (
        spatial_values
        .fillna(0)
        .clip(0, 100)
        / 100
    )

    data_component = (
        result["recent_ch4_ppb"]
        .notna()
        .astype(float)
    )

    result["evidence_score"] = (
        100
        * (
            0.50 * anomaly_component
            + 0.30 * z_component
            + 0.15 * spatial_component
            + 0.05 * data_component
        )
    ).clip(0, 100)

    result["confidence"] = (
        100
        * (
            0.70 * data_component
            + 0.30 * (
                z_component > 0.20
            ).astype(float)
        )
    ).clip(0, 100)

    def classify(row):

        score = row["evidence_score"]
        confidence = row["confidence"]

        if pd.isna(score):
            return "NO DATA"

        if score >= 70 and confidence >= 60:
            return "HIGH"

        if score >= 40 and confidence >= 45:
            return "ELEVATED"

        return "LOW"

    result["status"] = result.apply(
        classify,
        axis=1,
    )

    return result


# ============================================================
# RUN ONLY WHEN BUTTON IS PRESSED
# ============================================================

if run_scan:

    chunk_size = 250

    chunks = [
        landfills[i:i + chunk_size].copy()
        for i in range(
            0,
            len(landfills),
            chunk_size,
        )
    ]

    progress = st.progress(
        0,
        text="Starting satellite scan..."
    )

    results = []

    try:

        for index, chunk in enumerate(chunks):

            chunk_result = analyse_chunk(
                chunk
            )

            results.append(
                chunk_result
            )

            done = index + 1
            total = len(chunks)

            progress.progress(
                int(
                    done / total * 100
                ),
                text=(
                    "Analysing "
                    + str(
                        min(
                            done * chunk_size,
                            len(landfills),
                        )
                    )
                    + "/"
                    + str(len(landfills))
                    + " landfill sites"
                ),
            )

        final = pd.concat(
            results,
            ignore_index=True,
        ).copy()

        st.session_state[
            "methane_results"
        ] = final

        progress.empty()

        st.success(
            "✅ India-wide methane scan completed."
        )

    except Exception as exc:

        progress.empty()

        st.error(
            "❌ Scan failed"
        )

        st.code(
            str(exc)
        )


# ============================================================
# ============================================================
# DISPLAY RESULTS - ROBUST / TYPE-SAFE
# ============================================================

if "methane_results" in st.session_state:

    raw_results = st.session_state["methane_results"]

    # Streamlit sessions can survive code changes. Never assume that
    # an old object in session_state is still a DataFrame.
    if not isinstance(raw_results, pd.DataFra