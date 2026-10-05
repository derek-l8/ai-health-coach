// An offline Apps Script API double, not evidence of real Google execution.
import {readFileSync} from "node:fs";
import {fileURLToPath} from "node:url";
import vm from "node:vm";

export function createStudy() {
  const source = readFileSync(new URL("../../scripts/google-forms-study.js", import.meta.url), "utf8");
  const properties = new Map();
  const files = [];
  const logs = [];
  const folders = new Map();
  let form;
  let sheet;
  let released = false;
  class Item {
    constructor(type) { this.type = type; this.id = form.items.length + 1; this.title = ""; this.help = ""; this.required = false; this.next = null; form.items.push(this); }
    getId() { return this.id; }
    getType() { return this.type; }
    getTitle() { return this.title; }
    getHelpText() { return this.help; }
    setTitle(value) { this.title = value; return this; }
    setHelpText(value) { this.help = value; return this; }
    setRequired(value) { this.required = value; return this; }
    setValidation(value) { this.validation = value; return this; }
    isRequired() { return this.required; }
    createChoice(value, page = null) { return {getValue: () => value, getGotoPage: () => page}; }
    setChoiceValues(values) { return this.setChoices(values.map(value => this.createChoice(value))); }
    setChoices(values) { this.choices = values; return this; }
    getChoices() { return this.choices; }
    setGoToPage(value) { this.next = value; return this; }
    getGoToPage() { return this.next; }
    getPageNavigationType() { return this.next ? "GO_TO_PAGE" : "CONTINUE"; }
    setBounds(lower, upper) { this.lower = lower; this.upper = upper; return this; }
    getLowerBound() { return this.lower; }
    getUpperBound() { return this.upper; }
    setLabels(lower, upper) { this.labels = [lower, upper]; return this; }
    asMultipleChoiceItem() { if (this.type !== "MULTIPLE_CHOICE") throw Error("wrong cast"); return this; }
    asScaleItem() { if (this.type !== "SCALE") throw Error("wrong cast"); return this; }
    asPageBreakItem() { if (this.type !== "PAGE_BREAK") throw Error("wrong cast"); return this; }
    asTextItem() { if (this.type !== "TEXT") throw Error("wrong cast"); return this; }
    asParagraphTextItem() { if (this.type !== "PARAGRAPH_TEXT") throw Error("wrong cast"); return this; }
  }
  function folder(name) {
    const id = "synthetic-folder-" + folders.size;
    const value = {name, getId: () => id, getUrl: () => "https://example.invalid/" + id,
      createFolder: child => folder(child), createFile: blob => {
        files.push(blob); return {getUrl: () => "https://example.invalid/snapshot-" + files.length};
      }};
    folders.set(id, value); return value;
  }
  const services = {
    FormApp: {
      ItemType: {MULTIPLE_CHOICE: "MULTIPLE_CHOICE", SCALE: "SCALE", PAGE_BREAK: "PAGE_BREAK", TEXT: "TEXT", PARAGRAPH_TEXT: "PARAGRAPH_TEXT"},
      DestinationType: {SPREADSHEET: "SPREADSHEET"},
      create: (title, published) => {
        form = {title, published, items: [], responses: [],
          getId: () => "synthetic-form-only", getEditUrl: () => "https://example.invalid/form",
          getItems() { return this.items; }, getResponses() { return this.responses; },
          setDescription(value) { this.description = value; return this; },
          setAllowResponseEdits(value) { this.edits = value; return this; },
          setLimitOneResponsePerUser(value) { this.limit = value; return this; },
          setPublishingSummary(value) { this.summary = value; return this; },
          setCollectEmail(value) { this.email = value; return this; },
          canEditResponse() { return this.edits; }, isPublishingSummary() { return this.summary; },
          setDestination(kind, id) { this.destination = [kind, id]; return this; },
          addMultipleChoiceItem: () => new Item("MULTIPLE_CHOICE"),
          addScaleItem: () => new Item("SCALE"), addPageBreakItem: () => new Item("PAGE_BREAK"),
          addTextItem: () => new Item("TEXT"), addParagraphTextItem: () => new Item("PARAGRAPH_TEXT"),
        }; return form;
      },
      openById: id => { if (id !== form.getId()) throw Error("unknown form"); return form; },
      createTextValidation: () => ({requireTextMatchesPattern(value) { this.pattern = value; return this; }, setHelpText(value) { this.help = value; return this; }, build() { return {pattern: this.pattern, help: this.help}; }}),
      createParagraphTextValidation: () => ({requireTextLengthLessThanOrEqualTo(value) { this.maximum = value; return this; }, build() { return {maximum: this.maximum}; }}),
    },
    SpreadsheetApp: {
      create: title => {
        sheet = {title, getId: () => "synthetic-sheet", getUrl: () => "https://example.invalid/sheet",
          setSpreadsheetTimeZone(value) { this.timezone = value; return this; }};
        return sheet;
      },
      openById: () => sheet,
    },
    DriveApp: {createFolder: folder, getFolderById: id => folders.get(id),
      getFileById: () => ({moveTo: () => {}})},
    PropertiesService: {getScriptProperties: () => ({getProperty: name => properties.get(name) || null,
      setProperty: (name, value) => properties.set(name, value)})},
    LockService: {getScriptLock: () => ({waitLock: () => {}, releaseLock: () => { released = true; }})},
    Utilities: {newBlob: (content, mime, name) => ({content, mime, name})},
    console: {log: value => logs.push(value)},
    Date: class extends Date { constructor(...args) { super(...(args.length ? args : ["2024-11-03T18:00:00.000Z"])); } },
  };
  const context = vm.createContext(services);
  vm.runInContext(source, context);
  const evaluate = code => vm.runInContext(code, context);
  const state = () => JSON.parse(properties.get("ai-health-coach-forms-v1"));
  const response = (values, id = "synthetic-response-1", timestamp = "2024-11-03T09:30:00.000Z") => {
    const fields = state().fields;
    const defaults = Object.fromEntries(form.items.filter(item => ["TEXT", "PARAGRAPH_TEXT"].includes(item.type)).map(item => [fields[String(item.id)], ""]));
    return {getId: () => id, getTimestamp: () => new Date(timestamp),
      getItemResponses: () => Object.entries({...defaults, ...values}).map(([name, value]) => {
        const item = form.items.find(candidate => fields[String(candidate.id)] === name);
        if (!item) throw Error("mock response references unknown field");
        return {getItem: () => item, getResponse: () => value};
      })};
  };
  return {evaluate, state, response, files, logs, folders, get form() { return form; }, get sheet() { return sheet; }, get released() { return released; }};
}

if (process.argv[1] === fileURLToPath(import.meta.url) && process.argv[2] === "--snapshot") {
  const study = createStudy();
  study.evaluate("setupStudy()");
  study.form.responses.push(study.response({status: "Completed", event_completed: "Morning readiness", rating_0: 7, google_seen: "No", acted_on: "Unknown"}));
  process.stdout.write(JSON.stringify(study.evaluate("exportSnapshot()")));
}
