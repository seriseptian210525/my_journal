import pandas as pd
import numpy as np
import json
import re

def clean_numeric_vectorized(series):
    """
    Vectorized cleanup for numeric columns.
    """
    # Force to string, replace comma, coerce to float
    return pd.to_numeric(series.astype(str).str.replace(',', '', regex=False).str.replace(r'[^\d.-]', '', regex=True), errors='coerce').fillna(0)

def standardize_service_type_vectorized(series):
    return series.astype(str).str.upper().str.strip().replace('NAN', '').replace('NONE', '')


def normalize_odometer(df, max_odometer=200000, daily_km_estimate=100, max_delta_per_month=50000):
    """
    Normalize odometer values for data quality.
    Benchmarked from work_orders/transformers.py process_odometer.
    
    Logic:
    1. Clean non-numeric characters
    2. Forward-fill zero/missing values with estimate (last_value + days * daily_km)
    3. Cap outliers at max_odometer
    4. Enforce monotonic increase per plate (cap decreasing values to previous)
    5. Cap large jumps (> max_delta_per_month within 30 days)
    
    Args:
        df: DataFrame with 'vehicle_plate', 'created_at', 'odometer' columns
        max_odometer: Cap values above this (default 200,000 km)
        daily_km_estimate: Estimated km/day for zero-fill (default 100)
        max_delta_per_month: Max allowed delta in 30 days (default 50,000 km)
    """
    if df.empty or 'odometer' not in df.columns:
        return df
    
    print("🔧 Normalizing Odometer...")
    
    # Step 1: Clean - extract numeric only
    df['odometer'] = df['odometer'].astype(str).str.replace(r'[^\d]', '', regex=True).replace('', '0')
    df['odometer'] = pd.to_numeric(df['odometer'], errors='coerce').fillna(0).astype('int64')
    
    # Step 2: Sort by plate and time for proper sequence
    df = df.sort_values(['vehicle_plate', 'created_at']).reset_index(drop=True)
    
    # Step 3: Cap extreme outliers first (e.g., 51 million km -> max_odometer)
    outliers_capped = (df['odometer'] > max_odometer).sum()
    df.loc[df['odometer'] > max_odometer, 'odometer'] = max_odometer
    if outliers_capped > 0:
        print(f"   ⚠️ Capped {outliers_capped:,} outliers (> {max_odometer:,} km)")
    
    # Step 4: Forward-fill zeros with estimate (last_value + days * daily_km)
    temp_odo = df['odometer'].replace(0, np.nan)
    last_val = df.groupby('vehicle_plate')['odometer'].transform(
        lambda x: x.replace(0, np.nan).ffill()
    )
    last_date = df.groupby('vehicle_plate')['created_at'].transform(
        lambda x: x.where(df.loc[x.index, 'odometer'] > 0).ffill()
    )
    
    diff_days = (pd.to_datetime(df['created_at']) - pd.to_datetime(last_date)).dt.days.fillna(0)
    
    # Only fill where odometer is 0 and we have a valid last value
    mask_fill = (df['odometer'] == 0) & (last_val > 0)
    estimated_values = (last_val + (diff_days * daily_km_estimate)).clip(upper=max_odometer)
    
    zeros_filled = mask_fill.sum()
    df.loc[mask_fill, 'odometer'] = estimated_values[mask_fill].astype('int64')
    if zeros_filled > 0:
        print(f"   ✅ Estimated {zeros_filled:,} zero odometer values")
    
    # Step 5: Enforce monotonic increase per plate
    # If current < previous, cap to previous value
    df['prev_odometer'] = df.groupby('vehicle_plate')['odometer'].shift(1)
    monotonic_violations = ((df['odometer'] < df['prev_odometer']) & (df['prev_odometer'].notna())).sum()
    
    if monotonic_violations > 0:
        mask_decrease = (df['odometer'] < df['prev_odometer']) & (df['prev_odometer'].notna())
        df.loc[mask_decrease, 'odometer'] = df.loc[mask_decrease, 'prev_odometer'].astype('int64')
        print(f"   🔄 Fixed {monotonic_violations:,} monotonic violations (odometer decreased)")
    
    # Cleanup temp column
    df = df.drop(columns=['prev_odometer'], errors='ignore')
    
    print(f"   ✅ Odometer normalized. Final range: {df['odometer'].min():,} - {df['odometer'].max():,}")
    
    return df


