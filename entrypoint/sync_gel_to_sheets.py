"""
Sync GEL data from Neon to Google Sheet.
Runs weekly on Friday at 11:00 WIB (cron job).

Pipeline:
1. Query all GEL data from Neon
2. Dedup by (date, vehicle_plate, item_name, service_location_name)
3. Recalculate pergantian_ke and warranty_coverage
4. Upload to Google Sheet (clear + replace)
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
from src.pipelines.neon_sync.loader import NeonLoader
from src.pipelines.neon_sync.transformers import calculate_warranty_coverage
from src.common.config import SHEET_ID_MAPPINGS, WORKSHEET_MAPPINGS

# Config from env
GRAB_ID_SHEET = os.getenv('GRAB_ID_SHEET', 'your_sheet_id_here')
SERVICE_HISTORY_GRAB = os.getenv('SERVICE_HISTORY_GRAB', 'SERVICE HISTORY GRAB')

# Final output columns (25 columns)
FINAL_COLUMNS = [
    'created_at', 'order_number', 'vehicle_plate', 'sku', 'item_name',
    'item_type', 'service_type', 'service_location_name', 'completed_by',
    'customer_type', 'quantity', 'unit_price', 'final_price', 'subtotal_price',
    'old_price', 'status', 'odometer', 'bike_type', 'delivery_date',
    'bulan_ke', 'year_cycle', 'limit_per_year', 'pergantian_ke_total',
    'pergantian_ke_yearly', 'warranty_coverage'
]

# Query for GEL data — pull all columns needed for warranty recalculation
QUERY_GEL = """
SELECT 
    created_at, order_number, vehicle_plate, sku, item_name,
    item_type, service_type, service_location_name, completed_by,
    customer_type, quantity, unit_price, final_price, subtotal_price,
    old_price, status, odometer, bike_type, delivery_date,
    bulan_ke, year_cycle, limit_per_year, pergantian_ke_total,
    pergantian_ke_yearly, warranty_coverage
FROM unified_part_logs
WHERE customer_type LIKE '%GEL%'
ORDER BY created_at ASC;
"""

# Dedup key columns
DEDUP_COLUMNS = ['created_date', 'vehicle_plate', 'item_name', 'service_location_name']


def dedup_gel_data(df):
    """
    Remove duplicates where same date (ignoring time), vehicle_plate,
    item_name, service_location_name but different order_number.
    Keep first occurrence.
    """
    before = len(df)
    
    # Create date-only column for dedup
    df['created_date'] = pd.to_datetime(df['created_at']).dt.date
    
    df = df.drop_duplicates(subset=DEDUP_COLUMNS, keep='first')
    df = df.drop(columns=['created_date'])
    
    removed = before - len(df)
    print(f"   🔄 Dedup: {before} → {len(df)} rows ({removed} duplicates removed)")
    
    return df


def recalculate_warranty(df, mapping_df):
    """
    Recalculate pergantian_ke_total, pergantian_ke_yearly, and warranty_coverage
    after dedup changes row counts.
    """
    print("   🔧 Recalculating warranty coverage...")
    
    # Ensure created_at is datetime for sorting
    df['created_at'] = pd.to_datetime(df['created_at'], errors='coerce')
    df['delivery_date'] = pd.to_datetime(df['delivery_date'], errors='coerce')
    
    # Recalculate using existing transformer logic
    # skip_sequence_calc=False → recalculates pergantian_ke_total and pergantian_ke_yearly
    df = calculate_warranty_coverage(
        df,
        asset_df=None,       # delivery_date already in data, no need to re-join
        mapping_df=mapping_df,
        skip_sequence_calc=False
    )
    
    # Print distribution
    if 'warranty_coverage' in df.columns:
        print(f"   📊 Warranty distribution after recalc:")
        print(df['warranty_coverage'].value_counts().to_string())
    
    return df


def sync_gel_to_sheets():
    """
    Main function to sync GEL data from Neon to Google Sheets.
    Pipeline: Query → Dedup → Recalculate Warranty → Upload
    """
    print("🚀 Starting GEL Sync to Google Sheets...")
    print(f"   Target Sheet: {GRAB_ID_SHEET}")
    print(f"   Target Worksheet: {SERVICE_HISTORY_GRAB}")
    
    # Validate config
    if GRAB_ID_SHEET == 'your_sheet_id_here':
        raise ValueError("❌ GRAB_ID_SHEET not configured! Please set in .env or GitHub Secrets.")
    
    # Initialize clients
    neon = NeonLoader()
    dl = DataLoader()
    
    # --- Step 1: Load ALL GEL data ---
    print("\n📥 Step 1: Querying GEL data from Neon...")
    df = neon.fetch_df(QUERY_GEL)
    print(f"   📊 Total GEL rows fetched: {len(df)}")
    
    if df.empty:
        print("   ⚠️ No GEL data found. Nothing to sync.")
        return {'status': 'skipped', 'rows': 0}
    
    # --- Step 2: Dedup ---
    print("\n🔄 Step 2: Removing duplicates...")
    df = dedup_gel_data(df)
    
    # --- Step 3: Load Mappings & Recalculate Warranty ---
    print("\n🔧 Step 3: Recalculating warranty coverage...")
    mapping_df = dl.load_gspread_data(SHEET_ID_MAPPINGS, WORKSHEET_MAPPINGS)
    print(f"   📚 Loaded {len(mapping_df)} mapping rows")
    df = recalculate_warranty(df, mapping_df)
    
    # --- Step 4: Prepare & Upload ---
    print("\n📤 Step 4: Uploading to Google Sheet...")
    
    # Ensure correct column order
    df = df[[c for c in FINAL_COLUMNS if c in df.columns]]
    
    # Format datetime columns for sheet
    for col in ['created_at', 'delivery_date']:
        if col in df.columns:
            df[col] = df[col].astype(str).replace('NaT', '')
    
    # Replace NaN with empty string
    df = df.fillna('')
    
    # Upload: clear sheet + write all data
    print(f"   📤 Uploading {len(df)} rows to Google Sheet...")
    dl.upload_to_sheet(df, GRAB_ID_SHEET, SERVICE_HISTORY_GRAB)
    
    print(f"\n✅ GEL Sync Complete!")
    print(f"   📊 Total rows written: {len(df)}")
    
    return {'status': 'success', 'rows': len(df)}


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    sync_gel_to_sheets()
