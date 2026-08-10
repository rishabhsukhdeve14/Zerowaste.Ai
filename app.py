import ee

# -----------------------------------------------------------------------------
# 1. GEE INITIALIZATION WITH YOUR GCP PROJECT ID
# -----------------------------------------------------------------------------
PROJECT_ID = 'stalwart-fx-490910-e3'

try:
  ee.Initialize(project=PROJECT_ID)
  print(
      f"🟢 Earth Engine Successfully Initialized with Project ID: {PROJECT_ID}"
  )
except Exception as e:
  print("⚠️ Authentication required. Run ee.Authenticate() first.")
  ee.Authenticate()
  ee.Initialize(project=PROJECT_ID)


# -----------------------------------------------------------------------------
# 2. MULTI-SATELLITE DATA FUSION PIPELINE
# -----------------------------------------------------------------------------
def fetch_fused_satellite_telemetry(lat, lon, start_date, end_date):
  poi = ee.Geometry.Point([lon, lat])
  region = poi.buffer(2000)  # 2km perimeter buffer around site

  # 🛰️ 1. Sentinel-5P (Atmospheric Methane - CH4)
  s5p_ch4 = (
      ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_CH4')
      .filterBounds(region)
      .filterDate(start_date, end_date)
      .select('CH4_column_number_density')
      .mean()
  )

  # 🛰️ 2. Sentinel-2 (High-Res 10m Optical & Vegetation Stress / Landfill Boundary)
  s2_optical = (
      ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
      .filterBounds(region)
      .filterDate(start_date, end_date)
      .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
      .median()
  )

  # 🛰️ 3. Sentinel-1 (SAR Ground Deformation / Subsidence)
  s1_sar = (
      ee.ImageCollection('COPERNICUS/S1_GRD')
      .filterBounds(region)
      .filterDate(start_date, end_date)
      .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
      .select('VV')
      .mean()
  )

  # 🛰️ 4. NASA ECOSTRESS (Land Surface Temperature Anomalies / Subsurface Heat)
  ecostress_lst = (
      ee.ImageCollection('NASA/ECOSTRESS/GEO1kmL2T_001')
      .filterBounds(region)
      .filterDate(start_date, end_date)
      .select('LST')
      .mean()
  )

  # 🛰️ 5. NASA EMIT (Hyperspectral Methane/Gas Absorption Signature)
  emit_spectral = (
      ee.ImageCollection('NASA/EMIT/L2B_CH4ENH')
      .filterBounds(region)
      .filterDate(start_date, end_date)
      .mean()
  )

  # -----------------------------------------------------------------------------
  # 3. REDUCE & EXTRACT FUSED TELEMETRY
  # -----------------------------------------------------------------------------
  ch4_val = s5p_ch4.reduceRegion(
      reducer=ee.Reducer.mean(), geometry=poi, scale=1113.2
  ).get('CH4_column_number_density')
  sar_val = s1_sar.reduceRegion(
      reducer=ee.Reducer.mean(), geometry=poi, scale=10
  ).get('VV')
  lst_val = ecostress_lst.reduceRegion(
      reducer=ee.Reducer.mean(), geometry=poi, scale=70
  ).get('LST')

  return {
      'S5P_CH4_ppb': ch4_val.getInfo(),
      'S1_SAR_Backscatter': sar_val.getInfo(),
      'ECOSTRESS_LST_K': lst_val.getInfo(),
      'Project_ID': PROJECT_ID,
      'Fusion_Status': 'ACTIVE',
  }


# Testing Fusion Pipeline on Ghazipur Landfill, Delhi
telemetry = fetch_fused_satellite_telemetry(
    lat=28.6231, lon=77.3288, start_date='2026-01-01', end_date='2026-08-10'
)

print("\n🚀 Fused Satellite Telemetry Output:")
print(telemetry)
