# Decision 0002: Local Windows application and user-controlled lifecycle

- Status: accepted
- Date: 2026-08-15

The first product is a single-user Windows application presented through a local
browser dashboard. It is not a hosted multi-user service. A scheduled daily mode
generates a report and exits; interactive dashboard use starts separately.

The target runtime collects Google Fitbit Air data through consented Google Health
API access; live collection is not part of the current scaffold.
Raw provider responses expire after 30 days. Canonical observations, scores,
reports, prompts, responses, goals, and feedback remain until user deletion.
Normal deletion is recoverable for seven days and never removes upstream records.
Immediate permanent deletion is deferred until encrypted backup and restore
acceptance tests pass.

The first scoring release includes Efficiency, Recovery, and Energy. Incomplete
input produces a low-confidence score with available and missing evidence rather
than an unexplained failure or invented value. The dashboard presents today's
results and longer-term trends.

Codex is the intended first coaching provider using existing subscription
authentication where supported. The integration is replaceable, has no authority
to alter deterministic scoring, and may automatically act only within separate,
standing, revocable AI-processing consent. Its unattended Windows Task Scheduler
operation remains subject to a manual live proof-of-concept.
