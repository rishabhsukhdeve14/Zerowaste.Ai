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
# Clean, lazy-loading Streamlit application
# ============================================================

PROJECT_ID = "stalwart-fx-490910-e3"

S5P_DATASET = "COPERNICUS/S5P/OFFL/L3_CH4"

CH4_BAND = "CH4_column_volume_mixing_ratio_dry_air"
UNCERTAINTY_BAND = (
    "CH4_column_volume_mixing_ratio_dry_air_uncertainty"
)

TROPOMI_SCALE = 1113.2


# ============================================================
# PAGE
# ============================================================

st.set_page_config(
    page_title="ZeroWaste.AI",
    page_icon="🌍",
    layout="wide",
)

st.markdown(
    """ <style> .stApp { background: #020617; color: #f8fafc; } .hero { font-size: 3rem; font-weight: 900; line-height: 1.05; background: linear-gradient( 90deg, #38bdf8, #22c55e, #f43f5e ); -webkit-background-clip: text; -webkit-text-fill-color: transparent; } .subtitle { color: #94a3b8; font-size: 1.05rem; margin: 10px 0 20px; } .card { background: #0f172a; border: 1px solid #1e293b; border-radius: 14px; padding: 16px; margin: 10px 0; } </style> """,
    unsafe_allow_html=True,
)


# ============================================================
# EARTH ENGINE
# ============================================================

@st.cache_resource
def connect_earth_engine():
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

        return True, "Connected"

    except Exception as exc:
        return False, str(exc)


EE_OK, EE_MESSAGE = connect_earth_engine()


# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<div class="hero">ZERO WASTE.AI</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="subtitle">'
    "🇮🇳 India-wide methane intelligence • "
    "Sentinel-5P/TROPOMI • Landfill screening"
    "</div>",
    unsafe_allow_html=True,
)

if EE_OK:
    st.success(
        "🛰️ Earth Engine connected • Project: "
        + PROJECT_ID
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
    "Recent window (days)",
    min_value=3,
    max_value=14,
    value=7,
)

baseline_days = st.sidebar.slider(
    "Baseline (days)",
    min_value=30,
    max_value=180,
    value=90,
)

radius_km = st.sidebar.slider(
    "Landfill radius (km)",
    min_value=1,
    max_value=5,
    value=2,
)

uncertainty_limit = st.sidebar.slider(
    "Maximum uncertainty (ppb)",
    min_value=1.0,
    max_value=10.0,
    value=5.0,
    step=0.5,
)

st.sidebar.markdown("---")


# ============================================================
# LANDFILL DATA
# ============================================================

def load_landfills():
    uploaded = st.sidebar.file_uploader(
        "Upload landfill CSV",
        type=["csv"],
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
            ],
            columns=["name", "state", "lat", "lon"],
        )
        source = "Demo database"

    df.columns = [
        str(col).strip().lower()
        for col in df.columns
    ]

    required = {"name", "lat", "lon"}
    missing = required - set(df.columns)

    if missing:
        st.error(
            "CSV must contain: name, lat, lon. Missing: "
            + ", ".join(sorted(missing))
        )
        st.stop()

    df["name"] = df["name"].astype(str)
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


landfills, landfill_source = load_landfills()

st.sidebar.success(
    f"{len(landfills):,} sites loaded"
)


# ============================================================
# INDIA GEOMETRY
# ============================================================

@st.cache_resource
def india_geometry():
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


INDIA = india_geometry()


# ============================================================
# DATE WINDOW
# ============================================================

today = datetime.now(timezone.utc).date()

recent_start = (
    today - timedelta(days=recent_days)
).strftime("%Y-%m-%d")

recent_end = (
    today + timedelta(days=1)
).strftime("%Y-%m-%d")

baseline_start = (
    today
    - timedelta(
        days=recent_days + baseline_days
    )
).strftime("%Y-%m-%d")

baseline_end = recent_start


# ============================================================
# SATELLITE COLLECTION
# ============================================================

def satellite_collection(start_date, end_date):
    collection = (
        ee.ImageCollection(S5P_DATASET)
        .filterDate(start_date, end_date)
        .filterBounds(INDIA)
        .select(
            [
                CH4_BAND,
                UNCERTAINTY_BAND,
            ]
        )
    )

    def mask_image(image):
        methane = image.select(CH4_BAND)
        uncertainty = image.select(
            UNCERTAINTY_BAND
        )

        return methane.updateMask(
            uncertainty.lte(
                uncertainty_limit
            )
        )

    return collection.map(mask_image)


recent_collection = satellite_collection(
    recent_start,
    recent_end,
)


# ============================================================
# MAP
# ============================================================

st.subheader("🗺️ India Methane Map")

st.markdown(
    f""" <div class="card"> <b>Satellite window:</b> {recent_start} → {recent_end} &nbsp; • &nbsp; <b>Landfill database:</b> {landfill_source} &nbsp; • &nbsp; <b>Sites:</b> {len(landfills):,} </div> """,
    unsafe_allow_html=True,
)

