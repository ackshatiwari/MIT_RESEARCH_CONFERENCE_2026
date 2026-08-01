# Quantifying the Traffic Footprint of Data Center Construction: A Multi-Method Causal Analysis of Loudoun and Prince William Counties, Virginia

## Abstract

Data center construction in Northern Virginia has accelerated sharply over the past decade, and residents, planners, and local media routinely attribute worsening road congestion to it. Whether this attribution survives rigorous causal scrutiny, however, is untested. We assemble a longitudinal panel of Virginia Department of Transportation (VDOT) Annual Average Daily Traffic (AADT) counts (2011–2025, 135,250 segment-year observations across 10,723 road segments) and merge it with real data-center completion records from Loudoun and Prince William Counties (228 permitted/occupied facilities) to identify 2,888 road segments within 1.5 miles of a completed data center. We estimate the effect of data-center completion on nearby AADT using four independent causal-inference approaches: synthetic control (SCM), event-study difference-in-differences (DiD), placebo/permutation inference, and causal forest. The four methods disagree substantially: SCM finds a near-zero median effect (mean +1.32%, median +0.00%) with unstable point estimates; DiD finds a growing, nominally significant post-treatment increase (up to +7.6% by five years out) but also significant pre-treatment divergence, violating the parallel-trends assumption it depends on; placebo tests find the SCM estimates statistically indistinguishable from noise for 87% of tested segments; and causal forest finds a small mean effect (+34.9 vehicles/day) swamped by enormous unit-level variance (SD 1,209). We report this disagreement as the central finding rather than collapsing it into a single headline number, and we identify the specific data limitations — non-annual VDOT count cycles, missing zoning/population-density covariates, and uneven treatment-year coverage — that most plausibly explain why no method converges on a stable estimate.

## 1. Introduction

Loudoun and Prince William Counties, Virginia sit at the center of the world's largest data-center market by capacity, and both counties have seen rapid growth in permitted and completed data-center facilities over the past fifteen years. Local reporting and public comment at zoning hearings frequently assert that this construction measurably worsens traffic on nearby roads, both during construction (heavy-equipment and workforce traffic) and after occupancy (ongoing staff, security, and maintenance trips, plus the broader commercial/logistics activity such facilities attract to a corridor). This claim is plausible but, to our knowledge, has not been tested against public traffic-count data using causal-inference methods designed to separate a genuine treatment effect from confounding regional growth trends.

This paper asks a narrow, answerable version of that question: **using VDOT's own published AADT counts and each county's own data-center permit records, does the completion of a data center produce a detectable, method-robust increase in AADT on nearby road segments?** We treat this as a triangulation problem rather than a single-estimator problem, because no one method's identifying assumptions are obviously satisfied by this data-generating process. We therefore run four methods with different assumptions and different failure modes, and report where they agree, where they disagree, and why.

## 2. Related Research

**Synthetic control.** The synthetic control method was introduced by Abadie, Diamond, and Hainmueller (2010) to estimate the effect of California's tobacco control program by constructing a weighted combination of untreated "donor" units that closely tracks the treated unit's pre-treatment outcome path. Abadie (2021) provides the methodological guidance we follow most closely here, including donor-pool screening and the caution that unscreened, high-dimensional donor pools can produce spuriously perfect pre-treatment fits.

**Difference-in-differences with staggered timing.** Because our treated segments have staggered treatment years (data centers complete in different years), we use an event-study specification rather than a static two-period DiD, which recent econometric work (Goodman-Bacon, 2021) shows can otherwise produce badly biased estimates under staggered adoption when treatment effects are heterogeneous over time.

**Causal forests.** For heterogeneous treatment effect estimation we use the causal forest of Wager and Athey (2018), implemented via `econml`'s `CausalForestDML`, which extends Breiman's random forest to produce pointwise-consistent, asymptotically normal treatment-effect estimates under unconfoundedness.

