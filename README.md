# Personal AI Health Coach

Personal AI Health Coach is an open-source, local-first project for people who
want control of their health data and increasingly personalized insight from it.
The target application runs on one Windows computer. Its backend and scheduled
pipeline work independently of the browser, while a responsive local web
dashboard presents explainable calculations and AI-assisted wellness coaching.
It is not a diagnostic device, emergency monitor, or source of emergency care.

## Implemented today

- Strict validation and normalization of a narrow, synthetic Google Health
  steps-response shape.
- Canonical SQLite observation storage with provenance, units, offset-aware
  timestamps, IANA timezones, DST checks, explicit missingness, atomic batches,
  conflict detection, and idempotent replay.
- Formula-neutral immutable contracts and transactional persistence for separate
  Efficiency, Recovery, and predicted Energy score snapshots, including source
  evidence, missing inputs, confidence, completeness, and version provenance.
- Immutable daily feedback with nullable 1–10 ratings, timezone-aware submission
  context, and a database-enforced prediction-before-feedback relationship.
- Immutable nightly scoring contexts preserving separate score identities, local
  date, DST-valid sleep windows, and the input cutoff used for late-arrival safety.
- Synthetic fixtures, automated regression tests, and a synthetic smoke command.

No sleep formulas are implemented, no live health data is collected, no web
dashboard is served, and no AI model is called by this version. The current code
is the reliable data foundation, not a finished health application.

## Requirements

- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/)

```bash
uv sync --dev --frozen
uv run ai-health-coach --synthetic-smoke
uv run pytest
```

## Planned

The first useful release is planned as a single-user Windows application with:

- Google Health OAuth collection for a Google Fitbit Air.
- A local browser dashboard showing today's results and longer-term trends.
- Three separate, versioned sleep scores: Efficiency, Recovery, and predicted
  Energy. They are never collapsed into one overall score.
- Confidence levels that identify available and missing inputs.
- An optional, skippable daily survey stored separately from the earlier Energy
  prediction.
- Codex-first coaching informed by inspectable personal history, baselines,
  goals, check-ins, and feedback—not opaque model memory.
- Separate, persistent, revocable consent for Google access and AI processing.
- A daily non-interactive run suitable for Windows Task Scheduler.
- Up-to-30-day raw-response retention, a seven-day deletion undo window,
  complete export, and planned encrypted local backups.

The intended runtime flow is:

```text
Google Fitbit Air through the Google Health API
  -> trusted local application runtime
  -> protected local storage
  -> deterministic health modules
  -> subscription-authenticated Codex coaching process
  -> stored coaching report
  -> responsive local web dashboard
```

Runtime OAuth and Codex authentication stay outside Git. Private coaching must
run in a distinct trusted or isolated runtime. Autonomous Codex development takes
place in a separately configured disposable sandbox outside this repository,
using public code and synthetic data only. The included devcontainer is only a
reproducible Python development environment. Routine coaching receives a bounded
read-only packet and cannot edit code or activate algorithm changes.

Current OpenAI documentation does not prove that personal-subscription Codex can
run reliably unattended from Windows Task Scheduler. That path requires a manual
live proof-of-concept. No API-key billing fallback is assumed. Deterministic scores
remain available when coaching fails.

See [architecture](docs/architecture.md), [data model](docs/data-model.md),
[privacy and data lifecycle](docs/privacy-and-data-lifecycle.md), and the
[roadmap](ROADMAP.md).