india_map = folium.Map(
    location=[22.5, 80.0],
    zoom_start=5,
    tiles="CartoDB dark_matter",
    control_scale=True,
)


# Only create the visual satellite layer.
# No reduceRegions/getInfo is executed here.
try:
    recent_image = (
        recent_collection
        .median()
        .rename("CH4")
    )

    map_id = recent_image.getMapId(
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
        tiles=map_id["tile_fetcher"].url_format,
        attr="Copernicus Sentinel-5P/TROPOMI",
        name="🛰️ CH₄",
        overlay=True,
        control=True,
        opacity=0.65,
    ).add_to(india_map)

except Exception as exc:
    st.warning(
        "Satellite map layer unavailable: "
        + str(exc)
    )


# Landfill markers
marker_points = [
    [
        float(row["lat"]),
        float(row["lon"]),
        str(row["name"]),
    ]
    for _, row in landfills.iterrows()
]

if marker_points:
    plugins.FastMarkerCluster(
        marker_points
    ).add_to(india_map)

folium.LayerControl(
    collapsed=False
).add_to(india_map)

plugins.Fullscreen().add_to(
    india_map
)

st_folium(
    india_map,
    width=None,
    height=600,
    returned_objects=[],
)


# ============================================================
# ANALYSIS BUTTON
# ============================================================

st.subheader(
    "🇮🇳 India-wide Landfill Analysis"
)

st.info(
    "Dashboard and map are loaded first. "
    "Detailed satellite analysis starts only after "
    "you press the button."
)

run_scan = st.button(
    "🚀 RUN INDIA-WIDE METHANE SCAN",
    type="primary",
    use_container_width=True,
)


# ============================================================
# HELPERS
# ============================================================

def make_feature_collection(df):
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


def safe_float(value):
    try:
        if value is None:
            return np.nan
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def get_property_map(features, field):
    result = {}

    for feature in features:
        props = feature.get(
            "properties",
            {},
        )

        site_id = str(
            props.get("site_id", "")
        )

        result[site_id] = safe_float(
            props.get(field)
        )

    return result


# ============================================================
# ONE CHUNK
# ============================================================

