import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from src.services.part_usage_service import PartUsageService

st.set_page_config(page_title="After Sales Analysis", page_icon="🛠️", layout="wide")

st.title("🛠️ After Sales Analysis")

# =============================================================================
# DATA UPLOAD SECTION
# =============================================================================
with st.expander("📤 Upload New Data (CSV)", expanded=False):
    st.info("Upload CSV files to append new part usage data. Duplicates based on `order_number` will be skipped.")
    uploaded_file = st.file_uploader("Choose a CSV file", type=['csv'])
    
    if uploaded_file is not None:
        try:
            df_upload = pd.read_csv(uploaded_file)
            st.dataframe(df_upload.head())
            st.caption(f"Previewing first 5 rows of {len(df_upload)} total rows.")
            
            if st.button("Sync to Google Sheet", type="primary"):
                with st.spinner("Syncing data to Google Sheets..."):
                    try:
                        service = PartUsageService()
                        service.sync_to_gsheet(df_upload)
                        st.success(f"✅ Successfully synced {len(df_upload)} rows!")
                    except Exception as e:
                        st.error(f"❌ Sync failed: {str(e)}")
        except Exception as e:
            st.error(f"Error reading file: {e}")

st.markdown("""
Dashboard ini menampilkan metrik **Asset Downtime** dan **Service Throughput** untuk membantu tim operasional memantau performa bengkel dan armada.
""")

# =============================================================================
# DUMMY DATA GENERATION
# =============================================================================
@st.cache_data
def generate_dummy_data():
    np.random.seed(42)
    
    # Generate 6 months of daily data
    date_range = pd.date_range(start='2025-07-01', end='2026-01-26', freq='D')
    n_days = len(date_range)
    
    # Asset Downtime Data (per day, per location)
    locations = ['Kembangan', 'Depok', 'Bekasi']
    downtime_records = []
    for date in date_range:
        for loc in locations:
            # Simulate daily downtime hours (0-24 hours per asset average)
            avg_downtime = np.random.exponential(scale=4) + np.random.uniform(0, 2)
            avg_downtime = min(avg_downtime, 24)  # Cap at 24 hours
            
            # Simulate number of assets in service
            assets_in_service = np.random.poisson(lam=8 if loc == 'Kembangan' else 5)
            
            downtime_records.append({
                'date': date,
                'location': loc,
                'avg_downtime_hours': round(avg_downtime, 2),
                'assets_in_service': assets_in_service,
                'total_downtime_hours': round(avg_downtime * assets_in_service, 2)
            })
    
    df_downtime = pd.DataFrame(downtime_records)
    
    # Service Throughput Data (work orders completed per day)
    throughput_records = []
    for date in date_range:
        for loc in locations:
            # Base throughput with some variance
            base = 12 if loc == 'Kembangan' else (8 if loc == 'Depok' else 6)
            wo_completed = max(0, int(np.random.normal(base, 3)))
            wo_received = wo_completed + np.random.randint(0, 5)
            avg_tat = np.random.uniform(1.5, 6)  # Turn Around Time in hours
            
            throughput_records.append({
                'date': date,
                'location': loc,
                'wo_received': wo_received,
                'wo_completed': wo_completed,
                'avg_tat_hours': round(avg_tat, 2)
            })
    
    df_throughput = pd.DataFrame(throughput_records)
    
    return df_downtime, df_throughput

df_downtime, df_throughput = generate_dummy_data()

# =============================================================================
# SIDEBAR FILTERS
# =============================================================================
st.sidebar.header("🔧 Filters")

# Date Range
min_date = df_downtime['date'].min().date()
max_date = df_downtime['date'].max().date()
date_range = st.sidebar.date_input(
    "Date Range",
    value=(max_date - timedelta(days=30), max_date),
    min_value=min_date,
    max_value=max_date
)

# Location Filter
locations = df_downtime['location'].unique().tolist()
selected_locations = st.sidebar.multiselect("Locations", locations, default=locations)

# Apply Filters
mask_downtime = (
    (df_downtime['date'].dt.date >= date_range[0]) &
    (df_downtime['date'].dt.date <= date_range[1]) &
    (df_downtime['location'].isin(selected_locations))
)
mask_throughput = (
    (df_throughput['date'].dt.date >= date_range[0]) &
    (df_throughput['date'].dt.date <= date_range[1]) &
    (df_throughput['location'].isin(selected_locations))
)

filtered_downtime = df_downtime[mask_downtime]
filtered_throughput = df_throughput[mask_throughput]

# =============================================================================
# KPI METRICS
# =============================================================================
st.markdown("---")
st.subheader("📊 Key Performance Indicators")

col1, col2, col3, col4 = st.columns(4)

