from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Iterable, List

import pandas as pd
import streamlit as st
from rapidfuzz import fuzz

DATABASE_PATH_DEFAULT = (
    r"C:\Users\rcgar\OneDrive\Unclaimed Property\Anderson\Municipality Databases\Municipality Database 2025.xlsx"
)
REQUIRED_COLUMNS = ["Jurisdiction", "Name", "Amount", "Date"]

SUFFIX_PATTERN = re.compile(
    r"\b(LLC|INC|CO|CORP|CORPORATION|LP|LLP)\b\.?", re.IGNORECASE
)
NON_ALNUM_PATTERN = re.compile(r"[^A-Z0-9 ]+")
SPACE_PATTERN = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Normalize names by uppercasing, stripping suffixes, and compacting whitespace."""
    if pd.isna(name):
        return ""
    cleaned = str(name).upper().strip()
    cleaned = NON_ALNUM_PATTERN.sub(" ", cleaned)
    cleaned = SUFFIX_PATTERN.sub(" ", cleaned)
    cleaned = SPACE_PATTERN.sub(" ", cleaned).strip()
    return cleaned


def read_search_names(text_input: str, uploaded_file) -> List[str]:
    names: List[str] = []

    if text_input.strip():
        names.extend([line.strip() for line in text_input.splitlines() if line.strip()])

    if uploaded_file is not None:
        file_name = uploaded_file.name.lower()
        if file_name.endswith(".csv"):
            search_df = pd.read_csv(uploaded_file)
        else:
            search_df = pd.read_excel(uploaded_file)

        if search_df.empty:
            return names

        first_col = search_df.columns[0]
        file_names = (
            search_df[first_col].dropna().astype(str).str.strip().loc[lambda s: s != ""].tolist()
        )
        names.extend(file_names)

    # Deduplicate while preserving order
    unique_names = list(dict.fromkeys(names))
    return unique_names


def classify_match(search_norm: str, candidate_norm: str) -> tuple[str, int]:
    if not search_norm or not candidate_norm:
        return "No Match", 0

    if search_norm == candidate_norm:
        return "Exact", 100

    if search_norm in candidate_norm or candidate_norm in search_norm:
        confidence = max(75, fuzz.token_set_ratio(search_norm, candidate_norm))
        return "Partial", int(round(confidence))

    confidence = int(round(fuzz.token_set_ratio(search_norm, candidate_norm)))
    return "Fuzzy", confidence


def search_records(db_df: pd.DataFrame, search_names: Iterable[str], fuzzy_threshold: int = 70) -> pd.DataFrame:
    records = []

    for raw_name in search_names:
        search_norm = normalize_name(raw_name)
        if not search_norm:
            continue

        for _, row in db_df.iterrows():
            matched_name = str(row["Name"])
            candidate_norm = row["__normalized_name"]
            match_type, confidence = classify_match(search_norm, candidate_norm)

            if match_type == "Fuzzy" and confidence < fuzzy_threshold:
                continue

            if match_type in {"Exact", "Partial", "Fuzzy"}:
                records.append(
                    {
                        "Search Name": raw_name,
                        "Matched Name": matched_name,
                        "Jurisdiction": row["Jurisdiction"],
                        "Amount": row["Amount"],
                        "Date": row["Date"],
                        "Match Type": match_type,
                        "Confidence Score": confidence,
                    }
                )

    results_df = pd.DataFrame(records)
    if not results_df.empty:
        results_df = results_df.sort_values(
            by=["Search Name", "Confidence Score", "Match Type"], ascending=[True, False, True]
        ).reset_index(drop=True)
    return results_df


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Matches")
    output.seek(0)
    return output.getvalue()


def load_database(path: str) -> pd.DataFrame:
    db_path = Path(path)
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found at: {path}")

    df = pd.read_excel(db_path)
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Database is missing required columns: {', '.join(missing)}")

    df = df[REQUIRED_COLUMNS].copy()
    df["__normalized_name"] = df["Name"].map(normalize_name)
    return df


def main() -> None:
    st.set_page_config(page_title="Unclaimed Property Search", layout="wide")
    st.title("Unclaimed Property Excel Search")
    st.write(
        "Search a municipality unclaimed-property Excel database using exact, partial, and fuzzy matching."
    )

    db_path = st.text_input("Database path", value=DATABASE_PATH_DEFAULT)
    fuzzy_threshold = st.slider("Minimum fuzzy confidence score", min_value=0, max_value=100, value=70)

    text_input = st.text_area(
        "Paste names/business names (one per line)",
        placeholder="ACME LLC\nSMITH CONSTRUCTION INC\nJOHN DOE",
        height=180,
    )

    uploaded_file = st.file_uploader(
        "Upload search list (Excel or CSV; first column is used)", type=["xlsx", "xls", "csv"]
    )

    if st.button("Search", type="primary"):
        try:
            db_df = load_database(db_path)
            search_names = read_search_names(text_input, uploaded_file)

            if not search_names:
                st.warning("Enter names in the text box and/or upload a file with names in the first column.")
                return

            results_df = search_records(db_df, search_names, fuzzy_threshold=fuzzy_threshold)

            if results_df.empty:
                st.info("No matches found using the current threshold.")
                return

            st.success(f"Found {len(results_df)} matching rows.")
            st.dataframe(results_df, use_container_width=True)

            excel_data = to_excel_bytes(results_df)
            st.download_button(
                label="Download results as Excel",
                data=excel_data,
                file_name="unclaimed_property_search_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except Exception as exc:
            st.error(str(exc))


if __name__ == "__main__":
    main()
