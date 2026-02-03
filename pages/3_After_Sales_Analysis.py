import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import calendar
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
if 'filter_date_mode' not in st.session_state:
    st.session_state.filter_date_mode = "All Time"
if 'filter_start_date' not in st.session_state:
    st.session_state.filter_start_date = None
if 'filter_end_date' not in st.session_state:
    st.session_state.filter_end_date = None

if 'filter_plate' not in st.session_state:
    st.session_state.filter_plate = "All"
if 'filter_order' not in st.session_state:
    st.session_state.filter_order = ""
if 'filter_location' not in st.session_state:
    st.session_state.filter_location = "All"
if 'filter_item' not in st.session_state:
    st.session_state.filter_item = "All"
if 'filter_customer' not in st.session_state:
    st.session_state.filter_customer = "All"
if 'filter_warranty' not in st.session_state:
    st.session_state.filter_warranty = "All"
if 'filter_sku' not in st.session_state:
    st.session_state.filter_sku = "All"
if 'filter_loc_cat' not in st.session_state:
    st.session_state.filter_loc_cat = "All"
if 'current_page' not in st.session_state:
    st.session_state.current_page = 1
if 'prime_page' not in st.session_state:
    st.session_state.prime_page = 1

# Load Filter Options from DB
filter_options = {
    'vehicle_plate': [],
    'item_name': [],
    'customer_type': [],
    'warranty_coverage': [],
    'sku': []
}

if NEON_AVAILABLE:
    try:
        filter_options = neon_service.get_filter_options()
    except Exception as e:
        st.error(f"Error loading filter options: {e}")

# --- Date Filter Section ---
st.markdown("##### 📅 Date & Location")
col_date_mode, col_date_input, col_loc_cat = st.columns([1, 2, 1])

with col_date_mode:
    date_mode_options = ["All Time", "Specific Date", "Date Range", "Month & Year"]
    current_mode_idx = date_mode_options.index(st.session_state.filter_date_mode) if st.session_state.filter_date_mode in date_mode_options else 0
    date_mode = st.selectbox(
        "Mode",
        date_mode_options,
        index=current_mode_idx,
        key="input_date_mode"
    )

with col_loc_cat:
    loc_cats = ["All", "B2B Repair", "Internal Repair", "Official Partner"]
    current_loc = st.session_state.filter_loc_cat
    idx = loc_cats.index(current_loc) if current_loc in loc_cats else 0
    input_loc_cat = st.selectbox("🏭 Tipe Lokasi", loc_cats, index=idx, key="input_loc_cat")

start_date_input = None
end_date_input = None

with col_date_input:
    if date_mode == "Specific Date":
        date_val = st.date_input("Select Date", value=datetime.today(), key="input_date_specific")
        if date_val:
            start_date_input = datetime.combine(date_val, datetime.min.time())
            end_date_input = datetime.combine(date_val, datetime.max.time())
            
    elif date_mode == "Date Range":
        # Default to last 30 days
        default_start = datetime.today() - timedelta(days=30)
        default_end = datetime.today()
        date_range = st.date_input(
            "Select Range",
            value=(default_start, default_end),
            key="input_date_range"
        )
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date_input = datetime.combine(date_range[0], datetime.min.time())
            end_date_input = datetime.combine(date_range[1], datetime.max.time())
            
    elif date_mode == "Month & Year":
        c1, c2 = st.columns(2)
        with c1:
            month_names = list(calendar.month_name)[1:]
            current_month_idx = datetime.today().month - 1
            selected_month = st.selectbox("Month", month_names, index=current_month_idx, key="input_month")
        with c2:
            current_year = datetime.today().year
            selected_year = st.number_input("Year", min_value=2020, max_value=2030, value=current_year, step=1, key="input_year")
        
        if selected_month and selected_year:
            month_idx = list(calendar.month_name).index(selected_month)
            _, last_day = calendar.monthrange(selected_year, month_idx)
            start_date_input = datetime(selected_year, month_idx, 1)
            end_date_input = datetime(selected_year, month_idx, last_day, 23, 59, 59)

