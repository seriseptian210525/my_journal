
import pandas as pd
import sys
import os
import warnings
from src.common.data_loader import DataLoader
from src.pipelines.work_orders.transformers import ServiceDataPipeline, ServiceDataEnricher
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
    SAVE_LOCAL_CSV
)
from src.pipelines.work_orders.odometer_processor import OdometerProcessor
from src.pipelines.work_orders.complaint_cleaner import ComplaintCleaner

def run_work_order_pipeline():
    print("🚀 Starting Work Order Pipeline (Modular)...")
    
    # Suppress warnings
    warnings.filterwarnings('ignore')
    pd.options.mode.chained_assignment = None

    # 1. Initialize Loader
    loader = DataLoader()
    
    # 2. Load Reference Data
    print("\n📥 Loading Reference Data...")
    asset_df = loader.load_gspread_data(SHEET_ID_ASSET_LIST, WORKSHEET_ASSET)
    mekanik_df = loader.load_gspread_data(SHEET_ID_MEKANIK, WORKSHEET_MEKANIK)
    
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
    
    # S4 (With Filter)
    def s4_filter(df):
        if 'Status' in df.columns and 'Bengkel Tujuan' in df.columns:
            return df[
                df['Status'].astype(str).str.contains('Completed', case=False, na=False) &
                df['Bengkel Tujuan'].notna()
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
        .standardize_location_names()
        .generate_snowflake_ids()
        .randomize_working_hours()
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
    
    # 7. Export Preparation
    print("\nPreparing Export Dataframes...")
    
    tech_columns = [
        'delivery_date_internal', 'odometer_raw', 'odometer_stage1', 
        'delta_days', 'delta_odo', 'km_per_day', 'is_anomaly_rule', 
        'needs_impute', 'odometer_clean', 
        'customer_problems_details', 'customer_problems_clean'
    ]
    
    business_df = final_df.drop(columns=[c for c in tech_columns if c in final_df.columns], errors='ignore').copy()
    
    key_cols = ['order_id', 'created_at', 'vechicle_vin', 'vehicle_license_plate']
    tech_cols_to_use = [c for c in tech_columns if c in final_df.columns]
    tech_df = final_df[key_cols + tech_cols_to_use].copy()
    
    if 'customer_problems_details' in tech_df.columns:
        tech_df['customer_problems_details'] = tech_df['customer_problems_details'].astype(str)

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
    
    if SHEET_ID_OUTPUT and WORKSHEET_OUTPUT:
        loader.upload_to_sheet(business_df, SHEET_ID_OUTPUT, WORKSHEET_OUTPUT)
    else:
        print("⚠️ Skipping Final Data Upload: Missing SHEET_ID_OUTPUT or WORKSHEET_OUTPUT.")

    if SHEET_ID_OUTPUT and WORKSHEET_TECH_LOG:
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
