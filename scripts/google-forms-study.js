// Paste into a new Apps Script project. Run setupStudy(), then exportSnapshot().
// No deployment or scheduled trigger is needed. See docs/data-collection-protocol.md.
const STUDY = {
  timezone: "America/Los_Angeles",
  afternoonStartHours: 5,
  afternoonEndHours: 9,
  caffeineCutoff: null, // Optional HH:MM; choose before creating the Form.
};
const STATE_KEY = "ai-health-coach-forms-v1";
const EVENTS = ["Morning readiness", "Afternoon energy", "Overall energy"];
const PROMPTS = [
  ["How capable do I feel of handling the demands planned for today?", "1: unable to handle ordinary demands · 5: essentials take noticeable effort · 10: fully capable of a highly demanding day"],
  ["How alert and energized do I feel right now?", "1: barely able to stay alert · 5: enough for routine work, with dips · 10: unusually high alertness and usable energy"],
  ["Looking back, how much usable energy did I have across the day?", "1: almost no usable energy · 5: enough for essentials, but limited · 10: abundant, sustained energy"],
];

function configuration() {
  if (!STUDY.timezone || !Number.isFinite(STUDY.afternoonStartHours) ||
      !Number.isFinite(STUDY.afternoonEndHours) || STUDY.afternoonStartHours < 0 ||
      STUDY.afternoonEndHours <= STUDY.afternoonStartHours || STUDY.afternoonEndHours > 168 ||
      (STUDY.caffeineCutoff !== null && !/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(STUDY.caffeineCutoff))) {
    throw new Error("Invalid study configuration; no Form was created.");
  }
  // Check identifier syntax here; Python's ZoneInfo validates actual IANA membership.
  if (typeof STUDY.timezone !== "string" || !/^(?:UTC|[A-Za-z_]+\/[A-Za-z0-9_+\-/]+)$/.test(STUDY.timezone)) {
    throw new Error("Use an IANA timezone such as America/Los_Angeles.");
  }
  return {
    version: "forms-config-1.0.0", timezone: STUDY.timezone,
    caffeine_cutoff_local_time: STUDY.caffeineCutoff,
    windows: [
      {event: "wake", trigger: "manual", opens_after_wake_hours: null, closes_after_wake_hours: null},
      {event: "afternoon", trigger: "relative_to_wake", opens_after_wake_hours: STUDY.afternoonStartHours, closes_after_wake_hours: STUDY.afternoonEndHours},
      {event: "day_close", trigger: "manual", opens_after_wake_hours: null, closes_after_wake_hours: null},
    ],
  };
}

function schema(form) {
  return JSON.stringify(form.getItems().map(item => {
    const entry = {id: String(item.getId()), type: String(item.getType()), title: item.getTitle(), help: item.getHelpText()};
    if (item.getType() === FormApp.ItemType.MULTIPLE_CHOICE) {
      const choice = item.asMultipleChoiceItem();
      entry.required = choice.isRequired();
      entry.choices = choice.getChoices().map(value => ({value: value.getValue(), page: value.getGotoPage() ? String(value.getGotoPage().getId()) : null}));
    } else if (item.getType() === FormApp.ItemType.SCALE) {
      const scale = item.asScaleItem();
      entry.required = scale.isRequired();
      entry.lower = scale.getLowerBound(); entry.upper = scale.getUpperBound();
    } else if (item.getType() === FormApp.ItemType.PAGE_BREAK) {
      const page = item.asPageBreakItem();
      entry.next = page.getGoToPage() ? String(page.getGoToPage().getId()) : null;
      entry.navigation = String(page.getPageNavigationType());
    } else if (item.getType() === FormApp.ItemType.TEXT) {
      entry.required = item.asTextItem().isRequired();
    } else if (item.getType() === FormApp.ItemType.PARAGRAPH_TEXT) {
      entry.required = item.asParagraphTextItem().isRequired();
    }
    return entry;
  }));
}