# Filter inputs - ROW 1: Identity & Location
st.markdown("##### 🏷️ Filters")
row1_col1, row1_col2, row1_col3, row1_col4 = st.columns([1.5, 1.5, 2, 1.5])

with row1_col1:
    plate_opts = ["All"] + filter_options.get('vehicle_plate', [])
    idx = plate_opts.index(st.session_state.filter_plate) if st.session_state.filter_plate in plate_opts else 0
    filter_plate = st.selectbox("🚗 Plat Nomor", plate_opts, index=idx, key="input_plate")

with row1_col2:
    filter_order = st.text_input("📋 Order #", value=st.session_state.filter_order, key="input_order", placeholder="Search order...")

with row1_col3:
    loc_opts = ["All"] + filter_options.get('service_location_name', [])
    idx = loc_opts.index(st.session_state.filter_location) if st.session_state.filter_location in loc_opts else 0
    filter_location = st.selectbox("📍 Lokasi Servis", loc_opts, index=idx, key="input_location")

with row1_col4:
    cust_opts = ["All"] + filter_options.get('customer_type', [])
    idx = cust_opts.index(st.session_state.filter_customer) if st.session_state.filter_customer in cust_opts else 0
    filter_customer = st.selectbox("👤 Customer", cust_opts, index=idx, key="input_customer")

# Filter inputs - ROW 2: Product & Actions
row2_col1, row2_col2, row2_col3, row2_col4, row2_col5 = st.columns([2, 1.5, 1.2, 0.6, 0.6])

with row2_col1:
    item_opts = ["All"] + filter_options.get('item_name', [])
    idx = item_opts.index(st.session_state.filter_item) if st.session_state.filter_item in item_opts else 0
    filter_item = st.selectbox("📦 Item Name", item_opts, index=idx, key="input_item")

with row2_col2:
    sku_opts = ["All"] + filter_options.get('sku', [])
    idx = sku_opts.index(st.session_state.filter_sku) if st.session_state.filter_sku in sku_opts else 0
    filter_sku = st.selectbox("🏷️ SKU", sku_opts, index=idx, key="input_sku")

with row2_col3:
    warranty_opts = ["All"] + filter_options.get('warranty_coverage', [])
    idx = warranty_opts.index(st.session_state.filter_warranty) if st.session_state.filter_warranty in warranty_opts else 0
    filter_warranty = st.selectbox("🛡️ Warranty", warranty_opts, index=idx, key="input_warranty")

with row2_col4:
    st.markdown("<br>", unsafe_allow_html=True)
    apply_filter = st.button("🔍", type="primary", use_container_width=True, help="Apply Filters")

with row2_col5:
    st.markdown("<br>", unsafe_allow_html=True)
    clear_filter = st.button("🗑️", use_container_width=True, help="Clear Filters")

# Apply filter button logic
if apply_filter:
    st.session_state.filter_plate = filter_plate
    st.session_state.filter_order = filter_order
    st.session_state.filter_location = filter_location
    st.session_state.filter_item = filter_item
    st.session_state.filter_customer = filter_customer
    st.session_state.filter_warranty = filter_warranty
    st.session_state.filter_sku = filter_sku
    st.session_state.filter_loc_cat = input_loc_cat
    
    # Save Date State
    st.session_state.filter_date_mode = date_mode
    st.session_state.filter_start_date = start_date_input
    st.session_state.filter_end_date = end_date_input

    st.session_state.current_page = 1  # Reset to page 1
    st.rerun()

# Clear filter button logic
if clear_filter:
    st.session_state.filter_plate = "All"
    st.session_state.filter_order = ""
    st.session_state.filter_location = "All"
    st.session_state.filter_item = "All"
    st.session_state.filter_customer = "All"
    st.session_state.filter_warranty = "All"
    st.session_state.filter_sku = "All"
    st.session_state.filter_loc_cat = "All"
    
    # Reset Date
    st.session_state.filter_date_mode = "All Time"
    st.session_state.filter_start_date = None
    st.session_state.filter_end_date = None
    
    st.session_state.current_page = 1
    st.rerun()

