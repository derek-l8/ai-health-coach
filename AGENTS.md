# Agent rules

- Never place credentials, tokens, databases, or health exports in Git.
- Autonomous Codex development runs in a separately configured disposable sandbox
  outside this repository with public code and synthetic data only. The included
  devcontainer is an ordinary development environment, not that security boundary.
- Private coaching runs in a separate trusted or isolated runtime with a bounded
  read-only packet.
- Preserve source provenance; distinguish missing values from zero.
- Preserve units, offset-aware timestamps, IANA timezones, and DST behavior.
- Keep the three versioned sleep scores separate from model interpretation and
  frontend presentation; never silently recalculate historical reports.
- Store Energy predictions before and separately from optional survey outcomes.
- Codex may suggest calibration but cannot change active weights or code directly;
  deterministic gates, validation, atomic activation, and rollback are required.
- Preserve transactions, conflict detection, and idempotent replay safeguards.
- Commit only synthetic test data and test boundary and missingness behavior.
- Provide wellness guidance, never diagnosis or emergency care.
- Codex must not commit, push, deploy, publish, or perform destructive operations.