function setupStudy() {
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const properties = PropertiesService.getScriptProperties();
    const existing = properties.getProperty(STATE_KEY);
    if (existing) { return showLinks(JSON.parse(existing)); }
    const config = configuration();
    const folder = DriveApp.createFolder("AI Health Coach — private study");
    const screenshots = folder.createFolder("screenshots");
    const snapshots = folder.createFolder("snapshots");
    const form = FormApp.create("Personal sleep and readiness check-in", false);
    form.setDescription("Private N-of-1 study. Record your own rating before looking at Google guidance when possible. Optional context can be left blank. No assumed wake time.")
      .setAllowResponseEdits(false).setLimitOneResponsePerUser(false)
      .setPublishingSummary(false).setCollectEmail(false);
    const sheet = SpreadsheetApp.create("AI Health Coach — responses");
    sheet.setSpreadsheetTimeZone(config.timezone);
    form.setDestination(FormApp.DestinationType.SPREADSHEET, sheet.getId());
    DriveApp.getFileById(form.getId()).moveTo(folder);
    DriveApp.getFileById(sheet.getId()).moveTo(folder);
    const fields = {};
    const register = (name, item) => { fields[String(item.getId())] = name; return item; };
    const radio = (name, title, choices, required = false) => register(name,
      form.addMultipleChoiceItem().setTitle(title).setChoiceValues(choices).setRequired(required));
    const status = radio("status", "Entry status", ["Completed", "Skipped", "Missing"], true);
    const completed = form.addPageBreakItem().setTitle("Choose a rating");
    const event = radio("event_completed", "Check-in", EVENTS, true);
    const ratingPages = EVENTS.map((title, index) => {
      const page = form.addPageBreakItem().setTitle(title);
      register("rating_" + index, form.addScaleItem().setTitle(PROMPTS[index][0])
        .setHelpText(PROMPTS[index][1]).setBounds(1, 10).setLabels("1", "10").setRequired(true));
      return page;
    });
    const absent = form.addPageBreakItem().setTitle("Absent rating");
    radio("event_absent", "Which check-in was skipped or missing?", EVENTS, true);
    const common = form.addPageBreakItem().setTitle("Timing and optional context");
    status.setChoices([status.createChoice("Completed", completed), status.createChoice("Skipped", absent), status.createChoice("Missing", absent)]);
    event.setChoices(EVENTS.map((title, index) => event.createChoice(title, ratingPages[index])));
    // PageBreak navigation governs the page BEFORE that break, not its own page.
    ratingPages[1].setGoToPage(common);
    ratingPages[2].setGoToPage(common);
    absent.setGoToPage(common);
    const timeHelp = "Optional ISO timestamp with UTC offset, e.g. 2026-11-01T01:30:00-08:00 (second repeated hour). Never enter a bare local time.";
    const timeValidation = FormApp.createTextValidation()
      .requireTextMatchesPattern("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2}(\\.[0-9]+)?)?(Z|[+-][0-9]{2}:[0-9]{2})$")
      .setHelpText("Leave blank or enter an ISO timestamp with UTC offset, such as 2024-11-03T01:30:00-08:00.").build();
    register("observed_at", form.addTextItem().setTitle("Earlier time this rating describes (optional)")
      .setHelpText("Leave blank for the actual submission time. " + timeHelp).setValidation(timeValidation));
    register("wake_at", form.addTextItem().setTitle("Actual wake time (optional)").setHelpText(timeHelp).setValidation(timeValidation));
    radio("reported_late", "Are you recording this late?", ["Yes", "No"]);
    radio("google_seen", "Google guidance seen before this rating?", ["Yes", "No", "Unsure"], true);
    radio("acted_on", "Recommendation acted on?", ["No", "Partly", "Yes", "Unknown"], true);
    radio("academic_stress", "Academic stress", ["Low", "Medium", "High"]);
    radio("exercise_level", "Exercise", ["None", "Light", "Moderate", "Hard"]);
    radio("illness", "Illness", ["Yes", "No"]);
    radio("deadline_within_48h", "Exam or deadline within 48 hours", ["Yes", "No"]);
    radio("alcohol", "Alcohol", ["None", "One drink", "Two or more"]);
    radio("medication_changed_or_missed", "Medication changed or missed", ["Yes", "No"]);
    radio("unusual_sleep", "Unusual sleep circumstances", ["Yes", "No"]);
    if (config.caffeine_cutoff_local_time !== null) {
      radio("caffeine_after_cutoff", "Caffeine at or after " + config.caffeine_cutoff_local_time + " on the rating's local date (" + config.timezone + ")", ["Yes", "No"]);
    }
    register("note", form.addParagraphTextItem().setTitle("Short note (optional, at most 2000 characters)")
      .setValidation(FormApp.createParagraphTextValidation().requireTextLengthLessThanOrEqualTo(2000).build()));
    const state = {form_id: form.getId(), sheet_id: sheet.getId(), folder_id: folder.getId(), screenshots_id: screenshots.getId(), snapshots_id: snapshots.getId(), configuration: config, fields, schema: schema(form)};
    properties.setProperty(STATE_KEY, JSON.stringify(state));
    return showLinks(state);
  } finally { lock.releaseLock(); }
}

function showLinks(state) {
  const form = FormApp.openById(state.form_id);
  const links = {form_editor: form.getEditUrl(), responses: SpreadsheetApp.openById(state.sheet_id).getUrl(), folder: DriveApp.getFolderById(state.folder_id).getUrl()};
  console.log(JSON.stringify(links));
  return links;
}

function exportSnapshot() {
  const stored = PropertiesService.getScriptProperties().getProperty(STATE_KEY);
  if (!stored) { throw new Error("Run setupStudy first."); }
  const state = JSON.parse(stored);
  const form = FormApp.openById(state.form_id);
  if (schema(form) !== state.schema || form.canEditResponse() || form.isPublishingSummary()) {
    throw new Error("Form definition or history settings changed. Restore them or start a new study Form; do not relabel old responses.");
  }
  const responses = form.getResponses().map(response => {
    const values = {};
    response.getItemResponses().forEach(item => {
      const name = state.fields[String(item.getItem().getId())];
      if (!name) { throw new Error("Response contains an unrecognized question."); }
      values[name] = String(item.getResponse());
    });
    const event = values[values.status === "Completed" ? "event_completed" : "event_absent"];
    const index = EVENTS.indexOf(event);
    if (index < 0) { throw new Error("Response has no recognized event."); }
    const answers = {event, status: values.status, rating: values.status === "Completed" ? (values["rating_" + index] || "") : ""};
    Object.keys(values).forEach(name => {
      if (!name.startsWith("rating_") && name !== "event_completed" && name !== "event_absent" && name !== "status") { answers[name] = values[name]; }
    });
    return {response_id: response.getId(), submitted_at: response.getTimestamp().toISOString(), answers};
  });
  const snapshot = {kind: "google_forms_checkins", schema_version: 1, form_id: state.form_id, exported_at: new Date().toISOString(), configuration: state.configuration, responses};
  const name = "checkins-" + snapshot.exported_at.replace(/[:.]/g, "-") + ".json";
  const blob = Utilities.newBlob(JSON.stringify(snapshot, null, 2), "application/json", name);
  const file = DriveApp.getFolderById(state.snapshots_id).createFile(blob);
  console.log(JSON.stringify({snapshot: file.getUrl(), responses: responses.length}));
  return snapshot;
}
