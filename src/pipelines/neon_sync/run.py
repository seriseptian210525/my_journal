import sys
import os
from pathlib import Path
import pandas as pd
from datetime import datetime

# Add project root
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
sys.path.append(str(project_root))

from src.pipelines.neon_sync.loader import NeonLoader
from src.pipelines.neon_sync.transformers import (
    standardize_service_items, 
    standardize_part_usage,
    explode_rows,
    calculate_pergantian_ke,
    calculate_warranty_coverage,
    normalize_odometer
)
from src.common.data_loader import DataLoader
from src.common.config import (
    SHEET_ID_SERVICE_ITEMS, WORKSHEET_SERVICE_ITEMS,
    SHEET_ID_MAPPINGS, WORKSHEET_MAPPINGS,
    SHEET_ID_ASSET_LIST, WORKSHEET_ASSET,
    SHEET_ID_OUTPUT_REVIEW, WORKSHEET_PART_USAGE
)

from dotenv import load_dotenv
load_dotenv()

GDRIVE_OUTPUT_FOLDER_ID = os.environ.get("GDRIVE_OUTPUT_FOLDER_ID", "1lLb2vjbsccIMvL6LCFdvPxYwroIkMr2S")

def run_pipeline():
    """
    Main Neon Sync Pipeline with Warranty Recalculation.
    
    Modes:
    - full: Truncate + Full refresh with warranty recalculation
    - incremental: Append new data only (with warranty calc)
    - recalculate: Re-calculate warranty for existing data (upsert)
    """
    # Read Pipeline Mode from Environment (default: full)
    pipeline_mode = os.getenv('PIPELINE_MODE', 'full').lower()
    
    print(f"🚀 Starting Neon Sync Pipeline (Mode: {pipeline_mode.upper()})...")
    
    dl = DataLoader()
    
    # --- 0. PRELOAD AUXILIARY DATA (Enrichment Sources) ---
    print("\n📚 Loading Auxiliary Data...")
    
    # Asset List (for Customer Type + Delivery Date)
    print("   Fetching Asset List...")
    asset_df = dl.load_gspread_data(SHEET_ID_ASSET_LIST, WORKSHEET_ASSET)
    print(f"   Shape: {asset_df.shape}")
    
    # Mappings (for Old Price + Warranty Config)
    print("   Fetching Mappings...")
    mapping_df = dl.load_gspread_data(SHEET_ID_MAPPINGS, WORKSHEET_MAPPINGS)
    print(f"   Shape: {mapping_df.shape}")
    
    # Safety check: abort if critical data failed to load
    if mapping_df.empty:
        raise RuntimeError("❌ ABORTED: Mappings DataFrame is empty (possible Google API error). Re-run pipeline.")
    if asset_df.empty:
        raise RuntimeError("❌ ABORTED: Asset List DataFrame is empty (possible Google API error). Re-run pipeline.")
    
    # --- INCREMENTAL MODE: Get Max Date from Neon ---
    max_date_filter = None
    if pipeline_mode == 'incremental':
        print("\n🔍 Incremental Mode: Checking last sync date...")
        max_date = loader.get_max_created_at()
        if max_date:
            max_date_filter = pd.to_datetime(max_date).tz_localize(None)
            print(f"   Last sync: {max_date_filter}")
        else:
            print("   No existing data in Neon. Running as Full Refresh.")
            pipeline_mode = 'full'  # Fallback to full if empty
    
    # --- 1. SERVICE ITEMS (from GSheet) ---
    print("\n📦 Processing: Service Items...")
    si_df = pd.DataFrame()
    try:
        raw_si = dl.load_gspread_data(SHEET_ID_SERVICE_ITEMS, WORKSHEET_SERVICE_ITEMS)
        
        # Incremental Filter
        if max_date_filter is not None and not raw_si.empty:
            raw_si['created_at'] = pd.to_datetime(raw_si['created_at'])
            original_count = len(raw_si)
            raw_si = raw_si[raw_si['created_at'] > max_date_filter]
            print(f"   Filtered: {original_count} → {len(raw_si)} rows (new data only)")
        
        if not raw_si.empty:
            si_df = standardize_service_items(raw_si, asset_df=asset_df, mapping_df=mapping_df)
            print(f"   Standardized {len(si_df)} rows.")
        else:
            print("   No new Service Items data.")
    except Exception as e:
        print(f"❌ Error Service Items: {e}")

    # --- 2. PART USAGE (from GSheet - NOT CSV) ---
    print("\n📦 Processing: Part Usage (from GSheet)...")
    pu_df = pd.DataFrame()
    try:
        raw_pu = dl.load_gspread_data(SHEET_ID_OUTPUT_REVIEW, WORKSHEET_PART_USAGE)
        print(f"   Fetched {len(raw_pu)} rows from GSheet.")
        
        # Incremental Filter
        if max_date_filter is not None and not raw_pu.empty:
            raw_pu['created_at'] = pd.to_datetime(raw_pu['created_at'])
            original_count = len(raw_pu)
            raw_pu = raw_pu[raw_pu['created_at'] > max_date_filter]
            print(f"   Filtered: {original_count} → {len(raw_pu)} rows (new data only)")
        
        if not raw_pu.empty:
            pu_df = standardize_part_usage(raw_pu, asset_df=asset_df, mapping_df=mapping_df)
            print(f"   Standardized {len(pu_df)} rows.")
        else:
            print("   No new Part Usage data.")
    except Exception as e:
        print(f"❌ Error Part Usage: {e}")

    # --- 3. MERGE & TRANSFORMATION ---
    print("\n🔄 Merging & Transforming...")
    
    if si_df.empty and pu_df.empty:
        print("❌ No data to process. Exiting.")
        return

    # Merge
    unified_df = pd.concat([si_df, pu_df], ignore_index=True)
    print(f"   Merged Total: {len(unified_df)} rows.")
    
    # --- EXCLUDE TEST/INVALID PLATES ---
    test_plates = [
        'B 1234 XXX', 'B 3252 WWD', 'B 4086 SWF', 'B 4921 SVO', 'B 5050 BCA',
        'B 9999 BLU', 'B 9999 GRE', 'EL 0015 H3', 'EL 1234 MKT'
    ]
    before_exclude = len(unified_df)
    unified_df = unified_df[~unified_df['vehicle_plate'].isin(test_plates)]
    excluded_count = before_exclude - len(unified_df)
    if excluded_count > 0:
        print(f"   🚫 Excluded {excluded_count} rows (test plates)")
    
    # --- FORWARD FILL MISSING DATA (delivery_date, customer_type, bike_type) ---
    # For plates with missing data, borrow from nearby records (same plate)
    fill_cols = ['delivery_date', 'customer_type', 'bike_type']
    for col in fill_cols:
        if col in unified_df.columns:
            missing_before = unified_df[col].isna().sum()
            if missing_before > 0:
                # Sort by plate and created_at, then forward fill within same plate
                unified_df = unified_df.sort_values(['vehicle_plate', 'created_at'])
                unified_df[col] = unified_df.groupby('vehicle_plate')[col].transform(
                    lambda x: x.ffill().bfill()
                )
                missing_after = unified_df[col].isna().sum()
                filled = missing_before - missing_after
                if filled > 0:
                    print(f"   ✅ Forward-filled {filled} missing {col} values")
    
    # --- FALLBACK MISSING DATA FROM ASSET LIST ---
    print("   🔍 Checking for remaining missing data against Asset List...")
    if asset_df is not None and not asset_df.empty:
        asset_clean = asset_df.copy()
        
        # Try different column names for plate
        asset_plate_col = None
        for col in ['Plat Nomor', 'Plate Number', 'vehicle_license_plate']:
            if col in asset_clean.columns:
                asset_plate_col = col
                break
                
        asset_customer_col = 'Jenis Customer' if 'Jenis Customer' in asset_clean.columns else None
        asset_bike_type_col = 'Type Motor' if 'Type Motor' in asset_clean.columns else None
        
        if asset_plate_col and (asset_customer_col or asset_bike_type_col):
            asset_clean['join_plate'] = asset_clean[asset_plate_col].astype(str).str.strip().str.upper().str.replace(' ', '')
            asset_clean = asset_clean.drop_duplicates(subset=['join_plate'])
            unified_df['join_plate'] = unified_df['vehicle_plate'].astype(str).str.strip().str.upper().str.replace(' ', '')
            
            # Fallback customer_type
            if asset_customer_col and 'customer_type' in unified_df.columns:
                missing_ct = unified_df['customer_type'].isna() | (unified_df['customer_type'] == '')
                if missing_ct.any():
                    ct_map = dict(zip(asset_clean['join_plate'], asset_clean[asset_customer_col]))
                    unified_df.loc[missing_ct, 'customer_type'] = unified_df.loc[missing_ct, 'join_plate'].map(ct_map).fillna('')
                    still_missing_ct = unified_df['customer_type'].isna() | (unified_df['customer_type'] == '')
                    if still_missing_ct.any():
                        unified_df.loc[still_missing_ct, 'customer_type'] = 'UNKNOWN'
                    print(f"   🔧 Fallback mapped {missing_ct.sum() - still_missing_ct.sum()} missing customer_type from Asset List.")
            
            # Fallback bike_type
            if asset_bike_type_col and 'bike_type' in unified_df.columns:
                missing_bt = unified_df['bike_type'].isna() | (unified_df['bike_type'] == '')
                if missing_bt.any():
                    bt_map = dict(zip(asset_clean['join_plate'], asset_clean[asset_bike_type_col]))
                    unified_df.loc[missing_bt, 'bike_type'] = unified_df.loc[missing_bt, 'join_plate'].map(bt_map).fillna('')
                    still_missing_bt = unified_df['bike_type'].isna() | (unified_df['bike_type'] == '')
                    if still_missing_bt.any():
                        unified_df.loc[still_missing_bt, 'bike_type'] = 'UNKNOWN'
                    print(f"   🔧 Fallback mapped {missing_bt.sum() - still_missing_bt.sum()} missing bike_type from Asset List.")
            
            unified_df = unified_df.drop(columns=['join_plate'])
    
    # --- FIX INCONSISTENT CUSTOMER_TYPE ---
    # Rule: L-prefix plate + H1 model = GEL (from Asset List master convention)
    if 'customer_type' in unified_df.columns and 'bike_type' in unified_df.columns:
        l_prefix_h1_mask = (
            unified_df['vehicle_plate'].astype(str).str.startswith('L ') & 
            (unified_df['bike_type'].astype(str).str.upper() == 'H1')
        )
        before_fix = (unified_df.loc[l_prefix_h1_mask, 'customer_type'] != 'GEL').sum()
        if before_fix > 0:
            unified_df.loc[l_prefix_h1_mask, 'customer_type'] = 'GEL'
            print(f"   🔧 Fixed {before_fix} rows: L-prefix + H1 → customer_type = GEL")
    
    # DEDUPLICATION: Remove cross-source duplicates BEFORE explode
    # Key: (vehicle_plate, sku, created_date, service_location_name)
    # Priority: WO- prefix (from Part Usage) is preferred over non-WO (Service Items)
    print("   🔄 Deduplicating cross-source duplicates (BEFORE explode)...")
    print("\n🔄 Deduplicating (same asset+part+date+location)...")
    
    # Step 1: Detect WO- prefix (from Part Usage) - these get priority
    unified_df['has_wo_prefix'] = unified_df['order_number'].astype(str).str.contains('WO-', case=False, na=False)
    
    # Step 2: Strict normalization for dedup keys
    unified_df['dedup_plate'] = unified_df['vehicle_plate'].astype(str).str.strip().str.upper()
    unified_df['dedup_sku'] = unified_df['sku'].astype(str).str.strip().str.upper()
    unified_df['dedup_loc'] = unified_df['service_location_name'].astype(str).str.strip().str.upper()
    unified_df['dedup_date'] = pd.to_datetime(unified_df['created_at']).dt.date.astype(str)
    
    # Step 3: Sort by WO- priority (True first = WO- records on top)
    unified_df = unified_df.sort_values(by=['has_wo_prefix'], ascending=[False])
    
    key_cols = ['dedup_plate', 'dedup_sku', 'dedup_date', 'dedup_loc']
    before_dedup = len(unified_df)
    
    # Step 4: Dedup keeping first (which is WO- due to sort)
    unified_df = unified_df.drop_duplicates(subset=key_cols, keep='first')
    after_dedup = len(unified_df)
    
    # Cleanup temp columns
    unified_df = unified_df.drop(columns=['dedup_plate', 'dedup_sku', 'dedup_loc', 'dedup_date', 'has_wo_prefix'], errors='ignore')
    print(f"   Deduplicated: {before_dedup} -> {after_dedup} (removed {before_dedup - after_dedup})")
    
    # Explode (Split Qty > 1) - AFTER dedup, so qty-based rows are preserved
    print("   💥 Exploding rows (Qty > 1)...")
    exploded_df = explode_rows(unified_df)
    print(f"   Post-Explosion Total: {len(exploded_df)} rows.")
    
    # Sort by created_at (ASC) to ensure chronological order for warranty calculation
    print("   Sorting by created_at (ASC)...")
    exploded_df['created_at'] = pd.to_datetime(exploded_df['created_at'])
    exploded_df.sort_values(by='created_at', ascending=True, inplace=True)
    
    # --- 4. WARRANTY RECALCULATION (NEW) ---
    print("\n🛡️ Calculating Warranty Coverage...")
    enriched_df = calculate_warranty_coverage(exploded_df, asset_df=asset_df, mapping_df=mapping_df)
    print(f"   Enriched Total: {len(enriched_df)} rows.")
    
    # --- 5. ODOMETER NORMALIZATION ---
    enriched_df = normalize_odometer(enriched_df)
    
    # Sample Check
    if not enriched_df.empty:
        sample = enriched_df[['vehicle_plate', 'sku', 'customer_category', 'bulan_ke', 'year_cycle', 'pergantian_ke_total', 'pergantian_ke_yearly', 'warranty_coverage']].head(5)
        print(f"   Sample Enriched Data:\n{sample}")
    
    # --- 5. PREPARE FINAL COLUMNS ---
    print("\n📝 Preparing Final Columns...")
    
    # Ensure all required columns exist
    final_columns = [
        'source_system', 'created_at', 'order_number', 'vehicle_plate', 'sku', 'item_name', 'erp_product_id',
        'item_type', 'service_type', 'service_location_name', 'completed_by', 'customer_type',
        'quantity', 'unit_price', 'final_price', 'subtotal_price', 'old_price',
        'warranty_status', 'status', 'odometer', 'bike_type',
        # NEW warranty columns
        'delivery_date', 'bulan_ke', 'year_cycle', 'customer_category',
        'warranty_type', 'covered_for', 'limit_per_year', 'pergantian_ke_total', 'pergantian_ke_yearly', 'warranty_coverage'
    ]
    
    # Add missing columns with defaults
    for col in final_columns:
        if col not in enriched_df.columns:
            enriched_df[col] = None
    
    final_df = enriched_df[final_columns].copy()

    # SORT GLOBAL BY CREATED_AT (ASC)
    # Ensure ID 1 corresponds to earliest date (2024)
    print("   Sorting globally by created_at (ASC) and sequence for ID sequence stability...")
    final_df.sort_values(by=['created_at', 'vehicle_plate', 'pergantian_ke_total'], ascending=[True, True, True], inplace=True)

    # --- 6. EXPORT TO GOOGLE DRIVE (CSV) ---
    print("\n💾 Exporting to Google Drive (CSV)...")
    
    try:
        from datetime import datetime
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"unified_part_logs_latest.csv" # Overwrite same file for dashboard integration
        
        file_id = dl.upload_csv_to_drive(final_df, GDRIVE_OUTPUT_FOLDER_ID, filename)
        
        print(f"   📊 Total rows exported: {len(final_df)}")
        print(f"   ✅ Export successful. Google Drive File ID: {file_id}")
        
        # Also save locally for Streamlit cache
        local_output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), 'output', 'unified_part_logs_latest.csv')
        os.makedirs(os.path.dirname(local_output_path), exist_ok=True)
        final_df.to_csv(local_output_path, index=False)
        print(f"   💾 Local copy saved: {local_output_path}")
        
    except Exception as e:
        print(f"❌ Error Exporting to Google Drive: {e}")
        raise e
        
    print("\n✨ Pipeline Finished.")

if __name__ == "__main__":
    run_pipeline()
