from __future__ import annotations

import io
import re
import time
from typing import Callable, List

import pandas as pd
import streamlit as st
from rapidfuzz import fuzz

REQUIRED_COLUMNS = ["Jurisdiction", "Name", "Amount", "Date"]
PROGRESS_UPDATE_INTERVAL_SECONDS = 0.2

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


def format_seconds(seconds: float) -> str:
    seconds = max(0.0, seconds)
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remaining = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {remaining}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m {remaining}s"


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


def prepare_search_names(search_names: List[str]) -> List[tuple[str, str]]:
    """Return raw and normalized search names, excluding values that normalize to empty."""
    return [(name, normalized) for name in search_names if (normalized := normalize_name(name))]


def update_search_progress(
    progress_bar,
    status_text,
    metrics_text,
    processed_names: int,
    total_names: int,
    elapsed: float,
) -> None:
    """Refresh Streamlit-native progress widgets for the current search batch."""
    pct = processed_names / total_names if total_names else 0.0
    avg_per_name = elapsed / processed_names if processed_names else 0.0
    eta = max(0.0, avg_per_name * (total_names - processed_names))

    progress_bar.progress(
        pct,
        text=(
            f"{processed_names}/{total_names} names processed "
            f"({pct * 100:.1f}%) | Elapsed: {format_seconds(elapsed)} | ETA: {format_seconds(eta)}"
        ),
    )
    status_text.info(f"Processing {processed_names} of {total_names} names...")
    metrics_text.caption(
        f"Processed: {processed_names} | Total: {total_names} | Complete: {pct * 100:.1f}% | "
        f"Elapsed: {format_seconds(elapsed)} | ETA: {format_seconds(eta)}"
    )


def search_records_with_progress(
    db_df: pd.DataFrame,
    search_names: List[str],
    fuzzy_threshold: int = 70,
    timer: Callable[[], float] = time.perf_counter,
) -> tuple[pd.DataFrame, dict]:
    records = []
    prepared_searches = prepare_search_names(search_names)
    total_names = len(prepared_searches)

    progress_bar = st.progress(0.0, text="Waiting to start search...")
    status_text = st.empty()
    metrics_text = st.empty()

    if total_names == 0:
        progress_bar.empty()
        status_text.warning("No valid names to process after normalization.")
        metrics_text.empty()
        return pd.DataFrame(), {"total_time": 0.0, "total_names": 0, "total_matches": 0, "avg_time": 0.0}

    db_records = db_df[["Name", "Jurisdiction", "Amount", "Date", "__normalized_name"]].to_dict("records")

    start_time = timer()
    last_progress_elapsed = 0.0

    for i, (raw_name, search_norm) in enumerate(prepared_searches, start=1):
        for row in db_records:
            match_type, confidence = classify_match(search_norm, row["__normalized_name"])

            if match_type == "Fuzzy" and confidence < fuzzy_threshold:
                continue

            if match_type in {"Exact", "Partial", "Fuzzy"}:
                records.append(
                    {
                        "Search Name": raw_name,
                        "Matched Name": str(row["Name"]),
                        "Jurisdiction": row["Jurisdiction"],
                        "Amount": row["Amount"],
                        "Date": row["Date"],
                        "Match Type": match_type,
                        "Confidence Score": confidence,
                    }
                )

        elapsed = timer() - start_time
        should_update_progress = (
            i == 1
            or i == total_names
            or elapsed - last_progress_elapsed >= PROGRESS_UPDATE_INTERVAL_SECONDS
        )
        if should_update_progress:
            update_search_progress(progress_bar, status_text, metrics_text, i, total_names, elapsed)
            last_progress_elapsed = elapsed

    total_time = timer() - start_time
    total_matches = len(records)
    avg_time = total_time / total_names if total_names else 0.0

    update_search_progress(progress_bar, status_text, metrics_text, total_names, total_names, total_time)
    status_text.success("Search complete.")
    metrics_text.caption(
        f"Completed {total_names}/{total_names} (100.0%) in {format_seconds(total_time)}. "
        f"Total matches: {total_matches}."
    )

    results_df = pd.DataFrame(records)
    if not results_df.empty:
        results_df = results_df.sort_values(
            by=["Search Name", "Confidence Score", "Match Type"], ascending=[True, False, True]
        ).reset_index(drop=True)

    summary = {
        "total_time": total_time,
        "total_names": total_names,
        "total_matches": total_matches,
        "avg_time": avg_time,
    }
    return results_df, summary


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Matches")
    output.seek(0)
    return output.getvalue()


def remember_database_upload(uploaded_database) -> None:
    """Persist the selected database file in Streamlit session state."""
    if uploaded_database is None:
        return

    st.session_state["database_file_name"] = uploaded_database.name
    st.session_state["database_file_bytes"] = uploaded_database.getvalue()


def has_database_selected() -> bool:
    return "database_file_bytes" in st.session_state


def load_database(database_bytes: bytes) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(database_bytes))
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

    uploaded_database = st.file_uploader(
        "Select Database",
        type=["xlsx", "xls"],
        help="Upload the Excel database containing Jurisdiction, Name, Amount, and Date columns.",
    )
    remember_database_upload(uploaded_database)

    if has_database_selected():
        st.success(f"Database selected: {st.session_state['database_file_name']}")
    else:
        st.info("Please upload a database Excel file before searching.")

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
            if not has_database_selected():
                st.warning("Please upload a database Excel file before searching.")
                return

            db_df = load_database(st.session_state["database_file_bytes"])
            search_names = read_search_names(text_input, uploaded_file)

            if not search_names:
                st.warning("Enter names in the text box and/or upload a file with names in the first column.")
                return

            with st.spinner("Searching records. Please wait..."):
                results_df, summary = search_records_with_progress(
                    db_df, search_names, fuzzy_threshold=fuzzy_threshold
                )

            st.subheader("Search Summary")
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Search Time", format_seconds(summary["total_time"]))
            c2.metric("Total Matches Found", f"{summary['total_matches']:,}")
            c3.metric("Average Time per Search", format_seconds(summary["avg_time"]))

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
