import pandas as pd
import numpy as np
import random
import re
from difflib import SequenceMatcher
from src.common.utils import ServiceUtils
from src.common.config import (
    SERVICE_TYPE_MAPPING, COLUMN_MAPPING, PARTS_COLUMNS_MAPPING,
    DRIVER_CATEGORY_RULES
)

class ServiceDataPipeline:
    """
    Handles data ingestion, standardization, and initial cleaning.
    """
    def __init__(self):
        self.raw_dfs = []
        self.master_data = pd.DataFrame()

    def _clean_odometer(self, series):
        clean_series = series.astype(str).str.replace(r'[^\d]', '', regex=True).replace('', '0')
        return pd.to_numeric(clean_series, errors='coerce').fillna(0).astype('int64')

    def _assign_standard_columns(self, df, source_key):
        if df.empty: return df
        df.columns = df.columns.str.strip()

        # 1. Column Mapping
        if source_key in COLUMN_MAPPING:
            mapping = COLUMN_MAPPING[source_key]
            rename_dict = {k: v for k, v in mapping.items() if k in df.columns and v not in df.columns}
            df = df.rename(columns=rename_dict)

        # 2. Hardcode Logic for Specific Sources
        if source_key == 'S5_AFTER_REPAIR':
            if 'created_at' not in df.columns:
                candidates = [c for c in df.columns if 'tanggal' in c.lower()]
                if candidates:
                    df = df.rename(columns={candidates[0]: 'created_at'})
            
            df['service_type'] = "Repo Maintenance"
            if 'service_location_name' not in df.columns: df['service_location_name'] = "Pondok Indah"
        
        elif source_key == 'S4_REQUEST_SPK':
            df['service_type'] = "Official Partner Service"

        # 3. Parts Combination
        if source_key in PARTS_COLUMNS_MAPPING:
            valid_parts = [c for c in PARTS_COLUMNS_MAPPING[source_key] if c in df.columns]
            if valid_parts:
                df['item_name'] = df.apply(lambda r: ServiceUtils.combine_columns_to_string(r, valid_parts), axis=1)

        # 4. Service Type Mapping
        if 'service_type' in df.columns:
            df['service_type'] = df['service_type'].map(SERVICE_TYPE_MAPPING).fillna(df['service_type'])
            df['service_type'] = df['service_type'].fillna("Repo Maintenance")

        # 5. Date Parsing
        if 'created_at' in df.columns:
            df['created_at'] = ServiceUtils.robust_date_parse(df['created_at'], source_key)
        else:
            cands = [c for c in df.columns if any(x in str(c).lower() for x in ['timestamp', 'tanggal', 'date', 'time'])]
            if cands:
                print(f"   -> Auto-detect date ({source_key}): {cands[0]}")
                df['created_at'] = ServiceUtils.robust_date_parse(df[cands[0]], source_key)
            else:
                print(f"   ❌ CRITICAL: No date column found for {source_key}")

        for col in ['updated_at', 'completed_at', 'prize_finalized_at']:
            if col in df.columns: df[col] = ServiceUtils.robust_date_parse(df[col], f"{source_key}-{col}")

        # 6. Timeline Fill
        df = df.apply(ServiceUtils.fill_timeline, axis=1)

        # 7. Odometer
        if 'odometer' in df.columns: df['odometer'] = self._clean_odometer(df['odometer'])
        else: df['odometer'] = 0

        # 8. License Plate Backup
        if 'vehicle_license_plate' not in df.columns: df['vehicle_license_plate'] = np.nan
        for backup in ['vehicle_license_plate_backup', 'vehicle_license_plate_backup_2']:
            if backup in df.columns:
                df['vehicle_license_plate'] = df['vehicle_license_plate'].fillna(df[backup])
        
        df['vehicle_license_plate'] = df['vehicle_license_plate'].apply(ServiceUtils.format_plat_nomor)

        if 'order_status' not in df.columns: df['order_status'] = 'COMPLETED'
        
        # [FIX] Ensure driver_category exists for ALL sources (even if null)
        if 'driver_category' not in df.columns:
            df['driver_category'] = np.nan

        return df

    def _process_cabang_logic(self, df, location_name, source_key):
        if df.empty: return df
        df.columns = df.columns.str.strip()

        # Parts
        if source_key in PARTS_COLUMNS_MAPPING:
            valid_cols = [c for c in PARTS_COLUMNS_MAPPING[source_key] if c in df.columns]
            if valid_cols:
                df['item_name'] = df.apply(lambda r: ServiceUtils.combine_columns_to_string(r, valid_cols), axis=1)

        # Smart Rename for Date
        time_priority = ['Timestamp', 'Date', 'Tanggal']
        renamed = False
        for col in time_priority:
            if col in df.columns:
                df = df.rename(columns={col: 'created_at'})
                renamed = True
                break
        
        if not renamed:
             cands = [c for c in df.columns if 'time' in c.lower() or 'date' in c.lower()]
             if cands:
                 df = df.rename(columns={cands[0]: 'created_at'})

        # Manual Map
        col_map = {
            'SparePart Name': 'item_name', 'Plate Number': 'vehicle_license_plate',
            'Plat Nomor': 'vehicle_license_plate', 'Plat Number': 'vehicle_license_plate',
            'Plat Kendaraan / VIN': 'vehicle_license_plate',
            'Date Bike Repair': 'completed_at',
            'Problem': 'customer_problems', 'Repair Action': 'action_description',
            'Mechanic Name': 'completed_by', 'Checker / Repair': 'completed_by', 'Nama Mekani': 'completed_by'
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        
        # Standardize
        df = df.loc[:, ~df.columns.duplicated()]
        if 'vehicle_license_plate' in df.columns:
            df['vehicle_license_plate'] = df['vehicle_license_plate'].astype(str).apply(ServiceUtils.format_plat_nomor)

        df['service_location_name'] = location_name
        df['order_status'] = 'COMPLETED'

        if source_key == 'S6_KEMBANGAN': df['service_type'] = "Repo Maintenance"
        else: df['service_type'] = "Walk-In Maintenance"

        if 'service_type' in df.columns:
            df['service_type'] = df['service_type'].map(SERVICE_TYPE_MAPPING).fillna(df['service_type'])
            df['service_type'] = df['service_type'].fillna("Repo Maintenance")

        # Dates
        if 'created_at' in df.columns:
             df['created_at'] = ServiceUtils.robust_date_parse(df['created_at'], source_key)
        
        if 'completed_at' in df.columns: 
            df['completed_at'] = ServiceUtils.robust_date_parse(df['completed_at'], f"{source_key}-completed")

        if 'odometer' not in df.columns: df['odometer'] = 0
        else: df['odometer'] = self._clean_odometer(df['odometer'])

        df = df.apply(ServiceUtils.fill_timeline, axis=1)
        return df

    def _append_to_raw(self, df, source_key):
        df = df.loc[:, ~df.columns.duplicated()]
        final_cols = [
            'created_at', 'updated_at', 'completed_at', 'prize_finalized_at', 
            'vehicle_license_plate', 'odometer', 'service_location_name', 
            'bike_type', 'item_name', 'customer_name', 'service_type', 
            'order_status', 'customer_problems', 'action_description', 
            'completed_by', 'total_price', 'data_source', 'vechicle_vin', 
            'vechicle_engine', 'color', 'customer_type', 'driver_category'
        ]
        for c in final_cols:
            if c not in df.columns: df[c] = None
        
        df['data_source'] = source_key
        self.raw_dfs.append(df[final_cols])

    def ingest_generic(self, df, source_key, filter_func=None):
        if df is None or df.empty: return
        if filter_func: df = filter_func(df)
        df = self._assign_standard_columns(df, source_key)
        self._append_to_raw(df, source_key)

    def ingest_cabang(self, df, source_key, location_name):
        if df is None or df.empty: return
        df = self._process_cabang_logic(df, location_name, source_key)
        self._append_to_raw(df, source_key)

    def merge_and_finalize(self):
        print(f"Merging {len(self.raw_dfs)} sources...")
        if not self.raw_dfs: return pd.DataFrame()
        self.master_data = pd.concat(self.raw_dfs, ignore_index=True)
        
        # Final cleanup on merged data
        if 'odometer' in self.master_data.columns:
             self.master_data['odometer'] = self._clean_odometer(self.master_data['odometer'])
        
        for col in ['created_at', 'updated_at', 'completed_at', 'prize_finalized_at']:
             self.master_data[col] = pd.to_datetime(self.master_data[col], errors='coerce')
        
        self.master_data.sort_values(by='created_at', inplace=True)
        return self.master_data


class ServiceDataEnricher:
    """
    Handles enrichment, fuzzy matching, and business logic.
    """
    def __init__(self, master_data, asset_list_df):
        self.df = master_data.copy()
        self.assets = asset_list_df.copy() if asset_list_df is not None else pd.DataFrame()
        self.bad_data = pd.DataFrame()
        self._prepare_asset_maps()

    def _prepare_asset_maps(self):
        if 'Plat Nomor' in self.assets.columns:
            self.assets['Plat_Clean'] = self.assets['Plat Nomor'].astype(str).apply(ServiceUtils.format_plat_nomor).fillna('').str.strip().str.upper()
            
            valid_assets = self.assets[self.assets['Plat_Clean'] != '']
            
            # Helper to find columns case-insensitively
            def get_col(candidates):
                for c in candidates:
                    if c in self.assets.columns: return c
                return None

            col_model = get_col(['Model', 'model', 'Bike Model'])
            col_sewa = get_col(['Tempat Sewa Unit', 'tempat sewa unit', 'Sewa', 'Customer Type'])
            col_color = get_col(['Color', 'color', 'Warna', 'Colour'])

            self.vin_map = valid_assets.set_index('Plat_Clean')['VIN'].to_dict()
            self.engine_map = valid_assets.set_index('Plat_Clean')['Engine No'].to_dict()
            self.model_map = valid_assets.set_index('Plat_Clean')[col_model].to_dict() if col_model else {}
            self.sewa_map = valid_assets.set_index('Plat_Clean')[col_sewa].to_dict() if col_sewa else {}
            self.color_map = valid_assets.set_index('Plat_Clean')[col_color].to_dict() if col_color else {}
            
            # [NEW] Driver Category Map (Asset List is for Rentals, but maybe useful? User said NO for B2C)
            # Keeping it empty or just for rentals if needed. 
            # User instruction: "asset_list hanya berisi unit rental bukan punya B2C"
            # So we rely on backfill and standardization.
            self.driver_cat_map = {} 
            self.cust_driver_cat_map = {}
        else:
            self.vin_map = {}; self.engine_map = {}; self.model_map = {}; self.sewa_map = {}; self.color_map = {}; self.driver_cat_map = {}; self.cust_driver_cat_map = {}

    def _log_bad_data(self, bad_rows, reason):
        if not bad_rows.empty:
            bad_rows = bad_rows.copy()
            bad_rows['reject_reason'] = reason
            self.bad_data = pd.concat([self.bad_data, bad_rows], ignore_index=True)

    def _fuzzy_match_plate(self, bad_plate, threshold=0.85):
        if pd.isna(bad_plate) or len(str(bad_plate)) < 4: return None
        best_match, best_score = None, 0
        target_len = len(bad_plate)
        
        # Optimization: only check candidates with similar length
        candidates = [p for p in self.vin_map.keys() if isinstance(p, str) and abs(len(p) - target_len) <= 1]

        for asset_plate in candidates:
            score = SequenceMatcher(None, bad_plate, asset_plate).ratio()
            if score > best_score:
                best_score, best_match = score, asset_plate
        return best_match if best_score >= threshold else None

    def clean_critical_data(self):
        """Log & Remove missing created_at"""
        print("   - Cleaning data without created_at...")
        mask_missing = self.df['created_at'].isna()
        self._log_bad_data(self.df[mask_missing], "Missing Timestamp")
        
        len_before = len(self.df)
        self.df = self.df[~mask_missing].reset_index(drop=True)
        print(f"     Dropped {len_before - len(self.df)} rows.")
        return self

    def repair_identities_and_clean(self):
        """Repair Identities & Fuzzy Match & Recovery"""
        print("🚀 Repairing Identities & Cleaning Bad Data...")
        
        for c in ['vechicle_vin', 'vechicle_engine', 'color', 'customer_type', 'bike_type', 'driver_category']:
            if c not in self.df.columns: self.df[c] = np.nan

        self.df['plat_clean'] = self.df['vehicle_license_plate'].astype(str).apply(ServiceUtils.format_plat_nomor).fillna('').str.strip().str.upper()

        # 1. Exact Match
        self.df['vechicle_vin'] = self.df['vechicle_vin'].fillna(self.df['plat_clean'].map(self.vin_map))
        self.df['vechicle_engine'] = self.df['vechicle_engine'].fillna(self.df['plat_clean'].map(self.engine_map))
        self.df['color'] = self.df['color'].fillna(self.df['plat_clean'].map(self.color_map))
        self.df['driver_category'] = self.df['driver_category'].fillna(self.df['plat_clean'].map(self.driver_cat_map))

        # 2. Fuzzy Match
        mask_still_missing = self.df['vechicle_vin'].isna()
        unique_missing = self.df.loc[mask_still_missing, 'plat_clean'].unique()
        
        corrected_map = {}
        for bad_plate in unique_missing:
            if not bad_plate or len(bad_plate) < 4: continue
            match = self._fuzzy_match_plate(bad_plate)
            if match: corrected_map[bad_plate] = match
        
        if corrected_map:
            print(f"   - Correcting {len(corrected_map)} typo plates...")
            for bad, good in corrected_map.items():
                mask_fix = self.df['plat_clean'] == bad
                self.df.loc[mask_fix, 'vehicle_license_plate'] = good
                self.df.loc[mask_fix, 'plat_clean'] = good
                self.df.loc[mask_fix, 'vechicle_vin'] = self.vin_map.get(good)
                self.df.loc[mask_fix, 'vechicle_engine'] = self.engine_map.get(good)
                self.df.loc[mask_fix, 'color'] = self.color_map.get(good)
                self.df.loc[mask_fix, 'driver_category'] = self.driver_cat_map.get(good)

        # 3. Recovery Strategy (Customer History)
        mask_invalid = self.df['vechicle_vin'].isna()
        if mask_invalid.any():
            print(f"   - Attempting to recover {mask_invalid.sum()} rows using customer history...")
            self._recover_dropped_rows(mask_invalid)
            
        # 4. Log Bad Data (Final Check)
        mask_invalid = self.df['vechicle_vin'].isna()
        
        # [NEW] Retain B2C even if invalid plate
        mask_b2c = self.df['driver_category'].astype(str).str.contains('B2C', case=False, na=False)
        
        # Drop only if invalid AND NOT B2C
        mask_drop = mask_invalid & ~mask_b2c
        
        self._log_bad_data(self.df[mask_drop], "Invalid/Unknown License Plate")
        
        n_dropped = mask_drop.sum()
        if n_dropped > 0:
            self.df = self.df[~mask_drop].reset_index(drop=True)
            print(f"     Dropped {n_dropped} rows (Unrecognized License Plate). Retained {mask_invalid.sum() - n_dropped} B2C rows.")
        
        self.df.drop(columns=['plat_clean'], inplace=True)
        return self

    def _recover_dropped_rows(self, mask_invalid):
        """
        Recover rows with missing VIN by looking up customer_name in valid history.
        """
        # 1. Build Customer Map from Valid Data
        valid_data = self.df[~mask_invalid].copy()
        if valid_data.empty: return

        # Count frequency of (customer, plate)
        cust_plate_counts = valid_data.groupby(['customer_name', 'vehicle_license_plate']).size().reset_index(name='count')
        
        # Get most frequent plate for each customer
        best_plate = cust_plate_counts.sort_values('count', ascending=False).drop_duplicates('customer_name')
        cust_map = best_plate.set_index('customer_name')['vehicle_license_plate'].to_dict()
        
        # [NEW] Also build map for driver_category from history
        cust_cat_counts = valid_data.groupby(['customer_name', 'driver_category']).size().reset_index(name='count')
        best_cat = cust_cat_counts.sort_values('count', ascending=False).drop_duplicates('customer_name')
        cust_cat_map = best_cat.set_index('customer_name')['driver_category'].to_dict()

        # 2. Apply Recovery
        invalid_indices = self.df[mask_invalid].index
        recovered_count = 0
        
        for idx in invalid_indices:
            cust_name = self.df.at[idx, 'customer_name']
            if pd.notna(cust_name) and cust_name in cust_map:
                recovered_plate = cust_map[cust_name]
                
                # Clean plate for lookup
                recovered_plate_clean = str(recovered_plate).strip().upper()
                
                # Verify if recovered plate is valid in assets
                if recovered_plate_clean in self.vin_map:
                    self.df.at[idx, 'vehicle_license_plate'] = recovered_plate
                    self.df.at[idx, 'plat_clean'] = recovered_plate_clean
                    self.df.at[idx, 'vechicle_vin'] = self.vin_map[recovered_plate_clean]
                    self.df.at[idx, 'vechicle_engine'] = self.engine_map.get(recovered_plate_clean)
                    self.df.at[idx, 'color'] = self.color_map.get(recovered_plate_clean)
                    self.df.at[idx, 'driver_category'] = self.driver_cat_map.get(recovered_plate_clean)
                    recovered_count += 1
            
            # [NEW] Recover driver_category if still missing (from History OR Asset List)
            # Removed Asset List lookup for B2C as per user instruction.
            current_cat = self.df.at[idx, 'driver_category']
            if pd.isna(current_cat) and pd.notna(cust_name):
                # Try History
                if cust_name in cust_cat_map:
                    self.df.at[idx, 'driver_category'] = cust_cat_map[cust_name]
        
        if recovered_count > 0:
            print(f"     ✅ Recovered {recovered_count} rows using customer history.")

    def standardize_driver_category(self):
        print("🚀 Standardizing Driver Category...")
        if 'driver_category' not in self.df.columns: return self
        
        def _std_cat(val):
            s = str(val).strip()
            if not s or s.lower() == 'nan': return np.nan
            for pattern, replacement in DRIVER_CATEGORY_RULES.items():
                if re.search(pattern, s):
                    return replacement
            return s

        self.df['driver_category'] = self.df['driver_category'].apply(_std_cat)
        return self

    def backfill_driver_category(self):
        print("🚀 Backfilling Driver Category...")
        if 'driver_category' not in self.df.columns or 'vehicle_license_plate' not in self.df.columns: return self
        
        # Sort by date to ensure propagation makes sense (optional, but good practice)
        if 'created_at' in self.df.columns:
            self.df = self.df.sort_values('created_at')

        # Group by plate and ffill/bfill
        # We use transform to keep the index aligned
        self.df['driver_category'] = self.df.groupby('vehicle_license_plate')['driver_category'].transform(lambda x: x.ffill().bfill())
        
        return self

    def enrich_asset_details(self):
        """Fill Details from Asset List"""
        print("🚀 Enriching Asset Details...")
        self.df['plat_clean'] = self.df['vehicle_license_plate'].astype(str).str.strip().str.upper()
        
        self.df['bike_type'] = self.df['bike_type'].fillna(self.df['plat_clean'].map(self.model_map))
        self.df['customer_type'] = self.df['customer_type'].fillna(self.df['plat_clean'].map(self.sewa_map))
        self.df['color'] = self.df['color'].fillna(self.df['plat_clean'].map(self.color_map))
        
        self.df.drop(columns=['plat_clean'], inplace=True)
        return self

    def fill_customer_names(self):
        """Backfill & Fallback for Customer Names"""
        print("🚀 Backfilling Customer Names...")
        self.df.sort_values(['vehicle_license_plate', 'created_at'], inplace=True)
        
        self.df['customer_name'] = self.df.groupby('vehicle_license_plate')['customer_name'].ffill().bfill()
        
        def fallback_name(row):
            if pd.notna(row['customer_name']): return row['customer_name']
            ctype = str(row['customer_type']).upper()
            if 'GEL' in ctype: return "Driver GEL"
            if 'DAX' in ctype or 'GRAB' in ctype: return "Driver Grab"
            return "Sahabat Electrum"

        mask_empty = self.df['customer_name'].isna()
        if mask_empty.any():
            self.df.loc[mask_empty, 'customer_name'] = self.df.loc[mask_empty].apply(fallback_name, axis=1)
            
        return self

    def process_odometer(self):
        """Estimasi ODO 0 & Keep Original Value"""
        print("🚀 Processing Odometer...")
        if 'odometer' not in self.df.columns: self.df['odometer'] = 0
        self.df['odometer'] = pd.to_numeric(self.df['odometer'], errors='coerce').fillna(0)

        self.df.sort_values(by=['vehicle_license_plate', 'created_at'], inplace=True)
        temp_odo = self.df['odometer'].replace(0, np.nan)
        last_val = temp_odo.ffill()
        
        last_date = self.df['created_at'].where(self.df['odometer'] > 0).ffill()
        last_plate = self.df['vehicle_license_plate'].where(self.df['odometer'] > 0).ffill()
        
        diff_days = (self.df['created_at'] - last_date).dt.days
        mask_est = (self.df['odometer'] == 0) & (last_val.notna()) & (last_plate == self.df['vehicle_license_plate']) & (diff_days >= 0)
        
        self.df.loc[mask_est, 'odometer'] = last_val + (diff_days * 100)
        self.df['odometer'] = self.df['odometer'].astype('int64')
        
        return self

    def standardize_mechanics(self, employee_df):
        print("🚀 Standardizing Mechanics...")
        if employee_df is None or employee_df.empty: return self
        
        patterns = []
        for _, row in employee_df.iterrows():
            if pd.notna(row['Pola Regex']) and str(row['Pola Regex']).strip() != '':
                try: patterns.append((re.compile(r'\b' + str(row['Pola Regex']) + r'\b', re.IGNORECASE), row['Full Name']))
                except: continue

        def _match(name, stype):
            name = str(name).strip()
            if stype == 'Official Partner Service': return "Mechanic Workshop Partner"
            if len(name) < 3 or name.lower() in ['nan', 'none', '']: return "Daily Worker"
            for p, full in patterns:
                if p.search(name): return full
            return "Daily Worker"

        self.df['completed_by'] = self.df.apply(lambda x: _match(x['completed_by'], x['service_type']), axis=1)
        return self

    def standardize_location_names(self):
        """Standardize service_location_name"""
        print("🚀 Standardizing Location Names...")
        
        def _standardize_location(loc):
            if pd.isna(loc): return loc
            loc_str = str(loc).strip()
            
            # Check for Grab Cakung
            if any(keyword in loc_str for keyword in ['Grab', 'Cakung', 'grab', 'cakung']):
                return "Grab Cakung"
            
            # Check for Pondok Indah
            if any(keyword in loc_str for keyword in ['Electrum', 'Pondok Indah', 'electrum', 'pondok indah']):
                return "Pondok Indah"
            
            return loc_str
        
        if 'service_location_name' in self.df.columns:
            self.df['service_location_name'] = self.df['service_location_name'].apply(_standardize_location)
        
        return self

    def generate_snowflake_ids(self):
        print("🚀 Generating IDs (Deterministic)...")
        # Ensure created_at is datetime
        self.df['created_at'] = pd.to_datetime(self.df['created_at'])
        
        # Sort to ensure consistent sequencing
        self.df = self.df.sort_values(['created_at', 'vechicle_vin'])
        
        # Generate sequence (0 to N) for each identical timestamp
        # Using cumcount to get unique sequence for same timestamp
        self.df['id_sequence'] = self.df.groupby('created_at').cumcount()
        
        # Apply generator with explicit sequence
        self.df['order_id'] = self.df.apply(
            lambda row: ServiceUtils.create_historical_snowflake_id(
                row['created_at'], 
                row['id_sequence']
            ), axis=1
        )
        
        # Cleanup
        self.df.drop(columns=['id_sequence'], inplace=True, errors='ignore')
        return self
    
    def randomize_working_hours(self, start_hour: int = 8, end_hour: int = 17):
        """
        Randomize working hours for created_at timestamps with 00:00:00 time.
        
        Args:
            start_hour: Business hours start (default 8 AM)
            end_hour: Business hours end (default 5 PM)
        """
        print("🚀 Randomizing Working Hours...")
        
        # Convert to datetime if not already
        self.df['created_at'] = pd.to_datetime(self.df['created_at'])
        
        # Find rows with 00:00:00 time (midnight)
        midnight_mask = (self.df['created_at'].dt.hour == 0) & (self.df['created_at'].dt.minute == 0) & (self.df['created_at'].dt.second == 0)
        midnight_count = midnight_mask.sum()
        
        if midnight_count > 0:
            print(f"   -> Found {midnight_count} rows with 00:00:00 time")
            
            # Generate random hours and minutes for each row
            random_hours = np.random.randint(start_hour, end_hour, size=midnight_count)
            random_minutes = np.random.randint(0, 60, size=midnight_count)
            random_seconds = np.random.randint(0, 60, size=midnight_count)
            
            # Create time deltas
            time_deltas = pd.to_timedelta(
                random_hours * 3600 + random_minutes * 60 + random_seconds, 
                unit='s'
            )
            
            # Add time deltas to the dates
            self.df.loc[midnight_mask, 'created_at'] = self.df.loc[midnight_mask, 'created_at'] + time_deltas
            
            print(f"   ✅ Randomized {midnight_count} timestamps to business hours ({start_hour}:00-{end_hour}:00)")
        else:
            print("   ✅ No 00:00:00 timestamps found")
        
        return self
    
    def clean_odometer_pipeline_soft(
        self,
        df_asset_list: pd.DataFrame = None,  # Asset list with delivery dates
        assumed_daily_mileage: float = 150.0,   # rata-rata jarak tempuh per hari
        max_daily_mileage: float = 600.0,       # batas wajar konsumsi km/hari
        min_daily_mileage: float = 10.0,        # batas bawah wajar konsumsi km/hari
    ):
        """
        Soft cleaning odometer (mileage consumption), kolom wajib:
          - 'created_at'
          - 'vechicle_vin'
          - 'odometer'

        [ENHANCED] Menggunakan Delivery Date dari Asset List untuk estimasi Cold Start.
        Fokus: konsumsi jarak (mileage) per hari, BUKAN speed.
        """
        print("🚀 Cleaning Odometer (Soft Pipeline with Delivery Date)...")
        
        df = self.df.copy()

        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
        df["odometer_raw"] = pd.to_numeric(df["odometer"], errors="coerce")

        # MIN_INT64 (placeholder NULL) -> treat as missing
        MIN_INT64 = np.iinfo("int64").min
        mask_min = df["odometer_raw"] == MIN_INT64
        df["is_min_int_placeholder"] = mask_min
        df.loc[mask_min, "odometer_raw"] = np.nan

        # ===== MERGE DELIVERY DATE DARI ASSET LIST =====
        delivery_date_col = "delivery_date_internal"
        if df_asset_list is not None:
            print("   -> Merging Delivery Dates from Asset List...")
            
            # Cari kolom delivery date di asset list
            delivery_candidates = [c for c in df_asset_list.columns if 'delivery' in c.lower() or 'tanggal terima' in c.lower()]
            
            if delivery_candidates and 'VIN' in df_asset_list.columns:
                col_delivery = delivery_candidates[0]
                
                # Prepare Asset Data
                df_asset_clean = df_asset_list[['VIN', col_delivery]].copy()
                df_asset_clean['VIN'] = df_asset_clean['VIN'].astype(str).str.strip()
                df_asset_clean[col_delivery] = pd.to_datetime(df_asset_clean[col_delivery], errors='coerce')
                
                # Drop invalid dates & duplicates
                df_asset_clean = df_asset_clean.dropna(subset=[col_delivery])
                df_asset_clean = df_asset_clean.drop_duplicates(subset=['VIN'])
                
                # Prepare ELSA Key
                df['vechicle_vin'] = df['vechicle_vin'].astype(str).str.strip()
                
                # Merge
                df = pd.merge(
                    df, 
                    df_asset_clean, 
                    left_on='vechicle_vin', 
                    right_on='VIN', 
                    how='left'
                )
                
                # Rename to standard internal name
                df.rename(columns={col_delivery: delivery_date_col}, inplace=True)
                df.drop(columns=['VIN'], inplace=True, errors='ignore')
                
                match_count = df[delivery_date_col].notna().sum()
                print(f"      ✅ Matched Delivery Dates for {match_count} rows.")
            else:
                print(f"   ⚠️ Delivery date or VIN column not found in Asset List.")
                df[delivery_date_col] = pd.NaT
        else:
            df[delivery_date_col] = pd.NaT

        # ===== STANDARD CLEANING LOGIC =====
        df = df.sort_values(["vechicle_vin", "created_at"])
        df["odometer_stage1"] = df["odometer_raw"]

        # odometer negatif = invalid
        neg_mask = df["odometer_stage1"] < 0
        df.loc[neg_mask, "odometer_stage1"] = np.nan

        # ===== hitung konsumsi mileage per hari =====
        df["delta_days"] = (
            df.groupby("vechicle_vin")["created_at"]
            .diff()
            .dt.total_seconds()
            .div(86400)
        )
        df["delta_odo"] = df.groupby("vechicle_vin")["odometer_stage1"].diff()

        # ini adalah KONSUMSI MILEAGE per hari (km/hari), bukan speed
        df["daily_mileage"] = df["delta_odo"] / df["delta_days"]

        # ===== flag anomaly (berdasarkan konsumsi mileage) =====
        df["is_anomaly_rule"] = False

        # odometer mundur
        df.loc[df["delta_odo"] < 0, "is_anomaly_rule"] = True

        # konsumsi harian terlalu besar (km/hari di atas wajar)
        df.loc[df["daily_mileage"] > max_daily_mileage, "is_anomaly_rule"] = True

        # negatif / MIN_INT tadi juga dianggap anomali
        df.loc[neg_mask | mask_min, "is_anomaly_rule"] = True

        # ===== STATISTICAL OUTLIER DETECTION (IQR Method) =====
        print("   -> Detecting statistical outliers (IQR method)...")
        df["is_statistical_outlier"] = False

        for vin in df["vechicle_vin"].unique():
            mask = df["vechicle_vin"] == vin
            vehicle_values = df.loc[mask, "odometer_stage1"].dropna()
            
            if len(vehicle_values) >= 4:  # Need at least 4 values for meaningful IQR
                Q1 = vehicle_values.quantile(0.25)
                Q3 = vehicle_values.quantile(0.75)
                IQR = Q3 - Q1
                
                if IQR > 0:  # Avoid division by zero
                    lower_bound = Q1 - (3 * IQR)
                    upper_bound = Q3 + (3 * IQR)
                    
                    # Flag outliers
                    outlier_mask = (
                        mask & 
                        (
                            (df["odometer_stage1"] < lower_bound) | 
                            (df["odometer_stage1"] > upper_bound)
                        ) &
                        df["odometer_stage1"].notna()
                    )
                    df.loc[outlier_mask, "is_statistical_outlier"] = True

        statistical_outlier_count = df["is_statistical_outlier"].sum()
        print(f"   ✅ Found {statistical_outlier_count} statistical outliers")

        # Combine statistical outliers with rule-based anomalies
        df.loc[df["is_statistical_outlier"], "is_anomaly_rule"] = True

        # ===== tentukan mana yang perlu imputasi =====
        df["needs_impute"] = False
        first_idx = df.groupby("vechicle_vin").head(1).index

        zero_mid = (df["odometer_stage1"] == 0) & (~df.index.isin(first_idx))
        null_mask = df["odometer_stage1"].isna()
        anomaly_mask = df["is_anomaly_rule"]

        df.loc[zero_mid | null_mask | anomaly_mask, "needs_impute"] = True

        # ===== HELPER: Multi-Benchmark Calculator =====
        def calculate_benchmark(g, i, curr_date, delivery_date, assumed_daily_mileage):
            """
            Calculate expected odometer benchmark using fallback strategy:
            1. Delivery date (best, if available)
            2. Estimated delivery from first service
            3. Rolling average from recent services
            
            Returns benchmark odometer value or None
            """
            # Tier 1: Delivery Date (Most Accurate)
            if pd.notna(delivery_date) and pd.notna(curr_date):
                total_age_days = (curr_date - delivery_date).total_seconds() / 86400.0
                if total_age_days > 0:
                    return total_age_days * assumed_daily_mileage
            
            # Tier 2: Estimated Delivery from First Service
            if i > 0:
                first_date = g.iloc[0]["created_at"]
                first_odo = g.iloc[0]["odometer_clean"]
                
                if pd.notna(first_odo) and first_odo > 0 and pd.notna(first_date):
                    # Backward estimate: delivery ~ first_date - (first_odo / daily_avg)
                    estimated_delivery_days = first_odo / assumed_daily_mileage
                    estimated_delivery_date = first_date - pd.Timedelta(days=estimated_delivery_days)
                    
                    total_age_days = (curr_date - estimated_delivery_date).total_seconds() / 86400.0
                    if total_age_days > 0:
                        return total_age_days * assumed_daily_mileage
            
            # Tier 3: Rolling Average from Last 3-5 Services
            if i >= 3:
                # Look at last 3 cleaned values
                lookback = min(3, i)
                last_n_odo = g.iloc[i-lookback:i]["odometer_clean"]
                last_n_dates = g.iloc[i-lookback:i]["created_at"]
                
                # Check if all values are valid
                if last_n_odo.notna().all() and last_n_dates.notna().all():
                    total_increase = last_n_odo.iloc[-1] - last_n_odo.iloc[0]
                    total_days = (last_n_dates.iloc[-1] - last_n_dates.iloc[0]).total_seconds() / 86400.0
                    
                    if total_days > 0:
                        # Calculate vehicle's recent average km/day
                        recent_avg_per_day = total_increase / total_days
                        
                        # Extrapolate to current
                        days_since_last = (curr_date - last_n_dates.iloc[-1]).total_seconds() / 86400.0
                        if days_since_last > 0:
                            return last_n_odo.iloc[-1] + (days_since_last * recent_avg_per_day)
            
            # No benchmark available
            return None

        # ===== monotonic repair berdasarkan konsumsi mileage harian =====
        def repair_group(g: pd.DataFrame):
            g = g.sort_values("created_at").copy()
            g["odometer_clean"] = g["odometer_stage1"].copy()
            
            col_idx_clean = g.columns.get_loc("odometer_clean")
            
            # Ambil delivery date dari kolom internal (hasil merge)
            delivery_date = pd.NaT
            if delivery_date_col in g.columns:
                valid_dates = g[delivery_date_col].dropna()
                if not valid_dates.empty:
                    delivery_date = valid_dates.iloc[0]


            # ===== FIRST PASS: Estimate missing/anomaly values =====
            for i in range(len(g)):
                curr_odo = g.iloc[i]["odometer_clean"]
                curr_date = g.iloc[i]["created_at"]
                
                # --- LOGIC BARIS PERTAMA (i=0) - COLD START WITH VALIDATION ---
                if i == 0:
                    # If missing or zero, estimate from delivery date
                    if pd.isna(curr_odo) or curr_odo <= 0:
                        if pd.notna(delivery_date) and pd.notna(curr_date):
                            delta_days = (curr_date - delivery_date).total_seconds() / 86400.0
                            if delta_days > 0:
                                base_est = assumed_daily_mileage * delta_days
                                max_est = max_daily_mileage * delta_days
                                
                                # Add randomness (±20%)
                                random_factor = np.random.uniform(0.8, 1.2)
                                est = base_est * random_factor
                                est = float(np.round(np.clip(est, 0, max_est)))
                                g.iat[i, col_idx_clean] = est
                        continue
                    
                    # Has value (>0) - VALIDATE against next services to prevent chain error
                    if len(g) >= 3:  # Need at least 3 rows for validation
                        next_valid = []
                        next_dates = []
                        
                        # Look at next 2-3 services
                        for j in range(1, min(len(g), 4)):
                            next_odo = g.iloc[j]["odometer_stage1"]
                            next_date = g.iloc[j]["created_at"]
                            if pd.notna(next_odo) and next_odo > 0 and pd.notna(next_date):
                                next_valid.append(next_odo)
                                next_dates.append(next_date)
                        
                        if len(next_valid) >= 2:
                            median_next = np.median(next_valid)
                            
                            # CRITICAL CHECK: Is first value way higher than median of next?
                            # This catches typos like 50,000 when should be 10,000
                            if curr_odo > median_next * 1.5:  # First is 50% higher
                                # First is likely error - use backward estimate
                                first_next_odo = next_valid[0]
                                first_next_date = next_dates[0]
                                
                                days_diff = (first_next_date - curr_date).total_seconds() / 86400.0
                                if days_diff > 0:
                                    # Backward estimate with randomness
                                    random_factor = np.random.uniform(0.8, 1.2)
                                    backward_est = first_next_odo - (days_diff * assumed_daily_mileage * random_factor)
                                    backward_est = max(0, backward_est)  # Can't be negative
                                    g.iat[i, col_idx_clean] = float(np.round(backward_est))
                                    continue
                    
                    # Validation passed or not enough data to validate - KEEP
                    continue
                
                # --- LOGIC BARIS SELANJUTNYA (i>0) ---
                prev_odo = g.iloc[i - 1]["odometer_clean"]
                prev_date = g.iloc[i - 1]["created_at"]

                if pd.isna(prev_odo) or pd.isna(prev_date) or pd.isna(curr_date):
                    continue

                delta_days = (curr_date - prev_date).total_seconds() / 86400
                if delta_days <= 0 or pd.isna(delta_days):
                    delta_days = 1.0

                # --- [ENHANCED] REALITY CHECK with Multi-Benchmark ---
                # Check if RAW value is closer to expected benchmark than CLEANED previous
                should_trust_raw = False
                benchmark_odo = calculate_benchmark(g, i, curr_date, delivery_date, assumed_daily_mileage)
                
                if pd.notna(curr_odo) and benchmark_odo is not None:
                    diff_raw_benchmark = abs(curr_odo - benchmark_odo)
                    diff_clean_benchmark = abs(prev_odo - benchmark_odo)
                    
                    # If RAW is closer to reality than cleaned previous
                    if diff_raw_benchmark < diff_clean_benchmark:
                        # Minimum threshold: at least 50% of expected
                        min_wajar = benchmark_odo * 0.5
                        if curr_odo > min_wajar:
                            should_trust_raw = True

                # --- ANOMALY DETECTION ---
                monotonic_violation = False
                if pd.notna(curr_odo) and curr_odo < prev_odo:
                    monotonic_violation = True

                is_missing = pd.isna(curr_odo) or (curr_odo == 0)

                is_spike = False
                if pd.notna(curr_odo) and not is_missing:
                    speed = (curr_odo - prev_odo) / delta_days
                    if speed > max_daily_mileage:
                        is_spike = True

                # --- DECISION MAKING ---
                if should_trust_raw and (monotonic_violation or is_spike):
                    # Trust Raw, Reset Chain - raw value is closer to reality
                    g.iat[i, col_idx_clean] = float(np.round(curr_odo))
                    continue

                # Normal imputation check
                if not bool(g.iloc[i]["needs_impute"]):
                    continue

                # estimasi KONSUMSI MILEAGE (km/hari) -> odometer baru
                base_increase = assumed_daily_mileage * delta_days

                # Add randomness to the INCREASE amount (not total) to ensure monotonicity
                random_factor = np.random.uniform(0.8, 1.2)
                randomized_increase = base_increase * random_factor
                
                # Clamp the increase within min/max daily mileage
                min_increase = min_daily_mileage * delta_days
                max_increase = max_daily_mileage * delta_days
                final_increase = np.clip(randomized_increase, min_increase, max_increase)
                
                # Calculate new odometer: prev + increase (ALWAYS >= prev)
                est = prev_odo + final_increase
                est = float(np.round(est))

                g.iat[i, col_idx_clean] = est

            # ===== SECOND PASS: Enforce STRICT Monotonicity =====
            # Pastikan odometer SELALU naik, tidak pernah turun
            # NOTE: Ini akan mengubah SEMUA nilai yang turun, bahkan dari raw data
            for i in range(1, len(g)):
                curr_odo = g.iloc[i]["odometer_clean"]
                prev_odo = g.iloc[i - 1]["odometer_clean"]
                curr_date = g.iloc[i]["created_at"]
                prev_date = g.iloc[i - 1]["created_at"]
                
                # Skip jika salah satu NaN
                if pd.isna(curr_odo) or pd.isna(prev_odo):
                    # Jika current NaN tapi prev valid, estimasi dari prev
                    if pd.isna(curr_odo) and pd.notna(prev_odo) and pd.notna(curr_date) and pd.notna(prev_date):
                        delta_days = (curr_date - prev_date).total_seconds() / 86400
                        if delta_days <= 0 or pd.isna(delta_days):
                            delta_days = 1.0
                        
                        # Add randomness to increase amount for natural values
                        base_increase = assumed_daily_mileage * delta_days
                        random_factor = np.random.uniform(0.8, 1.2)
                        randomized_increase = base_increase * random_factor
                        
                        min_increase = min_daily_mileage * delta_days
                        max_increase = max_daily_mileage * delta_days
                        final_increase = np.clip(randomized_increase, min_increase, max_increase)
                        
                        est = prev_odo + final_increase
                        est = float(np.round(est))
                        g.iat[i, col_idx_clean] = est
                    continue
                
                # Jika odometer turun atau sama, SELALU estimasi ulang untuk monotonicity
                if curr_odo <= prev_odo:
                    delta_days = (curr_date - prev_date).total_seconds() / 86400
                    if delta_days <= 0 or pd.isna(delta_days):
                        delta_days = 1.0
                    
                    # Estimasi monotonic - SELALU minimal prev_odo + min_daily
                    # Add randomness to increase amount for natural values
                    base_increase = assumed_daily_mileage * delta_days
                    random_factor = np.random.uniform(0.8, 1.2)
                    randomized_increase = base_increase * random_factor
                    
                    min_increase = min_daily_mileage * delta_days
                    max_increase = max_daily_mileage * delta_days
                    final_increase = np.clip(randomized_increase, min_increase, max_increase)
                    
                    est = prev_odo + final_increase
                    est = float(np.round(est))
                    
                    g.iat[i, col_idx_clean] = est

            # ===== THIRD PASS: Post-Repair Validation (Cap Extreme Increases) =====
            # Even if monotonic, prevent unrealistic jumps (e.g., 20k -> 280k)
            for i in range(1, len(g)):
                curr_odo = g.iloc[i]["odometer_clean"]
                prev_odo = g.iloc[i - 1]["odometer_clean"]
                curr_date = g.iloc[i]["created_at"]
                prev_date = g.iloc[i - 1]["created_at"]
                
                if pd.isna(curr_odo) or pd.isna(prev_odo) or pd.isna(curr_date) or pd.isna(prev_date):
                    continue
                
                delta_days = (curr_date - prev_date).total_seconds() / 86400
                if delta_days <= 0 or pd.isna(delta_days):
                    delta_days = 1.0
                
                # Calculate actual increase
                actual_increase = curr_odo - prev_odo
                expected_increase = assumed_daily_mileage * delta_days
                
                # If increase is TOO extreme (>3x expected), cap it
                if actual_increase > (expected_increase * 3):
                    # Cap to max allowed increase
                    max_allowed_increase = max_daily_mileage * delta_days
                    capped_odo = prev_odo + max_allowed_increase
                    g.iat[i, col_idx_clean] = float(np.round(capped_odo))

            return g

        df = df.groupby("vechicle_vin", group_keys=False).apply(repair_group)
        
        # ===== DEBUG LOG: DELIVERY DATE IMPACT =====
        print("\n" + "="*50)
        print("   [DEBUG] DELIVERY DATE IMPACT ON FIRST SERVICES")
        print("="*50)
        if delivery_date_col in df.columns:
            first_rows = df.groupby("vechicle_vin").head(1)
            # Cek baris pertama yang Odo Raw-nya kosong tapi Odo Clean-nya terisi
            rescued = first_rows[
                (first_rows["odometer_raw"].isna() | (first_rows["odometer_raw"] == 0)) &
                (first_rows["odometer_clean"] > 0)
            ]
            print(f"   First Service Rows Rescued by Delivery Date: {len(rescued)}")
            if not rescued.empty and len(rescued) <= 10:
                cols_show = ['vechicle_vin', delivery_date_col, 'created_at', 'odometer_raw', 'odometer_clean']
                print("\n" + rescued[cols_show].to_string(index=False))
            elif len(rescued) > 10:
                print(f"   (Showing first 5 of {len(rescued)} rescued rows)")
                cols_show = ['vechicle_vin', delivery_date_col, 'created_at', 'odometer_raw', 'odometer_clean']
                print("\n" + rescued[cols_show].head(5).to_string(index=False))
        else:
            print("   ⚠️ Delivery Date column NOT FOUND. Skipped cold start estimation.")
        print("="*50 + "\n")
        
        # Update self.df dengan odometer yang sudah dibersihkan
        self.df['odometer'] = df['odometer_clean'].fillna(df['odometer_raw']).fillna(0).astype('int64')
        
        total_imputed = df['needs_impute'].sum()
        print(f"   ✅ Odometer cleaned. Total imputed: {total_imputed} values.")
        return self

    def normalize_total_price(self):
        """
        Normalizes total_price column.
        - Handles 'K' suffix (100K -> 100000)
        - Handles shorthand (100 -> 100000) for values < 10000
        - Cleans regex (Rp, ./,/-)
        """
        print("   -> Normalizing Total Price...")
        if 'total_price' not in self.df.columns:
            return self

        def _clean_price(val):
            if pd.isna(val): return None
            s = str(val).strip().lower()
            
            # Handle 'k' multiplier
            multiplier = 1
            if 'k' in s:
                multiplier = 1000
                s = s.replace('k', '')
            
            # Remove non-digits
            digits = re.sub(r'[^0-9]', '', s)
            if not digits: return None
            
            try:
                num = int(digits) * multiplier
                # Heuristic Tier:
                # 1. If < 1000 (1-3 digits): shorthand, *1000 (e.g. 100->100k)
                # 2. If 1000 <= num < 10000 (4 digits): add 0 to make 5 digit, *10 (e.g. 5000->50k)
                # 3. If >= 10000: keep (5-6 digits)
                
                if 0 < num < 1000:
                    num *= 1000
                elif 1000 <= num < 10000:
                    num *= 10
                
                return num
            except:
                return None

        self.df['total_price'] = self.df['total_price'].apply(_clean_price).fillna(0).astype(int)
        return self

    def get_results(self):
        return self.df, self.bad_data
