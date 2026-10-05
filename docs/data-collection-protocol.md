# Data-collection protocol

- Status: Forms setup/export and private import implemented; real-account pilot pending
- Protocol version: 0.1.0
- Scope: prospective single-person wellness study

This protocol defines the minimum records needed to compare a historical
baseline, Google Health Premium, a personal raw-data model, and a hybrid model.
It is intentionally tolerant of inconsistent participation.

## Primary route: Google Forms and Drive

Daily entries use a Google Form linked to a private response Sheet. Safari on
iPhone can open the responder link without a running laptop, local certificate,
or firewall rule. This route uses your Google account; it is not local-only.

The repository supplies a setup/export script and a validated Python importer.
They are tested with fictional data and mocked Google services. The script has
not yet been run in a real account, and the iPhone flow still needs a pilot.

### One-time setup

1. Open [Apps Script](https://script.google.com/) in the Google account you want
   to use and create a new project. Replace the editor's starter code with
   [google-forms-study.js](../scripts/google-forms-study.js). Review the script:
   it creates a Form, response Sheet, and Drive folders; it does not deploy a
   web app, access Google Health, or install an automatic trigger.
2. Set `STUDY.timezone` to your IANA timezone before running it. Afternoon timing
   defaults to 5–9 elapsed hours after actual wake. Wake and day-close are manual.
   `caffeineCutoff` is optional: leave `null` to omit that question, or choose
   a 24-hour `HH:MM` cutoff. The answer refers to caffeine at or after that time
   on the rating's study-local date. No cutoff or wake hour is assumed.
3. Select `setupStudy` in the function menu and click Run. Review and authorize
   the Google permissions yourself. This script requests Forms, Sheets, and
   Drive access; do not authorize code you have not reviewed. Its execution log
   prints links to the Form editor, response Sheet, and private study folder.
4. Check sharing on the Form, Sheet, and folder. Keep editor/file access
   Restricted and responder access limited to your own account. Leave response
   summaries and response editing off, and do not limit the Form to one response.
   The script creates the Form unpublished. Review its branches, then publish it
   from the Forms editor with the intended responder access; publishing the
   responder form is not permission to share the Sheet or study folder.
5. Open the responder link in Safari while signed into that account. Bookmark it
   or add it to the Home Screen. Submit one entry and confirm it appears in the
   response Sheet. Export and import that entry as below to verify the full path.

Running `setupStudy` again in the same Apps Script project returns existing links,
rather than creating duplicates. The first configuration and question identities
are frozen in Script Properties. Do not delete those properties or edit the
questions, anchors, branches, or response-history settings after collection
starts. For new timezone, window, or caffeine settings, create a new Apps Script
project and Form; keep the old Form, snapshots, and configuration for historical
records. Altered target prompts or anchors require a code/protocol version change;
the current importer supports the supplied prompts only. If setup fails
before it finishes, inspect the account for partial artifacts before retrying.

### Everyday use

Choose the event and status. Completed entries require the selected 1–10 rating;
skipped and missing entries bypass the rating. Optional context may be left blank.
Record whether Google guidance was seen before the rating and whether it was
acted on. Missing an event does not discard the other labels from that day.

Leave the earlier-time field blank when describing your state at submission.
Google's actual submission timestamp becomes `observed_at` and `captured_at`.
For backfills, enter an explicit ISO timestamp with a UTC offset, such as
`2024-11-03T01:30:00-08:00` for the second repeated hour in Los Angeles. Wake
time is also optional and uses that format. A bare local time is rejected by the
importer; it never guesses which DST occurrence you meant. An afternoon entry
without wake time remains unanchored. There are no automatic reminders.

Upload Google Health screenshots or exports to the study's private Drive folder.
Use the `screenshots/` subfolder for images. Preserve the original file, capture
time, period shown, and original/historical/reconstructed provenance in a companion
note. A capture date is not proof an insight was available at prediction time.
Drive stores these files; screenshot parsing and Google Health imports are not
implemented. A connected Codex session may inspect authorized files on request,
but there is no background Drive synchronization in this repository.

### Export and import

In the same Apps Script project, run `exportSnapshot` whenever you want to bring
new check-ins into the local database. It writes a new JSON file into `snapshots/`
and prints its link and response count, not health answers. Download it to a
private directory outside Git, then run from the repository in PowerShell:

```powershell
$studyDirectory = Join-Path $env:LOCALAPPDATA 'AIHealthCoach'
$studyDatabase = Join-Path $studyDirectory 'study.sqlite3'
$studySnapshot = Join-Path $studyDirectory 'checkins.json' # Your downloaded snapshot.
uv run ai-health-coach --import-form-snapshot $studySnapshot --database $studyDatabase
```

The command prints the snapshot hash and inserted/replayed counts. Re-running it
does not duplicate rows or replace the original import time. One invalid or edited
response rejects the entire snapshot. Errors do not echo answer text. Correct a
mistake with a new submission and a note referring to the original; automatic
correction reconciliation is not implemented.

That correction path applies to valid entries whose meaning needs correcting.
If a malformed response blocks import, preserve the snapshot and resolve the
source error before proceeding; adding another response does not remove the bad
one. Selective quarantine tooling is not implemented. Form validation checks
timestamp syntax and note length; the importer additionally checks actual dates,
time ordering, and configuration. Pilot backfills before relying on them.

Snapshots use this project's versioned JSON contract, **not a native Google Health
export or arbitrary Sheet CSV**. The exporter reads the Form's original response
store so stable [response IDs and submission timestamps](https://developers.google.com/apps-script/reference/forms/form-response)
survive locale formatting and repeated DST hours. The linked Sheet is a readable
live view; editing it does not change imported Form responses.

The database preserves exact snapshot bytes privately and assigns `available_at`
to the first local import, conservatively preventing backfilled context from
entering earlier predictions. Google submission time, event time, export time,
and local import time remain distinct. Keep the model clock synchronized.

For an offline demonstration, import the explicitly fictional fixture into a
**separate** private database so synthetic rows do not enter your personal study:

```powershell
$demoDatabase = Join-Path $env:TEMP 'AIHealthCoach/forms-demo.sqlite3'
uv run ai-health-coach --import-form-snapshot fixtures/synthetic/form-snapshot.json --database $demoDatabase
```

## Optional local demo

The original Python check-in page remains available for development and comparison.
Its [local setup guide](local-check-in-demo.md) retains desktop and private-network
iPhone instructions. It is not required for the Google Forms collection route.

## Google Health capture boundary

The intended capture route is a desktop Android emulator running Google Health,
but app compatibility and account sign-in have not been verified. Screenshot
automation depends on that verification; manual screenshots remain an alternative.
Neither check-in route accesses Google Health. Original screenshots belong
in the private Drive capture folder or a separate private directory, with capture
time, source, and original-versus-reconstructed provenance.
The adapter and screenshot automation require inspecting the actual app and its
artifacts first. Check-in collection can begin independently of that setup.

## Collection events

The interface uses configurable events, not fixed clock times.

### Wake event

Collect after waking and, when practical, after the night's sleep metrics are
available:

- morning readiness rating;
- whether Google readiness or guidance was already seen;
- whether any seen recommendation is expected to be followed;
- illness state;
- academic stress;
- exam or deadline within 48 hours;
- medication changed or missed, only when applicable;
- unusual sleep circumstances; and
- an optional short note.

### Afternoon event

Collect current afternoon energy during a user-configurable window. Preserve the
window and actual response time. A late response is accepted and marked late.

### Day-close event

Collect overall energy for the day, final recommendation-action state, and an
optional short note. A note may be invited every other day, but is never required
for a day to be usable.

Exercise may be derived from device data when available. Otherwise record
`none`, `light`, `moderate`, `hard`, or missing. Also capture caffeine
at or after the explicitly configured study-local cutoff, alcohol as `none`,
`one`, or `two_or_more`, and unusual circumstances when known.

## Label definitions

Each rating uses an integer from 1 to 10. The prompt and anchors are versioned;
changing them starts a new protocol version.

### Morning readiness

Prompt: **How capable do I feel of handling the demands planned for today?**

- **1:** unable to handle ordinary planned demands;
- **5:** able to handle essential demands, but only with noticeable effort or
  reduction; and
- **10:** fully capable of handling a highly demanding day.

### Afternoon energy

Prompt: **How alert and energized do I feel right now?**

- **1:** barely able to stay alert or complete basic tasks;
- **5:** enough energy for routine work, with clear dips or effort; and
- **10:** sustained, unusually high alertness and usable energy.

### Overall energy

Prompt: **Looking back, how much usable energy did I have across the day?**

- **1:** almost no usable energy across the day;
- **5:** enough for essential tasks, but limited or inconsistent; and
- **10:** abundant, sustained usable energy across the day.

Intermediate ratings are judgments between the anchors. Readiness and energy are
not interchangeable: readiness incorporates the day's expected demands; energy
describes alertness and usable capacity.

## Timing and leakage fields

Every record preserves:

- the local date and IANA timezone;
- the interval or event being described;
- `observed_at`, when the state applied;
- `available_at`, when the pipeline could first use a source value;
- `captured_at`, when the source recorded it;
- `imported_at`, when a Forms snapshot entered the local database;
- capture method and schema version; and
- whether it was on time, late, skipped, or missing.

A model may use only data whose `available_at` is no later than its prediction
cutoff. A later reconstruction of a Google insight cannot be used as if it had
been available that morning.

## Provider exposure

For each target, record:

- `google_seen_before_label`: `yes`, `no`, or `unsure`;
- `recommendation_acted_on`: `no`, `partly`, `yes`, or `unknown`;
- output type and target/horizon, when known; and
- when the output first became available and when it was captured.

The protocol does not require the user to avoid Google guidance. Exposure is a
real part of the system and becomes a stratification or sensitivity variable.

## Premium insight provenance

Classify captured text as:

- `original_insight`: the message presented at the relevant time;
- `historical_insight`: a stored past message retrieved later; or
- `reconstructed_insight`: a new answer generated later about an earlier
  period.

Also record whether the text is exact, transcribed, summarized, or parsed. Keep
the screenshot or source artifact private.

## Missing and partial days

Prompts may be missed. Do not backfill a rating by pretending it was observed on
time. A late rating is allowed when the described interval is still clear, but
the delay is retained.

Completeness is target-specific. For example, a day can be eligible for morning
readiness analysis even if afternoon energy is missing. Partial days remain in
storage and are excluded only by an explicit evaluation rule.

A **complete labeled day** for a target contains:

- a valid target rating;
- valid observed and capture timing;
- a provider-exposure record, including `unsure` when necessary; and
- the minimum feature-availability record required by that model arm.

## Collection phases

- **Days 1-20:** debug prompts, timing, missingness, and source mappings. Report
  descriptions only.
- **After 21 complete target labels:** allow exploratory plots and associations.
- **After 60 complete target labels:** freeze the first training protocol and fit
  the initial personal models.
- **After at least 14 later predictions:** permit a preliminary held-out
  comparison.
- **90-180 days:** preferred range for more stable conclusions.

Calendar days and complete labeled days are reported separately. Reaching a
calendar date never substitutes for the label-count gate.

## Optional future interventions

Controlled caffeine, exercise, bedtime, or workload experiments are not required
for the initial study. If later added, each intervention needs its own
pre-registered schedule, adherence field, safety review, and analysis. Ordinary
behavioral variation must not be mislabeled as randomized evidence.
