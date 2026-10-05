import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import {createStudy} from "./forms_mock.mjs";

const completed = {status: "Completed", event_completed: "Morning readiness", rating_0: 7, google_seen: "No", acted_on: "Unknown"};

test("setup is unpublished, linked to a Sheet, frozen and idempotent", () => {
  const study = createStudy();
  study.evaluate("setupStudy()");
  assert.equal(study.form.published, false);
  assert.equal(study.form.edits, false);
  assert.equal(study.form.summary, false);
  assert.equal(study.form.email, false);
  assert.equal(study.form.limit, false);
  assert.deepEqual(study.form.destination, ["SPREADSHEET", "synthetic-sheet"]);
  assert.equal(study.sheet.timezone, "America/Los_Angeles");
  assert.equal(study.folders.size, 3);
  assert.equal(study.released, true);
  const form = study.form;
  study.evaluate('STUDY.caffeineCutoff = "14:00"; setupStudy()');
  assert.equal(study.form, form);
  assert.equal(study.state().configuration.caffeine_cutoff_local_time, null);
  assert.equal(study.folders.size, 3);
});

test("completed paths visit only the selected required rating; absent paths visit none", () => {
  const study = createStudy(); study.evaluate("setupStudy()");
  const items = study.form.items;
  const status = items.find(item => item.title === "Entry status");
  const event = items.find(item => item.title === "Check-in");
  const common = items.find(item => item.title === "Timing and optional context");
  assert.equal(status.choices[0].getGotoPage().title, "Choose a rating");
  for (const choice of event.choices) {
    const start = items.indexOf(choice.getGotoPage());
    const nextBreak = items.slice(start + 1).find(item => item.type === "PAGE_BREAK");
    const rating = items[start + 1];
    assert.equal(rating.type, "SCALE");
    assert.equal(rating.required, true);
    assert.equal(rating.lower, 1); assert.equal(rating.upper, 10);
    assert.equal(nextBreak.next, common);
  }
  assert.equal(status.choices[1].getGotoPage().title, "Absent rating");
  assert.equal(status.choices[2].getGotoPage().title, "Absent rating");
  assert.equal(items[items.indexOf(status.choices[1].getGotoPage()) + 1].type, "MULTIPLE_CHOICE");
});

test("exports stable native IDs, source timestamps and the Python fixture contract", () => {
  const study = createStudy(); study.evaluate("setupStudy()");
  study.form.responses.push(study.response(completed));
  const first = study.evaluate("exportSnapshot()");
  const fixture = JSON.parse(readFileSync(new URL("../../fixtures/synthetic/form-snapshot.json", import.meta.url), "utf8"));
  assert.deepEqual(JSON.parse(JSON.stringify(first)), fixture);
  study.evaluate("exportSnapshot()");
  assert.equal(study.files.length, 2); // New artifacts, not overwritten filenames.
  assert.equal(study.files[0].mime, "application/json");
  assert.equal(study.logs.some(log => log.includes("rating")), false);
});

test("skipped or missing ratings export null-equivalent blanks, not another page's rating", () => {
  const study = createStudy(); study.evaluate("setupStudy()");
  study.form.responses.push(study.response({status: "Skipped", event_absent: "Overall energy", rating_0: "9"}));
  const response = study.evaluate("exportSnapshot()").responses[0];
  assert.equal(response.answers.event, "Overall energy");
  assert.equal(response.answers.rating, "");
});

test("configuration changes do not reinterpret prior responses", () => {
  const study = createStudy();
  study.evaluate('STUDY.caffeineCutoff = "14:00"; setupStudy()');
  assert.equal(study.state().configuration.caffeine_cutoff_local_time, "14:00");
  assert.ok(study.form.items.some(item => item.title.includes("Caffeine at or after 14:00")));
  study.evaluate('STUDY.caffeineCutoff = "18:00"');
  assert.equal(study.evaluate("exportSnapshot()").configuration.caffeine_cutoff_local_time, "14:00");
});

test("edited prompts or response-history settings block exports", () => {
  for (const edit of [study => { study.form.items[0].title = "Different meaning"; }, study => { study.form.edits = true; }, study => { study.form.summary = true; }]) {
    const study = createStudy(); study.evaluate("setupStudy()"); edit(study);
    assert.throws(() => study.evaluate("exportSnapshot()"), /changed/);
    assert.equal(study.files.length, 0);
  }
});

test("invalid configuration fails before creating Drive artifacts", () => {
  for (const code of ['STUDY.caffeineCutoff = "25:00"', 'STUDY.afternoonEndHours = 1', 'STUDY.timezone = "not-an-iana-name"']) {
    const study = createStudy(); study.evaluate(code);
    assert.throws(() => study.evaluate("setupStudy()"));
    assert.equal(study.folders.size, 0);
    assert.equal(study.released, true);
  }
});

test("export before setup reports the missing step", () => {
  assert.throws(() => createStudy().evaluate("exportSnapshot()"), /setupStudy/);
});

test("Form validation requires offsets for backfills and bounds optional notes", () => {
  const study = createStudy(); study.evaluate("setupStudy()");
  const time = study.form.items.find(item => item.title.startsWith("Earlier time"));
  const pattern = new RegExp(time.validation.pattern);
  assert.ok(pattern.test("2024-11-03T01:30:00-08:00"));
  assert.ok(pattern.test("2024-11-03T09:30:00.000Z"));
  assert.equal(pattern.test("2024-11-03T01:30:00"), false);
  assert.equal(time.required, false);
  assert.equal(study.form.items.find(item => item.title.startsWith("Short note")).validation.maximum, 2000);
});
