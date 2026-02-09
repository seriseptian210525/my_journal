"""
Enrich Google Sheets (service_items + part_usage) with Asset List lookup.
Updates the source sheets with customer_type, bike_type, delivery_date from Asset List.
"""
import sys
import os
from pathlib import Path
import pandas as pd
from datetime import datetime

# Add project root
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent
sys.path.append(str(project_root))

from src.common.data_loader import DataLoader
from src.common.config import (
    SHEET_ID_SERVICE_ITEMS, WORKSHEET_SERVICE_ITEMS,
    SHEET_ID_ASSET_LIST, WORKSHEET_ASSET,
    SHEET_ID_OUTPUT_REVIEW, WORKSHEET_PART_USAGE
)

def enrich_from_asset_list(df: pd.DataFrame, asset_df: pd.DataFrame, plate_col: str) -> pd.DataFrame:
    """
    Enrich DataFrame with customer_type, bike_type, delivery_date from Asset List.
    
    Args:
        df: Source DataFrame to enrich
        asset_df: Asset List DataFrame
        plate_col: Column name containing vehicle plate in source df
    """
    if df.empty or asset_df.empty:
        return df
    
    out = df.copy()
    
    # Normalize plate for join
    out['_join_plate'] = out[plate_col].astype(str).str.strip().str.upper().str.replace(' ', '')
    
    # Prepare asset lookup
    asset_clean = asset_df.copy()
    asset_clean['_join_plate'] = asset_clean['Plat Nomor'].astype(str).str.strip().str.upper().str.replace(' ', '')
    asset_clean['_asset_customer_type'] = asset_clean['Tempat Sewa Unit'].astype(str)
    asset_clean['_asset_model'] = asset_clean['Model'].astype(str)
    
    # Delivery date - try multiple column names
    delivery_col = None
    for col in ['Delivery - Outbone', 'Delivery Date', 'delivery_date']:
        if col in asset_clean.columns:
            delivery_col = col
            break
    if delivery_col:
        asset_clean['_asset_delivery_date'] = pd.to_datetime(asset_clean[delivery_col], errors='coerce')
    else:
        asset_clean['_asset_delivery_date'] = pd.NaT
    
    asset_clean = asset_clean.drop_duplicates(subset=['_join_plate'])
    
    # Merge
    merged = pd.merge(
        out, 
        asset_clean[['_join_plate', '_asset_customer_type', '_asset_model', '_asset_delivery_date']], 
        on='_join_plate', 
        how='left'
    )
    
    # Update columns
    # customer_type
    if 'customer_type' in merged.columns or 'Customer Type' in merged.columns:
        cust_col = 'Customer Type' if 'Customer Type' in merged.columns else 'customer_type'
        merged[cust_col] = merged.apply(
            lambda r: r['_asset_customer_type'] if (pd.isna(r.get(cust_col)) or str(r.get(cust_col, '')).strip() in ['', 'nan', 'None']) else r.get(cust_col),
            axis=1
        )
    else:
        merged['customer_type'] = merged['_asset_customer_type']
    
    # bike_type
    if 'bike_type' in merged.columns:
        merged['bike_type'] = merged.apply(
            lambda r: r['_asset_model'] if (pd.isna(r.get('bike_type')) or str(r.get('bike_type', '')).strip() in ['', 'nan', 'None']) else r.get('bike_type'),
            axis=1
        )
    else:
        merged['bike_type'] = merged['_asset_model']
    
    # delivery_date
    if 'delivery_date' in merged.columns:
        merged['delivery_date'] = merged.apply(
            lambda r: r['_asset_delivery_date'] if pd.isna(r.get('delivery_date')) else r.get('delivery_date'),
            axis=1
        )
    else:
        merged['delivery_date'] = merged['_asset_delivery_date']
    
    # Cleanup temp columns
    merged = merged.drop(columns=['_join_plate', '_asset_customer_type', '_asset_model', '_asset_delivery_date'], errors='ignore')
    
    return merged


