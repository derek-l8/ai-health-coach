# Security policy

## Reporting

Report non-sensitive defects through a GitHub issue. Do not include credentials,
tokens, health exports, screenshots, private records, account identifiers, or
other sensitive material in a public issue. This project does not currently
publish a private vulnerability-reporting channel; use a minimal, non-sensitive
description while seeking a safe contact route.

If a credential has entered a public commit, revoke or rotate it before treating
history cleanup as sufficient.

## Current exposure

The current repository is a Python library and synthetic CLI scaffold. It does
not serve a dashboard, authenticate users, collect live health data, or run a
trained personal model. Its current tests therefore do not establish the security
of a future phone form, OAuth flow, emulator workflow, private deployment, or AI
integration.

## Public-repository boundary

Only code, documentation, and synthetic fixtures belong in Git. Keep these
outside the repository and its history:

- Google account exports and archives;
- health screenshots and Premium insight captures;
- personal labels, notes, and context fields;
- SQLite databases, generated reports, and model artifacts trained on private
  data;
- OAuth material, session files, cookies, API keys, and provider credentials;
- logs or caches that may contain identifiers or health content.

Synthetic reproductions should preserve the relevant schema and failure behavior
without copying personal values or unique identifiers. Recreate public fixtures
with fictional values rather than relying on redaction. Aggregate results from a
single-person study may still be sensitive and require review before publication.

## Private runtime boundary

The eventual study runtime may be local or may use a service the user explicitly
approves. That is a separate trust boundary from the public source repository.
Private data access must be limited to the component performing an authorized
capture, analysis, or coaching task. Credentials must use operating-system or
provider-managed storage rather than health tables, model inputs, exports, or
logs.

Screenshot and emulator workflows deserve the same treatment as raw exports:
screen recordings, notification text, clipboard contents, emulator backups, and
authentication state may all contain sensitive material. Automation should use a
dedicated profile where practical and must not commit or upload artifacts by
default.

Any future networked form or dashboard requires a separate threat-model review
covering authentication, transport security, session handling, cross-site request
forgery, authorization, logging, backups, and recovery. Loopback or a private
network is not by itself proof of adequate protection.

## Health boundary

The project produces wellness estimates only. It must not present a model output
as diagnosis, treatment, emergency monitoring, or a reason to delay professional
care. Provider scores and personal predictions must remain distinguishable from
measured facts and self-reported outcomes.
