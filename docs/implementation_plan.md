# Implementation Plan: Phase 2 - Operationalization & Visualization

## 🎯 Goal
Leverage the newly restructured modular architecture to **automate** the ETL process and **complete** the Streamlit Dashboard visualization. This plan serves as the reference roadmap for the next development steps.

## 🏗️ Baseline (Current State - "Update Terbaru")
Following the recent `Project Restructuring`, the project now stands as follows:

| Component | Status | New Location / Config |
| :--- | :--- | :--- |
| **Orchestrator** | ✅ Modular | `entrypoint/run_pipeline.py` |
| **ETL Source** | ✅ Clean | `src/pipelines/work_orders/` |
| **Output** | ✅ Centralized | `output/` (CSV logs) |
| **Config** | ✅ Robust | `src/common/config.py` (Auto-load `env.yaml`) |
| **IDs** | ✅ Persistent | `order_id` (Snowflake + Sequence) |

## 🚧 Proposed Changes (Next Steps)

### 1. Automation (GitHub Actions)
**Objective**: Automate the daily ETL run using the new entry point.

- [ ] **Workflow File**: Re-create `.github/workflows/daily_etl.yml`.
- [ ] **Command**: Update to use `python entrypoint/run_pipeline.py --pipeline work_orders`.
- [ ] **Secrets**: Map `GOOGLE_APPLICATION_CREDENTIALS` (JSON) and `.env` vars in GitHub Secrets.

### 2. Dashboard Integration (Streamlit)
**Objective**: Ensure all Dashboard pages consume data from the new `output/` folder and `src` modules.

#### Remaining Pages to Update:
- **Page 1 (`1_About_Me.py`)**: Static, low priority.
- **Page 2 (`2_Fleet_Analysis.py`)**: needs local CSV connection update.
- **Page 4 (`4_ERA_Support.py`)**: needs `DataLoader` integration.
- **Page 5 (`5_Quality_Improvement.py`)**: needs defect rate calculation from `output/final_historical_data.csv`.

### 3. Usage & Documentation
**Objective**: Make the project easy to onboard.

- [ ] **README.md**: Create a root README explaining the architecture.
- [ ] **Requirements**: Verify `requirements.txt` is minimal and sufficient (remove dev tools if any).

## 🧪 Verification Plan

### Automated Tests
- Run `python entrypoint/run_pipeline.py` (Passed ✅)
- Confirm `output/final_historical_data.csv` is generated (Passed ✅)

### Dashboard Verification
- Run `streamlit run app.py` and navigate to:
    - **Home**: Check layout.
    - **Page 3**: Check "After Sales Analysis" loads data from `output/`.
    - **Page 4/5**: Verify charts render correctly with new data path.
