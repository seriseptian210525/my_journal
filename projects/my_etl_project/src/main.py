
import sys
import os

# Ensure project root is in python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipelines.work_orders.run import run_work_order_pipeline

def main():
    """
    Entry point for the ETL pipeline.
    Redirects to the modular pipeline implementation which handles:
    - Deterministic Snowflake ID generation (via sorted cumcount)
    - Data cleaning and enrichment
    - Odometer processing
    """
    run_work_order_pipeline()

if __name__ == "__main__":
    main()
