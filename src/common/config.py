import os
from pathlib import Path
from dotenv import load_dotenv
import datetime
from dataclasses import dataclass

# --- Snowflake Configuration ---
WORKER_ID = 1
DATACENTER_ID = 1
SNOWFLAKE_EPOCH = datetime.datetime(2024, 1, 1)

env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Fallback to env.yaml if .env doesn't have data (User uses env.yaml with .env syntax)
if not os.getenv("SHEET_ID_ASSET_LIST"):
    yaml_path = Path(__file__).resolve().parent.parent.parent / "env.yaml"
    if yaml_path.exists():
        load_dotenv(dotenv_path=yaml_path)

# --- Service Category Mapping ---
SERVICE_TYPE_MAPPING = {
    'Interval Service': 'Regular',
    'Interval Service, Driver Coming (Trouble)': 'Regular',
    'Interval Service, Mechanic Visit (CS)': 'Regular',
    'Interval Service, Campaign (Big Issue)': 'Regular',
    'Regular Service': 'Regular',
    'Dax In / Walk In (Service Reguler)': 'Regular',
    'Pause Unit': 'Urgent',
    'Driver Coming (Trouble)': 'Urgent',
    'Mechanic Visit (CS)': 'Storing',
    'Mechanic Visit (CS), Driver Coming (Trouble)': 'Storing',
    'ERA (Emergency Roadside Assistance) / Towing': 'Storing',
    'Repossesion': 'Repo Maintenance',
    'Reppo': 'Repo Maintenance',
    'Repo': 'Repo Maintenance',
    'repo maintenance': 'Repo Maintenance',
    'Walk In': 'Walk-In Maintenance',
    'Walk In/Offboarding': 'Walk-In Maintenance',
    'Broken Unit': 'Walk-In Maintenance',
    'Reduce NG': 'Walk-In Maintenance',
    'Campaign (Big Issue)': 'Storing',
    'Undangan DSS': 'Storing',
    'Unit Stock Grab': 'Walk-In Maintenance',
    'Reject QC': 'Urgent',
    'Official Partner Service': 'Official Partner Service',
    'Warranty Claim': 'Regular',
    'Swap In (Tukar Unit)': 'Urgent',
    'Driver Coming (Trouble), Mechanic Visit (CS)': 'Urgent',
    'Resign / Offboarding': 'Walk-In Maintenance'
}

# --- Columns to Combine for Parts ---
PARTS_COLUMNS_MAPPING = {
    'S1_FORM_SERVICE': [
        'Nama Part yang diganti', 'Part lain yang diganti (1)', 'Part lain yang diganti (2)', 
        'Part lain yang diganti (3)', 'Part lain yang diganti (4)', 'Part lain yang diganti (5)'
    ],
    'S2_SERVICE_GRAB': [
        'Consummable Part yang diganti', 'Sparepart lain yang diganti', '2. Part lain yang diganti',
        '3. Part lain yang diganti', '4. Part lain yang diganti', '5. Part lain yang diganti', 'Sparepart yang diganti'
    ],
    'S3_FORM_RESPONSES': [
        'Fast Moving Part (H5)', 'Medium Moving Part (H5)', 'Slow Moving Part (H5)',
        'Fast Moving Part (H3)', 'Medium Moving Part (H3)', 'Slow Moving Part (H3)',
        'Fast Moving Part (H1)', 'Medium Moving Part (H1)', 'Slow Moving Part (H1)'
    ],
    'S4_REQUEST_SPK': ['Nama Sparepart', 'Item Pengerjaan'],
    'S5_AFTER_REPAIR': [
        'Sparepart yang diganti - H3 ONLY', 'Sparepart yang diganti - H5 ONLY', 'Sparepart yang diganti - H1 ONLY'
    ],
    'S6_KEMBANGAN': ['SparePart Changes', 'SparePart Name'],
    'S7_DEPOK': [
        'Consumable Part yang Diganti H3', 'Consumable Part yang Diganti H5', 'Consumable Part yang Diganti ALL',
        'Part lain yang di ganti (1)', 'Part lain yang di ganti (2)', 'Part lain yang di ganti (3)',
        'Part lain yang di ganti (4)', 'Part lain yang di ganti (5)'
    ],
    'S8_BEKASI': ['Sparepart yang diganti - H3 ONLY', 'Sparepart yang diganti - H5 ONLY', 'ALL SPAREPART', 'BAHAN BAKU']
}

