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
    calculate_pergantian_ke
)
from src.common.data_loader import DataLoader
from src.common.config import (
    SHEET_ID_SERVICE_ITEMS, WORKSHEET_SERVICE_ITEMS,
    SHEET_ID_MAPPINGS, WORKSHEET_MAPPINGS,
    SHEET_ID_ASSET_LIST, WORKSHEET_ASSET,
    SHEET_ID_OUTPUT_REVIEW, WORKSHEET_PART_USAGE
)

def run_pipeline():
    # Read Pipeline Mode from Environment (default: full)
    pipeline_mode = os.getenv('PIPELINE_MODE', 'full').lower()
    
    print(f"🚀 Starting Neon Sync Pipeline (Mode: {pipeline_mode.upper()})...")
    loader = NeonLoader()
    dl = DataLoader()
    
    # --- 0. PRELOAD AUXILIARY DATA (Enrichment Sources) ---
    print("\n📚 Loading Auxiliary Data...")
    
    # Asset List (for Customer Type)
    print("   Fetching Asset List...")
    asset_df = dl.load_gspread_data(SHEET_ID_ASSET_LIST, WORKSHEET_ASSET)
    print(f"   Shape: {asset_df.shape}")
    
    # Mappings (for Old Price)
    print("   Fetching Mappings...")
    mapping_df = dl.load_gspread_data(SHEET_ID_MAPPINGS, WORKSHEET_MAPPINGS)
    print(f"   Shape: {mapping_df.shape}")
    
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
    
    # Explode (Split Qty > 1)
    print("   💥 Exploding rows (Qty > 1)...")
    exploded_df = explode_rows(unified_df)
    print(f"   Post-Explosion Total: {len(exploded_df)} rows.")
    
    # Sort for Pergantian Ke calculation
    print("   Sorting for Calculation...")
    exploded_df['created_at'] = pd.to_datetime(exploded_df['created_at'])
    exploded_df.sort_values(by=['vehicle_plate', 'sku', 'created_at'], inplace=True)
    
    # Calculate Pergantian Ke
    # NOTE: For Incremental mode, this calculation is LOCAL to the new batch only.
    # For accurate cumulative counting, use FULL mode.
    print("   🧮 Calculating 'Pergantian Ke'...")
    final_df = calculate_pergantian_ke(exploded_df)
    
    # DEDUPLICATION: Remove duplicates based on unique constraint columns
    key_cols = ['source_system', 'order_number', 'sku', 'item_name', 'pergantian_ke']
    before_dedup = len(final_df)
    final_df = final_df.drop_duplicates(subset=key_cols, keep='first')
    after_dedup = len(final_df)
    if before_dedup != after_dedup:
        print(f"   🔄 Deduplicated: {before_dedup} → {after_dedup} (removed {before_dedup - after_dedup})")
    
    # Sample Check
    if not final_df.empty:
        sample = final_df[['vehicle_plate', 'sku', 'pergantian_ke']].head(5)
        print(f"   Sample Calc:\n{sample}")

    # --- 4. LOAD TO NEON ---
    print("\n💾 Loading to Neon...")
    
    try:
        if pipeline_mode == 'full':
            # FULL REFRESH: Truncate + Insert
            loader.execute_query("TRUNCATE TABLE unified_part_logs;")
            print("   Truncated target table (Full Refresh).")
        else:
            # INCREMENTAL: Append only (no truncate)
            print("   Appending new data (Incremental)...")
        
        # Load Data
        loader.load_df_append(final_df, 'unified_part_logs')
        print(f"   ✅ Successfully loaded {len(final_df)} rows to Neon.")
        
    except Exception as e:
        print(f"❌ Error Loading to Neon: {e}")
        
    print("\n✨ Pipeline Finished.")

if __name__ == "__main__":
    run_pipeline()
