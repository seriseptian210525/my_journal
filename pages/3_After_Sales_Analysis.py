import streamlit as st
import pandas as pd
import os
import sys

# --- Path Integration for Shared Modules ---
# Add ETL project root to path so we can import src.common
etl_project_path = os.path.join(os.getcwd(), "projects", "my_etl_project")
if etl_project_path not in sys.path:
    sys.path.append(etl_project_path)

try:
    from src.common.data_loader import DataLoader
    from src.common.config import SHEET_ID_OUTPUT, WORKSHEET_OUTPUT
except ImportError as e:
    st.error(f"Failed to import ETL modules. Make sure 'projects/my_etl_project' exists. Error: {e}")
    st.stop()

st.set_page_config(page_title="After Sales Analysis", layout="wide")
st.title("📋 Work Orders Data")

# --- Datasource Selection ---
st.sidebar.header("Configuration")
data_source = st.sidebar.radio("Data Source:", ["Local CSV", "Google Sheets (Live)"])

@st.cache_data(ttl=300) # Cache for 5 minutes
def load_data_from_gsheets():
    """Load data directly from Google Sheets using ETL Loader."""
    loader = DataLoader()
    if not SHEET_ID_OUTPUT or not WORKSHEET_OUTPUT:
        st.error("Sheet Configuration missing in .env")
        return pd.DataFrame()
    
    try:
        df = loader.load_gspread_data(SHEET_ID_OUTPUT, WORKSHEET_OUTPUT)
        return df
    except Exception as e:
        st.error(f"GSheets Error: {e}")
        return pd.DataFrame()

# --- Main Logic ---
df = pd.DataFrame()

if data_source == "Google Sheets (Live)":
    with st.spinner("Fetching data from Google Sheets..."):
        df = load_data_from_gsheets()
        st.success(f"Loaded {len(df)} rows from Cloud.")

else: # Local CSV
    DATA_PATH = os.path.join("projects", "my_etl_project", "output", "final_historical_data.csv")
    if os.path.exists(DATA_PATH):
        df = pd.read_csv(DATA_PATH)
    else:
        st.warning(f"⚠️ Local file not found: `{DATA_PATH}`")
        st.info("Try switching to 'Google Sheets' or run the ETL pipeline.")

if not df.empty:
    st.markdown("""
    ### Dataset Overview
    Data berikut adalah **Work Orders** yang telah diproses.
    """)

    # Preprocessing for View
    if 'created_at' in df.columns:
        df['created_at'] = pd.to_datetime(df['created_at'], errors='coerce')
        df = df.sort_values(by='created_at', ascending=True)

    # Display
    st.dataframe(
        df, 
        use_container_width=True,
        column_config={
            "created_at": st.column_config.DatetimeColumn(
                "Created At", format="D MMM YYYY, HH:mm"
            ),
            "total_price": st.column_config.NumberColumn(
                "Total Price", format="Rp %d"
            )
        }
    )
