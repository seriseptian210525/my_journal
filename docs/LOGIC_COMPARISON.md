# Logic Comparison: Notebook vs ETL Modules

Setelah review notebook `HISTORICAL_SERVICE.ipynb`, berikut adalah perbedaan logic yang perlu disesuaikan:

## 1. ❌ `round_odo()` Logic - BERBEDA TOTAL!

### Notebook Version (CORRECT):
```python
def round_odo(row, asset_list_df):
    # Logic kompleks berdasarkan Umur Kendaraan:
    # - Umur <= 12: Pembulatan 5 digit (10.000+)
    # - Umur == 24: Pembulatan 6 digit (100.000+)
    # - Menggunakan logika digit ke-6/ke-7 untuk pembulatan
```

### Current Module (`transformers.py`): ❌ SALAH
```python
def fill_zero_odometer_logic(df):
    # Hanya estimasi simpel dengan ESTIMATED_DAILY_MILEAGE = 100
    # TIDAK ADA logika pembulatan berdasarkan Umur Kendaraan
```

**ACTION REQUIRED**: `round_odo()` harus dipindahkan dari notebook ke `transformers.py` dan disesuaikan strukturnya.

---

## 2. ✅ `format_plat_nomor()` - SUDAH SAMA

### Notebook Version:
```python
plat_nomor_cleaned[:8]  # Maksimal 8 karakter
match = re.match(r'^([A-Z])(\d{1,4})([A-Z]{0,3})$', plat_nomor_cleaned)
```

### Current Module (`utils.py`): ✅ OK
Sudah identik dengan notebook.

---

## 3. ❓ Missing Logic dari Notebook

### A. **Timestamp Generation** - Tidak ada di notebook asli
Logic `random_time_work_hours()` di `utils.py` dan `process_cabang_data()` di `transformers.py` sepertinya logic tambahan yang tidak ada di notebook.

**NOTE**: Ini mungkin logic baru yang user mau tambahkan untuk handling data cabang.

### B. **VIN/Engine Filling Logic**

#### Dari Notebook:
Sepertinya tidak ada explicit function `fill_missing_vin_engine_by_history()` atau `fill_missing_vin_engine_by_similarity()` di notebook yang saya lihat.

**ACTION REQUIRED**: Konfirmasi dengan user apakah logic ini:
1. Sudah ada tapi dengan nama berbeda di notebook?
2. Logic baru yang dikembangkan terpisah untuk pipeline ini?

---

## 4. Output Columns - Perlu Verifikasi

### Dari Notebook yang terlihat:
Asset list memiliki kolom:
- `VIN`
- `Engine No`
- `Model`
- `Plat Nomor`
- `Color`
- `Umur Kendaraan` ⚠️ (Penting untuk round_odo!)

### Current Module assumes:
- Kolom sama tapi tidak menggunakan `Umur Kendaraan` untuk rounding!

---

## 5. Snowflake ID Generation

Tidak terlihat di snippet notebook yang direview. Kemungkinan:
1. Commented out (`# import pysnowflake as snowflake`)
2. Logic baru untuk pipeline

---

## 🎯 PRIORITY FIXES:

### HIGH Priority:
1. **Replace `fill_zero_odometer_logic()` dengan `round_odo()`** dari notebook
   - Perlu akses ke `asset_list_df` dengan kolom `Umur Kendaraan`
   - Logic pembulatan 5 digit vs 6 digit

### MEDIUM Priority:
2. **Verify VIN/Engine filling logic** - apakah ada di notebook atau ini logic baru?
3. **Verify column mappings** - pastikan semua kolom yang dibutuhkan ada

### LOW Priority:
4. **Parts combined columns** - belum terlihat di notebook snippet
5. **Service type mapping** - ada di config, perlu verify dengan data asli

---

## 📝 Questions for User:

1. Apakah ada function untuk fill missing VIN/Engine di notebook asli?
2. Apakah logic `round_odo()` dari notebook yang kompleks itu masih valid dan ingin dipakai?
3. Apakah ada bagian lain dari notebook yang krusial tapi belum dipindahkan ke modules?
