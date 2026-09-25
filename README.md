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
| Synthetic Google-shaped ingestion and canonical SQLite storage | Live Google or Fitbit collection |
| Provenance, missingness, DST, conflict, and replay safeguards | Verified Takeout or Premium import formats |
| Deterministic sleep-score foundation | A trained personal or hybrid model |
| Versioned study records and event-relative configuration | Persistent real check-ins |
| Deterministic 60-day CSV fixture and Coach insight fixtures | Real personal results |
| Baselines, model interfaces, rolling-origin evaluation, and leakage tests | Production phone service or dashboard |
| Static responsive phone-form prototype | Medical or diagnostic functionality |

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

## Run the synthetic system

Requirements:

- Python 3.14 or newer
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/)

CI runs the full validation suite on Python 3.14.

```bash
uv sync --dev --frozen
uv run ai-health-coach --synthetic-smoke
uv run ai-health-coach --synthetic-score-night
uv run ai-health-coach --synthetic-evaluate
uv run ai-health-coach --write-synthetic-study study.csv
uv run pytest
```

The checked-in [60-day CSV](fixtures/synthetic/longitudinal-60-days.csv) is
deterministic and explicitly fictional. The standalone
[phone-form prototype](prototype/phone-form/index.html) submits nowhere and keeps
its synthetic entry only in the browser tab.

## Repository map

```text
src/ai_health_coach/       validated records, ingestion, scoring, evaluation
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
