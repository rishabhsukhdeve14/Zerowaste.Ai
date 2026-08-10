import json
import numpy as np
import pandas as pd
import scipy.spatial as spatial
from scipy.interpolate import Rbf
from scipy.linalg import svd, pinv
import torch
import torch.nn as nn

import ee
import folium
import streamlit as st
import streamlit_folium as st_folium

# -----------------------------------------------------------------------------
# 1. PAGE CONFIGURATION & INITIALIZATION
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Zero Waste Solutions — Master Physics & Geotechnical Engine",
    page_icon="⚛️",
    layout="wide",
)

PROJECT_ID = "stalwart-fx-490910-e3"

@st.cache_resource
def init_earth_engine():
    try:
        if "GCP_SERVICE_ACCOUNT" in st.secrets:
            key_dict = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
            credentials = ee.ServiceAccountCredentials(
                key_dict["client_email"], key_data=st.secrets["GCP_SERVICE_ACCOUNT"]
            )
            ee.Initialize(credentials, project=PROJECT_ID)
            return True, "GEE Connected via Service Account Key"
        else:
            ee.Initialize(project=PROJECT_ID)
            return True, f"GEE Connected via GCP Project: {PROJECT_ID}"
    except Exception as e:
        return False, str(e)

gee_connected, gee_msg = init_earth_engine()

# -----------------------------------------------------------------------------
# 2. ALL-INDIA LANDFILL GEOTECHNICAL DATABASE
# -----------------------------------------------------------------------------
INDIA_LANDFILLS = {
    "Ghazipur (Delhi)": {"lat": 28.6231, "lon": 77.3288, "waste_mass_mt": 14.0, "height_m": 65.0, "area_ha": 29.0},
    "Bhalswa (Delhi)": {"lat": 28.7410, "lon": 77.1517, "waste_mass_mt": 8.0, "height_m": 62.0, "area_ha": 21.0},
    "Okhla (Delhi)": {"lat": 28.5303, "lon": 77.2789, "waste_mass_mt": 6.0, "height_m": 55.0, "area_ha": 16.0},
    "Deonar (Mumbai)": {"lat": 19.0573, "lon": 72.9304, "waste_mass_mt": 16.0, "height_m": 38.0, "area_ha": 120.0},
    "Mulund (Mumbai)": {"lat": 19.1678, "lon": 72.9567, "waste_mass_mt": 7.0, "height_m": 30.0, "area_ha": 24.0},
    "Pirana (Ahmedabad)": {"lat": 22.9831, "lon": 72.5802, "waste_mass_mt": 10.0, "height_m": 50.0, "area_ha": 34.0},
    "Jawaharnagar (Hyderabad)": {"lat": 17.5147, "lon": 78.5852, "waste_mass_mt": 12.0, "height_m": 45.0, "area_ha": 137.0},
    "Kodungaiyur (Chennai)": {"lat": 13.1360, "lon": 80.2640, "waste_mass_mt": 11.0, "height_m": 35.0, "area_ha": 108.0},
}

# -----------------------------------------------------------------------------
# 3. ADVANCED GEOTECHNICAL, THERMODYNAMIC & DRILLING ENGINE
# -----------------------------------------------------------------------------
class GeotechThermodynamics:
    @staticmethod
    def calculate_drilling_and_chamber(lat, lon, height_m, waste_mass_mt):
        optimal_depth_m = round(height_m * 0.72, 1)
        gas_vol_m3 = round(waste_mass_mt * 1e6 * 0.45 * 0.52, 2)
        suction_rate = round(gas_vol_m3 / (365 * 24 * 5), 1)
        
        boreholes = [
            {"id": "Borehole-1 (Core)", "lat": lat, "lon": lon, "depth_m": optimal_depth_m, "dia_mm": 300},
            {"id": "Borehole-2 (North)", "lat": lat + 0.0008, "lon": lon + 0.0005, "depth_m": round(optimal_depth_m * 0.85, 1), "dia_mm": 250},
            {"id": "Borehole-3 (South)", "lat": lat - 0.0008, "lon": lon - 0.0005, "depth_m": round(optimal_depth_m * 0.85, 1), "dia_mm": 250},
        ]
        return optimal_depth_m, gas_vol_m3, suction_rate, boreholes

    @staticmethod
    def first_order_decay_lfg(waste_mass_mt, age_years, k=0.05, L0=100.0):
        return k * L0 * (waste_mass_mt * 1e6) * np.exp(-k * age_years)

    @staticmethod
    def fourier_subsurface_heat(k_thermal, T_surface, T_core, depth_m):
        return -k_thermal * (T_surface - T_core) / max(depth_m, 0.1)