**Data-center traffic impacts specifically.** Formal academic literature isolating data centers' effect on *road* traffic (as opposed to data-center *network* traffic, a separate and unrelated literature) is limited. Industry transportation-planning practice notes that data centers do not fit standard trip-generation assumptions used in conventional traffic impact studies and that their largest surge in vehicle activity is during the temporary construction phase rather than steady-state operation (Kittelson & Associates; Wells + Associates). Recent public-health-oriented work has begun examining data centers' broader community impacts in Virginia specifically, including construction-related truck traffic (Frontiers in Climate, 2026). We are not aware of a prior study that applies synthetic control, event-study DiD, and causal forest methods jointly to VDOT's public AADT panel to test this question directly, which is the gap this paper addresses.

## 3. Data

**AADT panel.** VDOT publishes AADT by road segment (`Link ID`) annually; we loaded 30 source files spanning three schema variants (a legacy header-row format, a header-row-free 2021 Loudoun export, and a 2022 "TMS" export with different column names) into a single long panel: 137,904 raw segment-year rows, reduced to 135,250 after removing 2,654 exact duplicate `(segment_id, year)` rows (verified to carry identical AADT values, so no information was lost). Overall AADT is missing for 3.6% of rows.

**Route geometry.** VDOT AADT exports carry no coordinates. We joined each segment to VDOT's published route-geometry layer by route name, building a `segment_id → route name` crosswalk from the subset of file-years that carry a route-name field and propagating it to all years for the same segment (a segment's `Link ID` is stable over time). This resolved a route name for 10,502 of 10,723 segments (97.9%), of which 9,654 (91.9%) matched a real route-geometry feature.

**Treatment anchors.** We define "treated" using each county's own real permit/occupancy data, not a proxy:
- **Prince William County**: 211 data-center buildings in the county's open-data feature layer, of which 56 have `PermitStatus == "Finaled"` and a non-null occupancy date (`OCCDate`); the remaining 155 are still Planned, Issued, or Pending and are excluded rather than treated as completed.
- **Loudoun County**: 239 data-center buildings in the county's `Existing_Permitted_Data_Center_Buildings` layer, of which 172 have a genuine final-inspection date (`BP_FINAL_DATE`); the other 67 are still under construction and carry either an Esri null-date sentinel (`1899-12-30`/`1901-01-01`) or a true null in that field, and are excluded.

This yields **228 real treatment anchors** (56 PWC + 172 Loudoun), each with a `treat_year` equal to its completion/occupancy year.

**Treatment assignment.** A road segment is "treated" if any point on its route geometry falls within 1.5 miles of a treatment anchor (computed via flat-earth mile projection and point-to-segment distance, not a third-party GIS library), with 1.0-mile and 2.0-mile radii available as robustness checks. At 1.5 miles this flags 2,888 of 10,723 segments (26.9%) as treated, versus 7,835 control/donor segments. Sensitivity to radius: 1,249 segments are within 1.0 mile and 2,857 within 2.0 miles, so the treated group roughly doubles across this range — a real sensitivity that should be checked, not a bug.

**Known data gaps, disclosed rather than filled with guesses:** `zoning` and `pop_density` covariates are unavailable for both counties (no general zoning-boundary layer was sourced, and the Census ACS pull lacks a land-area field) and are carried as `NaN` throughout; `road_class` is real (from VDOT route geometry) but 94% of all segments are classified "Secondary," limiting its discriminating power. Treatment-year coverage is also uneven: qualifying anchors' completion dates range from 1986 to 2026, and only a subset falls inside a usable pre/post window within the panel's 2011–2025 span (see Section 5).

## 4. Methodology

We apply four methods, each with a different identifying assumption, to the same underlying panel.

### 4.1 Synthetic Control (SCM)

For each treated segment, we construct a synthetic counterfactual as a weighted average of donor (control) segments, with weights chosen to minimize pre-treatment root mean squared prediction error (RMSPE) subject to non-negativity and a sum-to-one constraint. We solve this as a non-negative least squares problem (`scipy.optimize.nnls`) with the equality constraint enforced by an augmented penalty row, rather than general nonlinear (SLSQP) optimization, for tractability across thousands of segments with near-collinear donor pools.

With several thousand potential donors fitting only 5–14 pre-period points, an unscreened SCM fit will essentially always find a spuriously perfect pre-period match by linear-algebra coincidence. Following standard large-donor-pool practice (Abadie, 2021), we pre-screen to the 25 donors with the closest pre-period Euclidean distance (`max_donors=25`) before fitting. We additionally restrict SCM to treated segments with `treat_year` between 2016 and 2023 (guaranteeing ≥5 pre-period years and ≥2 post-period years); this is the primary defense against degenerate fits, and remaining degenerate cases (`pre_rmspe == 0`) are reported rather than discarded.

