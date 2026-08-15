# Decision 0001: Authorized online AI processing

- Status: accepted
- Date: 2026-08-10

With separate affirmative AI consent, the trusted application may send a bounded
selection of raw or derived health context to a subscription-authenticated Codex
coaching process. The packet may include necessary measurements, deterministic
scores, provenance, confidence, uncertainty, relevant history, goals, and feedback.
It excludes credentials, secrets, keys, the full database, unrelated files, Git
access, and application code.

Routine coaching is output-only with respect to application code. It may return
wellness text and calibration suggestions, but cannot directly activate weights or
algorithms. Deterministic calculations execute first and remain independently
testable. Coaching is not diagnosis, emergency monitoring, or emergency care.

Autonomous Codex development uses a separately configured disposable sandbox
outside this repository with public code and synthetic fixtures only. The included
devcontainer is an ordinary development environment, not that security boundary.
Private coaching requires a distinct trusted or isolated runtime. The Codex runner
remains replaceable, and unattended personal-subscription execution under Windows
Task Scheduler is an unresolved live integration check rather than an accepted
capability claim.
