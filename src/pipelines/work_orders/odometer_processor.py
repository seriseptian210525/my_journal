import pandas as pd
import numpy as np
import random
from src.common.config import PipelineConfig


class OdometerProcessor:
    """
    LOGIC 1: Membersihkan Odometer pada data ELSA.
    [UPDATED] Smart Monotonic Repair + Integer Rounding:
    - Enforce Monotonicity (Naik).
    - Reality Check (Self-Correction).
    - Rounding: Membulatkan hasil estimasi menjadi bilangan bulat.
    """
    def __init__(self, config: PipelineConfig):
        self.config = config

    def _repair_group(self, g: pd.DataFrame):
        """
        Helper function untuk apply per grup kendaraan.
        """
        g = g.sort_values("created_at").copy()
        g[self.config.COL_ODO_CLEAN] = g["odometer_stage1"].copy()
        
        col_idx_clean = g.columns.get_loc(self.config.COL_ODO_CLEAN)
        col_idx_created_at = g.columns.get_loc("created_at")
        is_anomaly_idx = g.columns.get_loc("is_anomaly_rule")
        
        # Ambil delivery date
        delivery_date = pd.NaT
        if self.config.COL_DELIVERY_DATE in g.columns:
            valid_dates = g[self.config.COL_DELIVERY_DATE].dropna()
            if not valid_dates.empty:
                delivery_date = valid_dates.iloc[0]

        for i in range(len(g)):
            curr_date = g.iat[i, col_idx_created_at]
            
            # --- LOGIC BARIS PERTAMA (i=0) ---
            if i == 0:
                curr_odo = g.iat[i, col_idx_clean]
                if pd.notna(curr_odo) and curr_odo > 0: 
                    continue
                
                if pd.notna(delivery_date):
                    delta_days = (curr_date - delivery_date).total_seconds() / 86400.0
                    if delta_days > 0:
                        est = self.config.ASSUMED_KM_PER_DAY * delta_days
                        max_est = self.config.MAX_KM_PER_DAY * delta_days
                        # Rounding to Integer
                        est = float(np.round(np.clip(est, 0, max_est)))
                        g.iat[i, col_idx_clean] = est
                continue
            
            # --- LOGIC BARIS SELANJUTNYA (i>0) ---
            curr_odo_raw = g.iat[i, col_idx_clean]
            prev_odo_clean = g.iat[i-1, col_idx_clean]  # Clean prev
            prev_date = g.iat[i-1, col_idx_created_at]

            if pd.isna(prev_odo_clean) or pd.isna(prev_date) or pd.isna(curr_date):
                continue

            delta_days = (curr_date - prev_date).total_seconds() / 86400.0
            if delta_days <= 0 or pd.isna(delta_days): 
                delta_days = 0.01

            # --- [SMART LOGIC] REALITY CHECK ---
            should_trust_raw = False
            if pd.notna(curr_odo_raw) and pd.notna(delivery_date):
                total_age_days = (curr_date - delivery_date).total_seconds() / 86400.0
                if total_age_days > 0:
                    benchmark_odo = total_age_days * self.config.ASSUMED_KM_PER_DAY
                    diff_raw_benchmark = abs(curr_odo_raw - benchmark_odo)
                    diff_clean_benchmark = abs(prev_odo_clean - benchmark_odo)
                    
                    if diff_raw_benchmark < diff_clean_benchmark:
                        min_wajar = total_age_days * self.config.MIN_KM_PER_DAY
                        if curr_odo_raw > min_wajar:
                            should_trust_raw = True

            # --- DETEKSI PERBAIKAN ---
            flagged_anomaly = g.iloc[i, is_anomaly_idx]
            
            monotonic_violation = False
            if pd.notna(curr_odo_raw) and curr_odo_raw < prev_odo_clean:
                monotonic_violation = True

            is_missing = pd.isna(curr_odo_raw) or (curr_odo_raw == 0)
            
            is_spike = False
            if pd.notna(curr_odo_raw) and not is_missing:
                speed = (curr_odo_raw - prev_odo_clean) / delta_days
                if speed > self.config.MAX_KM_PER_DAY:
                    is_spike = True

            # --- DECISION MAKING ---
            if should_trust_raw and (monotonic_violation or is_spike):
                # Trust Raw, Reset Chain.
                g.iat[i, col_idx_clean] = float(np.round(curr_odo_raw))
            
            elif flagged_anomaly or monotonic_violation or is_missing or is_spike:
                # REPAIR MODE
                base_increase = self.config.ASSUMED_KM_PER_DAY * delta_days
                
                # Random Variance
                variance = self.config.RANDOM_VARIANCE
                random_factor = random.uniform(1.0 - variance, 1.0 + variance)
                final_increase = base_increase * random_factor
                
                # Clamping Increase
                min_increase = self.config.MIN_KM_PER_DAY * delta_days
                max_increase = self.config.MAX_KM_PER_DAY * delta_days
                final_increase = np.clip(final_increase, min_increase, max_increase)

                est_odo = prev_odo_clean + final_increase
                
                # Rounding to Integer
                est_odo = float(np.round(est_odo))
                
                g.iat[i, col_idx_clean] = est_odo
            
            else:
                # Data Valid
                pass

        return g

    def process_pipeline(self, df_raw: pd.DataFrame, df_asset_list: pd.DataFrame = None) -> pd.DataFrame:
        print("Starting Odometer Cleaning Pipeline (ELSA)...")
        df = df_raw.copy()
        df.columns = df.columns.str.strip()
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
        
        # MERGE DELIVERY DATE
        if df_asset_list is not None:
            print("   -> Merging Delivery Dates from Asset List...")
            vin_elsa = "vehicle_vin"
            vin_asset = self.config.COL_ASSET_VIN
            col_delivery = self.config.COL_ASSET_DELIVERY
            
            if vin_asset in df_asset_list.columns and col_delivery in df_asset_list.columns:
                df_asset_clean = df_asset_list[[vin_asset, col_delivery]].copy()
                df_asset_clean[vin_asset] = df_asset_clean[vin_asset].astype(str).str.strip()
                df_asset_clean[col_delivery] = pd.to_datetime(df_asset_clean[col_delivery], errors='coerce')
                df_asset_clean = df_asset_clean.dropna(subset=[col_delivery]).drop_duplicates(subset=[vin_asset])
                
                df[vin_elsa] = df[vin_elsa].astype(str).str.strip()
                df = pd.merge(df, df_asset_clean, left_on=vin_elsa, right_on=vin_asset, how="left")
                df.rename(columns={col_delivery: self.config.COL_DELIVERY_DATE}, inplace=True)
                if vin_elsa != vin_asset:
                    df.drop(columns=[vin_asset], inplace=True, errors='ignore')
                print(f"      Matched Delivery Dates for {df[self.config.COL_DELIVERY_DATE].notna().sum()} rows.")

        # Pre-cleaning
        if "odometer" in df.columns:
            df["odometer_raw"] = pd.to_numeric(df["odometer"].astype(str), errors="coerce")
        else:
            df["odometer_raw"] = np.nan

        try:
            MIN_INT64 = np.iinfo("int64").min
            df.loc[df["odometer_raw"] == MIN_INT64, "odometer_raw"] = np.nan
        except: 
            pass
        
        df = df.sort_values(["vehicle_vin", "created_at"])
        df["odometer_stage1"] = df["odometer_raw"]
        df.loc[df["odometer_stage1"] < 0, "odometer_stage1"] = np.nan

        # STEP 1 & 2: Delta & Flagging
        df["delta_days"] = df.groupby("vehicle_vin")["created_at"].diff().dt.total_seconds().div(86400)
        df["delta_odo"] = df.groupby("vehicle_vin")["odometer_stage1"].diff()
        df["km_per_day"] = df["delta_odo"] / df["delta_days"]

        df["is_anomaly_rule"] = False
        df.loc[df["delta_odo"] < 0, "is_anomaly_rule"] = True
        df.loc[df["km_per_day"] > self.config.MAX_KM_PER_DAY, "is_anomaly_rule"] = True

        # STEP 3: Impute Flag
        df["needs_impute"] = False
        first_idx = df.groupby("vehicle_vin").head(1).index
        zero_mid = (df["odometer_stage1"] == 0) & (~df.index.isin(first_idx))
        null_mask = df["odometer_stage1"].isna()
        anomaly_mask = df["is_anomaly_rule"]
        df.loc[zero_mid | null_mask | anomaly_mask, "needs_impute"] = True

        # STEP 4: Smart Repair
        print("   -> Running Smart Monotonic Repair (with Rounding)...")
        df_cleaned = df.groupby("vehicle_vin", group_keys=False).apply(self._repair_group)
        
        print("Odometer Cleaning Pipeline Completed.")
        return df_cleaned
