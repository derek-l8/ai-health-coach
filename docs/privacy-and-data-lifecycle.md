# Privacy and data lifecycle

The user owns the local record and controls collection, processing, retention,
export, and deletion. The application has no hosted account or application cloud
database in its first deployment.

## Consent

Two affirmative, inspectable authorizations are independent: Google Health data
access and AI coaching processing. The AI disclosure explains that selected raw or
derived health context may be sent to subscription-authenticated Codex/OpenAI for
the visible coaching feature. Revoking Google access stops synchronization and
handles token revocation or expiry. Revoking AI processing stops future coaching
without deleting deterministic records. Deletion remains a separate control.

OAuth scopes are least-privilege and feature-specific. The sleep-first phase does
not request unrelated write or deletion scopes.

## Retention classes

| Data | Default retention |
| --- | --- |
| Raw Google Health responses | 30 days |
| Canonical observations | Until user deletion |
| Deterministic scores and explanations | Until user deletion |
| Coaching prompts, responses, and metadata | Until user deletion |
| Goals, check-ins, and feedback | Until user deletion |
| Deleted items in recoverable trash | 7 days |

Raw responses are deleted within 30 days only after successful canonical ingestion
and are used for replay, validation, and debugging. Local expiry never deletes an
upstream Google/Fitbit record. Automated expiry is transactional, auditable without
retaining deleted content, and safe to replay; it preserves canonical provenance.

## Export and deletion

Export produces a portable archive of retained raw responses, canonical
observations, missingness, units, timestamps, timezones, provenance, scores and
versions, surveys, predicted-versus-observed outcomes, coaching history, goals,
preferences, calibration/revision history, and relevant consent settings. It
excludes OAuth tokens, API keys, client secrets, encryption keys, and unrelated
operational logs. The UI warns that exports contain sensitive health information
and will support optional export encryption.

Normal deletion moves selected local data and dependent derived results into
recoverable trash for seven days. Restore returns identifiers and relationships
intact. Automatic purge then removes them from active storage. Neither action
deletes upstream Google/Fitbit records.

Immediate permanent deletion is deferred until encrypted backup creation,
retention, expiry, integrity, and restore behavior pass acceptance tests. The
future flow shows affected dates/categories and dependent results, requires typed
`DELETE PERMANENTLY` and a second confirmation, removes active local copies, never
deletes upstream records, and accurately allows encrypted backups to expire under
their documented retention policy.

## Backups

Automatic encrypted local backups will have configurable schedule and retention,
integrity verification, and a tested restore command. Defaults remain an
implementation decision. Backup contents and manifests must support deletion and
expiry audits without falsely promising immediate removal from every historical
backup.

Revoking Google or Codex access is separate from deleting local data. The
dashboard should explain both actions and link to provider-side account controls.
