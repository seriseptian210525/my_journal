import gspread
import pandas as pd
import os
from .config import SERVICE_ACCOUNT_FILE

class DataLoader:
    """
    Handles connection to Google Sheets and data loading.
    """
    def __init__(self, service_account_file=SERVICE_ACCOUNT_FILE):
        self.service_account_file = service_account_file
        self.client = None
        self._connect()

    def _connect(self):
        """Authenticates with Google Sheets API."""
        try:
            if not self.service_account_file or not os.path.exists(self.service_account_file):
                raise FileNotFoundError(f"Service account file not found: {self.service_account_file}")
            
            self.client = gspread.service_account(filename=str(self.service_account_file))
            print("✅ Connected to Google Sheets.")
        except Exception as e:
            print(f"❌ Connection Failed: {e}")
            raise e

    def load_gspread_data(self, sheet_id, worksheet_name):
        """
        Loads data from a specific Google Sheet and Worksheet.
        """
        try:
            sheet = self.client.open_by_key(sheet_id)
            worksheet = sheet.worksheet(worksheet_name)
            data = worksheet.get_all_values()
            
            if not data:
                print(f"⚠️ Warning: Worksheet '{worksheet_name}' is empty.")
                return pd.DataFrame()

            headers = data[0]
            rows = data[1:]
            df = pd.DataFrame(rows, columns=headers)
            return df
        except Exception as e:
            print(f"❌ Error loading {worksheet_name}: {e}")
            return pd.DataFrame()

    def load_csv(self, filepath):
        """
        Loads data from a CSV file (for local testing or alternative sources).
        """
        try:
            return pd.read_csv(filepath)
        except Exception as e:
            print(f"❌ Error loading CSV {filepath}: {e}")
            return pd.DataFrame()
            
    def upload_to_sheet(self, df, sheet_id, worksheet_name):
        """
        Uploads a DataFrame to a specific Google Sheet and Worksheet.
        Replaces existing content.
        Uses USER_ENTERED option to preserve numeric and date formats.
        """
        try:
            print(f"📤 Uploading {len(df)} rows to {worksheet_name}...")
            sheet = self.client.open_by_key(sheet_id)
            try:
                worksheet = sheet.worksheet(worksheet_name)
            except gspread.WorksheetNotFound:
                print(f"⚠️ Worksheet '{worksheet_name}' not found. Creating it...")
                worksheet = sheet.add_worksheet(title=worksheet_name, rows=len(df)+100, cols=len(df.columns))

            # Prepare dataframe for upload
            df_clean = self._prepare_df_for_upload(df)
            
            # Prepare data: header + rows
            data = [df_clean.columns.values.tolist()] + df_clean.values.tolist()
            
            # Clear and update with USER_ENTERED option
            # This makes Google Sheets parse values as if user typed them directly
            worksheet.clear()
            worksheet.update('A1', data, value_input_option='USER_ENTERED')
            print(f"✅ Successfully uploaded to {worksheet_name}.")
            
        except Exception as e:
            print(f"❌ Error uploading to {worksheet_name}: {e}")
            raise e
    
    def _prepare_df_for_upload(self, df):
        """
        Internal function to clean and format DataFrame before upload.
        - Converts datetime columns to string with appropriate format (date or datetime).
        - Replaces infinity and NaN with empty string.
        - Preserves numeric types for proper Google Sheets interpretation.
        """
        import numpy as np
        
        df_copy = df.copy()

        # Smart datetime formatting - detect date-only vs datetime
        for col in df_copy.columns:
            if pd.api.types.is_datetime64_any_dtype(df_copy[col]):
                # Check if all non-null values are date-only (no time component)
                is_date_only = (df_copy[col].dropna().dt.normalize() == df_copy[col].dropna()).all()
                if is_date_only:
                    df_copy[col] = df_copy[col].dt.strftime('%Y-%m-%d')
                else:
                    df_copy[col] = df_copy[col].dt.strftime('%Y-%m-%d %H:%M:%S')

        # Replace infinity values with NaN, then fill NaN with empty string
        df_copy.replace([np.inf, -np.inf], np.nan, inplace=True)
        df_copy.fillna('', inplace=True)
        
        return df_copy

# Legacy support functions (to be deprecated)
def get_gspread_client():
    loader = DataLoader()
    return loader.client

def load_from_google_sheet(client, sheet_id, worksheet_name):
    # This is a bit hacky to support old calls, ideally we use the class instance
    # But since old calls pass 'client', we can just use the library directly or ignore client if we use the class
    # To be safe and support legacy, let's just use the logic here but typically we want to move to DataLoader instance
    try:
        sheet = client.open_by_key(sheet_id)
        worksheet = sheet.worksheet(worksheet_name)
        data = worksheet.get_all_values()
        if not data: return pd.DataFrame()
        return pd.DataFrame(data[1:], columns=data[0])
    except Exception as e:
        print(f"Error: {e}")
        return pd.DataFrame()