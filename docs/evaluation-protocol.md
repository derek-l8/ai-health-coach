# Evaluation protocol

- Status: synthetic evaluation utilities implemented; protocol not yet frozen
- Protocol version: 0.1.0
- Scope: prospective single-person prediction comparison

## Research questions

Primary question:

> Can a transparent model trained on longitudinal Fitbit/Google Health data and
> self-reports predict morning readiness, afternoon energy, or overall energy
> better than a simple historical baseline for this user?

Secondary questions:

1. How does eligible Google Health Premium output compare on the same target and
   horizon?
2. Does adding eligible Google output to the personal model improve prospective
   performance?
3. How much do missing data, late capture, and seeing or acting on Google guidance
   change the result?

The study does not test medical validity or population-level performance.

## Targets and prediction horizons

Evaluate each target separately under the definitions in
[data-collection-protocol.md](data-collection-protocol.md):

- morning readiness, predicted after eligible sleep data is available;
- afternoon energy, predicted that morning for the configured afternoon window;
- overall energy, predicted that morning for the full day; and
- optional next-day energy, predicted the night before as a secondary,
  higher-uncertainty task.

A model is not credited with a prediction created after the target window begins
unless that horizon is explicitly evaluated as a different task.

## Comparison arms

### Historical baseline

Use a rolling median of earlier eligible labels as the minimum baseline. Other
simple baselines, such as last observation or day-of-week median, may be added but
cannot replace the minimum baseline after results are seen.

### Google comparison

Use a Google numeric output only when its target, scale, availability time, and
horizon can be mapped defensibly to the personal target. Preserve the original
provider value and document any transformation.

Qualitative guidance is not forced into a numeric MAE comparison. It may instead
be evaluated on pre-defined ordinal direction, coverage, or decision usefulness,
clearly separated from numeric prediction performance.

### Personal raw-data model

The initial model is elastic-net regression using eligible raw measurements,
lagged values, rolling summaries, missingness indicators, and the compact context
fields. Build one model per target.

### Hybrid model

Use the same pipeline as the personal model and add only Google output available
by the prediction cutoff. The difference between hybrid and raw-data performance
estimates the incremental predictive value of captured Google output; it does not
identify Google's internal causal contribution.

## Data gates

- Days 1-20 are descriptive and used to debug collection.
- Exploratory associations may begin after 21 complete labels for a target.
- Initial model fitting begins after 60 complete labels for that target.
- A preliminary prospective claim requires at least 14 later eligible
  predictions.
- Stronger conclusions should wait for 90-180 days and meaningful coverage of
  schedule variation.

Exploratory analysis must not silently redefine the frozen target, anchors,
feature set, primary metric, or claim threshold.

## Split and training procedure

Use expanding-window rolling-origin evaluation:

1. sort eligible records by target time;
2. train only on earlier records;
3. fit preprocessing and hyperparameters inside the training window;
4. create the next prediction before its outcome is known;
5. retain the immutable prediction; and
6. advance the window and repeat.

Do not randomize days across train and test sets. Lagged and rolling features must
exclude the current and future outcome. Closely related repeated predictions for
one target window are either prevented or grouped so they cannot inflate sample
size.

A weekly retraining cadence is a starting choice, not a requirement. Record the
actual training cutoff and use the prior active model between retraining events.

## Metrics

Primary metric:

- **Mean absolute error (MAE)** on the 1-10 target scale.

Supporting metrics:

- median absolute error;
- fraction within one rating point;
- Spearman rank correlation, with uncertainty;
- prediction coverage;
- calibration by predicted range;
- bias, including mean signed error; and
- performance by target, missingness, exposure state, and major schedule context.

Report sample count and eligible coverage beside every metric. Do not compare
metrics calculated on materially different subsets without also reporting the
common-subset result.

## Preliminary claim rule

A personal model is a preliminary improvement only when:

- it has at least 14 prospective held-out predictions;
- its MAE is at least 10% lower than the rolling-median baseline on the common
  eligible set;
- the direction is not explained by one or two obvious outliers;
- uncertainty and coverage are reported; and
- no material leakage or protocol violation is found.

This threshold is a working decision rule, not statistical proof. Use a
time-aware or block bootstrap when reporting an interval, and show the paired
per-day error difference. If the interval is too wide to distinguish the models,
the result is inconclusive.

A claim that the hybrid adds value requires comparison with the personal
raw-data model on the same eligible days. A claim about Google requires comparable
target and horizon; otherwise report a descriptive comparison only.

## Missingness and exposure analyses

Run at least these sensitivity checks:

- complete target days only;
- all eligible days supported by each arm;
- common days shared by all compared arms;
- labels submitted before Google guidance was seen;
- guidance seen before labeling;
- recommendation acted on vs. not acted on;
- on-time vs. late labels; and
- major collection-protocol versions.

Missing values may be imputed only inside the training window, with missingness
indicators when appropriate. Do not use future values to fill earlier gaps.

## Result artifact

A versioned result report includes:

- target and horizon;
- protocol and label-anchor versions;
- eligible date range and split boundaries;
- exact model and feature-pipeline versions;
- sample count, coverage, and missingness;
- metrics with uncertainty;
- paired error plot or table;
- exposure sensitivity;
- important failure cases;
- deviations from the protocol; and
- a conclusion of improvement, no improvement, or inconclusive.

Public reports use reviewed aggregate or synthetic data only. Private row-level
predictions and labels remain outside Git.

## Interpretation limits

A successful result means one model predicted one person's defined ratings better
over the observed period. It does not prove clinical benefit, causal effects,
generalization to other people, or superiority over Google Health Premium as a
whole.
