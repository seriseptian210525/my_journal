import pandas as pd
import numpy as np
import re
try:
    from rapidfuzz import process
except ImportError:
    process = None
    print("Warning: rapidfuzz not found. Complaint cleaning will be limited.")

from src.common.config import PipelineConfig, SHEET_KAMUS_KELUHAN, WORKSHEET_TOP_KELUHAN
from src.common.data_loader import DataLoader

class TextProcessor:
    @staticmethod
    def clean_and_split(text):
        """Membersihkan teks dan memecahnya menjadi list standar."""
        if not isinstance(text, str):
            return []

        text_lower = text.lower()
        # Hapus simbol aneh (menggunakan pattern standar)
        text_cleaned = re.sub(r'[^a-z0-9,\s]', '', text_lower)
        # Ganti semua delimiter jadi ;
        text_std = re.sub(r'(,\s*)|(\n)|(\s+(dan|&)\s+)|(\.\s*)', ';', text_cleaned)
        # Split dan strip
        return [item.strip() for item in text_std.split(';') if item.strip()]

    @staticmethod
    def generate_problem_name(part, masalah, section, label_standar):
        """Membuat nama masalah yang user-friendly (Title Case)."""
        part = part.strip().capitalize() if isinstance(part, str) else ""
        masalah = masalah.strip().capitalize() if isinstance(masalah, str) else ""
        section = section.strip().lower() if isinstance(section, str) else ""
        label_standar = label_standar if isinstance(label_standar, str) else ""

        # Handling khusus
        if masalah == 'Aus(twi)':
            masalah = 'Aus/TWI'

        if section == 'neutral':
            return f"{part} {masalah}".strip()
        elif section in ['rear', 'front']:
            section_text = 'Depan' if section == 'front' else 'Belakang'
            return f"{part} {section_text} {masalah}".strip()
        elif section in ['rear/front', 'left/right', 'all']:
            return f"Semua {part} {masalah}".strip()
        else:
            # Fallback ke label standar jika format aneh
            return ' '.join([word.capitalize() for word in label_standar.split('_')])

class ComplaintCleaner:
    def __init__(self, config: PipelineConfig, loader: DataLoader):
        self.config = config
        self.loader = loader
        self.kamus_df = None
        self.threshold = config.FUZZY_THRESHOLD

    def load_dictionary(self):
        """Memuat data kamus dari Google Sheet dan mengubahnya menjadi format grouped."""
        print("\n[ComplaintCleaner] Loading dictionary...")
        if not SHEET_KAMUS_KELUHAN or not WORKSHEET_TOP_KELUHAN:
            print("❌ MISSING CONFIG: SHEET_KAMUS_KELUHAN or WORKSHEET_TOP_KELUHAN not set.")
            return False

        df_raw = self.loader.load_gspread_data(SHEET_KAMUS_KELUHAN, WORKSHEET_TOP_KELUHAN)
        if df_raw.empty:
            print("❌ Dictionary Sheet Empty.")
            return False

        required_cols = ['raw_keluhan', 'part', 'masalah', 'label_standar', 'section']
        # Normalize columns handling
        df_raw.columns = [c.strip() for c in df_raw.columns]
        
        missing = [c for c in required_cols if c not in df_raw.columns]
        if missing:
            print(f"❌ Missing dictionary columns: {missing}")
            return False

        df_clean = df_raw.dropna(subset=required_cols).copy()

        # Grouping
        self.kamus_df = df_clean.groupby(['label_standar', 'section']).agg(
            part=('part', 'first'),
            masalah=('masalah', 'first'),
            raw_keluhan_list=('raw_keluhan', list)
        ).reset_index()

        # Generate Problem Name
        self.kamus_df['problem_name'] = self.kamus_df.apply(
            lambda row: TextProcessor.generate_problem_name(
                row['part'], row['masalah'], row['section'], row['label_standar']
            ), axis=1
        )
        
        print(f"✅ Dictionary loaded with {len(self.kamus_df)} categories.")
        return True

    def _normalize_single_complaint(self, keluhan_text):
        if not isinstance(keluhan_text, str) or self.kamus_df is None:
            return None

        keluhan_clean = keluhan_text.strip().lower()
        if not keluhan_clean: return None
        
        best_match = None
        best_score = -1

        # Optimization: Pre-check exact match before iteration? 
        # But structure requires iteration over list columns.
        # This implementation matches the notebook logic (O(N) * M)
        
        for _, row in self.kamus_df.iterrows():
            raw_list = [str(r).strip().lower() for r in row['raw_keluhan_list']]

            # A. Exact Match
            if keluhan_clean in raw_list:
                return self._format_result(row, keluhan_clean)

            # B. Fuzzy Match (Only if rapidfuzz available)
            if process and raw_list:
                match, score, _ = process.extractOne(keluhan_clean, raw_list)
                if score > self.threshold and score > best_score:
                    best_score = score
                    best_match = self._format_result(row, match)

        return best_match

    def _format_result(self, row, raw_match):
        return {
            'category': row['label_standar'],
            'section': row['section'],
            'part': row['part'],
            'masalah': row['masalah'],
            'problem_name': row['problem_name'],
            'raw_match': raw_match
        }

    def process_dataframe(self, df: pd.DataFrame, col_name='customer_problems'):
        """Runs the full cleaning pipeline on a dataframe column."""
        if not self.load_dictionary():
             print("⚠️ Dictionary load failed. Skipping complaint cleaning.")
             return df
        
        print(f"Processing complaints for {len(df)} rows...")
        
        # 1. Clean & Split
        # Using a temporary list column to hold split complaints
        keluhan_list_col = df[col_name].apply(TextProcessor.clean_and_split)

        # 2. Normalize
        # Since each row can have multiple complaints, we process list of complaints
        def process_row(k_list):
            normalized_results = []
            problem_names = []
            
            for k in k_list:
                res = self._normalize_single_complaint(k)
                if res:
                    normalized_results.append(res)
                    problem_names.append(res['problem_name'])
            
            # If no normalized results found, keep original or empty?
            # Notebook keeps extracted details.
            
            # Return tuple to expand later
            # Logic: If we found standardized problems, use them. 
            # If not, extracted problem string might be empty or original text?
            # User request: "helper cleaning data ... agar output lebih clean"
            
            clean_str = ", ".join(problem_names)
            return clean_str, normalized_results

        # Apply
        results = keluhan_list_col.apply(process_row)
        
        # 3. Assign back to DataFrame
        # We can overwrite customer_problems or create new column.
        # Ideally create 'customer_problems_clean' and maybe overwrite if requested.
        # Let's create 'customer_problems_clean' and 'problem_details' (JSON)
        
        df['customer_problems_clean'] = results.apply(lambda x: x[0])
        df['customer_problems_details'] = results.apply(lambda x: x[1])
        
        # Fill empty clean problems with original? Or keep empty?
        # Usually for analysis, we want mapped data. The unmapped remains as is in original column.
        # But if the user wants "cleaner output", maybe we fallback to original if cleaned is empty.
        mask_empty = df['customer_problems_clean'] == ""
        df.loc[mask_empty, 'customer_problems_clean'] = df.loc[mask_empty, col_name] # Fallback
        
        print("✅ Complaint cleaning completed.")
        return df
