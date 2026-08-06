# GitHub Actions Setup Guide

Panduan lengkap untuk menjalankan ETL pipeline secara otomatis menggunakan GitHub Actions dengan cron schedule dan konfigurasi secrets yang aman.

---

## 📋 Daftar Isi

1. [Cron Schedule Setup](#1-cron-schedule-setup)
2. [Migrasi Secrets dari .env ke GitHub](#2-migrasi-secrets-dari-env-ke-github)
3. [Workflow Configuration](#3-workflow-configuration)
4. [Troubleshooting](#4-troubleshooting)

---

## 1. Cron Schedule Setup

### Apa itu Cron?

Cron adalah sistem penjadwalan yang memungkinkan workflow berjalan otomatis pada waktu tertentu.

### Format Cron Syntax

```
┌───────────── menit (0 - 59)
│ ┌───────────── jam (0 - 23)
│ │ ┌───────────── hari dalam bulan (1 - 31)
│ │ │ ┌───────────── bulan (1 - 12)
│ │ │ │ ┌───────────── hari dalam minggu (0 - 6, Minggu = 0)
│ │ │ │ │
* * * * *
```

### Contoh Jadwal Umum

| Schedule | Cron Expression | Keterangan |
|----------|----------------|------------|
| Setiap hari jam 00:00 UTC | `0 0 * * *` | Jam 07:00 WIB |
| Setiap hari jam 02:00 UTC | `0 2 * * *` | Jam 09:00 WIB |
| Setiap Senin jam 08:00 UTC | `0 8 * * 1` | Jam 15:00 WIB |
| Setiap 6 jam | `0 */6 * * *` | |
| Setiap hari kerja jam 07:00 UTC | `0 7 * * 1-5` | Jam 14:00 WIB |

> [!IMPORTANT]
> **Zona Waktu**: GitHub Actions menggunakan **UTC**. 
> Untuk WIB (UTC+7), kurangi 7 jam dari jadwal yang diinginkan.
> Contoh: Ingin jalan jam 14:00 WIB → set cron ke jam 07:00 UTC

---

## 2. Migrasi Secrets dari .env ke GitHub

### Langkah 1: Buka Repository Settings

1. Buka repository GitHub Anda
2. Klik tab **Settings**
3. Di sidebar kiri, klik **Secrets and variables** → **Actions**

### Langkah 2: Tambahkan Repository Secrets

Klik **"New repository secret"** untuk setiap secret berikut:

#### Google Credentials (Service Account JSON)

| Secret Name | Value |
|-------------|-------|
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | Isi seluruh konten file `credentials/seri-automation-etl.json` |

> [!WARNING]
> Jangan upload file JSON langsung! Copy-paste **isi lengkap** file JSON sebagai value secret.

#### Sheet IDs - Sources

| Secret Name | Value dari .env |
|-------------|-----------------|
| `SHEET_ID_FORM_SERVICE` | `1uyHApnwb7zsFt07gkQnvsc1H5pjz9MKu5aB5M63uEkw` |
| `SHEET_ID_SERVICE_GRAB` | `11awD-EhAEuZleRkW7b75fdItEhX3-SFM--ThDvXT3gc` |
| `SHEET_ID_FORM_RESPONSES` | `1uyHApnwb7zsFt07gkQnvsc1H5pjz9MKu5aB5M63uEkw` |
| `SHEET_ID_REQUEST_SPK` | `1peeX57zocYks_hMaRWZ8QoMsa-ZTvHI_U-R99wSYkQE` |
| `SHEET_ID_AFTER_REPAIR` | `1dw3joYxdsAz5oyoVDd-vUv_bKZfKJDd8_nXOPoDrD9w` |
| `SHEET_ID_CABANG_KEMBANGAN` | `1dw3joYxdsAz5oyoVDd-vUv_bKZfKJDd8_nXOPoDrD9w` |
| `SHEET_ID_CABANG_DEPOK` | `1dw3joYxdsAz5oyoVDd-vUv_bKZfKJDd8_nXOPoDrD9w` |
| `SHEET_ID_CABANG_BEKASI` | `1dw3joYxdsAz5oyoVDd-vUv_bKZfKJDd8_nXOPoDrD9w` |

#### Sheet IDs - Reference Data

| Secret Name | Value dari .env |
|-------------|-----------------|
| `SHEET_ID_ASSET_LIST` | `1lHkQ9D35xVdRjpZB09SV89pSO_TKb8iEc9lehw6-LCo` |
| `SHEET_ID_MEKANIK` | `1WRCUIeDXaqfkpRCdYh2pc5W2P7ry3uT3-5uXcHFZR4w` |
| `SHEET_KAMUS_KELUHAN` | `17xIg-V-lQpPLTp8vpHVlaJOoUb1YnHZm6xMErme4SzM` |

#### Sheet IDs - Output

| Secret Name | Value dari .env |
|-------------|-----------------|
| `SHEET_ID_OUTPUT` | `1DiCivMEoFNDQxlaGIb66VdsVN9jsE-qkpQF2VJ28Xok` |
| `SHEET_ID_SERVICE_ITEMS` | `1QAyBGFQCjTsSSdRzYCn8mNUQy-Vp_X8GTr5hcYofg4M` |
| `SHEET_ID_MAPPINGS` | `1EH8grZAABi2wJlYQg8Q46hd1NLE5nlY2jHTm6reX_1g` |

### Langkah 3: Tambahkan Repository Variables (Non-Sensitive)

Buka tab **Variables** (bukan Secrets), lalu tambahkan:

| Variable Name | Value |
|--------------|-------|
| `SAVE_LOCAL_CSV` | `false` |
| `STRICT_COMPLAINT_CLEANING` | `false` |

> [!TIP]
> **Variables vs Secrets**: Gunakan Variables untuk nilai yang tidak sensitif dan bisa terlihat di logs. Gunakan Secrets untuk nilai rahasia seperti API keys dan Sheet IDs.

---

## 3. Workflow Configuration

### File: `.github/workflows/daily_etl.yml`

Workflow ini sekarang mendukung multi-job untuk efisiensi dan pemicu manual dengan parameter:

```yaml
name: Daily ETL Pipeline

on:
  # Trigger manual dengan opsi parameter
  workflow_dispatch:
    inputs:
      pipeline:
        description: 'Pipeline to run'
        required: true
        default: 'all'
        type: choice
        options: [all, work_orders, service_items, gel_sync]
      mode:
        description: 'incremental = append only, full = replace'
        required: true
        default: 'incremental'
        type: choice
        options: [incremental, full]

  # Jadwal otomatis (UTC)
  schedule:
    - cron: '0 17 * * *' # Work Orders (00:00 WIB)
    - cron: '0 18 * * *' # Service Items (01:00 WIB)
    - cron: '0 4 * * 5'  # GEL Sync (Jumat 11:00 WIB)

jobs:
  work-orders:
    # Berjalan sesuai jadwal 17:00 UTC atau manual 'all'/'work_orders'
    if: github.event_name == 'schedule' && contains(github.event.schedule, '17') || ...
    steps:
      # ... setup python & install deps ...
      - name: Run Work Orders Pipeline
        run: python -m src.pipelines.work_orders.run

  service-items:
    # Berjalan sesuai jadwal 18:00 UTC atau manual 'all'/'service_items'
    steps:
      - name: Run Service Items Pipeline
        run: python -m src.pipelines.service_items.run

  gel-sync:
    # Berjalan sesuai jadwal Jumat atau manual 'all'/'gel_sync'
    steps:
      - name: Run GEL Sync to Google Sheets
        run: python -m entrypoint.sync_gel_to_sheets
```

### Fitur Baru dalam Workflow

1.  **Job Separation**: Setiap pipeline (`work-orders`, `service_items`, `gel-sync`) dipisahkan menjadi job mandiri. Jika salah satu gagal, job lainnya tetap bisa berjalan atau ditinjau secara terpisah.
2.  **Manual Input**: Anda bisa memilih mode `full` saat menjalankan manual jika ingin membersihkan seluruh data di Google Sheets dan mengisinya kembali dari awal.
3.  **Selective Execution**: Melalui pemicu manual, Anda bisa memilih hanya menjalankan satu pipeline spesifik (misal: hanya `gel_sync`) tanpa harus menjalankan semuanya.

### Penjelasan Steps

| Step | Fungsi |
|------|--------|
| **Checkout** | Clone repository ke runner |
| **Set up Python** | Install Python 3.11 dengan pip caching |
| **Install Dependencies** | Install semua packages dari requirements.txt |
| **Create Credentials** | Buat file JSON credentials dari secret |
| **Run ETL** | Jalankan pipeline |
| **Cleanup** | Hapus credentials file (keamanan) |

---

## 4. Troubleshooting

### Error: "Credentials file not found"

**Penyebab**: Secret `GOOGLE_APPLICATION_CREDENTIALS_JSON` belum diset atau isinya tidak valid.

**Solusi**:
1. Pastikan sudah menambahkan secret dengan nama yang tepat
2. Pastikan isi file JSON di-copy lengkap (termasuk `{` dan `}`)

### Error: "Permission denied" pada Google Sheets

**Penyebab**: Service account belum di-share ke Google Sheets.

**Solusi**:
1. Buka setiap Google Sheets
2. Klik **Share**
3. Tambahkan email service account (ada di field `client_email` dalam JSON)
4. Berikan akses **Editor**

### Workflow tidak jalan sesuai jadwal

**Penyebab**: 
- Cron schedule dalam UTC, bukan WIB
- GitHub Actions mungkin delay hingga 15 menit

**Solusi**:
- Verifikasi konversi zona waktu
- Gunakan `workflow_dispatch` untuk test manual

### Melihat Logs

1. Buka tab **Actions** di repository
2. Klik workflow run yang ingin dilihat
3. Expand setiap step untuk melihat detail output

---

## 📝 Checklist Migrasi

Gunakan checklist ini untuk memastikan semua konfigurasi sudah benar:

- [ ] Semua Sheet IDs sudah ditambahkan sebagai Secrets
- [ ] `GOOGLE_APPLICATION_CREDENTIALS_JSON` sudah berisi isi lengkap file JSON
- [ ] Variables `SAVE_LOCAL_CSV` dan `STRICT_COMPLAINT_CLEANING` sudah ditambahkan
- [ ] Service account sudah di-share ke semua Google Sheets
- [ ] File `.github/workflows/daily_etl.yml` sudah di-update
- [ ] Test workflow dengan "Run workflow" manual
- [ ] Verifikasi data ter-update di Google Sheets output

---

> [!NOTE]
> Setelah semua secrets dikonfigurasi, file `.env` tetap diperlukan untuk **development lokal**. 
> GitHub Actions akan menggunakan secrets, sementara development lokal menggunakan `.env`.
