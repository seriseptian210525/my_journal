import os
from pathlib import Path
from dotenv import load_dotenv
import datetime
from dataclasses import dataclass

# --- Snowflake Configuration ---
WORKER_ID = 1
DATACENTER_ID = 1
SNOWFLAKE_EPOCH = datetime.datetime(2024, 1, 1)

import os
import yaml
from pathlib import Path
from dotenv import load_dotenv
import datetime
from dataclasses import dataclass

# --- Snowflake Configuration ---
WORKER_ID = 1
DATACENTER_ID = 1
SNOWFLAKE_EPOCH = datetime.datetime(2024, 1, 1)

# Base Directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# --- Config Loading Logic ---
CONFIG_DIR = BASE_DIR / "config"
WORK_ORDERS_CONFIG_PATH = CONFIG_DIR / "work_orders.yaml"

def load_yaml_config(path: Path):
    if not path.exists():
        print(f"⚠️ Warning: Config file not found at {path}. Using empty defaults.")
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        try:
            return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            print(f"❌ Error parsing YAML config {path}: {e}")
            return {}

# Load work_orders.yaml
_wo_config = load_yaml_config(WORK_ORDERS_CONFIG_PATH)

# --- Service Category Mapping ---
SERVICE_TYPE_MAPPING = _wo_config.get('service_type_mapping', {})

# --- Columns to Combine for Parts ---
PARTS_COLUMNS_MAPPING = _wo_config.get('parts_columns_mapping', {})

# --- Column Standardization Mapping ---
COLUMN_MAPPING = _wo_config.get('column_mapping', {})

# --- Driver Category Standardization Rules ---
DRIVER_CATEGORY_RULES = _wo_config.get('driver_category_rules', {})

# --- Environment Loading ---
# Load .env (Standard)
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)

# Credentials
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# Auto-discovery fallback for Credentials
if not SERVICE_ACCOUNT_FILE:
    # silent debug or minimal log
    cred_dir = BASE_DIR / "credentials"
    if cred_dir.exists():
        json_files = list(cred_dir.glob("*.json"))
        if json_files:
            SERVICE_ACCOUNT_FILE = json_files[0]
            # print(f"DEBUG: Found credential file: {SERVICE_ACCOUNT_FILE}")

if SERVICE_ACCOUNT_FILE and not os.path.isabs(SERVICE_ACCOUNT_FILE):
    SERVICE_ACCOUNT_FILE = BASE_DIR / SERVICE_ACCOUNT_FILE

# IDs (Loaded from .env)
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

@dataclass
class PipelineConfig:
    """Configuration for Odometer Cleaning Pipeline"""
    def __init__(self):
        # Load defaults from YAML if available
        defaults = _wo_config.get('pipeline_config', {})
        
        self.ASSUMED_KM_PER_DAY = float(defaults.get('assumed_km_per_day', 150.0))
        self.MAX_KM_PER_DAY = float(defaults.get('max_km_per_day', 600.0))
        self.MIN_KM_PER_DAY = float(defaults.get('min_km_per_day', 10.0))
        self.RANDOM_VARIANCE = float(defaults.get('random_variance', 0.2))
        self.FUZZY_THRESHOLD = int(defaults.get('fuzzy_threshold', 85))
        
        self.COL_ASSET_VIN = defaults.get('col_asset_vin', "VIN")
        self.COL_ASSET_DELIVERY = defaults.get('col_asset_delivery', "Delivery - Outbone")
        self.COL_ASSET_MODEL = defaults.get('col_asset_model', "Model")
        self.COL_ASSET_PLATE = defaults.get('col_asset_plate', "Plat Nomor")
        
        self.COL_ODO_CLEAN = defaults.get('col_odo_clean', "odometer_clean")
        self.COL_DELIVERY_DATE = defaults.get('col_delivery_date', "delivery_date_internal")
        
        self.COL_ELSA_ORDER_ID = defaults.get('col_elsa_order_id', "order_id")
        self.COL_ITEMS_ORDER_ID = defaults.get('col_items_order_id', "order_id")
        self.COL_ITEMS_ODO = defaults.get('col_items_odo', "odometer")
        
        self.COL_PART_NAME = defaults.get('col_part_name', "part_name")
        self.COL_MAP_PRICE = defaults.get('col_map_price', "price")
        self.COL_MAP_SKU = defaults.get('col_map_sku', "sku")
        self.COL_TARGET_PRICE = defaults.get('col_target_price', "enriched_price")
        self.COL_TARGET_SKU = defaults.get('col_target_sku', "enriched_sku")