def analyse_chunk(df):
    recent = satellite_collection(
        recent_start,
        recent_end,
    )

    baseline = satellite_collection(
        baseline_start,
        baseline_end,
    )

    recent_image = (
        recent.median()
        .rename("recent_ch4")
    )

    baseline_image = (
        baseline.median()
        .rename("baseline_ch4")
    )

    anomaly_image = (
        recent_image
        .subtract(baseline_image)
        .rename("anomaly")
    )

    std_image = (
        baseline
        .reduce(ee.Reducer.stdDev())
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

    sites = make_feature_collection(df)

    landfill_regions = sites.map(
        lambda feature: feature.buffer(
            radius_km * 1000
        )
    )

    background_regions = sites.map(
        lambda feature: feature.buffer(
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

    raw = (
        stack
        .reduceRegions(
            collection=landfill_regions,
            reducer=ee.Reducer.mean(),
            scale=TROPOMI_SCALE,
            tileScale=8,
        )
        .getInfo()
    )

    raw_background = (
        anomaly_image
        .rename("background")
        .reduceRegions(
            collection=background_regions,
            reducer=ee.Reducer.mean(),
            scale=TROPOMI_SCALE,
            tileScale=8,
        )
        .getInfo()
    )

    features = raw.get(
        "features",
        []
    )

    background_features = raw_background.get(
        "features",
        []
    )

    recent_map = get_property_map(
        features,
        "recent_ch4",
    )

    baseline_map = get_property_map(
        features,
        "baseline_ch4",
    )

    anomaly_map = get_property_map(
        features,
        "anomaly",
    )

    zscore_map = get_property_map(
        features,
        "zscore",
    )

    background_map = get_property_map(
        background_features,
        "background",
    )

    output = df.copy()

    output["recent_ch4_ppb"] = (
        output["site_id"].map(
            lambda x: recent_map.get(
                str(x),
                np.nan,
            )
        )
    )

    output["baseline_ch4_ppb"] = (
        output["site_id"].map(
            lambda x: baseline_map.get(
                str(x),
                np.nan,
            )
        )
    )

    output["anomaly_ppb"] = (
        output["site_id"].map(
            lambda x: anomaly_map.get(
                str(x),
                np.nan,
            )
        )
    )

    output["zscore"] = (
        output["site_id"].map(
            lambda x: zscore_map.get(
                str(x),
                np.nan,
            )
        )
    )

    output["background_anomaly_ppb"] = (
        output["site_id"].map(
            lambda x: background_map.get(
                str(x),
                np.nan,
            )
        )
    )

    output["spatial_contrast_ppb"] = (
        output["anomaly_ppb"]
        - output["background_anomaly_ppb"]
    )

    current = pd.to_numeric(
        output["recent_ch4_ppb"],
        errors="coerce",
    )

    baseline_value = pd.to_numeric(
        output["baseline_ch4_ppb"],
        errors="coerce",
    )

    anomaly_value = pd.to_numeric(
        output["anomaly_ppb"],
        errors="coerce",
    )

    zscore_value = pd.to_numeric(
        output["zscore"],
        errors="coerce",
    )

    spatial_value = pd.to_numeric(
        output["spatial_contrast_ppb"],
        errors="coerce",
    )

    output["anomaly_percent"] = np.where(
        baseline_value > 0,
        (
            (current - baseline_value)
            / baseline_value
        ) * 100,
        np.nan,
    )

    anomaly_component = (
        anomaly_value
        .fillna(0)
        .clip(0, 150)
        / 150
    )

    z_component = (
        zscore_value
        .fillna(0)
        .clip(0, 5)
        / 5
    )

    spatial_component = (
        spatial_value
        .fillna(0)
        .clip(0, 100)
        / 100
    )

    data_component = (
        output["recent_ch4_ppb"]
        .notna()
        .astype(float)
    )

    output["evidence_score"] = (
        100
        * (
            0.50 * anomaly_component
            + 0.30 * z_component
            + 0.15 * spatial_component
            + 0.05 * data_component
        )
    ).clip(0, 100)

    output["confidence"] = (
        100
        * (
            0.70 * data_component
            + 0.30
            * (
                z_component > 0.20
            ).astype(float)
        )
    ).clip(0, 100)

    def status(row):
        score = safe_float(
            row["evidence_score"]
        )

        confidence = safe_float(
            row["confidence"]
        )

        if np.isnan(score):
            return "NO DATA"

        if score >= 70 and confidence >= 60:
            return "HIGH"

        if score >= 40 and confidence >= 45:
            return "ELEVATED"

        return "LOW"

    output["status"] = output.apply(
        status,
        axis=1,
    )

    return output


# ============================================================
# RUN SCAN
# ============================================================

if run_scan:
    chunk_size = 100

    chunks = [
        landfills[
            start:start + chunk_size
        ].copy()
        for start in range(
            0,
            len(landfills),
            chunk_size,
        )
    ]

    progress = st.progress(
        0,
        text="Starting satellite analysis...",
    )

    all_results = []

    try:
        for index, chunk in enumerate(chunks):
            result = analyse_chunk(chunk)
            all_results.append(result)

            done = index + 1
            total = len(chunks)

            progress.progress(
                int(done / total * 100),
                text=(
                    f"Analysed "
                    f"{min(done * chunk_size, len(landfills)):,}"
                    f"/{len(landfills):,} sites"
                ),
            )

        final_results = pd.concat(
            all_results,
            ignore_index=True,
        )

        st.session_state["results"] = final_results

        progress.empty()

        st.success(
            "✅ India-wide methane scan completed."
        )

    except Exception as exc:
        progress.empty()

        st.error(
            "❌ Satellite analysis failed."
        )

        st.exception(exc)


# ============================================================
# RESULTS
# ============================================================

if "results" in st.session_state:
    results = st.session_state["results"].copy()

    # Defensive validation
    if not isinstance(results, pd.DataFrame):
        st.error("Invalid scan result. Please run the scan again.")
        st.stop()

    required_result_columns = [
        "name",
        "lat",
        "lon",
        "recent_ch4_ppb",
        "baseline_ch4_ppb",
        "anomaly_ppb",
        "evidence_score",
        "confidence",
        "status",
    ]

    for column in required_result_columns:
        if column not in results.columns:
            results[column] = np.nan

    results["evidence_score"] = pd.to_numeric(
        results["evidence_score"],
        errors="coerce",
    )

    results["confidence"] = pd.to_numeric(
        results["confidence"],
        errors="coerce",
    )

    results["anomaly_ppb"] = pd.to_numeric(
        results["anomaly_ppb"],
        errors="coerce",
    )

    results = results.sort_values(
        by=[
            "evidence_score",
            "confidence",
        ],
        ascending=False,
        na_position="last",
    ).reset_index(drop=True)

    st.subheader(
        "🔥 Methane Priority Ranking"
    )

    high_count = int(
        (
            results["status"] == "HIGH"
        ).sum()
    )

    elevated_count = int(
        (
            results["status"] == "ELEVATED"
        ).sum()
    )

    valid_count = int(
        results["recent_ch4_ppb"]
        .notna()
        .sum()
    )

    avg_score = results[
        "evidence_score"
    ].mean()

    a, b, c, d = st.columns(4)

    a.metric(
        "Sites analysed",
        f"{len(results):,}",
    )

    b.metric(
        "Usable CH₄",
        f"{valid_count:,}",
    )

    c.metric(
        "HIGH evidence",
        f"{high_count:,}",
    )

    d.metric(
        "Average evidence",
        (
            f"{avg_score:.1f}/100"
            if pd.notna(avg_score)
      