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


def normalize_odometer(df, daily_km_estimate=100):
    """
    Normalize odometer values using linear estimation.
    
    Logic:
    1. Clean non-numeric characters, keep original values > 0 as-is.
    2. Intra-Order Sync: all items in the same WO share the highest odometer.
    3. Zero-fill: estimate from previous service odometer + (days_gap * daily_km_estimate).
       If no previous service, estimate from delivery_date to created_at.
    4. Final Intra-Order Sync after estimation.
    
    No max_odometer cap, no cummax, no time interpolation.
    """
    if df.empty or 'odometer' not in df.columns:
        return df
    
    print("🔧 Normalizing Odometer (Linear Estimation V3)...")
    
    # 0. Clean string types
    df['odometer'] = df['odometer'].astype(str).str.replace(r'[^\d]', '', regex=True).replace('', '0')
    df['odometer'] = pd.to_numeric(df['odometer'], errors='coerce').fillna(0).astype('int64')
    
    # 1. Intra-Order Sync: broadcast highest odometer within the same Work Order
    if 'order_number' in df.columns:
        df['odometer'] = df.groupby('order_number')['odometer'].transform('max')
    
    df = df.sort_values(['vehicle_plate', 'created_at']).reset_index(drop=True)
    
    # 2. Zero-fill estimation
    df['created_at_dt'] = pd.to_datetime(df['created_at'], errors='coerce')
    
    if 'delivery_date' in df.columns:
        df['delivery_date_dt'] = pd.to_datetime(df['delivery_date'], errors='coerce')
    else:
        df['delivery_date_dt'] = pd.NaT
    
    zeros_filled = 0
    
    # Process per plate group
    for plate, group in df.groupby('vehicle_plate'):
        last_valid_odo = 0
        last_valid_date = None  # Will be delivery_date or last valid service date
        
        # Try to use delivery_date as the starting anchor
        delivery_dt = group['delivery_date_dt'].iloc[0] if group['delivery_date_dt'].notna().any() else None
        if delivery_dt is not None and pd.notna(delivery_dt):
            last_valid_date = delivery_dt
        
        for idx in group.index:
            odo_val = df.at[idx, 'odometer']
            service_date = df.at[idx, 'created_at_dt']
            
            if odo_val > 0:
                # Keep original value, update anchor
                last_valid_odo = odo_val
                if pd.notna(service_date):
                    last_valid_date = service_date
            else:
                # Estimate from previous anchor
                if last_valid_date is not None and pd.notna(service_date) and pd.notna(last_valid_date):
                    days_gap = (service_date - last_valid_date).days
                    days_gap = max(0, days_gap)
                    estimated = last_valid_odo + (days_gap * daily_km_estimate)
                    df.at[idx, 'odometer'] = int(estimated)
                    zeros_filled += 1
                    # Update anchor to this estimated value so next zero builds on it
                    last_valid_odo = int(estimated)
                    last_valid_date = service_date
                elif last_valid_odo > 0:
                    # No valid date, just carry forward
                    df.at[idx, 'odometer'] = last_valid_odo
                    zeros_filled += 1
    
    if zeros_filled > 0:
        print(f"   ✅ Estimated {zeros_filled:,} zero odometer values")
    
    # 3. Final Intra-Order Sync after estimation
    if 'order_number' in df.columns:
        df['odometer'] = df.groupby('order_number')['odometer'].transform('max')
    
    # Cleanup temp cols
    df = df.drop(columns=['created_at_dt', 'delivery_date_dt'], errors='ignore')
    
    df['odometer'] = df['odometer'].astype('int64')
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
            asset_clean['_delivery_date'] = pd.to_datetime(asset_clean[delivery_col], errors='coerce', dayfirst=True)
            asset_clean = asset_clean.drop_duplicates(subset=['join_plate'])
            
            # If the dataframe already has a 'delivery_date' column, we only want to fill NaNs
            # But the signature suggests we are pulling it fresh if asset_df is provided.
            # Let's check if 'delivery_date' exists in the incoming df
            if 'delivery_date' in out.columns:
                # Ensure existing is datetime
                out['delivery_date'] = pd.to_datetime(out['delivery_date'], errors='coerce', dayfirst=True)
                
                # Merge and fill
                out = pd.merge(out, asset_clean[['join_plate', '_delivery_date']], on='join_plate', how='left')
                out['delivery_date'] = out['delivery_date'].fillna(out['_delivery_date'])
                out = out.drop(columns=['_delivery_date', 'join_plate'], errors='ignore')
            else:
                out = pd.merge(out, asset_clean[['join_plate', '_delivery_date']], on='join_plate', how='left')
                out['delivery_date'] = out['_delivery_date']
                out = out.drop(columns=['_delivery_date', 'join_plate'], errors='ignore')
        else:
            if 'delivery_date' not in out.columns:
                out['delivery_date'] = pd.NaT
            else:
                out['delivery_date'] = pd.to_datetime(out['delivery_date'], errors='coerce', dayfirst=True)
    else:
        if 'delivery_date' not in out.columns:
            out['delivery_date'] = pd.NaT
        else:
            out['delivery_date'] = pd.to_datetime(out['delivery_date'], errors='coerce', dayfirst=True)
    
    # --- Step 2: Customer Category Mapping ---
    # GEL → PARTNER_USER, else → ELECTRUM_USER
    out['customer_category'] = np.where(
        out['customer_type'].astype(str).str.upper().str.strip() == 'GEL',
        'PARTNER_USER',
        'ELECTRUM_USER'
    )
    
    # Ensure delivery_date is timezone-naive for safe calculations
    out['delivery_date'] = pd.to_datetime(out['delivery_date'], errors='coerce', dayfirst=True)
    if out['delivery_date'].dt.tz is not None:
        out['delivery_date'] = out['delivery_date'].dt.tz_localize(None)

    out['created_at'] = pd.to_datetime(out['created_at'], errors='coerce')
    if out['created_at'].dt.tz is not None:
        out['created_at'] = out['created_at'].dt.tz_localize(None)
    
    # --- Step 3: Calculate Bulan Ke (Calendar-based) ---
    # Uses calendar month diff so anniversary dates align exactly
    # e.g. delivery 2025-03-11 → created 2026-03-11 = bulan_ke 12, year_cycle 1
    mask_valid_dates = out['delivery_date'].notna() & out['created_at'].notna()
    
    out['bulan_ke'] = 0
    if mask_valid_dates.any():
        _created = out.loc[mask_valid_dates, 'created_at']
        _delivery = out.loc[mask_valid_dates, 'delivery_date']
        
        # Calendar month difference
        _month_diff = (_created.dt.year - _delivery.dt.year) * 12 + (_created.dt.month - _delivery.dt.month)
        # Subtract 1 if day-of-month hasn't been reached yet
        _before_day = (_created.dt.day < _delivery.dt.day).astype(int)
        out.loc[mask_valid_dates, 'bulan_ke'] = (_month_diff - _before_day).clip(lower=0).astype(int)
    
    # --- Step 4: Calculate Year Cycle ---
    out['year_cycle'] = (out['bulan_ke'] // 12).astype(int)
    
    # Create mask for invalid delivery date logic
    out['missing_delivery_date'] = ~mask_valid_dates
    
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
    def determine_warranty(row):
        """
        Determine warranty coverage following Mappings 'Warranty Type' taxonomy.
        
        Semantic covered_for matching:
          - PARTNER_USER → customer_type != EKB (i.e., customer_category == PARTNER_USER)
          - ELECTRUM_USER → customer_type == EKB (i.e., customer_category == ELECTRUM_USER)
          - BOTH → all customers
        
        Decision tree:
          1. No delivery_date → INVALID_WARRANTY
          2. covered_for mismatch → NOT_COVERED
          3. warranty_type == PACKAGE_SERVICE → check limit & period → PACKAGE_SERVICE or NOT_COVERED
          4. warranty_type == WARRANT → check period → WARRANT or NOT_COVERED
          5. warranty_type == INSURANCE, WARRANT → within period? WARRANT : INSURANCE
          6. warranty_type == INSURANCE → INSURANCE
          7. Else → NOT_COVERED
        """
        # 0. Strict delivery_date check
        if row.get('missing_delivery_date', False):
            return 'INVALID_WARRANTY (NO_DELIVERY_DATE)'
        
        # 1. Parse covered_for and check semantic match
        covered_for_raw = str(row.get('covered_for', '')).strip().upper()
        covered_list = [c.strip() for c in covered_for_raw.split(',') if c.strip()]
        customer_category = str(row.get('customer_category', '')).strip().upper()
        
        # Semantic matching
        # Empty covered_for = universal coverage (covers everyone)
        is_covered = False
        if not covered_list:
            is_covered = True  # No restriction = covers all
        elif 'BOTH' in covered_list:
            is_covered = True
        elif 'PARTNER_USER' in covered_list and customer_category == 'PARTNER_USER':
            is_covered = True
        elif 'ELECTRUM_USER' in covered_list and customer_category == 'ELECTRUM_USER':
            is_covered = True
        
        if not is_covered:
            return 'NOT_COVERED'
        
        # 2. Read warranty_type from Mappings
        wt = str(row.get('warranty_type', '')).strip().upper()
        bulan_ke = row.get('bulan_ke', 0)
        periode_garansi = row.get('periode_garansi', 0)
        limit_per_year = row.get('limit_per_year', 0)
        pergantian_ke_yearly = row.get('pergantian_ke_yearly', 1)
        within_period = (periode_garansi <= 0) or (bulan_ke <= periode_garansi)
        
        # 3. PACKAGE_SERVICE: check period + limit
        if wt == 'PACKAGE_SERVICE':
            if not within_period:
                return 'NOT_COVERED'
            if limit_per_year > 0 and pergantian_ke_yearly > limit_per_year:
                return 'NOT_COVERED'
            return 'PACKAGE_SERVICE'
        
        # 4. WARRANT: check period only
        if wt == 'WARRANT':
            if within_period:
                return 'WARRANT'
            else:
                return 'NOT_COVERED'
        
        # 5. INSURANCE, WARRANT: conditional split
        if wt == 'INSURANCE, WARRANT' or wt == 'INSURANCE,WARRANT':
            if within_period:
                return 'WARRANT'
            else:
                return 'INSURANCE'
        
        # 6. INSURANCE: always INSURANCE if covered
        if wt == 'INSURANCE':
            return 'INSURANCE'
        
        # 7. No mapping / unknown type → NOT_COVERED
        if wt == '' or wt == 'NOT_COVERED' or wt == 'NAN' or wt == 'NONE':
            return 'NOT_COVERED'
        
        # Fallback: return the warranty_type as-is
        return wt

    out['warranty_coverage'] = out.apply(determine_warranty, axis=1)
    
    # Clean up temp cols
    out = out.drop(columns=['missing_delivery_date'], errors='ignore')
    
    # Ensure standard categories where possible
    # Rename default to something recognizable if we only want 3 standard flags downstream.
    # We will keep detailed flags (e.g., NOT_COVERED (LIMIT_EXCEEDED)) as they are very useful for debugging.
    
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
    out['created_at'] = pd.to_datetime(out['created_at'], errors='coerce', format='mixed')
    
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
    out['created_at'] = pd.to_datetime(out['created_at'], errors='coerce', format='mixed')

    final_cols = ['source_system', 'created_at', 'order_number', 'vehicle_plate', 'sku', 'item_name', 'erp_product_id',
                  'item_type', 'service_type', 'service_location_name', 'completed_by', 'customer_type',
                  'quantity', 'unit_price', 'final_price', 'subtotal_price', 'old_price',
                  'warranty_status', 'status', 'odometer', 'bike_type', 'delivery_date']

    # Fill missing cols if any
    for col in final_cols:
        if col not in out.columns:
            out[col] = None
    return out[final_cols]
