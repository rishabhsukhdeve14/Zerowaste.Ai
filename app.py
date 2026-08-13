
import json
from datetime import datetime, timedelta, timezone

import ee
import folium
import pandas as pd
import streamlit as st
from folium import plugins
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh

# ============================================================
# ZERO WASTE SOLUTIONS — INDIA LANDFILL METHANE MONITOR
# Latest available Sentinel-5P + methane anomaly + wind/plume
# ============================================================

PROJECT_ID = "stalwart-fx-490910-e3"
S5P = "COPERNICUS/S5P/OFFL/L3_CH4"

st.set_page_config(
    page_title="Zero Waste Solutions — India Methane Monitor",
    page_icon="🌍",
    layout="wide",
)

st.markdown(""" <style> .stApp {background:#030712;color:#f8fafc;} .hero {font-size:2rem;font-weight:900; background:linear-gradient(90deg,#38bdf8,#10b981,#f43f5e); -webkit-background-clip:text;-webkit-text-fill-color:transparent;} .card {background:rgba(17,24,39,.82);border:1px solid rgba(255,255,255,.10); border-radius:14px;padding:14px;box-shadow:0 8px 32px rgba(0,0,0,.35);} .small {color:#94a3b8;font-size:.85rem;} </style> """, unsafe_allow_html=True)

# ---------- Earth Engine ----------
@st.cache_resource
def init_ee():
    try:
        if "GCP_SERVICE_ACCOUNT" in st.secrets:
            key = dict(st.secrets["GCP_SERVICE_ACCOUNT"])
            key["private_key"] = key["private_key"].replace("\\n", "\n")
            creds = ee.ServiceAccountCredentials(
                key["client_email"], key_data=json.dumps(key)
            )
            ee.Initialize(credentials=creds, project=PROJECT_ID)
        else:
            ee.Initialize(project=PROJECT_ID)
        return True, "Earth Engine connected"
    except Exception as e:
        return False, str(e)

EE_OK, EE_MSG = init_ee()

# ---------- Refresh UI every 10 minutes ----------
st_autorefresh(interval=10 * 60 * 1000, key="methane_refresh")

st.markdown(
    '<div class="hero">ZERO WASTE SOLUTIONS — INDIA LANDFILL METHANE MONITOR</div>',
    unsafe_allow_html=True,
)
st.caption(
    "Satellite-derived monitoring. The app refreshes automatically, but satellite observations "
    "are not continuous; the dashboard always labels the latest observation actually available."
)

# ---------- Landfill CSV ----------
REQUIRED = {"name", "lat", "lon"}

def load_landfills():
    uploaded = st.sidebar.file_uploader(
        "Upload India landfill CSV",
        type=["csv"],
        help="Required columns: name,lat,lon. Optional: state,city,area_ha,height_m,mass_mt,status"
    )

    if uploaded is not None:
        df = pd.read_csv(uploaded)
        source = "Uploaded CSV"
    else:
        # Small demo only. Replace with your full 3,159-site file.
        df = pd.DataFrame([
            ["Ghazipur (Delhi)", "Delhi", 28.6231, 77.3288, 65.0],
            ["Bhalswa (Delhi)", "Delhi", 28.7410, 77.1517, 62.0],
            ["Okhla (Delhi)", "Delhi", 28.5303, 77.2789, 55.0],
            ["Deonar (Mumbai)", "Maharashtra", 19.0573, 72.9304, 38.0],
            ["Mulund (Mumbai)", "Maharashtra", 19.1678, 72.9567, 30.0],
            ["Pirana (Ahmedabad)", "Gujarat", 22.9831, 72.5802, 50.0],
            ["Jawaharnagar (Hyderabad)", "Telangana", 17.5147, 78.5852, 45.0],
            ["Kodungaiyur (Chennai)", "Tamil Nadu", 13.1360, 80.2640, 35.0],
            ["Durg-Rajnandgaon Yard", "Chhattisgarh", 21.1904, 81.2848, 22.0],
        ], columns=["name", "state", "lat", "lon", "height_m"])
        source = "Demo sites — upload the complete India file for national monitoring"

    df.columns = [c.strip().lower() for c in df.columns]
    missing = REQUIRED - set(df.columns)
    if missing:
        st.error(f"CSV missing required columns: {', '.join(sorted(missing))}")
        st.stop()

    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"]).copy()
    df = df[(df.lat >= 6) & (df.lat <= 38) & (df.lon >= 68) & (df.lon <= 98)].copy()
    df["name"] = df["name"].astype(str)

    return df, source

landfills, landfill_source = load_landfills()

