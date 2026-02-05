
import pandas as pd
import sys
import os
import warnings
from datetime import datetime, timedelta
from src.common.data_loader import DataLoader
from src.pipelines.work_orders.transformers import ServiceDataPipeline, ServiceDataEnricher, MetadataEnricher
from src.common.config import (
    SHEET_ID_OUTPUT, WORKSHEET_OUTPUT, WORKSHEET_BAD_OUTPUT,
    SHEET_ID_FORM_SERVICE, WORKSHEET_FORM_SERVICE,
    SHEET_ID_SERVICE_GRAB, WORKSHEET_SERVICE_GRAB,
    SHEET_ID_FORM_RESPONSES, WORKSHEET_FORM_RESPONSES,
    SHEET_ID_REQUEST_SPK, WORKSHEET_REQUEST_SPK,
    SHEET_ID_AFTER_REPAIR, WORKSHEET_AFTER_REPAIR,
    SHEET_ID_CABANG_KEMBANGAN, WORKSHEET_CABANG_KEMBANGAN,
    SHEET_ID_CABANG_DEPOK, WORKSHEET_CABANG_DEPOK,
    SHEET_ID_CABANG_BEKASI, WORKSHEET_CABANG_BEKASI,
    SHEET_ID_ASSET_LIST, WORKSHEET_ASSET,
    SHEET_ID_MEKANIK, WORKSHEET_MEKANIK,
    PipelineConfig,
    WORKSHEET_TECH_LOG,
    SAVE_LOCAL_CSV,
    SHEET_ID_LOCATIONS, WORKSHEET_LOCATIONS,
    WORKSHEET_OUTPUT_REVIEW
)
from src.common.utils import ServiceUtils
from src.pipelines.work_orders.odometer_processor import OdometerProcessor
from src.pipelines.work_orders.complaint_cleaner import ComplaintCleaner

# Pipeline Mode Configuration
PIPELINE_MODE = os.getenv('PIPELINE_MODE', 'full')  # 'full' or 'incremental'
LOOKBACK_DAYS = int(os.getenv('LOOKBACK_DAYS', '2'))  # Days to look back for incremental mode

