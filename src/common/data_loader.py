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
        self.drive_service = None
        self._connect()

    def _get_drive_service(self, creds_dict=None):
        """Initializes Google Drive API service."""
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        
        SCOPES = ['https://www.googleapis.com/auth/drive.file']
        
        try:
            if creds_dict:
                creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            else:
                creds = service_account.Credentials.from_service_account_file(str(self.service_account_file), scopes=SCOPES)
            
            self.drive_service = build('drive', 'v3', credentials=creds)
            print("✅ Connected to Google Drive API.")
        except Exception as e:
            print(f"⚠️ Failed to connect to Google Drive API: {e}")

    def _connect(self):
        """Authenticates with Google Sheets API."""
        try:
            # 1. Try Streamlit Secrets (Cloud)
            try:
                import streamlit as st
                if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
                    # gspread expects specific keys, ensure st.secrets dict is compatible
                    # st.secrets returns a purely string-based dict which is what we need
                    creds_dict = dict(st.secrets["gcp_service_account"])
                    
                    
                    # Fix private_key if it contains escaped newlines (common issue in TOML/Streamlit secrets)
                    if "private_key" in creds_dict:
                         creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

                    self.client = gspread.service_account_from_dict(creds_dict)
                    print("✅ Connected to Google Sheets via Streamlit Secrets.")
                    
                    # Also init drive service
                    self._get_drive_service(creds_dict)
                    return
            except ImportError:
                pass # Streamlit not installed or not running in streamlit context
            except Exception as e:
                print(f"⚠️ Failed to connect via Streamlit Secrets: {e}")

            # 2. Fallback to File (Local / Env)
            if not self.service_account_file or not os.path.exists(self.service_account_file):
                raise FileNotFoundError(f"Service account file not found: {self.service_account_file}")
            
            self.client = gspread.service_account(filename=str(self.service_account_file))
            print("✅ Connected to Google Sheets via File.")
            
            # Init drive service
            self._get_drive_service()
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

    def upload_csv_to_drive(self, df, folder_id, filename):
        """
        Converts DataFrame to CSV and uploads it directly to Google Drive.
        If a file with the same name exists in the folder, it updates it.
        Otherwise, it creates a new file.
        Returns the file ID.
        """
        import io
        from googleapiclient.http import MediaIoBaseUpload
        
        if not self.drive_service:
            print("❌ Drive service not initialized. Cannot upload to Drive.")
            raise ConnectionError("Google Drive API is not connected.")
            
        try:
            print(f"📤 Exporting {len(df)} rows to CSV format...")
            
            # Write to string buffer
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            csv_buffer.seek(0)
            
            # Check if file exists in folder (include supportsAllDrives=True for Shared Drives)
            query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
            results = self.drive_service.files().list(
                q=query, spaces='drive', fields='files(id, name)',
                includeItemsFromAllDrives=True, supportsAllDrives=True
            ).execute()
            items = results.get('files', [])
            
            media = MediaIoBaseUpload(io.BytesIO(csv_buffer.getvalue().encode('utf-8')), mimetype='text/csv', resumable=True)
            
            if items:
                # Update existing file
                file_id = items[0]['id']
                print(f"   🔄 Updating existing file '{filename}' (ID: {file_id}) in Drive...")
                response = self.drive_service.files().update(
                    fileId=file_id,
                    media_body=media,
                    supportsAllDrives=True
                ).execute()
            else:
                # Create new file
                print(f"   ➕ Creating new file '{filename}' in Drive folder...")
                file_metadata = {
                    'name': filename,
                    'parents': [folder_id],
                    'mimeType': 'text/csv'
                }
                response = self.drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id',
                    supportsAllDrives=True
                ).execute()
                file_id = response.get('id')
                
            print(f"✅ Successfully uploaded '{filename}' to Google Drive (ID: {file_id}).")
            return file_id
            
        except Exception as e:
            print(f"❌ Error uploading to Google Drive: {e}")
            raise e

    def load_csv_from_drive(self, folder_id, filename):
        """
        Download a CSV file from Google Drive and return as Pandas DataFrame.
        """
        self._connect()
        try:
            from googleapiclient.http import MediaIoBaseDownload
            import io
            
            # Find the file ID
            query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
            results = self.drive_service.files().list(
                q=query, spaces='drive', fields='files(id, name)',
                includeItemsFromAllDrives=True, supportsAllDrives=True
            ).execute()
            items = results.get('files', [])
            
            if not items:
                raise FileNotFoundError(f"File '{filename}' not found in Google Drive folder '{folder_id}'.")
                
            file_id = items[0]['id']
            
            # Download file
            request = self.drive_service.files().get_media(fileId=file_id)
            file_buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(file_buffer, request)
            
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                
            file_buffer.seek(0)
            df = pd.read_csv(file_buffer)
            return df
            
        except Exception as e:
            print(f"❌ Error downloading CSV from Google Drive: {e}")
            raise e
            
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
                worksheet = sheet.add_worksheet(title=worksheet_name, rows=len(df)+100, cols=len(df.columns)+5)

            # Build data with guaranteed JSON safety
            headers = [str(col) for col in df.columns.tolist()]
            rows = []
            
            for idx, row in df.iterrows():
                safe_row = [make_json_safe(val) for val in row.values]
                rows.append(safe_row)
            
            # RESIZE WORKSHEET if needed (avoid grid limit error)
            required_rows = len(rows) + 10  # +10 buffer for header and safety
            required_cols = len(headers) + 5  # +5 buffer
            current_rows = worksheet.row_count
            current_cols = worksheet.col_count
            
            if current_rows < required_rows or current_cols < required_cols:
                new_rows = max(current_rows, required_rows)
                new_cols = max(current_cols, required_cols)
                print(f"   📐 Resizing worksheet from {current_rows}x{current_cols} to {new_rows}x{new_cols}...")
                worksheet.resize(rows=new_rows, cols=new_cols)
            
            # Clear existing content
            worksheet.clear()
            
            # BATCH UPLOAD LOGIC - handle large datasets
            BATCH_SIZE = 10000  # 10k rows per batch to avoid API timeout
            total_rows = len(rows)
            
            if total_rows <= BATCH_SIZE:
                # Small dataset - upload all at once
                data = [headers] + rows
                worksheet.update('A1', data, value_input_option='USER_ENTERED')
            else:
                # Large dataset - upload in batches
                print(f"   📦 Large dataset detected. Uploading in batches of {BATCH_SIZE}...")
                
                # First batch includes headers
                first_batch = [headers] + rows[:BATCH_SIZE]
                worksheet.update('A1', first_batch, value_input_option='USER_ENTERED')
                print(f"   ✅ Batch 1/{(total_rows // BATCH_SIZE) + 1} uploaded ({min(BATCH_SIZE, total_rows)} rows)")
                
                # Subsequent batches
                batch_num = 2
                for start_idx in range(BATCH_SIZE, total_rows, BATCH_SIZE):
                    end_idx = min(start_idx + BATCH_SIZE, total_rows)
                    batch_data = rows[start_idx:end_idx]
                    
                    # Calculate starting row (A1 is row 1, header is row 1, data starts row 2)
                    start_row = start_idx + 2  # +1 for header, +1 for 1-indexing
                    
                    worksheet.update(f'A{start_row}', batch_data, value_input_option='USER_ENTERED')
                    print(f"   ✅ Batch {batch_num}/{(total_rows // BATCH_SIZE) + 1} uploaded ({end_idx - start_idx} rows)")
                    batch_num += 1
                    
                    # Small delay to avoid rate limiting
                    import time
                    time.sleep(1)
            
            print(f"✅ Successfully uploaded {total_rows} rows to {worksheet_name}.")
            
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
            
            # IMPORTANT: Reorder DataFrame columns to match existing sheet headers
            # This ensures data is written to correct columns
            df_columns = df.columns.tolist()
            missing_in_sheet = [col for col in df_columns if col not in existing_headers]
            missing_in_df = [col for col in existing_headers if col not in df_columns]
            
            if missing_in_sheet:
                print(f"   ⚠️ Columns in data but not in sheet (will be ignored): {missing_in_sheet}")
            if missing_in_df:
                print(f"   ⚠️ Columns in sheet but not in data (will be empty): {missing_in_df}")
            
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
                
                # Build row in SAME ORDER as existing sheet headers
                safe_row = []
                for header in existing_headers:
                    if header in df.columns:
                        val = row[header]
                        safe_row.append(make_json_safe(val))
                    else:
                        safe_row.append(None)  # Column missing in new data
                
                new_rows.append(safe_row)
                existing_keys.add(key_tuple)  # Prevent duplicates within batch
            
            if not new_rows:
                print(f"   ℹ️ No new rows to append (skipped {skipped} duplicates).")
                return
            
            print(f"   Adding {len(new_rows)} new rows (skipped {skipped} duplicates)...")
            
            # Calculate next row position
            next_row = len(existing_data) + 1
            
            # Check if we need to expand the sheet
            required_rows = next_row + len(new_rows) - 1
            current_max_rows = worksheet.row_count
            
            if required_rows > current_max_rows:
                rows_to_add = required_rows - current_max_rows + 100  # Add buffer
                print(f"   📏 Expanding sheet by {rows_to_add} rows...")
                worksheet.add_rows(rows_to_add)
            
            # Append new rows
            worksheet.update(f'A{next_row}', new_rows, value_input_option='USER_ENTERED')
            print(f"✅ Successfully appended {len(new_rows)} rows to {worksheet_name}.")
            
        except Exception as e:
            print(f"❌ Error appending to {worksheet_name}: {e}")
            raise e
    
    def sort_sheet(self, sheet_id, worksheet_name, sort_column_name, ascending=True):
        """
        Sorts a Google Sheet by a specific column, preserving the header row.
        Uses batch_update to ensure robustness even with many columns.
        """
        try:
            print(f"🔄 Auto-sorting {worksheet_name} by '{sort_column_name}'...")
            sheet = self.client.open_by_key(sheet_id)
            worksheet = sheet.worksheet(worksheet_name)
            
            # Get headers to find the column index
            headers = worksheet.row_values(1)
            if sort_column_name not in headers:
                print(f"   ⚠️ Column '{sort_column_name}' not found. Skipping sort.")
                return
                
            col_idx = headers.index(sort_column_name)
            
            body = {
                "requests": [
                    {
                        "sortRange": {
                            "range": {
                                "sheetId": worksheet.id,
                                "startRowIndex": 1,  # Skip header row (0-indexed)
                            },
                            "sortSpecs": [
                                {
                                    "dimensionIndex": col_idx,
                                    "sortOrder": "ASCENDING" if ascending else "DESCENDING"
                                }
                            ]
                        }
                    }
                ]
            }
            
            sheet.batch_update(body)
            print(f"✅ Successfully sorted {worksheet_name} by {sort_column_name}.")
            
        except Exception as e:
            print(f"❌ Error sorting {worksheet_name}: {e}")
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