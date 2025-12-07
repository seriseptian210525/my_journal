# Final Project Structure & Deployment Guide

Dokumen ini menjelaskan struktur akhir project `my_journal` yang telah di-refactor menjadi modular, aman, dan siap deploy.

## 1. Modular Architecture Overview

Codebase kini terbagi menjadi dua domain utama yang terpisah namun terintegrasi:

### A. Frontend (Streamlit)
*   **Lokasi**: Root folder (`/`)
*   **Fungsi**: Visualisasi data.
*   **Dependencies**: `requirements.txt` (termasuk `streamlit`, `gspread`).
*   **Logic**: Membaca data dari Google Sheets (Production) atau CSV Local (Testing) menggunakan modules dari ETL.

### B. Backend (ETL Pipelines)
*   **Lokasi**: `projects/my_etl_project/`
*   **Fungsi**: Pengolahan data berat, Cleaning, Normalisasi.
*   **Dependencies**: `projects/my_etl_project/requirements.txt` (Hanya library data: `pandas`, `gspread`, `rapidfuzz`).
*   **Structure**:
    *   `src/common/`: Shared tools (Config, Loader, Utils).
    *   `src/pipelines/`: Logic spesifik per pipeline (`work_orders`, `service_items`, dll).
    *   `run_pipeline.py`: Satu pintu masuk (Orchestrator).

## 2. Local Testing Guide (Hybrid Mode)

Mode ini digunakan saat development di komputer Anda.

**1. Setup Environment**
Pastikan `.env` memiliki `SAVE_LOCAL_CSV=true`.

**2. Jalankan ETL Pipeline**
Pipeline akan memproses data dan menyimpannya ke folder `output/`.
```bash
cd projects/my_etl_project
python run_pipeline.py --pipeline work_orders
```
*   **Output**: `output/final_historical_data.csv`
*   **Log**: `tests/latest_validation_summary.txt`

**3. Jalankan Streamlit**
Aplikasi akan mendeteksi file CSV lokal jika Anda memilih "Local CSV" di sidebar.
```bash
# Dari root folder my_journal
streamlit run app.py
```

## 3. Production Deployment Guide

### A. GitHub Actions (Backend)
Pipeline berjalan otomatis tanpa UI.
1.  **Secrets**: Set Google Credentials & Sheet IDs di GitHub Secrets.
2.  **Config**: Tambahkan Variable `SAVE_LOCAL_CSV = false`.
3.  **Command**:
    ```yaml
    run: python run_pipeline.py --pipeline work_orders
    ```
    Script **TIDAK** akan menghasilkan CSV (hemat storage runner) dan langsung upload ke Google Sheets.

### B. Streamlit Cloud (Frontend)
1.  **Repository**: Connect ke repo GitHub Anda.
2.  **Secrets**: Copy isi `.env` ke Streamlit Secrets.
3.  **App Logic**: Aplikasi akan menggunakan mode "Google Sheets (Live)" untuk menampilkan data yang di-upload oleh GitHub Actions.

## 4. Maintenance
*   **Menambah Pipeline Baru**:
    1. Buat folder `src/pipelines/new_pipeline/`.
    2. Tambahkan logic di `run_pipeline.py`.
*   **Membersihkan Junk**: Cek folder `tests/` secara berkala (hanya berisi test valid).

---
**Status**: ✅ Verified Modular & Ready.
