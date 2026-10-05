# Data model

The model separates measurements, provider output, predictions, and later
self-reports. It also preserves when each value occurred, became available, and
was captured.

## Canonical observations

`MetricObservation` is implemented and persisted in SQLite. It records:

- provider and source observation identity;
- metric type and offset-aware interval;
- nullable numeric value and unit;
- IANA timezone and quality status; and
- platform, recording method, and device provenance.

Missing is `NULL`, never zero or an empty string. Timestamp offsets must agree
with the named timezone, including DST transitions.

`ObservationStore` writes batches transactionally. Exact replays are no-ops; a
changed payload under the same source identity is a conflict and rolls back the
batch. Schema versions are committed atomically and newer unknown schemas are
rejected.

## Existing sleep records

Immutable SQLite records are implemented for:

- separate Efficiency, Recovery, and predicted Energy snapshots;
- the exact inputs, missing inputs, evidence, confidence, and versions used;
- nightly contexts with sleep window and input cutoff;
- later optional daily feedback; and
- provider-owned comparison scores.

These records are an engineering foundation. Their heuristic values are not the
new study targets or trained personal models.

## Study records

Validated in-memory contracts are implemented for:

- `EventConfiguration`: wake-relative or manual capture windows and an optional
  study-local caffeine cutoff;
- `PersonalLabel`: one target rating, prompt version, status, and timing;
- `ContextObservation`: nullable potential confounders;
- `PredictionExposure`: whether provider guidance was seen or acted on; and
- `CoachInsight`: provider, interval, availability, origin, and text fidelity.

`CheckInStore` persists each submitted label, context, and Google exposure together
in a separate private SQLite database. Each append-only envelope includes a UUID,
the exact event-configuration identity, optional wake timestamp and note, capture
delay, a user-reported lateness flag, and a computed event-window status. A missing
wake time produces `unanchored`, rather than an invented wake time. The original
configuration remains stored when later service runs use different boundaries.

The optional `caffeine_cutoff_local_time` uses 24-hour `HH:MM` in the configuration's
IANA timezone. A non-null caffeine answer requires this field. Earlier stored
configurations remain unchanged; if they lack a cutoff, their caffeine answers
have an unknown threshold and must not be treated as equivalent to defined ones.

The server assigns `captured_at`. The submitted `observed_at` is normalized to the
configured IANA timezone. `available_at` for the captured envelope is its capture
time, including when a rating describes an earlier event. Context and exposure
must not become model inputs before that time.

An exact retry preserves its first capture timestamp and inserts nothing. Changed
content under the same UUID is a conflict. Configuration and envelope insertion
are transactional; update and delete triggers protect existing records. Separate
ratings may be recorded for the same event without silently replacing history.

Coach insight and prediction persistence remain planned. The check-in database
does not alter the older `ObservationStore` schema.

### Forms snapshot import

The implemented version-1 snapshot contract is defined by
`scripts/google-forms-study.js` and `forms_import.py`. It is this project's format,
not an assumed Google Health export. It contains a Form ID, export time, frozen
configuration, and responses with native response IDs, submission timestamps,
and mapped answers. Public examples use fictional IDs and values.

Google submission time supplies `captured_at`; an optional earlier event time
supplies `observed_at`, otherwise it equals submission. Imported labels use
`capture_method=google_form`. `available_at` and `imported_at` equal the first
local import, not the historical submission; context cannot be used in an earlier
prediction merely because a later import describes that day. Capture delay and
import delay are stored separately. Window timing uses the submission instant.

A UUID derived from the Form/response ID pair identifies each envelope. The
importer binds each Form to one configuration and rejects changed answers or
definitions. Exact snapshot bytes and SHA-256, first import time, and all
snapshot-to-check-in links are stored in immutable supplementary tables. The
entire batch rolls back on invalid data or conflicts. Later exports can add
responses or omit rows without deleting previously imported history. Editing
the response Sheet does not edit the Form response store.

## Evaluation records

Implemented evaluation contracts include:

- `FeatureValue`: numeric value plus availability time;
- `LabeledExample`: target, cutoff-safe inputs, provider output, and later
  outcome;
- `Prediction`: immutable arm prediction and observed value;
- `RollingOriginSplit`: eligible historical training rows and the next test
  example;
- `CalibrationBin` and `MetricReport`: metrics with sample count and coverage.

Personal and hybrid trainers use protocols so a later modeling library can be
replaced without changing evaluation semantics.

## Time semantics

When applicable, preserve:

- `observed_at`: when the event or state occurred;
- `available_at`: when it could first influence a prediction; and
- `captured_at`: when the source recorded it; and
- `imported_at`: when a Forms snapshot entered the private runtime.

A model can use only values available by its prediction cutoff. A label captured
late retains both its target interval and capture delay.

## Missingness and completeness

Missing, skipped, not applicable, late, and zero are distinct states.
Completeness is target-specific: a day missing afternoon energy may still be
eligible for morning readiness.

Partial days remain stored and are excluded only by a versioned evaluation rule.

## History and remaining persistence work

Source records, labels, predictions, and evaluations are append-only. Corrections
should create linked replacements rather than mutate history. New adapters,
prompts, features, or models start new versions.

The next storage task is to persist provider insight and evaluation identities without
weakening the existing transaction, replay, provenance, and timing guarantees.
