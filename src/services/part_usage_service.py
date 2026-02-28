import pandas as pd
import os
import glob
from pathlib import Path
from src.common.config import (
    SHEET_ID_OUTPUT_REVIEW, 
    WORKSHEET_PART_USAGE,
    SHEET_ID_ASSET_LIST,
    WORKSHEET_ASSET,
    BASE_DIR
)
from src.common.data_loader import DataLoader
from src.common.utils import ServiceUtils

class PartUsageService:
    def __init__(self):
        self.data_loader = DataLoader()
        self.sheet_id = SHEET_ID_OUTPUT_REVIEW
        self.worksheet_name = WORKSHEET_PART_USAGE
        
        # Deduplication key based on user request (order_number)
        self.deduplication_keys = ['order_number']

    def consolidate_local_files(self, source_dir: str = "output/part_usage") -> pd.DataFrame:
        """
        Reads all CSV files from source_dir and combines them.
        """
        source_path = Path(BASE_DIR) / source_dir
        
        # Find all CSV files
        csv_files = glob.glob(str(source_path / "*.csv"))
        
        if not csv_files:
            print(f"⚠️ No CSV files found in {source_path}")
            return pd.DataFrame()
            
        print(f"📦 Found {len(csv_files)} files in {source_dir}")
        
        dfs = []
        for file in csv_files:
            try:
                print(f"   Reading {os.path.basename(file)}...")
                df = pd.read_csv(file)
                dfs.append(df)
            except Exception as e:
                print(f"❌ Error reading {file}: {e}")
                
        if not dfs:
            return pd.DataFrame()
            
        consolidated_df = pd.concat(dfs, ignore_index=True)
        print(f"✅ Consolidated {len(consolidated_df)} rows total.")
        
        return consolidated_df

    def _enrich_from_asset_list(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Enrich DataFrame with customer_type, bike_type, delivery_date from Asset List.
        """
        if df.empty:
            return df
        
        # Load Asset List
        try:
            asset_df = self.data_loader.load_gspread_data(SHEET_ID_ASSET_LIST, WORKSHEET_ASSET)
            if asset_df.empty:
                print("   ⚠️ Asset List is empty, skipping enrichment")
                return df
        except Exception as e:
            print(f"   ⚠️ Could not load Asset List: {e}")
            return df
        
        print(f"   📚 Enriching from Asset List ({len(asset_df)} assets)...")
        
        out = df.copy()
        
        # Find plate column - try common names
        plate_col = None
        for col in ['vehicle_license_plate', 'Vehicle License Plate', 'vehicle_plate', 'plat_nomor']:
            if col in out.columns:
                plate_col = col
                break
        
        if not plate_col:
            print("   ⚠️ No plate column found, skipping enrichment")
            return df
        
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
        
        # Update/add columns
        if 'customer_type' not in merged.columns:
            merged['customer_type'] = ''
        merged['customer_type'] = merged.apply(
            lambda r: r['_asset_customer_type'] if (pd.isna(r.get('customer_type')) or str(r.get('customer_type', '')).strip() in ['', 'nan', 'None']) else r.get('customer_type'),
            axis=1
        )
        
        if 'bike_type' not in merged.columns:
            merged['bike_type'] = ''
        merged['bike_type'] = merged.apply(
            lambda r: r['_asset_model'] if (pd.isna(r.get('bike_type')) or str(r.get('bike_type', '')).strip() in ['', 'nan', 'None']) else r.get('bike_type'),
            axis=1
        )
        
        if 'delivery_date' not in merged.columns:
            merged['delivery_date'] = pd.NaT
        merged['delivery_date'] = merged.apply(
            lambda r: r['_asset_delivery_date'] if pd.isna(r.get('delivery_date')) else r.get('delivery_date'),
            axis=1
        )
        
        # Cleanup intermediary join columns
        merged = merged.drop(columns=['_join_plate', '_asset_customer_type', '_asset_model', '_asset_delivery_date'], errors='ignore')
        
        # --- ROBUST SAFETY NET (Phase 12) ---
        print("   🛡️ Applying Robust Safety Net for Missing Data...")
        
        # 1. Forward Fill within the same plate (if history exists in this batch)
        if 'created_at' in merged.columns:
            merged['created_at_dt'] = pd.to_datetime(merged['created_at'], errors='coerce')
            merged = merged.sort_values(['vehicle_plate', 'created_at_dt'])
            
            fill_cols = ['delivery_date', 'customer_type', 'bike_type']
            for col in fill_cols:
                if col in merged.columns:
                    missing_before = merged[col].isna().sum() + (merged[col] == '').sum() if merged[col].dtype == 'object' else merged[col].isna().sum()
                    if missing_before > 0:
                        merged[col] = merged.groupby('vehicle_plate')[col].transform(lambda x: x.ffill().bfill())

        # 2. String Fallback ('UNKNOWN') & Date Repair (using 'created_at')
        merged['customer_type'] = merged['customer_type'].replace(['', 'nan', 'None'], pd.NA).fillna('UNKNOWN')
        merged['bike_type'] = merged['bike_type'].replace(['', 'nan', 'None'], pd.NA).fillna('UNKNOWN')
        
        if 'created_at' in merged.columns and 'delivery_date' in merged.columns:
            merged['delivery_date'] = merged['delivery_date'].fillna(merged['created_at'])
            
            # Robust Date Formatting: Avoid to_datetime array mixing bugs by taking first 10 chars (YYYY-MM-DD)
            merged['delivery_date'] = merged['delivery_date'].astype(str).str.strip().str[:10]
            merged['delivery_date'] = merged['delivery_date'].replace(['nan', 'NaT', 'None', '<NA>'], '')

        # Re-sort to natural index order to preserve original upload chronology
        merged = merged.sort_index()
        # ------------------------------------
        
        # Stats
        enriched_count = merged['customer_type'].notna().sum()
        print(f"   ✅ Enriched {enriched_count}/{len(merged)} rows")
        
        return merged

    def sync_to_gsheet(self, df: pd.DataFrame):
        """
        Syncs DataFrame to Google Sheet using append-only logic.
        Data is enriched with Asset List lookup and sorted by created_at ASC.
        """
        if df.empty:
            print("⚠️ Dataframe is empty, skipping sync.")
            return

        # Ensure required columns exist for deduplication
        missing_keys = [k for k in self.deduplication_keys if k not in df.columns]
        if missing_keys:
            raise ValueError(f"❌ Missing deduplication keys in data: {missing_keys}")
        
        # ENRICHMENT: Add customer_type, bike_type, delivery_date from Asset List
        df = self._enrich_from_asset_list(df)
        
        # Sort by created_at ASC to maintain chronological order
        if 'created_at' in df.columns:
            df = df.copy()
            df['created_at'] = pd.to_datetime(df['created_at'], errors='coerce')
            df = df.sort_values(by='created_at', ascending=True)
            print(f"   📅 Sorted {len(df)} rows by created_at ASC")

        # Use DataLoader's robust append capability
        self.data_loader.append_to_sheet(
            df=df,
            sheet_id=self.sheet_id,
            worksheet_name=self.worksheet_name,
            key_columns=self.deduplication_keys
        )

    def backfill_part_usage_sheet(self) -> dict:
        """
        Reads the part_usage GSheet, backfills empty [customer_type, bike_type, delivery_date]
        using Asset List lookup + ffill/bfill + fallback, then writes changes back.
        
        Returns stats dict with counts of cells fixed.
        """
        import gspread
        
        stats = {'customer_type': 0, 'bike_type': 0, 'delivery_date': 0, 'total_rows_checked': 0}
        target_cols = ['customer_type', 'bike_type', 'delivery_date']
        
        print("🔍 Backfill Part Usage: Reading sheet...")
        
        try:
            df = self.data_loader.load_gspread_data(self.sheet_id, self.worksheet_name)
        except Exception as e:
            print(f"   ❌ Failed to load part_usage sheet: {e}")
            return stats
        
        if df.empty:
            print("   ⚠️ Part Usage sheet is empty.")
            return stats
        
        stats['total_rows_checked'] = len(df)
        
        # Check for missing values
        def is_empty(val):
            return pd.isna(val) or str(val).strip().lower() in ['', 'nan', 'none', 'nat', '<na>', 'unknown']
        
        missing_mask = pd.DataFrame(False, index=df.index, columns=target_cols)
        for col in target_cols:
            if col in df.columns:
                missing_mask[col] = df[col].apply(is_empty)
        
        total_missing = missing_mask.any(axis=1).sum()
        if total_missing == 0:
            print("   ✅ No missing values found. Backfill not needed.")
            return stats
        
        # Save original missing mask for batch update (only write cells that were originally empty)
        original_missing = missing_mask.copy()
        
        print(f"   ⚠️ Found {total_missing} rows with missing data. Backfilling...")
        
        # Detect plate column name
        plate_col = None
        for col_candidate in ['vehicle_license_plate', 'Vehicle License Plate', 'vehicle_plate', 'plat_nomor']:
            if col_candidate in df.columns:
                plate_col = col_candidate
                break
        
        if not plate_col:
            print("   ⚠️ No plate column found in part_usage sheet, skipping Asset List lookup")
        
        # --- Backfill Logic (reuse _enrich_from_asset_list approach) ---
        
        # 1. Load Asset List for lookup
        try:
            asset_df = self.data_loader.load_gspread_data(SHEET_ID_ASSET_LIST, WORKSHEET_ASSET)
        except Exception:
            asset_df = pd.DataFrame()
        
        if not asset_df.empty:
            # Build lookup dict: plate -> {customer_type, bike_type, delivery_date}
            asset_clean = asset_df.copy()
            asset_clean['_plate'] = asset_clean['Plat Nomor'].astype(str).str.strip().str.upper().str.replace(' ', '')
            
            delivery_col = None
            for col in ['Delivery - Outbone', 'Delivery Date', 'delivery_date']:
                if col in asset_clean.columns:
                    delivery_col = col
                    break
            
            lookup = {}
            for _, row in asset_clean.iterrows():
                plate = row['_plate']
                if plate not in lookup:
                    lookup[plate] = {
                        'customer_type': str(row.get('Tempat Sewa Unit', '')).strip(),
                        'bike_type': str(row.get('Model', '')).strip(),
                        'delivery_date': str(row.get(delivery_col, '')).strip() if delivery_col else ''
                    }
            
            # Apply Asset List lookup to empty cells
            if plate_col:
                for idx in df.index:
                    plate = str(df.at[idx, plate_col]).strip().upper().replace(' ', '')
                    if plate in lookup:
                        for col in target_cols:
                            if col in df.columns and missing_mask.at[idx, col]:
                                val = lookup[plate].get(col, '')
                                if val and val.lower() not in ['', 'nan', 'none', 'nat']:
                                    df.at[idx, col] = val
                                    missing_mask.at[idx, col] = False
        
        # 2. ffill + bfill per plate
        if plate_col:
            for col in target_cols:
                if col in df.columns and missing_mask[col].any():
                    df[col] = df.groupby(plate_col)[col].transform(
                        lambda x: x.replace(['', 'nan', 'None', 'NaT'], pd.NA).ffill().bfill()
                    )
                    # Re-check
                    missing_mask[col] = df[col].apply(is_empty)
        
        # 3. Fallback: UNKNOWN for strings, created_at for delivery_date
        for col in ['customer_type', 'bike_type']:
            if col in df.columns:
                still_empty = missing_mask[col]
                if still_empty.any():
                    df.loc[still_empty, col] = 'UNKNOWN'
                    missing_mask.loc[still_empty, col] = False
        
        if 'delivery_date' in df.columns and 'created_at' in df.columns:
            still_empty = missing_mask['delivery_date']
            if still_empty.any():
                df.loc[still_empty, 'delivery_date'] = df.loc[still_empty, 'created_at']
                missing_mask.loc[still_empty, 'delivery_date'] = False
        
        # --- Write changes back to GSheet via batch update ---
        print("   📤 Writing backfilled data to Google Sheet...")
        
        try:
            sheet = self.data_loader.client.open_by_key(self.sheet_id)
            worksheet = sheet.worksheet(self.worksheet_name)
            headers = worksheet.row_values(1)
            
            # Build batch update cells — only update cells that were originally empty
            updates = []
            for col in target_cols:
                if col not in headers:
                    continue
                col_idx = headers.index(col) + 1  # 1-indexed for gspread
                
                for df_row_idx in df.index:
                    if not original_missing.at[df_row_idx, col]:
                        continue  # Skip cells that were NOT originally empty
                    sheet_row = int(df_row_idx) + 2  # +2: header=row1, DataFrame=0-indexed
                    raw_val = df.at[df_row_idx, col]
                    # Format delivery_date as YYYY-MM-DD
                    if col == 'delivery_date' and pd.notna(raw_val):
                        try:
                            new_val = pd.to_datetime(raw_val, errors='coerce').strftime('%Y-%m-%d')
                        except Exception:
                            new_val = str(raw_val).strip()[:10]
                    else:
                        new_val = str(raw_val).strip() if pd.notna(raw_val) else ''
                    if new_val and new_val.lower() not in ['nan', 'none', 'nat', '<na>']:
                        updates.append(gspread.Cell(row=sheet_row, col=col_idx, value=new_val))
                        stats[col] += 1
            
            if updates:
                # Batch update in chunks of 5000
                chunk_size = 5000
                for i in range(0, len(updates), chunk_size):
                    chunk = updates[i:i+chunk_size]
                    worksheet.update_cells(chunk)
                    print(f"   ✅ Batch {i//chunk_size + 1}: Updated {len(chunk)} cells")
            
            print(f"   ✅ Backfill complete: customer_type={stats['customer_type']}, bike_type={stats['bike_type']}, delivery_date={stats['delivery_date']}")
            
        except Exception as e:
            print(f"   ❌ Batch update failed: {e}")
        
        return stats
