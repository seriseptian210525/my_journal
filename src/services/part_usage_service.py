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

