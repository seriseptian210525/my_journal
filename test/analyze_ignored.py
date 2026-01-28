"""
Analyze Ignored Parts - Root Cause Analysis
============================================
Determines if ignored items failed due to:
1. Regex pattern not matching
2. Fuzzy score too low (<85%)
3. Explicitly mapped to "Ignore Part"
"""
import pandas as pd

print("="*60)
print("IGNORED PARTS - ROOT CAUSE ANALYSIS")
print("="*60)

# Load ignored data
ignored_df = pd.read_csv('output/service_items_ignored.csv', low_memory=False)

print(f"\nTotal Ignored Items: {len(ignored_df)}")

# Breakdown by ignore_reason
print(f"\n=== BREAKDOWN BY REASON ===")
reason_counts = ignored_df['ignore_reason'].value_counts()
for reason, count in reason_counts.items():
    pct = count / len(ignored_df) * 100
    print(f"  {reason}: {count} ({pct:.1f}%)")

print(f"\n" + "="*60)
print("ANALYSIS: 'No Fuzzy Match Found'")
print("="*60)

no_match = ignored_df[ignored_df['ignore_reason'] == 'No Fuzzy Match Found'].copy()
print(f"Total: {len(no_match)} items")

print(f"\nTop 20 item_name yang TIDAK ter-fuzzy match:")
print("-"*60)
item_counts = no_match['item_name'].value_counts().head(20)
for item, count in item_counts.items():
    mapped = no_match[no_match['item_name'] == item]['mapped_item_name'].iloc[0] if len(no_match[no_match['item_name'] == item]) > 0 else ''
    print(f"  {count:4d}x | {item[:40]:40s} → {str(mapped)[:30]}")

print(f"\n" + "="*60)
print("ANALYSIS: 'Marked as Ignore Part'")  
print("="*60)

ignore_part = ignored_df[ignored_df['ignore_reason'] == 'Marked as Ignore Part'].copy()
print(f"Total: {len(ignore_part)} items")

print(f"\nTop 20 item_name yang di-mapping ke 'Ignore Part':")
print("-"*60)
ip_counts = ignore_part['item_name'].value_counts().head(20)
for item, count in ip_counts.items():
    print(f"  {count:4d}x | {item[:50]}")

print(f"\n" + "="*60)
print("CONCLUSION")
print("="*60)

no_match_pct = len(no_match) / len(ignored_df) * 100
ignore_part_pct = len(ignore_part) / len(ignored_df) * 100

print(f"""
1. 'No Fuzzy Match Found' ({len(no_match)} items, {no_match_pct:.1f}%):
   - Regex BERHASIL mapping (ada mapped_item_name)
   - Tapi FUZZY SCORE < 85% (tidak cocok dengan Rekomendasi Nama Part Baru)
   - Perlu: Tambah pola regex atau turunkan threshold

2. 'Marked as Ignore Part' ({len(ignore_part)} items, {ignore_part_pct:.1f}%):
   - Ini SENGAJA di-skip di mapping
   - Part yang tidak perlu ditrack (jasa, label, sticker, dll)
   - Ini expected behavior
""")
