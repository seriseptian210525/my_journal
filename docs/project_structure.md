# Project Structure

This project follows a modular ETL architecture designed for scalability and maintainability.

## 📂 Directory Layout

```
## 📂 Directory Layout

```
├── .github/                   # GitHub Actions and workflows
├── docs/                      # Documentation files (.md, .txt)
├── entrypoint/                # Main Orchestrator Entry Points
│   └── run_pipeline.py        # Centralized CLI Runner
│
├── notebook/                  # Jupyter Notebooks for analysis
│   ├── ADVANCED_HISTORICAL_SERVICE.ipynb
│   └── [ELSA]_Kamus_Keluhan.ipynb
│
├── output/                    # Pipeline Outputs (CSVs)
│   ├── final_historical_data.csv
│   └── cleaning_tech_log.csv
│
├── src/                       # Source Code
│   ├── common/                # Shared utilities and configurations
│   └── pipelines/             # Modular pipelines
│       └── work_orders/       # Main Work Order Processing Pipeline
│
├── app.py                     # Streamlit Dashboard Entry Point (Root)
├── requirements.txt           # Python dependencies
└── README.md                  # Project overview
```

## 🔑 Key Modules

### 1. Entry Points
- **`entrypoint/run_pipeline.py`**: The main orchestrator for ETL pipelines.
  - Usage: `python entrypoint/run_pipeline.py --pipeline work_orders`
- **`app.py`**: The entry point for the Streamlit Dashboard.
  - Usage: `streamlit run app.py`

### 2. Output
- **`output/`**: All ETL artifacts (reports, clean data, bad data logs) are saved here.

### 2. Common (`src/common/`)
- **`config.py`**: Centralized configuration. **Edit this file** to change Google Sheet IDs or column mappings.
- **`utils.py`**: Contains the critical `create_historical_snowflake_id` function (Persistent ID generation).

### 3. Pipelines (`src/pipelines/work_orders/`)
- **`transformers.py`**: Contains `ServiceDataEnricher` class which holds the core business logic (Customer Name backfill, Asset Enrichment, ID generation).
- **`odometer_processor.py`**: Specialized logic for filtering and estimating odometer readings.

## 🛠️ How to Maintain

- **Adding a new data source:**
  1. Add Sheet ID to `src/common/config.py`.
  2. Register the source in `src/pipelines/work_orders/run.py` inside `run_work_order_pipeline()`.

- **Modifying ID Logic:**
  - Logic is in `src/pipelines/work_orders/transformers.py` -> `generate_snowflake_ids`.
  - Helper function in `src/common/utils.py`.

- **Fixing Data Quality Rules:**
  - Edit `src/pipelines/work_orders/transformers.py` for general rules.
  - Edit `src/pipelines/work_orders/complaint_cleaner.py` for complaint text cleaning.
