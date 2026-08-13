import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# ==========================================
# 1. PAGE CONFIGURATION & SETUP
# ==========================================
st.set_page_config(
    page_title="Zero Waste AI Dashboard",
    page_icon="♻️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("♻️ Zero Waste AI Analysis & Dashboard")
st.markdown("Real-time environmental metrics and analytical tracking.")

# ==========================================
# 2. DATA PROCESSING & UTILITY FUNCTIONS
# ==========================================
@st.cache_data
def load_sample_data():
    """Generates dummy data if primary source is unavailable."""
    dates = pd.date_range(start="2026-01-01", periods=30, freq="D")
    data = pd.DataFrame({
        "Day": [d.strftime("%Y-%m-%d") for d in dates],
        "Waste_Reduced_KG": np.random.randint(100, 500, size=30),
        "Efficiency_Score": np.random.uniform(70.0, 99.0, size=30)
    })
    return data

# Load Data
df = load_sample_data()

# Helper function to validate trace arrays safely
def is_valid_array(arr):
    if arr is None:
        return False
    if isinstance(arr, (list, tuple)):
        return len(arr) > 0
    if isinstance(arr, (pd.Series, np.ndarray)):
        return not arr.empty if isinstance(arr, pd.Series) else arr.size > 0
    return False

# Sidebar Controls
st.sidebar.header("Filter & Settings")
selected_range = st.sidebar.slider("Select Days Window", 5, 30, 15)

# Prep axis variables
day_axis = df["Day"].tolist()[:selected_range]
b = df["Waste_Reduced_KG"].tolist()[:selected_range]

# ==========================================
# 3. METRICS OVERVIEW
# ==========================================
col1, col2, col3 = st.columns(3)
col1.metric("Total Days Tracked", len(day_axis))
col2.metric("Total Waste Saved (kg)", f"{sum(b):,}")
col3.metric("Avg Savings/Day", f"{round(sum(b)/len(b), 2) if len(b) > 0 else 0} kg")

st.divider()

# ==========================================
# 4. PLOTLY CHART IMPLEMENTATION (SAFE BLOCK)
# ==========================================
st.subheader("📈 Waste Reduction Trend")

fig_t = go.Figure()

try:
    # Safe retrieval of scope variables
    _day_axis = locals().get('day_axis', globals().get('day_axis', None))
    _b = locals().get('b', globals().get('b', None))

    # Defensive Check before adding trace
    if is_valid_array(_day_axis) and is_valid_array(_b):
        if len(_day_axis) == len(_b):
            # FIXED TRACE (Line 375 Syntax Fix Applied)
            fig_t.add_trace(
                go.Scatter(
                    x=_day_axis,
                    y=_b,
                    mode='lines+markers',
                    name='Waste Saved (kg)',
                    line=dict(color='#2ECC71', width=3),
                    marker=dict(size=6, color='#27AE60'),
                    connectgaps=True
                )
            )
        else:
            st.warning(f"⚠️ Data Mismatch: X-axis ({len(_day_axis)}) vs Y-axis ({len(_b)}) length match nahi ho raha.")
    else:
        st.info("ℹ️ 'day_axis' ya 'b' array empty hai. Chart generation skip ho gaya.")

except Exception as e:
    st.error(f"❌ Chart Error: {str(e)}")

# Layout polish
fig_t.update_layout(
    title="Daily Waste Reduction Performance",
    xaxis_title="Timeline / Days",
    yaxis_title="Quantity (kg)",
    template="plotly_white",
    hovermode="x unified",
    margin=dict(l=40, r=40, t=50, b=40)
)

# Render Chart
st.plotly_chart(fig_t, use_container_width=True)

# ==========================================
# 5. DATA TABLE SECTION
# ==========================================
with st.expander("📄 View Raw Data"):
    st.dataframe(df.head(selected_range), use_container_width=True)
