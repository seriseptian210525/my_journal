
import sys
import os

# Add project root to python path to ensure imports work
# Current file is in entrypoint/, we need to go up one level to reach src/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run specific ETL pipelines.")
    parser.add_argument(
        "--pipeline", 
        type=str, 
        default="work_orders", 
        choices=["work_orders", "service_items", "wo_activity", "neon_sync"],
        help="Name of the pipeline to run"
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="full",
        choices=["full", "incremental", "recalculate"],
        help="Pipeline mode (for neon_sync): full=truncate+refresh, incremental=append new, recalculate=upsert"
    )
    args = parser.parse_args()

    if args.pipeline == "work_orders":
        from src.pipelines.work_orders.run import run_work_order_pipeline
        run_work_order_pipeline()
    
    elif args.pipeline == "service_items":
        print("🚧 Pipeline 'service_items' is under construction.")
        # from src.pipelines.service_items.run import run_service_items_pipeline
        # run_service_items_pipeline()
        
    elif args.pipeline == "wo_activity":
        print("🚧 Pipeline 'wo_activity' is under construction.")
    
    elif args.pipeline == "neon_sync":
        os.environ['PIPELINE_MODE'] = args.mode
        print(f"🚀 Running Neon Sync Pipeline (Mode: {args.mode.upper()})...")
        from src.pipelines.neon_sync.run import run_pipeline
        run_pipeline()
