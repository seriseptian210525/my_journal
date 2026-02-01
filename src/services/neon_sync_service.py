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
    explode_rows
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
        self.data_loader = DataLoader()
    
    def get_max_pergantian_ke(self) -> pd.DataFrame:
        """
        Get MAX pergantian_ke per (vehicle_plate, sku) from Neon.
        Used for offset calculation in incremental mode.
        """
        query = """
        SELECT vehicle_plate, sku, MAX(pergantian_ke) as max_pk
        FROM unified_part_logs
        GROUP BY vehicle_plate, sku
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
            exploded_df.sort_values(by=['vehicle_plate', 'sku', 'created_at'], inplace=True)
            
            # --- SMART PERGANTIAN KE CALCULATION ---
            # Calculate local cumcount first
            exploded_df['local_pk'] = exploded_df.groupby(['vehicle_plate', 'sku']).cumcount() + 1
            
            # Merge with offset
            if not offset_df.empty:
                exploded_df = pd.merge(
                    exploded_df,
                    offset_df,
                    on=['vehicle_plate', 'sku'],
                    how='left'
                )
                exploded_df['max_pk'] = exploded_df['max_pk'].fillna(0).astype(int)
                exploded_df['pergantian_ke'] = exploded_df['max_pk'] + exploded_df['local_pk']
                exploded_df.drop(columns=['max_pk', 'local_pk'], inplace=True)
            else:
                exploded_df['pergantian_ke'] = exploded_df['local_pk']
                exploded_df.drop(columns=['local_pk'], inplace=True)
            
            # Deduplication
            key_cols = ['source_system', 'order_number', 'sku', 'item_name', 'pergantian_ke']
            exploded_df = exploded_df.drop_duplicates(subset=key_cols, keep='first')
            
            # --- INSERT TO NEON ---
            if not exploded_df.empty:
                self.loader.load_df_append(exploded_df, 'unified_part_logs')
                stats['total_inserted'] = len(exploded_df)
            
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
            if filters.get('vehicle_plate'):
                where_clauses.append("vehicle_plate ILIKE :plate")
                params['plate'] = f"%{filters['vehicle_plate']}%"
            
            if filters.get('item_name'):
                where_clauses.append("item_name ILIKE :item")
                params['item'] = f"%{filters['item_name']}%"
            
            if filters.get('customer_type'):
                where_clauses.append("customer_type ILIKE :cust")
                params['cust'] = f"%{filters['customer_type']}%"
            
            if filters.get('warranty_status'):
                where_clauses.append("warranty_status = :warranty")
                params['warranty'] = filters['warranty_status']
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # Count query
        count_query = f"SELECT COUNT(*) FROM unified_part_logs WHERE {where_sql}"
        total_count = self.loader.fetch_df(count_query, params).iloc[0, 0]
        
        # Data query with pagination
        offset = (page - 1) * page_size
        data_query = f"""
        SELECT 
            created_at, source_system, order_number, vehicle_plate, 
            sku, item_name, bike_type, customer_type, 
            quantity, final_price, warranty_status, pergantian_ke, odometer
        FROM unified_part_logs 
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT {page_size} OFFSET {offset}
        """
        
        df = self.loader.fetch_df(data_query, params)
        
        return df, total_count
    
    def get_cohort_data(self, vehicle_plate: str = None) -> pd.DataFrame:
        """
        Get cohort data for heatmap visualization.
        Shows pergantian_ke timeline per vehicle+sku.
        """
        query = """
        SELECT 
            vehicle_plate,
            sku,
            item_name,
            DATE_TRUNC('month', created_at) as month,
            pergantian_ke,
            final_price
        FROM unified_part_logs
        WHERE vehicle_plate IS NOT NULL
        """
        
        if vehicle_plate:
            query += f" AND vehicle_plate ILIKE '%{vehicle_plate}%'"
        
        query += " ORDER BY vehicle_plate, sku, created_at"
        
        return self.loader.fetch_df(query)
    
    def get_cost_per_km_data(self) -> pd.DataFrame:
        """
        Get cost/km data for chart visualization.
        """
        query = """
        SELECT 
            vehicle_plate,
            bike_type,
            SUM(final_price) as total_cost,
            MAX(odometer) - MIN(odometer) as km_traveled,
            COUNT(*) as service_count
        FROM unified_part_logs
        WHERE odometer > 0
        GROUP BY vehicle_plate, bike_type
        HAVING MAX(odometer) - MIN(odometer) > 0
        ORDER BY SUM(final_price) / NULLIF(MAX(odometer) - MIN(odometer), 0) DESC
        LIMIT 100
        """
        
        df = self.loader.fetch_df(query)
        if not df.empty:
            df['cost_per_km'] = df['total_cost'] / df['km_traveled']
        return df