# Build filters dict from session state
filters = {}
if st.session_state.filter_plate != "All":
    filters['vehicle_plate'] = st.session_state.filter_plate
if st.session_state.filter_order:
    filters['order_number'] = st.session_state.filter_order
if st.session_state.filter_location != "All":
    filters['service_location_name'] = st.session_state.filter_location
if st.session_state.filter_item != "All":
    filters['item_name'] = st.session_state.filter_item
if st.session_state.filter_customer != "All":
    filters['customer_type'] = st.session_state.filter_customer
if st.session_state.filter_warranty != "All":
    filters['warranty_coverage'] = st.session_state.filter_warranty
if st.session_state.filter_sku != "All":
    filters['sku'] = st.session_state.filter_sku
if st.session_state.filter_loc_cat != "All":
    filters['location_category'] = st.session_state.filter_loc_cat

# Add Date Filters
if st.session_state.filter_date_mode != "All Time":
    if st.session_state.filter_start_date:
        filters['start_date'] = st.session_state.filter_start_date
    if st.session_state.filter_end_date:
        filters['end_date'] = st.session_state.filter_end_date

# Show active filters
if filters:
    active_filters = []
    if st.session_state.filter_date_mode != "All Time":
        d_str = f"{st.session_state.filter_date_mode}"
        if st.session_state.filter_start_date:
            d_str += f" ({st.session_state.filter_start_date.strftime('%Y-%m-%d')}"
            if st.session_state.filter_end_date:
                d_str += f" to {st.session_state.filter_end_date.strftime('%Y-%m-%d')})"
            else:
                 d_str += ")"
        active_filters.append(d_str)
        
    for k, v in filters.items():
        if k not in ['start_date', 'end_date']:
             active_filters.append(f"**{k}**: {v}")
             
    st.info(f"🏷️ Active Filters: {' | '.join(active_filters)}")

# =============================================================================
# PAGINATED DATA TABLE
# =============================================================================
st.markdown("---")

with st.expander("📋 Service History", expanded=True):
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
                # ENRICHMENT: Add Location Category flag (3-Tier)
                # B2B = Grab, Internal = Pondok Indah/Kembangan/Depok/Bekasi, else Official Partner
                if 'service_location_name' in df_display.columns:
                    loc_col = df_display['service_location_name'].astype(str)
                    
                    # Check conditions
                    is_b2b = loc_col.str.contains('GRAB', case=False, na=False)
                    is_internal = (
                        loc_col.str.contains('Pondok Indah', case=False, na=False) |
                        loc_col.str.contains('Kembangan', case=False, na=False) |
                        loc_col.str.contains('Depok', case=False, na=False) |
                        loc_col.str.contains('Bekasi', case=False, na=False)
                    )
                    
                    df_display['location_category'] = np.where(
                        is_b2b, 'B2B Repair',
                        np.where(is_internal, 'Internal Repair', 'Official Partner')
                    )
                else:
                    df_display['location_category'] = 'Unknown'

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
                        # NEW LOCATION COLUMNS
                        "service_location_name": st.column_config.TextColumn("Lokasi Servis"),
                        "location_category": st.column_config.TextColumn("Tipe Lokasi", help="Internal vs B2B (Grab)"),
                        
                        "bike_type": st.column_config.TextColumn("Bike Type"),
                        "customer_type": st.column_config.TextColumn("Customer"),
                        "quantity": st.column_config.NumberColumn("Qty", format="%.0f"),
                        
                        # NEW COLUMNS
                        "subtotal_price": st.column_config.NumberColumn("Subtotal", format="Rp %.0f"),
                        "old_price": st.column_config.NumberColumn("Old Price", format="Rp %.0f"), 
                        
                        "final_price": st.column_config.NumberColumn("Price", format="Rp %.0f"),
                        "warranty_status": st.column_config.TextColumn("Warranty Coverage"), 
                        "pergantian_ke_total": st.column_config.NumberColumn("#Total", format="%d", help="Total pergantian seumur hidup"),
                        "pergantian_ke_yearly": st.column_config.NumberColumn("#Yearly", format="%d", help="Pergantian dalam siklus tahun berjalan (reset tiap tahun)"),
                        "odometer": st.column_config.NumberColumn("Odometer (km)", format="%d")
                    }
                )
            else:
                st.info("No data found with current filters.")
                
        except Exception as e:
            st.error(f"Error loading data: {e}")
    else:
        st.warning("Connect to Neon to view data")