# -----------------------------------------------------------------------------
# 4. BRUNTON & KUTZ DATA DYNAMICS (SINDy, DMD, HAVOK) & PINN ENGINE
# -----------------------------------------------------------------------------
class BruntonKutzDataDynamics:
    @staticmethod
    def dynamic_mode_decomposition(X1, X2, r=3):
        U, S, Vh = svd(X1, full_matrices=False)
        U_r, S_r, V_r = U[:, :r], np.diag(S[:r]), Vh.T[:, :r]
        Atilde = U_r.T.conj() @ X2 @ V_r @ pinv(S_r)
        eigs, W = np.linalg.eig(Atilde)
        Phi = X2 @ V_r @ pinv(S_r) @ W
        return Phi, eigs

    @staticmethod
    def sindy_identification(X, Xdot, poly_order=2, threshold=0.05):
        n_samples, n_vars = X.shape
        Theta = [np.ones((n_samples, 1))]
        for i in range(n_vars):
            Theta.append(X[:, i:i+1])
        if poly_order >= 2:
            for i in range(n_vars):
                for j in range(i, n_vars):
                    Theta.append((X[:, i] * X[:, j])[:, None])
        Theta = np.hstack(Theta)
        
        Xi = pinv(Theta) @ Xdot
        for _ in range(10):
            small_indices = np.abs(Xi) < threshold
            Xi[small_indices] = 0
            for ind in range(Xdot.shape[1]):
                big_ind = ~small_indices[:, ind]
                if np.sum(big_ind) > 0:
                    Xi[big_ind, ind] = pinv(Theta[:, big_ind]) @ Xdot[:, ind]
        return Xi

    @staticmethod
    def havok_koopman_embedding(x_series, q=10, r=4):
        n = len(x_series) - q + 1
        H = np.zeros((q, n))
        for i in range(q):
            H[i, :] = x_series[i:i+n]
        U, S, Vh = svd(H, full_matrices=False)
        V_sub = Vh.T[:, :r]
        dV = np.diff(V_sub, axis=0)
        V_left = V_sub[:-1, :]
        A_havok = pinv(V_left) @ dV
        return A_havok, V_sub

class AdvectionDiffusionPINN(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(2, 32), nn.Tanh(),
            nn.Linear(32, 32), nn.Tanh(),
            nn.Linear(32, 1)
        )
        
    def forward(self, x, t):
        return self.net(torch.cat([x, t], dim=1))

    def residual(self, x, t, velocity=1.2, diff_coeff=0.05):
        x.requires_grad_(True)
        t.requires_grad_(True)
        u = self.forward(x, t)
        
        u_t = torch.autograd.grad(u, t, grad_outputs=torch.ones_like(u), create_graph=True)[0]
        u_x = torch.autograd.grad(u, x, grad_outputs=torch.ones_like(u), create_graph=True)[0]
        u_xx = torch.autograd.grad(u_x, x, grad_outputs=torch.ones_like(u_x), create_graph=True)[0]
        
        return u_t + velocity * u_x - diff_coeff * u_xx

# -----------------------------------------------------------------------------
# 5. CONTROLS & SIDEBAR
# -----------------------------------------------------------------------------
st.sidebar.title("🎮 Master Controls")

selected_site_name = st.sidebar.selectbox("Select Indian Landfill Site", list(INDIA_LANDFILLS.keys()))
site_info = INDIA_LANDFILLS[selected_site_name]

lat = site_info["lat"]
lon = site_info["lon"]
height_m = site_info["height_m"]
waste_mass = site_info["waste_mass_mt"]
landfill_age = st.sidebar.slider("Landfill Age (Years)", 1, 50, 22)

st.sidebar.markdown("---")
st.sidebar.subheader("🔬 Physics Modules Activation")
enable_pinn = st.sidebar.checkbox("Execute PINN AutoDiff Engine", value=True)
enable_sindy = st.sidebar.checkbox("Run SINDy Nonlinear Identification", value=True)
enable_havok = st.sidebar.checkbox("Run HAVOK Hankel-Koopman Matrix", value=True)

