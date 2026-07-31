"""In-space and in-time placebo tests for the synthetic control fits from
02_synthetic_control.py, plus a permutation-style rank p-value -- the
standard Abadie/Diamond/Hainmueller approach to SCM inference (no
distributional assumptions needed since there's no closed-form standard
error for the SCM weights).
"""

from __future__ import annotations

import importlib.util
import sys

import numpy as np
import pandas as pd

from panel_schema import validate_panel


def _load(modname: str, path: str):
    if modname in sys.modules:
        return sys.modules[modname]
    spec = importlib.util.spec_from_file_location(modname, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[modname] = m
    spec.loader.exec_module(m)
    return m


def _scm():
    return _load("_scm_02", "02_synthetic_control.py")


def in_space_placebo(
    panel: pd.DataFrame,
    treated_id: str,
    pre_years: list[int],
    outcome: str = "aadt",
    max_placebos: int | None = None,
    max_donors: int | None = None,
) -> pd.DataFrame:
    """Re-run SCM treating each donor as if it were the treated unit (same
    treat_year as the real treated unit), against the rest of the donor
    pool. Returns a table of pre/post RMSPE per placebo run, for comparison
    against the real treated unit's ratio. max_donors should match whatever
    was used for the real treated-unit fit (see 02_synthetic_control.py) --
    otherwise the placebo and real fits aren't using comparable donor pools.
    """
    validate_panel(panel)
    scm = _scm()
    treat_year = int(panel.loc[panel["segment_id"] == treated_id, "treat_year"].iloc[0])
    donor_ids = scm.build_donor_pool(panel, treated_id)
    if max_placebos is not None:
        donor_ids = donor_ids[:max_placebos]

    rows = []
    for pid in donor_ids:
        placebo_panel = panel.copy()
        mask = placebo_panel["segment_id"] == pid
        placebo_panel.loc[mask, "treated"] = True
        placebo_panel.loc[mask, "treat_year"] = treat_year
        try:
            r = scm.fit_synthetic_control(placebo_panel, pid, pre_years, outcome=outcome, max_donors=max_donors)
        except ValueError:
            continue
        rows.append({
            "segment_id": pid, "pre_rmspe": r.pre_rmspe,
            "post_rmspe": r.post_rmspe, "ratio": r.post_pre_rmspe_ratio,
        })
    return pd.DataFrame(rows)


def in_time_placebo(panel: pd.DataFrame, treated_id: str, fake_treat_year: int, outcome: str = "aadt"):
    """Re-run SCM on the real treated unit with an earlier fake treatment
    year, using only data from before the REAL treatment (so no genuine
    effect can contaminate the result). A well-specified model should show
    no meaningful post/pre RMSPE jump around the fake year.
    """
    validate_panel(panel)
    scm = _scm()
    real_treat_year = int(panel.loc[panel["segment_id"] == treated_id, "treat_year"].iloc[0])
    if fake_treat_year >= real_treat_year:
        raise ValueError("fake_treat_year must be before the real treatment year")

    sub_panel = panel[panel["year"] < real_treat_year].copy()
    mask = sub_panel["segment_id"] == treated_id
    sub_panel.loc[mask, "treat_year"] = fake_treat_year
    fake_pre_years = sorted(y for y in sub_panel["year"].unique() if y < fake_treat_year)
    if len(fake_pre_years) < 2:
        raise ValueError("not enough years before fake_treat_year to fit a pre-period")
    return scm.fit_synthetic_control(sub_panel, treated_id, fake_pre_years, outcome=outcome)


def filter_degenerate_placebos(
    placebo_table: pd.DataFrame,
    treated_pre_rmspe: float,
    min_relative_pre_rmspe: float = 0.05,
) -> pd.DataFrame:
    """Drop placebo fits whose pre-period RMSPE is implausibly small
    relative to the treated unit's own pre-fit.

    This is a known SCM pitfall when the donor pool is large relative to
    the number of pre-treatment periods: with e.g. ~150 donors fitting only
    ~8 pre-period points, some placebo donors get a near machine-precision
    "perfect" pre-fit by pure linear-algebra coincidence (the system is
    heavily underdetermined), not because they're meaningfully similar to
    the treated unit. Those give post/pre RMSPE ratios that blow up toward
    infinity and swamp the rank test. Excluding them before ranking is
    standard practice; the alternative fixes (shrink the donor pool,
    lengthen the pre-period) are noted in 06_error_analysis.py.
    """
    threshold = min_relative_pre_rmspe * treated_pre_rmspe
    return placebo_table[placebo_table["pre_rmspe"] >= threshold].copy()


def compute_rank_pvalue(true_ratio: float, placebo_ratios: pd.Series | np.ndarray) -> float:
    """Permutation-style rank p-value: how many placebo (post/pre RMSPE)
    ratios are at least as extreme as the real treated unit's. Standard
    SCM inference, per Abadie/Diamond/Hainmueller (2010).

    Callers should pass placebo_ratios that have already gone through
    filter_degenerate_placebos -- this function does not filter itself,
    since it's also used for already-clean distributions.
    """
    placebo_ratios = np.asarray(placebo_ratios)
    placebo_ratios = placebo_ratios[np.isfinite(placebo_ratios)]
    n = len(placebo_ratios)
    if n == 0:
        return float("nan")
    at_least_as_extreme = np.sum(placebo_ratios >= true_ratio)
    return float((at_least_as_extreme + 1) / (n + 1))


def plot_placebo_distribution(true_ratio: float, placebo_ratios: pd.Series | np.ndarray, ax=None):
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=(7, 4))
    ax.hist(np.asarray(placebo_ratios), bins=20, alpha=0.7, label="Placebo ratios")
    ax.axvline(true_ratio, color="red", linestyle="--", label="Treated unit ratio")
    ax.set_xlabel("Post/pre RMSPE ratio")
    ax.set_ylabel("Count")
    ax.set_title("In-space placebo distribution")
    ax.legend()
    return ax
