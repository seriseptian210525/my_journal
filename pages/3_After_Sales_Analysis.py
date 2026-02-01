import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import math

# Page config
st.set_page_config(page_title="Service Items Tracker", page_icon="🛠️", layout="wide")

st.title("🛠️ Historical Service Items Tracker")
st.caption("Single Source of Truth - Data dari Neon Database")

# =============================================================================
# IMPORTS & SERVICES
# =============================================================================
try:
    from src.services.part_usage_service import PartUsageService
    from src.services.neon_sync_service import NeonSyncService
    neon_service = NeonSyncService()
    NEON_AVAILABLE = True
except Exception as e:
    NEON_AVAILABLE = False
    st.warning(f"⚠️ Neon connection not available: {e}")

# =============================================================================
# HELPER: Reset page on filter change
# =============================================================================
def reset_page():
    st.session_state.current_page = 1

# =============================================================================
# DATA UPLOAD & SYNC SECTION
# =============================================================================
with st.expander("📤 Upload & Sync Data", expanded=False):
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### Upload Part Usage CSV")
        st.info("Upload CSV untuk append data part usage ke Google Sheet.")
        uploaded_file = st.file_uploader("Choose a CSV file", type=['csv'], key="csv_upload")
        
        if uploaded_file is not None:
            try:
                df_upload = pd.read_csv(uploaded_file)
                st.dataframe(df_upload.head(), use_container_width=True)
                st.caption(f"Previewing first 5 rows of {len(df_upload)} total rows.")
                
                if st.button("📤 Sync to Google Sheet", type="primary"):
                    with st.spinner("Syncing data to Google Sheets..."):
                        try:
                            service = PartUsageService()
                            service.sync_to_gsheet(df_upload)
                            st.success(f"✅ Successfully synced {len(df_upload)} rows to Google Sheet!")
                            st.session_state['csv_uploaded'] = True
                        except Exception as e:
                            st.error(f"❌ Sync failed: {str(e)}")
            except Exception as e:
                st.error(f"Error reading file: {e}")
    
    with col2:
        st.markdown("### Sync to Neon Database")
        st.info("Setelah upload CSV, sync ke Neon untuk update data.")
        
        if NEON_AVAILABLE:
            if st.button("🔄 Sync to Neon (Incremental)", type="secondary", use_container_width=True):
                with st.spinner("Syncing to Neon Database..."):
                    try:
                        result = neon_service.run_incremental_sync()
                        if result['status'] == 'success':
                            st.success(f"""
                            ✅ Sync completed!
                            - Service Items: {result['service_items_new']} new
                            - Part Usage: {result['part_usage_new']} new
                            - Total Inserted: {result['total_inserted']} rows
                            """)
                        elif result['status'] == 'no_new_data':
                            st.info("ℹ️ No new data to sync.")
                        else:
                            st.error(f"❌ Sync failed: {result.get('error', 'Unknown error')}")
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
        else:
            st.warning("Neon connection not available")

# =============================================================================
# FILTERS (Dynamic with Apply Button)
# =============================================================================
st.markdown("---")
st.subheader("🔍 Filter Data")

# Initialize session state for filters
if 'filter_plate' not in st.session_state:
    st.session_state.filter_plate = ""
if 'filter_item' not in st.session_state:
    st.session_state.filter_item = ""
if 'filter_customer' not in st.session_state:
    st.session_state.filter_customer = ""
if 'filter_warranty' not in st.session_state:
    st.session_state.filter_warranty = "All"
if 'current_page' not in st.session_state:
    st.session_state.current_page = 1

# Filter inputs
filter_col1, filter_col2, filter_col3, filter_col4, filter_col5 = st.columns([1.5, 1.5, 1.5, 1, 0.8])

with filter_col1:
    filter_plate = st.text_input("🚗 Plat Nomor", value=st.session_state.filter_plate, placeholder="B 1234 XX", key="input_plate")

with filter_col2:
    filter_item = st.text_input("📦 Item Name", value=st.session_state.filter_item, placeholder="Tire, Oil, etc", key="input_item")

with filter_col3:
    filter_customer = st.text_input("👤 Customer Type", value=st.session_state.filter_customer, placeholder="Grab, Gojek, etc", key="input_customer")

with filter_col4:
    warranty_options = ["All", "Garansi", "Non-Garansi"]
    warranty_index = warranty_options.index(st.session_state.filter_warranty) if st.session_state.filter_warranty in warranty_options else 0
    filter_warranty = st.selectbox("🛡️ Warranty", warranty_options, index=warranty_index, key="input_warranty")

