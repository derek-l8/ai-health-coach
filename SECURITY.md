# Security policy

Do not report vulnerabilities with real credentials or health exports. Use
synthetic reproductions. Keep OAuth secrets, model-provider keys, databases, and
raw exports outside Git. Revoke any credential accidentally exposed and remove it
from all history before sharing the repository.

Non-sensitive defects may be reported through a GitHub issue. Never post
credentials, health exports, tokens, private records, or other sensitive material
in a public issue. This project does not currently claim a private reporting
channel; do not publish sensitive details while seeking a safe contact route.

The planned local web service binds to loopback by default and has no public
internet deployment. Later phone access may use an explicitly configured private
network such as Tailscale, with authentication and threat-model review. Google
OAuth tokens and Codex authentication belong in protected operating-system or
provider-managed credential storage, not in the health database.

Routine private coaching and autonomous Codex development are separate trust
boundaries. Codex development occurs in separately configured disposable
infrastructure outside this repository, using public code and synthetic data only;
the included devcontainer does not enforce that boundary. The
coaching runner receives a generated bounded packet and cannot access application
code, the complete database, OAuth or Git credentials, client secrets, encryption
keys, or unrelated files.

Initial local storage is not advertised as application-encrypted. Windows account
isolation and file permissions are the first boundary while protected storage and
automatic encrypted backups are designed and tested. Raw responses expire within
30 days only after successful canonical ingestion. Normal local deletion has a
seven-day undo period and never deletes upstream Google/Fitbit records.

Immediate permanent deletion is deliberately deferred until encrypted backup
creation, retention, expiry, integrity verification, and restore tests pass. A
future permanent-delete flow must show affected dates and categories, explain
dependent results, require typed `DELETE PERMANENTLY` plus a second confirmation,
and accurately disclose backup expiry instead of promising instant erasure from
every backup.
