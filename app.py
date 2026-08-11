import json
import os
from datetime import datetime, timedelta, timezone

import ee
import folium
import numpy as np
import pandas as pd
import streamlit as st
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium


# ============================================================
# ZERO WASTE.AI
# ============================================================

PROJECT_ID = "stalwart-fx-490910-e3"
S5P = "COPERNICUS/S5P/OFFL/L3_CH4"

CH4_BAND = "CH4_column_volume_mixing_ratio_dry_air"
UNC_BAND = "CH4_column_volume_mixing_ratio_dry_air_uncertainty"

st.set_page_config(
    page_title="ZeroWaste.AI",
    page_icon="🌍",
    layout="wide",
)

st.markdown(
    """ <style> .stApp { background:#020617; color:#f8fafc; } .hero { font-size:3rem; font-weight:900; background:linear-gradient(90deg,#38bdf8,#22c55e,#f43f5e); -webkit-background-clip:text; -webkit-text-fill-color:transparent; } .card { background:#0f172a; border:1px solid #1e293b; border-radius:14px; padding:16px; margin:10px 0; } </style> """,
    unsafe_allow_html=True,
)


# ============================================================
# EARTH ENGINE CONNECTION
# ============================================================

@st.cache_resource
def init_ee():
    try:
        if "GCP_SERVICE_ACCOUNT" in st.secrets:
            key = dict(st.secrets["GCP_SERVICE_ACCOUNT"])
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


EE_OK, EE_ERROR = init_ee()

st.markdown(
    '<div class="hero">ZERO WASTE.AI</div>',
    unsafe_allow_html=True,
)

st.markdown(
    "🇮🇳 India-wide methane intelligence • "
    "Sentinel-5P/TROPOMI • Landfill screening"
)

if EE_OK:
    st.success(
        "🛰️ Earth Engine connected • Project: "
        + PROJECT_ID
    )
else:
    st.error("Earth Engine connection failed")
    st.code(EE_ERROR)
    st.stop()


# ============================================================
# CONTROLS
# ============================================================

st.sidebar.header("⚙️ Satellite Controls")

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
    "Landfill analysis radius",
    1,
    5,
    2,
)

uncertainty_limit = st.sidebar.slider(
    "Maximum uncertainty",
    1.0,
    10.0,
    5.0,
    0.5,
)


# ============================================================
# LANDfill DATABASE
# ============================================================

def load_sites():
    uploaded = st.sidebar.file_uploader(
        "Upload landfill CSV",
        type=["csv"],
    )

    if uploaded is not None:
        data = pd.read_csv(uploaded)
        source = "Uploaded CSV"
    elif os.path.exists("landfills.csv"):
        data = pd.read_csv("landfills.csv")
        source = "landfills.csv"
    else:
        data = pd.DataFrame(
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
        source = "Demo sites"

    data.columns = [
        str(x).strip().lower()
        for x in data.columns
    ]

    required = {"name", "lat", "lon"}
    missing = required - set(data.columns)

    if missing:
        st.error(
            "CSV needs name, lat, lon. Missing: "
            + ", ".join(sorted(missing))
        )
        st.stop()

    data["name"] = data["name"].astype(str)
    data["lat"] = pd.to_numeric(
        data["lat"], errors="coerce"
    )
    data["lon"] = pd.to_numeric(
        data["lon"], errors="coerce"
    )

    data = data.dropna(
        subset=["lat", "lon"]
    )

    data = data[
        (data["lat"] >= 6)
        & (data["lat"] <= 38)
        & (data["lon"] >= 68)
        & (data["lon"] <= 98)
    ].copy()

    data = data.drop_duplicates(
        subset=["lat", "lon"]
    ).reset_index(drop=True)

    data["site_id"] = data.index.astype(str)

    return data, source


sites, source = load_sites()

st.sidebar.success(
    f"{len(sites):,} landfill sites loaded"
)


# ============================================================
# DATES
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
    - timedelta(days=recent_days + baseline_days)
).strftime("%Y-%m-%d")

baseline_end = recent_start


# ============================================================
# SATELLITE COLLECTION
# ============================================================

def make_collection(start_date, end_date):
    collection = (
        ee.ImageCollection(S5P)
        .filterDate(start_date, end_date)
        .filterBounds(
            ee.Geometry.Rectangle(
                [68, 6, 98, 38]
            )
        )
        .select(
            [CH4_BAND, UNC_BAND]
        )
    )

    def mask_image(image):
        return image.select(CH4_BAND).updateMask(
            image.select(UNC_BAND).lte(
                uncertainty_limit
            )
        )

    return collection.map(mask_image)


recent_collection = make_collection(
    recent_start,
    recent_end,
)


# ============================================================
# MAP
# ============================================================

st.subheader("🗺️ India Methane Map")

st.markdown(
    f""" <div class="card"> <b>Satellite period:</b> {recent_start} → {recent_end}<br> <b>Database:</b> {source}<br> <b>Sites:</b> {len(sites):,} </div> """,
    unsafe_allow_html=True,
)