### 4.2 Event-Study Difference-in-Differences

We estimate a two-way (segment and year) fixed-effects event-study specification on `log(AADT)`, with event time defined as `year − treat_year`, clipped to an eleven-point window (event time −5 to +5) and treatment years restricted to 2013–2024. Fixed effects are absorbed via iterative within-demeaning (the Frisch–Waugh–Lovell approach) rather than explicit dummy variables, because the panel is large (thousands of segments) and unbalanced, making an explicit-dummy design matrix impractical; standard errors are clustered by `segment_id`. Because the outcome is logged, coefficients are read approximately as percentage effects relative to the omitted reference period (event time −1).

### 4.3 Placebo / Permutation Inference

To assess whether SCM's point estimates are distinguishable from chance, we run in-space placebo tests: for a subset of treated segments, we reassign pseudo-treatment to each of up to 80 donor segments in turn, refit SCM, and compute each placebo unit's post/pre RMSPE ratio. We then compute a permutation-style rank p-value — the fraction of placebo ratios at least as extreme as the real treated unit's ratio (following the logic of Abadie, Diamond, and Hainmueller, 2010). Due to computational cost (fitting SCM ~100 times per treated unit), this was run on the first 15 SCM-eligible segments rather than the full 1,035.

### 4.4 Causal Forest

To estimate heterogeneous treatment effects and use covariates beyond a single average, we fit a causal forest (Wager and Athey, 2018) via `econml`'s `CausalForestDML`, with a `RandomForestRegressor` (100 trees) as the outcome nuisance model and a `RandomForestClassifier` (100 trees) as the treatment-propensity nuisance model, and 300 trees in the causal forest itself. Each segment's panel history is collapsed to one row (pre/post mean AADT delta around the median treat_year among eligible treated segments), with `road_class` and pre-period mean AADT level as the only real covariates available to split on, since `zoning` and `pop_density` are unavailable (Section 3).

## 5. Results

**Panel composition.** The assembled panel has 10,723 unique segments (2,888 treated, 7,835 control) across 135,250 segment-year rows. Treated segments' completion years span 1986–2026; only a fraction fall inside a usable estimation window (Table 1 discussion below), which drives each method's differing effective sample size.

**Synthetic control.** Of 1,379 segments eligible for SCM (`treat_year` in [2016, 2023]), 1,035 fit successfully (the rest were dropped for missing-year coverage or lack of complete-coverage donors). Despite donor screening, 224 of 1,035 fitted segments (21.6%) still show a degenerate, exactly-zero pre-period RMSPE fit. The mean post-treatment percentage gap across fitted segments is **+1.32%**, but the **median is 0.00%** — more than half of segments show no detectable gap at all, and the mean is being pulled by a smaller number of large deviations. Notably, the same 1,035 segments' *level*-based average post-treatment gap (used in the cross-method comparison, Table 2) is **−24.1 AADT**, the opposite sign of the percentage-based average. This is not two separate findings: it is the same fitted segments reweighted two different ways, with degenerate fits (whose post-period behavior is unconstrained by the fitting procedure) dominating an unnormalized level-average differently than a per-segment percentage-average. We interpret this as direct evidence that SCM's point estimate from this panel is unstable, not as two results requiring reconciliation.

**Event-study DiD.** Table 1 below reports the full event-study coefficient path.

| Event time (years from completion) | Coefficient (≈ % of AADT) | Std. error | 95% CI |
|---:|---:|---:|---|
| −5 | −4.75% | 1.21% | [−7.12%, −2.38%] |
| −4 | −2.48% | 1.00% | [−4.44%, −0.53%] |
| −3 | −1.34% | 0.84% | [−2.99%, 0.31%] |
| −2 | −1.18% | 0.50% | [−2.15%, −0.20%] |
| −1 (reference) | 0.00% | — | — |
| 0 | −0.66% | 0.36% | [−1.37%, 0.06%] |
| +1 | +0.12% | 0.46% | [−0.78%, 1.03%] |
| +2 | +1.35% | 0.80% | [−0.22%, 2.92%] |
| +3 | +4.73% | 0.87% | [3.02%, 6.43%] |
| +4 | +4.63% | 0.97% | [2.74%, 6.52%] |
| +5 | +7.59% | 1.28% | [5.08%, 10.11%] |

