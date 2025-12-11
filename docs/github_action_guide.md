# GitHub Actions Deployment Guide

To run your ETL pipeline in GitHub Actions without generating local CSVs, follow these steps:

## 1. Configure Secrets
Go to your **GitHub Repository -> Settings -> Secrets and variables -> Actions**.
Add the following Repository Secrets (copy values from your local `.env`):

- `GOOGLE_APPLICATION_CREDENTIALS` (Content of your JSON key file)
- `SHEET_ID_OUTPUT`
- `SHEET_ID_FORM_SERVICE`
- ... (Add all other Sheet IDs from your .env)

## 2. Configure Environment Variables
You also need to set the configuration for the CSV export behavior. Since this is not sensitive data, you can set it directly in the workflow YAML or as a Repository Variable.

### Option A: Repository Variable (Recommended)
Go to **Settings -> Secrets and variables -> Actions -> Variables** tab.
- Name: `SAVE_LOCAL_CSV`
- Value: `false`

### Option B: Directly in Workflow YAML
In your `.github/workflows/pipeline.yml`, add it to the `env` section:

```yaml
name: Daily ETL Pipeline

on:
  schedule:
    - cron: '0 2 * * *' # Run at 2 AM UTC
  workflow_dispatch:

jobs:
  run-etl:
    runs-on: ubuntu-latest
    
    env:
      # Disable CSV generation for this runner
      SAVE_LOCAL_CSV: "false" 
      
      # Map Secrets to Env Vars
      SHEET_ID_OUTPUT: ${{ secrets.SHEET_ID_OUTPUT }}
      SHEET_ID_FORM_SERVICE: ${{ secrets.SHEET_ID_FORM_SERVICE }}
      # ... map other sheet IDs ...

    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
          
      - name: Install Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          
      - name: Create Credentials File
        run: |
          echo "${{ secrets.GOOGLE_APPLICATION_CREDENTIALS }}" > google_credentials.json
        env:
          GOOGLE_APPLICATION_CREDENTIALS: ${{ secrets.GOOGLE_APPLICATION_CREDENTIALS }}

      - name: Run ETL Pipeline
        run: python -m src.main
        env:
          # Point the script to the temp json file
          GOOGLE_APPLICATION_CREDENTIALS: "./google_credentials.json"
```

## Summary
By setting `SAVE_LOCAL_CSV: "false"` in the `env` block of the action, the script will skip the `to_csv` step and only perform the Google Sheet upload.
