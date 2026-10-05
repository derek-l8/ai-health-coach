"use strict";
import {localTime, timeCandidates, timestamp} from "./time.mjs";

const token = new URLSearchParams(location.hash.slice(1)).get("token") || "";
history.replaceState(null, "", location.pathname);
window.addEventListener("hashchange", () => {
  if (new URLSearchParams(location.hash.slice(1)).has("token")) location.reload();
});
const form = document.querySelector("#check-in");
const result = document.querySelector("#result");
const submit = document.querySelector("#submit");
const entry = document.querySelector("#entry");
const prompts = {
  wake: ["How capable do I feel of handling the demands planned for today?",
    "1: unable to handle ordinary demands · 5: essentials take noticeable effort · 10: fully capable of a highly demanding day"],
  afternoon: ["How alert and energized do I feel right now?",
    "1: barely able to stay alert · 5: enough for routine work, with dips · 10: unusually high alertness and usable energy"],
  day_close: ["Looking back, how much usable energy did I have across the day?",
    "1: almost no usable energy · 5: enough for essentials, but limited · 10: abundant, sustained energy"]
};
let pending = null;

function updateTimeChoice(name, choiceName, labelId, offsetId) {
  const candidates = timeCandidates(form.elements[name].value);
  const choice = form.elements[choiceName];
  const previous = choice.value;
  choice.replaceChildren(new Option("Choose an occurrence", ""));
  candidates.forEach((value, index) => {
    choice.add(new Option(`${index === 0 ? "First" : "Second"}: ${new Date(value).toString()}`, value));
  });
  choice.value = candidates.includes(previous) ? previous : "";
  choice.required = candidates.length > 1;
  document.querySelector(labelId).hidden = !choice.required;
  const selected = candidates.length === 1 ? candidates[0] : choice.value;
  document.querySelector(offsetId).textContent = selected
    ? `Selected time: ${new Date(selected).toString()}. This offset is saved with the entry.`
    : candidates.length > 1 ? "This time occurs twice. Choose the occurrence you mean." : "";
}

function updatePrompt() {
  const [prompt, anchors] = prompts[form.elements.event.value];
  document.querySelector("#prompt").textContent = prompt;
  document.querySelector("#anchors").textContent = anchors;
  const completed = form.elements.status.value === "completed";
  form.elements.rating.disabled = !completed;
  form.elements.rating.required = completed;
  document.querySelector("#rating-label").hidden = !completed;
  updateTimeChoice("observed_at", "observed_occurrence", "#observed-choice", "#offset");
  updateTimeChoice("wake_at", "wake_occurrence", "#wake-choice", "#wake-offset");
}

function setCurrentTime() {
  const now = new Date();
  form.elements.observed_at.value = localTime(now);
  updatePrompt();
  // The current instant is known, so preserve it even during a repeated hour.
  now.setUTCSeconds(0, 0);
  form.elements.observed_occurrence.value = now.toISOString();
  updatePrompt();
}

setCurrentTime();
form.addEventListener("input", () => { pending = null; updatePrompt(); });
form.addEventListener("change", () => { pending = null; updatePrompt(); });
updatePrompt();

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {"Authorization": `Bearer ${token}`, "Content-Type": "application/json"},
    cache: "no-store"
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Could not save this entry.");
  return data;
}

api("/api/config").then(config => {
  const window = config.windows.find(item => item.event === "afternoon");
  const deviceZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  document.querySelector("#configuration").textContent =
    `Study timezone: ${config.timezone}. Times below use this device's timezone (${deviceZone}). ` +
    `Afternoon window: ${window.opens_after_wake_hours}–${window.closes_after_wake_hours} hours after actual wake. ` +
    "Entries save to your private database on the computer running this page.";
  const cutoff = config.caffeine_cutoff_local_time;
  form.elements.caffeine_after_cutoff.disabled = !cutoff;
  document.querySelector("#caffeine-prompt").textContent = cutoff
    ? `Caffeine at or after ${cutoff} (${config.timezone}), on this rating's local date`
    : "Caffeine not captured: restart the service with --caffeine-cutoff HH:MM to define it";
  submit.disabled = false;
  entry.disabled = false;
}).catch(error => {
  document.querySelector("#configuration").textContent = "Session unavailable.";
  result.textContent = error.message;
});

form.addEventListener("submit", async event => {
  event.preventDefault();
  submit.disabled = true;
  result.textContent = "Saving…";
  try {
    if (!pending) {
      const fields = Object.fromEntries(new FormData(form));
      const optionalBoolean = name => !fields[name] ? null : fields[name] === "true";
      pending = {
        checkin_id: crypto.randomUUID(), event: fields.event,
        observed_at: timestamp(fields.observed_at, fields.observed_occurrence),
        wake_at: fields.wake_at ? timestamp(fields.wake_at, fields.wake_occurrence) : null,
        status: fields.status,
        rating: fields.status === "completed" ? Number(fields.rating) : null,
        google_seen: fields.google_seen, acted_on: fields.acted_on,
        reported_late: form.elements.reported_late.checked,
        context: {
          academic_stress: fields.academic_stress || null,
          exercise_level: fields.exercise_level || null,
          illness: optionalBoolean("illness"),
          deadline_within_48h: optionalBoolean("deadline_within_48h"),
          caffeine_after_cutoff: optionalBoolean("caffeine_after_cutoff"),
          alcohol: fields.alcohol || null,
          medication_changed_or_missed: optionalBoolean("medication_changed_or_missed"),
          unusual_sleep: optionalBoolean("unusual_sleep")
        },
        note: fields.note.trim() || null
      };
    }
    entry.disabled = true;
    const saved = await api("/api/checkins", {method: "POST", body: JSON.stringify(pending)});
    result.textContent = `Saved at ${saved.captured_at}. Window: ${saved.window_status}.`;
    form.reset();
    setCurrentTime();
    pending = null;
    updatePrompt();
  } catch (error) {
    result.textContent = `${error.message} Your entries remain here so you can retry.`;
  } finally {
    entry.disabled = false;
    submit.disabled = false;
  }
});
