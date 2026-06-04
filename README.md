# Excel Query Bot (Streamlit)

A local Streamlit app for searching an Excel database of unclaimed property records.

## Features

- Works locally on Windows.
- Search names pasted into a textbox (one per line).
- Select an Excel database file (`.xlsx` or `.xls`) in the app; no hardcoded database path is required.
- Upload a CSV or Excel search list (first column is used).
- Returns exact, partial, and fuzzy matches.
- Normalizes common business suffixes: `LLC`, `INC`, `CO`, `CORP`, `CORPORATION`, `LP`, `LLP`.
- Provides confidence score from 0–100.
- Displays results with:
  - Search Name
  - Matched Name
  - Jurisdiction
  - Amount
  - Date
  - Match Type
  - Confidence Score
- Download results as an Excel file.

## Database columns required

Your database file must include these columns:

- `Jurisdiction`
- `Name`
- `Amount`
- `Date`

## Setup (Windows)

1. Open **PowerShell** in this project folder.
2. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Install dependencies:

```powershell
pip install -r requirements.txt
```

## Run the app

```powershell
streamlit run app.py
```

Streamlit will open a local URL (typically `http://localhost:8501`).

## Using your database

Use the **Select Database** upload button in the app to choose your unclaimed-property database file. The database upload accepts `.xlsx` and `.xls` files and is remembered during your Streamlit session.

If no database is selected, the app will ask you to upload a database before searching.

## How to search

1. Click **Select Database** and upload your `.xlsx` or `.xls` database file.
2. Paste names/business names into the text area (one per line), **and/or** upload a CSV/Excel search list.
3. Adjust the fuzzy threshold slider (default 70).
4. Click **Search**.
5. Review matches and click **Download results as Excel**.
