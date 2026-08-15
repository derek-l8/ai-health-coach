# Roadmap

## Implemented foundation

- Canonical observations with provenance, units, missingness, offset-aware time,
  IANA timezones, and DST validation.
- Transactional SQLite storage with replay idempotency and conflict detection.
- Strict synthetic Google Health steps ingestion and synthetic regression tests.

## Milestone 1: local application shell

- Add a loopback-only Python web service and local browser dashboard.
- Keep backend and scheduled execution independent of browser lifecycle and
  Windows-specific presentation behavior.
- Add application-owned protected data directories and Windows startup docs.
- Display foundation status without claiming live collection or scores.

## Milestone 2: user control and Google Health collection

- Implement Google OAuth with least-privilege, category-specific consent.
- Verify Google Fitbit Air API fields, units, timestamps, provenance, pagination,
  quotas, and replay behavior against synthetic contract tests.
- Retain successfully ingested raw responses for up to 30 days and canonical
  observations until local user deletion; never delete upstream source records.
- Add separate inspectable/revocable Google and AI-processing consent.
- Add complete sensitive-data export and seven-day recoverable local deletion.

## Milestone 3: all three sleep scores

- Implement separately versioned Efficiency, Recovery, and predicted Energy
  modules without an overall composite score.
- Store predicted Energy before a separate, optional daily 1–10 energy, recovery,
  and sleep-quality survey; every response and note remains nullable.
- Show confidence, completeness, evidence, limitations, contributing inputs,
  missing inputs, and graceful degradation.
- Store provider proprietary scores only as labeled comparisons.
- Validate DST, late-arriving data, personal baselines, sensitivity, and differing
  single-night and multi-night horizons before presenting scores as useful.

## Milestone 4: Codex-first coaching

- Define a replaceable runner accepting only a bounded read-only coaching packet
  in a private trusted/isolated runtime, never the external development sandbox.
- Manually prove subscription-authenticated, noninteractive Codex on Windows under
  the intended Task Scheduler account; do not substitute API-key billing.
- Store immutable prompts, responses, failure categories, actual model/provider
  metadata, request version, and exact deterministic score snapshots.
- Keep deterministic-only reports useful when coaching fails and retry only the
  coaching stage without attaching stale output.

## Milestone 5: daily Windows workflow and dashboard

- Add an idempotent, resumable non-interactive command for Windows Task Scheduler,
  configured to run once when the computer next becomes available.
- Generate at most one canonical report per local date and pipeline version, using
  the user's configured timezone, then exit cleanly.
- Present today's report plus weekly, monthly, and longer-term trends.
- Preserve original report snapshots and expose complete version/provenance detail
  behind one readable active sleep-model bundle label.

## Milestone 6: guarded personalization and revisions

- Accept structured Codex calibration suggestions without direct activation.
- Gate bounded weekly calibration by sample size, allowed ranges, data quality,
  historical validation, measurable improvement, and rollback availability.
- Add separate tested development workflow for formula, prompt, schema,
  orchestration, and code revisions with atomic parent-linked activation.
- Explain changes and expose rollback/freeze controls in the dashboard.

## Milestone 7: backups and deletion completion

- Add configurable automatic encrypted local backups, retention, integrity checks,
  and a tested restore command.
- Validate the relationship among trash, active storage, backups, and expiry.
- Only then implement double-confirmed permanent deletion with accurate backup
  retention disclosure.

Phone access through an authenticated private network such as Tailscale and a
packaged desktop shell are deferred until the local application works. Public
internet deployment is out of scope.
