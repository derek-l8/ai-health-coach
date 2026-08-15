# Architecture

## Target deployment

The first deployment is a single-user application on Windows. A platform-neutral
Python backend owns collection, storage, deterministic calculations, retention,
and report generation. A responsive local web server binds to loopback so the
user can open it in a normal browser without creating a hosted account. Browser
state and Windows-specific presentation behavior never control backend progress.

Windows Task Scheduler eventually starts a non-interactive daily run even when the
browser is closed. It is configured to run once when the computer next becomes
available after being asleep, off, or offline. A packaged desktop shell is deferred
unless it later provides a concrete benefit. Phone access is also deferred; the
loopback-first design may later gain authenticated private-network access such as
Tailscale, never public deployment infrastructure.

## Runtime flow

The trusted application boundary will collect user-authorized Google Fitbit Air
data through the Google Health API, retain it in application-controlled storage,
run deterministic modular calculations, and then provide explicitly selected raw
or derived context to Codex for wellness coaching.

```text
Google Fitbit Air -> Google Health OAuth/API
  -> raw response archive (30-day retention)
  -> canonical observations (retained until user deletion)
  -> separate deterministic Efficiency, Recovery, and predicted Energy modules
  -> consent and context selection
  -> replaceable subscription Codex coaching runner
  -> immutable local report history
  -> responsive local dashboard
```

The coaching runner is an interface rather than part of scoring. It accepts a
versioned, bounded, read-only packet and returns coaching text plus optional
structured calibration suggestions. It receives only necessary measurements,
scores, provenance, confidence, uncertainty, relevant history, goals, and
feedback. It receives no complete database, source tree, credentials, secrets,
keys, or unrelated files. Routine coaching is output-only with respect to code and
cannot activate weights or algorithms.

The intended first runner uses subscription-authenticated Codex, not API-key
billing. Official OpenAI documentation describes [ChatGPT subscription sign-in
for local Codex](https://learn.chatgpt.com/docs/auth), and the [`codex exec`
noninteractive interface](https://learn.chatgpt.com/docs/non-interactive-mode)
states that it reuses saved CLI authentication and can run in scheduled jobs.
Separately, OpenAI documents [ChatGPT desktop scheduled
tasks](https://learn.chatgpt.com/docs/automations) and the [Windows desktop
app](https://learn.chatgpt.com/docs/windows/windows-app). Those desktop tasks are
not Windows Task Scheduler and do not prove the exact personal-subscription plus
Windows Task Scheduler combination as a reliable unattended application service.
That combination remains an unresolved live integration check. A different
supported plan, runner, provider, or model can later replace it without changing
canonical observations or deterministic scoring.

Private coaching must run in a trusted or isolated runtime distinct from the
separately configured disposable Codex development sandbox. That external sandbox
contains public code and synthetic fixtures only and must never receive real
coaching packets. The repository devcontainer is an ordinary development
environment and does not enforce this boundary.

## Daily pipeline contract

For the user's configured IANA timezone, the scheduled pipeline:

1. retrieves, validates, and stores new Google Health data;
2. calculates the three separate scores, storing predicted Energy before survey;
3. builds the bounded coaching packet;
4. requests and validates coaching; and
5. makes the stored report available to the dashboard.

The canonical report identity is `(local_date, pipeline_version)`. Stages use
durable status and idempotency keys so interrupted work resumes without duplicating
observations, scores, surveys, requests, or responses. A Codex authentication,
network, or execution failure does not roll back deterministic scores. The report
records a non-sensitive coaching failure category and may retry only the coaching
stage; stale coaching is never attached to a newer report.

## Separation of responsibilities

Collection, canonical storage, deterministic analysis, context selection, model
interpretation, and presentation are separate layers. Frontend flow and styling
must not implement or modify scoring logic. A model may explain or contextualize
a score, but it cannot replace the deterministic result or silently change its
inputs.

Standing consent authorizes scheduled collection, calculation, and report
generation for selected data categories. Consent remains reviewable and
revocable. It does not authorize unrelated filesystem, application, or network
actions. The coaching process should run with the least local permissions needed.

The dashboard shows today's status first and historical trends second. Every score
includes confidence, completeness, evidence, limitations, and missing inputs.
Fitbit proprietary Sleep Score, Readiness, or similar values are comparison series
only, never ground truth for independently versioned algorithms.

## Personalization and activation

Versioned base algorithms calculate the three scores. Personal calibration uses
bounded weights and thresholds learned from inspectable feedback. Codex may propose
a structured change, but a deterministic gate checks minimum sample size, parameter
ranges, data quality, historical validation, measurable improvement, and rollback
availability. Calibration normally activates no more than weekly.

Larger formula, prompt, schema, orchestration, or code changes use a separate Codex
development workflow with synthetic tests and evaluations. Activation is atomic,
records its parent, and retains the previous working revision. The dashboard
explains what changed, why, evidence window, validation, measured improvement,
activation time, parent revision, and rollback or freeze controls.

## Version and report identity

Human-facing sleep bundles use semantic labels such as `sleep-model 1.0.0`.
Internally each report records separate semantic versions for Efficiency,
Recovery, and Energy; monotonic calibration revision such as `cal-000001`; prompt
and coaching-runner versions; the actual configured or returned provider/model
identifier; application and request versions; parent revision; activation instant;
and source provenance.

Historical reports retain the exact original scores, inputs, completeness,
versions, timestamp, offset, and IANA timezone. They are never silently
recalculated. A future current-model comparison must be separately labeled.

## Manual Codex runner proof-of-concept

Before enabling scheduled coaching on Windows, a user-controlled acceptance test
must sign in with ChatGPT, confirm subscription authentication, run the bounded
packet noninteractively with read-only/no-code access, validate structured output,
restart Windows, run under the intended Task Scheduler account with the browser
and dashboard closed, exercise offline/auth-expiry failures, confirm no credential
or unrelated-file access, and verify deterministic-only fallback and safe retry.
Passing locally demonstrates feasibility for that environment; it is not a claim
that the external Codex development sandbox tested private coaching.

## Security evolution

Protected storage and encrypted local backups are planned behind narrow storage
interfaces. Backup schedule and retention defaults remain implementation choices,
but integrity verification and a tested restore command are acceptance gates for
permanent deletion. OAuth and Codex session material never enter Git, health
tables, coaching packets, exports, or backups unless a separately reviewed secure
credential-backup design explicitly permits it.

Only the synthetic ingestion and canonical-storage layers exist today.
