"""
Prime Input Tracking Service
============================
Reusable service for tracking "primed" status of records.
Can be used with Streamlit, Django, FastAPI, or any Python project.

Usage:
    from src.services.prime_tracking_service import PrimeTrackingService
    
    service = PrimeTrackingService()
    
    # Mark as primed
    service.set_primed("ORDER-123", "SKU-001", "B 1234 XYZ", True)
    
    # Check status
    is_primed = service.is_primed("ORDER-123", "SKU-001", "B 1234 XYZ")
    
    # Get all primed records
    primed_df = service.get_all_primed()
"""

import os
from datetime import datetime
from typing import Optional, List, Dict
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# Try to load from dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class PrimeTrackingService:
    """
    Framework-agnostic service for tracking Prime Input status.
    Stores data in a separate `prime_input_tracking` table.
    """
    
    TABLE_NAME = "prime_input_tracking"
    
    def __init__(self, connection_string: str = None):
        """
        Initialize the service.
        
        Args:
            connection_string: Database connection string. 
                              If None, uses NEON_DB_CONNECTION_STRING env var.
        """
        self.connection_string = connection_string or os.getenv('NEON_DB_CONNECTION_STRING')
        if not self.connection_string:
            raise ValueError("Database connection string required. Set NEON_DB_CONNECTION_STRING or pass directly.")
        
        self.engine = create_engine(self.connection_string, pool_pre_ping=True)
    
    def init_table(self) -> bool:
        """
        Create the tracking table if it doesn't exist.
        Returns True if successful.
        """
        create_sql = f"""
        CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
            id SERIAL PRIMARY KEY,
            order_number VARCHAR(100) NOT NULL,
            sku VARCHAR(100) NOT NULL,
            vehicle_plate VARCHAR(50) NOT NULL,
            is_primed BOOLEAN DEFAULT FALSE,
            primed_at TIMESTAMP,
            primed_by VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW(),
            notes TEXT,
            UNIQUE(order_number, sku, vehicle_plate)
        );
        
        CREATE INDEX IF NOT EXISTS idx_prime_tracking_composite 
        ON {self.TABLE_NAME}(order_number, sku, vehicle_plate);
        
        CREATE INDEX IF NOT EXISTS idx_prime_tracking_primed 
        ON {self.TABLE_NAME}(is_primed);
        """
        try:
            with self.engine.begin() as conn:
                conn.execute(text(create_sql))
            return True
        except SQLAlchemyError as e:
            print(f"Error creating table: {e}")
            return False
    
    def set_primed(self, order_number: str, sku: str, vehicle_plate: str, 
                   is_primed: bool, primed_by: str = None, notes: str = None) -> bool:
        """
        Set or update the primed status for a record.
        Uses UPSERT (INSERT ON CONFLICT UPDATE).
        
        Args:
            order_number: Order number
            sku: SKU code
            vehicle_plate: Vehicle plate number
            is_primed: True/False status
            primed_by: Optional username who marked it
            notes: Optional notes
            
        Returns:
            True if successful
        """
        upsert_sql = text(f"""
            INSERT INTO {self.TABLE_NAME} 
                (order_number, sku, vehicle_plate, is_primed, primed_at, primed_by, notes)
            VALUES 
                (:order_number, :sku, :vehicle_plate, :is_primed, :primed_at, :primed_by, :notes)
            ON CONFLICT (order_number, sku, vehicle_plate) 
            DO UPDATE SET 
                is_primed = EXCLUDED.is_primed,
                primed_at = EXCLUDED.primed_at,
                primed_by = EXCLUDED.primed_by,
                notes = EXCLUDED.notes
        """)
        
        try:
            with self.engine.begin() as conn:
                conn.execute(upsert_sql, {
                    'order_number': order_number,
                    'sku': sku,
                    'vehicle_plate': vehicle_plate,
                    'is_primed': is_primed,
                    'primed_at': datetime.now() if is_primed else None,
                    'primed_by': primed_by,
                    'notes': notes
                })
            return True
        except SQLAlchemyError as e:
            print(f"Error setting primed status: {e}")
            return False
    
    def is_primed(self, order_number: str, sku: str, vehicle_plate: str) -> bool:
        """
        Check if a record is marked as primed.
        
        Returns:
            True if primed, False otherwise
        """
        query = text(f"""
            SELECT is_primed FROM {self.TABLE_NAME}
            WHERE order_number = :order_number 
            AND sku = :sku 
            AND vehicle_plate = :vehicle_plate
        """)
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(query, {
                    'order_number': order_number,
                    'sku': sku,
                    'vehicle_plate': vehicle_plate
                }).fetchone()
                return result[0] if result else False
        except SQLAlchemyError:
            return False
    
    def get_primed_status_bulk(self, records: List[Dict]) -> Dict[str, bool]:
        """
        Get primed status for multiple records at once.
        
        Args:
            records: List of dicts with keys: order_number, sku, vehicle_plate
            
        Returns:
            Dict mapping "order_number|sku|plate" to is_primed status
        """
        if not records:
            return {}
        
        # Build composite keys for lookup
        keys = [(r['order_number'], r['sku'], r['vehicle_plate']) for r in records]
        
        query = text(f"""
            SELECT order_number, sku, vehicle_plate, is_primed 
            FROM {self.TABLE_NAME}
            WHERE (order_number, sku, vehicle_plate) = ANY(:keys)
        """)
        
        try:
            with self.engine.connect() as conn:
                # PostgreSQL array of tuples
                result = conn.execute(text(f"""
                    SELECT order_number, sku, vehicle_plate, is_primed 
                    FROM {self.TABLE_NAME}
                """)).fetchall()
                
                status_map = {}
                for row in result:
                    key = f"{row[0]}|{row[1]}|{row[2]}"
                    status_map[key] = row[3]
                
                return status_map
        except SQLAlchemyError as e:
            print(f"Error getting bulk status: {e}")
            return {}
    
    def get_all_primed(self, primed_only: bool = True) -> pd.DataFrame:
        """
        Get all records from tracking table.
        
        Args:
            primed_only: If True, only return primed records
            
        Returns:
            DataFrame with all tracking records
        """
        where_clause = "WHERE is_primed = TRUE" if primed_only else ""
        query = f"""
            SELECT * FROM {self.TABLE_NAME}
            {where_clause}
            ORDER BY primed_at DESC NULLS LAST
        """
        
        try:
            with self.engine.connect() as conn:
                return pd.read_sql(text(query), conn)
        except SQLAlchemyError as e:
            print(f"Error getting primed records: {e}")
            return pd.DataFrame()
    
    def get_stats(self) -> Dict:
        """
        Get summary statistics.
        
        Returns:
            Dict with total_tracked, total_primed, total_pending
        """
        query = text(f"""
            SELECT 
                COUNT(*) as total_tracked,
                COUNT(CASE WHEN is_primed = TRUE THEN 1 END) as total_primed,
                COUNT(CASE WHEN is_primed = FALSE THEN 1 END) as total_pending
            FROM {self.TABLE_NAME}
        """)
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(query).fetchone()
                return {
                    'total_tracked': result[0] or 0,
                    'total_primed': result[1] or 0,
                    'total_pending': result[2] or 0
                }
        except SQLAlchemyError:
            return {'total_tracked': 0, 'total_primed': 0, 'total_pending': 0}
