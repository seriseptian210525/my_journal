import pandas as pd
import sys
import os
import io
import contextlib
from unittest.mock import patch

# --- Setup Path ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)
sys.path.append(os.path.join(project_root, 'src'))

# Import fungsi yang dibutuhkan
from src.main import main
from src.config import SHEET_ID_OUTPUT # Pastikan ini ada di .env Anda
from src.data_loader import write_to_google_sheet

# Nama worksheet tujuan untuk testing
TEST_WORKSHEET_NAME = "test_output"

def run_integration_test():
    print(f"🚀 Starting LIVE Integration Test (Target: Sheet '{TEST_WORKSHEET_NAME}')")
    
    # 1. Jalankan ETL Main Process
    # Kita tidak me-mock write_to_google_sheet karena kita ingin benar-benar menulis nanti.
    # Namun, kita capture stdout agar log tetap bersih atau bisa dianalisis.
    captured_output = io.StringIO()
    
    df_result = None
    
    try:
        with contextlib.redirect_stdout(captured_output):
            # Main sekarang mengembalikan DataFrame
            df_result = main()
            
    except Exception as e:
        print(f"\n❌ ETL CRASHED: {e}")
        import traceback
        traceback.print_exc()
        # Print logs sampai crash
        print("\n--- CRASH LOGS ---")
        print(captured_output.getvalue())
        return

    # Print logs execution (opsional, jika ingin melihat prosesnya)
    print("\n--- ETL EXECUTION LOGS ---")
    print(captured_output.getvalue())

    if df_result is None or df_result.empty:
        print("❌ ETL finished but returned empty DataFrame.")
        return

    print(f"\n📊 DATA READY FOR UPLOAD:")
    print(f"   Rows: {len(df_result)}")
    print(f"   Columns: {len(df_result.columns)}")

    # 2. VALIDASI SEDERHANA SEBELUM UPLOAD
    # Pastikan ID terbentuk
    if 'order_number' in df_result.columns:
        print("   ✅ Order ID column exists.")
    else:
        print("   ⚠️ WARNING: Order ID column missing!")

    # 3. UPLOAD KE GOOGLE SHEET (REAL)
    print(f"\n📤 Uploading to Google Sheet...")
    print(f"   Spreadsheet ID: {SHEET_ID_OUTPUT}")
    print(f"   Worksheet: {TEST_WORKSHEET_NAME}")
    
    if not SHEET_ID_OUTPUT:
        print("❌ ERROR: SHEET_ID_OUTPUT is not set in .env or config.py")
        return

    try:
        success = write_to_google_sheet(
            df=df_result, 
            sheet_id=SHEET_ID_OUTPUT, 
            worksheet_name=TEST_WORKSHEET_NAME
        )
        
        if success:
            print(f"\n✅ SUCCESS! Data has been updated in '{TEST_WORKSHEET_NAME}'.")
        else:
            print("\n❌ FAILED to write to Google Sheet. Check console logs above.")
            
    except Exception as e:
        print(f"\n❌ Upload Error: {e}")

if __name__ == "__main__":
    run_integration_test()