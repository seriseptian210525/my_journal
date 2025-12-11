# ETL Pipeline - Perbaikan & Konfigurasi

## ✅ Perbaikan Yang Sudah Dilakukan:

### 1. **Import Fixes**
- **main.py**: Semua import diubah jadi relative import (`.data_loader`, `.utils`, `.transformers`, `.config`)
- **utils.py**: Import snowflake library diganti dari `pysnowflake` ke `pysnowflake_id` (library yang ada)
- **transformers.py**: Sudah menggunakan relative import dengan benar

### 2. **Function Signature Fixes**
- **data_loader.py**: 
  - `load_from_google_sheet()` sekarang support 2 mode:
    - Mode 1: `load_from_google_sheet(sheet_id="xxx", worksheet_name="yyy")`
    - Mode 2: `load_from_google_sheet(client=client, sheet_name="xxx", worksheet_name="yyy")`
  - Ini untuk kompatibilitas dengan kode lama dan baru

### 3. **Dependencies Updated**
- **requirements.txt**: Ditambahkan `pysnowflake-id` untuk ID generation

### 4. **Package Structure**
- **src/__init__.py**: Dibuat agar folder `src` jadi proper Python package

### 5. **Snowflake ID Generator**
- **utils.py**: Diupdate untuk menggunakan `SnowflakeGenerator` dari `pysnowflake_id`

---

## ⚠️ Catatan Penting untuk Konfigurasi:

### 1. **Environment Variables (.env)**
Pastikan file `.env` sudah terisi dengan benar:
```env
SPREADSHEET_ID=your_actual_spreadsheet_id_here
WORKSHEET_NAME=Sheet1
```

### 2. **Service Account Permission**
File `seri-automation-etl.json` harus:
- Memiliki akses ke semua Google Sheets yang akan diakses
- Share sheets ke email service account

### 3. **Nama Sheets dan Worksheets**
Di `main.py`, sesuaikan nama-nama ini dengan data real kamu:
- `"List All Bike SCM"` → Sheet name untuk master asset
- `"ALL BIKE NEW"` → Worksheet name di dalam sheet tersebut
- `"DATA KARYAWAN"` → Sheet name untuk data mekanik
- `"mekanik list"` → Worksheet name

### 4. **Data Sources (S1-S8)**
Sekarang baru ada contoh untuk 2 sumber:
- Kembangan (dari CSV - path perlu disesuaikan)
- Depok (dari Google Sheets - nama perlu disesuaikan)

**TODO**: Tambahkan 6 sumber lainnya sesuai DAG:
- S1: Form Service 2024-25
- S2: Service Unit Grab
- S3: Form Responses
- S4: List Request SPK
- S5: After Repair List
- S6, S7, S8: Cabang lainnya (Bekasi, dll)

---

## 🚀 Cara Menjalankan:

### 1. Install Dependencies
```bash
cd projects/my_etl_project
pip install -r requirements.txt
```

### 2. Setup Environment
```bash
# Copy .env.example menjadi .env
cp .env.example .env

# Edit .env dengan nilai sebenarnya
# SPREADSHEET_ID=...
```

### 3. Test Individual Function
```bash
# Test transformers
python -m unittest tests/test_transformers.py
```

### 4. Run Full Pipeline
```bash
# Dari root folder my_journal
python -m projects.my_etl_project.src.main
```

---

## 📋 Checklist Sebelum Production:

- [ ] Isi semua `.env` dengan nilai production
- [ ] Verifikasi service account punya akses ke semua sheets
- [ ] Test koneksi ke Google Sheets
- [ ] Implementasi semua data sources (S1-S8)
- [ ] Test pipeline end-to-end dengan data sample
- [ ] Setup GitHub Actions workflow (daily_etl.yml)
- [ ] Add error notification (email/Slack jika pipeline fail)

---

## 🔧 Config Yang Masih Bisa Disesuaikan:

### Di `config.py`:
- `WORKER_ID` dan `DATACENTER_ID` untuk Snowflake ID
- `SERVICE_TYPE_MAPPING` jika ada kategori baru
- `PARTS_COLUMNS_MAPPING` untuk mapping kolom parts per sumber data

### Di `transformers.py`:
- `ESTIMATED_DAILY_MILEAGE` (default 100 km/hari)
- `PLATE_SIMILARITY_THRESHOLD` (default 0.8)
- `ODO_DIFF_THRESHOLD` (default 5000 km)