# ---------- Sidebar ----------
st.sidebar.markdown("### 🛰️ Monitoring Controls")
window_days = st.sidebar.slider("Recent satellite window (days)", 3, 14, 7)
baseline_days = st.sidebar.slider("Baseline window (days)", 30, 180, 60)
buffer_km = st.sidebar.slider("Landfill analysis radius (km)", 1, 5, 2)

if not EE_OK:
    st.error(
        "Earth Engine is not connected. Check your Streamlit secrets/service account and "
        f"Earth Engine project. Error: {EE_MSG}"
    )
    st.stop()

# ---------- India geometry ----------
INDIA = (
    ee.FeatureCollection("FAO/GAUL/2015/level0")
    .filter(ee.Filter.eq("ADM0_NAME", "India"))
    .geometry()
)

# ---------- Satellite-availability-aware time windows ----------
# Important: do NOT assume the current clock time equals the latest satellite observation.
# We anchor all analysis windows to the latest S5P observation actually present in Earth Engine.
base_s5p = (
    ee.ImageCollection(S5P)
    .filterBounds(INDIA)
    .select("CH4_column_volume_mixing_ratio_dry_air_bias_corrected")
    .sort("system:time_start", False)
)
latest_img = ee.Image(base_s5p.first())

try:
    latest_ms = latest_img.get("system:time_start").getInfo()
    latest_dt = datetime.fromtimestamp(latest_ms / 1000, tz=timezone.utc)
except Exception:
    st.error("No Sentinel-5P methane observation is currently available in Earth Engine.")
    st.stop()

latest_text = latest_dt.strftime("%Y-%m-%d %H:%M UTC")

recent_end = latest_dt + timedelta(days=1)
recent_start = latest_dt - timedelta(days=window_days)
baseline_start = recent_start - timedelta(days=baseline_days)

def iso(d):
    return d.strftime("%Y-%m-%d")

# ---------- Sentinel-5P methane ----------
@st.cache_resource(ttl=600)
def build_methane_layers(recent_start_s, recent_end_s, baseline_start_s):
    recent = (
        ee.ImageCollection(S5P)
        .filterDate(recent_start_s, recent_end_s)
        .filterBounds(INDIA)
        .select([
            "CH4_column_volume_mixing_ratio_dry_air_bias_corrected",
            "CH4_column_volume_mixing_ratio_dry_air_uncertainty",
        ])
        .map(lambda img: img.updateMask(
            img.select("CH4_column_volume_mixing_ratio_dry_air_uncertainty").lte(10)
        ))
    )

    baseline = (
        ee.ImageCollection(S5P)
        .filterDate(baseline_start_s, recent_start_s)
        .filterBounds(INDIA)
        .select("CH4_column_volume_mixing_ratio_dry_air_bias_corrected")
    )

    recent_mean = recent.mean().clip(INDIA)
    baseline_mean = baseline.mean().clip(INDIA)
    anomaly = recent_mean.subtract(baseline_mean).rename("CH4_anomaly_ppb")

    return recent, baseline, recent_mean, anomaly

recent_ic, baseline_ic, ch4_recent, ch4_anomaly = build_methane_layers(
    iso(recent_start), iso(recent_end), iso(baseline_start)
)

recent_count = recent_ic.size().getInfo()
baseline_count = baseline_ic.size().getInfo()

# ---------- ERA5 wind ----------
@st.cache_resource(ttl=1800)
def latest_wind():
    wind_ic = (
        ee.ImageCollection("ECMWF/ERA5/HOURLY")
        .filterDate(iso(now - timedelta(days=3)), iso(now + timedelta(days=1)))
        .select([
            "u_component_of_wind_10m",
            "v_component_of_wind_10m",
        ])
        .sort("system:time_start", False)
    )
    return wind_ic.first()

wind_img = latest_wind()

