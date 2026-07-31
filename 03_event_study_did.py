"""Event-study difference-in-differences with two-way (segment + year) fixed
effects, estimated via iterative within-demeaning rather than explicit
dummy columns.

Why demeaning instead of `C(segment_id)` dummies: a real panel here can have
several thousand distinct segments. A dense OLS design matrix with one dummy
column per segment (thousands of columns x tens of thousands of rows) is
both slow and memory-heavy. The within (FWL) transformation absorbs entity
and year fixed effects by iteratively demeaning, which is what packages like
linearmodels/pyfixest do under the hood -- this avoids the dependency while
keeping the same estimator for a panel like this one. Iterative (not
one-shot) demeaning is used because the panel is unbalanced (segments don't
all have identical year coverage -- see the AADT schema-quality notes from
earlier in the project), where the closed-form two-way demeaning formula
doesn't exactly hold.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from panel_schema import validate_panel


def build_event_time(panel: pd.DataFrame, event_window: tuple[int, int] = (-5, 5)) -> pd.DataFrame:
    """Add an `event_time` column: year - treat_year for treated rows,
    clipped to event_window; NaN for never-treated (control) rows.
    """
    validate_panel(panel)
    df = panel.copy()
    df["event_time"] = pd.NA
    treated_mask = df["treated"]
    raw_event_time = df.loc[treated_mask, "year"] - df.loc[treated_mask, "treat_year"]
    clipped = raw_event_time.clip(lower=event_window[0], upper=event_window[1])
    df.loc[treated_mask, "event_time"] = clipped
    return df


def _iterative_demean(
    df: pd.DataFrame,
    value_cols: list[str],
    entity_col: str = "segment_id",
    time_col: str = "year",
    n_iter: int = 50,
    tol: float = 1e-10,
) -> np.ndarray:
    """Absorb entity and time fixed effects via alternating demeaning
    (the standard within-transformation approach for unbalanced two-way
    panels). Returns a plain ndarray, same row order as df.
    """
    values = df[value_cols].to_numpy(dtype=float)
    entity_idx, _ = pd.factorize(df[entity_col].to_numpy())
    time_idx, _ = pd.factorize(df[time_col].to_numpy())
    n_entity, n_time = entity_idx.max() + 1, time_idx.max() + 1

    for _ in range(n_iter):
        entity_sums = np.zeros((n_entity, values.shape[1]))
        entity_counts = np.zeros(n_entity)
        np.add.at(entity_sums, entity_idx, values)
        np.add.at(entity_counts, entity_idx, 1)
        entity_means = entity_sums / entity_counts[:, None]
        values = values - entity_means[entity_idx]

        time_sums = np.zeros((n_time, values.shape[1]))
        time_counts = np.zeros(n_time)
        np.add.at(time_sums, time_idx, values)
        np.add.at(time_counts, time_idx, 1)
        time_means = time_sums / time_counts[:, None]
        values = values - time_means[time_idx]

        if max(np.abs(entity_means).max(), np.abs(time_means).max()) < tol:
            break

    return values


def run_event_study(
    panel: pd.DataFrame,
    outcome: str = "aadt",
    event_window: tuple[int, int] = (-5, 5),
    reference_period: int = -1,
    cluster: bool = True,
) -> tuple[pd.DataFrame, "sm.regression.linear_model.RegressionResultsWrapper"]:
    """Two-way FE event-study regression. Returns (tidy coefficient table,
    raw statsmodels result). Standard errors are clustered by segment_id
    (approximate after manual demeaning -- exact panel-cluster SE
    computation with degrees-of-freedom correction is what linearmodels
    would give you if that dependency is later added; this is the standard,
    widely-used approximation).
    """
    df = build_event_time(panel, event_window)

    event_times = [k for k in range(event_window[0], event_window[1] + 1) if k != reference_period]
    for k in event_times:
        df[f"event_{k}"] = (df["event_time"] == k).astype(float)
    dummy_cols = [f"event_{k}" for k in event_times]

    demeaned = _iterative_demean(df, [outcome] + dummy_cols)
    y_tilde = demeaned[:, 0]
    x_tilde = demeaned[:, 1:]

    model = sm.OLS(y_tilde, x_tilde)
    if cluster:
        fit = model.fit(cov_type="cluster", cov_kwds={"groups": df["segment_id"].to_numpy()})
    else:
        fit = model.fit(cov_type="HC1")

    ci = fit.conf_int()
    table = pd.DataFrame({
        "event_time": event_times,
        "coef": fit.params,
        "se": fit.bse,
        "ci_low": ci[:, 0],
        "ci_high": ci[:, 1],
    })
    ref_row = pd.DataFrame([{
        "event_time": reference_period, "coef": 0.0, "se": 0.0, "ci_low": 0.0, "ci_high": 0.0,
    }])
    table = pd.concat([table, ref_row], ignore_index=True).sort_values("event_time").reset_index(drop=True)

    return table, fit


def plot_event_study(table: pd.DataFrame, ax=None):
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=(8, 4.5))
    yerr = [table["coef"] - table["ci_low"], table["ci_high"] - table["coef"]]
    ax.errorbar(table["event_time"], table["coef"], yerr=yerr, fmt="o-", capsize=3)
    ax.axhline(0, color="gray", linestyle=":")
    ax.axvline(-0.5, color="gray", linestyle="--", label="Treatment")
    ax.set_xlabel("Event time (years relative to treatment)")
    ax.set_ylabel("Estimated effect on outcome")
    ax.set_title("Event-study coefficients (two-way FE, clustered SE)")
    ax.legend()
    return ax