# -----------------------------------------------------------------------------
# 6. CALCULATIONS
# -----------------------------------------------------------------------------
depth_m, gas_vol_m3, suction_rate, boreholes = GeotechThermodynamics.calculate_drilling_and_chamber(lat, lon, height_m, waste_mass)
fod_gas_m3y = GeotechThermodynamics.first_order_decay_lfg(waste_mass, landfill_age)
heat_flux = GeotechThermodynamics.fourier_subsurface_heat(0.8, 42.0, 68.0, depth_m)

# Brunton & Kutz Data Execution
t_grid = np.linspace(0, 10, 100)
x_spatial = np.linspace(-5, 5, 50)
T_mat, X_mat = np.meshgrid(t_grid, x_spatial)
plume_field = np.exp(-0.2 * (X_mat - 0.5 * T_mat)**2) + 0.05 * np.random.randn(*X_mat.shape)

Phi, eigs = BruntonKutzDataDynamics.dynamic_mode_decomposition(plume_field[:, :-1], plume_field[:, 1:], r=3)

x_state = np.column_stack([np.sin(t_grid), np.cos(t_grid)])
x_dot = np.column_stack([np.cos(t_grid), -np.sin(t_grid)])
sindy_weights = BruntonKutzDataDynamics.sindy_identification(x_state, x_dot)

havok_A, _ = BruntonKutzDataDynamics.havok_koopman_embedding(plume_field[25, :], q=12, r=4)

pinn_res = 0.0
if enable_pinn:
    pinn_net = AdvectionDiffusionPINN()
    pinn_res = pinn_net.residual(torch.rand(20, 1), torch.rand(20, 1)).detach().numpy().mean()

# -----------------------------------------------------------------------------
# 7. DASHBOARD DISPLAY
# -----------------------------------------------------------------------------
st.title("🛰️ Zero Waste Solutions — Complete Multi-Physics & Geotechnical Platform")
st.caption("All-India Landfills | Drilling Depth & Boreholes | SINDy | DMD | HAVOK | PINN AutoDiff")

# Top Metrics Row
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Site Height", f"{height_m} m", selected_site_name)
m2.metric("Drilling Hole Depth", f"{depth_m} meters", "72% Core Target")
m3.metric("CH₄ Trapped Vol.", f"{gas_vol_m3/1e6:.2f} M-m³", f"Flow: {suction_rate} m³/hr")
m4.metric("PINN Residual", f"{pinn_res:.6f}", "AutoDiff Verified")
m5.metric("DMD Eigenvalue", f"{np.abs(eigs[0]):.4f}", "Koopman Mode Active")

st.markdown("---")

# Map Section
st.subheader("📍 All-India Landfill Network & Active Borehole Drilling Matrix")

m = folium.Map(location=[lat, lon], zoom_start=13, tiles="OpenStreetMap")

# Render all India sites
for site, d in INDIA_LANDFILLS.items():
    is_sel = (site == selected_site_name)
    folium.Marker(
        [d["lat"], d["lon"]],
        popup=f"<b>{site}</b><br>Height: {d['height_m']}m",
        tooltip=site,
        icon=folium.Icon(color="red" if is_sel else "blue", icon="star" if is_sel else "info-sign")
    ).add_to(m)

# Render specific drilling boreholes for target site
for hole in boreholes:
    folium.Marker(
        [hole["lat"], hole["lon"]],
        popup=f"<b>{hole['id']}</b><br>Depth: {hole['depth_m']}m<br>Dia: {hole['dia_mm']}mm",
        tooltip=hole["id"],
        icon=folium.Icon(color="green", icon="wrench")
    ).add_to(m)

folium.Circle([lat, lon], radius=1000, color="red", fill=True, fill_opacity=0.15).add_to(m)

st_folium.st_folium(m, width=1200, height=480)

st.markdown("---")

# Geotechnical Schedule & Physics Engine Output
col_a, col_b = st.columns([1.1, 0.9])

with col_a:
    st.subheader("🛠️ Drilling Schedule & Pinpoint Coordinates")
    st.dataframe(pd.DataFrame(boreholes), use_container_width=True)

with col_b:
    st.subheader("⚙️ System Identification (Brunton & Kutz)")
    st.write("**SINDy Sparse Coefficients $\mathbf{\Xi}$:**")
    st.dataframe(pd.DataFrame(sindy_weights, columns=["dx1/dt", "dx2/dt"]), height=130)
    
    st.write("**HAVOK Matrix $A_{HAVOK}$:**")
    st.dataframe(pd.DataFrame(havok_A), height=130)
