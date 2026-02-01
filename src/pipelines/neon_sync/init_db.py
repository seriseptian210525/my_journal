import sys
import os
from pathlib import Path

# Add project root to path
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
sys.path.append(str(project_root))

from src.pipelines.neon_sync.loader import NeonLoader

def init_db():
    print("🚀 Initializing Neon Database (Final Schema)...")
    
    try:
        loader = NeonLoader()
        
        # DROP Table to ensure fresh schema
        print("   ⚠️ Dropping existing table `unified_part_logs`...")
        loader.execute_query("DROP TABLE IF EXISTS unified_part_logs CASCADE;")
        
        # DDL: Create Table
        create_table_query = """
        CREATE TABLE IF NOT EXISTS unified_part_logs (
            id SERIAL PRIMARY KEY,
            source_system VARCHAR(50) NOT NULL, -- 'service_items' or 'part_usage'
            created_at TIMESTAMP WITH TIME ZONE,
            order_number VARCHAR(100),
            
            -- Core Identifiers
            vehicle_plate VARCHAR(50),
            sku VARCHAR(100),
            item_name VARCHAR(255),
            erp_product_id VARCHAR(100),
            
            -- Transaction Details
            item_type VARCHAR(50),
            service_type VARCHAR(50),
            service_location_name VARCHAR(100),
            completed_by VARCHAR(100), -- price_finalized_by_name
            customer_type VARCHAR(100),
            
            -- Metrics
            quantity NUMERIC(10, 2),
            unit_price NUMERIC(15, 2), -- Base Price
            final_price NUMERIC(15, 2),
            subtotal_price NUMERIC(15, 2), -- Total Price
            old_price NUMERIC(15, 2), -- Landed Price from Mappings
            
            -- Status & Context
            warranty_status VARCHAR(50),
            status VARCHAR(50),
            odometer INTEGER,
            bike_type VARCHAR(50),
            
            -- Calculated
            pergantian_ke INTEGER,
            
            -- System Metadata
            ingested_at TIMESTAMP DEFAULT NOW(),
            
            -- Unique Key for Deduplication (Composite)
            -- Note: 'pergantian_ke' is calculated, so it's part of the uniqueness of the event effectively
            -- But for raw data, source + order + sku + item name might be better?
            -- Actually, if we explode rows, we need a way to distinguish them.
            -- We might rely on ID or just loose constraints for now.
            -- Let's keep a flexible unique constraint if possible, or none if full refresh.
            -- Removing constraint for now to allow full refresh flexibility.
            CONSTRAINT unique_log_entry UNIQUE(source_system, order_number, sku, item_name, pergantian_ke)
        );
        """
        
        print("   Executing CREATE TABLE...")
        loader.execute_query(create_table_query)
        
        # DDL: Create Indexes
        print("   Creating Indexes...")
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_order_number ON unified_part_logs(order_number);",
            "CREATE INDEX IF NOT EXISTS idx_created_at ON unified_part_logs(created_at);",
            "CREATE INDEX IF NOT EXISTS idx_sku ON unified_part_logs(sku);",
            "CREATE INDEX IF NOT EXISTS idx_vehicle_plate ON unified_part_logs(vehicle_plate);"
        ]
        
        for idx in indexes:
            loader.execute_query(idx)
            
        print("✅ Database Table `unified_part_logs` is ready!")
        
    except Exception as e:
        print(f"❌ Failed to initialize database: {e}")
        raise e

if __name__ == "__main__":
    init_db()
