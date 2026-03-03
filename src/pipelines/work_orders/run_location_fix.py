"""
Location Fix Pipeline - Hybrid Mode
Reads from existing work_orders, applies location remapping, outputs to work_orders_v2
Does NOT regenerate order_id - keeps existing values
"""

import pandas as pd
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from src.common.data_loader import DataLoader
from src.common.config import (
    SHEET_ID_OUTPUT, WORKSHEET_OUTPUT,
    SHEET_ID_LOCATIONS, WORKSHEET_LOCATIONS,
    SHEET_ID_OUTPUT_REVIEW, WORKSHEET_OUTPUT_REVIEW
)


def run_location_fix():
    """
    Hybrid mode: Read work_orders, apply location fix, output to work_orders_v2
    """
    print("🔧 Starting Location Fix Pipeline (Hybrid Mode)...")
    print("=" * 60)
    
    loader = DataLoader()
    
    # 1. Load existing work_orders
    print("\n📥 Loading existing work_orders...")
    df = loader.load_gspread_data(SHEET_ID_OUTPUT, WORKSHEET_OUTPUT)
    print(f"   Loaded {len(df)} rows from work_orders")
    
    if df.empty:
        print("❌ No data in work_orders. Aborting.")
        return None
    
    # 2. Load master location
    print("\n📥 Loading master location data...")
    
    if not SHEET_ID_LOCATIONS or SHEET_ID_LOCATIONS == '<PLACEHOLDER_SHEET_ID>':
        print("❌ SHEET_ID_LOCATIONS not configured. Please update .env file.")
        return None
    
    location_df = loader.load_gspread_data(SHEET_ID_LOCATIONS, WORKSHEET_LOCATIONS)
    
    if location_df.empty:
        print("❌ No master location data. Aborting.")
        return None
    
    # Build location map with pattern support
    import re
    
    location_map = {}
    alias_map = {}
    pattern_list = []  # List of (compiled_regex, name, id)
    
    print("\n🗺️ Building location map...")
    for _, row in location_df.iterrows():
        loc_id = str(row.get('id', '')).strip()
        loc_name = str(row.get('name', '')).strip()
        pattern = str(row.get('pattern', '')).strip()
        
        if loc_id and loc_name and loc_id != 'nan' and loc_name != 'nan':
            norm_name = loc_name.strip()
            location_map[norm_name] = loc_id
            alias_map[loc_name.lower()] = (norm_name, loc_id)
            alias_map[norm_name.lower()] = (norm_name, loc_id)
            
            # Build regex patterns
            if pattern and pattern != 'nan' and pattern != '':
                try:
                    compiled = re.compile(pattern, re.IGNORECASE)
                    pattern_list.append((compiled, norm_name, loc_id))
                except re.error as e:
                    print(f"   ⚠️ Invalid regex for {norm_name}: {pattern}")
    
    print(f"   ✅ Loaded {len(location_map)} locations, {len(pattern_list)} patterns")
    
    # 3. Apply location fix
    print("\n🔄 Applying location mapping...")
    
    def resolve_location(row):
        """Resolve location name to ID with status tracking"""
        loc = row.get('service_location_name')
        original = loc
        
        # Flag for null/empty
        if pd.isna(loc) or str(loc).strip() == '' or str(loc).lower() == 'nan':
            return None, None, True, "EMPTY_FROM_SOURCE"
        
        loc_str = str(loc).strip()
        loc_lower = loc_str.lower()
        
        # 1. Exact match in alias map
        if loc_lower in alias_map:
            norm_name, loc_id = alias_map[loc_lower]
            return norm_name, loc_id, False, "EXACT_MATCH"
        
        # 2. Pattern/Regex match (driven by master sheet 'pattern' column)
        for compiled_regex, norm_name, loc_id in pattern_list:
            if compiled_regex.search(loc_str):
                return norm_name, loc_id, False, "PATTERN_MATCH"
        
        # 3. No match found — flag for review
        return loc_str, None, True, f"NOT_IN_MASTER:{original}"
    
    # Apply to all rows
    results = df.apply(resolve_location, axis=1)
    
    df['service_location_name'] = results.apply(lambda x: x[0])
    df['service_location_id'] = results.apply(lambda x: x[1])
    df['location_is_null'] = results.apply(lambda x: x[2])  # Boolean flag
    df['location_resolve_status'] = results.apply(lambda x: x[3])
    
    # 4. Print stats
    null_count = df['location_is_null'].sum()
    total = len(df)
    
    print(f"\n📊 Results:")
    print(f"   Total rows: {total}")
    print(f"   Mapped successfully: {total - null_count}")
    print(f"   Null/Unresolved: {null_count}")
    
    # Breakdown by status
    status_counts = df['location_resolve_status'].value_counts()
    print(f"\n📋 Status Breakdown:")
    for status, count in status_counts.items():
        pct = (count / total) * 100
        print(f"   - {status}: {count} ({pct:.1f}%)")
    
    # Show unique unresolved locations
    unresolved = df[df['location_is_null'] == True]
    if not unresolved.empty:
        unique_locs = unresolved['location_resolve_status'].unique()
        print(f"\n⚠️ Unique unresolved patterns ({len(unique_locs)}):")
        for loc in unique_locs[:20]:  # Show first 20
            count = len(unresolved[unresolved['location_resolve_status'] == loc])
            print(f"   - {loc}: {count}")
    
    # 5. Output to review sheet  
    output_sheet_id = SHEET_ID_OUTPUT_REVIEW if SHEET_ID_OUTPUT_REVIEW and SHEET_ID_OUTPUT_REVIEW != '<PLACEHOLDER_SHEET_ID>' else SHEET_ID_OUTPUT
    output_worksheet = WORKSHEET_OUTPUT_REVIEW if WORKSHEET_OUTPUT_REVIEW else 'work_orders_v2'
    print(f"\n💾 Saving to {output_worksheet}...")
    print(f"   Target Sheet ID: {output_sheet_id[:20]}...")
    
    loader.upload_to_sheet(df, output_sheet_id, output_worksheet)
    
    print("\n" + "=" * 60)
    print("✅ Location fix complete!")
    print(f"   Review output in: {output_worksheet}")
    print(f"   Filter by 'location_is_null = TRUE' to see issues")
    print("=" * 60)
    
    return df


if __name__ == "__main__":
    run_location_fix()
