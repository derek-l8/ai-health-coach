# Architecture

## Purpose and current boundary

The system supports a prospective single-person comparison of historical
baselines, Google Health Premium output, personal models, and hybrid models for
readiness and energy.

The repository currently implements synthetic ingestion, canonical storage,
heuristic scoring, validated study records, deterministic fixtures, experiment
interfaces, rolling-origin evaluation, Google Forms setup/export and private snapshot
import, an optional local check-in service, and a static
synthetic phone-form prototype. It does not implement live Google Health collection,
trained personal models, or public hosting.

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
labels, context, provider exposure, and Coach insight provenance. `checkins.py`
persists check-in envelopes and configuration snapshots transactionally, with
immutable records and exact-retry handling. Coach insight storage remains planned.

The primary daily capture route is Google Forms, linked to a private response
Sheet. `scripts/google-forms-study.js` creates an unpublished Form and private
Drive folders when the user runs and authorizes it. It freezes configuration and
item identities, and exports the native Form response store into a repo-defined
JSON snapshot. Google-side execution and iPhone access still require a real pilot;
tests use mocked services, not a live account.

`forms_import.py` validates those snapshots and appends to `CheckInStore` in one
transaction. Stable Form/response IDs identify retries. Exact source bytes and
configuration bindings remain private and immutable. Submission time records
source capture; first local import determines conservative pipeline availability.
The response Sheet is a live view, not a CSV ingestion contract. No background
Drive sync or screenshot parsing is implemented.

`checkin_server.py` serves the packaged mobile page and validates submissions.
It binds loopback by default. An explicit private IPv4 address requires HTTPS.
Each running session has a random bearer token; API requests check both the token
and browser origin. Host validation, bounded JSON requests, fixed asset routes,
no-store responses, and suppressed request logs reduce the capture service's
exposure. It has no private-history endpoint or provider connection.

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

Google Forms uses Google account permissions and cloud storage. The user reviews
scopes and responder access before using the Form. Code changes do not authorize
publishing health data. Optional local phone-network access requires a certificate
trusted by the phone and deliberate network configuration. The service is a
single-user collection tool, not a public
deployment. Emulator capture, OAuth integration, hosted services, or an AI provider
need their own configuration and review. The standalone synthetic form demonstrates
layout only.