# ---------- National landfill scoring ----------
# One server-side operation over all uploaded landfill points.
# Score is a screening/anomaly score, NOT a certified emission rate.
@st.cache_data(ttl=1800)
def score_landfills(df_json, radius_km):
    df = pd.read_json(df_json)
    features = []

    for _, r in df.iterrows():
        props = {"name": str(r["name"])}
        if "state" in df.columns:
            props["state"] = str(r.get("state", ""))
        if "height_m" in df.columns and pd.notna(r.get("height_m")):
            props["height_m"] = float(r["height_m"])

        features.append(
            ee.Feature(
                ee.Geometry.Point([float(r["lon"]), float(r["lat"])]),
                props
            )
        )

    fc = ee.FeatureCollection(features)

    buffers = fc.map(lambda f: f.buffer(radius_km * 1000))

    methane_stats = ch4_recent.reduceRegions(
        collection=buffers,
        reducer=ee.Reducer.mean().combine(
            reducer2=ee.Reducer.max(),
            sharedInputs=True
        ),
        scale=1113,
        tileScale=8,
    )

    anomaly_stats = ch4_anomaly.reduceRegions(
        collection=buffers,
        reducer=ee.Reducer.mean().combine(
            reducer2=ee.Reducer.max(),
            sharedInputs=True
        ),
        scale=1113,
        tileScale=8,
    )

    wind_stats = wind_img.reduceRegions(
        collection=fc,
        reducer=ee.Reducer.mean(),
        scale=27830,
        tileScale=8,
    )

    m = {}
    for f in methane_stats.getInfo()["features"]:
        p = f["properties"]
        m[p["name"]] = {
            "ch4_mean_ppb": p.get("mean"),
            "ch4_max_ppb": p.get("max"),
        }

    a = {}
    for f in anomaly_stats.getInfo()["features"]:
        p = f["properties"]
        a[p["name"]] = {
            "anomaly_mean_ppb": p.get("mean"),
            "anomaly_max_ppb": p.get("max"),
        }

    w = {}
    for f in wind_stats.getInfo()["features"]:
        p = f["properties"]
        u = p.get("u_component_of_wind_10m")
        v = p.get("v_component_of_wind_10m")
        w[p["name"]] = {"u": u, "v": v}

    out = df.copy()
    out["ch4_mean_ppb"] = out["name"].map(lambda x: m.get(x, {}).get("ch4_mean_ppb"))
    out["ch4_max_ppb"] = out["name"].map(lambda x: m.get(x, {}).get("ch4_max_ppb"))
    out["anomaly_mean_ppb"] = out["name"].map(lambda x: a.get(x, {}).get("anomaly_mean_ppb"))
    out["anomaly_max_ppb"] = out["name"].map(lambda x: a.get(x, {}).get("anomaly_max_ppb"))
    out["wind_u_mps"] = out["name"].map(lambda x: w.get(x, {}).get("u"))
    out["wind_v_mps"] = out["name"].map(lambda x: w.get(x, {}).get("v"))

    out["wind_speed_mps"] = (
        (out["wind_u_mps"].fillna(0) ** 2 + out["wind_v_mps"].fillna(0) ** 2) ** 0.5
    )

    # Meteorological direction: direction wind is travelling TO, clockwise from north.
    import numpy as np
    out["wind_to_deg"] = (
        (np.degrees(np.arctan2(out["wind_u_mps"], out["wind_v_mps"])) + 360) % 360
    )

    # Conservative screening score based on anomaly + absolute CH4.
    # This is deliberately NOT called an emission rate.
    out["screening_score"] = (
        0.65 * out["anomaly_mean_ppb"].fillna(0).clip(lower=0) +
        0.35 * (out["ch4_mean_ppb"].fillna(0) - 1800).clip(lower=0)
    )

    def label(x):
        if pd.isna(x):
            return "NO DATA"
        if x >= 120:
            return "HIGH"
        if x >= 50:
            return "ELEVATED"
        return "LOW"

    out["status"] = out["screening_score"].apply(label)
    return out

results = score_landfills(landfills.to_json(orient="records"), buffer_km)

# ---------- KPI ----------
high = int((results.status == "HIGH").sum())
elevated = int((results.status == "ELEVATED").sum())

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Landfill nodes", f"{len(results):,}")
c2.metric("Recent S5P scenes", f"{recent_count:,}")
c3.metric("Baseline scenes", f"{baseline_count:,}")
c4.metric("High screening", f"{high:,}")
c5.metric("Latest S5P observation", latest_text)

st.markdown(
    f'<div class="card"><b>Data status:</b> {landfill_source}<br>'
    f'<span class="small">S5P latest observation: {latest_text} | '
    f'Recent window: {iso(recent_start)} → {iso(now)} | '
    f'Baseline: {iso(baseline_start)} → {iso(recent_start)}</span></div>',
    unsafe_allow_html=True,
)

# ---------- India map ----------
st.markdown("### 🇮🇳 India methane field + landfill screening map")

m = folium.Map(
    location=[22.5, 80.0],
    zoom_start=5,
    tiles="CartoDB dark_matter",
    control_scale=True,
)

# Satellite methane concentration layer.
try:
    vis_ch4 = {
        "min": 1750,
        "max": 2000,
        "palette": ["0b1020", "2563eb", "06b6d4", "22c55e", "eab308", "f97316", "ef4444"],
    }
    ch4_map = ch4_recent.getMapId(vis_ch4)
    folium.TileLayer(
        tiles=ch4_map["tile_fetcher"].url_format,
        attr="Copernicus / ESA Sentinel-5P TROPOMI",
        name="S5P CH4 (recent mean)",
        overlay=True,
        control=True,
        opacity=0.62,
    ).add_to(m)
