import assert from "node:assert/strict";
import test from "node:test";
import {localTime, timeCandidates, timestamp} from "../../src/ai_health_coach/web/time.mjs";

function inZone(zone, run) {
  const previous = process.env.TZ;
  process.env.TZ = zone;
  try { run(); }
  finally {
    if (previous === undefined) delete process.env.TZ;
    else process.env.TZ = previous;
  }
}

test("a repeated LA hour requires an explicit occurrence", () => inZone("America/Los_Angeles", () => {
  const value = "2026-11-01T01:30";
  const candidates = timeCandidates(value);
  assert.deepEqual(candidates, ["2026-11-01T08:30:00.000Z", "2026-11-01T09:30:00.000Z"]);
  assert.throws(() => timestamp(value), /occurs twice/);
  assert.throws(() => timestamp(value, "stale selection"), /occurs twice/);
  for (const candidate of candidates) assert.equal(timestamp(value, candidate), candidate);
}));

test("the second current occurrence round-trips without losing an hour", () => inZone("America/Los_Angeles", () => {
  const now = new Date("2026-11-01T09:30:00Z");
  assert.equal(timestamp(localTime(now), now.toISOString()), now.toISOString());
}));

test("nonexistent spring times and malformed input are rejected", () => inZone("America/Los_Angeles", () => {
  for (const value of ["2026-03-08T02:30", "2026-02-30T12:00", "", "not a date"]) {
    assert.deepEqual(timeCandidates(value), []);
    assert.throws(() => timestamp(value), /invalid|does not exist/);
  }
}));

test("ordinary times need no occurrence choice", () => inZone("America/Los_Angeles", () => {
  assert.equal(timestamp("2026-01-05T14:00"), "2026-01-05T22:00:00.000Z");
}));

test("half-hour fallback transitions are disambiguated", () => inZone("Australia/Lord_Howe", () => {
  const value = "2026-04-05T01:45";
  assert.deepEqual(timeCandidates(value), ["2026-04-04T14:45:00.000Z", "2026-04-04T15:15:00.000Z"]);
  assert.equal(timestamp(value, "2026-04-04T15:15:00.000Z"), "2026-04-04T15:15:00.000Z");
}));

test("a date-line skip does not become another calendar day", () => inZone("Pacific/Apia", () => {
  assert.deepEqual(timeCandidates("2011-12-30T12:00"), []);
}));
