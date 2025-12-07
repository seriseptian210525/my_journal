# Architecture Proposal: Modular ETL & Streamlit Integration

Saat ini logic Anda terpusat di `src/main.py`. Untuk mengakomodasi pipeline baru (`service_items`, `work_order_activity`) dan integrasi dengan Streamlit, saya sarankan **Refactoring Modular**.

## 1. Proposed Directory Structure

Kita akan memecah `src` menjadi `common` (bisa dipakai siapa saja) dan `pipelines` (logic spesifik).

```
projects/my_etl_project/
├── .env                      # Pusat Config & Secrets
├── run_pipeline.py           # (NEW) Orchestrator utama
├── src/
│   ├── __init__.py
│   │
│   ├── common/               # [SHARED] Logic yang dipakai semua pipeline
│   │   ├── __init__.py
│   │   ├── config.py         # Config terpusat (Sheet IDs, dll)
│   │   ├── loader.py         # Google Sheets / CSV Loader generic
│   │   └── utils.py          # Helper function (date parse, text handling)
│   │
│   └── pipelines/            # [SPECIFIC] Logic per domain
│       ├── __init__.py
│       │
│       ├── work_orders/      # Pipeline data utama (Current main.py)
│       │   ├── __init__.py
│       │   ├── run.py        # Logic pipeline utama
│       │   ├── transform.py  # ServiceDataEnricher, OdometerProcessor
│       │   └── cleaning.py   # ComplaintCleaner
│       │
│       ├── service_items/    # (Next) Pipeline detail item
│       │   ├── __init__.py
│       │   └── run.py
│       │
│       └── wo_activity/      # (Next) Pipeline aktivitas
│           ├── __init__.py
│           └── run.py
```

## 2. Why This Structure?
1.  **Reusability**: `src.common.loader` bisa dipanggil oleh `service_items` tanpa copy-paste code koneksi GSheets.
2.  **Scalability**: Setiap pipeline punya folder sendiri. Debugging `work_orders` tidak akan mengganggu `wo_activity`.
3.  **Isolation**: Config pipeline work orders tidak tercampur dengan logic item.

## 3. Integration with Streamlit (`my_journal/app.py`)

Bagaimana menghubungkannya dengan Dashboard Streamlit di folder parent?

### A. Data Integration (Recommended)
Streamlit sebaiknya **HANYA membaca Output**, bukan memanggil Internal Function ETL.
*   **ETL (Back-end)**: Lari otomatis (cron/manual), output ke -> `Google Sheets` atau `CSV` di folder `data/`.
*   **Streamlit (Front-end)**: Terhubung ke `Google Sheets` tersebut atau membaca `projects/my_etl_project/output/*.csv`.

### B. Shared Modules (If necessary)
Jika Streamlit butuh akses ke function `utils.py` atau `config.py` milik ETL:
Anda bisa install project ETL sebagai local package.
Di `projects/my_etl_project/setup.py`:
```python
from setuptools import setup, find_packages
setup(name="my_etl", version="0.1", packages=find_packages())
```
Lalu install di environment: `pip install -e projects/my_etl_project`.
Maka di Streamlit bisa import:
```python
from src.common.config import SHEET_ID_OUTPUT
```

## 4. Next Action Plan
1.  **Refactor**: Pindahkan code sekarang (`data_loader.py`, `utils.py`) ke `src/common`.
2.  **Move**: Pindahkan logic `main.py` ke `src/pipelines/work_orders/run.py`.
3.  **Develop**: Mulai buat `src/pipelines/service_items` dengan mengimport `src.common.loader`.