The post-treatment coefficients grow over time and are statistically significant from event time +3 onward. Taken at face value, this suggests a real, growing traffic increase beginning roughly three years after data-center completion. However, the pre-treatment coefficients are **not flat**: event time −5 (−4.75%) and −2 (−1.18%) are also significant and nonzero, which is direct evidence of a pre-existing trend and a violation of DiD's parallel-trends assumption. This means the apparent post-treatment growth cannot be cleanly attributed to treatment; treated segments may simply have been on a different trajectory before treatment as well, for reasons the design does not control for (e.g., broader regional commercial growth that both attracts data centers and independently increases traffic).

**Placebo tests.** Across the 15-segment subset tested, the median p-value is **0.519**, and only **13%** of tested segments achieve p < 0.10 — barely above the ~10% base rate expected under a true null by chance alone. This indicates that, for this subset, SCM's point estimates are largely indistinguishable from the placebo/noise distribution.

**Causal forest.** Across 8,743 segments (1,465 treated, 8 covariate columns), the mean estimated effect is **+34.9 AADT**, but with a standard deviation of **1,209** and an interquartile range of roughly [−0.4, +43.2] AADT — the 95% confidence intervals for most segments include zero (mean CI: [−305.7, +375.4]). With only `road_class` and pre-period AADT level as real covariates, the forest has little to split heterogeneity on beyond noise.

**Cross-method comparison.**

| Method | Estimate | Units | N (segments) | Treat-year window |
|---|---:|---|---:|---|
| Synthetic Control | −24.12 | avg. post-period AADT gap (level) | 1,035 | 2016–2023 |
| Event-study DiD | +0.0296 | avg. post-period log-scale coefficient | all panel-years | 2013–2024 |
| Causal Forest | +34.86 | avg. treatment effect (level AADT delta) | 8,743 | 2013–2024 |

These three numbers are **not directly comparable and should not be averaged**: they differ in units (a level AADT gap vs. a log-scale coefficient vs. a level AADT delta), in which segments and years they are computed over, and in treat-year eligibility window. The table is presented to show the pattern of disagreement across methods, not to produce a single pooled estimate.

## 6. Discussion

No single number from this analysis should be reported as "the" effect of data-center construction on nearby AADT. The four methods disagree in a specific, diagnosable way: DiD suggests a real and growing post-treatment increase, but its own pre-trend diagnostic undermines the causal interpretation of that increase; SCM's central tendency is near zero (median 0.00%) and its own point estimate flips sign depending on aggregation method; placebo tests cannot distinguish the SCM estimates from noise for the large majority of tested segments; and causal forest's mean is small relative to its own variance. Read together, the honest conclusion is that **this pipeline surfaces a plausible positive signal (DiD) that a stricter, assumption-light method (SCM + placebo) does not confirm**, and the most likely explanation is the data limitations discussed below rather than a settled result in either direction.

## 7. Limitations

1. **VDOT's AADT is not a clean annual measurement.** Segments are counted on a rotating multi-year cycle, and off-cycle years often carry forward the prior count rather than a fresh measurement (e.g., the 2025 Loudoun export has AADT values bulk-stamped with a `Data Date` of 2025-01-01 alongside a cluster still dated 2022, and 23% of that file's rows had no AADT value at all). This measurement staleness likely contributes to both the degenerate SCM pre-fits and the DiD pre-trend.
2. **DiD's parallel-trends assumption is violated** in this data, as shown directly by significant pre-treatment event-study coefficients — a finding from running the estimator, not an assumption made in advance.
3. **`zoning` and `pop_density` are unavailable (`NaN`)** for both counties, leaving the causal forest with almost no real covariates to explain heterogeneity beyond `road_class` (94% "Secondary") and pre-period AADT level.
4. **Treatment-year coverage is uneven.** Only 1,379 of 2,888 treated segments fall inside SCM's usable 2016–2023 window; the remainder are tied to anchors as far back as 1986 or as recent as 2026, too old or too recent to contribute a usable pre/post comparison.
5. **Donor-pool overfitting makes SCM's own point estimate unstable**, not merely a pre-fit curiosity: 21.6% of fitted units still show a degenerate pre-period fit despite donor screening, and this instability is directly visible in the level-vs-percentage sign flip described in Section 5. Any single SCM number from this pipeline should be treated as fragile.
6. **The three cross-method point estimates are not on comparable footing** (different units, different segment/year sets, different treat-year windows) and should not be pooled or read as convergent evidence, even though they are presented side by side.