# =============================================================================
# PRIME INPUT TABLE (GEL + Internal Repair + NOT_COVERED)
# =============================================================================
st.markdown("---")

with st.expander("🎯 Prime Input Queue", expanded=False):
    st.caption("Data yang perlu diinput manual: **Internal Repair** + **GEL** + **NOT_COVERED**")
    
    if NEON_AVAILABLE:
        try:
            from src.services.prime_tracking_service import PrimeTrackingService
            from src.common.config import NEON_DB_CONNECTION_STRING
            # Use same connection string as NeonLoader
            prime_service = PrimeTrackingService(connection_string=NEON_DB_CONNECTION_STRING)
            
            # Pre-filter for Prime Input candidates
            prime_filters = {
                'customer_type': 'GEL',
                'warranty_coverage': 'NOT_COVERED',
                'location_category': 'Internal Repair',
                'exclude_skus': ['GEN-F9060-001-N-NE', 'GEN-F9110-001-N-NE', 'H3A-F9130-001-N-NE']
            }
            
            # Add date filters if set
            if st.session_state.filter_date_mode != "All Time":
                if st.session_state.filter_start_date:
                    prime_filters['start_date'] = st.session_state.filter_start_date
                if st.session_state.filter_end_date:
                    prime_filters['end_date'] = st.session_state.filter_end_date
            
            prime_df, prime_count = neon_service.get_data_for_display(
                filters=prime_filters,
                page=st.session_state.prime_page,
                page_size=25
            )
            
            # Stats
            prime_stats = prime_service.get_stats()
            stat_col1, stat_col2, stat_col3 = st.columns(3)
            with stat_col1:
                st.metric("Total Queue", prime_count)
            with stat_col2:
                st.metric("✅ Sudah Input", prime_stats['total_primed'])
            with stat_col3:
                st.metric("⏳ Belum Input", prime_stats['total_pending'])
            
            if not prime_df.empty:
                # Get primed status for current batch
                primed_map = prime_service.get_primed_status_bulk(
                    prime_df[['order_number', 'sku', 'vehicle_plate']].to_dict('records')
                )
                
                # Add checkbox column
                prime_df['is_primed'] = prime_df.apply(
                    lambda r: primed_map.get(f"{r['order_number']}|{r['sku']}|{r['vehicle_plate']}", False),
                    axis=1
                )
                
                # Display with checkboxes (using data_editor for interactivity)
                edited_df = st.data_editor(
                    prime_df[['is_primed', 'created_at', 'order_number', 'vehicle_plate', 'sku', 'item_name', 'quantity', 'service_location_name', 'subtotal_price', 'old_price', 'final_price']],
                    column_config={
                        "is_primed": st.column_config.CheckboxColumn("✅ Input?", default=False),
                        "created_at": st.column_config.DatetimeColumn("Date", format="YYYY-MM-DD HH:mm"),
                        "order_number": st.column_config.TextColumn("Order #"),
                        "vehicle_plate": st.column_config.TextColumn("Plat"),
                        "sku": st.column_config.TextColumn("SKU"),
                        "item_name": st.column_config.TextColumn("Item"),
                        "quantity": st.column_config.NumberColumn("Qty", format="%.0f"),
                        "service_location_name": st.column_config.TextColumn("Lokasi"),
                        "subtotal_price": st.column_config.NumberColumn("Subtotal", format="Rp %.0f"),
                        "old_price": st.column_config.NumberColumn("Old Price", format="Rp %.0f"),
                        "final_price": st.column_config.NumberColumn("Final Price", format="Rp %.0f"),
                    },
                    disabled=['created_at', 'order_number', 'vehicle_plate', 'sku', 'item_name', 'quantity', 'service_location_name', 'subtotal_price', 'old_price', 'final_price'],
                    hide_index=True,
                    use_container_width=True,
                    key="prime_editor"
                )
                
                # Save button for changes
                if st.button("💾 Save Prime Status", type="primary"):
                    changes_made = 0
                    for idx, row in edited_df.iterrows():
                        orig_row = prime_df.iloc[idx]
                        if row['is_primed'] != orig_row['is_primed']:
                            prime_service.set_primed(
                                order_number=orig_row['order_number'],
                                sku=orig_row['sku'],
                                vehicle_plate=orig_row['vehicle_plate'],
                                is_primed=row['is_primed']
                            )
                            changes_made += 1
                    
                    if changes_made > 0:
                        st.success(f"✅ Saved {changes_made} changes!")
                        st.rerun()
                    else:
                        st.info("No changes to save.")
                
                # Pagination for Prime table
                prime_total_pages = max(1, (prime_count + 24) // 25)
                pcol1, pcol2, pcol3 = st.columns([1, 2, 1])
                with pcol1:
                    if st.button("⬅️ Prev", disabled=st.session_state.prime_page <= 1, key="prime_prev"):
                        st.session_state.prime_page -= 1
                        st.rerun()
                with pcol2:
                    st.markdown(f"<center>Page **{st.session_state.prime_page}** of **{prime_total_pages}**</center>", unsafe_allow_html=True)
                with pcol3:
                    if st.button("Next ➡️", disabled=st.session_state.prime_page >= prime_total_pages, key="prime_next"):
                        st.session_state.prime_page += 1
                        st.rerun()
            else:
                st.success("🎉 Tidak ada data yang perlu diinput!")
                
        except Exception as e:
            st.error(f"Error loading Prime Input data: {e}")

# =============================================================================
# CHARTS SECTION
# =============================================================================
st.markdown("---")
st.subheader("📊 Analytics")

chart_tab1, chart_tab2, chart_tab3 = st.tabs(["🔥 Cohort Heatmap", "💰 Cost per KM", "🍩 Tire Analysis"])

# --- COHORT HEATMAP ---
with chart_tab1:
    st.markdown("### Pergantian Part per Asset")
    st.caption("Matriks Odometer saat pergantian part. Kuning = Reset Cycle / Package Service.")
    
    try:
        # Pass ALL filters including dates
        cohort_df = neon_service.get_cohort_data(filters=filters if filters else None)
        
        if not cohort_df.empty:
            # 1. AUTO-SELECT LOGIC
            # If no specific vehicle filter is selected, pick the most active one
            selected_plate = None
            is_auto_selected = False
            
            if filters.get('vehicle_plate'):
                selected_plate = filters['vehicle_plate']
            else:
                # Find vehicle with most rows
                most_active_plate = cohort_df['vehicle_plate'].value_counts().idxmax()
                selected_plate = most_active_plate
                is_auto_selected = True
                st.info(f"⚠️ Menampilkan data untuk kendaraan dengan aktivitas tertinggi: **{selected_plate}** (Gunakan filter 'Plat Nomor' untuk melihat kendaraan lain)")

            # Filter data for the selected plate
            df_plate = cohort_df[cohort_df['vehicle_plate'] == selected_plate].copy()
            
            if not df_plate.empty:
                # 2. SEQUENCE LOGIC FOR HEATMAP COLUMNS
                # Use TIME-BASED Rank for X-Axis (Visual Sequence) to handle gaps gracefully
                df_plate = df_plate.sort_values(['item_name', 'created_at'])
                df_plate['visual_rank'] = df_plate.groupby('item_name').cumcount() + 1
                
                # 3. PIVOT: Data Values = Odometer
                df_plate['odometer_fmt'] = df_plate['odometer'].apply(lambda x: f"{x:,.0f}" if pd.notnull(x) else "-")
                
                pivot = df_plate.pivot_table(
                    index='item_name', 
                    columns='visual_rank', 
                    values='odometer_fmt', 
                    aggfunc='first'
                ).fillna("")
                
                # 4. PIVOT: Context for Styling (Warranty & Reset Detection)
                # Pivot Warranty Coverage
                pivot_warranty = df_plate.pivot_table(
                    index='item_name', columns='visual_rank', values='warranty_coverage', aggfunc='first'
                )
                
                # Pivot Yearly Counter (To detect Reset: 1 after >1)
                pivot_yearly = df_plate.pivot_table(
                    index='item_name', columns='visual_rank', values='pergantian_ke_yearly', aggfunc='first'
                )

                # Pivot Total Counter (For Tooltip/Info - Optional, currently not displayed in cell but good for logic)
                pivot_total = df_plate.pivot_table(
                   index='item_name', columns='visual_rank', values='pergantian_ke_total', aggfunc='first'
                )
                
                # 5. DATA DISPLAY & STYLING
                def apply_heatmap_style(df_view):
                    df_style = pd.DataFrame('', index=df_view.index, columns=df_view.columns)
                    try:
                        for idx in df_style.index:
                            for col in df_style.columns:
                                style = ''
                                # Logic: Highlight if Package Service OR Reset Cycle Detected
                                
                                # Check Warranty Coverage
                                is_package = False
                                if idx in pivot_warranty.index and col in pivot_warranty.columns:
                                    coverage = pivot_warranty.loc[idx, col]
                                    if coverage == 'PACKAGE_SERVICE':
                                        is_package = True
                                
                                # Check Reset Cycle (Yearly Counter == 1 but it's not the first global occurrence)
                                is_reset = False
                                if idx in pivot_yearly.index and col in pivot_yearly.columns:
                                    yearly_counter = pivot_yearly.loc[idx, col]
                                    
                                    # If yearly counter is 1, AND it's not the very first visual rank (1), it's likely a reset
                                    # OR check against Total Counter: if Total > 1 and Yearly == 1
                                    if idx in pivot_total.index and col in pivot_total.columns:
                                        total_counter = pivot_total.loc[idx, col]
                                        if total_counter > 1 and yearly_counter == 1:
                                            is_reset = True
                                
                                if is_package or is_reset:
                                    style = 'background-color: #FFD700; color: black; font-weight: bold' # Gold
                                    
                                df_style.loc[idx, col] = style
                    except Exception as e:
                        pass
                    return df_style

                # Apply style
                st.dataframe(
                    pivot.style.apply(apply_heatmap_style, axis=None),
                    use_container_width=True,
                    column_config={
                        str(c): st.column_config.Column(f"#{c}", width="small") 
                        for c in pivot.columns
                    }
                )
                
                # Legend / Info
                st.caption("Keterangan: Kolom #1, #2, dst adalah urutan kejadian berdasarkan waktu. Warna Emas menandakan Paket Servis atau Reset Siklus Garansi (Tahun Baru).")
                
            else:
                st.info(f"No data found for vehicle {selected_plate} in this period.")
        else:
            st.info("No cohort data available for selected filters.")
            
    except Exception as e:
        st.error(f"Error loading cohort data: {e}")

# --- COST PER KM ---
with chart_tab2:
    st.markdown("### Cost per Kilometer Analysis")
    st.caption("Top vehicles by Cost Efficiency (Cost / KM). Requires Odometer data.")
    
    if NEON_AVAILABLE:
        try:
            # Pass ALL filters including dates
            cost_df = neon_service.get_cost_per_km_data(filters=filters if filters else None)
            
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

#   - - -   T I R E   C O S T   A N A L Y S I S   - - -  
 w i t h   c h a r t _ t a b 3 :  
         s t . m a r k d o w n ( " # # #   
# --- TIRE COST ANALYSIS ---
with chart_tab3:
    st.markdown("### 🍩 Tire Replacement Analysis")
    st.caption("Comparison of Tire Life (Duration & Odometer) for GEL vs Non-GEL Customers.")
    
    try:
        # Pass filters
        tire_df = neon_service.get_tire_cohort_data(filters=filters if filters else None)
        
        if not tire_df.empty:
            # Stats Summary
            st.markdown("#### 📈 Summary Stats")
            summary_cols = st.columns(4)
            with summary_cols[0]:
                st.metric("Total Replacements", len(tire_df))
            with summary_cols[1]:
                avg_month = tire_df['duration_months'].mean()
                st.metric("Avg Duration (Months)", f"{avg_month:.1f}")
            with summary_cols[2]:
                avg_km = tire_df['odometer_diff'].mean()
                st.metric("Avg Tire Life (KM)", f"{avg_km:,.0f}")
            with summary_cols[3]:
                avg_cost = tire_df['final_price'].mean()
                st.metric("Avg Cost", f"Rp {avg_cost:,.0f}")
            
            # --- COMPARATIVE CHARTS ---
            st.markdown("#### 📊 Comparative Analysis (GEL vs Non-GEL)")
            
            # Group by Pergantian Ke (1-5) & Category
            # Cap at 5 replacements for cleaner chart
            tire_df['Sequence'] = tire_df['pergantian_ke_total'].apply(lambda x: x if x <= 5 else '6+')
            
            cohort_grp = tire_df.groupby(['Sequence', 'customer_category']).agg({
                'duration_months': 'mean',
                'odometer_diff': 'mean',
                'final_price': 'mean',
                'vehicle_plate': 'count'
            }).reset_index()
            
            # Rename for display
            cohort_grp.columns = ['Sequence', 'Category', 'Avg Duration (Mo)', 'Avg Life (KM)', 'Avg Cost', 'Count']
            
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                st.markdown("##### 📅 Average Duration (Months)")
                st.bar_chart(
                    data=cohort_grp,
                    x='Sequence',
                    y='Avg Duration (Mo)',
                    color='Category',
                    use_container_width=True
                )
            
            with col_chart2:
                st.markdown("##### 🛣️ Average Tire Life (KM)")
                st.bar_chart(
                    data=cohort_grp,
                    x='Sequence',
                    y='Avg Life (KM)',
                    color='Category',
                    use_container_width=True
                )

            # --- COHORT TABLE ---
            st.markdown("#### 📋 Detailed Cohort Metrics")
            
            # Pivot for cleaner reading
            cohort_pivot = cohort_grp.pivot(index='Sequence', columns='Category', values=['Avg Life (KM)', 'Avg Duration (Mo)', 'Count'])
            # Flatten columns
            cohort_pivot.columns = [f"{col[1]} - {col[0]}" for col in cohort_pivot.columns]
            
            st.dataframe(
                cohort_pivot.style.format("{:,.1f}", subset=cohort_pivot.columns.difference([c for c in cohort_pivot.columns if 'Count' in c]))
                                  .format("{:,.0f}", subset=[c for c in cohort_pivot.columns if 'Count' in c]),
                use_container_width=True
            )
            
            # --- DETAILED DATA TABLE ---
            with st.expander("🔍 View Detailed List", expanded=False):
                st.dataframe(
                    tire_df[[
                        'vehicle_plate', 'customer_category', 'item_name', 
                        'pergantian_ke_total', 'replacement_date', 
                        'delivery_date', 'duration_months', 
                        'odometer', 'delivery_odometer', 'odometer_diff', 
                        'final_price'
                    ]].sort_values(['vehicle_plate', 'pergantian_ke_total']),
                    column_config={
                        'replacement_date': st.column_config.DateColumn("Replace Date"),
                        'delivery_date': st.column_config.DateColumn("Delivery Date"),
                        'odometer': st.column_config.NumberColumn("Current KM", format="%.0f"),
                        'delivery_odometer': st.column_config.NumberColumn("Start KM", format="%.0f"),
                        'odometer_diff': st.column_config.NumberColumn("Delta KM", format="%.0f"),
                        'final_price': st.column_config.NumberColumn("Cost", format="Rp %.0f"),
                    },
                    use_container_width=True,
                    hide_index=True
                )
                
        else:
            st.warning("No Tire data found with current filters.")
            
    except Exception as e:
        st.error(f"Error loading Tire Analysis: {e}")
