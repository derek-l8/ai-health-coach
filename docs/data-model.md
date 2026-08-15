# Canonical observation data model

`MetricObservation` records provider source and observation identity, metric type,
offset-aware interval boundaries, nullable numeric value and unit, IANA timezone,
quality status, platform, recording method, device manufacturer, and device display
name. Missing is stored as `NULL`, never as an empty string or zero. Timestamp
offsets must agree with the named timezone at each instant, including DST
transitions. Blank device metadata is rejected.

`ObservationStore` writes a batch in one SQLite transaction. The pair `(source,
source_observation_id)` is unique. Exact replays are no-ops; a replay with any
different canonical field raises a conflict and rolls back the batch. Existing
databases gain nullable provenance columns without changing older rows. When a
provider point lacks an explicit observation name, generated identity includes
platform, recording method, canonical device identity, and absolute interval so
otherwise identical observations from different devices cannot collide.

## Planned records

The following contracts are designed but not implemented:

- Separate immutable score records for Efficiency, Recovery, and predicted Energy,
  each with value, confidence, completeness, inputs, missing inputs, limitations,
  evidence, algorithm version, calibration revision, and calculation time.
- An optional daily survey with nullable 1–10 perceived energy, perceived
  recovery, and overall sleep quality plus a nullable note. Every field is
  skippable. The observed survey is stored separately and never overwrites the
  earlier Energy prediction.
- Comparison observations for provider-owned scores such as Fitbit Sleep Score or
  Readiness, identified as external comparisons rather than application truth.
- One canonical daily report per `(local_date, pipeline_version)`, with resumable
  stage status and distinct deterministic, coaching-request, and coaching-response
  identities.
- Immutable report snapshots containing the exact three displayed scores, source
  and completeness data, all algorithm and calibration revisions, prompt and
  runner versions, actual provider/model identifier, request and application
  versions, parent revision, activation timestamp, timezone, and provenance.
- Inspectable goals, confirmed or rejected observations, preferences, coaching
  interactions, feedback, calibration proposals, validations, activations,
  rollbacks, and revision history.

Historical report snapshots are append-only. New algorithm or calibration
versions do not update them. Corrected source observations create explicit new
calculations or later comparisons rather than rewriting what was originally shown.
