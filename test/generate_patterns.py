"""
Generate Regex Patterns for Top Failed Fuzzy Items
===================================================
Creates CSV with suggested patterns to add to Mappings sheet
"""
import pandas as pd
import re

print("="*60)
print("GENERATING REGEX PATTERNS FOR TOP FAILED ITEMS")
print("="*60)

# Load ignored data
ignored_df = pd.read_csv('output/service_items_ignored.csv', low_memory=False)

# Filter only 'No Fuzzy Match Found'
no_match = ignored_df[ignored_df['ignore_reason'] == 'No Fuzzy Match Found'].copy()
print(f"Total 'No Fuzzy Match Found': {len(no_match)}")

# Get top 20 by frequency
top_items = no_match['item_name'].value_counts().head(20)

def generate_regex(item_name):
    """Generate regex pattern from item name"""
    # Clean and escape special characters
    pattern = item_name.strip()
    # Convert to case-insensitive
    pattern = re.sub(r'\s+', r'\\s*', pattern)  # Flexible whitespace
    pattern = re.sub(r'\[|\]|\(|\)', '', pattern)  # Remove brackets
    pattern = f"(?i){pattern}"
    return pattern

# Generate patterns
patterns = []
for item_name, count in top_items.items():
    # Get the mapped_item_name for reference
    mapped = no_match[no_match['item_name'] == item_name]['mapped_item_name'].iloc[0]
    
    pattern = {
        'item_name (original)': item_name,
        'count': count,
        'mapped_item_name': mapped,
        'Pola (Regex)': generate_regex(item_name),
        'Rekomendasi Nama Part Baru': mapped,  # Use mapped as recommendation
        'New SKU': '',  # To be filled manually
        'ERP Product ID': '',  # To be filled manually
        'Base Price': ''  # To be filled manually
    }
    patterns.append(pattern)

# Save to CSV
output_path = 'output/suggested_regex_patterns.csv'
patterns_df = pd.DataFrame(patterns)
patterns_df.to_csv(output_path, index=False)

print(f"\n✅ Generated {len(patterns)} patterns → {output_path}")
print("\nSuggested patterns:")
print("-"*80)
for _, row in patterns_df.head(10).iterrows():
    print(f"  {row['count']:4d}x | {row['item_name (original)'][:35]:35s} | {row['Pola (Regex)'][:30]}")

print(f"""

NEXT STEPS:
1. Open '{output_path}'
2. Fill in 'New SKU', 'ERP Product ID', 'Base Price'
3. Copy rows to Google Sheets Mappings
4. Or just run with lowered threshold (80%) first to see improvement
""")