def explode_rows(df):
    """
    Explode rows where quantity > 1 into multiple rows with quantity = 1.
    """
    if df.empty:
        return df
    
    # Ensure quantity is int for repeat
    df['repeat_count'] = df['quantity'].fillna(0).astype(int)
    # Clip at 1 to avoid losing rows (qty 0 or 1 both count as 1 row effectively for existence, but logic says qty=0 -> 0 rows? No, usually distinct items.)
    # Let's assume Qty >= 1 means at least 1 item.
    df['repeat_count'] = df['repeat_count'].apply(lambda x: max(1, x)) 
    
    # Repeat rows
    exploded_df = df.loc[df.index.repeat(df['repeat_count'])].copy()
    
    # Reset quantity to 1 for all rows
    exploded_df['quantity'] = 1
    
    # Recalculate Subtotal? 
    exploded_df['subtotal_price'] = exploded_df['final_price'] * 1
    
    return exploded_df.drop(columns=['repeat_count'])

def calculate_pergantian_ke(df):
    """
    Calculate 'Pergantian Ke' (Running Count) per Vehicle + SKU + Year Cycle.
    Now includes yearly reset based on year_cycle column.
    """
    if df.empty:
        return df
    
    # Sort by vehicle, sku, then created_at for proper sequence
    df = df.sort_values(['vehicle_plate', 'sku', 'created_at']).reset_index(drop=True)
    
    # Check if year_cycle exists (enhanced mode)
    if 'year_cycle' in df.columns:
        df['pergantian_ke'] = df.groupby(['vehicle_plate', 'sku', 'year_cycle']).cumcount() + 1
    else:
        # Fallback: simple count without yearly reset
        df['pergantian_ke'] = df.groupby(['vehicle_plate', 'sku']).cumcount() + 1
    
    return df