def run_enrichment(sheets: list = None, dry_run: bool = False):
    """
    Run enrichment on specified sheets.
    
    Args:
        sheets: List of sheets to enrich ['service_items', 'part_usage']. Default: both.
        dry_run: If True, only show stats without writing to sheets.
    """
    if sheets is None:
        sheets = ['service_items', 'part_usage']
    
    print(f"🚀 Starting Sheet Enrichment (dry_run={dry_run})...")
    print(f"   Sheets to process: {sheets}")
    
    dl = DataLoader()
    
    # Load Asset List
    print("\n📚 Loading Asset List...")
    asset_df = dl.load_gspread_data(SHEET_ID_ASSET_LIST, WORKSHEET_ASSET)
    print(f"   Loaded {len(asset_df)} assets")
    
    stats = {}
    
    # --- SERVICE ITEMS ---
    if 'service_items' in sheets:
        print("\n📦 Processing: Service Items...")
        try:
            raw_si = dl.load_gspread_data(SHEET_ID_SERVICE_ITEMS, WORKSHEET_SERVICE_ITEMS)
            print(f"   Loaded {len(raw_si)} rows")
            
            # Pre-enrichment stats
            pre_stats = {
                'customer_type_null': raw_si['Customer Type'].isna().sum() + (raw_si['Customer Type'] == '').sum() if 'Customer Type' in raw_si.columns else len(raw_si),
                'bike_type_null': raw_si['bike_type'].isna().sum() + (raw_si['bike_type'] == '').sum() if 'bike_type' in raw_si.columns else len(raw_si),
                'delivery_date_null': raw_si['delivery_date'].isna().sum() if 'delivery_date' in raw_si.columns else len(raw_si)
            }
            
            # Enrich
            enriched_si = enrich_from_asset_list(raw_si, asset_df, 'Vehicle License Plate')
            
            # Post-enrichment stats
            post_stats = {
                'customer_type_null': enriched_si['Customer Type'].isna().sum() + (enriched_si['Customer Type'] == '').sum() if 'Customer Type' in enriched_si.columns else 0,
                'bike_type_null': enriched_si['bike_type'].isna().sum() + (enriched_si['bike_type'] == '').sum() if 'bike_type' in enriched_si.columns else 0,
                'delivery_date_null': enriched_si['delivery_date'].isna().sum() if 'delivery_date' in enriched_si.columns else 0
            }
            
            print(f"   📊 Stats:")
            print(f"      customer_type NULL: {pre_stats['customer_type_null']} → {post_stats['customer_type_null']}")
            print(f"      bike_type NULL: {pre_stats['bike_type_null']} → {post_stats['bike_type_null']}")
            print(f"      delivery_date NULL: {pre_stats['delivery_date_null']} → {post_stats['delivery_date_null']}")
            
            stats['service_items'] = {'pre': pre_stats, 'post': post_stats}
            
            if not dry_run:
                print("   💾 Uploading to sheet...")
                dl.upload_to_sheet(enriched_si, SHEET_ID_SERVICE_ITEMS, WORKSHEET_SERVICE_ITEMS)
                print("   ✅ Service Items updated!")
            else:
                print("   ⏸️ Dry run - skipping upload")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            stats['service_items'] = {'error': str(e)}
    
    # --- PART USAGE ---
    if 'part_usage' in sheets:
        print("\n📦 Processing: Part Usage...")
        try:
            raw_pu = dl.load_gspread_data(SHEET_ID_OUTPUT_REVIEW, WORKSHEET_PART_USAGE)
            print(f"   Loaded {len(raw_pu)} rows")
            
            # Pre-enrichment stats - check various column name variants
            cust_col = 'customer_type' if 'customer_type' in raw_pu.columns else None
            bike_col = 'bike_type' if 'bike_type' in raw_pu.columns else None
            del_col = 'delivery_date' if 'delivery_date' in raw_pu.columns else None
            
            pre_stats = {
                'customer_type_null': raw_pu[cust_col].isna().sum() + (raw_pu[cust_col] == '').sum() if cust_col else len(raw_pu),
                'bike_type_null': raw_pu[bike_col].isna().sum() + (raw_pu[bike_col] == '').sum() if bike_col else len(raw_pu),
                'delivery_date_null': raw_pu[del_col].isna().sum() if del_col else len(raw_pu)
            }
            
            # Enrich
            enriched_pu = enrich_from_asset_list(raw_pu, asset_df, 'vehicle_license_plate')
            
            # Post-enrichment stats
            post_stats = {
                'customer_type_null': enriched_pu['customer_type'].isna().sum() + (enriched_pu['customer_type'] == '').sum() if 'customer_type' in enriched_pu.columns else 0,
                'bike_type_null': enriched_pu['bike_type'].isna().sum() + (enriched_pu['bike_type'] == '').sum() if 'bike_type' in enriched_pu.columns else 0,
                'delivery_date_null': enriched_pu['delivery_date'].isna().sum() if 'delivery_date' in enriched_pu.columns else 0
            }
            
            print(f"   📊 Stats:")
            print(f"      customer_type NULL: {pre_stats['customer_type_null']} → {post_stats['customer_type_null']}")
            print(f"      bike_type NULL: {pre_stats['bike_type_null']} → {post_stats['bike_type_null']}")
            print(f"      delivery_date NULL: {pre_stats['delivery_date_null']} → {post_stats['delivery_date_null']}")
            
            stats['part_usage'] = {'pre': pre_stats, 'post': post_stats}
            
            if not dry_run:
                print("   💾 Uploading to sheet...")
                dl.upload_to_sheet(enriched_pu, SHEET_ID_OUTPUT_REVIEW, WORKSHEET_PART_USAGE)
                print("   ✅ Part Usage updated!")
            else:
                print("   ⏸️ Dry run - skipping upload")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            stats['part_usage'] = {'error': str(e)}
    
    print("\n✨ Enrichment finished!")
    return stats


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Enrich Google Sheets with Asset List lookup")
    parser.add_argument(
        "--sheets",
        type=str,
        nargs='+',
        default=['service_items', 'part_usage'],
        choices=['service_items', 'part_usage'],
        help="Sheets to enrich (default: both)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show stats only, don't update sheets"
    )
    
    args = parser.parse_args()
    
    run_enrichment(sheets=args.sheets, dry_run=args.dry_run)
