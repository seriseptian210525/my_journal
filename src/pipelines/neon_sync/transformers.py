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
    Calculate 'Pergantian Ke' (Running Count) per Vehicle + SKU.
    """
    if df.empty:
        return df
    df['pergantian_ke'] = df.groupby(['vehicle_plate', 'sku']).cumcount() + 1
    return df

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
    out['vehicle_plate'] = out['Vehicle License Plate'].astype(str).str.slice(0, 50)
    out['sku'] = out['Sku'].astype(str).str.slice(0, 100)
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
    
    # BIKE_TYPE ENRICHMENT from Asset List
    if not asset_df.empty:
        out['join_plate'] = out['vehicle_plate'].str.strip().str.upper()
        asset_clean = asset_df.copy()
        asset_clean['join_plate'] = asset_clean['Plat Nomor'].astype(str).str.strip().str.upper()
        asset_clean['asset_model'] = asset_clean['Model'].astype(str).str.slice(0, 50)
        asset_clean = asset_clean.drop_duplicates(subset=['join_plate'])
        
        merged = pd.merge(out, asset_clean[['join_plate', 'asset_model']], on='join_plate', how='left')
        # Fill bike_type where empty
        merged['bike_type'] = merged.apply(
            lambda r: r['asset_model'] if (pd.isna(r['bike_type']) or r['bike_type'] in ['', 'nan', 'None']) else r['bike_type'],
            axis=1
        )
        out = merged.drop(columns=['asset_model', 'join_plate'], errors='ignore')
    
    out['source_system'] = 'service_items'
    out['created_at'] = pd.to_datetime(out['created_at'])
    
    # Select columns
    final_cols = ['source_system', 'created_at', 'order_number', 'vehicle_plate', 'sku', 'item_name', 'erp_product_id',
                  'item_type', 'service_type', 'service_location_name', 'completed_by', 'customer_type',
                  'quantity', 'unit_price', 'final_price', 'subtotal_price', 'old_price',
                  'warranty_status', 'status', 'odometer', 'bike_type']
                  
    # Fill missing cols if any
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

    out['vehicle_plate'] = out['vehicle_license_plate'].astype(str).str.slice(0, 50)
    out['sku'] = out['sku'].astype(str).str.slice(0, 100)
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

    # CUSTOMER TYPE ENRICHMENT
    if not asset_df.empty:
        out['join_plate'] = out['vehicle_plate'].str.strip().str.upper()
        asset_clean = asset_df.copy()
        asset_clean['join_plate'] = asset_clean['Plat Nomor'].astype(str).str.strip().str.upper()
        
        # Deduplicate asset list? Assume 1 plate = 1 customer type?
        # Drop duplicates on plate to ensure 1:1 join
        asset_clean = asset_clean.drop_duplicates(subset=['join_plate'])
        
        merged = pd.merge(out, asset_clean[['join_plate', 'Tempat Sewa Unit', 'Model']], on='join_plate', how='left')
        merged['customer_type'] = merged['Tempat Sewa Unit'].fillna('')
        
        # BIKE_TYPE Enrichment
        merged['asset_model'] = merged['Model'].astype(str).str.slice(0, 50)
        merged['bike_type'] = merged.apply(
            lambda r: r['asset_model'] if (pd.isna(r['bike_type']) or r['bike_type'] in ['', 'nan', 'None']) else r['bike_type'],
            axis=1
        )
        out = merged.drop(columns=['Tempat Sewa Unit', 'Model', 'asset_model', 'join_plate'], errors='ignore')
    else:
        out['customer_type'] = ''

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
                  'warranty_status', 'status', 'odometer', 'bike_type']

    return out[final_cols]
