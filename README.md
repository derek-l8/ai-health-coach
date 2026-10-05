# Personal AI Health Coach

Personal AI Health Coach is a prospective N-of-1 machine-learning study of sleep,
readiness, and energy. It asks:

> Can a transparent model trained on my longitudinal Fitbit/Google Health data
> and self-reports predict my defined outcomes better than simple history or
> Google Health Premium, and does Google's output add useful signal?

The comparison has four arms:

1. rolling historical baselines;
2. eligible Google Health Premium output;
3. a personal model using measurements and self-reported context; and
4. a hybrid model that also uses eligible Google output.

"Better" means lower prospective error on defined personal targets. It does not
mean clinically superior, better for other users, or better than every Google
feature.

## Current status

| Implemented | Not implemented |
| --- | --- |
| Synthetic Google-shaped ingestion and canonical SQLite storage | Live Google Health or Fitbit metrics/insight collection |
| Provenance, missingness, DST, conflict, and replay safeguards | Verified Takeout or Premium import formats |
| Deterministic sleep-score foundation | A trained personal or hybrid model |
| Private SQLite check-ins and event-relative configuration | Automatic reminders |
| Google Forms setup/export script and validated snapshot import (offline tested) | Real-account Form setup and iPhone pilot verification |
| Deterministic 60-day CSV fixture and Coach insight fixtures | Real personal results |
| Baselines, model interfaces, rolling-origin evaluation, and leakage tests | Production phone service or dashboard |
| Responsive check-in service and standalone synthetic prototype | Medical or diagnostic functionality |

The earlier Efficiency, Recovery, and predicted Energy heuristics remain
engineering baselines and possible model features. They are not validated health
outcomes.

## Targets and evidence rules

The initial 1-10 outcomes are:

- **Morning readiness:** capability to handle the demands planned for the day.
- **Afternoon energy:** current alertness and usable energy.
- **Overall energy:** usable energy across the completed day.

Prompts are tied to wake, afternoon, and day-close events rather than a fixed wake
time. Predictions may use only information available by their recorded cutoff.

The detailed rules live in the
[data-collection protocol](docs/data-collection-protocol.md) and
[evaluation protocol](docs/evaluation-protocol.md).

## Quick start

Run the project from a source checkout. It is not currently published as an
installable release.

Requirements:

- Python 3.14 (the currently tested version)
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/)

```bash
git clone https://github.com/derek-l8/ai-health-coach.git
cd ai-health-coach
uv sync --dev --frozen
uv run ai-health-coach --synthetic-smoke
```

The smoke check should print:

```json
{"application": "ai-health-coach", "mode": "synthetic-smoke", "private_data_accessed": false, "version": "0.1.0"}
```

## Explore the synthetic system

These commands score a fictional night, evaluate the synthetic 60-day study,
and write a generated copy of the study dataset to the ignored `data/`
directory:

```bash
uv run ai-health-coach --synthetic-score-night
uv run ai-health-coach --synthetic-evaluate
uv run ai-health-coach --write-synthetic-study data/synthetic-study.csv
```

The checked-in [60-day CSV](fixtures/synthetic/longitudinal-60-days.csv) is
deterministic and explicitly fictional. After cloning, open the
[phone-form prototype](prototype/phone-form/index.html) directly in a browser.
It submits nowhere and keeps its synthetic entry only in the browser tab.

## Collect personal check-ins

The primary route is a **Google Form linked to a private Google Sheet**, with
screenshots and exports kept in a private Drive folder. The iPhone responder link
does not require a running laptop, local certificates, or firewall changes.

Follow the [one-time Google setup and collection guide](docs/data-collection-protocol.md#primary-route-google-forms-and-drive).
The repository's Apps Script creates the collection resources when you run and
authorize it in your account. No live Form has been created or verified yet.

Export a response snapshot using that script, download it outside Git, and import
it from the repository directory in PowerShell:

```powershell
$studyDatabase = Join-Path $env:LOCALAPPDATA 'AIHealthCoach/study.sqlite3'
$studySnapshot = Join-Path $env:LOCALAPPDATA 'AIHealthCoach/checkins.json'
uv run ai-health-coach --import-form-snapshot $studySnapshot --database $studyDatabase
```

The importer validates all responses atomically, preserves source IDs and timing,
and rejects edited history. Google Health screenshot parsing is still planned;
Drive access is not automatic synchronization or account capture.

The original [local check-in service](docs/local-check-in-demo.md) remains an
optional development demo. Neither route assumes a fixed wake hour or requires
complete participation.

## Validate changes

CI runs formatting, linting, and tests on Python 3.14 and Node.js 24. Install Node
as well as Python/uv for the complete suite, including the exporter/importer
contract check:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

Browser time-conversion and mocked Apps Script tests also run in CI:

```bash
node --test tests/web/time.test.mjs tests/web/forms.test.mjs
```

## Update an existing checkout

Check `git status` first and commit or stash local changes before updating.

```bash
git pull --ff-only
uv sync --dev --frozen
```

## Repository map

```text
src/ai_health_coach/       records, check-in service, ingestion, scoring, evaluation
scripts/                   Google Forms setup and snapshot export
tests/                     synthetic regression and leakage tests
fixtures/synthetic/        public fictional inputs and Coach examples
prototype/phone-form/      static mobile-form demonstration
docs/                      architecture and prospective study protocols
```

See [architecture](docs/architecture.md), [data model](docs/data-model.md), and
[roadmap](ROADMAP.md).

## Data boundary

Git contains code, documentation, and synthetic fixtures only. Real exports,
screenshots, labels, notes, databases, emulator state, credentials, trained
private artifacts, and row-level personal results belong in a separate private
location.

Private processing may be local or use a service explicitly approved for the
task. Authorization to inspect health data does not authorize committing or
publishing it. See [SECURITY.md](SECURITY.md).

## Interpretation limits

The synthetic evaluation demonstrates software behavior, not health usefulness.
A preliminary personal claim requires at least 60 complete target labels followed
by at least 14 prospective held-out predictions. The working threshold is at
least 10% lower mean absolute error than the rolling-median baseline, with
coverage, uncertainty, exposure state, and failure cases reported.

This project supports wellness research only. It is not diagnosis, treatment,
emergency monitoring, or medical advice.