## 8. Future Work

In rough priority order: (a) source real zoning-boundary layers and a Census land-area field for both counties to populate the two placeholder covariates; (b) directly address the DiD pre-trend — e.g., a leads-only pre-trend test, or restricting to segments with flatter pre-trends — rather than reporting the raw post-period coefficients; (c) recover VDOT's true count-year (not just report-year) per segment to build a cleaner "was this segment actually recounted this year" panel; (d) find a covariate that better differentiates segment types than `road_class`, given its 94% imbalance toward "Secondary"; (e) report SCM's post-period effect as a per-segment distribution (median and interquartile range) rather than a single mean, given how sensitive the mean is to a minority of degenerate fits.

## 9. Conclusion

Using VDOT's public AADT panel and real data-center completion records from both Loudoun and Prince William Counties, we do not find a robust, cross-method-confirmed effect of data-center construction on nearby road traffic. This is a substantive finding in its own right: claims that data-center construction obviously and measurably worsens nearby traffic are not currently supported by rigorous causal analysis of the available public data, and the specific ways our four methods disagree point to concrete, fixable limitations in current traffic-count infrastructure and data-center permit record-keeping — an open problem worth further investigation rather than a closed question in either direction.

## References

Abadie, A., Diamond, A., & Hainmueller, J. (2010). Synthetic Control Methods for Comparative Case Studies: Estimating the Effect of California's Tobacco Control Program. *Journal of the American Statistical Association*, 105(490), 493–505. https://doi.org/10.1198/jasa.2009.ap08746

Abadie, A. (2021). Using Synthetic Controls: Feasibility, Data Requirements, and Methodological Aspects. *Journal of Economic Literature*, 59(2), 391–425. https://doi.org/10.1257/jel.20191450

Goodman-Bacon, A. (2021). Difference-in-Differences with Variation in Treatment Timing. *Journal of Econometrics*, 225(2), 254–277. https://doi.org/10.1016/j.jeconom.2021.03.014

Wager, S., & Athey, S. (2018). Estimation and Inference of Heterogeneous Treatment Effects using Random Forests. *Journal of the American Statistical Association*, 113(523), 1228–1242. https://doi.org/10.1080/01621459.2017.1319839

Kittelson & Associates, Inc. Why Data Centers Don't Fit Standard Traffic Assumptions—and How to Plan for Their Transportation Impacts. https://www.kittelson.com/ideas/why-data-centers-dont-fit-standard-traffic-assumptions-and-how-to-plan-for-their-transportation-impacts/

Wells + Associates. Data Center Traffic Impact Studies and Transportation Analyses. https://www.wellsandassociates.com/data-centers/

Frontiers in Climate (2026). Health implications of the rapid rise of data centers in Virginia: an exploratory assessment. https://www.frontiersin.org/journals/climate/articles/10.3389/fclim.2026.1648912/full

Virginia Department of Transportation. Traffic Counts Data Description. https://www.vdot.virginia.gov/doing-business/technical-guidance-and-support/traffic-operations/traffic-counts/description/

**Data sources:** VDOT Annual Average Daily Traffic exports, 2011–2025 (`Datasets_2011_til_2025/`); Prince William County GIS Open Data, Data Center Buildings layer (`External_Data/pwc_data_center_buildings.geojson`); Loudoun County GIS, `Existing_Permitted_Data_Center_Buildings` ArcGIS FeatureServer layer (`External_Data/loudoun_data_center_buildings.xlsx`); VDOT route geometry, Virginia GIS Clearinghouse (`External_Data/vdot_routes.geojson`).
