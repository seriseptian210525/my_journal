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
        import numpy as np
        import math
        
        def make_json_safe(val):
            """Convert any value to be JSON compliant."""
            if val is None:
                return None
            
            # Handle pandas NaT
            if pd.isna(val):
                return None
            
            # Handle numpy/python floats - check for inf/nan
            if isinstance(val, (float, np.floating)):
                if math.isnan(val) or math.isinf(val):
                    return None
                return float(val)
            
            # Handle numpy integers
            if isinstance(val, (np.integer,)):
                return int(val)
            
            # Handle numpy bool
            if isinstance(val, np.bool_):
                return bool(val)
            
            # Handle datetime
            if isinstance(val, (pd.Timestamp, np.datetime64)):
                try:
                    ts = pd.Timestamp(val)
                    if pd.isna(ts):
                        return None
                    if ts.hour == 0 and ts.minute == 0 and ts.second == 0:
                        return ts.strftime('%Y-%m-%d')
                    return ts.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    return str(val) if val else None
            
            # Handle strings - empty strings become None
            if isinstance(val, str):
                return val if val.strip() else None
            
            # Handle numpy arrays/lists
            if isinstance(val, (np.ndarray, list)):
                return str(val)
            
            return val
        
        try:
            print(f"📤 Uploading {len(df)} rows to {worksheet_name}...")
            sheet = self.client.open_by_key(sheet_id)
            try:
                worksheet = sheet.worksheet(worksheet_name)
            except gspread.WorksheetNotFound:
                print(f"⚠️ Worksheet '{worksheet_name}' not found. Creating it...")
                worksheet = sheet.add_worksheet(title=worksheet_name, rows=len(df)+100, cols=len(df.columns))

            # Build data with guaranteed JSON safety
            headers = [str(col) for col in df.columns.tolist()]
            rows = []
            
            for idx, row in df.iterrows():
                safe_row = [make_json_safe(val) for val in row.values]
                rows.append(safe_row)
            
            data = [headers] + rows
            
            # Clear and update with USER_ENTERED option
            worksheet.clear()
            worksheet.update('A1', data, value_input_option='USER_ENTERED')
            print(f"✅ Successfully uploaded to {worksheet_name}.")
            
        except Exception as e:
            print(f"❌ Error uploading to {worksheet_name}: {e}")
            raise e
    
    def append_to_sheet(self, df, sheet_id, worksheet_name, key_columns=None):
        """
        Append new rows to existing sheet, checking for duplicates.
        
        Args:
            df: DataFrame to append
            sheet_id: Google Sheet ID
            worksheet_name: Name of the worksheet
            key_columns: List of columns to use for deduplication (default: ['order_id'])
        """
        import numpy as np
        import math
        
        if key_columns is None:
            key_columns = ['order_id']
        
        def make_json_safe(val):
            """Convert any value to be JSON compliant."""
            if val is None:
                return None
            if pd.isna(val):
                return None
            if isinstance(val, (float, np.floating)):
                if math.isnan(val) or math.isinf(val):
                    return None
                return float(val)
            if isinstance(val, (np.integer,)):
                return int(val)
            if isinstance(val, np.bool_):
                return bool(val)
            if isinstance(val, (pd.Timestamp, np.datetime64)):
                try:
                    ts = pd.Timestamp(val)
                    if pd.isna(ts):
                        return None
                    if ts.hour == 0 and ts.minute == 0 and ts.second == 0:
                        return ts.strftime('%Y-%m-%d')
                    return ts.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    return str(val) if val else None
            if isinstance(val, str):
                return val if val.strip() else None
            if isinstance(val, (np.ndarray, list)):
                return str(val)
            return val
        
        try:
            print(f"📤 Appending up to {len(df)} rows to {worksheet_name}...")
            sheet = self.client.open_by_key(sheet_id)
            
            try:
                worksheet = sheet.worksheet(worksheet_name)
            except gspread.WorksheetNotFound:
                print(f"⚠️ Worksheet '{worksheet_name}' not found. Creating with full data...")
                # If sheet doesn't exist, create and upload all
                return self.upload_to_sheet(df, sheet_id, worksheet_name)
            
            # Read existing data to check for duplicates
            existing_data = worksheet.get_all_values()
            
            if not existing_data:
                print("   Sheet is empty, uploading all data...")
                return self.upload_to_sheet(df, sheet_id, worksheet_name)
            
            existing_headers = existing_data[0]
            existing_rows = existing_data[1:]
            
            # Build set of existing keys for fast lookup
            existing_keys = set()
            key_indices = []
            
            for col in key_columns:
                if col in existing_headers:
                    key_indices.append(existing_headers.index(col))
            
            if not key_indices:
                print(f"   ⚠️ Key columns {key_columns} not found in sheet. Appending all...")
            else:
                for row in existing_rows:
                    key_parts = []
                    for idx in key_indices:
                        if idx < len(row):
                            key_parts.append(str(row[idx]).strip().lower())
                    if key_parts:
                        existing_keys.add(tuple(key_parts))
                
                print(f"   Found {len(existing_keys)} existing records.")
            
            # Filter out duplicates from new data
            new_rows = []
            skipped = 0
            
            for idx, row in df.iterrows():
                # Build key from new row
                key_parts = []
                for col in key_columns:
                    if col in df.columns:
                        val = row[col]
                        key_parts.append(str(val).strip().lower() if pd.notna(val) else '')
                
                key_tuple = tuple(key_parts)
                
                if key_tuple in existing_keys:
                    skipped += 1
                    continue
                
                # Convert row to JSON-safe list
                safe_row = [make_json_safe(val) for val in row.values]
                new_rows.append(safe_row)
                existing_keys.add(key_tuple)  # Prevent duplicates within batch
            
            if not new_rows:
                print(f"   ℹ️ No new rows to append (skipped {skipped} duplicates).")
                return
            
            print(f"   Adding {len(new_rows)} new rows (skipped {skipped} duplicates)...")
            
            # Calculate next row position
            next_row = len(existing_data) + 1
            
            # Append new rows
            worksheet.update(f'A{next_row}', new_rows, value_input_option='USER_ENTERED')
            print(f"✅ Successfully appended {len(new_rows)} rows to {worksheet_name}.")
            
        except Exception as e:
            print(f"❌ Error appending to {worksheet_name}: {e}")
            raise e
    
    def _prepare_df_for_upload(self, df):
        """
        Internal function to clean and format DataFrame before upload.
        Uses a safe approach that converts everything to native Python types
        without relying on pandas operations that can fail on mixed types.
        """
        import numpy as np
        
        def safe_convert(val):
            """Convert any value to Google Sheets compatible format."""
            # Handle None and NaN
            if val is None:
                return None
            
            # Handle pandas NaT (Not a Time)
            if isinstance(val, pd.NaT.__class__):
                return None
            
            # Check for NaN (works for numpy and python floats)
            try:
                if pd.isna(val):
                    return None
            except (TypeError, ValueError):
                pass
            
            # Handle infinity
            try:
                if np.isinf(val):
                    return None
            except (TypeError, ValueError):
                pass
            
            # Handle numpy integer types
            if isinstance(val, (np.integer, np.int64, np.int32, np.int16, np.int8)):
                return int(val)
            
            # Handle numpy float types
            if isinstance(val, (np.floating, np.float64, np.float32, np.float16)):
                if np.isnan(val) or np.isinf(val):
                    return None
                return float(val)
            
            # Handle numpy bool
            if isinstance(val, np.bool_):
                return bool(val)
            
            # Handle datetime types
            if isinstance(val, (pd.Timestamp, np.datetime64)):
                try:
                    ts = pd.Timestamp(val)
                    if pd.isna(ts):
                        return None
                    # Check if date-only (no time component)
                    if ts.hour == 0 and ts.minute == 0 and ts.second == 0 and ts.microsecond == 0:
                        return ts.strftime('%Y-%m-%d')
                    return ts.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    return str(val)
            
            # Handle numpy arrays and lists
            if isinstance(val, (np.ndarray, list)):
                return str(val)
            
            # Handle strings
            if isinstance(val, str):
                return val if val.strip() != '' else None
            
            # For everything else, return as-is
            return val
        
        # Convert DataFrame to list of lists with safe conversion
        # This avoids all pandas dtype issues
        headers = df.columns.tolist()
        rows = []
        
        for idx, row in df.iterrows():
            converted_row = [safe_convert(val) for val in row.values]
            rows.append(converted_row)
        
        # Create new DataFrame from converted data
        df_clean = pd.DataFrame(rows, columns=headers)
        
        return df_clean

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