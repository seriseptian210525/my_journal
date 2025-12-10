# Project Structure

This project follows a modular ETL architecture designed for scalability and maintainability.

## 📂 Directory Layout

```
├── .github/                   # GitHub Actions and workflows
├── docs/                      # Documentation files
├── src/                       # Source Code
│   ├── common/                # Shared utilities and configurations
│   │   ├── config.py          # Configuration constants (Sheet IDs, mappings)
│   │   ├── data_loader.py     # GSheet connection & loading logic
│   │   └── utils.py           # Shared helper functions (Date parsing, ID generation)
│   │   
│   ├── pipelines/             # Modular pipelines
│   │   └── work_orders/       # Main Work Order Processing Pipeline
│   │       ├── run.py                 # Pipeline Orchestrator (Runner)
│   │       ├── transformers.py        # Core Transformation Logic
│   │       ├── odometer_processor.py  # Specific Odometer Logic
│   │       └── complaint_cleaner.py   # NLP/Regex Complaint Cleaning
│   │
│   └── main.py                # Main Entry Point (Wrapper for work_orders pipeline)
│
├── tests/                     # Integration and Unit Tests
│   └── integration_test_etl.py
│
├── run_pipeline.py            # CLI Utility to run specific pipelines (extensible)
├── requirements.txt           # Python dependencies
└── README.md                  # Project overview
```

## 🔑 Key Modules

### 1. Entry Points
- **`src/main.py`**: The primary entry point. Runs the default Work Order pipeline.
  - Usage: `python -m src.main`
- **`run_pipeline.py`**: CLI tool for running specific pipelines (useful when multiple pipelines exist).
  - Usage: `python run_pipeline.py --pipeline work_orders`

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
