"""
Script to clean duplicate items in item_name column for S4_REQUEST_SPK rows.
Run this script to backfill existing data without full regeneration.

Usage:
    python scripts/clean_item_name_duplicates.py
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
    
    # Try JSON string first (for GitHub Actions)
    creds_json = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')
    if creds_json:
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    else:
        # Fall back to file path
        creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if not creds_path:
            raise ValueError("No credentials found. Set GOOGLE_APPLICATION_CREDENTIALS or GOOGLE_APPLICATION_CREDENTIALS_JSON")
        creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    
    return gspread.authorize(creds)


def deduplicate_items(item_string):
    """
    Deduplicate comma-separated or newline-separated items while preserving order.
    Case-insensitive deduplication.
    """
    if not item_string or str(item_string).strip() == '':
        return item_string
    
    seen = set()
    parts = []
    
    # Split by comma OR newline
    import re
    items = re.split(r'[,\n]+', str(item_string))
    
    for item in items:
        item_clean = item.strip()
        item_lower = item_clean.lower()
        if item_clean and item_lower not in seen:
            seen.add(item_lower)
            parts.append(item_clean)
    
    return ', '.join(parts)


def main():
    print("🚀 Starting item_name deduplication for S4_REQUEST_SPK...")
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
    
    # Find column indices
    try:
        item_name_idx = headers.index('item_name')
        data_source_idx = headers.index('data_source')
    except ValueError as e:
        print(f"❌ Column not found: {e}")
        return
    
    print(f"   Found {len(rows)} total rows")
    print(f"   item_name column index: {item_name_idx}")
    print(f"   data_source column index: {data_source_idx}")
    
    # Find rows to update
    updates = []
    for row_num, row in enumerate(rows, start=2):  # start=2 because row 1 is header
        if len(row) > data_source_idx and row[data_source_idx] == 'S4_REQUEST_SPK':
            original_value = row[item_name_idx] if len(row) > item_name_idx else ''
            cleaned_value = deduplicate_items(original_value)
            
            if original_value != cleaned_value:
                updates.append({
                    'row': row_num,
                    'col': item_name_idx + 1,  # gspread uses 1-indexed
                    'original': original_value,
                    'cleaned': cleaned_value
                })
    
    print(f"\n📋 Found {len(updates)} rows with duplicates to clean")
    
    if not updates:
        print("✅ No duplicates found. Sheet is already clean!")
        return
    
    # Show preview
    print("\n📝 Preview (first 5):")
    for i, u in enumerate(updates[:5]):
        print(f"   Row {u['row']}: '{u['original'][:50]}...' → '{u['cleaned'][:50]}...'")
    
    # Confirm
    confirm = input(f"\n⚠️ Update {len(updates)} cells? (y/n): ")
    if confirm.lower() != 'y':
        print("❌ Cancelled")
        return
    
    # Batch update using range format (more efficient)
    print("\n🔄 Updating cells...")
    
    # Group updates for batch operation
    batch_size = 500
    total_batches = (len(updates) + batch_size - 1) // batch_size
    
    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(updates))
        batch = updates[start_idx:end_idx]
        
        # Build batch update data
        batch_data = []
        for u in batch:
            # Convert to A1 notation (e.g., "I5" for column 9, row 5)
            col_letter = chr(ord('A') + u['col'] - 1) if u['col'] <= 26 else 'A' + chr(ord('A') + u['col'] - 27)
            cell_ref = f"{col_letter}{u['row']}"
            batch_data.append({
                'range': cell_ref,
                'values': [[u['cleaned']]]
            })
        
        # Execute batch update
        worksheet.batch_update(batch_data, value_input_option='USER_ENTERED')
        print(f"   Updated batch {batch_num + 1}/{total_batches} ({len(batch)} cells)")
    
    print(f"\n✅ Successfully cleaned {len(updates)} rows!")


if __name__ == "__main__":
    main()