except Exception as e:
    st.warning(f"Could not render methane raster layer: {e}")

# Methane anomaly layer.
try:
    vis_anom = {
        "min": -30,
        "max": 80,
        "palette": ["313695", "74add1", "ffffbf", "f46d43", "a50026"],
    }
    anom_map = ch4_anomaly.getMapId(vis_anom)
    folium.TileLayer(
        tiles=anom_map["tile_fetcher"].url_format,
        attr="Copernicus / ESA Sentinel-5P TROPOMI",
        name="CH4 anomaly vs baseline",
        overlay=True,
        control=True,
        opacity=0.68,
    ).add_to(m)
except Exception as e:
    st.warning(f"Could not render anomaly layer: {e}")

# Landfill points + wind direction.
for _, r in results.iterrows():
    if pd.isna(r["lat"]) or pd.isna(r["lon"]):
        continue

    status = r["status"]
    if status == "HIGH":
        icon_color = "red"
    elif status == "ELEVATED":
        icon_color = "orange"
    elif status == "LOW":
        icon_color = "green"
    else:
        icon_color = "gray"

    popup = f""" <b>{r['name']}</b><br> Status: {status}<br> CH₄ mean: {r['ch4_mean_ppb']:.1f} ppb<br> CH₄ max: {r['ch4_max_ppb']:.1f} ppb<br> Anomaly mean: {r['anomaly_mean_ppb']:.1f} ppb<br> Anomaly max: {r['anomaly_max_ppb']:.1f} ppb<br> Wind: {r['wind_speed_mps']:.1f} m/s<br> Wind-to: {r['wind_to_deg']:.0f}° """

    folium.CircleMarker(
        location=[r["lat"], r["lon"]],
        radius=6 if status != "HIGH" else 9,
        color=icon_color,
        fill=True,
        fill_color=icon_color,
        fill_opacity=0.9,
        popup=folium.Popup(popup, max_width=340),
        tooltip=f"{r['name']} — {status}",
    ).add_to(m)

    # Simple plume-direction arrow. This is a visualization of wind transport,
    # not a satellite-derived methane plume boundary.
    if pd.notna(r["wind_speed_mps"]) and r["wind_speed_mps"] >= 1:
        folium.Marker(
            [r["lat"], r["lon"]],
            icon=folium.DivIcon(
                html=f""" <div style=" transform: rotate({r['wind_to_deg']}deg); font-size:18px;color:white; text-shadow:0 0 3px black; width:20px;height:20px;">➤</div> """
            ),
        ).add_to(m)

folium.LayerControl(collapsed=False).add_to(m)
plugins.Fullscreen().add_to(m)

st_folium(m, width=None, height=650, returned_objects=[])

# ---------- Ranked table ----------
st.markdown("### 🔥 National landfill screening ranking")

show_cols = [
    "name", "state", "lat", "lon",
    "ch4_mean_ppb", "ch4_max_ppb",
    "anomaly_mean_ppb", "anomaly_max_ppb",
    "wind_speed_mps", "wind_to_deg", "status"
]
show_cols = [c for c in show_cols if c in results.columns]

ranked = results.sort_values(
    ["screening_score", "anomaly_max_ppb"],
    ascending=False,
    na_position="last"
)

st.dataframe(
    ranked[show_cols].round(2),
    use_container_width=True,
    hide_index=True,
)

csv = ranked.to_csv(index=False).encode("utf-8")
st.download_button(
    "⬇️ Download national methane screening CSV",
    csv,
    "india_landfill_methane_screening.csv",
    "text/csv",
)

st.markdown(""" ### ⚠️ Scientific interpretation - Sentinel-5P/TROPOMI is the national atmospheric methane layer. Its Earth Engine methane product has ~1.1 km pixels and a nominal 2-day revisit, so it is **not a continuous live sensor**. - The anomaly layer compares the recent satellite window with an earlier baseline. - A high value near a landfill is a **screening signal**, not proof that the landfill alone caused the methane. Urban gas networks, wastewater, agriculture, wetlands and other sources can overlap. - The wind arrows show the direction of modeled 10-m wind transport. They are not the measured boundary of a methane plume. - Do not convert a single TROPOMI ppb value directly into tonnes/hour. Emission-rate inversion requires wind/atmospheric transport, background estimation and plume attribution. - Sentinel-2 is useful for high-resolution landfill surface/land-cover monitoring, but it should not be treated as a native continuous methane sensor. """)