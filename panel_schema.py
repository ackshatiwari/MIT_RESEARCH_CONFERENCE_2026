"""Shared tidy long-panel contract used by 01_simulate_data.py through
06_error_analysis.py and main.ipynb, so the schema can't drift between them.
"""

from __future__ import annotations

import pandas as pd

PANEL_COLUMNS = [
    "segment_id",
    "year",
    "aadt",
    "treated",
    "treat_year",
    "road_class",
    "zoning",
    "pop_density",
    "has_confound",
]

def validate_panel(df: pd.DataFrame) -> None:
    """Raise ValueError if df doesn't conform to the PANEL_COLUMNS contract."""
    missing = [c for c in PANEL_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"panel is missing required columns: {missing}")

    if df["segment_id"].isna().any():
        raise ValueError("panel has null segment_id values")
    if df["year"].isna().any():
        raise ValueError("panel has null year values")
    if not pd.api.types.is_bool_dtype(df["treated"]):
        raise ValueError(
            f"'treated' must be bool dtype, got {df['treated'].dtype}"
        )

    dup_key = df.duplicated(subset=["segment_id", "year"]).sum()
    if dup_key:
        raise ValueError(
            f"panel has {dup_key} duplicate (segment_id, year) rows -- "
            "aggregate or dedupe before use"
        )

    treated_no_year = df.loc[df["treated"], "treat_year"].isna().sum()
    if treated_no_year:
        raise ValueError(
            f"{treated_no_year} treated rows have a null treat_year"
        )
