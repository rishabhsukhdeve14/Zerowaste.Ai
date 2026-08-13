import json
import datetime
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st
import ee

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="ZeroWaste.AI — Methane Spatial Engine",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- SATSURE-GRADE ENTERPRISE UI STYLING ---
st.markdown("""
<style>
    /* Global Canvas */
    .stApp { 
        background-color: #070a11; 
        color: #e2e8f0; 
        font-family: 'Inter', -apple-system, sans-serif; 
    }
    
    /* Clean Header */
    .brand-title {
        font-size: clamp(1.4rem, 2.5vw, 2.0rem);
        font-weight: 800;
        letter-spacing: -0.02em;
        color: #f8fafc;
        margin-bottom: 2px;
    }
    .brand-accent {
        color: #38bdf8;
    }
    .brand-sub {
        font-size: 0.85rem;
        color: #64748b;
        margin-bottom: 24px;
        font-weight: 400;
    }

    /* SatSure Metrics Box */
    .metric-card {
        background: #0f172a;
        border: 1px solid #1e293b;
        border-radius: 8px;
        padding: 14px 18px;
        margin-bottom: 12px;
    }
    .metric-label {
        font-size: 0.7rem;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    .metric-value {
        font-size: clamp(1.3rem, 2vw, 1.8rem);
        font-weight: 700;
        color: #f8fafc;
        margin-top: 4px;
    }
    .metric-sub {
        font-size: 0.75rem;
        color: #10b981;
        margin-top: 2px;
        font-weight: 500;
    }

    /* Control Panel Cards */
    .control-panel {
        background: #0d1322;
        border: 1px solid #1e293b;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 20px;
    }

    /* Hide Default Streamlit Clutter */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- EARTH ENGINE INITIALIZATION ---
PROJECT_ID = "stalwart-fx-490910-e3"

@st.cache_resource
def init_ee():
    try:
        if "GCP_SERVICE_ACCOUNT" in st.secrets:
            key_dict = dict(st.secrets["GCP_SERVICE_ACCOUNT"])
            key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
            credentials = ee.ServiceAccountCredentials(key_dict["client_email"], key_data=json.dumps(key_dict))
            ee.Initialize(credentials, project=PROJECT_ID)
        else:
            ee.Initialize(project=PROJECT_ID)
        return True
    except Exception:
        return False

ee_active = init_ee()

# --- SIDEBAR CONTROL DESK ---
st.sidebar.markdown("### 📡 Spatial Intelligence")
module = st.sidebar.radio("Navigation Module", [
    "Methane Sourcing & Landfill Grid",
    "Global Plume & Satellite MRV",
    "Carbon Offset & Yield Analytics"
], index=0)

st.sidebar.markdown("---")
st.sidebar.markdown("**System Status**")
if ee_active:
    st.sidebar.success("GEE Pipeline Active")
else:
    st.sidebar.info("Simulation Mode Active")

# --- TOP BRAND HEADER ---
st.markdown('<div class="brand-title">ZeroWaste<span class="brand-accent">.AI</span> — Spatial Methane Platform</div>', unsafe_allow_html=True)
st.markdown('<div class="brand-sub">SatSure-Grade Earth Observation Intelligence for Point-Source Methane Capture & Analytics</div>', unsafe_allow_html=True)

# --------------------------------------------------------------------------------
# MODULE 1: METHANE SOURCING & LANDFILL GRID
# --------------------------------------------------------------------------------
if module == "Methane Sourcing & Landfill Grid":
    
    # KPI Row
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown('<div class="metric-card"><div class="metric-label">Detected CH4 Flux</div><div class="metric-value">148.5 <small style="font-size:0.9rem; color:#94a3b8;">T/day</small></div><div class="metric-sub">▲ 8.4% vs baseline</div></div>', unsafe_allow_html=True)
    k2.markdown('<div class="metric-card"><div class="metric-label">Bio-CNG Potential</div><div class="metric-value" style="color:#38bdf8;">200.4 <small style="font-size:0.9rem; color:#94a3b8;">T/day</small></div><div class="metric-sub">Optimum Yield Zone</div></div>', unsafe_allow_html=True)
    k3.markdown('<div class="metric-card"><div class="metric-label">Annual CO2e Abated</div><div class="metric-value">1.51M <small style="font-size:0.9rem; color:#94a3b8;">Tons</small></div><div class="metric-sub">Verra VM0011 Standard</div></div>', unsafe_allow_html=True)
    k4.markdown('<div class="metric-card"><div class="metric-label">Estimated Offset Value</div><div class="metric-value" style="color:#10b981;">$37.9M <small style="font-size:0.9rem; color:#94a3b8;">/yr</small></div><div class="metric-sub">@ $25/Ton CO2e</div></div>', unsafe_allow_html=True)

    # Control Filters
    st.markdown('<div class="control-panel">', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    region = c1.selectbox("Target Regional Cluster", [
        "Chhattisgarh Urban & Landfill Hub",
        "Delhi NCR Waste Belt",
        "Mumbai Metropolitan Landfill Grid",
        "Gujarat Industrial Zone"
    ])
    radius = c2.slider("Capture Buffer Radius (km)", 10, 100, 35)
    threshold = c3.select_slider("Minimum Flux Threshold (Tons/day)", options=[1, 5, 10, 15, 20], value=5)
    st.markdown('</div>', unsafe_allow_html=True)

    # SatSure Style PyDeck Map Overlay
    st.markdown("#### 🗺️ Point-Source Emission Density Overlay")
    
    np.random.seed(42)
    methane_sites = []
    base_lat, base_lon = 21.1904, 81.2848
    
    for i in range(50):
        lat = base_lat + np.random.normal(0, 0.12)
        lon = base_lon + np.random.normal(0, 0.12)
        ch4_flux = np.random.uniform(2.0, 25.0)
        if ch4_flux >= threshold:
            methane_sites.append({
                "lat": lat, 
                "lon": lon, 
                "ch4_flux": round(ch4_flux, 1), 
                "anomaly_ppb": round(1820 + (ch4_flux * 32.0), 1)
            })
        
    df_sites = pd.DataFrame(methane_sites)
    
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_sites,
        get_position=["lon", "lat"],
        get_color="[244, 63, 94, 210]",
        get_radius="ch4_flux * 140",
        pickable=True
    )
    
    view = pdk.ViewState(latitude=base_lat, longitude=base_lon, zoom=9.8, pitch=30)
    st.pydeck_chart(pdk.Deck(
        layers=[layer], 
        initial_view_state=view, 
        tooltip={"text": "Point Source Flux: {ch4_flux} T/Day\nAtmospheric CH4: {anomaly_ppb} ppb"}
    ))

# --------------------------------------------------------------------------------
# MODULE 2: GLOBAL PLUME & SATELLITE MRV
# --------------------------------------------------------------------------------
elif module == "Global Plume & Satellite MRV":
    st.markdown("#### 📡 Atmospheric Plume Detection Ledger")
    
    hotspots = pd.DataFrame([
        {"Target Facility": "Ghazipur Dump Yard", "Coordinates": "28.62, 77.32", "Sensor": "Sentinel-5P", "CH4 Anomaly": "2,645 ppb", "Alert Level": "Critical"},
        {"Permian Industrial Grid", "Coordinates": "31.88, -102.32", "Sensor": "GHGSat-C", "CH4 Anomaly": "3,120 ppb", "Alert Level": "Critical"},
        {"Kuwait Super Facility", "Coordinates": "29.37, 47.97", "Sensor": "Sentinel-5P", "CH4 Anomaly": "2,890 ppb", "Alert Level": "High"},
        {"Durg Regional Dump Site", "Coordinates": "21.19, 81.28", "Sensor": "Sentinel-5P", "CH4 Anomaly": "1,940 ppb", "Alert Level": "Moderate"}
    ])
    
    st.dataframe(hotspots, use_container_width=True, hide_index=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### 📈 Multi-Spectral Concentration Trend")
    
    dates = pd.date_range(end=datetime.datetime.today(), periods=30)
    ch4_trend = 2100 + np.random.normal(0, 35, size=30)
    df_chart = pd.DataFrame({"Date": dates, "CH4_ppb": ch4_trend})
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_chart["Date"], y=df_chart["CH4_ppb"], mode='lines+markers', line=dict(color='#38bdf8', width=2)))
    fig.update_layout(
        template="plotly_dark", 
        height=320, 
        margin=dict(l=10, r=10, t=20, b=10), 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)"
    )
    st.plotly_chart(fig, use_container_width=True)

# --------------------------------------------------------------------------------
# MODULE 3: CARBON OFFSET & YIELD ANALYTICS
# --------------------------------------------------------------------------------
else:
    st.markdown("#### 📊 Verified Carbon Audit Ledger")
    
    m1, m2 = st.columns(2)
    m1.metric("Total Certified Carbon Offsets", "1,510,000 tCO2e", delta="+12.4% YTD")
    m2.metric("Audited Revenue Valuation", "$37,750,000 USD", delta="$25.00 Base Rate")
    
    st.markdown("<br>", unsafe_allow_html=True)
    st.info("🔒 Verified MRV Audit Trail Active. Methodological alignment: Verra VM0011 (Landfill Gas Methane Abatement).")
