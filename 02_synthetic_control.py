
"""Synthetic control method (SCM), Abadie-style donor weighting.

Simplification vs. the full Abadie/Diamond/Hainmueller procedure: this
implementation optimizes only the pre-period outcome (AADT) RMSPE with
equal weighting (V = identity), rather than jointly optimizing a separate
predictor-weighting matrix V. That's a standard, defensible simplification
for a single-outcome panel like this one and is transparent in the code
below -- flagged here so it isn't mistaken for the full two-step procedure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import nnls

from panel_schema import validate_panel


@dataclass
class SCMResult:
    treated_id: str
    treat_year: int
    weights: dict = field(repr=False)
    donor_ids: list
    treated_series: pd.Series
    synthetic_series: pd.Series
    gap_series: pd.Series
    pre_rmspe: float
    post_rmspe: float

    @property
    def post_pre_rmspe_ratio(self) -> float:
        if self.pre_rmspe == 0:
            return np.inf
        return self.post_rmspe / self.pre_rmspe


def build_donor_pool(panel: pd.DataFrame, treated_id: str) -> list:
    """Every never-treated segment is eligible; other treated segments are
    excluded so the donor pool isn't contaminated by other units' effects.
    """
    validate_panel(panel)
    donors = panel.loc[~panel["treated"], "segment_id"].unique().tolist()
    return [d for d in donors if d != treated_id]


def fit_synthetic_control(
    panel: pd.DataFrame,
    treated_id: str,
    pre_years: list[int],
    outcome: str = "aadt",
    max_donors: int | None = None,
) -> SCMResult:
    """Fit donor weights minimizing pre-period RMSPE, then project the
    synthetic control across the full panel's year range.

    max_donors: if set, pre-screen the donor pool down to the N donors with
    the closest pre-period outcome pattern (smallest Euclidean distance) to
    the treated unit before fitting. This matters when the donor pool is
    large relative to the number of pre-period points -- e.g. thousands of
    donors fitting only 5-10 pre-years is a heavily underdetermined system,
    and NNLS/any least-squares solver will find some combination that fits
    the pre-period near-perfectly (pre_rmspe -> 0) by pure linear-algebra
    coincidence, not genuine similarity. That degenerate "perfect fit" isn't
    trustworthy for reading off a post-period effect. Standard SCM practice
    for large donor pools is exactly this kind of pre-screening (see e.g.
    Abadie 2021, "Using Synthetic Controls"). Leave as None (no screening)
    for small, hand-curated donor pools like the simulated-data tests.
    """
    validate_panel(panel)
    treat_year = int(panel.loc[panel["segment_id"] == treated_id, "treat_year"].iloc[0])

    donor_ids = build_donor_pool(panel, treated_id)
    all_ids = [treated_id] + donor_ids

    wide = panel[panel["segment_id"].isin(all_ids)].pivot(
        index="segment_id", columns="year", values=outcome
    )

    # Only keep donors with complete data across every year needed (pre + full range).
    all_years = sorted(panel["year"].unique())
    wide = wide.dropna(subset=all_years)
    if treated_id not in wide.index:
        raise ValueError(
            f"{treated_id} itself has missing years somewhere in the panel's "
            f"full {all_years[0]}-{all_years[-1]} range, so it can't be used "
            "as an SCM treated unit under this full-coverage requirement"
        )
    donor_ids = [d for d in donor_ids if d in wide.index]
    if not donor_ids:
        raise ValueError(f"no complete-coverage donors available for {treated_id}")

    if max_donors is not None and len(donor_ids) > max_donors:
        treated_pre_for_screen = wide.loc[treated_id, pre_years].to_numpy()
        donors_pre_for_screen = wide.loc[donor_ids, pre_years].to_numpy()
        dist = np.sqrt(((donors_pre_for_screen - treated_pre_for_screen) ** 2).sum(axis=1))
        keep_idx = np.argsort(dist)[:max_donors]
        donor_ids = [donor_ids[i] for i in keep_idx]

    treated_full = wide.loc[treated_id]
    donors_full = wide.loc[donor_ids]

    treated_pre = treated_full[pre_years].to_numpy()
    donors_pre = donors_full[pre_years].to_numpy()  # (n_donors, n_pre_years)

    n_donors = len(donor_ids)

    # Solve min ||treated_pre - donors_pre.T @ w||^2 s.t. w >= 0, sum(w) = 1
    # as a non-negative least squares problem (scipy.optimize.nnls, an
    # active-set method) rather than general nonlinear SLSQP. With ~150
    # donors sharing very similar pre-period trends, the loss surface is
    # severely ill-conditioned/near-collinear, and SLSQP's SQP iterations
    # took 6-8+ seconds per fit (occasionally worse) on that landscape; NNLS
    # handles it in well under a second. The equality constraint is enforced
    # by appending one heavily-weighted row so sum(w) is pulled to ~1 --
    # a standard soft-constraint reformulation for simplex-constrained NNLS.
    scale = np.abs(treated_pre).mean()
    penalty = 1e4 * max(scale, 1.0)
    donors_aug = np.vstack([donors_pre.T, np.full((1, n_donors), penalty)])
    treated_aug = np.concatenate([treated_pre, [penalty]])

    weights, _ = nnls(donors_aug, treated_aug)
    if weights.sum() == 0:
        raise ValueError(f"NNLS returned all-zero weights for {treated_id}")
    weights = weights / weights.sum()

    synthetic_full = pd.Series(
        donors_full.to_numpy().T @ weights, index=donors_full.columns, name="synthetic"
    )
    gap = treated_full - synthetic_full

    pre_mask = synthetic_full.index.isin(pre_years)
    post_mask = synthetic_full.index >= treat_year
    pre_rmspe = float(np.sqrt(np.mean(gap[pre_mask] ** 2)))
    post_rmspe = float(np.sqrt(np.mean(gap[post_mask] ** 2))) if post_mask.any() else float("nan")

    return SCMResult(
        treated_id=treated_id,
        treat_year=treat_year,
        weights=dict(zip(donor_ids, weights)),
        donor_ids=donor_ids,
        treated_series=treated_full,
        synthetic_series=synthetic_full,
        gap_series=gap,
        pre_rmspe=pre_rmspe,
        post_rmspe=post_rmspe,
    )


def run_all_scm(panel: pd.DataFrame, outcome: str = "aadt", max_donors: int | None = None) -> dict:
    """Fit SCM for every treated segment, using each segment's own treat_year
    to define its pre-period. See fit_synthetic_control for max_donors.
    """
    validate_panel(panel)
    treated_ids = panel.loc[panel["treated"], "segment_id"].unique().tolist()
    results = {}
    for tid in treated_ids:
        treat_year = int(panel.loc[panel["segment_id"] == tid, "treat_year"].iloc[0])
        pre_years = sorted(y for y in panel["year"].unique() if y < treat_year)
        if len(pre_years) < 2:
            continue  # not enough pre-period to fit meaningfully
        try:
            results[tid] = fit_synthetic_control(panel, tid, pre_years, outcome=outcome, max_donors=max_donors)
        except ValueError:
            continue
    return results


def plot_scm_fit(scm_result: SCMResult, ax=None):
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(scm_result.treated_series.index, scm_result.treated_series.values,
            label=f"Treated ({scm_result.treated_id})", marker="o")
    ax.plot(scm_result.synthetic_series.index, scm_result.synthetic_series.values,
            label="Synthetic control", linestyle="--", marker="x")
    ax.axvline(scm_result.treat_year, color="gray", linestyle=":", label="Treatment")
    ax.set_xlabel("Year")
    ax.set_ylabel("AADT")
    ax.set_title(f"SCM fit: {scm_result.treated_id} "
                 f"(post/pre RMSPE ratio={scm_result.post_pre_rmspe_ratio:.2f})")
    ax.legend()
    return ax
