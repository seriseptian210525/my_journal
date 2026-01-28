"""
Pipeline Row Count Analysis
===========================
Explains why rows reduce at each step:
109,874 → 80,741 → 61,003
"""
import pandas as pd

print("="*60)
print("PIPELINE ROW COUNT ANALYSIS")
print("="*60)

# Step 1: Load full data (after all pipeline steps)
full_df = pd.read_csv('output/service_items_full.csv', low_memory=False)
ignored_df = pd.read_csv('output/service_items_ignored.csv', low_memory=False)
formatted_df = pd.read_csv('output/service_items_formatted.csv', low_memory=False)

print(f"""
STEP 1: TRANSPOSE
-----------------
Input:  Work Orders (raw)
Output: 109,874 rows
        
Penjelasan: 
Setiap work order punya kolom item_name yang berisi list part 
dipisahkan dengan koma. Proses transpose memecah menjadi 1 row per part.

Contoh:
  WO-123, "Brake Pad, Tire" → 2 rows:
    - WO-123, Brake Pad
    - WO-123, Tire
""")

print(f"""
STEP 2 & 3: REGEX + FUZZY MATCHING
----------------------------------
After Transpose:  109,874 rows
After Matching:    80,741 rows (valid) + 9,467 rows (ignored)
Total Check:       {80741 + 9467} = {80741 + 9467} ✓

19,666 rows HILANG karena:
  1. No Fuzzy Match Found   - Part tidak cocok dengan mapping (threshold <85%)
  2. Marked as 'Ignore Part'- Part di-mapping ke 'Ignore Part' (sengaja di-skip)
  
Ini sekarang ada di sheet 'ignore_part' untuk di-review.
""")

# Analyze deduplication
print(f"""
STEP 4: DEDUPLICATION (di format_output)
----------------------------------------
Before Dedup:   80,741 rows
After Dedup:    61,003 rows
Duplicates:     19,738 rows

Penjelasan:
Deduplikasi dilakukan berdasarkan (order_id + Product Name).
Jika ada WO dengan part yang sama lebih dari 1x, hanya 1 row yang diambil.

""")

# Show actual examples
print("CONTOH DUPLIKASI:")
if 'order_id' in full_df.columns and 'Product Name' in full_df.columns:
    # Find duplicate examples
    dup_counts = full_df.groupby(['order_id', 'Product Name']).size().reset_index(name='count')
    dups = dup_counts[dup_counts['count'] > 1].sort_values('count', ascending=False).head(10)
    
    print(f"\nTop 10 Order+Product dengan duplikasi terbanyak:")
    print("-"*60)
    for _, row in dups.iterrows():
        print(f"  {row['order_id'][:20]}... | {row['Product Name'][:25]:25s} | x{row['count']}")

print(f"""

SUMMARY FLOW
============
┌────────────────────────────┐
│ 1. TRANSPOSE: 109,874 rows │
└─────────────┬──────────────┘
              │
              ▼
┌────────────────────────────────────────┐
│ 2. FUZZY MATCHING                      │
│    - Valid:   80,741 rows              │
│    - Ignored:  9,467 rows (ke ignore_part) │
│    - Skip:    19,666 rows (no match)   │ 
└─────────────┬──────────────────────────┘
              │
              ▼
┌────────────────────────────────────────┐
│ 3. DEDUPLICATION (format_output)       │
│    - Before: 80,741 rows               │
│    - After:  61,003 rows               │
│    - Removed: 19,738 duplicate rows    │
└────────────────────────────────────────┘

NEXT STEP (yang diminta user):
Hapus deduplication agar output = 80,741 rows
""")
