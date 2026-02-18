"""
Sync GEL data from Neon to Google Sheet.
Runs weekly on Friday at 11:00 WIB (cron job).
"""
import sys
import os
from pathlib import Path

# Add project root
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent
sys.path.append(str(project_root))

from src.common.data_loader import DataLoader
from src.pipelines.neon_sync.loader import NeonLoader

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

# Query for GEL data
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



def sync_gel_to_sheets():
    """
    Main function to sync GEL data from Neon to Google Sheets.
    Loads all GEL data then uses upload_to_sheet (clear + batch write).
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
    
    # Load ALL GEL data in single query
    # ~38K rows × 25 cols ≈ 5-10 MB — safe for single load
    print("   📥 Querying GEL data from Neon...")
    df = neon.fetch_df(QUERY_GEL)
    
    print(f"   📊 Total GEL rows fetched: {len(df)}")
    
    if df.empty:
        print("   ⚠️ No GEL data found. Nothing to sync.")
        return {'status': 'skipped', 'rows': 0}
    
    # Ensure correct column order
    df = df[[c for c in FINAL_COLUMNS if c in df.columns]]
    
    # Format datetime columns for sheet
    for col in ['created_at', 'delivery_date']:
        if col in df.columns:
            df[col] = df[col].astype(str).replace('NaT', '')
    
    # Replace NaN with empty string
    df = df.fillna('')
    
    # Upload: clear sheet + write all data (handles batching internally)
    print(f"   📤 Uploading {len(df)} rows to Google Sheet...")
    dl.upload_to_sheet(df, GRAB_ID_SHEET, SERVICE_HISTORY_GRAB)
    
    print(f"\n✅ GEL Sync Complete!")
    print(f"   📊 Total rows written: {len(df)}")
    
    return {'status': 'success', 'rows': len(df)}


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    sync_gel_to_sheets()
