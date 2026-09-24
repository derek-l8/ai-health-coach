# Data-collection protocol

- Status: synthetic contracts implemented; private collection not started
- Protocol version: 0.1.0
- Scope: prospective single-person wellness study

This protocol defines the minimum records needed to compare a historical
baseline, Google Health Premium, a personal raw-data model, and a hybrid model.
It is intentionally tolerant of inconsistent participation.

## Collection events

The interface uses configurable events, not fixed clock times.

### Wake event

Collect after waking and, when practical, after the night's sleep metrics are
available:

- morning readiness rating;
- whether Google readiness or guidance was already seen;
- whether any seen recommendation is expected to be followed;
- illness state;
- academic stress;
- exam or deadline within 48 hours;
- medication changed or missed, only when applicable;
- unusual sleep circumstances; and
- an optional short note.

### Afternoon event

Collect current afternoon energy during a user-configurable window. Preserve the
window and actual response time. A late response is accepted and marked late.

### Day-close event

Collect overall energy for the day, final recommendation-action state, and an
optional short note. A note may be invited every other day, but is never required
for a day to be usable.

Exercise may be derived from device data when available. Otherwise record
`none`, `light`, `moderate`, `hard`, or missing. Also capture caffeine
after the configured cutoff, alcohol as `none`, `one`, or `two_or_more`,
and unusual circumstances when known.

## Label definitions

Each rating uses an integer from 1 to 10. The prompt and anchors are versioned;
changing them starts a new protocol version.

### Morning readiness

Prompt: **How capable do I feel of handling the demands planned for today?**

- **1:** unable to handle ordinary planned demands;
- **5:** able to handle essential demands, but only with noticeable effort or
  reduction; and
- **10:** fully capable of handling a highly demanding day.

### Afternoon energy

Prompt: **How alert and energized do I feel right now?**

- **1:** barely able to stay alert or complete basic tasks;
- **5:** enough energy for routine work, with clear dips or effort; and
- **10:** sustained, unusually high alertness and usable energy.

### Overall energy

Prompt: **Looking back, how much usable energy did I have across the day?**

- **1:** almost no usable energy across the day;
- **5:** enough for essential tasks, but limited or inconsistent; and
- **10:** abundant, sustained usable energy across the day.

Intermediate ratings are judgments between the anchors. Readiness and energy are
not interchangeable: readiness incorporates the day's expected demands; energy
describes alertness and usable capacity.

## Timing and leakage fields

Every record preserves:

- the local date and IANA timezone;
- the interval or event being described;
- `observed_at`, when the state applied;
- `available_at`, when a source value became visible;
- `captured_at`, when it was stored;
- capture method and schema version; and
- whether it was on time, late, skipped, or missing.

A model may use only data whose `available_at` is no later than its prediction
cutoff. A later reconstruction of a Google insight cannot be used as if it had
been available that morning.

## Provider exposure

For each target, record:

- `google_seen_before_label`: `yes`, `no`, or `unsure`;
- `recommendation_acted_on`: `no`, `partly`, `yes`, or `unknown`;
- output type and target/horizon, when known; and
- when the output first became available and when it was captured.

The protocol does not require the user to avoid Google guidance. Exposure is a
real part of the system and becomes a stratification or sensitivity variable.

## Premium insight provenance

Classify captured text as:

- `original_insight`: the message presented at the relevant time;
- `historical_insight`: a stored past message retrieved later; or
- `reconstructed_insight`: a new answer generated later about an earlier
  period.

Also record whether the text is exact, transcribed, summarized, or parsed. Keep
the screenshot or source artifact private.

## Missing and partial days

Prompts may be missed. Do not backfill a rating by pretending it was observed on
time. A late rating is allowed when the described interval is still clear, but
the delay is retained.

Completeness is target-specific. For example, a day can be eligible for morning
readiness analysis even if afternoon energy is missing. Partial days remain in
storage and are excluded only by an explicit evaluation rule.

A **complete labeled day** for a target contains:

- a valid target rating;
- valid observed and capture timing;
- a provider-exposure record, including `unsure` when necessary; and
- the minimum feature-availability record required by that model arm.

## Collection phases

- **Days 1-20:** debug prompts, timing, missingness, and source mappings. Report
  descriptions only.
- **After 21 complete target labels:** allow exploratory plots and associations.
- **After 60 complete target labels:** freeze the first training protocol and fit
  the initial personal models.
- **After at least 14 later predictions:** permit a preliminary held-out
  comparison.
- **90-180 days:** preferred range for more stable conclusions.

Calendar days and complete labeled days are reported separately. Reaching a
calendar date never substitutes for the label-count gate.

## Optional future interventions

Controlled caffeine, exercise, bedtime, or workload experiments are not required
for the initial study. If later added, each intervention needs its own
pre-registered schedule, adherence field, safety review, and analysis. Ordinary
behavioral variation must not be mislabeled as randomized evidence.
