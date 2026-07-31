"""Heterogeneous treatment effect estimation via econml's CausalForestDML.

Simplification vs. a full panel causal-forest specification: this collapses
each segment's panel history to one row (a DiD-style "delta" outcome:
mean post-reference-year AADT minus mean pre-reference-year AADT) rather
than modeling the full time series. `reference_year` defaults to the
median treat_year across treated segments, applied to every segment
(control units don't have their own treat_year, so they need a shared
split point to define "pre"/"post"). This means treated segments whose
actual treat_year differs a lot from the reference year have a mismatched
pre/post window -- flagged here and in the notebook, not hidden.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from econml.dml import CausalForestDML
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor

from panel_schema import validate_panel


def prepare_cf_inputs(
    panel: pd.DataFrame,
    outcome: str = "aadt",
    reference_year: int | None = None,
):
    """Collapse the panel to one row per segment: covariates (road_class,
    zoning, pop_density, pre-period baseline level), treatment indicator,
    and a DiD-style delta outcome. Rows where zoning/pop_density are NaN
    (known real-data gaps -- see project plan) are still included; those
    columns just won't provide signal until the gap is filled.
    """
    validate_panel(panel)
    if reference_year is None:
        reference_year = int(panel.loc[panel["treated"], "treat_year"].median())

    def unit_row(df: pd.DataFrame) -> pd.Series:
        pre = df.loc[df["year"] < reference_year, outcome]
        post = df.loc[df["year"] >= reference_year, outcome]
        return pd.Series({
            "pre_mean": pre.mean() if len(pre) else np.nan,
            "delta": (post.mean() - pre.mean()) if len(pre) and len(post) else np.nan,
            "road_class": df["road_class"].iloc[0],
            "zoning": df["zoning"].iloc[0],
            "pop_density": df["pop_density"].iloc[0],
            "treated": bool(df["treated"].iloc[0]),
        })

    unit_df = panel.groupby("segment_id").apply(unit_row, include_groups=False).reset_index()
    unit_df = unit_df.dropna(subset=["delta", "pre_mean"])

    covariate_df = unit_df[["road_class", "zoning", "pre_mean"]].copy()
    covariate_df["pop_density"] = unit_df["pop_density"].fillna(0)
    covariate_df["pop_density_missing"] = unit_df["pop_density"].isna().astype(float)
    X = pd.get_dummies(covariate_df, columns=["road_class", "zoning"], dummy_na=True)
    X = X.astype(float)
    T = unit_df["treated"].astype(int).to_numpy()
    Y = unit_df["delta"].to_numpy()
    segment_ids = unit_df["segment_id"].to_numpy()
    return X, T, Y, segment_ids


def fit_causal_forest(
    X: pd.DataFrame,
    T: np.ndarray,
    Y: np.ndarray,
    n_estimators: int = 500,
    min_samples_leaf: int = 5,
    random_state: int = 42,
) -> CausalForestDML:
    model = CausalForestDML(
        model_y=RandomForestRegressor(n_estimators=100, min_samples_leaf=min_samples_leaf, random_state=random_state),
        model_t=RandomForestClassifier(n_estimators=100, min_samples_leaf=min_samples_leaf, random_state=random_state),
        discrete_treatment=True,
        n_estimators=n_estimators,
        min_samples_leaf=min_samples_leaf,
        random_state=random_state,
    )
    model.fit(Y, T, X=X)
    return model


def estimate_heterogeneous_effects(
    model: CausalForestDML, X: pd.DataFrame, segment_ids: np.ndarray, alpha: float = 0.1
) -> pd.DataFrame:
    effects = model.effect(X)
    lb, ub = model.effect_interval(X, alpha=alpha)
    return pd.DataFrame({
        "segment_id": segment_ids,
        "effect": effects,
        "ci_low": lb,
        "ci_high": ub,
    })


def plot_effect_heterogeneity(effects_df: pd.DataFrame, covariate: pd.Series | None = None, ax=None):
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=(7, 4))
    if covariate is not None:
        ax.scatter(covariate, effects_df["effect"], alpha=0.6)
        ax.set_xlabel(covariate.name or "covariate")
    else:
        ax.hist(effects_df["effect"], bins=20, alpha=0.75)
        ax.set_xlabel("Estimated treatment effect")
    ax.axhline(0, color="gray", linestyle=":") if covariate is not None else None
    ax.set_title("Heterogeneous treatment effects (causal forest)")
    return ax