india_map = folium.Map(
    location=[22.5, 80.0],
    zoom_start=5,
    tiles="CartoDB dark_matter",
)

try:
    methane_image = (
        recent_collection
        .median()
        .rename("CH4")
    )

    map_info = methane_image.getMapId(
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
        tiles=map_info["tile_fetcher"].url_format,
        attr="Copernicus Sentinel-5P/TROPOMI",
        name="Sentinel-5P CH4",
        overlay=True,
        opacity=0.65,
    ).add_to(india_map)

except Exception as exc:
    st.warning(
        "CH4 map layer unavailable: "
        + str(exc)
    )


cluster = MarkerCluster(
    name="Landfills"
).add_to(india_map)

for _, row in sites.iterrows():
    folium.Marker(
        [
            float(row["lat"]),
            float(row["lon"]),
        ],
        popup=str(row["name"]),
        tooltip=str(row["name"]),
    ).add_to(cluster)

folium.LayerControl().add_to(india_map)

st_folium(
    india_map,
    width=None,
    height=600,
    returned_objects=[],
)


# ============================================================
# ANALYSIS FUNCTIONS
# ============================================================

def make_fc(frame):
    features = []

    for _, row in frame.iterrows():
        point = ee.Geometry.Point(
            [
                float(row["lon"]),
                float(row["lat"]),
            ]
        )

        features.append(
            ee.Feature(
                point,
                {
                    "site_id": str(row["site_id"]),
                    "name": str(row["name"]),
                },
            )
        )

    return ee.FeatureCollection(features)


def property_map(feature_list, field):
    output = {}

    for item in feature_list:
        props = item.get(
            "properties",
            {},
        )

        site_id = str(
            props.get("site_id", "")
        )

        value = props.get(field)

        try:
            output[site_id] = float(value)
        except (TypeError, ValueError):
            output[site_id] = np.nan

    return output


