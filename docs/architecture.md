# Architecture

## Purpose and current boundary

The system supports a prospective single-person comparison of historical
baselines, Google Health Premium output, personal models, and hybrid models for
readiness and energy.

The repository currently implements synthetic ingestion, canonical storage,
heuristic scoring, validated study records, deterministic fixtures, experiment
interfaces, rolling-origin evaluation, and a static phone-form prototype. It does
not implement live collection, private study persistence, trained personal
models, or a production service.

## Logical flow

```text
private metrics, provider output, and check-ins
                 |
                 v
source-specific adapters
                 |
                 v
canonical observations and capture provenance
                 |
                 v
cutoff-safe feature snapshot
       |            |             |
       v            v             v
historical       personal       hybrid
baseline          model          model
       \            |             /
        +------ immutable predictions
                       |
                       v
              later personal labels
                       |
                       v
             rolling-origin evaluation
```

Optional presentation and coaching consume stored predictions after they are
fixed. They cannot redefine a target or rewrite a past result.

## Components

### Canonical observation foundation

`MetricObservation` and `ObservationStore` preserve provider identity, units,
missingness, timestamps, timezone, device provenance, transactions, conflict
detection, and idempotent replay. Existing deterministic sleep scores remain
separate, versioned baselines or candidate features.

### Study records

`study_protocol.py` defines event-relative configuration and validated personal
labels, context, provider exposure, and Coach insight provenance. A later
persistence layer should store these records without changing their meanings.

### Capture adapters

`import_adapters.py` defines an opaque source artifact, normalized import batch,
and a registry that accepts exactly one matching adapter. Final Google export,
screenshot, emulator, and API formats are deliberately unspecified until observed
and verified.

A Premium item must remain classified as an original insight, retrieved
historical insight, or later reconstruction.

### Evaluation

`evaluation.py` implements historical and provider comparison arms,
ML-library-neutral personal and hybrid interfaces, rolling-origin splits,
temporal-leakage checks, and the initial metrics.

The first trained personal model is planned as elastic-net regression. Feature
generation, imputation, scaling, selection, and tuning must be fitted inside each
training window.

### Synthetic demonstration

`synthetic_study.py` generates fictional irregular wake times, measurements,
context, provider scores, and targets. The checked-in CSV and Coach screenshots
exercise public demos without exposing a real person. The static phone form has no
backend or persistence.

## Time and leakage

Three times remain distinct:

- `observed_at`: when a state or event applied;
- `available_at`: when it could first be used; and
- `captured_at`: when it entered storage.

A feature or provider output is eligible only when available by the prediction
cutoff. A late label keeps both the interval it describes and its actual capture
time. A retrospective Coach answer cannot be treated as the message available on
the original day.

## Storage and versioning

SQLite is the initial canonical store. Predictions and later evaluations should
reference immutable source, feature, model, target, and protocol versions rather
than recalculating history in place.

Version independently:

- capture adapter and schema;
- target prompt and anchors;
- feature pipeline;
- model and training window; and
- evaluation protocol.

## Public and private execution

The public checkout contains code and fictional fixtures only. Real exports,
screenshots, labels, credentials, databases, trained artifacts, and row-level
results remain in a separate private location.

A real form, emulator, OAuth integration, hosted service, or AI provider creates
a new trust boundary requiring explicit configuration and review. The static form
in this repository proves layout only, not production security.
