
import pandas as pd
import sys
import os
import warnings
from src.common.data_loader import DataLoader
from src.pipelines.service_items.pipeline import ServiceItemsPipeline
from src.common.config import (
    SHEET_ID_OUTPUT, WORKSHEET_OUTPUT,
    SHEET_ID_MAPPINGS, WORKSHEET_MAPPINGS,
    SHEET_ID_ASSET_LIST, WORKSHEET_ASSET,
    SHEET_ID_SERVICE_ITEMS, WORKSHEET_SERVICE_ITEMS,
    WORKSHEET_IGNORE_PART
)

def run_service_items_pipeline():
    print("🚀 Starting Service Items Pipeline (Pipeline 2)...")
    
    # Suppress warnings
    warnings.filterwarnings('ignore')
    pd.options.mode.chained_assignment = None

    # 1. Initialize Loader
    loader = DataLoader()
    
    # 2. Load Data
    print("\n📥 Loading Data Sources...")

    # Input: Work Orders (Output from Pipeline 1)
    if not SHEET_ID_OUTPUT or not WORKSHEET_OUTPUT:
        print("❌ CRITICAL: Missing SHEET_ID_OUTPUT or WORKSHEET_OUTPUT config.")
        return

    print(f"   Loading Work Orders from {WORKSHEET_OUTPUT}...")
    work_orders_df = loader.load_gspread_data(SHEET_ID_OUTPUT, WORKSHEET_OUTPUT)
    
    if work_orders_df.empty:
        print("❌ CRITICAL: Work Orders data is empty. Cannot proceed.")
        return

    # Mapping Data
    if not SHEET_ID_MAPPINGS:
        print("❌ CRITICAL: SHEET_ID_MAPPINGS is not set in .env")
        return

    print(f"   Loading Mappings from {WORKSHEET_MAPPINGS}...")
    mapping_df = loader.load_gspread_data(SHEET_ID_MAPPINGS, WORKSHEET_MAPPINGS)

    # Bike Data (Asset List)
    print(f"   Loading Bike Data from {WORKSHEET_ASSET}...")
    bike_df = loader.load_gspread_data(SHEET_ID_ASSET_LIST, WORKSHEET_ASSET)

    # 3. Initialize Pipeline
    pipeline = ServiceItemsPipeline(work_orders_df, mapping_df, bike_df)
    
    # 4. Run Pipeline (returns full data, formatted output, and ignored parts)
    print("\n⚙️ Running Pipeline Logic...")
    full_df, formatted_df, ignored_df = pipeline.run_with_output()

    # 5. Export Results
    print("\n💾 Exporting Results...")

    # Export full data to local CSV (for debugging/archival)
    output_dir = os.path.join(os.getcwd(), 'output')
    os.makedirs(output_dir, exist_ok=True)
    
    local_path_full = os.path.join(output_dir, 'service_items_full.csv')
    full_df.to_csv(local_path_full, index=False)
    print(f"✅ Full data saved to {local_path_full} ({len(full_df)} rows)")
    
    local_path_formatted = os.path.join(output_dir, 'service_items_formatted.csv')
    formatted_df.to_csv(local_path_formatted, index=False)
    print(f"✅ Formatted data saved to {local_path_formatted} ({len(formatted_df)} rows)")

    # Save ignored parts locally
    if not ignored_df.empty:
        local_path_ignored = os.path.join(output_dir, 'service_items_ignored.csv')
        ignored_df.to_csv(local_path_ignored, index=False)
        print(f"⚠️ Ignored parts saved to {local_path_ignored} ({len(ignored_df)} rows)")

    # Upload FORMATTED output to Google Sheets
    print(f"\n☁️ Uploading to Google Sheets...")
    
    target_sheet_id = SHEET_ID_SERVICE_ITEMS
    
    if target_sheet_id and WORKSHEET_SERVICE_ITEMS:
        # Sort by created_at ascending before upload
        if 'created_at' in formatted_df.columns:
            formatted_df = formatted_df.sort_values('created_at', ascending=True).reset_index(drop=True)
            print(f"   📅 Sorted by created_at ASC")
        
        # Upload formatted output to main sheet
        print(f"   Uploading formatted data to {WORKSHEET_SERVICE_ITEMS}...")
        loader.upload_to_sheet(formatted_df, target_sheet_id, WORKSHEET_SERVICE_ITEMS)
        
        # Upload ignored parts to ignore_part sheet
        if not ignored_df.empty:
            print(f"   Uploading ignored parts to {WORKSHEET_IGNORE_PART}...")
            loader.upload_to_sheet(ignored_df, target_sheet_id, WORKSHEET_IGNORE_PART)
    else:
        print("⚠️ Skipping Upload: SHEET_ID_SERVICE_ITEMS or WORKSHEET_SERVICE_ITEMS not configured.")

    print("\n✅ Service Items Pipeline Completed Successfully.")

if __name__ == "__main__":
    run_service_items_pipeline()
