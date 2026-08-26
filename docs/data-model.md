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
databases gain nullable provenance columns without changing older rows. Schema
changes and their version marker are committed atomically; a database marked with
a newer schema version is rejected instead of being changed by older code. Write
batches acquire the SQLite write reservation before checking replay identities so
concurrent retry processes cannot race between conflict detection and insertion.
When a provider point lacks an explicit observation name, generated identity
includes platform, recording method, canonical device identity, and absolute
interval so otherwise identical observations from different devices cannot
collide.

## Sleep score records

Separate immutable records for Efficiency, Recovery, and predicted Energy are
implemented. Each contains a 0–100 value, independent 0–1 confidence and
completeness values, present inputs with units and provider-qualified source
observation references, missing inputs, limitations, evidence, algorithm version,
calibration revision, and an offset-aware calculation time. Only these three score
types are accepted; there is no overall composite. Writes are transactional and
idempotent by score identifier, and conflicting replays roll back.

The contracts intentionally contain no scoring formulas or weights until provider
fields and algorithm choices have been verified. Energy records identify a
prediction and do not contain later survey outcomes.

Daily feedback records are also implemented. They reference a previously stored
predicted Energy score and contain a local date, IANA timezone, offset-aware
submission time, and nullable 1–10 perceived energy, perceived recovery, and sleep
quality fields plus a nullable note. All optional fields may remain `NULL`. A
database gate enforces prediction-before-feedback and one feedback record per
Energy prediction; stored feedback cannot be updated in place.

Nightly scoring contexts are implemented without introducing a composite score.
Each immutable context records the local sleep date, IANA timezone, offset-aware
sleep-window boundaries, the cutoff for included input data, and distinct
Efficiency, Recovery, and predicted Energy score identifiers. The window offsets
must agree with the timezone across DST, the date must match the local window end,
and each score must exist with the expected type and a calculation time at or
after the cutoff. A score snapshot can belong to only one context. Feedback must
match the linked context's date and timezone.

## Planned records

The following contracts are designed but not implemented:

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
