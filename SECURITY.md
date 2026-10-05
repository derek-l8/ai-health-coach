# Security policy

## Reporting

Report security vulnerabilities through
[GitHub private vulnerability reporting](https://github.com/derek-l8/ai-health-coach/security/advisories/new).
Report non-sensitive defects through a GitHub issue. Do not include credentials,
tokens, health exports, screenshots, private records, account identifiers, or
other sensitive material in a public issue.

If a credential has entered a public commit, revoke or rotate it before treating
history cleanup as sufficient.

## Current exposure

The repository includes a Python library, synthetic CLI demonstrations, and an
optional single-user check-in service. Check-ins persist to a private SQLite file
outside Git. The service binds loopback by default; other private IPv4 bindings
require HTTPS. It does not collect live Google Health data or run a trained model.

The check-in service generates a fresh random bearer token each time it starts.
The session link carries that token in its URL fragment, which the page removes
after reading it into memory. Anyone with the link can submit entries while the
service runs. Closing the service invalidates that session. Refreshing the page
requires opening the original session link again.

API requests check the token, Host, and browser Origin; payloads are bounded and
validated. The service serves only packaged assets, exposes no history endpoint,
disables browser caching, and suppresses request logs. The database is unencrypted
on disk and needs operating-system access controls and a private backup location.
This is not a hardened public server or a multi-user authentication system.

## Google Forms and Drive collection

The primary phone route stores check-ins in a Google Form and response Sheet,
with screenshots and snapshot exports in a private Drive folder. This is cloud
storage, not a local-only guarantee. The repo-owned Apps Script needs user-granted
Forms, Sheets, and Drive permissions; inspect the code and authorize it personally.
Do not deploy it as a web app or authorize an unreviewed copy.

Setup creates an unpublished Form. Before using it, verify Restricted access on
the Form editor, response Sheet, folder, and snapshots, and limit responder
access to the intended account. Keep response summaries and response editing off.
No public links, automatic capture, or background Drive synchronization are
created by the script. Account policy and permissions still need a real pilot.

The importer bounds snapshots to 5 MiB and 10,000 responses, rejects invalid
schemas and edited history, and logs only hashes/counts. Exact source bytes in
the private SQLite file can contain account IDs, notes, and health answers. The
database is unencrypted; protect it and all downloaded snapshots with OS access
controls and private backups. Form/Sheet/folder IDs and account state belong in
Script Properties or private records, never checked-in configuration.

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

Public deployment or a broader dashboard requires a separate threat-model review
covering authentication, transport security, session handling, cross-site request
forgery, authorization, logging, backups, and recovery. Loopback or a private
network is not by itself proof of adequate protection.

## Health boundary

The project produces wellness estimates only. It must not present a model output
as diagnosis, treatment, emergency monitoring, or a reason to delay professional
care. Provider scores and personal predictions must remain distinguishable from
measured facts and self-reported outcomes.