def analyse_chunk(frame):
    recent = make_collection(
        recent_start,
        recent_end,
    )

    baseline = make_collection(
        baseline_start,
        baseline_end,
    )

    recent_image = (
        recent.median()
        .rename("recent")
    )

    baseline_image = (
        baseline.median()
        .rename("baseline")
    )

    anomaly = (
        recent_image
        .subtract(baseline_image)
        .rename("anomaly")
    )

    stddev = (
        baseline
        .reduce(ee.Reducer.stdDev())
        .rename("std")
    )

    zscore = (
        anomaly
        .divide(
            stddev.max(
                ee.Image.constant(2)
            )
        )
        .rename("zscore")
    )

    fc = make_fc(frame)

    local_regions = fc.map(
        lambda feature: feature.buffer(
            radius_km * 1000
        )
    )

    background_regions = fc.map(
        lambda feature: feature.buffer(
            radius_km * 3000
        )
    )

    image_stack = ee.Image.cat(
        [
            recent_image,
            baseline_image,
            anomaly,
            zscore,
        ]
    )

    local_raw = (
        image_stack
        .reduceRegions(
            collection=local_regions,
            reducer=ee.Reducer.mean(),
            scale=1113,
            tileScale=8,
        )
        .getInfo()
    )

    background_raw = (
        anomaly
        .reduceRegions(
            collection=background_regions,
            reducer=ee.Reducer.mean(),
            scale=1113,
            tileScale=8,
        )
        .getInfo()
    )

    local_features = local_raw.get(
        "features",
        []
    )

    background_features = background_raw.get(
        "features",
        []
    )

    recent_map = property_map(
        local_features,
        "recent",
    )

    baseline_map = property_map(
        local_features,
        "baseline",
    )

    anomaly_map = property_map(
        local_features,
        "anomaly",
    )

    z_map = property_map(
        local_features,
        "zscore",
    )

    background_map = property_map(
        background_features,
        "anomaly",
    )

    result = frame.copy()

    result["recent_ch4_ppb"] = result[
        "site_id"
    ].map(
        lambda x: recent_map.get(
            str(x),
            np.nan,
        )
    )

    result["baseline_ch4_ppb"] = result[
        "site_id"
    ].map(
        lambda x: baseline_map.get(
            str(x),
            np.nan,
        )
    )

    result["anomaly_ppb"] = result[
        "site_id"
    ].map(
        lambda x: anomaly_map.get(
            str(x),
            np.nan,
        )
    )

    result["zscore"] = result[
        "site_id"
    ].map(
        lambda x: z_map.get(
            str(x),
            np.nan,
        )
    )

    result["background_anomaly_ppb"] = result[
        "site_id"
    ].map(
        lambda x: background_map.get(
            str(x),
            np.nan,
        )
    )

    result["spatial_contrast_ppb"] = (
        result["anomaly_ppb"]
        - result["background_anomaly_ppb"]
    )

    current = pd.to_numeric(
        result["recent_ch4_ppb"],
        errors="coerce",
    )

    baseline_value = pd.to_numeric(
        result["baseline_ch4_ppb"],
        errors="coerce",
    )

    anomaly_value = pd.to_numeric(
        result["anomaly_ppb"],
        errors="coerce",
    )

    z_value = pd.to_numeric(
        result["zscore"],
        errors="coerce",
    )

    spatial_value = pd.to_numeric(
        result["spatial_contrast_ppb"],
        errors="coerce",
    )

    result["anomaly_percent"] = np.where(
        baseline_value > 0,
        (
            (current - baseline_value)
            / baseline_value
        ) * 100,
        np.nan,
    )

    anomaly_score = (
        anomaly_value
        .fillna(0)
        .clip(0, 150)
        / 150
    )

    z_score = (
        z_value
        .fillna(0)
        .clip(0, 5)
        / 5
    )

    spatial_score = (
        spatial_value
        .fillna(0)
        .clip(0, 100)
        / 100
    )

    data_score = (
        result["recent_ch4_ppb"]
        .notna()
        .astype(float)
    )

    result["evidence_score"] = (
        100
        * (
            0.50 * anomaly_score
            + 0.30 * z_score
            + 0.15 * spatial_score
            + 0.05 * data_score
        )
    ).clip(0, 100)

    result["confidence"] = (
        100
        * (
            0.70 * data_score
            + 0.30 * (
                z_score > 0.20
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
# RUN
# ============================================================

st.subheader("🚀 India-wide analysis")

run_scan = st.button(
    "RUN INDIA-WIDE METHANE SCAN",
    type="primary",
    use_container_width=True,
)

if run_scan:
    chunk_size = 100
    chunks = []

    for start in range(
        0,
        len(sites),
        chunk_size,
    ):
        chunks.append(
            sites[
                start:start + chunk_size
            ].copy()
        )

    progress = st.progress(
        0,
        text="Starting...",
    )

    results_list = []

    try:
        total = len(chunks)

        for index, chunk in enumerate(chunks):
            results_list.append(
                analyse_chunk(chunk)
            )

            progress.progress(
                int(
                    ((index + 1) / total)
                    * 100
                ),
                text=(
                    f"Analysed "
                    f"{min((index + 1) * chunk_size, len(sites)):,}"
                    f"/{len(sites):,} sites"
                ),
            )

        results = pd.concat(
            results_list,
            ignore_index=True,
        )

        st.session_state[
            "results"
        ] = results

        progress.empty()

        st.success(
            "✅ India-wide methane scan completed."
        )

    except Exception as exc:
        progress.empty()
        st.error("❌ Scan failed")
        st.exception(exc)


# ============================================================
# RESULTS
# ============================================================

if "results" in st.session_state:
    results = st.session_state["results"].copy()

    results["evidence_score"] = pd.to_numeric(
        results["evidence_score"],
        errors="coerce",
    )

    results["confidence"] = pd.to_numeric(
        results["confidence"],
        errors="coerce",
    )

    results = results.sort_values(
        "evidence_score",
        ascending=False,
        na_position="last",
    )

    st.subheader("🔥 Methane Priority Ranking")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Sites analysed",
        f"{len(results):,}",
    )

    c2.metric(
        "Usable CH4",
        f"{results['recent_ch4_ppb'].notna().sum():,}",
    )

    c3.metric(
        "HIGH evidence",
        f"{(results['status'] == 'HIGH').sum():,}",
    )

    average = results[
        "evidence_score"
    ].mean()

    c4.metric(
        "Average evidence",
        (
            f"{average:.1f}/100"
            if pd.notna(average)
            else "N/A"
        ),
    )

    display_columns = [
        "name",
        "state",
        "lat",
        "lon",
        "recent_ch4_ppb",
        "baseline_ch4_ppb",
        "anomaly_ppb",
        "anomaly_percent",
        "zscore",
        "background_anomaly_ppb",
        "spatial_contrast_ppb",
        "evidence_score",
        "confidence",
        "status",
    ]

    display_columns = [
        x
        for x in display_columns
        if x in results.columns
    ]

    table = results[
        display_columns
    ].copy()

    numeric = table.select_dtypes(
        include=[np.number]
    ).columns

    table[numeric] = table[
        numeric
    ].round(2)

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "⬇️ Download methane CSV",
        data=results.to_csv(
            index=False
        ).encode("utf-8"),
        file_name="zerowaste_ai_methane.csv",
        mime="text/csv",
        use_container_width=True,
    )


# ============================================================
# DISCLAIMER
# ============================================================

st.markdown(
    """ <div class="card"> <b>Scientific interpretation</b><br><br> Sentinel-5P/TROPOMI measures atmospheric-column methane. This system ranks landfill areas using recent methane, historical baseline, anomaly, local/background contrast, and uncertainty. <br><br> The score is a screening indicator. It is not a direct measurement of methane emission rate in kg/hour and should not be interpreted as proof that a particular landfill is the sole methane source. </div> """,
    unsafe_allow_html=True,
)