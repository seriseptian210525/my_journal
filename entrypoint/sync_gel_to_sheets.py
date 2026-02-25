"""
Sync GEL data from Cloud Data (Google Drive CSV) to Google Sheet.
Runs weekly on Friday at 11:00 WIB (cron job).

Pipeline:
1. Load latest Cloud Data CSV from Google Drive
2. Filter for GEL customers
3. Upload to Google Sheet (clear + replace)
"""
import sys
import os
from pathlib import Path
import pandas as pd

# Add project root
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent
sys.path.append(str(project_root))

from src.common.data_loader import DataLoader

# Config from env
GRAB_ID_SHEET = os.getenv('GRAB_ID_SHEET', 'your_sheet_id_here')
SERVICE_HISTORY_GRAB = os.getenv('SERVICE_HISTORY_GRAB', 'SERVICE HISTORY GRAB')
GDRIVE_OUTPUT_FOLDER_ID = os.getenv('GDRIVE_OUTPUT_FOLDER_ID', '1lLb2vjbsccIMvL6LCFdvPxYwroIkMr2S')

# Final output columns
FINAL_COLUMNS = [
    'created_at', 'order_number', 'vehicle_plate', 'sku', 'item_name',
    'item_type', 'service_type', 'service_location_name', 'completed_by',
    'customer_type', 'quantity', 'unit_price', 'final_price', 'subtotal_price',
    'old_price', 'status', 'odometer', 'bike_type', 'delivery_date',
    'bulan_ke', 'year_cycle', 'limit_per_year', 'pergantian_ke_total',
    'pergantian_ke_yearly', 'warranty_coverage'
]


def sync_gel_to_sheets():
    """
    Main function to sync GEL data from Cloud CSV to Google Sheets.
    Pipeline: Download CSV → Filter GEL → Upload
    """
    print("🚀 Starting GEL Sync to Google Sheets (from Cloud Data CSV)...")
    print(f"   Target Sheet: {GRAB_ID_SHEET}")
    print(f"   Target Worksheet: {SERVICE_HISTORY_GRAB}")
    
    # Validate config
    if GRAB_ID_SHEET == 'your_sheet_id_here':
        raise ValueError("❌ GRAB_ID_SHEET not configured! Please set in .env or GitHub Secrets.")
    
    dl = DataLoader()
    
    # --- Step 1: Load Cloud Data CSV ---
    print(f"\n📥 Step 1: Downloading latest Cloud Data CSV from Drive...")
    try:
        df = dl.load_csv_from_drive(GDRIVE_OUTPUT_FOLDER_ID, "unified_part_logs_latest.csv")
    except Exception as e:
        print(f"❌ Failed to load Cloud Data CSV: {e}")
        return {'status': 'failed', 'rows': 0}
        
    print(f"   📊 Total Cloud Data rows fetched: {len(df)}")
    
    if df.empty:
        print("   ⚠️ No data found in CSV. Nothing to sync.")
        return {'status': 'skipped', 'rows': 0}
    
    # --- Step 2: Filter GEL Data ---
    print("\n🔍 Step 2: Filtering for GEL customers...")
    
    # Prefer customer_category if it exists, otherwise fallback to customer_type
    if 'customer_category' in df.columns:
        gel_df = df[df['customer_category'].astype(str).str.upper() == 'PARTNER_USER'].copy()
    elif 'customer_type' in df.columns:
        gel_df = df[df['customer_type'].astype(str).str.upper() == 'GEL'].copy()
    else:
        print("   ❌ Neither customer_category nor customer_type column found!")
        return {'status': 'failed', 'rows': 0}
        
    print(f"   📊 GEL rows after filtering: {len(gel_df)}")
    
    if gel_df.empty:
        print("   ⚠️ No GEL data found after filtering. Skipping upload.")
        return {'status': 'skipped', 'rows': 0}
    
    # --- Step 3: Prepare & Upload ---
    print("\n📤 Step 3: Uploading to Google Sheet...")
    
    # Sort by created_at ASC for sheet output, use multi-column sort for stability
    if 'created_at' in gel_df.columns:
        sort_cols = ['created_at']
        if 'vehicle_plate' in gel_df.columns: sort_cols.append('vehicle_plate')
        if 'pergantian_ke_total' in gel_df.columns: sort_cols.append('pergantian_ke_total')
        
        gel_df = gel_df.sort_values(sort_cols, ascending=[True]*len(sort_cols)).reset_index(drop=True)
    
    # Ensure correct column order
    gel_df = gel_df[[c for c in FINAL_COLUMNS if c in gel_df.columns]]
    
    # --- Phase 8: Smart Repair Delivery Date ---
    print("   🔧 Applying Smart Repair on delivery_date...")
    if 'delivery_date' in gel_df.columns and 'created_at' in gel_df.columns:
        # Convert both to proper datetime for manipulation
        temp_delivery = pd.to_datetime(gel_df['delivery_date'], errors='coerce', dayfirst=True)
        temp_created = pd.to_datetime(gel_df['created_at'], errors='coerce')
        
        # Smart Repair: fill missing delivery_date using created_at
        temp_delivery = temp_delivery.fillna(temp_created)
        
        # Enforce YYYY-MM-DD
        gel_df['delivery_date'] = temp_delivery.dt.strftime('%Y-%m-%d')
        
    # Format other datetime columns for sheet
    if 'created_at' in gel_df.columns:
        gel_df['created_at'] = gel_df['created_at'].astype(str).replace('nan', '').replace('NaT', '')
    
    # Replace NaN with empty string
    gel_df = gel_df.fillna('')
    
    # Upload: clear sheet + write all data
    print(f"   📤 Uploading {len(gel_df)} rows to Google Sheet...")
    dl.upload_to_sheet(gel_df, GRAB_ID_SHEET, SERVICE_HISTORY_GRAB)
    
    print(f"\n✅ GEL Sync Complete!")
    print(f"   📊 Total rows written: {len(gel_df)}")
    
    return {'status': 'success', 'rows': len(gel_df)}


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    sync_gel_to_sheets()
