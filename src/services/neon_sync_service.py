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
    
    def get_max_pergantian_ke(self) -> pd.DataFrame:
        """
        Get MAX pergantian_ke per (vehicle_plate, sku, year_cycle) from Neon.
        Used for offset calculation in incremental mode.
        """
        query = """
        SELECT vehicle_plate, sku, year_cycle, MAX(pergantian_ke) as max_pk
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
            # Get last sync timestamp
            max_date = self.get_max_created_at()
            if max_date:
                max_date_filter = pd.to_datetime(max_date).tz_localize(None)
            else:
                max_date_filter = None
            
            # Get existing pergantian_ke offsets
            offset_df = self.get_max_pergantian_ke()
            
            # Load auxiliary data
            asset_df = self.data_loader.load_gspread_data(SHEET_ID_ASSET_LIST, WORKSHEET_ASSET)
            mapping_df = self.data_loader.load_gspread_data(SHEET_ID_MAPPINGS, WORKSHEET_MAPPINGS)
            
            # --- SERVICE ITEMS ---
            raw_si = self.data_loader.load_gspread_data(SHEET_ID_SERVICE_ITEMS, WORKSHEET_SERVICE_ITEMS)
            if not raw_si.empty:
                raw_si['created_at'] = pd.to_datetime(raw_si['created_at'], errors='coerce')
                if max_date_filter:
                    raw_si = raw_si[raw_si['created_at'] > max_date_filter]
                
                if not raw_si.empty:
                    si_df = standardize_service_items(raw_si, asset_df=asset_df, mapping_df=mapping_df)
                    stats['service_items_new'] = len(si_df)
                else:
                    si_df = pd.DataFrame()
            else:
                si_df = pd.DataFrame()
            
            # --- PART USAGE ---
            raw_pu = self.data_loader.load_gspread_data(SHEET_ID_OUTPUT_REVIEW, WORKSHEET_PART_USAGE)
            if not raw_pu.empty:
                raw_pu['created_at'] = pd.to_datetime(raw_pu['created_at'], errors='coerce')
                if max_date_filter:
                    raw_pu = raw_pu[raw_pu['created_at'] > max_date_filter]
                
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
            
            unified_df = pd.concat([si_df, pu_df], ignore_index=True)
            unified_df['created_at'] = pd.to_datetime(unified_df['created_at'])
            unified_df.sort_values(by=['created_at'], inplace=True)
            
            # Explode rows
            exploded_df = explode_rows(unified_df)
            
            # Sort by created_at (ASC) - Critical for chronological calculations
            exploded_df['created_at'] = pd.to_datetime(exploded_df['created_at'])
            exploded_df.sort_values(by=['created_at'], ascending=True, inplace=True)
            
            # --- PASS 1: ENRICHMENT (Bulan Ke, Year Cycle) ---
            # Call with skip_sequence_calc=True to only get Year Cycle and Config
            print("   🛡️ Pass 1: Enriching Warranty Data...")
            enriched_df = calculate_warranty_coverage(exploded_df, asset_df=asset_df, mapping_df=mapping_df, skip_sequence_calc=True)
            
            # --- SMART PERGANTIAN KE CALCULATION (INCREMENTAL) ---
            # Calculate local cumcount
            enriched_df['local_pk'] = enriched_df.groupby(['vehicle_plate', 'sku', 'year_cycle']).cumcount() + 1
            
            # Merge with offset
            # Ensure year_cycle is int
            if 'year_cycle' in enriched_df.columns:
                enriched_df['year_cycle'] = enriched_df['year_cycle'].fillna(0).astype(int)
            
            if not offset_df.empty:
                # Ensure types match for merge
                if 'year_cycle' in offset_df.columns:
                    offset_df['year_cycle'] = offset_df['year_cycle'].fillna(0).astype(int)
                
                enriched_df = pd.merge(
                    enriched_df,
                    offset_df,
                    on=['vehicle_plate', 'sku', 'year_cycle'],
                    how='left'
                )
                enriched_df['max_pk'] = enriched_df['max_pk'].fillna(0).astype(int)
                enriched_df['pergantian_ke'] = enriched_df['max_pk'] + enriched_df['local_pk']
                enriched_df.drop(columns=['max_pk', 'local_pk'], inplace=True)
            else:
                enriched_df['pergantian_ke'] = enriched_df['local_pk']
                enriched_df.drop(columns=['local_pk'], inplace=True)
            
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
                'warranty_type', 'covered_for', 'limit_per_year', 'pergantian_ke', 'warranty_coverage'
            ]
            
            # Add missing columns with defaults
            for col in final_columns:
                if col not in final_enriched_df.columns:
                    final_enriched_df[col] = None
            
            final_df = final_enriched_df[final_columns].copy()

            # Deduplication
            key_cols = ['source_system', 'order_number', 'sku', 'item_name', 'year_cycle', 'pergantian_ke']
            final_df = final_df.drop_duplicates(subset=key_cols, keep='first')
            
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
            
            if filters.get('item_name') and filters['item_name'] != 'All':
                where_clauses.append("item_name = :item")
                params['item'] = filters['item_name']
            
            if filters.get('customer_type') and filters['customer_type'] != 'All':
                where_clauses.append("customer_type = :cust")
                params['cust'] = filters['customer_type']
            
            if filters.get('warranty_coverage') and filters['warranty_coverage'] != 'All':
                where_clauses.append("warranty_coverage = :warranty")
                params['warranty'] = filters['warranty_coverage']
                
            # Date Range Filters
            if filters.get('start_date'):
                where_clauses.append("created_at >= :start_date")
                params['start_date'] = filters['start_date']
            
            if filters.get('end_date'):
                where_clauses.append("created_at <= :end_date")
                params['end_date'] = filters['end_date']
        
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
            pergantian_ke, odometer
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
            
        except Exception as e:
            print(f"⚠️ Error loading filter options: {e}")
            # Return empty lists on error
            options = {k: [] for k in ['vehicle_plate', 'item_name', 'customer_type', 'warranty_coverage']}
            
        return options
    
    def get_cohort_data(self, filters: dict = None) -> pd.DataFrame:
        """
        Get cohort data for heatmap visualization.
        Shows pergantian_ke timeline per vehicle+sku.
        Apply all filters including dates.
        """
        where_clauses = ["vehicle_plate IS NOT NULL"]
        params = {}
        
        if filters:
            if filters.get('vehicle_plate') and filters['vehicle_plate'] != 'All':
                where_clauses.append("vehicle_plate = :plate")
                params['plate'] = filters['vehicle_plate']
            
            # Additional filters for charts
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
            DATE_TRUNC('month', created_at) as month,
            pergantian_ke,
            final_price,
            odometer,
            warranty_coverage,
            created_at
        FROM unified_part_logs
        WHERE {where_sql}
        ORDER BY vehicle_plate, sku, created_at
        """
        
        return self.loader.fetch_df(query, params)
    
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
