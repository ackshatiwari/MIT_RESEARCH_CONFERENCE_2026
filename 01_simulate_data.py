"""Generate a synthetic long panel matching panel_schema.PANEL_COLUMNS, with
a known baked-in treatment effect. Used to validate 02-06 against ground
truth before/independent of the real merged panel -- e.g. "does SCM recover
approximately the true effect on data where we know the answer?"

This is NOT the real data pipeline. main.ipynb builds the real panel itself
(see plan) and only reuses PANEL_COLUMNS / validate_panel from panel_schema.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from panel_schema import PANEL_COLUMNS, validate_panel

ROAD_CLASSES = [
    "Secondary",
    "US Highway Primary",
    "Interstate Ramp",
    "Non-Interstate Ramp",
    "School Roads",
]
ZONING_CATEGORIES = ["Residential", "Commercial", "Industrial", "Mixed"]


def simulate_panel(
    n_control: int = 150,
    n_treated: int = 25,
    start_year: int = 2011,
    end_year: int = 2025,
    treat_year: int = 2019,
    base_aadt_range: tuple[float, float] = (500, 35_000),
    annual_growth_pct: float = 0.015,
    treatment_effect_pct: float = 0.15,
    noise_sd: float = 0.03,
    seed: int = 42,
) -> pd.DataFrame:
    """Simulate a tidy long panel with a known, recoverable treatment effect.

    Every segment has a base AADT, a shared regional growth trend, and
    idiosyncratic noise. Treated segments get an additional
    `treatment_effect_pct` multiplicative bump starting in `treat_year`.
    Returns a DataFrame conforming to panel_schema.PANEL_COLUMNS.
    """
    rng = np.random.default_rng(seed)
    years = np.arange(start_year, end_year + 1)
    n_segments = n_control + n_treated

    segment_id = [f"SIM{i:05d}" for i in range(n_segments)]
    treated_flags = np.array([False] * n_control + [True] * n_treated)
    base_aadt = rng.uniform(*base_aadt_range, size=n_segments)
    road_class = rng.choice(ROAD_CLASSES, size=n_segments)
    zoning = rng.choice(ZONING_CATEGORIES, size=n_segments)
    pop_density = rng.uniform(200, 6000, size=n_segments)

    rows = []
    for i in range(n_segments):
        for year in years:
            years_elapsed = year - start_year
            trend = (1 + annual_growth_pct) ** years_elapsed
            effect = (
                1 + treatment_effect_pct
                if treated_flags[i] and year >= treat_year
                else 1.0
            )
            noise = rng.normal(1.0, noise_sd)
            aadt = base_aadt[i] * trend * effect * noise
            rows.append(
                {
                    "segment_id": segment_id[i],
                    "year": int(year),
                    "aadt": max(aadt, 0.0),
                    "treated": bool(treated_flags[i]),
                    "treat_year": treat_year if treated_flags[i] else pd.NA,
                    "road_class": road_class[i],
                    "zoning": zoning[i],
                    "pop_density": pop_density[i],
                    "has_confound": False,
                }
            )

    panel = pd.DataFrame(rows)[PANEL_COLUMNS]
    panel["treat_year"] = panel["treat_year"].astype("Int64")
    validate_panel(panel)
    return panel


if __name__ == "__main__":
    df = simulate_panel()
    print(df.head())
    print(f"\n{len(df)} rows, {df['segment_id'].nunique()} segments, "
          f"{df.loc[df['treated'], 'segment_id'].nunique()} treated")