with filter_col5:
    st.markdown("<br>", unsafe_allow_html=True)
    apply_filter = st.button("🔍 Apply", type="primary", use_container_width=True)

# Apply filter button logic
if apply_filter:
    st.session_state.filter_plate = filter_plate
    st.session_state.filter_item = filter_item
    st.session_state.filter_customer = filter_customer
    st.session_state.filter_warranty = filter_warranty
    st.session_state.current_page = 1  # Reset to page 1
    st.rerun()

# Clear filter button
col_clear, _ = st.columns([1, 5])
with col_clear:
    if st.button("🗑️ Clear Filters"):
        st.session_state.filter_plate = ""
        st.session_state.filter_item = ""
        st.session_state.filter_customer = ""
        st.session_state.filter_warranty = "All"
        st.session_state.current_page = 1
        st.rerun()

# Build filters dict from session state
filters = {}
if st.session_state.filter_plate:
    filters['vehicle_plate'] = st.session_state.filter_plate
if st.session_state.filter_item:
    filters['item_name'] = st.session_state.filter_item
if st.session_state.filter_customer:
    filters['customer_type'] = st.session_state.filter_customer
if st.session_state.filter_warranty and st.session_state.filter_warranty != "All":
    filters['warranty_status'] = st.session_state.filter_warranty

# Show active filters
if filters:
    active_filters = " | ".join([f"**{k}**: {v}" for k, v in filters.items()])
    st.info(f"🏷️ Active Filters: {active_filters}")

# =============================================================================
# PAGINATED DATA TABLE
# =============================================================================
st.markdown("---")
st.subheader("📋 Service History")

if NEON_AVAILABLE:
    # Pagination controls
    page_size = st.selectbox("Rows per page", [25, 50, 100], index=1, key="page_size_select")
    
    # Get data
    try:
        df_display, total_count = neon_service.get_data_for_display(
            filters=filters if filters else None,
            page=st.session_state.current_page,
            page_size=page_size
        )
        
        total_pages = max(1, math.ceil(total_count / page_size))
        
        # Ensure current_page is within bounds
        if st.session_state.current_page > total_pages:
            st.session_state.current_page = total_pages
        
        # Pagination UI
        col_prev, col_info, col_next = st.columns([1, 2, 1])
        
        with col_prev:
            if st.button("⬅️ Previous", disabled=st.session_state.current_page <= 1, key="btn_prev"):
                st.session_state.current_page -= 1
                st.rerun()
        
        with col_info:
            st.markdown(f"<center>Page **{st.session_state.current_page}** of **{total_pages}** ({total_count:,} records)</center>", unsafe_allow_html=True)
        
        with col_next:
            if st.button("Next ➡️", disabled=st.session_state.current_page >= total_pages, key="btn_next"):
                st.session_state.current_page += 1
                st.rerun()
        
        # Display table
        if not df_display.empty:
            st.dataframe(
                df_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "created_at": st.column_config.DatetimeColumn("Date", format="YYYY-MM-DD HH:mm"),
                    "source_system": st.column_config.TextColumn("Source"),
                    "order_number": st.column_config.TextColumn("Order #", width="medium"),
                    "vehicle_plate": st.column_config.TextColumn("Plat Nomor"),
                    "sku": st.column_config.TextColumn("SKU"),
                    "item_name": st.column_config.TextColumn("Item Name", width="large"),
                    "bike_type": st.column_config.TextColumn("Bike Type"),
                    "customer_type": st.column_config.TextColumn("Customer"),
                    "quantity": st.column_config.NumberColumn("Qty", format="%.0f"),
                    "final_price": st.column_config.NumberColumn("Price", format="Rp %.0f"),
                    "warranty_status": st.column_config.TextColumn("Warranty"),
                    "pergantian_ke": st.column_config.NumberColumn("Pergantian Ke", format="%d"),
                    "odometer": st.column_config.NumberColumn("Odometer", format="%,d km")
                }
            )
        else:
            st.info("No data found with current filters.")
            
    except Exception as e:
        st.error(f"Error loading data: {e}")
else:
    st.warning("Connect to Neon to view data")

# =============================================================================
# CHARTS SECTION
# =============================================================================
st.markdown("---")
st.subheader("📊 Analytics")

chart_tab1, chart_tab2 = st.tabs(["🔥 Cohort Heatmap", "💰 Cost per KM"])