# --- Column Standardization Mapping ---
# Hanya memetakan kolom transaksi. Kolom Asset (VIN, Engine, dll) tidak dipetakan disini.
COLUMN_MAPPING = {
    'S1_FORM_SERVICE': {
        'Timestamp': 'created_at', 'Tanggal Service': 'completed_at', 'Lokasi Pool': 'service_location_name',
        'Nama Driver (1)': 'customer_name', 'Nama Driver': 'customer_name_backup',
        'ODO / KM': 'odometer', 
        'Plate Number (1)': 'vehicle_license_plate', 'Plate Number': 'vehicle_license_plate_backup',
        'Plat Nomor': 'vehicle_license_plate_backup_2', 'Mechanic Name': 'completed_by',
        'Mechanic Action Category': 'service_type', 'Keluhan Driver': 'customer_problems',
        'Tindakan Dari Mekanik': 'action_description', 'Total Biaya Perbaikan': 'total_price',
        'Driver Category': 'driver_category'
    },
    'S2_SERVICE_GRAB': {
        'Timestamp': 'created_at', 'Tanggal': 'completed_at', 'Nama Mekanik': 'completed_by',
        'Plat Nomor': 'vehicle_license_plate', 'ODO / Kilometer': 'odometer',
        'Status Unit': 'service_type', 'Kendala Unit': 'customer_problems',
        'Lokasi Service': 'service_location_name'
    },
    'S3_FORM_RESPONSES': {
        'Timestamp': 'created_at', 'Lokasi Pool': 'service_location_name', 'Nama Driver': 'customer_name',
        'Tanggal Service': 'completed_at', 'Plate Number': 'vehicle_license_plate',
        'ODO / KM': 'odometer', 'Mechanic Action Category': 'service_type', 'Mechanic Name': 'completed_by',
        'Keluhan Driver': 'customer_problems', 'Tindakan dari Mekanik': 'action_description',
        'Driver Category': 'driver_category'
    },
    'S4_REQUEST_SPK': {
        'Tanggal Laporan': 'created_at', 'Nama Driver': 'customer_name',
        'Plat Nomor': 'vehicle_license_plate', 'Odo / Kilometer': 'odometer', 'Kendala Unit': 'customer_problems',
        'Bengkel Tujuan': 'service_location_name', 'Tanggal Service di Bengkel': 'completed_at'
    },
    'S5_AFTER_REPAIR': {
        'Tanggal': 'created_at', 'Plat Kendaraan / Vin': 'vehicle_license_plate',
        'Nama Mekanik': 'completed_by'
    },
    'S6_KEMBANGAN': {
        'Timestamp': 'created_at', 'Checker / Repair': 'completed_by',
        'Plate Number': 'vehicle_license_plate', 'Date Bike Repair': 'completed_at',
        'Problem': 'customer_problems', 'Repair Action': 'action_description'
    },
    'S7_DEPOK': {
        'Nama Driver': 'customer_name', 'ODO / KM': 'odometer',
        'Plat Number': 'vehicle_license_plate', 'Date': 'created_at', 'Mechanic Name': 'completed_by',
        'Mechanic Action Category': 'service_type', 'Keluhan dari Driver': 'customer_problems',
        'Tindakan Perbaikan dari Mechanic': 'action_description',
        'Driver Category': 'driver_category'
    },
    'S8_BEKASI': {
        'Timestamp': 'created_at', 'Tanggal': 'completed_at',
        'Plat Kendaraan / VIN': 'vehicle_license_plate', 'Nama Mekani': 'completed_by',
        'Perbaikan & Rpc': 'customer_problems', 'Status Unit': 'service_type'
    }
}

# Load environment variables
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent.parent / ".env")
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Credentials
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# Auto-discovery fallback
if not SERVICE_ACCOUNT_FILE:
    print("DEBUG: GOOGLE_APPLICATION_CREDENTIALS not found in env. Searching credentials/ directory...")
    cred_dir = BASE_DIR / "credentials"
    if cred_dir.exists():
        json_files = list(cred_dir.glob("*.json"))
        if json_files:
            SERVICE_ACCOUNT_FILE = json_files[0]
            print(f"DEBUG: Found credential file: {SERVICE_ACCOUNT_FILE}")

if SERVICE_ACCOUNT_FILE and not os.path.isabs(SERVICE_ACCOUNT_FILE):
    SERVICE_ACCOUNT_FILE = BASE_DIR / SERVICE_ACCOUNT_FILE


