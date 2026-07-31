"""Cross-method comparison and robustness checks, pulling together
02_synthetic_control.py, 03_event_study_did.py, 04_placebo_tests.py, and
05_causal_forest.py results.

Note on comparability: SCM, event-study DiD, and the causal forest report
effects on different scales (SCM/CF: level-or-delta AADT gap; DiD: a
regression coefficient, which is on a log scale if run with outcome=
"log_aadt"). summarize_treatment_effects() keeps each method's native units
visible rather than forcing a false apples-to-apples number -- see the
`unit` column in its output.
"""

from __future__ import annotations

import importlib.util
import sys

import numpy as np
import pandas as pd


def _load(modname: str, path: str):
    if modname in sys.modules:
        return sys.modules[modname]
    spec = importlib.util.spec_from_file_location(modname, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[modname] = m
    spec.loader.exec_module(m)
    return m


def summarize_treatment_effects(
    scm_results: dict | None = None,
    did_table: pd.DataFrame | None = None,
    cf_effects: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Side-by-side point-estimate comparison. Any of the three inputs can
    be omitted (pass None) if that method wasn't run.
    """
    rows = []
    if scm_results:
        scm_avg = np.mean([
            r.gap_series[r.gap_series.index >= r.treat_year].mean()
            for r in scm_results.values()
        ])
        rows.append({
            "method": "Synthetic Control", "estimate": scm_avg,
            "n_units": len(scm_results), "unit": "avg post-period AADT gap (level)",
        })
    if did_table is not None:
        did_post = did_table[did_table["event_time"] >= 0]
        rows.append({
            "method": "Event-study DiD", "estimate": did_post["coef"].mean(),
            "n_units": None, "unit": "avg post-period coefficient (scale of outcome passed in)",
        })
    if cf_effects is not None and len(cf_effects):
        rows.append({
            "method": "Causal Forest", "estimate": cf_effects["effect"].mean(),
            "n_units": len(cf_effects), "unit": "avg treatment effect (delta AADT)",
        })
    return pd.DataFrame(rows)


def robustness_radius_check(panel_builder_fn, radii=(1.0, 1.5, 2.0), max_donors: int | None = None) -> pd.DataFrame:
    """Rerun SCM at each treatment-radius definition and report how the
    average post-treatment effect and treated-segment count shift.
    `panel_builder_fn(radius_miles)` must return a fully-built tidy panel
    (this lives in main.ipynb, since the spatial join is done there).
    """
    scm = _load("_scm_02", "02_synthetic_control.py")
    rows = []
    for radius in radii:
        panel = panel_builder_fn(radius)
        results = scm.run_all_scm(panel, max_donors=max_donors)
        if not results:
            rows.append({"radius_mi": radius, "n_treated_fitted": 0, "avg_post_gap": np.nan})
            continue
        avg_gap = np.mean([
            r.gap_series[r.gap_series.index >= r.treat_year].mean()
            for r in results.values()
        ])
        rows.append({"radius_mi": radius, "n_treated_fitted": len(results), "avg_post_gap": avg_gap})
    return pd.DataFrame(rows)


def placebo_significance_table(
    panel: pd.DataFrame, treated_ids=None, max_placebos: int = 100, max_donors: int | None = None
) -> pd.DataFrame:
    """Run the in-space placebo test + rank p-value for every treated unit
    (or a given subset). See 04_placebo_tests.py for the degenerate-fit
    filtering this relies on.
    """
    scm = _load("_scm_02", "02_synthetic_control.py")
    placebo = _load("_placebo_04", "04_placebo_tests.py")

    if treated_ids is None:
        treated_ids = panel.loc[panel["treated"], "segment_id"].unique().tolist()

    rows = []
    for tid in treated_ids:
        treat_year = int(panel.loc[panel["segment_id"] == tid, "treat_year"].iloc[0])
        pre_years = sorted(y for y in panel["year"].unique() if y < treat_year)
        if len(pre_years) < 2:
            continue
        try:
            real = scm.fit_synthetic_control(panel, tid, pre_years, max_donors=max_donors)
        except ValueError:
            continue
        pt = placebo.in_space_placebo(panel, tid, pre_years, max_placebos=max_placebos, max_donors=max_donors)
        pt_filtered = placebo.filter_degenerate_placebos(pt, real.pre_rmspe)
        pval = placebo.compute_rank_pvalue(real.post_pre_rmspe_ratio, pt_filtered["ratio"])
        rows.append({
            "segment_id": tid, "post_pre_ratio": real.post_pre_rmspe_ratio,
            "p_value": pval, "n_placebos_used": len(pt_filtered),
        })
    return pd.DataFrame(rows)


def plot_method_comparison(summary_df: pd.DataFrame, ax=None):
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=(7, 4))
    ax.bar(summary_df["method"], summary_df["estimate"])
    ax.set_ylabel("Estimated effect (native units per method -- see 'unit' column)")
    ax.set_title("Cross-method effect comparison")
    ax.tick_params(axis="x", rotation=15)
    return ax