# --- COHORT HEATMAP ---
with chart_tab1:
    st.markdown("### Pergantian Part per Asset")
    st.caption("Heatmap menunjukkan berapa kali setiap item diganti per kendaraan")
    
    if NEON_AVAILABLE:
        cohort_plate = st.text_input("Filter by Plat Nomor (optional)", key="cohort_plate", placeholder="B 1234 XX")
        
        try:
            cohort_df = neon_service.get_cohort_data(cohort_plate if cohort_plate else None)
            
            if not cohort_df.empty:
                # Limit to top 20 vehicles for readability
                top_vehicles = cohort_df['vehicle_plate'].value_counts().head(20).index
                cohort_filtered = cohort_df[cohort_df['vehicle_plate'].isin(top_vehicles)]
                
                # Pivot for heatmap
                heatmap_data = cohort_filtered.groupby(['vehicle_plate', 'item_name'])['pergantian_ke'].max().reset_index()
                heatmap_pivot = heatmap_data.pivot(index='vehicle_plate', columns='item_name', values='pergantian_ke').fillna(0)
                
                if not heatmap_pivot.empty:
                    # Limit columns for readability
                    if len(heatmap_pivot.columns) > 15:
                        top_items = heatmap_data.groupby('item_name')['pergantian_ke'].sum().nlargest(15).index
                        heatmap_pivot = heatmap_pivot[top_items]
                    
                    fig_heatmap = px.imshow(
                        heatmap_pivot,
                        labels=dict(x="Item", y="Vehicle", color="Pergantian Ke"),
                        aspect="auto",
                        color_continuous_scale="YlOrRd",
                        title="Pergantian Ke Heatmap (Max per Vehicle-Item)"
                    )
                    fig_heatmap.update_layout(height=500)
                    st.plotly_chart(fig_heatmap, use_container_width=True)
                else:
                    st.info("No data available for heatmap")
            else:
                st.info("No cohort data available")
                
        except Exception as e:
            st.error(f"Error loading cohort data: {e}")
    else:
        st.warning("Connect to Neon to view analytics")

# --- COST PER KM ---
with chart_tab2:
    st.markdown("### Cost per Kilometer Analysis")
    st.caption("Analisis biaya per kilometer untuk setiap kendaraan")
    
    if NEON_AVAILABLE:
        try:
            cost_df = neon_service.get_cost_per_km_data()
            
            if not cost_df.empty:
                col_chart, col_stats = st.columns([2, 1])
                
                with col_chart:
                    # Bar chart of cost per km by vehicle
                    fig_cost = px.bar(
                        cost_df.head(20),
                        x='vehicle_plate',
                        y='cost_per_km',
                        color='bike_type',
                        title='Top 20 Vehicles by Cost/KM',
                        labels={'cost_per_km': 'Cost per KM (Rp)', 'vehicle_plate': 'Vehicle'}
                    )
                    fig_cost.update_layout(xaxis_tickangle=-45, height=400)
                    st.plotly_chart(fig_cost, use_container_width=True)
                
                with col_stats:
                    st.markdown("#### Summary Stats")
                    st.metric("Avg Cost/KM", f"Rp {cost_df['cost_per_km'].mean():,.0f}")
                    st.metric("Median Cost/KM", f"Rp {cost_df['cost_per_km'].median():,.0f}")
                    st.metric("Max Cost/KM", f"Rp {cost_df['cost_per_km'].max():,.0f}")
                    st.metric("Vehicles Analyzed", f"{len(cost_df):,}")
                
                # Distribution chart
                fig_dist = px.histogram(
                    cost_df,
                    x='cost_per_km',
                    nbins=30,
                    title='Cost/KM Distribution',
                    labels={'cost_per_km': 'Cost per KM (Rp)'}
                )
                st.plotly_chart(fig_dist, use_container_width=True)
                
            else:
                st.info("No cost/km data available (requires valid odometer readings)")
                
        except Exception as e:
            st.error(f"Error loading cost data: {e}")
    else:
        st.warning("Connect to Neon to view analytics")

# =============================================================================
# FOOTER
# =============================================================================
st.markdown("---")
# Safe check for total_count
record_count = total_count if 'total_count' in dir() and NEON_AVAILABLE else 'N/A'
st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Data Source: Neon PostgreSQL | Total Records: {record_count:,}" if isinstance(record_count, int) else f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Data Source: Neon PostgreSQL | Total Records: {record_count}")

