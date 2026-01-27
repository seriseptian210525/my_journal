import pandas as pd
import numpy as np
import re
import warnings
from fuzzywuzzy import fuzz
from tqdm.auto import tqdm

# Settings
warnings.filterwarnings('ignore')
tqdm.pandas()

class ServiceItemsPipeline:
    def __init__(self, service_df, mapping_df, bike_df):
        """
        Initializes the Service Items Pipeline.
        :param service_df: Main data (ELSA Work Orders)
        :param mapping_df: Mapping data (Regex + Price + SKU)
        :param bike_df: Bike database (SCM)
        """
        self.raw_service = service_df
        self.mapping_df = mapping_df
        self.bike_df = bike_df
        self.df = None

        # Prepare Mapping Data
        # Filter rows where regex is present
        self.mapping_df = self.mapping_df[self.mapping_df['Pola (Regex)'].notna()]
        # Calculate pattern length for sorting (prioritize longer patterns)
        self.mapping_df['pattern_length'] = self.mapping_df['Pola (Regex)'].astype(str).str.len()
        self.sorted_mapping = self.mapping_df.sort_values(by='pattern_length', ascending=False).drop(columns='pattern_length')

    # --- HELPER STATIC METHODS ---
    @staticmethod
    def _transpose_row_logic(row):
        """
        Splits multi-item strings (comma, newline, etc.) into individual rows.
        """
        part_string = str(row['item_name'])
        if not part_string or part_string.strip() == 'nan' or part_string.strip().lower() == 'none':
            return []

        # Cleaning delimiters: newline, ' dan ', ' & ', ' / ', bullet points
        part_list_raw = part_string.replace('\n', ',').replace(' dan ', ',').replace(' & ', ',').replace(' / ', ',').replace('• ', ',')
        part_list = [k.strip() for k in part_list_raw.split(',') if k.strip()]

        new_rows = []
        # Drop item_name from original row as we will add the split item
        original_data = row.drop(['item_name']).to_dict()

        for part in part_list:
            new_data = original_data.copy()
            new_data['item_name'] = part
            new_rows.append(new_data)

        return new_rows

    @staticmethod
    def _smart_fuzzy_match(text, part_list, threshold=85):
        """
        Fuzzy matching logic with token priority.
        """
        if pd.isna(text) or not isinstance(text, str) or text.strip() == '':
            return None

        text_clean = text.strip().lower()
        # Remove non-alphanumeric (except hyphens)
        text_tokens = set(re.sub(r'[^\w\s-]', '', text_clean).split())

        best_part = None
        best_score = 0

        for part in part_list:
            if pd.isna(part): continue
            part_clean = part.strip().lower()
            part_tokens = set(re.sub(r'[^\w\s-]', '', part_clean).split())

            # 1. Exact Match
            if text_clean == part_clean: return part

            # 2. Token Subset (if all tokens of one are in the other)
            if (text_tokens.issubset(part_tokens) and text_tokens) or (part_tokens.issubset(text_tokens) and part_tokens):
                score = max(len(text_tokens)/len(part_tokens), len(part_tokens)/len(text_tokens)) * 100
                if score > best_score:
                    best_score = score
                    best_part = part
                continue

            # 3. Fuzzy Fallback
            if best_score < 100:
                fuzzy_val = fuzz.partial_ratio(text_clean, part_clean)
                if fuzzy_val > best_score and fuzzy_val >= threshold:
                    best_score = fuzzy_val
                    best_part = part

        return best_part if best_score >= threshold else None

    # --- PROCESS METHODS ---

    def process_transpose(self):
        """
        Step 1: Transpose `item_name` into individual rows.
        """
        print(">>> [Step 1] Transposing Data...")

        # Sort by created_at if available
        if 'created_at' in self.raw_service.columns:
            try:
                self.raw_service['created_at'] = pd.to_datetime(self.raw_service['created_at'])
                df_clean = self.raw_service.sort_values(by='created_at', ascending=True).reset_index(drop=True)
            except Exception:
                df_clean = self.raw_service.copy()
        else:
            df_clean = self.raw_service.copy()

        # Filter valid items
        mask_valid = (df_clean['item_name'].notna()) & (df_clean['item_name'].astype(str).str.strip() != '') & (df_clean['item_name'].astype(str).str.lower() != 'nan')
        df_to_process = df_clean[mask_valid]

        # Apply transpose logic
        # Note: apply with axis=1 returns a Series of lists. .sum() concatenates them into one big list.
        transposed_list = df_to_process.apply(self._transpose_row_logic, axis=1).sum()
        
        if not transposed_list:
             print("⚠️ Warning: No items found to transpose.")
             self.df = pd.DataFrame(columns=df_to_process.columns)
             return self.df

        self.df = pd.DataFrame(transposed_list)

        # Type Casting for specific columns
        if 'odometer' in self.df.columns:
            self.df['odometer'] = self.df['odometer'].astype(str).str.replace(r'\D+', '', regex=True)
            self.df['odometer'] = pd.to_numeric(self.df['odometer'], errors='coerce').fillna(0).astype(int)

        print(f"✅ Transpose Complete. Total Individual Rows: {len(self.df)}")
        return self.df

    def process_regex_mapping(self):
        """
        Step 2: Regex Mapping using `item_name`, `color`, and `bike_type`.
        """
        print(">>> [Step 2] Running Regex Mapping...")

        # Clean item name for matching
        self.df['item_name_cleaned'] = self.df['item_name'].astype(str).str.replace(r'[\[\]\(\)]', '', regex=True)
        
        conditions = []
        values = []

        # Iterate through sorted mapping rules
        for _, row in self.sorted_mapping.iterrows():
            regex_pattern = row['Pola (Regex)']
            if pd.isna(regex_pattern) or regex_pattern == '': continue
            
            try:
                # Base condition: Regex match on item_name
                cond = self.df['item_name_cleaned'].str.contains(regex_pattern, case=False, na=False, regex=True)

                # Additional Condition: Color
                if pd.notna(row.get('Warna Unit')) and str(row.get('Warna Unit')).lower() != 'neutral':
                    if 'color' in self.df.columns:
                        colors = [c.strip().lower() for c in str(row['Warna Unit']).split(',')]
                        cond &= self.df['color'].astype(str).str.lower().isin(colors)

                # Additional Condition: Bike Type
                if pd.notna(row.get('Tipe Motor')) and str(row.get('Tipe Motor')).upper() != 'GEN':
                    if 'bike_type' in self.df.columns:
                        target_type = str(row['Tipe Motor']).strip().upper()
                        cond &= self.df['bike_type'].astype(str).str.upper() == target_type

                if cond.any():
                    conditions.append(cond)
                    values.append(row['Rekomendasi Nama Part Baru'])
            except Exception as e:
                print(f"⚠️ Error applying regex '{regex_pattern}': {e}")
                continue

        # Apply conditions driven by np.select (First match wins because 'conditions' is ordered by pattern length? 
        # Actually np.select checks condition 1, then 2. The order in 'conditions' matters.
        # We sorted mapping by pattern_length DESC, so specific/long patterns check first.
        if conditions:
            self.df['mapped_item_name'] = np.select(conditions, values, default=self.df['item_name_cleaned'])
        else:
            self.df['mapped_item_name'] = self.df['item_name_cleaned']

        self.df = self.df.drop(columns=['item_name_cleaned'])
        print("✅ Regex Mapping Complete.")
        return self.df

    def process_fuzzy_matching(self):
        """
        Step 3: Fuzzy Matching, Ignore Part Filtering, and Deduplication.
        """
        print(">>> [Step 3] Running Fuzzy Matching...")

        target_parts = [p for p in self.mapping_df['Rekomendasi Nama Part Baru'].unique() if pd.notna(p)]

        # Fuzzy Match
        self.df['Rekomendasi Nama Part Baru'] = self.df['mapped_item_name'].progress_apply(
            lambda x: self._smart_fuzzy_match(x, target_parts, threshold=85)
        )

        # --- CLEANING ---
        # 1. Drop NaN results (No match found > threshold)
        self.df = self.df.dropna(subset=['Rekomendasi Nama Part Baru'])

        # 2. Drop 'Ignore Part'
        print(">>> Filtering 'Ignore Part'...")
        before_ignore = len(self.df)
        self.df = self.df[self.df['Rekomendasi Nama Part Baru'].astype(str).str.lower() != 'ignore part']
        print(f"   Dropped {before_ignore - len(self.df)} rows (Ignore Part).")

        # 3. Drop Duplicates (Prevent double counting for sequence)
        # Subset: License Plate, Order ID, Part Name
        subset_cols = ['vehicle_license_plate', 'order_id', 'Rekomendasi Nama Part Baru']
        existing_subset = [c for c in subset_cols if c in self.df.columns]
        
        before_dedup = len(self.df)
        self.df = self.df.drop_duplicates(subset=existing_subset)
        print(f"   Dropped {before_dedup - len(self.df)} rows (Duplicates within same Service Order).")

        print(f"✅ Fuzzy & Cleaning Complete. Total Valid Rows: {len(self.df)}")
        return self.df

    def enrich_data(self):
        """
        Step 4: Enrich with Prices, SKU, Bike Info, Warranty Logic.
        """
        print(">>> [Step 4] Enriching Data (Prices, SKU, Warranty)...")

        # 1. Merge Bike Info
        # Rename 'Plate Number' -> 'vehicle_license_plate' to match raw data
        if 'Plate Number' in self.bike_df.columns:
            bike_info = self.bike_df[['Plate Number', 'Delivery - Outbone', 'BPKB Owner']].copy()
            bike_info = bike_info.rename(columns={'Plate Number': 'vehicle_license_plate'})
            
            # Ensure vehicle_license_plate is string
            self.df['vehicle_license_plate'] = self.df['vehicle_license_plate'].astype(str)
            bike_info['vehicle_license_plate'] = bike_info['vehicle_license_plate'].astype(str)

            self.df = pd.merge(self.df, bike_info, on='vehicle_license_plate', how='left')
        
        # 2. Merge Mapping Info (Price, SKU, Warranty Period, Product Name)
        cols_to_merge = ['Rekomendasi Nama Part Baru', 'Product Name', 'Cost Price', 'Base Price', 'New SKU', 'ERP Product ID', 'Periode Garansi']
        available_cols = [c for c in cols_to_merge if c in self.mapping_df.columns]
        
        # Take unique mapping rows for these columns
        mapping_subset = self.mapping_df[available_cols].drop_duplicates(subset=['Rekomendasi Nama Part Baru'])
        self.df = pd.merge(self.df, mapping_subset, on='Rekomendasi Nama Part Baru', how='left')

        # 3. Calculate Age (Bulan Ke)
        if 'Delivery - Outbone' in self.df.columns and 'created_at' in self.df.columns:
            self.df['Delivery - Outbone'] = pd.to_datetime(self.df['Delivery - Outbone'], errors='coerce')
            # Calculate months diff: (created_at - delivery_date) / 30.44
            self.df['Bulan Ke'] = ((self.df['created_at'] - self.df['Delivery - Outbone']).dt.days / 30.44).fillna(6).astype(int)
            # Clip negative values to 0? Or keep as is? Assuming >= 0.
            self.df['Bulan Ke'] = self.df['Bulan Ke'].apply(lambda x: max(0, x))

        # 4. Calculate Sequence (Pergantian Ke-n)
        if 'created_at' in self.df.columns:
            self.df = self.df.sort_values('created_at')
        
        # Group by Plate + Part Name -> Cumulative Count (Global)
        self.df['Pergantian Ke'] = self.df.groupby(['vehicle_license_plate', 'Rekomendasi Nama Part Baru']).cumcount() + 1

        # 5. Warranty Logic (Categorical, Priority-based)
        print("   Calculating Warranty status...")
        
        p_name = self.df['Rekomendasi Nama Part Baru']
        p_count = self.df['Pergantian Ke']
        
        if 'Periode Garansi' in self.df.columns:
             self.df['Periode Garansi'] = pd.to_numeric(self.df['Periode Garansi'], errors='coerce').fillna(0).astype(int)
        
        # Check customer type
        if 'convert_customer_type' in self.df.columns:
            is_electrum = self.df['convert_customer_type'].astype(str).str.upper() == 'ELECTRUM_USER'
            is_partner = self.df['convert_customer_type'].astype(str).str.upper() == 'PARTNER_USER'
        else:
            is_electrum = pd.Series([False] * len(self.df), index=self.df.index)
            is_partner = pd.Series([False] * len(self.df), index=self.df.index)
        
        # Calculate year-based reset for PARTNER_USER
        # Reset "Pergantian Ke" every 12 months
        if 'Bulan Ke' in self.df.columns:
            bulan_ke = self.df['Bulan Ke']
        else:
            bulan_ke = pd.Series([0] * len(self.df), index=self.df.index)
        year_cycle = (bulan_ke // 12).astype(int)
        
        # Group by Plate + Part + Year Cycle -> Cumulative Count (Reset per year)
        # Store year_cycle as a temp column for groupby
        self.df['_year_cycle'] = year_cycle
        self.df['Pergantian Ke Reset'] = self.df.groupby(
            ['vehicle_license_plate', 'Rekomendasi Nama Part Baru', '_year_cycle']
        ).cumcount() + 1
        self.df = self.df.drop(columns=['_year_cycle'])
        
        p_count_reset = self.df['Pergantian Ke Reset']
        
        # PACKAGE_SERVICE conditions:
        # ELECTRUM_USER: Only Brake Pad (1-6), NO yearly reset
        cond_package_electrum = (
            is_electrum &
            p_name.isin(['Rear Brake Pad', 'Front Brake Pad']) &
            p_count.isin(range(1, 7))
        )
        
        # PARTNER_USER: Tire (1-2) + Brake Pad (1-6), WITH yearly reset
        cond_package_partner = (
            is_partner &
            (
                (p_name.isin(['Rear Tire KENDA', 'Front Tire KENDA']) & p_count_reset.isin([1, 2])) |
                (p_name.isin(['Rear Brake Pad', 'Front Brake Pad']) & p_count_reset.isin(range(1, 7)))
            )
        )
        
        cond_package = cond_package_electrum | cond_package_partner
        
        # WARRANT: Month Age < Warranty Period
        if 'Bulan Ke' in self.df.columns:
            current_month = self.df['Bulan Ke']
        else:
            current_month = pd.Series([999] * len(self.df), index=self.df.index)
        
        if 'Periode Garansi' in self.df.columns:
            warranty_period = self.df['Periode Garansi']
        else:
            warranty_period = pd.Series([0] * len(self.df), index=self.df.index)
        cond_warranty = (current_month < warranty_period)
        
        # INSURANCE: Body parts, frame, mirrors (Placeholder - can be extended)
        insurance_parts = [
            'Body Cover', 'Front Fender', 'Rear Fender', 'Side Cover',
            'Rear Mirror', 'Plate Number Cover', 'Frame'
        ]
        cond_insurance = p_name.isin(insurance_parts)
        
        # Apply priority-based logic
        conds = [
            cond_package,    # Priority 1
            cond_warranty,   # Priority 2
            cond_insurance   # Priority 3
        ]
        choices = ['PACKAGE_SERVICE', 'WARRANT', 'INSURANCE']
        
        self.df['Warranty'] = np.select(conds, choices, default='NOT_COVERED')
        
        # Status Coverage (Electrum covers PACKAGE_SERVICE and WARRANT)
        self.df['Status Coverage'] = np.where(
            self.df['Warranty'].isin(['PACKAGE_SERVICE', 'WARRANT']), 
            'Electrum', 
            'Partner'
        )

        # Location Type
        if 'service_location_name' in self.df.columns:
            self.df['Jenis Lokasi'] = np.where(
                self.df['service_location_name'].isin(['Grab Cakung', 'Pondok Indah']),
                'Internal Service Center', 'Official Partner'
            )

        print("✅ Data Enrichment Complete.")
        return self.df

    def format_output(self):
        """
        Format output DataFrame for Google Sheets with specific column structure.
        
        Output Columns:
        - Order Number, Vehicle License Plate, Vehicle Vin, Vehicle Engine
        - Item Type (SPAREPART), Item Name, Base Price, Final Price
        - Qty, Subtotal Price, Warranty, Status (APPLIED), Sku, Erp Product ID
        """
        print(">>> [Step 5] Formatting Output for Google Sheets...")
        
        if self.df is None:
            raise ValueError("Pipeline has not been run. Call run() first.")
        
        # ERP Product IDs with default Qty = 2
        DEFAULT_QTY_2_ERP_IDS = [1735, 1742, 1736, 1762]
        
        # Create a copy to avoid modifying original
        output_df = self.df.copy()
        
        # Ensure ERP Product ID is numeric for comparison
        if 'ERP Product ID' in output_df.columns:
            output_df['ERP Product ID'] = pd.to_numeric(output_df['ERP Product ID'], errors='coerce').fillna(0).astype(int)
        
        # Calculate Qty
        # Step 1: Count occurrences of same Product Name within same Order Number
        if 'order_id' in output_df.columns and 'Product Name' in output_df.columns:
            output_df['_count'] = output_df.groupby(['order_id', 'Product Name'])['Product Name'].transform('count')
        else:
            output_df['_count'] = 1
        
        # Step 2: Apply default Qty=2 for specific ERP Product IDs, otherwise use count
        if 'ERP Product ID' in output_df.columns:
            output_df['Qty'] = np.where(
                output_df['ERP Product ID'].isin(DEFAULT_QTY_2_ERP_IDS),
                2,
                output_df['_count']
            )
        else:
            output_df['Qty'] = output_df['_count']
        
        output_df = output_df.drop(columns=['_count'])
        
        # Deduplicate rows with same order_id + Product Name (keep first, Qty already calculated)
        if 'order_id' in output_df.columns and 'Product Name' in output_df.columns:
            output_df = output_df.drop_duplicates(subset=['order_id', 'Product Name'], keep='first')
        
        # Ensure Base Price is numeric
        if 'Base Price' in output_df.columns:
            output_df['Base Price'] = pd.to_numeric(output_df['Base Price'], errors='coerce').fillna(0)
        else:
            output_df['Base Price'] = 0
        
        # Calculate Final Price (= Base Price, since we're not calculating INTERNAL_COVER)
        output_df['Final Price'] = output_df['Base Price']
        
        # Calculate Subtotal Price (Base Price * Qty)
        output_df['Subtotal Price'] = output_df['Base Price'] * output_df['Qty']
        
        # Add static columns
        output_df['Item Type'] = 'SPAREPART'
        output_df['Status'] = 'APPLIED'
        
        # Rename columns for output
        column_mapping = {
            'order_id': 'Order Number',
            'vehicle_license_plate': 'Vehicle License Plate',
            'vehicle_vin': 'Vehicle Vin',
            'vehicle_engine': 'Vehicle Engine',
            'Product Name': 'Item Name',
            'New SKU': 'Sku',
            'ERP Product ID': 'Erp Product ID'
        }
        
        # Apply renaming for existing columns
        for old_col, new_col in column_mapping.items():
            if old_col in output_df.columns:
                output_df = output_df.rename(columns={old_col: new_col})
        
        # Define final output column order
        final_columns = [
            'Order Number',
            'Vehicle License Plate',
            'Vehicle Vin',
            'Vehicle Engine',
            'Item Type',
            'Item Name',
            'Base Price',
            'Final Price',
            'Qty',
            'Subtotal Price',
            'Warranty',
            'Status',
            'Sku',
            'Erp Product ID'
        ]
        
        # Select only columns that exist
        available_columns = [col for col in final_columns if col in output_df.columns]
        
        # Add missing columns with empty values
        for col in final_columns:
            if col not in output_df.columns:
                output_df[col] = ''
        
        output_df = output_df[final_columns]
        
        print(f"✅ Output Formatted. Total Rows: {len(output_df)}")
        return output_df

    def run(self):
        """
        Executes the full pipeline sequence.
        Returns the enriched DataFrame (full data).
        """
        self.process_transpose()
        self.process_regex_mapping()
        self.process_fuzzy_matching()
        self.enrich_data()
        return self.df

    def run_with_output(self):
        """
        Executes the full pipeline and returns both:
        - Full enriched DataFrame
        - Formatted output DataFrame for Google Sheets
        """
        self.run()
        formatted_output = self.format_output()
        return self.df, formatted_output
