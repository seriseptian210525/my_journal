# Project Structure

This project follows a modular ETL architecture designed for scalability and maintainability.

## 📂 Directory Layout

```
my_journal/
├── .agent/                    # AI Agent rules and workflows
│   ├── rules/                 # Coding standards and guidelines
│   └── workflows/             # Automated agent task definitions
├── .github/                   # GitHub Actions and workflows
│   └── workflows/             # CI/CD pipeline definitions
├── docs/                      # Documentation files (.md, .txt)
├── entrypoint/                # Main Orchestrator Entry Points
│   └── run_pipeline.py        # Centralized CLI Runner
├── notebook/                  # Jupyter Notebooks for analysis
├── output/                    # Pipeline Outputs (CSVs)
├── pages/                     # Streamlit Dashboard Pages (Multi-page)
│   ├── 1_🏠_Home.py
│   ├── 2_👤_About_Me.py
│   └── ...                    # Other analysis pages
├── src/                       # Source Code
│   ├── common/                # Shared utilities and configurations
│   └── pipelines/             # Modular pipelines
│       ├── work_orders/       # Main Work Order Processing Pipeline
│       │   ├── transformers.py
│       │   ├── complaint_cleaner.py
│       │   └── odometer_processor.py
│       ├── service_items/     # Service Items details pipeline
│       └── gel_sync/          # External data synchronization
├── tests/                     # Unit and Integration Tests
├── app.py                     # Streamlit Dashboard Main Entry
├── requirements.txt           # Python dependencies
└── README.md                  # Project overview
```

## 🔑 Key Modules

### 1. Entry Points
- **`entrypoint/run_pipeline.py`**: The main orchestrator for ETL pipelines.
  - Usage: `python entrypoint/run_pipeline.py --pipeline work_orders`
- **`app.py`**: The entry point for the Streamlit Dashboard.
  - Usage: `streamlit run app.py`

### 2. Common (`src/common/`)
- **`config.py`**: Centralized configuration loader for YAML and Environment variables.
- **`logger.py`**: Centralized logging configuration for console and files.
- **`utils.py`**: Contains shared utilities like Snowflake ID generation.

### 3. Pipelines (`src/pipelines/work_orders/`)
- **`transformers.py`**: Core business logic for data enrichment, standardization, and merging.
- **`odometer_processor.py`**: Advanced logic for odometer anomaly detection and imputation.
- **`complaint_cleaner.py`**: Fuzzy matching logic for normalizing vehicle complaints.

### 4. Agent Rules (`.agent/rules/`)
- **`pythondatapipeline.md`**: Standards and guidance for Python data pipelines and Streamlit development.


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
