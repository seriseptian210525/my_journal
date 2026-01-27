import pandas as pd
import numpy as np

# Load data
print("Loading data...")
full_df = pd.read_csv('output/service_items_full.csv', low_memory=False)

print(f"\n=== DETAILED ROW ANALYSIS ===")
print(f"Total rows after pipeline: {len(full_df)}")

# Check unique combinations
if 'order_id' in full_df.columns and 'Product Name' in full_df.columns:
    unique_by_product = full_df.drop_duplicates(subset=['order_id', 'Product Name'])
    print(f"After dedup (order_id + Product Name): {len(unique_by_product)}")

# Breakdown by data quality
print(f"\n=== DATA QUALITY BREAKDOWN ===")

# Has Product Name
has_product_name = full_df['Product Name'].notna() & (full_df['Product Name'].astype(str).str.strip() != '')
print(f"Has Product Name: {has_product_name.sum()}")
print(f"Missing Product Name: {(~has_product_name).sum()}")

# Has ERP Product ID
has_erp = full_df['ERP Product ID'].notna() & (full_df['ERP Product ID'].astype(str).str.strip() != '') & (full_df['ERP Product ID'].astype(str) != '0')
print(f"\nHas ERP Product ID: {has_erp.sum()}")
print(f"Missing ERP Product ID: {(~has_erp).sum()}")

# Has Both (valid for output)
valid_for_output = has_product_name & has_erp
print(f"\nValid for output (has both): {valid_for_output.sum()}")
print(f"Invalid for output (ignored): {(~valid_for_output).sum()}")

# After dedup of valid rows
valid_df = full_df[valid_for_output]
if 'order_id' in valid_df.columns and 'Product Name' in valid_df.columns:
    valid_unique = valid_df.drop_duplicates(subset=['order_id', 'Product Name'])
    print(f"Valid unique (final output): {len(valid_unique)}")

# Analyze ignored items
ignored_df = full_df[~valid_for_output].copy()
print(f"\n=== IGNORED ITEMS ANALYSIS ({len(ignored_df)} rows) ===")

# Show distribution of mapped_item_name in ignored
print(f"\nTop 30 mapped_item_name in ignored parts:")
print(ignored_df['mapped_item_name'].value_counts().head(30))

# Show original item_name
print(f"\nTop 30 original item_name in ignored parts:")
print(ignored_df['item_name'].value_counts().head(30))

# Save detailed ignored report
print(f"\n=== SAVING DETAILED IGNORED REPORT ===")
ignored_cols = ['order_id', 'vehicle_license_plate', 'item_name', 'mapped_item_name', 
                'Rekomendasi Nama Part Baru', 'Product Name', 'ERP Product ID',
                'created_at', 'service_location_name', 'bike_type']
available_cols = [c for c in ignored_cols if c in ignored_df.columns]
ignored_report = ignored_df[available_cols].drop_duplicates()
ignored_report.to_csv('output/service_items_ignored_detailed.csv', index=False)
print(f"Saved {len(ignored_report)} unique ignored items to output/service_items_ignored_detailed.csv")