def run_work_order_pipeline():
    print("🚀 Starting Work Order Pipeline (Modular)...")
    print(f"   Mode: {PIPELINE_MODE.upper()}, Lookback: {LOOKBACK_DAYS} days")
    
    # Suppress warnings
    warnings.filterwarnings('ignore')
    pd.options.mode.chained_assignment = None

    # 1. Initialize Loader
    loader = DataLoader()
    
    # 2. Load Reference Data
    print("\n📥 Loading Reference Data...")
    asset_df = loader.load_gspread_data(SHEET_ID_ASSET_LIST, WORKSHEET_ASSET)
    mekanik_df = loader.load_gspread_data(SHEET_ID_MEKANIK, WORKSHEET_MEKANIK)
    
    # Load master location data
    location_df = None
    if SHEET_ID_LOCATIONS and SHEET_ID_LOCATIONS != '<PLACEHOLDER_SHEET_ID>':
        location_df = loader.load_gspread_data(SHEET_ID_LOCATIONS, WORKSHEET_LOCATIONS)
        if not location_df.empty:
            print(f"   ✅ Loaded {len(location_df)} locations from master data.")
        else:
            print("   ⚠️ Location master data empty. Will use fallback.")
    else:
        print("   ⚠️ Location master not configured. Will use fallback.")
    
    if asset_df.empty:
        print("❌ CRITICAL: Asset List empty. Aborting.")
        return

    # 3. Initialize Pipeline (Ingestion)
    pipeline = ServiceDataPipeline()
    
    # Ingest Sources
    print("\n📥 Ingesting Data Sources...")
    
    # S1
    s1 = loader.load_gspread_data(SHEET_ID_FORM_SERVICE, WORKSHEET_FORM_SERVICE)
    pipeline.ingest_generic(s1, 'S1_FORM_SERVICE')
    
    # S2
    s2 = loader.load_gspread_data(SHEET_ID_SERVICE_GRAB, WORKSHEET_SERVICE_GRAB)
    pipeline.ingest_generic(s2, 'S2_SERVICE_GRAB')
    
    # S3
    s3 = loader.load_gspread_data(SHEET_ID_FORM_RESPONSES, WORKSHEET_FORM_RESPONSES)
    pipeline.ingest_generic(s3, 'S3_FORM_RESPONSES')
    
    # S4 (With Filter - only Completed status with valid Bengkel Tujuan)
    def s4_filter(df):
        if 'Status' in df.columns and 'Bengkel Tujuan' in df.columns:
            # Filter: Status = Completed AND Bengkel Tujuan not null/empty
            return df[
                df['Status'].astype(str).str.contains('Completed', case=False, na=False) &
                df['Bengkel Tujuan'].notna() &
                (df['Bengkel Tujuan'].astype(str).str.strip() != '') &
                (df['Bengkel Tujuan'].astype(str).str.lower() != 'nan')
            ]
        return df

    s4 = loader.load_gspread_data(SHEET_ID_REQUEST_SPK, WORKSHEET_REQUEST_SPK)
    pipeline.ingest_generic(s4, 'S4_REQUEST_SPK', filter_func=s4_filter)
    
    # S5
    s5 = loader.load_gspread_data(SHEET_ID_AFTER_REPAIR, WORKSHEET_AFTER_REPAIR)
    pipeline.ingest_generic(s5, 'S5_AFTER_REPAIR')
    
    # Cabang
    s6 = loader.load_gspread_data(SHEET_ID_CABANG_KEMBANGAN, WORKSHEET_CABANG_KEMBANGAN)
    pipeline.ingest_cabang(s6, 'S6_KEMBANGAN', "Kembangan")
    
    s7 = loader.load_gspread_data(SHEET_ID_CABANG_DEPOK, WORKSHEET_CABANG_DEPOK)
    pipeline.ingest_cabang(s7, 'S7_DEPOK', "Depok")
    
    s8 = loader.load_gspread_data(SHEET_ID_CABANG_BEKASI, WORKSHEET_CABANG_BEKASI)
    pipeline.ingest_cabang(s8, 'S8_BEKASI', "Bekasi")
    
    # Merge
    merged_df = pipeline.merge_and_finalize()
    print(f"   Total rows merged: {len(merged_df)}")
    
    # [INCREMENTAL MODE] Filter by date if incremental
    if PIPELINE_MODE == 'incremental' and 'created_at' in merged_df.columns:
        cutoff_date = datetime.now() - timedelta(days=LOOKBACK_DAYS)
        merged_df['created_at'] = pd.to_datetime(merged_df['created_at'], errors='coerce')
        
        before_filter = len(merged_df)
        merged_df = merged_df[merged_df['created_at'] >= cutoff_date]
        print(f"   📅 Incremental filter: {before_filter} → {len(merged_df)} rows (last {LOOKBACK_DAYS} days)")
        
        if merged_df.empty:
            print("   ℹ️ No new data to process. Exiting.")
            return
    
    # [INCREMENTAL MODE] Fetch existing order_ids to avoid duplicates
    existing_order_ids = set()
    if PIPELINE_MODE == 'incremental' and SHEET_ID_OUTPUT and WORKSHEET_OUTPUT:
        print("   📋 Fetching existing order_ids from sheet...")
        try:
            existing_df = loader.load_gspread_data(SHEET_ID_OUTPUT, WORKSHEET_OUTPUT)
            if existing_df is not None and 'order_id' in existing_df.columns:
                existing_order_ids = set(existing_df['order_id'].dropna().astype(str).unique())
                print(f"   ✅ Found {len(existing_order_ids)} existing order_ids")
        except Exception as e:
            print(f"   ⚠️ Could not fetch existing IDs: {e}")
    
    # 4. Enrichment & Business Logic
    print("\n🔗 Enriching & Cleaning...")
    enricher = ServiceDataEnricher(merged_df, asset_df)
    
    enriched_df, bad_data_df = (
        enricher
        .clean_critical_data()
        .normalize_total_price()
        .backfill_driver_category()
        .standardize_driver_category()
        .repair_identities_and_clean()
        .enrich_asset_details()
        .backfill_driver_category()
        .standardize_driver_category()
        .fill_customer_names()
        .process_odometer()
        .standardize_mechanics(mekanik_df)
        .standardize_location_names(location_df)
        .generate_snowflake_ids(existing_order_ids)
        .randomize_working_hours()
        .normalize_service_type()
        .add_convert_customer_type_flag()
        .add_partner_name_flag()
        .get_results()
    )
    
    # 5. Apply Complaint Cleaner
    print("\n🧹 Applying Complaint Cleaner...")
    complaint_cleaner = ComplaintCleaner(PipelineConfig(), loader)
    enriched_df = complaint_cleaner.process_dataframe(enriched_df, col_name='customer_problems')
    
    if 'customer_problems_clean' in enriched_df.columns:
        enriched_df['customer_problems'] = enriched_df['customer_problems_clean']
    
    # 6. Apply OdometerProcessor
    print("\n🔧 Applying OdometerProcessor...")
    odo_config = PipelineConfig()
    odo_processor = OdometerProcessor(odo_config)
    
    final_df = odo_processor.process_pipeline(enriched_df, asset_df)
    
    if 'odometer_clean' in final_df.columns:
        final_df['odometer'] = final_df['odometer_clean'].fillna(final_df['odometer']).astype('int64')
        print(f"   ✅ Replaced odometer with odometer_clean values")

    # [NEW] Generate JSON Metadata Columns (After Odometer is Finalized)
    print("\n📦 Generating Final Metadata...")
    meta_enricher = MetadataEnricher(final_df)
    final_df = meta_enricher.process()
    
    # 7. Export Preparation
    print("\nPreparing Export Dataframes...")
    
    tech_columns = [
        'delivery_date_internal', 'odometer_raw', 'odometer_stage1', 
        'delta_days', 'delta_odo', 'km_per_day', 'is_anomaly_rule', 
        'needs_impute', 'odometer_clean', 
        'customer_problems_details', 'customer_problems_clean',
        'location_is_null', 'location_resolve_status'  # Debug columns - exclude from main output
    ]
    
    business_df = final_df.drop(columns=[c for c in tech_columns if c in final_df.columns], errors='ignore').copy()
    
    # [UPDATED] Sort by created_at globally before export
    if 'created_at' in business_df.columns:
        business_df.sort_values(by='created_at', ascending=True, inplace=True)
    
    key_cols = ['order_id', 'created_at', 'vehicle_vin', 'vehicle_license_plate']
    # Filter to only include columns that exist
    key_cols = [c for c in key_cols if c in final_df.columns]
    tech_cols_to_use = [c for c in tech_columns if c in final_df.columns]
    tech_df = final_df[key_cols + tech_cols_to_use].copy()

    # [UPDATED] Sort tech log too
    if 'created_at' in tech_df.columns:
        tech_df.sort_values(by='created_at', ascending=True, inplace=True)
    
    if 'customer_problems_details' in tech_df.columns:
        tech_df['customer_problems_details'] = tech_df['customer_problems_details'].astype(str)

    # [UPDATED] Format Dates for Output (ISO 8601 with Timezone)
    date_cols_to_format = ['created_at', 'updated_at', 'completed_at', 'prize_finalized_at']
    
    print("   Note: Formatting date columns to ISO 8601...")
    for col in date_cols_to_format:
        if col in business_df.columns:
            business_df[col] = ServiceUtils.format_for_output(business_df[col])
        if col in tech_df.columns:
            tech_df[col] = ServiceUtils.format_for_output(tech_df[col])

    print("\n💾 Exporting Results...")
    
    if SAVE_LOCAL_CSV:
        # Define output directory
        output_dir = os.path.join(os.getcwd(), 'output')
        os.makedirs(output_dir, exist_ok=True)
        
        business_df.to_csv(os.path.join(output_dir, 'final_historical_data.csv'), index=False)
        tech_df.to_csv(os.path.join(output_dir, 'cleaning_tech_log.csv'), index=False)
        print(f"✅ Main Data saved to output/final_historical_data.csv ({len(business_df)} rows)")
        print(f"✅ Tech Log saved to output/cleaning_tech_log.csv ({len(tech_df)} rows)")

        if not bad_data_df.empty:
            bad_data_df.to_csv(os.path.join(output_dir, 'bad_data.csv'), index=False)
            print(f"⚠️ Bad Data saved to output/bad_data.csv ({len(bad_data_df)} rows)")
    else:
        print("ℹ️ Local CSV export SKIPPED (SAVE_LOCAL_CSV=False)")
    
    # 8. Upload to Google Sheets
    print("\n☁️ Uploading to Google Sheets...")
    
    # Define deduplication keys - order_id should be unique
    dedup_keys = ['order_id']
    
    if SHEET_ID_OUTPUT and WORKSHEET_OUTPUT:
        if PIPELINE_MODE == 'incremental':
            loader.append_to_sheet(business_df, SHEET_ID_OUTPUT, WORKSHEET_OUTPUT, key_columns=dedup_keys)
        else:
            loader.upload_to_sheet(business_df, SHEET_ID_OUTPUT, WORKSHEET_OUTPUT)
    else:
        print("⚠️ Skipping Final Data Upload: Missing SHEET_ID_OUTPUT or WORKSHEET_OUTPUT.")

    if SHEET_ID_OUTPUT and WORKSHEET_TECH_LOG:
        # Safeguard: Clean float columns to avoid dtype errors
        import numpy as np
        for col in tech_df.columns:
            if tech_df[col].dtype in ['float64', 'float32', 'int64', 'int32']:
                tech_df[col] = tech_df[col].replace([np.inf, -np.inf], np.nan)
                tech_df[col] = tech_df[col].where(pd.notna(tech_df[col]), None)
        
        if PIPELINE_MODE == 'incremental':
            loader.append_to_sheet(tech_df, SHEET_ID_OUTPUT, WORKSHEET_TECH_LOG, key_columns=dedup_keys)
        else:
            loader.upload_to_sheet(tech_df, SHEET_ID_OUTPUT, WORKSHEET_TECH_LOG)
    else:
        print("ℹ️ Skipping Tech Log Upload: WORKSHEET_TECH_LOG not configured.")

    if not bad_data_df.empty and SHEET_ID_OUTPUT and WORKSHEET_BAD_OUTPUT:
        loader.upload_to_sheet(bad_data_df, SHEET_ID_OUTPUT, WORKSHEET_BAD_OUTPUT)
    elif bad_data_df.empty:
        print("ℹ️ Skipping Bad Data Upload: No bad data found.")
    else:
        print("⚠️ Skipping Bad Data Upload: Missing WORKSHEET_BAD_OUTPUT configuration.")

if __name__ == "__main__":
    run_work_order_pipeline()
