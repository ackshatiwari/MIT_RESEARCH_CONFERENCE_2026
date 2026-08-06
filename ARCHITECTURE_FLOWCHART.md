# Architecture — Event-Study DiD & Causal Forest

Pipeline for the two estimators used in this study. Shapes are annotated on the
edges in `(rows, cols)` form, following the tensor-shape convention.

---

## Full Pipeline

```mermaid
flowchart TB

%% ============ 1. INPUT LAYER ============
subgraph S1["1 &middot; Input Layer"]
  direction LR
  A1["VDOT AADT Exports<br/><i>30 files &middot; 3 schemas &middot; 2011&ndash;2025</i>"]
  A2["Data-Center Permits<br/><i>PWC GeoJSON + Loudoun XLSX</i>"]
  A3["VDOT Route Geometry<br/><i>vdot_routes.geojson</i>"]
end

%% ============ 2. PANEL CONSTRUCTION ============
subgraph S2["2 &middot; Panel Construction &nbsp;<i>(shared by both models)</i>"]
  direction TB
  B1["Multi-Schema Loader<br/>normalize &rarr; segment_id, aadt, year"]
  B2["Dedupe on (segment_id, year)<br/><i>&minus;2,654 rows</i>"]
  B3["Route-Name Crosswalk<br/><i>10,502 / 10,723 segments</i>"]
  B4["Spatial Join &mdash; flat-earth miles<br/><i>228 anchors &middot; radius 1.5 mi</i>"]
  B5["Tidy Long Panel<br/><b>validate_panel()</b>"]
  B1 --> B2 --> B3 --> B4 --> B5
end

%% ============ 3. ESTIMATORS ============
subgraph S3["3 &middot; Estimators &nbsp;<i>(independent, same input)</i>"]
  direction LR

  subgraph D["3a &middot; Event-Study DiD &nbsp;<code>03_event_study_did.py</code>"]
    direction TB
    D1["Filter aadt &gt; 0<br/>outcome = log(aadt)"]
    D2["Restrict treat_year &isin; [2013, 2024]"]
    D3["build_event_time()<br/>k = year &minus; treat_year, clipped [&minus;5, +5]"]
    D4["Event Dummies<br/><i>10 cols &middot; k =&minus;1 omitted as reference</i>"]
    D5["_iterative_demean()<br/><i>absorbs segment + year FE</i>"]
    D6["OLS &middot; SE clustered by segment_id"]
    D1 --> D2 --> D3 --> D4 --> D5 --> D6
  end

  subgraph C["3b &middot; Causal Forest &nbsp;<code>05_causal_forest.py</code>"]
    direction TB
    C1["Restrict treat_year &isin; [2013, 2024]"]
    C2["Collapse panel &rarr; 1 row / segment<br/><i>ref year = median treat_year</i>"]
    C3["Y = post-mean &minus; pre-mean AADT<br/>T = treated 0/1 &nbsp;&middot;&nbsp; X = covariates"]
    C4["CausalForestDML<br/><i>300 trees &middot; RF nuisance models</i>"]
    C5["effect() + effect_interval()<br/><i>&alpha; = 0.10</i>"]
    C1 --> C2 --> C3 --> C4 --> C5
  end
end

%% ============ 4. OUTPUTS ============
subgraph S4["4 &middot; Outputs"]
  direction LR
  E1["Event-Study Coefficients<br/><b>+4.7% at k=3 &middot; +7.6% at k=5</b><br/><i>pre-trend at k = &minus;5, &minus;4, &minus;2</i>"]
  E2["Per-Segment CATEs<br/><b>mean +34.9 AADT &middot; sd 1,209</b><br/><i>intervals mostly span zero</i>"]
end

%% ============ WIRING ============
A1 -- "137,904 rows" --> B1
A2 --> B4
A3 --> B3

B5 -- "(135,250, 9)" --> D1
B5 -- "(135,250, 9)" --> C1

D6 -- "(11, 5)" --> E1
C5 -- "(8,743, 4)" --> E2

%% ============ STYLE ============
classDef inp    fill:#f8d7da,stroke:#c96,stroke-width:1px,color:#000
classDef panel  fill:#d4edda,stroke:#6a9,stroke-width:1px,color:#000
classDef did    fill:#cfe2f3,stroke:#69c,stroke-width:1px,color:#000
classDef forest fill:#e2d4f0,stroke:#96c,stroke-width:1px,color:#000
classDef out    fill:#ffffff,stroke:#333,stroke-width:2px,color:#000

class A1,A2,A3 inp
class B1,B2,B3,B4,B5 panel
class D1,D2,D3,D4,D5,D6 did
class C1,C2,C3,C4,C5 forest
class E1,E2 out
```

---

## Shape Reference

| Stage | Object | Shape | Note |
|---|---|---|---|
| 1 | Raw AADT rows | `(137,904, 5)` | 30 files, 3 schemas |
| 2 | After dedupe | `(135,250, 5)` | 2,654 exact duplicates removed |
| 2 | **Tidy panel** | `(135,250, 9)` | `PANEL_COLUMNS` contract |
| 3a | DiD design matrix | `(n, 10)` | 10 event dummies, `k=−1` omitted |
| 3a | Coefficient table | `(11, 5)` | `event_time, coef, se, ci_low, ci_high` |
| 3b | Collapsed units | `(8,743, 8)` | 1,465 treated · 8 covariate cols |
| 3b | CATE table | `(8,743, 4)` | `segment_id, effect, ci_low, ci_high` |

---

## Why Two Estimators

Both consume the identical panel but make **different assumptions**, so agreement
would be evidence and disagreement localizes which assumption fails.

| | Event-Study DiD | Causal Forest |
|---|---|---|
| **Question** | Average effect over time, relative to opening | Does the effect vary by road? |
| **Unit of analysis** | Segment × year (full panel) | One row per segment |
| **Key assumption** | Parallel trends | Unconfoundedness given `X` |
| **Built-in check** | Pre-period coefficients (`k < 0`) | Confidence intervals per unit |
| **Time structure** | Preserved (event time) | Collapsed to pre/post delta |
| **Outcome scale** | log AADT → percent | Δ AADT → level |

---

## Known Structural Caveats

Design characteristics visible in the flowchart itself, not defects discovered later:

1. **Shared reference year (3b, C2).** Control segments have no `treat_year`, so
   the causal forest needs one common pre/post split point. Treated segments whose
   actual `treat_year` is far from the median get a mismatched window.
2. **Staggered adoption (3a).** Treatment years span 2013–2024 under two-way FE,
   so already-treated units act as controls — the Goodman-Bacon / Callaway–Sant'Anna
   concern. A heterogeneity-robust estimator is the natural next step.
3. **Endpoint binning (3a, D3).** `clip` collapses every lead ≤ −5 into the `k=−5`
   coefficient, so that bin is stacked rather than a clean single-year estimate.
4. **Covariate sparsity (3b, C3).** `zoning` and `pop_density` are unavailable
   panel-wide, and `road_class` is 94% "Secondary" — the forest has little to split on.
5. **Route-level treatment (2, B4).** Distance is measured anchor → route polyline,
   and all segments on a route inherit the flag. Median VDOT route in the study area
   is **0.17 mi** (95th pct 1.42 mi), so this closely approximates segment-level
   assignment in practice.
