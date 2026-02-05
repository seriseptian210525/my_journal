"""
Script to remove duplicate order_id rows from work_orders sheet.
Keeps only the FIRST occurrence of each order_id.

FASTER APPROACH: Reads all data, removes duplicates in memory, rewrites sheet.

Usage:
    python scripts/remove_duplicate_order_ids.py
"""

import os
import sys
import json
import gspread
from google.oauth2.service_account import Credentials

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# Config
SHEET_ID = os.getenv('SHEET_ID_OUTPUT')
WORKSHEET_NAME = os.getenv('WORKSHEET_OUTPUT', 'work_orders')


def get_gspread_client():
    """Initialize gspread client."""
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    
    creds_json = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')
    if creds_json:
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    else:
        creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if not creds_path:
            raise ValueError("No credentials found")
        creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    
    return gspread.authorize(creds)


def main():
    print("🚀 Starting duplicate order_id removal (FAST MODE)...")
    print(f"   Sheet ID: {SHEET_ID}")
    print(f"   Worksheet: {WORKSHEET_NAME}")
    
    if not SHEET_ID:
        print("❌ Error: SHEET_ID_OUTPUT not set in .env")
        return
    
    # Connect to Google Sheets
    print("\n📊 Connecting to Google Sheets...")
    client = get_gspread_client()
    sheet = client.open_by_key(SHEET_ID)
    worksheet = sheet.worksheet(WORKSHEET_NAME)
    
    # Get all data
    print("   Reading all data...")
    all_data = worksheet.get_all_values()
    
    if len(all_data) < 2:
        print("❌ No data found in sheet")
        return
    
    headers = all_data[0]
    rows = all_data[1:]
    
    # Find order_id column
    try:
        order_id_idx = headers.index('order_id')
    except ValueError:
        print("❌ Column 'order_id' not found")
        return
    
    print(f"   Found {len(rows)} total rows")
    print(f"   order_id column index: {order_id_idx}")
    
    # Deduplicate (keep first occurrence)
    seen_order_ids = set()
    unique_rows = []
    duplicates_count = 0
    
    for row in rows:
        if len(row) > order_id_idx:
            order_id = row[order_id_idx].strip()
            if order_id:
                if order_id in seen_order_ids:
                    duplicates_count += 1
                    continue  # Skip duplicate
                seen_order_ids.add(order_id)
        unique_rows.append(row)
    
    print(f"\n📋 Deduplication results:")
    print(f"   Original rows: {len(rows)}")
    print(f"   Duplicate rows: {duplicates_count}")
    print(f"   Unique rows: {len(unique_rows)}")
    
    if duplicates_count == 0:
        print("✅ No duplicates found. Sheet is already clean!")
        return
    
    # Confirm
    confirm = input(f"\n⚠️ Rewrite sheet with {len(unique_rows)} unique rows (removing {duplicates_count} duplicates)? (y/n): ")
    if confirm.lower() != 'y':
        print("❌ Cancelled")
        return
    
    # Rewrite sheet
    print("\n🔄 Rewriting sheet without duplicates...")
    
    # Prepare data with headers
    new_data = [headers] + unique_rows
    
    # Clear and write
    print("   Clearing sheet...")
    worksheet.clear()
    
    print(f"   Writing {len(new_data)} rows...")
    
    # Write in batches to avoid timeout
    batch_size = 5000
    for i in range(0, len(new_data), batch_size):
        batch = new_data[i:i+batch_size]
        start_row = i + 1
        end_row = start_row + len(batch) - 1
        
        worksheet.update(f'A{start_row}', batch, value_input_option='USER_ENTERED')
        print(f"   Written rows {start_row}-{end_row}")
    
    print(f"\n✅ Successfully removed {duplicates_count} duplicate rows!")
    print(f"   Final row count: {len(unique_rows)}")


if __name__ == "__main__":
    main()
