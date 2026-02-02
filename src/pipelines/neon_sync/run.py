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
    calculate_warranty_coverage  # NEW
)
from src.common.data_loader import DataLoader
from src.common.config import (
    SHEET_ID_SERVICE_ITEMS, WORKSHEET_SERVICE_ITEMS,
    SHEET_ID_MAPPINGS, WORKSHEET_MAPPINGS,
    SHEET_ID_ASSET_LIST, WORKSHEET_ASSET,
    SHEET_ID_OUTPUT_REVIEW, WORKSHEET_PART_USAGE
)

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
    loader = NeonLoader()
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
    
    # DEDUPLICATION: Remove cross-source duplicates BEFORE explode
    # Key: (vehicle_plate, sku, created_date, service_location_name)
    # This removes duplicates from Apps vs Manual Sheet while preserving qty-based rows
    print("   🔄 Deduplicating cross-source duplicates (BEFORE explode)...")
    unified_df['created_at'] = pd.to_datetime(unified_df['created_at'])
    unified_df['created_date'] = unified_df['created_at'].dt.date
    key_cols = ['vehicle_plate', 'sku', 'created_date', 'service_location_name']
    before_dedup = len(unified_df)
    unified_df = unified_df.drop_duplicates(subset=key_cols, keep='first')
    after_dedup = len(unified_df)
    unified_df = unified_df.drop(columns=['created_date'], errors='ignore')
    print(f"   Deduplicated: {before_dedup} → {after_dedup} (removed {before_dedup - after_dedup})")
    
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
    print("   Sorting globally by created_at (ASC) for ID sequence...")
    final_df.sort_values(by='created_at', ascending=True, inplace=True)

    # --- 6. LOAD TO NEON ---
    print("\n💾 Loading to Neon...")
    
    try:
        if pipeline_mode == 'full':
            # FULL REFRESH: Truncate + Insert
            loader.truncate_table('unified_part_logs')
            loader.load_df_append(final_df, 'unified_part_logs')
            print(f"   ✅ Full refresh completed: {len(final_df)} rows loaded.")
            
        elif pipeline_mode == 'recalculate':
            # RECALCULATE: Upsert (update existing + insert new)
            print("   Using UPSERT for recalculation...")
            loader.upsert_df(final_df, 'unified_part_logs')
            print(f"   ✅ Recalculation completed: {len(final_df)} rows upserted.")
            
        else:
            # INCREMENTAL: Append only (no truncate)
            print("   Appending new data (Incremental)...")
            loader.load_df_append(final_df, 'unified_part_logs')
            print(f"   ✅ Incremental load completed: {len(final_df)} rows appended.")
        
        # Show final row count
        total_rows = loader.get_row_count('unified_part_logs')
        print(f"   📊 Total rows in Neon: {total_rows}")
        
    except Exception as e:
        print(f"❌ Error Loading to Neon: {e}")
        raise e
        
    print("\n✨ Pipeline Finished.")

if __name__ == "__main__":
    run_pipeline()
