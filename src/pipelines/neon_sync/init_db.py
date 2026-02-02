import sys
import os
from pathlib import Path

# Add project root to path
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent.parent
sys.path.append(str(project_root))

from src.pipelines.neon_sync.loader import NeonLoader

def init_db():
    print("🚀 Initializing Neon Database (Enhanced Schema with Warranty)...")
    
    try:
        loader = NeonLoader()
        
        # DROP Table to ensure fresh schema
        print("   ⚠️ Dropping existing table `unified_part_logs`...")
        loader.execute_query("DROP TABLE IF EXISTS unified_part_logs CASCADE;")
        
        # DDL: Create Table with Enhanced Schema
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
            completed_by VARCHAR(100),
            customer_type VARCHAR(100),
            
            -- Metrics
            quantity NUMERIC(10, 2),
            unit_price NUMERIC(15, 2),
            final_price NUMERIC(15, 2),
            subtotal_price NUMERIC(15, 2),
            old_price NUMERIC(15, 2),
            
            -- Status & Context
            warranty_status VARCHAR(50),
            status VARCHAR(50),
            odometer INTEGER,
            bike_type VARCHAR(50),
            
            -- NEW: Warranty Calculation Fields
            delivery_date DATE,                    -- From Asset List
            bulan_ke INTEGER DEFAULT 0,            -- Months since delivery
            year_cycle INTEGER DEFAULT 0,          -- bulan_ke // 12
            customer_category VARCHAR(50),         -- PARTNER_USER / ELECTRUM_USER
            warranty_type VARCHAR(50),             -- From Mappings
            covered_for VARCHAR(255),              -- From Mappings
            limit_per_year INTEGER DEFAULT 0,      -- From Mappings
            pergantian_ke_total INTEGER DEFAULT 1, -- Cumulative per vehicle+sku (never resets)
            pergantian_ke_yearly INTEGER DEFAULT 1,-- Cumulative per vehicle+sku+year_cycle (resets yearly)
            warranty_coverage VARCHAR(50),         -- Final calculated warranty status
            
            -- System Metadata
            ingested_at TIMESTAMP DEFAULT NOW()
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
            "CREATE INDEX IF NOT EXISTS idx_vehicle_plate ON unified_part_logs(vehicle_plate);",
            "CREATE INDEX IF NOT EXISTS idx_year_cycle ON unified_part_logs(year_cycle);",
            "CREATE INDEX IF NOT EXISTS idx_customer_category ON unified_part_logs(customer_category);",
            "CREATE INDEX IF NOT EXISTS idx_warranty_coverage ON unified_part_logs(warranty_coverage);"
        ]
        
        for idx in indexes:
            loader.execute_query(idx)
            
        print("✅ Database Table `unified_part_logs` is ready with enhanced schema!")
        
    except Exception as e:
        print(f"❌ Failed to initialize database: {e}")
        raise e


def alter_existing_table():
    """
    Alternative: Add new columns to existing table without dropping.
    Use this if you want to preserve existing data.
    """
    print("🔧 Altering existing table (adding new columns)...")
    
    try:
        loader = NeonLoader()
        
        alter_queries = [
            "ALTER TABLE unified_part_logs ADD COLUMN IF NOT EXISTS delivery_date DATE;",
            "ALTER TABLE unified_part_logs ADD COLUMN IF NOT EXISTS bulan_ke INTEGER DEFAULT 0;",
            "ALTER TABLE unified_part_logs ADD COLUMN IF NOT EXISTS year_cycle INTEGER DEFAULT 0;",
            "ALTER TABLE unified_part_logs ADD COLUMN IF NOT EXISTS customer_category VARCHAR(50);",
            "ALTER TABLE unified_part_logs ADD COLUMN IF NOT EXISTS warranty_type VARCHAR(50);",
            "ALTER TABLE unified_part_logs ADD COLUMN IF NOT EXISTS covered_for VARCHAR(255);",
            "ALTER TABLE unified_part_logs ADD COLUMN IF NOT EXISTS limit_per_year INTEGER DEFAULT 0;",
            "ALTER TABLE unified_part_logs ADD COLUMN IF NOT EXISTS warranty_coverage VARCHAR(50);",
        ]
        
        for query in alter_queries:
            print(f"   Executing: {query[:50]}...")
            loader.execute_query(query)
        
        # Drop old constraint and add new one
        print("   Updating unique constraint...")
        loader.execute_query("ALTER TABLE unified_part_logs DROP CONSTRAINT IF EXISTS unique_log_entry;")
        loader.execute_query("""
            ALTER TABLE unified_part_logs 
            ADD CONSTRAINT unique_log_entry 
            UNIQUE(source_system, order_number, sku, item_name, year_cycle, pergantian_ke);
        """)
        
        # Add new indexes
        print("   Adding new indexes...")
        loader.execute_query("CREATE INDEX IF NOT EXISTS idx_year_cycle ON unified_part_logs(year_cycle);")
        loader.execute_query("CREATE INDEX IF NOT EXISTS idx_customer_category ON unified_part_logs(customer_category);")
        loader.execute_query("CREATE INDEX IF NOT EXISTS idx_warranty_coverage ON unified_part_logs(warranty_coverage);")
        
        print("✅ Table altered successfully!")
        
    except Exception as e:
        print(f"❌ Failed to alter table: {e}")
        raise e


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--alter', action='store_true', help='Alter existing table instead of recreating')
    args = parser.parse_args()
    
    if args.alter:
        alter_existing_table()
    else:
        init_db()