def calculate_warranty_coverage(df, asset_df=None, mapping_df=None, skip_sequence_calc=False):
    """
    Calculate customer_category, bulan_ke, year_cycle, pergantian_ke (with reset), and warranty_coverage.
    
    Args:
        skip_sequence_calc (bool): If True, skips pergantian_ke calculation (useful for incremental sync with custom offset).
    """
    if df.empty:
        return df
    
    out = df.copy()
    
    # Ensure created_at is datetime
    out['created_at'] = pd.to_datetime(out['created_at'], errors='coerce')
    
    # --- Step 1: Join delivery_date from Asset List ---
    if asset_df is not None and not asset_df.empty:
        # Robust Join: Remove spaces for matching
        out['join_plate'] = out['vehicle_plate'].astype(str).str.strip().str.upper().str.replace(' ', '')
        asset_clean = asset_df.copy()
        
        # Try different column names for plate
        plate_col = None
        for col in ['Plat Nomor', 'Plate Number', 'vehicle_license_plate']:
            if col in asset_clean.columns:
                plate_col = col
                break
        
        # Try different column names for delivery date
        delivery_col = None
        for col in ['Delivery - Outbone', 'Delivery Date', 'delivery_date']:
            if col in asset_clean.columns:
                delivery_col = col
                break
        
        if plate_col and delivery_col:
            asset_clean['join_plate'] = asset_clean[plate_col].astype(str).str.strip().str.upper().str.replace(' ', '')
            asset_clean['_delivery_date'] = pd.to_datetime(asset_clean[delivery_col], errors='coerce')
            asset_clean = asset_clean.drop_duplicates(subset=['join_plate'])
            
            out = pd.merge(out, asset_clean[['join_plate', '_delivery_date']], on='join_plate', how='left')
            out['delivery_date'] = out['_delivery_date']
            out = out.drop(columns=['_delivery_date', 'join_plate'], errors='ignore')
        else:
            out['delivery_date'] = pd.NaT
    else:
        out['delivery_date'] = pd.NaT
    
    # --- Step 2: Customer Category Mapping ---
    # GEL → PARTNER_USER, else → ELECTRUM_USER
    out['customer_category'] = np.where(
        out['customer_type'].astype(str).str.upper().str.strip() == 'GEL',
        'PARTNER_USER',
        'ELECTRUM_USER'
    )
    
    # --- Step 3: Calculate Bulan Ke ---
    # (created_at - delivery_date) in days / 30.44
    out['bulan_ke'] = ((out['created_at'] - out['delivery_date']).dt.days / 30.44).fillna(0).astype(int)
    out['bulan_ke'] = out['bulan_ke'].apply(lambda x: max(0, x))  # No negative months
    
    # --- Step 4: Calculate Year Cycle ---
    out['year_cycle'] = (out['bulan_ke'] // 12).astype(int)
    
    # --- Step 5: Join Warranty Config from Mappings ---
    out['warranty_type'] = ''
    out['covered_for'] = ''
    out['limit_per_year'] = 0
    out['periode_garansi'] = 0  # NEW: Warranty period in months
    
    if mapping_df is not None and not mapping_df.empty:
        mapping_clean = mapping_df.copy()
        
        # SKU column in mappings
        sku_col = 'New SKU' if 'New SKU' in mapping_clean.columns else 'sku'
        if sku_col in mapping_clean.columns:
            out['join_sku'] = out['sku'].astype(str).str.strip()
            mapping_clean['join_sku'] = mapping_clean[sku_col].astype(str).str.strip()
            
            # Get warranty columns
            warranty_cols = ['join_sku']
            if 'Warranty Type' in mapping_clean.columns:
                mapping_clean['_warranty_type'] = mapping_clean['Warranty Type'].fillna('').astype(str)
                warranty_cols.append('_warranty_type')
            if 'Covered For' in mapping_clean.columns:
                mapping_clean['_covered_for'] = mapping_clean['Covered For'].fillna('').astype(str)
                warranty_cols.append('_covered_for')
            if 'Limit Per Year' in mapping_clean.columns:
                mapping_clean['_limit_per_year'] = pd.to_numeric(mapping_clean['Limit Per Year'], errors='coerce').fillna(0).astype(int)
                warranty_cols.append('_limit_per_year')
            # NEW: Periode Garansi
            if 'Periode Garansi' in mapping_clean.columns:
                mapping_clean['_periode_garansi'] = pd.to_numeric(mapping_clean['Periode Garansi'], errors='coerce').fillna(0).astype(int)
                warranty_cols.append('_periode_garansi')
            
            # Deduplicate
            mapping_clean = mapping_clean.drop_duplicates(subset=['join_sku'])
            
            # Merge
            out = pd.merge(out, mapping_clean[warranty_cols], on='join_sku', how='left')
            
            # Apply
            if '_warranty_type' in out.columns:
                out['warranty_type'] = out['_warranty_type'].fillna('')
            if '_covered_for' in out.columns:
                out['covered_for'] = out['_covered_for'].fillna('')
            if '_limit_per_year' in out.columns:
                out['limit_per_year'] = out['_limit_per_year'].fillna(0).astype(int)
            if '_periode_garansi' in out.columns:
                out['periode_garansi'] = out['_periode_garansi'].fillna(0).astype(int)
            
            # Cleanup
            out = out.drop(columns=['join_sku', '_warranty_type', '_covered_for', '_limit_per_year', '_periode_garansi'], errors='ignore')
    
    # --- Step 6: Calculate Pergantian Ke (Conditionally Skipped) ---
    if not skip_sequence_calc:
        out = out.sort_values(['vehicle_plate', 'sku', 'created_at']).reset_index(drop=True)
        # Total: cumulative per (vehicle_plate, sku) - never resets
        out['pergantian_ke_total'] = out.groupby(['vehicle_plate', 'sku']).cumcount() + 1
        # Yearly: cumulative per (vehicle_plate, sku, year_cycle) - resets each year
        out['pergantian_ke_yearly'] = out.groupby(['vehicle_plate', 'sku', 'year_cycle']).cumcount() + 1
    
    # --- Step 7: Calculate Warranty Coverage ---
    def check_warranty_coverage(row):
        """
        Determine warranty coverage with priority.
        """
        covered_for = str(row.get('covered_for', '') or '').upper()
        cust_cat = str(row.get('customer_category', '') or '').upper()
        limit = int(row.get('limit_per_year', 0) or 0)
        pergantian = int(row.get('pergantian_ke_yearly', 1) or 1)
        warranty_types = str(row.get('warranty_type', '') or '').upper()
        bulan_ke = int(row.get('bulan_ke', 0) or 0)
        periode_garansi = int(row.get('periode_garansi', 0) or 0)
        
        # Check if customer category is covered
        is_customer_covered = cust_cat in covered_for if covered_for else False
        
        # Check if within limit (0 = unlimited)
        within_limit = (limit == 0) or (pergantian <= limit)
        
        # Check if within warranty period
        within_warranty_period = (periode_garansi > 0) and (bulan_ke < periode_garansi)
        
        # Parse multiple warranty types
        types_list = [t.strip() for t in warranty_types.split(',') if t.strip()]
        
        # Priority-based check
        # Priority-based check
        if 'PACKAGE_SERVICE' in types_list:
            if is_customer_covered and within_limit:
                return 'PACKAGE_SERVICE'
        
        # 2. WARRANTY: check for "WARRANT" (matches WARRANT and WARRANTY)
        # customer covered + bulan_ke < periode_garansi
        # If covered_for is empty, assume covered for ALL (if warranty type is present)
        # Relaxed check: match substring 'WARRANT'
        if any('WARRANT' in t for t in types_list):
            customer_ok = is_customer_covered or (not covered_for)
            if customer_ok and within_warranty_period:
                return 'WARRANTY'
        
        # 3. INSURANCE: Always covered if customer type matches
        if 'INSURANCE' in types_list:
            customer_ok = is_customer_covered or (not covered_for)
            if customer_ok:
                return 'INSURANCE'
        
        return 'NOT_COVERED'
    
    out['warranty_coverage'] = out.apply(check_warranty_coverage, axis=1)
    
    if not skip_sequence_calc:
        print(f"   ✅ Warranty coverage calculated. Distribution:")
        print(out['warranty_coverage'].value_counts().to_string())
    
    return out

def standardize_service_items(df, asset_df=pd.DataFrame(), mapping_df=pd.DataFrame()):
    """
    Transform Service Items (Google Sheet) to Unified Schema.
    """
    if df.empty:
        return pd.DataFrame()
    
    # Copy to avoid SettingWithCopy
    out = df.copy()
    
    # Clean Numerics (Vectorized)
    out['quantity'] = clean_numeric_vectorized(out['Qty'])
    out['unit_price'] = clean_numeric_vectorized(out['Base Price'])
    out['final_price'] = clean_numeric_vectorized(out['Final Price'])
    out['subtotal_price'] = clean_numeric_vectorized(out['Subtotal Price'])
    out['odometer'] = clean_numeric_vectorized(out['odometer']).astype(int)
    
    out['order_number'] = 'BF-' + out['Order Number'].astype(str).str.slice(0, 97)  # BF- prefix for service_items
    out['vehicle_plate'] = out['Vehicle License Plate'].astype(str).str.strip().str.upper().str.slice(0, 50)
    out['sku'] = out['Sku'].astype(str).str.strip().str.upper().str.slice(0, 100)
    out['item_name'] = out['Item Name'].astype(str).str.slice(0, 255)
    out['erp_product_id'] = out['Erp Product ID'].astype(str).str.slice(0, 100)
    
    out['item_type'] = 'SPAREPART'
    out['service_type'] = standardize_service_type_vectorized(out['service_type']).str.slice(0, 50)
    out['service_location_name'] = out['service_location_name'].astype(str).str.slice(0, 100)
    out['completed_by'] = out['completed_by'].astype(str).str.slice(0, 100)
    out['customer_type'] = out['Customer Type'].astype(str).str.slice(0, 100)
    
    out['warranty_status'] = out['Warranty'].astype(str).str.slice(0, 50)
    out['status'] = out['Status'].astype(str).str.slice(0, 50)
    
    # BIKE TYPE - Get from source first, enrich later if empty
    if 'bike_type' in out.columns:
        out['bike_type'] = out['bike_type'].astype(str).str.slice(0, 50)
    else:
        out['bike_type'] = ''
    
    # OLD PRICE ENRICHMENT (Vectorized)
    out['old_price'] = clean_numeric_vectorized(out['Old Price'])
    
    if not mapping_df.empty:
        # Prepare Join Keys
        # Service Items 'Sku' vs Mapping 'New SKU'
        out['join_sku'] = out['sku'].str.strip()
        mapping_clean = mapping_df.copy()
        mapping_clean['join_sku'] = mapping_clean['New SKU'].astype(str).str.strip()
        mapping_clean['landed_clean'] = clean_numeric_vectorized(mapping_clean['Landed Price'])
        
        # Deduplicate mappings
        mapping_clean = mapping_clean.drop_duplicates(subset=['join_sku'])
        
        # Merge left
        merged = pd.merge(out, mapping_clean[['join_sku', 'landed_clean']], on='join_sku', how='left')
        
        # Fill old_price where 0
        merged['old_price'] = np.where(merged['old_price'] == 0, merged['landed_clean'].fillna(0), merged['old_price'])
        # If still 0, remains 0
        
        out = merged
    
    # ASSET LIST ENRICHMENT (bike_type, customer_type fallback, delivery_date)
    if not asset_df.empty:
        # Robust Join: Remove spaces for matching
        out['join_plate'] = out['vehicle_plate'].str.strip().str.upper().str.replace(' ', '')
        asset_clean = asset_df.copy()
        asset_clean['join_plate'] = asset_clean['Plat Nomor'].astype(str).str.strip().str.upper().str.replace(' ', '')
        asset_clean['asset_model'] = asset_clean['Model'].astype(str).str.slice(0, 50)
        asset_clean['asset_customer_type'] = asset_clean['Tempat Sewa Unit'].astype(str).str.slice(0, 100)
        
        # Delivery date - try multiple column names
        delivery_col = None
        for col in ['Delivery - Outbone', 'Delivery Date', 'delivery_date']:
            if col in asset_clean.columns:
                delivery_col = col
                break
        if delivery_col:
            asset_clean['asset_delivery_date'] = pd.to_datetime(asset_clean[delivery_col], errors='coerce')
        else:
            asset_clean['asset_delivery_date'] = pd.NaT
        
        asset_clean = asset_clean.drop_duplicates(subset=['join_plate'])
        
        merged = pd.merge(out, asset_clean[['join_plate', 'asset_model', 'asset_customer_type', 'asset_delivery_date']], on='join_plate', how='left')
        
        # Fill bike_type where empty
        merged['bike_type'] = merged.apply(
            lambda r: r['asset_model'] if (pd.isna(r['bike_type']) or r['bike_type'] in ['', 'nan', 'None']) else r['bike_type'],
            axis=1
        )
        
        # Fill customer_type where empty (fallback to Asset List)
        merged['customer_type'] = merged.apply(
            lambda r: r['asset_customer_type'] if (pd.isna(r['customer_type']) or r['customer_type'] in ['', 'nan', 'None']) else r['customer_type'],
            axis=1
        )
        
        # Set delivery_date from Asset List
        merged['delivery_date'] = merged['asset_delivery_date']
        
        out = merged.drop(columns=['asset_model', 'asset_customer_type', 'asset_delivery_date', 'join_plate'], errors='ignore')
    else:
        out['delivery_date'] = pd.NaT
    
    out['source_system'] = 'service_items'
    out['created_at'] = pd.to_datetime(out['created_at'])
    
    # Select columns (including delivery_date)
    final_cols = ['source_system', 'created_at', 'order_number', 'vehicle_plate', 'sku', 'item_name', 'erp_product_id',
                  'item_type', 'service_type', 'service_location_name', 'completed_by', 'customer_type',
                  'quantity', 'unit_price', 'final_price', 'subtotal_price', 'old_price',
                  'warranty_status', 'status', 'odometer', 'bike_type', 'delivery_date']
                  
    # Fill missing cols if any
    for col in final_cols:
        if col not in out.columns:
            out[col] = None
    return out[final_cols]

def standardize_part_usage(df, asset_df=pd.DataFrame(), mapping_df=pd.DataFrame()):
    """
    Transform Part Usage (CSV) to Unified Schema with Enrichment.
    """
    if df.empty:
        return pd.DataFrame()
        
    out = df.copy()
    
    # Clean Numerics
    out['quantity'] = clean_numeric_vectorized(out['final_quantity'].fillna(out['quantity']))
    out['unit_price'] = clean_numeric_vectorized(out['base_price'])
    out['final_price'] = clean_numeric_vectorized(out['final_price'])
    out['subtotal_price'] = clean_numeric_vectorized(out['subtotal_price'])
    
    # Subtotal Fallback
    mask_recalc = (out['subtotal_price'] == 0) & (out['quantity'] > 0) & (out['final_price'] > 0)
    out.loc[mask_recalc, 'subtotal_price'] = out.loc[mask_recalc, 'quantity'] * out.loc[mask_recalc, 'final_price']
    
    out['odometer'] = clean_numeric_vectorized(out['odometer']).astype(int)

    out['vehicle_plate'] = out['vehicle_license_plate'].astype(str).str.strip().str.upper().str.slice(0, 50)
    out['sku'] = out['sku'].astype(str).str.strip().str.upper().str.slice(0, 100)
    out['order_number'] = out['order_number'].astype(str).str.slice(0, 100)
    
    out['item_name'] = out['item_name'].astype(str).str.slice(0, 255)
    out['erp_product_id'] = out['erp_product_id'].astype(str).str.slice(0, 100)
    out['item_type'] = out['item_type'].astype(str).str.slice(0, 50)
    out['service_type'] = standardize_service_type_vectorized(out['service_type']).str.slice(0, 50)
    out['service_location_name'] = out['service_location_name'].astype(str).str.slice(0, 100)
    out['completed_by'] = out['price_finalized_by_name'].astype(str).str.slice(0, 100)
    
    out['warranty_status'] = out['warranty'].astype(str).str.slice(0, 50)
    out['status'] = out['status'].astype(str).str.slice(0, 50)
    
    if 'bike_type' in out.columns:
        out['bike_type'] = out['bike_type'].astype(str).str.slice(0, 50)
    else:
        out['bike_type'] = ''

    # ASSET LIST ENRICHMENT (customer_type, bike_type, delivery_date)
    if not asset_df.empty:
        # Robust Join: Remove spaces for matching
        out['join_plate'] = out['vehicle_plate'].str.strip().str.upper().str.replace(' ', '')
        asset_clean = asset_df.copy()
        asset_clean['join_plate'] = asset_clean['Plat Nomor'].astype(str).str.strip().str.upper().str.replace(' ', '')
        
        # Prepare columns
        asset_clean['asset_customer_type'] = asset_clean['Tempat Sewa Unit'].astype(str).str.slice(0, 100)
        asset_clean['asset_model'] = asset_clean['Model'].astype(str).str.slice(0, 50)
        
        # Delivery date - try multiple column names
        delivery_col = None
        for col in ['Delivery - Outbone', 'Delivery Date', 'delivery_date']:
            if col in asset_clean.columns:
                delivery_col = col
                break
        if delivery_col:
            asset_clean['asset_delivery_date'] = pd.to_datetime(asset_clean[delivery_col], errors='coerce')
        else:
            asset_clean['asset_delivery_date'] = pd.NaT
        
        # Deduplicate asset list - 1 plate = 1 record
        asset_clean = asset_clean.drop_duplicates(subset=['join_plate'])
        
        merged = pd.merge(out, asset_clean[['join_plate', 'asset_customer_type', 'asset_model', 'asset_delivery_date']], on='join_plate', how='left')
        merged['customer_type'] = merged['asset_customer_type'].fillna('')
        
        # BIKE_TYPE Enrichment
        merged['bike_type'] = merged.apply(
            lambda r: r['asset_model'] if (pd.isna(r['bike_type']) or r['bike_type'] in ['', 'nan', 'None']) else r['bike_type'],
            axis=1
        )
        
        # DELIVERY_DATE from Asset List
        merged['delivery_date'] = merged['asset_delivery_date']
        
        out = merged.drop(columns=['asset_customer_type', 'asset_model', 'asset_delivery_date', 'join_plate'], errors='ignore')
    else:
        out['customer_type'] = ''
        out['delivery_date'] = pd.NaT

    # OLD PRICE ENRICHMENT
    out['old_price'] = 0.0 # Default
    if not mapping_df.empty:
        out['join_sku'] = out['sku'].str.strip()
        mapping_clean = mapping_df.copy()
        mapping_clean['join_sku'] = mapping_clean['New SKU'].astype(str).str.strip()
        mapping_clean['landed_clean'] = clean_numeric_vectorized(mapping_clean['Landed Price'])
        
        # Deduplicate
        mapping_clean = mapping_clean.drop_duplicates(subset=['join_sku'])
        
        # Merge
        merged = pd.merge(out, mapping_clean[['join_sku', 'landed_clean']], on='join_sku', how='left')
        merged['old_price'] = merged['landed_clean'].fillna(0)
        out = merged
        
    out['source_system'] = 'part_usage'
    out['created_at'] = pd.to_datetime(out['created_at'])

    final_cols = ['source_system', 'created_at', 'order_number', 'vehicle_plate', 'sku', 'item_name', 'erp_product_id',
                  'item_type', 'service_type', 'service_location_name', 'completed_by', 'customer_type',
                  'quantity', 'unit_price', 'final_price', 'subtotal_price', 'old_price',
                  'warranty_status', 'status', 'odometer', 'bike_type', 'delivery_date']

    # Fill missing cols if any
    for col in final_cols:
        if col not in out.columns:
            out[col] = None
    return out[final_cols]
