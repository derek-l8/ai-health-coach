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

- `EventConfiguration`: wake-relative or manual capture windows;
- `PersonalLabel`: one target rating, prompt version, status, and timing;
- `ContextObservation`: nullable potential confounders;
- `PredictionExposure`: whether provider guidance was seen or acted on; and
- `CoachInsight`: provider, interval, availability, origin, and text fidelity.

SQLite persistence for these records remains planned.

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
- `captured_at`: when the private runtime stored it.

A model can use only values available by its prediction cutoff. A label captured
late retains both its target interval and capture delay.

## Missingness and completeness

Missing, skipped, not applicable, late, and zero are distinct states.
Completeness is target-specific: a day missing afternoon energy may still be
eligible for morning readiness.

Partial days remain stored and are excluded only by a versioned evaluation rule.

## History and persistence gap

Source records, labels, predictions, and evaluations are append-only. Corrections
should create linked replacements rather than mutate history. New adapters,
prompts, features, or models start new versions.

The next storage task is to persist study and evaluation identities without
weakening the existing transaction, replay, provenance, and timing guarantees.
