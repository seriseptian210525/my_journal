import pandas as pd
import os
import glob
from pathlib import Path
from src.common.config import (
    SHEET_ID_OUTPUT_REVIEW, 
    WORKSHEET_PART_USAGE,
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

    def sync_to_gsheet(self, df: pd.DataFrame):
        """
        Syncs DataFrame to Google Sheet using append-only logic.
        Data is sorted by created_at ASC to maintain chronological order.
        """
        if df.empty:
            print("⚠️ Dataframe is empty, skipping sync.")
            return

        # Ensure required columns exist for deduplication
        missing_keys = [k for k in self.deduplication_keys if k not in df.columns]
        if missing_keys:
            raise ValueError(f"❌ Missing deduplication keys in data: {missing_keys}")
        
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
