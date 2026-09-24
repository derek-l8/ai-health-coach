# Agent rules

- Never place credentials, tokens, databases, screenshots, personal labels,
  health exports, trained private artifacts, or account data in Git.
- Treat the public repository and the private study-data location as separate
  trust boundaries. Private analysis may use an explicitly approved environment,
  but committed fixtures must remain synthetic.
- Preserve source provenance and distinguish missing, zero, not applicable, not
  captured, and captured late.
- Preserve units, offset-aware timestamps, IANA timezones, and DST behavior.
- Record `observed_at`, `available_at`, and `captured_at` separately when
  they differ; features may use only information available at prediction time.
- Distinguish original provider insights from historical summaries and later
  reconstructed answers.
- Store provider exposure and prediction records before the outcome label when
  the protocol requires an unbiased comparison.
- Keep heuristic Efficiency, Recovery, and Energy scores separate from
  self-reported targets, provider outputs, trained models, and coaching text.
- Never silently recalculate historical predictions or result reports.
- Preserve transactions, conflict detection, and idempotent replay safeguards.
- Keep implemented behavior, planned behavior, and study hypotheses visibly
  separate in public documentation.
- Use synthetic data for tests, including boundary, timing, missingness, leakage,
  provenance, and replay behavior.
- Provide wellness guidance only, never diagnosis, treatment, or emergency care.
- Do not commit, push, deploy, publish, rewrite history, change GitHub settings,
  or perform destructive operations without explicit authorization.
