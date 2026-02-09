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

CHUNK_SIZE = 10000


def sync_gel_to_sheets():
    """
    Main function to sync GEL data from Neon to Google Sheets.
    Uses chunked loading for memory efficiency.
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
    
    # First, get total count
    count_query = "SELECT COUNT(*) FROM unified_part_logs WHERE customer_type LIKE '%GEL%'"
    with neon.engine.connect() as conn:
        from sqlalchemy.sql import text
        total_rows = conn.execute(text(count_query)).scalar()
    
    print(f"   📊 Total GEL rows to sync: {total_rows}")
    
    if total_rows == 0:
        print("   ⚠️ No GEL data found. Nothing to sync.")
        return {'status': 'skipped', 'rows': 0}
    
    # Load data in chunks and write to sheet
    offset = 0
    chunk_num = 0
    total_written = 0
    
    while offset < total_rows:
        chunk_num += 1
        chunk_query = f"""
            SELECT 
                created_at, order_number, vehicle_plate, sku, item_name,
                item_type, service_type, service_location_name, completed_by,
                customer_type, quantity, unit_price, final_price, subtotal_price,
                old_price, status, odometer, bike_type, delivery_date,
                bulan_ke, year_cycle, limit_per_year, pergantian_ke_total,
                pergantian_ke_yearly, warranty_coverage
            FROM unified_part_logs
            WHERE customer_type LIKE '%GEL%'
            ORDER BY created_at ASC
            LIMIT {CHUNK_SIZE} OFFSET {offset}
        """
        
        df = neon.fetch_df(chunk_query)
        
        if df.empty:
            break
        
        # Format data for sheet
        # Convert datetime columns to string
        for col in ['created_at', 'delivery_date']:
            if col in df.columns:
                df[col] = df[col].astype(str).replace('NaT', '')
        
        # Replace NaN with empty string
        df = df.fillna('')
        
        print(f"   📤 Chunk {chunk_num}: {len(df)} rows (offset {offset})...")
        
        if offset == 0:
            # First chunk: clear and write header + data
            print("   🗑️ Clearing existing sheet data...")
            dl.upload_to_sheet(df, GRAB_ID_SHEET, SERVICE_HISTORY_GRAB)
        else:
            # Subsequent chunks: append only
            dl.append_to_sheet(df, GRAB_ID_SHEET, SERVICE_HISTORY_GRAB)
        
        total_written += len(df)
        offset += CHUNK_SIZE
    
    print(f"\n✅ GEL Sync Complete!")
    print(f"   📊 Total rows written: {total_written}")
    
    return {'status': 'success', 'rows': total_written}


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    sync_gel_to_sheets()
