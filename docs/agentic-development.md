# Agentic development

The included devcontainer is an ordinary reproducible Python development
environment. It installs project dependencies for the `vscode` user; it does not
provide or claim security isolation for autonomous agents.

Autonomous Codex development runs in a separately configured disposable sandbox
outside this repository, using public code and synthetic data only. That external
environment must not receive credentials, personal health data, or connected-app
access and must not commit, push, deploy, or publish.

The external development sandbox is also not the routine coaching runtime. Private
coaching requires a distinct trusted or isolated execution context. Its generated
input is bounded and read-only, and it cannot see the codebase, whole database,
OAuth material, encryption keys, Git credentials, or unrelated files.

External technical claims should be traceable to sources. Tests must exercise
missingness, timezones, DST, provenance, transactions, and replay behavior with
synthetic fixtures. Deterministic health calculations remain reviewable modules;
model prompts and user-interface decisions cannot silently redefine them.

Routine Codex coaching may return a structured calibration suggestion but cannot
edit code or activate it. A deterministic gate applies bounded calibration only
after sample-size, range, quality, historical-validation, improvement, and rollback
checks. Larger revisions use a separate development workflow; tests and evaluations
must pass before atomic activation, and the parent working revision remains
available for rollback.
