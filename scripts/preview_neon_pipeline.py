"""
Preview Pipeline Output - Review data before inserting to Neon.
Exports to CSV for validation of business logic.
"""
import os
import sys
from pathlib import Path
import pandas as pd

# Add project root
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from src.common.data_loader import DataLoader
from src.common.config import (
    SHEET_ID_SERVICE_ITEMS, WORKSHEET_SERVICE_ITEMS,
    SHEET_ID_MAPPINGS, WORKSHEET_MAPPINGS,
    SHEET_ID_ASSET_LIST, WORKSHEET_ASSET,
    SHEET_ID_OUTPUT_REVIEW, WORKSHEET_PART_USAGE
)
from src.pipelines.neon_sync.transformers import (
    standardize_service_items,
    standardize_part_usage,
    explode_rows,
    calculate_warranty_coverage
)


def preview_pipeline(export_csv=True, sample_size=None):
    """Run pipeline without inserting to Neon, output to CSV for review."""
    
    print("🔍 Starting Pipeline Preview (No DB Insert)...")
    
    loader = DataLoader()
    
    # Load auxiliary data
    print("\n📚 Loading Auxiliary Data...")
    asset_df = loader.load_gspread_data(SHEET_ID_ASSET_LIST, WORKSHEET_ASSET)
    print(f"   Asset List: {len(asset_df)} rows")
    
    mapping_df = loader.load_gspread_data(SHEET_ID_MAPPINGS, WORKSHEET_MAPPINGS)
    print(f"   Mappings: {len(mapping_df)} rows")
    
    # --- DIAGNOSTIC: Check Mapping Data ---
    print("\n🔎 DIAGNOSTIC: Mapping Warranty Config Distribution")
    if 'Warranty Type' in mapping_df.columns:
        print(mapping_df['Warranty Type'].value_counts(dropna=False).to_string())
    else:
        print("   ⚠️ 'Warranty Type' column not found in Mappings!")
    
    if 'Periode Garansi' in mapping_df.columns:
        print("\n   Periode Garansi Distribution:")
        print(mapping_df['Periode Garansi'].value_counts(dropna=False).head(10).to_string())
    else:
        print("   ⚠️ 'Periode Garansi' column not found in Mappings!")
    
    if 'Covered For' in mapping_df.columns:
        print("\n   Covered For Distribution:")
        print(mapping_df['Covered For'].value_counts(dropna=False).head(10).to_string())
    
    # --- SERVICE ITEMS ---
    print("\n📦 Processing: Service Items...")
    raw_si = loader.load_gspread_data(SHEET_ID_SERVICE_ITEMS, WORKSHEET_SERVICE_ITEMS)
    si_df = standardize_service_items(raw_si, asset_df=asset_df, mapping_df=mapping_df)
    print(f"   Standardized: {len(si_df)} rows.")
    
    # --- PART USAGE ---
    print("\n📦 Processing: Part Usage...")
    raw_pu = loader.load_gspread_data(SHEET_ID_OUTPUT_REVIEW, WORKSHEET_PART_USAGE)
    pu_df = standardize_part_usage(raw_pu, asset_df=asset_df, mapping_df=mapping_df)
    print(f"   Standardized: {len(pu_df)} rows.")
    
    # --- MERGE & TRANSFORM ---
    print("\n🔄 Merging & Transforming...")
    unified_df = pd.concat([si_df, pu_df], ignore_index=True)
    print(f"   Merged Total: {len(unified_df)} rows.")
    
    # Explode
    unified_df['created_at'] = pd.to_datetime(unified_df['created_at'])
    exploded_df = explode_rows(unified_df)
    print(f"   Post-Explosion Total: {len(exploded_df)} rows.")
    
    # Sort
    exploded_df.sort_values(by=['created_at'], ascending=True, inplace=True)
    
    # --- WARRANTY CALCULATION ---
    print("\n🛡️ Calculating Warranty Coverage...")
    enriched_df = calculate_warranty_coverage(exploded_df, asset_df=asset_df, mapping_df=mapping_df)
    
    # --- DIAGNOSTIC: Why no WARRANTY/INSURANCE? ---
    print("\n🔎 DIAGNOSTIC: Warranty Logic Debug")
    
    # Check warranty_type distribution in enriched data
    if 'warranty_type' in enriched_df.columns:
        print("   warranty_type in enriched data:")
        print(enriched_df['warranty_type'].value_counts(dropna=False).head(10).to_string())
    
    # Check periode_garansi distribution
    if 'periode_garansi' in enriched_df.columns:
        print("\n   periode_garansi in enriched data:")
        print(enriched_df['periode_garansi'].value_counts(dropna=False).head(10).to_string())
    
    # Check customer_category distribution
    if 'customer_category' in enriched_df.columns:
        print("\n   customer_category in enriched data:")
        print(enriched_df['customer_category'].value_counts(dropna=False).to_string())
    
    # Check covered_for distribution
    if 'covered_for' in enriched_df.columns:
        print("\n   covered_for in enriched data:")
        print(enriched_df['covered_for'].value_counts(dropna=False).head(10).to_string())
    
    # Check bulan_ke range
    if 'bulan_ke' in enriched_df.columns:
        print(f"\n   bulan_ke range: {enriched_df['bulan_ke'].min()} to {enriched_df['bulan_ke'].max()}")
    
    # --- FINAL COVERAGE DISTRIBUTION ---
    print("\n📊 Final Warranty Coverage Distribution:")
    print(enriched_df['warranty_coverage'].value_counts().to_string())
    
    # --- SAMPLE: Show rows that SHOULD be WARRANTY but are NOT_COVERED ---
    print("\n🔍 Sample: Rows with WARRANTY type but NOT_COVERED status:")
    warranty_type_rows = enriched_df[enriched_df['warranty_type'].str.upper().str.contains('WARRANTY', na=False)]
    not_covered_warranty = warranty_type_rows[warranty_type_rows['warranty_coverage'] == 'NOT_COVERED']
    if not not_covered_warranty.empty:
        sample = not_covered_warranty[['vehicle_plate', 'sku', 'item_name', 'warranty_type', 'customer_category', 
                                        'covered_for', 'bulan_ke', 'periode_garansi', 'warranty_coverage']].head(10)
        print(sample.to_string())
    else:
        print("   No rows with WARRANTY type found that are NOT_COVERED.")
    
    # --- EXPORT TO CSV ---
    if export_csv:
        output_dir = project_root / 'debug' / 'output'
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Sample or full
        if sample_size:
            export_df = enriched_df.head(sample_size)
            csv_path = output_dir / f'pipeline_preview_sample_{sample_size}.csv'
        else:
            export_df = enriched_df
            csv_path = output_dir / 'pipeline_preview_full.csv'
        
        export_df.to_csv(csv_path, index=False)
        print(f"\n✅ Exported to: {csv_path}")
        print(f"   Rows: {len(export_df)}")
    
    return enriched_df


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Preview pipeline output without DB insert")
    parser.add_argument('--sample', type=int, default=None, help="Sample size for export (default: full)")
    parser.add_argument('--no-export', action='store_true', help="Skip CSV export")
    args = parser.parse_args()
    
    preview_pipeline(export_csv=not args.no_export, sample_size=args.sample)
