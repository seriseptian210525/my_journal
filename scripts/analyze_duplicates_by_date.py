"""
Script to analyze duplicate order_ids and check if they're from incremental data.
Also allows deleting data from a specific date onwards.

Usage:
    python scripts/analyze_duplicates_by_date.py
"""

import os
import sys
import json
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


def parse_date(date_str):
    """Parse date string to datetime."""
    if not date_str or str(date_str).strip() == '':
        return None
    
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M:%S.%f',
        '%d/%m/%Y',
        '%d/%m/%Y %H:%M:%S'
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(str(date_str).strip()[:19], fmt[:len(str(date_str).strip())])
        except:
            continue
    return None


def main():
    print("🔍 Analyzing duplicate order_ids by date...")
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
        order_id_idx = headers.index('order_id')
        created_at_idx = headers.index('created_at')
    except ValueError as e:
        print(f"❌ Column not found: {e}")
        return
    
    print(f"   Found {len(rows)} total rows")
    
    # Analyze duplicates
    order_id_occurrences = {}  # order_id -> list of (row_num, created_at)
    
    for row_num, row in enumerate(rows, start=2):
        if len(row) > max(order_id_idx, created_at_idx):
            order_id = row[order_id_idx].strip()
            created_at = row[created_at_idx].strip() if len(row) > created_at_idx else ''
            
            if order_id:
                if order_id not in order_id_occurrences:
                    order_id_occurrences[order_id] = []
                order_id_occurrences[order_id].append({
                    'row': row_num,
                    'created_at': created_at
                })
    
    # Find duplicates
    duplicates = {k: v for k, v in order_id_occurrences.items() if len(v) > 1}
    
    print(f"\n📋 Analysis Results:")
    print(f"   Total unique order_ids: {len(order_id_occurrences)}")
    print(f"   Duplicate order_ids: {len(duplicates)}")
    
    if not duplicates:
        print("✅ No duplicates found!")
        return
    
    # Analyze dates of duplicates
    cutoff_date = datetime(2026, 2, 1)
    duplicates_from_feb = 0
    duplicates_before_feb = 0
    
    print(f"\n📅 Duplicate analysis (cutoff: {cutoff_date.strftime('%Y-%m-%d')}):")
    
    for order_id, occurrences in list(duplicates.items())[:10]:  # Show first 10
        print(f"\n   Order ID: {order_id}")
        for occ in occurrences:
            dt = parse_date(occ['created_at'])
            date_str = occ['created_at'][:19] if occ['created_at'] else 'N/A'
            is_feb = dt and dt >= cutoff_date
            marker = " 🔴 (>=Feb-01)" if is_feb else " ✅ (<Feb-01)"
            print(f"      Row {occ['row']}: {date_str}{marker}")
            
            if is_feb:
                duplicates_from_feb += 1
            elif dt:
                duplicates_before_feb += 1
    
    if len(duplicates) > 10:
        print(f"\n   ... and {len(duplicates) - 10} more duplicate order_ids")
    
    # Count rows by date
    print(f"\n📊 Row counts by date:")
    rows_before_feb = 0
    rows_from_feb = 0
    
    for row in rows:
        if len(row) > created_at_idx:
            dt = parse_date(row[created_at_idx])
            if dt:
                if dt >= cutoff_date:
                    rows_from_feb += 1
                else:
                    rows_before_feb += 1
    
    print(f"   Rows before Feb 1, 2026: {rows_before_feb}")
    print(f"   Rows from Feb 1, 2026 onwards: {rows_from_feb}")
    
    # Offer to delete Feb data
    if rows_from_feb > 0:
        print(f"\n⚠️ Found {rows_from_feb} rows from Feb 1, 2026 onwards.")
        confirm = input(f"Delete these {rows_from_feb} rows? (y/n): ")
        
        if confirm.lower() == 'y':
            print("\n🔄 Deleting rows from Feb 1, 2026 onwards...")
            
            # Keep only rows before Feb 1
            rows_to_keep = []
            deleted_count = 0
            
            for row in rows:
                if len(row) > created_at_idx:
                    dt = parse_date(row[created_at_idx])
                    if dt and dt >= cutoff_date:
                        deleted_count += 1
                        continue  # Skip this row
                rows_to_keep.append(row)
            
            # Rewrite sheet
            new_data = [headers] + rows_to_keep
            
            print(f"   Clearing sheet...")
            worksheet.clear()
            
            print(f"   Writing {len(new_data)} rows...")
            batch_size = 5000
            for i in range(0, len(new_data), batch_size):
                batch = new_data[i:i+batch_size]
                start_row = i + 1
                worksheet.update(f'A{start_row}', batch, value_input_option='USER_ENTERED')
                print(f"   Written rows {start_row}-{start_row + len(batch) - 1}")
            
            print(f"\n✅ Deleted {deleted_count} rows from Feb 1, 2026 onwards.")
            print(f"   Remaining rows: {len(rows_to_keep)}")
        else:
            print("❌ Cancelled")
    else:
        print("\n✅ No rows from Feb 1, 2026 found to delete.")


if __name__ == "__main__":
    main()
