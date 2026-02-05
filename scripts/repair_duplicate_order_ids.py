"""
Smart script to repair duplicate order_ids:
1. If rows with same order_id have DIFFERENT values -> Regenerate new unique ID
2. If rows with same order_id have IDENTICAL values -> Delete duplicate (keep first)

Usage:
    python scripts/repair_duplicate_order_ids.py
"""

import os
import sys
import json
import random
import gspread
from datetime import datetime
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


def generate_unique_order_id(existing_ids: set) -> str:
    """Generate a new unique order_id that doesn't exist in the set."""
    # Use current timestamp + random component
    timestamp = int(datetime.now().timestamp() * 1000)
    
    while True:
        random_suffix = random.randint(1000, 9999)
        new_id = f"WO-{timestamp}{random_suffix}"
        if new_id not in existing_ids:
            existing_ids.add(new_id)
            return new_id


def rows_are_identical(row1, row2, exclude_col_idx=None):
    """Check if two rows have identical values (excluding specified column)."""
    for i in range(min(len(row1), len(row2))):
        if exclude_col_idx is not None and i == exclude_col_idx:
            continue  # Skip order_id column
        if row1[i].strip() != row2[i].strip():
            return False
    return True


def main():
    print("🔧 Smart Repair for Duplicate order_ids...")
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
    
    # Build set of all existing order_ids
    existing_ids = set()
    for row in rows:
        if len(row) > order_id_idx:
            existing_ids.add(row[order_id_idx].strip())
    
    # Find duplicate order_ids with their row indices
    order_id_rows = {}  # order_id -> [(row_idx, row_data), ...]
    
    for row_idx, row in enumerate(rows):
        if len(row) > order_id_idx:
            order_id = row[order_id_idx].strip()
            if order_id:
                if order_id not in order_id_rows:
                    order_id_rows[order_id] = []
                order_id_rows[order_id].append((row_idx, row))
    
    # Find duplicates
    duplicates = {k: v for k, v in order_id_rows.items() if len(v) > 1}
    
    print(f"\n📋 Found {len(duplicates)} duplicate order_ids")
    
    if not duplicates:
        print("✅ No duplicates found!")
        return
    
    # Analyze and categorize duplicates
    to_regenerate = []  # (row_idx, new_order_id)
    to_delete = []  # row_idx
    
    for order_id, occurrences in duplicates.items():
        # Keep first occurrence, analyze the rest
        first_idx, first_row = occurrences[0]
        
        for other_idx, other_row in occurrences[1:]:
            if rows_are_identical(first_row, other_row, exclude_col_idx=order_id_idx):
                # Identical rows -> mark for deletion
                to_delete.append(other_idx)
            else:
                # Different rows -> regenerate order_id
                new_id = generate_unique_order_id(existing_ids)
                to_regenerate.append((other_idx, new_id))
    
    print(f"\n📊 Repair Plan:")
    print(f"   Rows to regenerate order_id: {len(to_regenerate)}")
    print(f"   True duplicate rows to delete: {len(to_delete)}")
    
    if not to_regenerate and not to_delete:
        print("✅ Nothing to repair!")
        return
    
    # Show preview
    if to_regenerate:
        print(f"\n📝 Preview - Regenerate IDs (first 5):")
        for row_idx, new_id in to_regenerate[:5]:
            old_id = rows[row_idx][order_id_idx]
            print(f"   Row {row_idx + 2}: '{old_id}' → '{new_id}'")
        if len(to_regenerate) > 5:
            print(f"   ... and {len(to_regenerate) - 5} more")
    
    if to_delete:
        print(f"\n🗑️ Preview - Delete true duplicates (first 5):")
        for row_idx in to_delete[:5]:
            order_id = rows[row_idx][order_id_idx]
            print(f"   Row {row_idx + 2}: order_id = {order_id}")
        if len(to_delete) > 5:
            print(f"   ... and {len(to_delete) - 5} more")
    
    # Confirm
    confirm = input(f"\n⚠️ Apply repairs? (y/n): ")
    if confirm.lower() != 'y':
        print("❌ Cancelled")
        return
    
    # Apply repairs
    print("\n🔄 Applying repairs...")
    
    # 1. Update regenerated IDs
    if to_regenerate:
        print(f"   Updating {len(to_regenerate)} order_ids...")
        
        batch_data = []
        for row_idx, new_id in to_regenerate:
            row_num = row_idx + 2  # +2 for header and 1-indexed
            col_letter = chr(ord('A') + order_id_idx)
            cell_ref = f"{col_letter}{row_num}"
            batch_data.append({
                'range': cell_ref,
                'values': [[new_id]]
            })
            # Update in-memory rows
            rows[row_idx][order_id_idx] = new_id
        
        # Batch update
        batch_size = 500
        for i in range(0, len(batch_data), batch_size):
            batch = batch_data[i:i+batch_size]
            worksheet.batch_update(batch, value_input_option='USER_ENTERED')
            print(f"      Updated batch {i//batch_size + 1}/{(len(batch_data) + batch_size - 1)//batch_size}")
    
    # 2. Remove true duplicates
    if to_delete:
        print(f"   Removing {len(to_delete)} true duplicate rows...")
        
        # Create new rows list without deleted rows
        delete_set = set(to_delete)
        new_rows = [row for idx, row in enumerate(rows) if idx not in delete_set]
        
        # Rewrite sheet
        new_data = [headers] + new_rows
        
        worksheet.clear()
        
        batch_size = 5000
        for i in range(0, len(new_data), batch_size):
            batch = new_data[i:i+batch_size]
            start_row = i + 1
            worksheet.update(f'A{start_row}', batch, value_input_option='USER_ENTERED')
            print(f"      Written rows {start_row}-{start_row + len(batch) - 1}")
    
    print(f"\n✅ Repairs completed!")
    print(f"   Regenerated {len(to_regenerate)} order_ids")
    print(f"   Deleted {len(to_delete)} true duplicate rows")
    print(f"   Final row count: {len(rows) - len(to_delete)}")


if __name__ == "__main__":
    main()
