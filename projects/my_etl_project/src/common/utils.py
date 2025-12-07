import pandas as pd
import numpy as np
import re
import random
from datetime import datetime, timedelta
from snowflake import SnowflakeGenerator

class ServiceUtils:
    """
    Static utility methods for the ETL pipeline.
    """

    @staticmethod
    def format_plat_nomor(plat_nomor):
        if not isinstance(plat_nomor, str):
            return None

        # Bersihkan karakter selain huruf dan angka
        plat_nomor_cleaned = re.sub(r'[^A-Za-z0-9]', '', plat_nomor).upper()

        if not plat_nomor_cleaned:
            return None

        plat_nomor_cleaned = plat_nomor_cleaned[:8]

        # Regex User
        match = re.match(r'^([A-Z])(\d{1,4})([A-Z]{0,3})$', plat_nomor_cleaned)

        if match:
            huruf_depan, angka, huruf_belakang = match.groups()
            formatted_plat = f"{huruf_depan} {angka}"
            if huruf_belakang:
                formatted_plat += f" {huruf_belakang}"
            return formatted_plat

        return None

    @staticmethod
    def combine_columns_to_string(row, columns_list):
        parts = []
        for col in columns_list:
            if col in row.index:
                val = row[col]
                if pd.notna(val) and str(val).strip() != '':
                    parts.append(str(val).strip())
        return ', '.join(parts)

    @staticmethod
    def randomize_work_hours(dt_val):
        """
        Mengubah jam 00:00:00 atau jam aneh menjadi jam kerja random (07:00 - 23:00).
        """
        if pd.isna(dt_val): return dt_val

        # Pastikan input adalah datetime
        if not isinstance(dt_val, (datetime, pd.Timestamp)):
            return dt_val

        # Cek komponen jam
        try:
            t = dt_val.time()
            # Logic: Jika jam persis 00:00:00 ATAU diluar range wajar (0-6 pagi)
            # Kita set ke jam kerja 07:00 - 23:00
            is_midnight = (t.hour == 0 and t.minute == 0 and t.second == 0)
            is_too_early = (t.hour < 7)

            if is_midnight or is_too_early:
                random_hour = random.randint(7, 23)
                random_minute = random.randint(0, 59)
                random_second = random.randint(0, 59)
                return dt_val.replace(hour=random_hour, minute=random_minute, second=random_second)
        except:
            pass

        return dt_val

    @staticmethod
    def fill_timeline(row):
        """
        Logika pintar mengisi timeline (Time Travel Logic).
        """
        created = row.get('created_at', pd.NaT)
        updated = row.get('updated_at', pd.NaT)
        completed = row.get('completed_at', pd.NaT)
        prize = row.get('prize_finalized_at', pd.NaT)

        def is_valid(dt): return pd.notna(dt)

        # 1. Tentukan Anchor
        anchor = None
        anchor_type = None

        if is_valid(completed):
            anchor = completed; anchor_type = 'completed'
        elif is_valid(created):
            anchor = created; anchor_type = 'created'
        elif is_valid(updated):
            anchor = updated; anchor_type = 'updated'

        if not anchor: return row

        # Pastikan anchor punya jam kerja yang masuk akal (07-23)
        anchor = ServiceUtils.randomize_work_hours(anchor)

        # 2. Logika Pengisian Relatif
        dur_service = timedelta(minutes=random.randint(30, 90))
        dur_start = timedelta(minutes=random.randint(5, 20))
        dur_admin = timedelta(minutes=random.randint(5, 15))

        if anchor_type == 'completed':
            completed = anchor
            if not is_valid(updated): updated = completed - dur_service
            if not is_valid(created): created = updated - dur_start
            if not is_valid(prize): prize = completed + dur_admin

        elif anchor_type == 'created':
            created = anchor
            if not is_valid(updated): updated = created + dur_start
            if not is_valid(completed): completed = updated + dur_service
            if not is_valid(prize): prize = completed + dur_admin

        elif anchor_type == 'updated':
            updated = anchor
            if not is_valid(created): created = updated - dur_start
            if not is_valid(completed): completed = updated + dur_service
            if not is_valid(prize): prize = completed + dur_admin

        # 3. Enforce Chronological Order (Fix inconsistencies)
        # Rule: created <= updated <= completed <= prize
        
        # Helper to push forward if B < A
        def ensure_order(a, b, min_delta_min=5, max_delta_min=60):
            if is_valid(a) and is_valid(b) and b < a:
                # If b is earlier than a, push b to a + random delta
                return a + timedelta(minutes=random.randint(min_delta_min, max_delta_min))
            return b

        updated = ensure_order(created, updated, 5, 30)
        completed = ensure_order(updated, completed, 15, 90)
        prize = ensure_order(completed, prize, 5, 60)

        row['created_at'] = created
        row['updated_at'] = updated
        row['completed_at'] = completed
        row['prize_finalized_at'] = prize

        return row

    @staticmethod
    def robust_date_parse(series, source_name="Unknown"):
        """
        Helper: Parsing tanggal yang aman untuk tipe campuran (String & Timestamp).
        """
        if series.isna().all(): return pd.to_datetime(series)

        # 1. Jika kolom sudah datetime murni, return langsung
        if pd.api.types.is_datetime64_any_dtype(series):
            return series

        # 2. Parsing dengan handling mixed types
        # to_datetime dengan errors='coerce' biasanya cukup pintar menangani Timestamp object + String
        res = pd.to_datetime(series, errors='coerce', dayfirst=True)

        nat_count = res.isna().sum()
        total_count = len(res)
        nat_ratio = nat_count / total_count if total_count > 0 else 0

        # 3. Fallback jika banyak gagal (>30%)
        if nat_ratio > 0.3:
            print(f"   ⚠️ High NaT ({nat_ratio:.1%}) in {source_name}. Trying fallback formats...")

            # Coba konversi ke string dulu baru parse (untuk format aneh)
            series_str = series.astype(str).str.strip()

            # Coba DayFirst=False (US)
            res_us = pd.to_datetime(series_str, errors='coerce', dayfirst=False)
            if res_us.isna().sum() < nat_count:
                print(f"   -> Fixed using DayFirst=False")
                return res_us

            # Coba format eksplisit
            formats = ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y %H:%M:%S']
            for fmt in formats:
                try:
                    res_fmt = pd.to_datetime(series_str, format=fmt, errors='coerce')
                    if res_fmt.isna().sum() < nat_count:
                        print(f"   -> Fixed using format: {fmt}")
                        return res_fmt
                except: continue

        return res

    @staticmethod
    def create_historical_snowflake_id(dt_val, sequence=0):
        """
        Generates a Snowflake ID based on a historical datetime object.
        """
        if pd.isna(dt_val):
            dt_val = datetime.now()
        
        # Ensure dt_val is a datetime object
        if not isinstance(dt_val, datetime):
             dt_val = pd.to_datetime(dt_val)

        # Use a fixed epoch for historical generation (e.g., 2024-01-01)
        EPOCH = 1704067200000 # 2024-01-01
        worker_id = 1
        datacenter_id = 1
        
        # Cap sequence to 12 bits (4095)
        sequence = sequence % 4096
        
        ts = int(dt_val.timestamp() * 1000) - EPOCH
        if ts < 0: ts = 0 # Handle dates before epoch
        
        sid = (ts << 22) | (datacenter_id << 17) | (worker_id << 12) | sequence
        return f"WO-{sid}"

# Legacy support for existing imports (can be removed later if all refs are updated)
create_historical_snowflake_id = ServiceUtils.create_historical_snowflake_id
format_plat_nomor = ServiceUtils.format_plat_nomor
randomize_work_hours = ServiceUtils.randomize_work_hours