with col1:
    avg_downtime = filtered_downtime['avg_downtime_hours'].mean()
    st.metric(
        label="Avg Downtime/Asset",
        value=f"{avg_downtime:.1f} hrs",
        delta=f"{np.random.uniform(-1, 1):.1f} hrs vs prev period",
        delta_color="inverse"
    )

with col2:
    total_wo = filtered_throughput['wo_completed'].sum()
    st.metric(
        label="Total WO Completed",
        value=f"{total_wo:,}",
        delta=f"+{np.random.randint(10, 50)} vs prev period"
    )

with col3:
    avg_tat = filtered_throughput['avg_tat_hours'].mean()
    st.metric(
        label="Avg TAT",
        value=f"{avg_tat:.1f} hrs",
        delta=f"{np.random.uniform(-0.5, 0.5):.1f} hrs",
        delta_color="inverse"
    )

with col4:
    completion_rate = (filtered_throughput['wo_completed'].sum() / 
                      filtered_throughput['wo_received'].sum() * 100)
    st.metric(
        label="Completion Rate",
        value=f"{completion_rate:.1f}%",
        delta=f"+{np.random.uniform(0, 3):.1f}%"
    )

# =============================================================================
# VISUALIZATIONS
# =============================================================================
st.markdown("---")

# Row 1: Downtime Charts
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("⏱️ Asset Downtime Trend")
    
    # Aggregate by date
    downtime_trend = filtered_downtime.groupby('date').agg({
        'avg_downtime_hours': 'mean',
        'total_downtime_hours': 'sum'
    }).reset_index()
    
    fig_downtime = px.area(
        downtime_trend,
        x='date',
        y='avg_downtime_hours',
        title='Average Downtime per Asset (Daily)',
        labels={'avg_downtime_hours': 'Hours', 'date': 'Date'},
        color_discrete_sequence=['#FF6B6B']
    )
    fig_downtime.update_layout(height=350)
    st.plotly_chart(fig_downtime, use_container_width=True)

with col_right:
    st.subheader("📍 Downtime by Location")
    
    downtime_by_loc = filtered_downtime.groupby('location').agg({
        'total_downtime_hours': 'sum',
        'assets_in_service': 'sum'
    }).reset_index()
    
    fig_loc = px.bar(
        downtime_by_loc,
        x='location',
        y='total_downtime_hours',
        title='Total Downtime Hours by Location',
        color='location',
        color_discrete_sequence=px.colors.qualitative.Set2
    )
    fig_loc.update_layout(height=350, showlegend=False)
    st.plotly_chart(fig_loc, use_container_width=True)

# Row 2: Throughput Charts
st.markdown("---")
col_left2, col_right2 = st.columns(2)

with col_left2:
    st.subheader("📈 Service Throughput Trend")
    
    throughput_trend = filtered_throughput.groupby('date').agg({
        'wo_received': 'sum',
        'wo_completed': 'sum'
    }).reset_index()
    
    fig_throughput = go.Figure()
    fig_throughput.add_trace(go.Scatter(
        x=throughput_trend['date'],
        y=throughput_trend['wo_received'],
        name='WO Received',
        line=dict(color='#4ECDC4', width=2)
    ))
    fig_throughput.add_trace(go.Scatter(
        x=throughput_trend['date'],
        y=throughput_trend['wo_completed'],
        name='WO Completed',
        line=dict(color='#45B7D1', width=2),
        fill='tonexty',
        fillcolor='rgba(69, 183, 209, 0.2)'
    ))
    fig_throughput.update_layout(
        title='Work Orders: Received vs Completed',
        height=350,
        legend=dict(orientation='h', yanchor='bottom', y=1.02)
    )
    st.plotly_chart(fig_throughput, use_container_width=True)

with col_right2:
    st.subheader("⏳ Turn Around Time Distribution")
    
    fig_tat = px.histogram(
        filtered_throughput,
        x='avg_tat_hours',
        nbins=20,
        title='TAT Distribution (Hours)',
        labels={'avg_tat_hours': 'TAT (Hours)', 'count': 'Frequency'},
        color_discrete_sequence=['#96CEB4']
    )
    fig_tat.update_layout(height=350)
    st.plotly_chart(fig_tat, use_container_width=True)

# =============================================================================
# DATA TABLE
# =============================================================================
st.markdown("---")
st.subheader("📋 Raw Data Preview")

tab1, tab2 = st.tabs(["📉 Downtime Data", "📊 Throughput Data"])

with tab1:
    st.dataframe(
        filtered_downtime.sort_values('date', ascending=False).head(100),
        use_container_width=True
    )

with tab2:
    st.dataframe(
        filtered_throughput.sort_values('date', ascending=False).head(100),
        use_container_width=True
    )

# Footer
st.markdown("---")
st.caption("⚠️ Data ini adalah **DUMMY DATA** untuk development. Integrasi dengan data real akan dilakukan kemudian.")