# IDs
SHEET_ID_FORM_SERVICE = os.getenv("SHEET_ID_FORM_SERVICE")
WORKSHEET_FORM_SERVICE = os.getenv("WORKSHEET_FORM_SERVICE")
SHEET_ID_SERVICE_GRAB = os.getenv("SHEET_ID_SERVICE_GRAB")
WORKSHEET_SERVICE_GRAB = os.getenv("WORKSHEET_SERVICE_GRAB")
SHEET_ID_FORM_RESPONSES = os.getenv("SHEET_ID_FORM_RESPONSES")
WORKSHEET_FORM_RESPONSES = os.getenv("WORKSHEET_FORM_RESPONSES")
SHEET_ID_REQUEST_SPK = os.getenv("SHEET_ID_REQUEST_SPK")
WORKSHEET_REQUEST_SPK = os.getenv("WORKSHEET_REQUEST_SPK")
SHEET_ID_AFTER_REPAIR = os.getenv("SHEET_ID_AFTER_REPAIR")
WORKSHEET_AFTER_REPAIR = os.getenv("WORKSHEET_AFTER_REPAIR")
SHEET_ID_CABANG_KEMBANGAN = os.getenv("SHEET_ID_CABANG_KEMBANGAN")
WORKSHEET_CABANG_KEMBANGAN = os.getenv("WORKSHEET_CABANG_KEMBANGAN")
SHEET_ID_CABANG_DEPOK = os.getenv("SHEET_ID_CABANG_DEPOK")
WORKSHEET_CABANG_DEPOK = os.getenv("WORKSHEET_CABANG_DEPOK")
SHEET_ID_CABANG_BEKASI = os.getenv("SHEET_ID_CABANG_BEKASI")
WORKSHEET_CABANG_BEKASI = os.getenv("WORKSHEET_CABANG_BEKASI")
SHEET_ID_ASSET_LIST = os.getenv("SHEET_ID_ASSET_LIST")
WORKSHEET_ASSET = os.getenv("WORKSHEET_ASSET")
SHEET_ID_MEKANIK = os.getenv("SHEET_ID_MEKANIK")
WORKSHEET_MEKANIK = os.getenv("WORKSHEET_MEKANIK")
SHEET_ID_OUTPUT = os.getenv("SHEET_ID_OUTPUT")
WORKSHEET_OUTPUT = os.getenv("WORKSHEET_OUTPUT")
WORKSHEET_BAD_OUTPUT = os.getenv("WORKSHEET_BAD_OUTPUT")
SHEET_KAMUS_KELUHAN = os.getenv("SHEET_KAMUS_KELUHAN")
WORKSHEET_TOP_KELUHAN = os.getenv("WORKSHEET_TOP_KELUHAN")
WORKSHEET_TECH_LOG = "cleaning_tech_log" 
SAVE_LOCAL_CSV = os.getenv("SAVE_LOCAL_CSV", "true").lower() == "true"

# --- Driver Category Standardization Rules ---
DRIVER_CATEGORY_RULES = {
    r'(?i)b2c': 'B2C',
    r'(?i)grab': 'Grab',
    r'(?i)gojek': 'Gojek',
    r'(?i)dash': 'Dash',
    r'(?i)blitz': 'Blitz',
    r'(?i)shopee': 'Shopee',
    r'(?i)maxim': 'Maxim'
}

@dataclass
class PipelineConfig:
    """Configuration for Odometer Cleaning Pipeline"""
    
    # --- Cleaning Parameters ---
    ASSUMED_KM_PER_DAY: float = 150.0
    MAX_KM_PER_DAY: float = 600.0
    MIN_KM_PER_DAY: float = 10.0
    RANDOM_VARIANCE: float = 0.2
    FUZZY_THRESHOLD: int = 85

    # Asset List Columns
    COL_ASSET_VIN: str = "VIN"
    COL_ASSET_DELIVERY: str = "Delivery - Outbone"
    COL_ASSET_MODEL: str = "Model"
    COL_ASSET_PLATE: str = "Plat Nomor"
    
    # Internal column names
    COL_ODO_CLEAN: str = "odometer_clean"
    COL_DELIVERY_DATE: str = "delivery_date_internal"
    
    # Column names - Service Items
    COL_ELSA_ORDER_ID: str = "order_id"
    COL_ITEMS_ORDER_ID: str = "order_id"
    COL_ITEMS_ODO: str = "odometer"
    
    # Column names - Mapping/Enrichment
    COL_PART_NAME: str = "part_name"
    COL_MAP_PRICE: str = "price"
    COL_MAP_SKU: str = "sku"
    COL_TARGET_PRICE: str = "enriched_price"
    COL_TARGET_SKU: str = "enriched_sku"
