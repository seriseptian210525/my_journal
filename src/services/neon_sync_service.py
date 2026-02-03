"""
Neon Sync Service - Triggered from Streamlit UI
Supports smart incremental sync with Pergantian Ke offset.
"""
import os
import sys
from pathlib import Path
import pandas as pd
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
    calculate_warranty_coverage
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
        self._data_loader = None  # Lazy load - only needed for sync
    
    @property
    def data_loader(self):
        """Lazy load DataLoader only when needed (requires Google credentials)."""
        if self._data_loader is None:
            self._data_loader = DataLoader()
        return self._data_loader
    
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
            # This ensures Service Items and Part Usage don't block each other
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
            
            # --- SERVICE ITEMS (Filter by SI's own max_date) ---
            raw_si = self.data_loader.load_gspread_data(SHEET_ID_SERVICE_ITEMS, WORKSHEET_SERVICE_ITEMS)
            if not raw_si.empty:
                raw_si['created_at'] = pd.to_datetime(raw_si['created_at'], errors='coerce')
                if max_date_filter_si:
                    raw_si = raw_si[raw_si['created_at'] > max_date_filter_si]
                
                if not raw_si.empty:
                    si_df = standardize_service_items(raw_si, asset_df=asset_df, mapping_df=mapping_df)
                    stats['service_items_new'] = len(si_df)
                else:
                    si_df = pd.DataFrame()
            else:
                si_df = pd.DataFrame()
            
            # --- PART USAGE (Filter by PU's own max_date) ---
            raw_pu = self.data_loader.load_gspread_data(SHEET_ID_OUTPUT_REVIEW, WORKSHEET_PART_USAGE)
            if not raw_pu.empty:
                raw_pu['created_at'] = pd.to_datetime(raw_pu['created_at'], errors='coerce')
                if max_date_filter_pu:
                    raw_pu = raw_pu[raw_pu['created_at'] > max_date_filter_pu]
                
                if not raw_pu.empty:
                    pu_df = standardize_part_usage(raw_pu, asset_df=asset_df, mapping_df=mapping_df)
                    stats['part_usage_new'] = len(pu_df)
                else:
                    pu_df = pd.DataFrame()
            else:
                pu_df = pd.DataFrame()
            
            # --- MERGE & TRANSFORM ---
            if si_df.empty and pu_df.empty:
                stats['status'] = 'no_new_data'
                return stats
            
            # Create unified_df by merging Service Items and Part Usage
            unified_df = pd.concat([si_df, pu_df], ignore_index=True)

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
            
            # --- INSERT TO NEON ---
            if not final_df.empty:
                self.loader.load_df_append(final_df, 'unified_part_logs')
                stats['total_inserted'] = len(final_df)
            
            stats['status'] = 'success'
            
        except Exception as e:
            stats['status'] = 'error'
            stats['error'] = str(e)
        
        return stats
    
    def get_data_for_display(self, filters: dict = None, page: int = 1, page_size: int = 50) -> tuple:
        """
        Get data from Neon for Streamlit display with filters and pagination.
        Returns (dataframe, total_count).
        """
        # Build WHERE clause
        where_clauses = []
        params = {}
        
        if filters:
            if filters.get('vehicle_plate') and filters['vehicle_plate'] != 'All':
                where_clauses.append("vehicle_plate = :plate")
                params['plate'] = filters['vehicle_plate']
            
            if filters.get('order_number'):
                where_clauses.append("order_number ILIKE :order")
                params['order'] = f"%{filters['order_number']}%"
            
            if filters.get('service_location_name') and filters['service_location_name'] != 'All':
                where_clauses.append("service_location_name = :location")
                params['location'] = filters['service_location_name']
            
            if filters.get('item_name') and filters['item_name'] != 'All':
                where_clauses.append("item_name = :item")
                params['item'] = filters['item_name']
            
            if filters.get('customer_type') and filters['customer_type'] != 'All':
                where_clauses.append("customer_type = :cust")
                params['cust'] = filters['customer_type']
            
            if filters.get('warranty_coverage') and filters['warranty_coverage'] != 'All':
                where_clauses.append("warranty_coverage = :warranty")
                params['warranty'] = filters['warranty_coverage']
            
            if filters.get('sku') and filters['sku'] != 'All':
                where_clauses.append("sku = :sku")
                params['sku'] = filters['sku']
                
            # Date Range Filters
            if filters.get('start_date'):
                where_clauses.append("created_at >= :start_date")
                params['start_date'] = filters['start_date']
            
            if filters.get('end_date'):
                where_clauses.append("created_at <= :end_date")
                params['end_date'] = filters['end_date']
            
            # Location Category Filter (3-Tier: B2B / Internal / Official Partner)
            # Internal = Pondok Indah, Kembangan, Depok, Bekasi
            if filters.get('location_category'):
                cat = filters['location_category']
                if cat == 'B2B Repair':
                    where_clauses.append("service_location_name ILIKE '%GRAB%'")
                elif cat == 'Internal Repair':
                    where_clauses.append("""(
                        service_location_name ILIKE '%Pondok Indah%' OR
                        service_location_name ILIKE '%Kembangan%' OR
                        service_location_name ILIKE '%Depok%' OR
                        service_location_name ILIKE '%Bekasi%'
                    )""")
                elif cat == 'Official Partner':
                    where_clauses.append("""(
                        service_location_name NOT ILIKE '%GRAB%'
                        AND service_location_name NOT ILIKE '%Pondok Indah%'
                        AND service_location_name NOT ILIKE '%Kembangan%'
                        AND service_location_name NOT ILIKE '%Depok%'
                        AND service_location_name NOT ILIKE '%Bekasi%'
                    )""")
            
            # Exclude specific SKUs (for Prime Input filter)
            if filters.get('exclude_skus'):
                excluded = filters['exclude_skus']
                placeholders = ", ".join([f":exclude_sku_{i}" for i in range(len(excluded))])
                where_clauses.append(f"sku NOT IN ({placeholders})")
                for i, sku_val in enumerate(excluded):
                    params[f'exclude_sku_{i}'] = sku_val
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # Count query
        count_query = f"SELECT COUNT(*) FROM unified_part_logs WHERE {where_sql}"
        total_count = self.loader.fetch_df(count_query, params).iloc[0, 0]
        
        # Data query with pagination
        offset = (page - 1) * page_size
        
        # Use COALESCE/NULL handling if columns might be missing initially, but let's assume they exist per plan
        data_query = f"""
        SELECT 
            created_at, source_system, order_number, vehicle_plate, 
            sku, item_name, bike_type, customer_type, 
            quantity, final_price, 
            subtotal_price, old_price, 
            warranty_coverage as warranty_status, -- Display coverage as warranty status
            pergantian_ke_total, pergantian_ke_yearly, odometer,
            service_location_name
        FROM unified_part_logs 
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT {page_size} OFFSET {offset}
        """
        
        df = self.loader.fetch_df(data_query, params)
        
        return df, total_count

    def get_filter_options(self) -> dict:
        """Get unique options for filters from database."""
        options = {}
        try:
            # 1. Vehicle Plates (Top 1000 active/recent)
            plate_query = "SELECT DISTINCT vehicle_plate FROM unified_part_logs WHERE vehicle_plate IS NOT NULL ORDER BY vehicle_plate"
            options['vehicle_plate'] = self.loader.fetch_df(plate_query)['vehicle_plate'].tolist()
            
            # 2. Item Names
            item_query = "SELECT DISTINCT item_name FROM unified_part_logs WHERE item_name IS NOT NULL ORDER BY item_name"
            options['item_name'] = self.loader.fetch_df(item_query)['item_name'].tolist()
            
            # 3. Customer Type
            cust_query = "SELECT DISTINCT customer_type FROM unified_part_logs WHERE customer_type IS NOT NULL ORDER BY customer_type"
            options['customer_type'] = self.loader.fetch_df(cust_query)['customer_type'].tolist()
            
            # 4. Warranty Coverage
            warranty_query = "SELECT DISTINCT warranty_coverage FROM unified_part_logs WHERE warranty_coverage IS NOT NULL ORDER BY warranty_coverage"
            options['warranty_coverage'] = self.loader.fetch_df(warranty_query)['warranty_coverage'].tolist()
            
            # 5. SKU
            sku_query = "SELECT DISTINCT sku FROM unified_part_logs WHERE sku IS NOT NULL ORDER BY sku"
            options['sku'] = self.loader.fetch_df(sku_query)['sku'].tolist()
            
            # 6. Service Location
            loc_query = "SELECT DISTINCT service_location_name FROM unified_part_logs WHERE service_location_name IS NOT NULL ORDER BY service_location_name"
            options['service_location_name'] = self.loader.fetch_df(loc_query)['service_location_name'].tolist()
            
        except Exception as e:
            print(f"⚠️ Error loading filter options: {e}")
            # Return empty lists on error
            options = {k: [] for k in ['vehicle_plate', 'item_name', 'customer_type', 'warranty_coverage', 'sku', 'service_location_name']}
            
        return options
    
    def get_tire_cohort_data(self, filters: dict = None) -> pd.DataFrame:
        """
        Get Tire Cost Analysis data with GEL vs Non-GEL comparison.
        Joins with Asset List to get delivery_date and initial_odometer.
        
        Logic:
        1. Query unified_part_logs for items containing 'Tire' or 'Ban'.
        2. Join with Asset List on vehicle_plate.
        3. Calculate duration_months = (created_at - delivery_date) / 30.44
        4. Calculate odometer_diff = odometer - delivery_odometer (default 0)
        """
        where_clauses = ["(item_name ILIKE '%Tire%' OR item_name ILIKE '%Ban%')"]
        params = {}
        
        if filters:
            if filters.get('vehicle_plate') and filters['vehicle_plate'] != 'All':
                where_clauses.append("vehicle_plate = :plate")
                params['plate'] = filters['vehicle_plate']
            
            # Start/End date filters for replacement date
            if filters.get('start_date'):
                where_clauses.append("created_at >= :start_date")
                params['start_date'] = filters['start_date']
            
            if filters.get('end_date'):
                where_clauses.append("created_at <= :end_date")
                params['end_date'] = filters['end_date']

        where_sql = " AND ".join(where_clauses)

        query = f"""
        SELECT 
            vehicle_plate,
            sku,
            item_name,
            customer_type,
            pergantian_ke_total,
            final_price,
            odometer,
            created_at,
            DATE(created_at) as replacement_date
        FROM unified_part_logs
        WHERE {where_sql}
        ORDER BY vehicle_plate, created_at
        """
        
        # 1. Fetch Logs data
        logs_df = self.loader.fetch_df(query, params)
        if logs_df.empty:
            return pd.DataFrame()

        # 2. Fetch Asset List for Delivery Date & Odometer
        try:
            asset_df = self.data_loader.load_gspread_data(SHEET_ID_ASSET_LIST, WORKSHEET_ASSET)
            
            if not asset_df.empty:
                # Prepare Asset data (Plate, Delivery Date, Delivery Odometer)
                asset_clean = asset_df.copy()
                
                # Normalize Plate
                plate_col = next((c for c in ['Plat Nomor', 'Plate Number', 'vehicle_license_plate'] if c in asset_clean.columns), None)
                date_col = next((c for c in ['Delivery - Outbone', 'Delivery Date', 'delivery_date'] if c in asset_clean.columns), None)
                odo_col = next((c for c in ['Delivery Odometer', 'Initial Odometer'] if c in asset_clean.columns), None) # Fallback to 0 if missing
                
                if plate_col and date_col:
                    asset_clean['join_plate'] = asset_clean[plate_col].astype(str).str.strip().str.upper().str.replace(' ', '')
                    asset_clean['delivery_date'] = pd.to_datetime(asset_clean[date_col], errors='coerce')
                    
                    if odo_col:
                        # Vectorized cleanup for Odometer
                        asset_clean['delivery_odometer'] = pd.to_numeric(
                            asset_clean[odo_col].astype(str).str.replace(',', '').str.replace(r'[^\d.-]', '', regex=True), 
                            errors='coerce'
                        ).fillna(0)
                    else:
                        asset_clean['delivery_odometer'] = 0
                        
                    # Deduplicate by plate
                    asset_clean = asset_clean.sort_values('delivery_date').drop_duplicates(subset=['join_plate'], keep='last')
                    
                    # 3. Join
                    logs_df['join_plate'] = logs_df['vehicle_plate'].astype(str).str.strip().str.upper().str.replace(' ', '')
                    merged = pd.merge(logs_df, asset_clean[['join_plate', 'delivery_date', 'delivery_odometer']], on='join_plate', how='left')
                    
                    # 4. Calculate Metrics
                    merged['created_at'] = pd.to_datetime(merged['created_at'])
                    merged['duration_months'] = ((merged['created_at'] - merged['delivery_date']).dt.days / 30.44).fillna(0).round(1)
                    
                    # Ensure positive duration (if data issue where replacement < delivery, set to 0)
                    merged['duration_months'] = merged['duration_months'].apply(lambda x: max(0, x))
                    
                    merged['current_odometer'] = pd.to_numeric(merged['odometer'], errors='coerce').fillna(0)
                    merged['odometer_diff'] = merged['current_odometer'] - merged['delivery_odometer'].fillna(0)
                    merged['odometer_diff'] = merged['odometer_diff'].apply(lambda x: max(0, x))
                    
                    # Categorize GEL vs Non-GEL
                    merged['customer_category'] = np.where(
                        merged['customer_type'].astype(str).str.strip().str.upper() == 'GEL',
                        'GEL',
                        'NON-GEL'
                    )
                    
                    return merged
                
        except Exception as e:
            print(f"⚠️ Error fetching Asset List or processing Tire data: {e}")
            pass
            
        # Fallback if asset join fails: return basic data without calculated metrics
        logs_df['duration_months'] = 0
        logs_df['odometer_diff'] = 0
        logs_df['delivery_date'] = pd.NaT
        logs_df['customer_category'] = np.where(logs_df['customer_type'].astype(str) == 'GEL', 'GEL', 'NON-GEL')
        
        return logs_df
    
    def get_cost_per_km_data(self, filters: dict = None) -> pd.DataFrame:
        """
        Get cost/km data for chart visualization.
        Apply filters including dates.
        """
        where_clauses = ["odometer > 0"]
        params = {}
        
        if filters:
            if filters.get('start_date'):
                where_clauses.append("created_at >= :start_date")
                params['start_date'] = filters['start_date']
            
            if filters.get('end_date'):
                where_clauses.append("created_at <= :end_date")
                params['end_date'] = filters['end_date']
            
            # Also apply other filters if relevant for context
            if filters.get('vehicle_plate') and filters['vehicle_plate'] != 'All':
                where_clauses.append("vehicle_plate = :plate")
                params['plate'] = filters['vehicle_plate']
        
        where_sql = " AND ".join(where_clauses)
        
        query = f"""
        SELECT 
            vehicle_plate,
            bike_type,
            SUM(final_price) as total_cost,
            MAX(odometer) - MIN(odometer) as km_traveled,
            COUNT(*) as service_count
        FROM unified_part_logs
        WHERE {where_sql}
        GROUP BY vehicle_plate, bike_type
        HAVING MAX(odometer) - MIN(odometer) > 0
        ORDER BY SUM(final_price) / NULLIF(MAX(odometer) - MIN(odometer), 0) DESC
        LIMIT 100
        """
        
        df = self.loader.fetch_df(query, params)
        if not df.empty:
            df['cost_per_km'] = df['total_cost'] / df['km_traveled']
        return df
