"""
Neon Sync Service - Triggered from Streamlit UI
Supports smart incremental sync with Pergantian Ke offset.
"""
import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime

# Add project root
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent
sys.path.append(str(project_root))

from src.pipelines.neon_sync.loader import NeonLoader
from src.pipelines.neon_sync.transformers import (
    standardize_service_items,
    standardize_part_usage,
    explode_rows,
    calculate_warranty_coverage,
    normalize_odometer
)
from src.common.data_loader import DataLoader
from src.common.config import (
    SHEET_ID_SERVICE_ITEMS, WORKSHEET_SERVICE_ITEMS,
    SHEET_ID_MAPPINGS, WORKSHEET_MAPPINGS,
    SHEET_ID_ASSET_LIST, WORKSHEET_ASSET,
    SHEET_ID_OUTPUT_REVIEW, WORKSHEET_PART_USAGE
)


class NeonSyncService:
    """
    Service for syncing data to Neon from Streamlit UI.
    Supports incremental sync with smart Pergantian Ke calculation.
    """
    
    def __init__(self):
        self.loader = NeonLoader()
        self._data_loader = None  # Lazy load
        self._cached_df = None # RAM cache for the drive export
        self.gdrive_folder_id = os.environ.get("GDRIVE_OUTPUT_FOLDER_ID", "1lLb2vjbsccIMvL6LCFdvPxYwroIkMr2S")
        self.gdrive_filename = "unified_part_logs_latest.csv"
    
    @property
    def data_loader(self):
        """Lazy load DataLoader only when needed."""
        if self._data_loader is None:
            self._data_loader = DataLoader()
        return self._data_loader
        
    def _get_drive_dataframe(self):
        """Fetches the latest CSV, caches it in memory.
        Priority: 1) RAM cache  2) Local file  3) Google Drive download
        """
        if self._cached_df is not None:
            return self._cached_df
        
        # Try local file first (faster, guaranteed same as last pipeline run)
        local_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            'output', 'unified_part_logs_latest.csv'
        )
        
        try:
            if os.path.exists(local_path):
                print(f"📂 Loading data from local cache: {local_path}")
                self._cached_df = pd.read_csv(local_path, low_memory=False)
            else:
                print("📥 Local cache not found, fetching from Google Drive...")
                self._cached_df = self.data_loader.load_csv_from_drive(self.gdrive_folder_id, self.gdrive_filename)
            
            # Ensure critical datetime columns
            if 'created_at' in self._cached_df.columns:
                self._cached_df['created_at'] = pd.to_datetime(self._cached_df['created_at'], errors='coerce')
            if 'delivery_date' in self._cached_df.columns:
                self._cached_df['delivery_date'] = pd.to_datetime(self._cached_df['delivery_date'], errors='coerce')
                
            return self._cached_df
        except Exception as e:
            print(f"❌ Failed to load data: {e}")
            return pd.DataFrame()
    
    def clear_cache(self):
        """Force clear the in-memory cached DataFrame.
        Call this after Refresh Cloud Data to ensure Streamlit reads fresh data.
        """
        self._cached_df = None
        print("🧹 Cache cleared. Next data request will reload from disk/Drive.")

    def get_max_total_pk(self) -> pd.DataFrame:
        """
        Get MAX pergantian_ke_total per (vehicle_plate, sku) from Neon.
        """
        query = """
        SELECT vehicle_plate, sku, MAX(pergantian_ke_total) as max_pk_total
        FROM unified_part_logs
        GROUP BY vehicle_plate, sku
        """
        return self.loader.fetch_df(query)

    def get_max_yearly_pk(self) -> pd.DataFrame:
        """
        Get MAX pergantian_ke_yearly per (vehicle_plate, sku, year_cycle) from Neon.
        """
        query = """
        SELECT vehicle_plate, sku, year_cycle, MAX(pergantian_ke_yearly) as max_pk_yearly
        FROM unified_part_logs
        GROUP BY vehicle_plate, sku, year_cycle
        """
        return self.loader.fetch_df(query)
    
    def get_max_created_at(self) -> datetime:
        """Get the latest created_at timestamp from Neon."""
        result = self.loader.get_max_created_at()
        return result
    
    def run_incremental_sync(self) -> dict:
        """
        Run incremental sync with smart Pergantian Ke calculation.
        Loads ALL source data for proper forward-fill, then inserts only new rows.
        Returns stats about the sync operation.
        """
        stats = {
            'status': 'started',
            'service_items_new': 0,
            'part_usage_new': 0,
            'total_inserted': 0,
            'timestamp': datetime.now()
        }
        
        try:
            # --- PER-SOURCE TIMESTAMP TRACKING ---
            # Get last sync timestamp for EACH source independently
            max_date_si = self.loader.get_max_created_at_by_source('Apps')
            max_date_pu = self.loader.get_max_created_at_by_source('Part Usage Sheet')
            
            if max_date_si:
                max_date_filter_si = pd.to_datetime(max_date_si).tz_localize(None)
            else:
                max_date_filter_si = None
                
            if max_date_pu:
                max_date_filter_pu = pd.to_datetime(max_date_pu).tz_localize(None)
            else:
                max_date_filter_pu = None
            
            # Load auxiliary data
            asset_df = self.data_loader.load_gspread_data(SHEET_ID_ASSET_LIST, WORKSHEET_ASSET)
            mapping_df = self.data_loader.load_gspread_data(SHEET_ID_MAPPINGS, WORKSHEET_MAPPINGS)
            
            # --- LOAD ALL SOURCE DATA (for proper forward-fill) ---
            print("   📥 Loading ALL source data for forward-fill...")
            raw_si_all = self.data_loader.load_gspread_data(SHEET_ID_SERVICE_ITEMS, WORKSHEET_SERVICE_ITEMS)
            raw_pu_all = self.data_loader.load_gspread_data(SHEET_ID_OUTPUT_REVIEW, WORKSHEET_PART_USAGE)
            
            # Standardize ALL data
            si_all = standardize_service_items(raw_si_all, asset_df=asset_df, mapping_df=mapping_df) if not raw_si_all.empty else pd.DataFrame()
            pu_all = standardize_part_usage(raw_pu_all, asset_df=asset_df, mapping_df=mapping_df) if not raw_pu_all.empty else pd.DataFrame()
            
            # Merge ALL data
            all_unified = pd.concat([si_all, pu_all], ignore_index=True)
            if all_unified.empty:
                stats['status'] = 'no_source_data'
                return stats
            
            # --- STEP 2: EXCLUDE TEST/INVALID PLATES ---
            test_plates = [
                'B 1234 XXX', 'B 3252 WWD', 'B 4086 SWF', 'B 4921 SVO', 'B 5050 BCA',
                'B 9999 BLU', 'B 9999 GRE', 'EL 0015 H3', 'EL 1234 MKT'
            ]
            all_unified = all_unified[~all_unified['vehicle_plate'].isin(test_plates)]
            
            # --- STEP 3: FORWARD FILL ON ALL DATA ---
            all_unified['created_at'] = pd.to_datetime(all_unified['created_at'], errors='coerce')
            all_unified = all_unified.sort_values(['vehicle_plate', 'created_at'])
            
            fill_cols = ['delivery_date', 'customer_type', 'bike_type']
            stats['forward_filled'] = {}
            for col in fill_cols:
                if col in all_unified.columns:
                    missing_before = all_unified[col].isna().sum()
                    all_unified[col] = all_unified.groupby('vehicle_plate')[col].transform(
                        lambda x: x.ffill().bfill()
                    )
                    missing_after = all_unified[col].isna().sum()
                    stats['forward_filled'][col] = missing_before - missing_after
            
            # --- STEP 3b: BACKFILL FROM NEON EXISTING DATA ---
            # For plates with missing data, lookup from existing Neon records
            stats['neon_backfilled'] = {}
            missing_plates = all_unified[
                (all_unified['customer_type'].isna() | (all_unified['customer_type'] == '') | (all_unified['customer_type'] == 'nan')) |
                (all_unified['bike_type'].isna() | (all_unified['bike_type'] == '') | (all_unified['bike_type'] == 'nan'))
            ]['vehicle_plate'].unique()
            
            if len(missing_plates) > 0:
                print(f"   🔍 Looking up {len(missing_plates)} plates from Neon...")
                # Query Neon for existing data on these plates
                plates_list = "', '".join([str(p).replace("'", "''") for p in missing_plates[:500]])  # Limit to 500 for safety
                neon_lookup = self.loader.fetch_df(f"""
                    SELECT DISTINCT ON (vehicle_plate) 
                        vehicle_plate, customer_type, bike_type, delivery_date
                    FROM unified_part_logs
                    WHERE vehicle_plate IN ('{plates_list}')
                        AND (customer_type IS NOT NULL AND customer_type != '' AND customer_type != 'nan')
                    ORDER BY vehicle_plate, created_at DESC
                """)
                
                if not neon_lookup.empty:
                    # Create lookup dict
                    neon_dict = neon_lookup.set_index('vehicle_plate').to_dict('index')
                    
                    for col in fill_cols:
                        if col in all_unified.columns:
                            missing_before = (all_unified[col].isna() | (all_unified[col] == '') | (all_unified[col] == 'nan')).sum()
                            
                            # Fill from Neon lookup
                            def fill_from_neon(row):
                                if pd.isna(row[col]) or row[col] in ['', 'nan', 'None']:
                                    plate = row['vehicle_plate']
                                    if plate in neon_dict and col in neon_dict[plate]:
                                        neon_val = neon_dict[plate][col]
                                        if pd.notna(neon_val) and neon_val not in ['', 'nan', 'None']:
                                            return neon_val
                                return row[col]
                            
                            all_unified[col] = all_unified.apply(fill_from_neon, axis=1)
                            missing_after = (all_unified[col].isna() | (all_unified[col] == '') | (all_unified[col] == 'nan')).sum()
                            stats['neon_backfilled'][col] = missing_before - missing_after
                    
                    print(f"   ✅ Neon backfill: {stats['neon_backfilled']}")
            
            # --- STEP 4: FIX INCONSISTENT CUSTOMER_TYPE ---
            # Rule: L-prefix plate + H1 model = GEL
            if 'customer_type' in all_unified.columns and 'bike_type' in all_unified.columns:
                l_prefix_h1_mask = (
                    all_unified['vehicle_plate'].astype(str).str.startswith('L ') & 
                    (all_unified['bike_type'].astype(str).str.upper() == 'H1')
                )
                stats['customer_type_fixed'] = (all_unified.loc[l_prefix_h1_mask, 'customer_type'] != 'GEL').sum()
                all_unified.loc[l_prefix_h1_mask, 'customer_type'] = 'GEL'
            
            # --- FILTER TO NEW DATA ONLY ---
            # Now filter to rows that are newer than max_date per source
            print("   🔍 Filtering to new data only...")
            
            # Tag source
            if 'source_system' not in all_unified.columns:
                all_unified['source_system'] = 'unknown'
            
            # Filter: SI new + PU new
            si_mask = all_unified['source_system'].str.lower().str.contains('service|apps|item', na=False)
            pu_mask = all_unified['source_system'].str.lower().str.contains('part|usage', na=False)
            
            new_rows = pd.DataFrame()
            
            if max_date_filter_si is not None:
                si_new = all_unified[si_mask & (all_unified['created_at'] > max_date_filter_si)]
                stats['service_items_new'] = len(si_new)
                new_rows = pd.concat([new_rows, si_new], ignore_index=True)
            else:
                # No existing SI data, take all SI
                si_new = all_unified[si_mask]
                stats['service_items_new'] = len(si_new)
                new_rows = pd.concat([new_rows, si_new], ignore_index=True)
            
            if max_date_filter_pu is not None:
                pu_new = all_unified[pu_mask & (all_unified['created_at'] > max_date_filter_pu)]
                stats['part_usage_new'] = len(pu_new)
                new_rows = pd.concat([new_rows, pu_new], ignore_index=True)
            else:
                # No existing PU data, take all PU
                pu_new = all_unified[pu_mask]
                stats['part_usage_new'] = len(pu_new)
                new_rows = pd.concat([new_rows, pu_new], ignore_index=True)
            
            # Check if we have new data
            if new_rows.empty:
                stats['status'] = 'no_new_data'
                stats['message'] = 'All data already synced'
                return stats
            
            unified_df = new_rows.copy()
            stats['test_plates_excluded'] = 0  # Already excluded above

            # --- DEDUPLICATION (CROSS-SOURCE) BEFORE EXPLODE ---
            # Priority: WO- prefix (from Part Usage) is preferred over non-WO (Service Items)
            
            # Step 1: Detect WO- prefix (from Part Usage) - these get priority
            unified_df['has_wo_prefix'] = unified_df['order_number'].astype(str).str.contains('WO-', case=False, na=False)
            
            # Step 2: Strict normalization for dedup keys
            unified_df['dedup_plate'] = unified_df['vehicle_plate'].astype(str).str.strip().str.upper()
            unified_df['dedup_sku'] = unified_df['sku'].astype(str).str.strip().str.upper()
            unified_df['dedup_loc'] = unified_df['service_location_name'].astype(str).str.strip().str.upper()
            unified_df['dedup_date'] = pd.to_datetime(unified_df['created_at']).dt.date.astype(str)
            
            # Step 3: Sort by WO- priority (True first = WO- records on top)
            unified_df = unified_df.sort_values(by=['has_wo_prefix'], ascending=[False])
            
            key_cols = ['dedup_plate', 'dedup_sku', 'dedup_date', 'dedup_loc']
            
            before_dedup = len(unified_df)
            
            # Step 4: Dedup keeping first (which is WO- due to sort)
            unified_df = unified_df.drop_duplicates(subset=key_cols, keep='first')
            after_dedup = len(unified_df)
            
            # Cleanup temp columns
            unified_df = unified_df.drop(columns=['dedup_plate', 'dedup_sku', 'dedup_loc', 'dedup_date', 'has_wo_prefix'], errors='ignore')
            
            if before_dedup != after_dedup:
                print(f"   🔄 Deduped batch: {before_dedup - after_dedup} rows removed.")

            # Explode rows (Split Qty > 1)
            exploded_df = explode_rows(unified_df)
            
            # Sort by created_at (ASC) - Critical for chronological calculations
            exploded_df['created_at'] = pd.to_datetime(exploded_df['created_at'])
            exploded_df.sort_values(by=['created_at'], ascending=True, inplace=True)
            
            # --- PASS 1: ENRICHMENT (Bulan Ke, Year Cycle) ---
            # Call with skip_sequence_calc=True to only get Year Cycle and Config
            print("   🛡️ Pass 1: Enriching Warranty Data...")
            enriched_df = calculate_warranty_coverage(exploded_df, asset_df=asset_df, mapping_df=mapping_df, skip_sequence_calc=True)
            
            # --- SMART PERGANTIAN KE CALCULATION (INCREMENTAL) ---
            # 1. Calculate local sequences
            enriched_df['local_total'] = enriched_df.groupby(['vehicle_plate', 'sku']).cumcount() + 1
            enriched_df['local_yearly'] = enriched_df.groupby(['vehicle_plate', 'sku', 'year_cycle']).cumcount() + 1
            
            # 2. Fetch offsets
            print("   📥 Fetching existing counters from Neon...")
            df_max_total = self.get_max_total_pk()
            df_max_yearly = self.get_max_yearly_pk()
            
            # 3. Merge & Add Offsets
            # Ensure types match
            if 'year_cycle' in enriched_df.columns:
                enriched_df['year_cycle'] = enriched_df['year_cycle'].fillna(0).astype(int)
            
            # -- Total Sequence --
            if not df_max_total.empty:
                enriched_df = pd.merge(enriched_df, df_max_total, on=['vehicle_plate', 'sku'], how='left')
                enriched_df['max_pk_total'] = enriched_df['max_pk_total'].fillna(0).astype(int)
                enriched_df['pergantian_ke_total'] = enriched_df['max_pk_total'] + enriched_df['local_total']
                enriched_df.drop(columns=['max_pk_total', 'local_total'], inplace=True, errors='ignore')
            else:
                 enriched_df['pergantian_ke_total'] = enriched_df['local_total']
                 enriched_df.drop(columns=['local_total'], inplace=True, errors='ignore')
                 
            # -- Yearly Sequence --
            if not df_max_yearly.empty:
                if 'year_cycle' in df_max_yearly.columns:
                     df_max_yearly['year_cycle'] = df_max_yearly['year_cycle'].fillna(0).astype(int)
                     
                enriched_df = pd.merge(enriched_df, df_max_yearly, on=['vehicle_plate', 'sku', 'year_cycle'], how='left')
                enriched_df['max_pk_yearly'] = enriched_df['max_pk_yearly'].fillna(0).astype(int)
                enriched_df['pergantian_ke_yearly'] = enriched_df['max_pk_yearly'] + enriched_df['local_yearly']
                enriched_df.drop(columns=['max_pk_yearly', 'local_yearly'], inplace=True, errors='ignore')
            else:
                 enriched_df['pergantian_ke_yearly'] = enriched_df['local_yearly']
                 enriched_df.drop(columns=['local_yearly'], inplace=True, errors='ignore')
            
            # --- PASS 2: FINAL COVERAGE CHECK ---
            # Call again with skip_sequence_calc=True. 
            # It will reuse the 'pergantian_ke' we just calculated to determine correct 'warranty_coverage'.
            print("   🛡️ Pass 2: Final Warranty Coverage Check...")
            final_enriched_df = calculate_warranty_coverage(enriched_df, asset_df=asset_df, mapping_df=mapping_df, skip_sequence_calc=True)
            
            # --- STEP 9: ODOMETER NORMALIZATION ---
            final_enriched_df = normalize_odometer(final_enriched_df)
            
            # Ensure all required columns exist (matching run.py)
            final_columns = [
                'source_system', 'created_at', 'order_number', 'vehicle_plate', 'sku', 'item_name', 
                'erp_product_id', 'item_type', 'service_type', 'service_location_name', 'completed_by', 
                'customer_type', 'quantity', 'unit_price', 'final_price', 'subtotal_price', 'old_price',
                'warranty_status', 'status', 'odometer', 'bike_type',
                # NEW warranty columns
                'delivery_date', 'bulan_ke', 'year_cycle', 'customer_category',
                'warranty_type', 'covered_for', 'limit_per_year', 'pergantian_ke_total', 'pergantian_ke_yearly', 'warranty_coverage'
            ]
            
            # Add missing columns with defaults
            for col in final_columns:
                if col not in final_enriched_df.columns:
                    final_enriched_df[col] = None
            
            final_df = final_enriched_df[final_columns].copy()
            
            # --- PREVENT DUPLICATE INSERT ---
            # Check existing order_numbers in Neon and filter out duplicates
            print("   🔍 Checking for existing order_numbers in Neon...")
            try:
                neon_orders_df = self.loader.fetch_df("""
                    SELECT DISTINCT order_number FROM unified_part_logs
                """)
                if not neon_orders_df.empty:
                    neon_order_set = set(neon_orders_df['order_number'].dropna().astype(str).str.strip().str.upper())
                    
                    # Normalize order_number in final_df for comparison
                    final_df['order_key'] = final_df['order_number'].astype(str).str.strip().str.upper()
                    
                    before_filter = len(final_df)
                    final_df = final_df[~final_df['order_key'].isin(neon_order_set)]
                    after_filter = len(final_df)
                    
                    # Cleanup temp column
                    final_df = final_df.drop(columns=['order_key'], errors='ignore')
                    
                    skipped = before_filter - after_filter
                    if skipped > 0:
                        print(f"   ⏭️ Skipped {skipped} rows (order_number already in Neon)")
                        stats['duplicates_skipped'] = skipped
            except Exception as e:
                print(f"   ⚠️ Could not check existing orders: {e}")
            
            # --- INSERT TO NEON ---
            if not final_df.empty:
                print(f"   📤 Inserting {len(final_df)} new rows to Neon...")
                self.loader.load_df_append(final_df, 'unified_part_logs')
                stats['total_inserted'] = len(final_df)
            else:
                stats['status'] = 'no_new_data'
                stats['message'] = 'All data already exists in Neon'
                return stats
            
            stats['status'] = 'success'
            
        except Exception as e:
            stats['status'] = 'error'
            stats['error'] = str(e)
        
        return stats
    
    def sync_missing_data(self) -> dict:
        """
        Sync data that might have been missed due to failed inserts.
        Uses order_number comparison instead of max_date filter.
        
        Logic:
        1. Get all unique order_numbers from Neon
        2. Get all order_numbers from source (Service Items + Part Usage)
        3. Find order_numbers in source but NOT in Neon
        4. Process and insert only those missing orders
        """
        stats = {
            'status': 'started',
            'source_orders': 0,
            'neon_orders': 0,
            'missing_orders': 0,
            'total_inserted': 0,
            'timestamp': datetime.now()
        }
        
        try:
            # --- STEP 1: Get existing order_numbers from Neon ---
            print("📡 Fetching existing order_numbers from Neon...")
            neon_orders_df = self.loader.fetch_df("""
                SELECT DISTINCT order_number FROM unified_part_logs
            """)
            neon_order_set = set(neon_orders_df['order_number'].dropna().astype(str).str.strip().str.upper())
            stats['neon_orders'] = len(neon_order_set)
            print(f"   Found {len(neon_order_set):,} unique orders in Neon")
            
            # --- STEP 2: Load auxiliary data ---
            asset_df = self.data_loader.load_gspread_data(SHEET_ID_ASSET_LIST, WORKSHEET_ASSET)
            mapping_df = self.data_loader.load_gspread_data(SHEET_ID_MAPPINGS, WORKSHEET_MAPPINGS)
            
            # --- STEP 3: Load all source data ---
            print("📦 Loading source data...")
            raw_si = self.data_loader.load_gspread_data(SHEET_ID_SERVICE_ITEMS, WORKSHEET_SERVICE_ITEMS)
            raw_pu = self.data_loader.load_gspread_data(SHEET_ID_OUTPUT_REVIEW, WORKSHEET_PART_USAGE)
            
            # Standardize
            si_df = standardize_service_items(raw_si, asset_df=asset_df, mapping_df=mapping_df) if not raw_si.empty else pd.DataFrame()
            pu_df = standardize_part_usage(raw_pu, asset_df=asset_df, mapping_df=mapping_df) if not raw_pu.empty else pd.DataFrame()
            
            # Merge all source
            all_source_df = pd.concat([si_df, pu_df], ignore_index=True)
            
            if all_source_df.empty:
                stats['status'] = 'no_source_data'
                return stats
            
            # Get source order_numbers
            all_source_df['order_key'] = all_source_df['order_number'].astype(str).str.strip().str.upper()
            source_order_set = set(all_source_df['order_key'].dropna())
            stats['source_orders'] = len(source_order_set)
            print(f"   Found {len(source_order_set):,} unique orders in source")
            
            # --- STEP 4: Find missing orders ---
            missing_orders = source_order_set - neon_order_set
            stats['missing_orders'] = len(missing_orders)
            
            if not missing_orders:
                stats['status'] = 'no_missing_data'
                print("✅ No missing data found. Neon is in sync with source.")
                return stats
            
            print(f"🔍 Found {len(missing_orders):,} missing orders to sync")
            
            # --- STEP 5: Filter source to only missing orders ---
            missing_df = all_source_df[all_source_df['order_key'].isin(missing_orders)].copy()
            missing_df = missing_df.drop(columns=['order_key'], errors='ignore')
            
            print(f"   Rows to process: {len(missing_df):,}")
            
            # --- APPLY ALL 9 PIPELINE STEPS ---
            
            # Step 2: Exclude test plates
            test_plates = [
                'B 1234 XXX', 'B 3252 WWD', 'B 4086 SWF', 'B 4921 SVO', 'B 5050 BCA',
                'B 9999 BLU', 'B 9999 GRE', 'EL 0015 H3', 'EL 1234 MKT'
            ]
            missing_df = missing_df[~missing_df['vehicle_plate'].isin(test_plates)]
            
            # Step 3: Forward fill
            fill_cols = ['delivery_date', 'customer_type', 'bike_type']
            for col in fill_cols:
                if col in missing_df.columns:
                    missing_before = missing_df[col].isna().sum()
                    if missing_before > 0:
                        missing_df = missing_df.sort_values(['vehicle_plate', 'created_at'])
                        missing_df[col] = missing_df.groupby('vehicle_plate')[col].transform(
                            lambda x: x.ffill().bfill()
                        )
            
            # Step 4: L+H1=GEL fix
            if 'customer_type' in missing_df.columns and 'bike_type' in missing_df.columns:
                l_prefix_h1_mask = (
                    missing_df['vehicle_plate'].astype(str).str.startswith('L ') & 
                    (missing_df['bike_type'].astype(str).str.upper() == 'H1')
                )
                missing_df.loc[l_prefix_h1_mask, 'customer_type'] = 'GEL'
            
            # Dedup
            missing_df['has_wo_prefix'] = missing_df['order_number'].astype(str).str.contains('WO-', case=False, na=False)
            missing_df['dedup_plate'] = missing_df['vehicle_plate'].astype(str).str.strip().str.upper()
            missing_df['dedup_sku'] = missing_df['sku'].astype(str).str.strip().str.upper()
            missing_df['dedup_loc'] = missing_df['service_location_name'].astype(str).str.strip().str.upper()
            missing_df['dedup_date'] = pd.to_datetime(missing_df['created_at']).dt.date.astype(str)
            missing_df = missing_df.sort_values(by=['has_wo_prefix'], ascending=[False])
            key_cols = ['dedup_plate', 'dedup_sku', 'dedup_date', 'dedup_loc']
            missing_df = missing_df.drop_duplicates(subset=key_cols, keep='first')
            missing_df = missing_df.drop(columns=['dedup_plate', 'dedup_sku', 'dedup_loc', 'dedup_date', 'has_wo_prefix'], errors='ignore')
            
            # Explode
            exploded_df = explode_rows(missing_df)
            
            # Sort
            exploded_df['created_at'] = pd.to_datetime(exploded_df['created_at'])
            exploded_df.sort_values(by=['created_at'], ascending=True, inplace=True)
            
            # Warranty calculation
            print("   🛡️ Calculating warranty coverage...")
            enriched_df = calculate_warranty_coverage(exploded_df, asset_df=asset_df, mapping_df=mapping_df, skip_sequence_calc=True)
            
            # Smart pergantian ke with offset
            enriched_df['local_total'] = enriched_df.groupby(['vehicle_plate', 'sku']).cumcount() + 1
            enriched_df['local_yearly'] = enriched_df.groupby(['vehicle_plate', 'sku', 'year_cycle']).cumcount() + 1
            
            df_max_total = self.get_max_total_pk()
            df_max_yearly = self.get_max_yearly_pk()
            
            if 'year_cycle' in enriched_df.columns:
                enriched_df['year_cycle'] = enriched_df['year_cycle'].fillna(0).astype(int)
            
            if not df_max_total.empty:
                enriched_df = pd.merge(enriched_df, df_max_total, on=['vehicle_plate', 'sku'], how='left')
                enriched_df['max_pk_total'] = enriched_df['max_pk_total'].fillna(0).astype(int)
                enriched_df['pergantian_ke_total'] = enriched_df['max_pk_total'] + enriched_df['local_total']
                enriched_df.drop(columns=['max_pk_total', 'local_total'], inplace=True, errors='ignore')
            else:
                enriched_df['pergantian_ke_total'] = enriched_df['local_total']
                enriched_df.drop(columns=['local_total'], inplace=True, errors='ignore')
                
            if not df_max_yearly.empty:
                if 'year_cycle' in df_max_yearly.columns:
                    df_max_yearly['year_cycle'] = df_max_yearly['year_cycle'].fillna(0).astype(int)
                enriched_df = pd.merge(enriched_df, df_max_yearly, on=['vehicle_plate', 'sku', 'year_cycle'], how='left')
                enriched_df['max_pk_yearly'] = enriched_df['max_pk_yearly'].fillna(0).astype(int)
                enriched_df['pergantian_ke_yearly'] = enriched_df['max_pk_yearly'] + enriched_df['local_yearly']
                enriched_df.drop(columns=['max_pk_yearly', 'local_yearly'], inplace=True, errors='ignore')
            else:
                enriched_df['pergantian_ke_yearly'] = enriched_df['local_yearly']
                enriched_df.drop(columns=['local_yearly'], inplace=True, errors='ignore')
            
            # Final coverage
            final_enriched_df = calculate_warranty_coverage(enriched_df, asset_df=asset_df, mapping_df=mapping_df, skip_sequence_calc=True)
            
            # Odometer normalization
            final_enriched_df = normalize_odometer(final_enriched_df)
            
            # Ensure columns
            final_columns = [
                'source_system', 'created_at', 'order_number', 'vehicle_plate', 'sku', 'item_name', 
                'erp_product_id', 'item_type', 'service_type', 'service_location_name', 'completed_by', 
                'customer_type', 'quantity', 'unit_price', 'final_price', 'subtotal_price', 'old_price',
                'warranty_status', 'status', 'odometer', 'bike_type',
                'delivery_date', 'bulan_ke', 'year_cycle', 'customer_category',
                'warranty_type', 'covered_for', 'limit_per_year', 'pergantian_ke_total', 'pergantian_ke_yearly', 'warranty_coverage'
            ]
            
            for col in final_columns:
                if col not in final_enriched_df.columns:
                    final_enriched_df[col] = None
            
            final_df = final_enriched_df[final_columns].copy()
            
            # Insert
            if not final_df.empty:
                print(f"   📤 Inserting {len(final_df):,} rows to Neon...")
                self.loader.load_df_append(final_df, 'unified_part_logs')
                stats['total_inserted'] = len(final_df)
            
            stats['status'] = 'success'
            print(f"✅ Sync missing data completed: {stats['total_inserted']:,} rows inserted")
            
        except Exception as e:
            stats['status'] = 'error'
            stats['error'] = str(e)
        
        return stats
    
    def _apply_filters_to_df(self, df: pd.DataFrame, filters: dict) -> pd.DataFrame:
        if df.empty or not filters:
            return df
            
        filtered = df.copy()
        
        if filters.get('vehicle_plate') and filters['vehicle_plate'] != 'All':
            filtered = filtered[filtered['vehicle_plate'] == filters['vehicle_plate']]
            
        if filters.get('order_number'):
            filtered = filtered[filtered['order_number'].astype(str).str.contains(filters['order_number'], case=False, na=False)]
            
        if filters.get('service_location_name') and filters['service_location_name'] != 'All':
            filtered = filtered[filtered['service_location_name'] == filters['service_location_name']]
            
        if filters.get('item_name') and filters['item_name'] != 'All':
            filtered = filtered[filtered['item_name'] == filters['item_name']]
            
        if filters.get('customer_type') and filters['customer_type'] != 'All':
            filtered = filtered[filtered['customer_type'] == filters['customer_type']]
            
        if filters.get('warranty_coverage') and filters['warranty_coverage'] != 'All':
            filtered = filtered[filtered['warranty_coverage'] == filters['warranty_coverage']]
            
        if filters.get('sku') and filters['sku'] != 'All':
            filtered = filtered[filtered['sku'] == filters['sku']]
            
        if filters.get('start_date'):
            filtered = filtered[filtered['created_at'] >= pd.to_datetime(filters['start_date'])]
            
        if filters.get('end_date'):
            filtered = filtered[filtered['created_at'] <= pd.to_datetime(filters['end_date'])]
            
        if filters.get('location_category'):
            cat = filters['location_category']
            locs = filtered['service_location_name'].astype(str).str.lower()
            if cat == 'B2B Repair':
                filtered = filtered[locs.str.contains('grab', na=False)]
            elif cat == 'Internal Repair':
                filtered = filtered[
                    locs.str.contains('pondok indah', na=False) |
                    locs.str.contains('kembangan', na=False) |
                    locs.str.contains('depok', na=False) |
                    locs.str.contains('bekasi', na=False)
                ]
            elif cat == 'Official Partner':
                filtered = filtered[
                    ~locs.str.contains('grab', na=False) &
                    ~locs.str.contains('pondok indah', na=False) &
                    ~locs.str.contains('kembangan', na=False) &
                    ~locs.str.contains('depok', na=False) &
                    ~locs.str.contains('bekasi', na=False)
                ]
                
        if filters.get('exclude_skus'):
            filtered = filtered[~filtered['sku'].isin(filters['exclude_skus'])]
            
        return filtered

    def get_data_for_display(self, filters: dict = None, page: int = 1, page_size: int = 50) -> tuple:
        """
        Get data from Google Drive for Streamlit display with filters and pagination.
        Returns (dataframe, total_count).
        """
        df = self._get_drive_dataframe()
        if df.empty:
            return df, 0
            
        filtered_df = self._apply_filters_to_df(df, filters)
        
        # Sort by created_at DESC
        filtered_df = filtered_df.sort_values(by='created_at', ascending=False)
        total_count = len(filtered_df)
        
        # Paginate
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_df = filtered_df.iloc[start_idx:end_idx].copy()
        
        # Standardize warranty_status col name for display
        if 'warranty_coverage' in paginated_df.columns:
            paginated_df['warranty_status'] = paginated_df['warranty_coverage']
            
        # Select required columns
        display_cols = [
            'created_at', 'source_system', 'order_number', 'vehicle_plate', 
            'sku', 'item_name', 'bike_type', 'customer_type', 
            'quantity', 'final_price', 'subtotal_price', 'old_price', 
            'warranty_status', 'pergantian_ke_total', 'pergantian_ke_yearly', 
            'odometer', 'service_location_name'
        ]
        
        # Ensure all cols exist
        for col in display_cols:
            if col not in paginated_df.columns:
                paginated_df[col] = None
                
        return paginated_df[display_cols], total_count

    def get_filter_options(self) -> dict:
        """Get unique options for filters from DataFrame."""
        options = {k: [] for k in ['vehicle_plate', 'item_name', 'customer_type', 'warranty_coverage', 'sku', 'service_location_name']}
        
        df = self._get_drive_dataframe()
        if df.empty:
            return options
            
        try:
            options['vehicle_plate'] = sorted([str(x) for x in df['vehicle_plate'].dropna().unique()])
            options['item_name'] = sorted([str(x) for x in df['item_name'].dropna().unique()])
            options['customer_type'] = sorted([str(x) for x in df['customer_type'].dropna().unique()])
            
            # Handle possible col rename or fallback
            if 'warranty_coverage' in df.columns:
                options['warranty_coverage'] = sorted([str(x) for x in df['warranty_coverage'].dropna().unique()])
            elif 'warranty_status' in df.columns:
                 options['warranty_coverage'] = sorted([str(x) for x in df['warranty_status'].dropna().unique()])
                 
            options['sku'] = sorted([str(x) for x in df['sku'].dropna().unique()])
            options['service_location_name'] = sorted([str(x) for x in df['service_location_name'].dropna().unique()])
            
        except Exception as e:
            print(f"⚠️ Error loading filter options from Local DataFrame: {e}")
            
        return options
    
    def get_cohort_data(self, filters: dict = None) -> pd.DataFrame:
        """
        Get cohort data for heatmap visualization.
        Shows pergantian_ke timeline per vehicle+sku.
        Apply all filters including dates.
        """
        df = self._get_drive_dataframe()
        if df.empty:
            return pd.DataFrame()
            
        # Base filter
        filtered_df = df[df['vehicle_plate'].notna()].copy()
        
        # Apply UI filters
        filtered_df = self._apply_filters_to_df(filtered_df, filters)
        
        if filtered_df.empty:
            return filtered_df
            
        # Create Month truncate
        filtered_df['month'] = pd.to_datetime(filtered_df['created_at']).dt.to_period('M').dt.to_timestamp()
        
        # Select target columns
        target_cols = [
            'vehicle_plate', 'sku', 'item_name', 'month', 
            'pergantian_ke_total', 'pergantian_ke_yearly', 
            'final_price', 'odometer', 'warranty_coverage', 'created_at'
        ]
        
        # Ensure columns exist safely
        for col in target_cols:
             if col not in filtered_df.columns:
                 if col == 'warranty_coverage' and 'warranty_status' in filtered_df.columns:
                     filtered_df['warranty_coverage'] = filtered_df['warranty_status']
                 else:
                     filtered_df[col] = None
                     
        result_df = filtered_df[target_cols].copy()
        result_df = result_df.sort_values(by=['vehicle_plate', 'sku', 'created_at'])
        
        return result_df
    
    def get_tire_cohort_data(self, filters: dict = None) -> pd.DataFrame:
        """
        Get Tire Cost Analysis data with GEL vs Non-GEL comparison.
        Uses delivery_date directly from unified_part_logs (already in Neon/CSV).
        """
        df = self._get_drive_dataframe()
        if df.empty:
            return pd.DataFrame()
            
        # 1. Base filter: Tires
        tire_mask = df['item_name'].astype(str).str.contains('Tire|Ban', case=False, na=False)
        filtered_df = df[tire_mask].copy()
        
        # 2. Apply UI Filters
        filtered_df = self._apply_filters_to_df(filtered_df, filters)
        
        if filtered_df.empty:
            return filtered_df
            
        # 3. Simulate FIRST_VALUE window function for customer_type and delivery_date per plate
        filtered_df = filtered_df.sort_values(['vehicle_plate', 'created_at'], ascending=[True, False])
        
        # Forward/Backward fill within groups to simulate FIRST_VALUE IGNORE NULLS logic simply
        filtered_df['customer_type'] = filtered_df.groupby('vehicle_plate')['customer_type'].transform(lambda x: x.replace(['', 'nan', 'None'], pd.NA).ffill().bfill())
        filtered_df['delivery_date'] = filtered_df.groupby('vehicle_plate')['delivery_date'].transform(lambda x: pd.to_datetime(x, errors='coerce').ffill().bfill())
        
        filtered_df['replacement_date'] = pd.to_datetime(filtered_df['created_at']).dt.date
        
        # Get target columns
        df = filtered_df[['vehicle_plate', 'sku', 'item_name', 'customer_type', 
                          'pergantian_ke_total', 'final_price', 'odometer', 
                          'created_at', 'delivery_date', 'replacement_date']].copy()
                          
        # Calculate metrics - normalize timezone (remove tz info)
        df['created_at'] = pd.to_datetime(df['created_at']).dt.tz_localize(None)
        df['delivery_date'] = pd.to_datetime(df['delivery_date'], errors='coerce').dt.tz_localize(None)
        df['current_odometer'] = pd.to_numeric(df['odometer'], errors='coerce').fillna(0)
        
        # Sort by plate and pergantian_ke for proper LAG calculation
        df = df.sort_values(['vehicle_plate', 'sku', 'pergantian_ke_total'])
        
        # Get previous replacement date and odometer per plate+sku using shift (LAG equivalent)
        df['prev_replacement_date'] = df.groupby(['vehicle_plate', 'sku'])['created_at'].shift(1)
        df['prev_odometer'] = df.groupby(['vehicle_plate', 'sku'])['current_odometer'].shift(1)
        
        # For pergantian ke-1: use delivery_date as baseline
        # For pergantian ke-2+: use previous replacement date
        df['baseline_date'] = df.apply(
            lambda row: row['delivery_date'] if row['pergantian_ke_total'] == 1 or pd.isna(row['prev_replacement_date'])
            else row['prev_replacement_date'],
            axis=1
        )
        
        # For KM: pergantian ke-1 uses delivery_odometer (0 if not available)
        # For pergantian ke-2+: uses previous odometer
        df['baseline_odometer'] = df.apply(
            lambda row: 0 if row['pergantian_ke_total'] == 1 or pd.isna(row['prev_odometer'])
            else row['prev_odometer'],
            axis=1
        )
        
        # Calculate incremental duration (months since previous replacement / delivery)
        df['duration_months'] = ((df['created_at'] - df['baseline_date']).dt.days / 30.44).fillna(0).round(1)
        df['duration_months'] = df['duration_months'].apply(lambda x: max(0, x))
        
        # Calculate incremental odometer difference
        df['odometer_diff'] = df['current_odometer'] - df['baseline_odometer']
        df['odometer_diff'] = df['odometer_diff'].apply(lambda x: max(0, x))
        
        # Keep delivery_odometer as baseline reference (for display)
        df['delivery_odometer'] = df['baseline_odometer']
        
        # Categorize GEL vs Non-GEL
        df['customer_category'] = np.where(
            df['customer_type'].astype(str).str.strip().str.upper() == 'GEL',
            'GEL',
            'NON-GEL'
        )
        
        return df
    
    def get_cost_per_km_data(self, filters: dict = None) -> pd.DataFrame:
        """
        Get cost/km data for chart visualization.
        Apply filters including dates.
        """
        df = self._get_drive_dataframe()
        if df.empty:
            return pd.DataFrame()
            
        # 1. Base filter
        df['odometer'] = pd.to_numeric(df['odometer'], errors='coerce').fillna(0)
        filtered_df = df[df['odometer'] > 0].copy()
        
        # 2. Apply UI Filters
        if filters:
            if filters.get('start_date'):
                filtered_df = filtered_df[filtered_df['created_at'] >= pd.to_datetime(filters['start_date'])]
            
            if filters.get('end_date'):
                filtered_df = filtered_df[filtered_df['created_at'] <= pd.to_datetime(filters['end_date'])]

            if filters.get('vehicle_plate') and filters['vehicle_plate'] != 'All':
                filtered_df = filtered_df[filtered_df['vehicle_plate'] == filters['vehicle_plate']]
                
        if filtered_df.empty:
            return pd.DataFrame()
            
        # 3. Group and aggregate
        filtered_df['final_price'] = pd.to_numeric(filtered_df['final_price'], errors='coerce').fillna(0)
        
        grouped = filtered_df.groupby(['vehicle_plate', 'bike_type']).agg(
            total_cost=('final_price', 'sum'),
            max_odo=('odometer', 'max'),
            min_odo=('odometer', 'min'),
            service_count=('odometer', 'count')
        ).reset_index()
        
        # Calculate km_traveled
        grouped['km_traveled'] = grouped['max_odo'] - grouped['min_odo']
        
        # Filter where km_traveled > 0
        grouped = grouped[grouped['km_traveled'] > 0].copy()
        
        if grouped.empty:
            return pd.DataFrame()
            
        # Calculate cost_per_km
        grouped['cost_per_km'] = grouped['total_cost'] / grouped['km_traveled']
        
        # Sort and limit 
        grouped = grouped.sort_values('cost_per_km', ascending=False).head(100)
        
        return grouped
