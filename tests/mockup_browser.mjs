// Drives a served mock-up in the installed Microsoft Edge and prints what it saw as one line of JSON.
// Usage: node tests/mockup_browser.mjs <mock-up URL, e.g. http://127.0.0.1:8765/> [record ids for the colour checks]
// MOCKUP_RED_URL: the same mock-up built with a red brand colour and larger text, served so that it follows
// its spec; MOCKUP_RED_SPEC: that spec, which this script changes to see the open page follow.
// MOCKUP_FILE: the built index.html, opened without a server (the walk-through kept by the browser tab alone).
// Called by tests/test_mockup.py, which makes the project, serves it and checks the result.
// Exit code 77: Edge could not be started (the test is then skipped).
import fs from "node:fs";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright-core";

const base = process.argv[2];
let browser, failure;
for (const channel of ["msedge", "chrome"]) {  // as tools/screenshot.mjs: Edge, or Chrome where there is no Edge
  try {
    browser = await chromium.launch({ channel, headless: true });
    break;
  } catch (e) {
    failure = failure || e;
  }
}
if (!browser) {
  console.error(String(failure));
  process.exit(77);
}
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
const out = { errors: [] };
page.on("pageerror", (e) => out.errors.push(String(e)));

// Every check starts from the sample data: the walk-through the server keeps for the room is reset first.
const open = async (hash) => {
  await page.request.post(base + "api/state", { data: { reset: true } });
  await keep(hash);
};
// A reload that keeps the walk-through, as a presenter's F5 or Update ready does.
const keep = async (hash, url) => {
  await page.goto("about:blank");
  await page.goto((url || base) + hash);
  await page.waitForSelector("#app > *");
};
const state = () => page.evaluate(() => ({
  dialog: !!document.querySelector(".modal"),
  screen: document.getElementById("app").dataset.screen,
  hash: location.hash,
  toasts: [...document.querySelectorAll(".toast")].map((t) => t.textContent),
}));

// ---- status colours: the class of the status chip on the detail screen, per record
out.chips = {};
for (const id of process.argv.slice(3)) {
  await open(`#/application-details?role=hr&record=${encodeURIComponent(id)}`);
  out.chips[id] = await page.locator(".status-bar .chip").getAttribute("class");
}

// ---- the project's own code runs after every screen is drawn
const own = () => page.evaluate(() => {
  const marks = document.querySelectorAll("#own-code");
  return { text: marks[0] ? marks[0].textContent : null, color: marks[0] ? getComputedStyle(marks[0]).color : null, count: marks.length };
});
await open("#/approvals?role=manager");
out.ownCode = { first: await own(), api: await page.evaluate(() => Object.keys(window.Mockup).sort()) };
await page.evaluate(() => { location.hash = "#/review-application?role=manager"; });
await page.waitForSelector('[data-el="button:Approve"]');
out.ownCode.next = await own();

// ---- dialogs: what the confirm button does
await open("#/review-application?role=manager");
await page.click('[data-el="button:Approve"]');
await page.waitForSelector(".modal");
await page.click('.modal [data-el="button:Confirm Approve"]');   // has a toast and nowhere to go
await page.waitForTimeout(150);
out.confirmWithoutTarget = await state();

await open("#/review-application?role=manager&dialog=info-dialog");
await page.click('.modal [data-el="button:OK"]');                 // the default button of a dialog without `confirm`
await page.waitForTimeout(150);
out.defaultOk = await state();

await open("#/review-application?role=manager&dialog=reject-dialog");
await page.fill('.modal [data-el="field:reason"] textarea', "Not this month");   // its required field
await page.click('.modal [data-el="button:Confirm Reject"]');     // goes to another screen
await page.waitForTimeout(150);
out.confirmWithTarget = await state();

await open("#/review-application?role=manager&dialog=reject-dialog");
await page.click(".modal-foot [data-close]:not([data-el])");      // Cancel
await page.waitForTimeout(150);
out.cancel = await state();

// ---- filters and search on a list
const listState = () => page.evaluate(() => ({
  rows: [...document.querySelectorAll("#content tbody tr[data-row]")].filter((tr) => !tr.hidden).map((tr) => tr.innerText.replace(/\s+/g, " ").trim()),
  pager: document.querySelector("#content .pager").textContent,
  noneShown: !document.querySelector("#content tr.none-match").hidden,
}));
await open("#/my-applications?role=employee");
out.listBefore = await listState();
await page.selectOption('[data-el="filter:Status"] select', "Approved");
out.listPickedNotApplied = await listState();              // nothing happens until Search is pressed
await page.click('[data-el="button:Search"]');
out.listFiltered = await listState();
await page.click('[data-el="button:Clear Filters"]');
out.listCleared = await listState();
out.filterAfterClear = await page.inputValue('[data-el="filter:Status"] select');

await open("#/approvals?role=manager");
await page.fill('[data-el="search:Employee"] input', "dAN");
await page.press('[data-el="search:Employee"] input', "Enter");   // part of the name, any letter case
out.searched = await listState();
await page.fill('[data-el="search:Employee"] input', "nobody of that name");
await page.click('[data-el="button:Search"]');
out.searchedNone = await listState();

// ---- what was typed survives a step change, and a new visit starts clean
await open("#/new-application?role=employee");
await page.fill('[data-el="field:reason"] textarea', "Family trip");
await page.selectOption('[data-el="field:leave_type"] select', { index: 2 });
const pickedType = await page.inputValue('[data-el="field:leave_type"] select');
await page.click('[data-el="tab:More"]');
await page.fill('[data-el="field:note"] input', "Back on Monday");
await page.click('[data-el="tab:Step 1"]');
out.typedBack = { reason: await page.inputValue('[data-el="field:reason"] textarea'),
                  typeKept: (await page.inputValue('[data-el="field:leave_type"] select')) === pickedType && pickedType !== "" };
await page.click('[data-el="tab:More"]');
out.typedStep2 = await page.inputValue('[data-el="field:note"] input');
await page.click('[data-el="menu:My Applications"]');
await page.waitForSelector('[data-el="title:My Leave Applications"]');
await page.click('[data-el="menu:New Application"]');
await page.waitForSelector('[data-el="field:reason"] textarea');
out.typedAfterLeaving = await page.inputValue('[data-el="field:reason"] textarea');

// ---- dialogs: the cursor, Esc, a click outside, and the browser's Back button
out.dialogs = {};
await open("#/approvals?role=manager");
await page.click('#content tbody tr[data-row] [data-el="action:Review"]');
await page.waitForSelector('[data-el="button:Approve"]');
await page.click('[data-el="button:Approve"]');
await page.waitForSelector(".modal");
out.dialogs.focus = await page.evaluate(() => `${document.activeElement.tagName} in ${document.activeElement.closest(".modal") ? "dialog" : "page"}`);
out.dialogs.role = await page.getAttribute(".modal", "role");
await page.keyboard.press("Escape");
await page.waitForTimeout(150);
out.dialogs.afterEscape = await state();
await page.click('[data-el="button:Approve"]');
await page.waitForSelector(".modal");
await page.mouse.click(15, 400);                                  // on the dimmed page, outside the dialog
await page.waitForTimeout(150);
out.dialogs.afterClickOutside = await state();
await page.click('[data-el="button:Approve"]');
await page.waitForSelector(".modal");
await page.click(".modal-foot [data-close]:not([data-el])");      // Cancel
await page.waitForTimeout(150);
await page.goBack();
await page.waitForTimeout(200);
out.dialogs.afterBack = await state();

// ---- required fields: pointed out on the first press, and the second press goes on
const required = () => page.evaluate(() => ({
  screen: document.getElementById("app").dataset.screen,
  dialog: !!document.querySelector(".modal"),
  page: new URLSearchParams(location.hash.split("?")[1] || "").get("page"),
  marked: [...document.querySelectorAll(".f-row.invalid")].map((row) => row.dataset.el),
  notes: [...document.querySelectorAll(".f-error")].map((n) => n.textContent),
  toastKinds: [...document.querySelectorAll(".toast")].map((t) => t.className),
  toasts: [...document.querySelectorAll(".toast")].map((t) => t.textContent),
  status: (document.querySelector(".status-bar .chip") || {}).textContent,
}));
out.required = {};
await open("#/review-application?role=manager&dialog=reject-dialog");
await page.click('.modal [data-el="button:Confirm Reject"]');     // the reason is required and empty
await page.waitForTimeout(150);
out.required.dialogFirst = await required();
await page.fill('.modal [data-el="field:reason"] textarea', "x");
out.required.dialogTyped = await required();                      // the mark goes as soon as it is filled
await page.fill('.modal [data-el="field:reason"] textarea', "");
await page.click('.modal [data-el="button:Confirm Reject"]');     // pressed again, still empty: goes on
await page.waitForSelector('[data-el="title:Pending Approvals"]');
out.required.dialogSecond = await required();

await open("#/new-application?role=employee&page=2");             // the last step, with Submit, has no required field
await page.click('[data-el="button:Submit"]');
await page.waitForTimeout(200);
out.required.formFirst = { ...(await required()), flagged: await page.evaluate(() => [...document.querySelectorAll(".tab.missing")].map((t) => t.textContent)) };
await page.click('[data-el="tab:Step 1"]');                       // the step that has them shows which
await page.waitForTimeout(150);
out.required.formFirstStep1 = await required();
await page.click('[data-el="tab:More"]');
await page.waitForTimeout(150);
await page.click('[data-el="button:Save as Draft"]');             // not the main button: no check
await page.waitForSelector('[data-el="title:My Leave Applications"]');
out.required.draft = await required();
await open("#/new-application?role=employee&page=2");
await page.click('[data-el="button:Submit"]');
await page.click('[data-el="button:Submit"]');
await page.waitForSelector('[data-el="title:My Leave Applications"]');
out.required.formSecond = await required();

// ---- a form in steps: Submit on the last step only, Next and Previous on the others
const stepButtons = () => page.evaluate(() => [...document.querySelectorAll("#content .form-buttons .btn")].map((b) => b.textContent));
out.steps = {};
await open("#/new-application?role=employee");
out.steps.first = await stepButtons();
await page.fill('[data-el="field:reason"] textarea', "Kept across steps");
await page.click('[data-el="button:Next"]');
await page.waitForTimeout(150);
out.steps.last = { buttons: await stepButtons(), page: await page.evaluate(() => new URLSearchParams(location.hash.split("?")[1]).get("page")),
  toasts: (await state()).toasts };
await page.click('[data-el="button:Previous"]');
await page.waitForTimeout(150);
out.steps.back = { buttons: await stepButtons(), reason: await page.inputValue('[data-el="field:reason"] textarea') };
await open("#/review-application?role=manager&dialog=reject-dialog");   // a dialog opened from a screen still works
out.steps.dialog = await page.evaluate(() => [...document.querySelectorAll(".modal-foot .btn")].map((b) => b.textContent));

// ---- a drop-down filtered by options_from {list, field, where}: it follows the walk-through
const carChoices = () => page.evaluate(() => [...document.querySelectorAll('[data-el="field:car"] option')].map((o) => o.textContent).slice(1));
await open("#/new-application?role=employee");
out.carChoices = { before: await carChoices() };

// ---- a detail screen shows a related list: the records that name the one shown
const related = () => page.evaluate(() => ({
  heading: (document.querySelector(".related-list h3") || {}).textContent,
  rows: [...document.querySelectorAll(".related-list tbody tr[data-row]")].map((tr) => tr.innerText.replace(/\s+/g, " ").trim()),
  empty: (document.querySelector(".related-list td.empty") || {}).textContent,
}));
out.related = {};
await open("#/car?role=manager&record=WXY%201234");
out.related.named = await related();
await open("#/car?role=manager&record=VBN%205678");
out.related.none = await related();

// ---- a step still to come with no word of its own reads Waiting
await open("#/application-details?role=hr&record=LV-T-1");
out.waitingWord = await page.evaluate(() => [...document.querySelectorAll('[data-el="section:Approval Progress"] tbody tr')].map((tr) => tr.lastElementChild.textContent));

// ---- a file field and a signature field answer a click, and keep what they hold across a step change
out.fakes = {};
await open("#/new-application?role=employee");
const fileText = () => page.evaluate(() => document.querySelector('[data-el="field:attachment"] .file-drop').innerText.replace(/\s+/g, " ").trim());
out.fakes.fileBefore = await fileText();
await page.click('[data-el="field:attachment"] .file-drop');
out.fakes.fileAttached = await fileText();
await page.click('[data-el="tab:More"]');
await page.waitForSelector('[data-el="field:sign"] .signature');   // the step is drawn a moment after the click
const signature = () => page.evaluate(() => document.querySelector('[data-el="field:sign"] .signature').innerText.trim());
out.fakes.signBefore = await signature();
await page.click('[data-el="field:sign"] .signature');
out.fakes.signed = await signature();
await page.click('[data-el="tab:Step 1"]');
await page.waitForSelector('[data-el="field:attachment"] .file-drop');
out.fakes.fileAfterStepChange = await fileText();
await page.click('[data-el="field:attachment"] [data-fake-clear]');
out.fakes.fileRemoved = await fileText();
await page.click('[data-el="tab:More"]');
await page.waitForSelector('[data-el="field:sign"] .signature');
out.fakes.signAfterStepChange = await signature();
await page.click('[data-el="field:sign"] .signature');
out.fakes.signCleared = await signature();

// ---- filters are still there after a visit to a record
await open("#/my-applications?role=employee");
await page.selectOption('[data-el="filter:Status"] select', "Approved");
await page.click('[data-el="button:Search"]');
const filteredRows = (await listState()).rows;
await page.click('#content tbody tr[data-row]:not([hidden]) [data-el="action:View"]');
await page.waitForSelector('[data-el="button:Back"]');
await page.click('[data-el="button:Back"]');
await page.waitForSelector('[data-el="title:My Leave Applications"]');
out.filtersKept = { before: filteredRows, after: (await listState()).rows, value: await page.inputValue('[data-el="filter:Status"] select') };

// ---- two messages at once sit above one another
await open("#/leave-types?role=hr");
await page.click('#content tbody tr[data-row] [data-el="action:Edit"]');
await page.click('#content tbody tr[data-row] [data-el="action:Edit"]');
await page.waitForTimeout(100);
out.twoToasts = await page.evaluate(() => [...document.querySelectorAll(".toast")].map((t) => { const r = t.getBoundingClientRect(); return [Math.round(r.top), Math.round(r.bottom)]; }));

// ---- the presenter's tools: together, apart from the system's own top bar, and clear of the page's buttons
out.tools = {};
await open("#/login");
out.tools.onLogin = await page.evaluate(() => ({ badge: document.querySelector(".fb-bar .fb-badge").textContent, viewAsShown: !document.querySelector(".fb-viewas").hidden }));
await open("#/application-details?role=employee");
out.tools.onScreen = await page.evaluate(() => ({
  viewAsShown: !document.querySelector(".fb-viewas").hidden, picked: document.querySelector(".fb-bar .role-switch").value,
  inTopBar: document.querySelectorAll(".topbar .role-switch, .topbar select").length,
}));
await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
await page.waitForTimeout(100);
out.tools.covered = await page.evaluate(() => {
  const bar = document.querySelector(".fb-bar").getBoundingClientRect();
  return [...document.querySelectorAll("#content .btn")].filter((b) => { const r = b.getBoundingClientRect(); return !(r.right < bar.left || r.left > bar.right || r.bottom < bar.top || r.top > bar.bottom); }).map((b) => b.textContent);
});
await page.selectOption(".fb-bar .role-switch", "manager");
await page.waitForSelector('[data-el="title:Pending Approvals"]');
out.tools.afterSwitch = await state();
// View as a role that starts on the screen already shown: the address does not change, and the screen is drawn again all the same.
await page.click('[data-el="menu:Pending Approvals"]');           // the address no longer names the role
await page.waitForTimeout(150);
await page.selectOption(".fb-bar .role-switch", "deputy");
await page.waitForTimeout(200);
out.tools.sameScreenSwitch = await page.evaluate(() => ({
  user: document.querySelector(".topbar .user").textContent, hash: location.hash, picked: document.querySelector(".fb-bar .role-switch").value,
}));
await page.click("#fb-toggle");                                   // in feedback mode the tools themselves are not commented on
await page.click(".fb-badge");
out.tools.commentBoxOnTools = (await page.locator(".fb-dialog").count()) > 0;
await page.click("#fb-toggle");

// ---- the presenter's chrome: dark charcoal with the Cobalt accent, never orange; it folds away, and the open
// Feedback panel lies over the page without moving it, so pins and boxes stay where they were put
const colour = (selector) => page.evaluate((sel) => { const s = getComputedStyle(document.querySelector(sel)); return { bg: s.backgroundColor, color: s.color }; }, selector);
out.chrome = {};
await open("#/approvals?role=manager");
out.chrome.bar = await colour(".fb-bar");
out.chrome.toggle = await colour("#fb-toggle");
out.chrome.css = await page.evaluate(() => [...document.styleSheets].flatMap((sh) => { try { return [...sh.cssRules].map((r) => r.cssText); } catch (e) { return []; } })
  .filter((t) => /fb-|cw-tag/.test(t)).join("\n"));
const pageAt = () => page.evaluate(() => { const r = document.querySelector("#content").getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.width)]; });
const before = await pageAt();
await page.click("#fb-toggle");
await page.waitForTimeout(150);
out.chrome.panel = await colour("#fb-panel");
out.chrome.room = { before, after: await pageAt(), overflow: await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1) };
await page.click("#fb-fold");                                     // folded away: the panel goes with it
await page.waitForTimeout(100);
const barState = () => page.evaluate(() => ({ width: Math.round(document.querySelector(".fb-bar").getBoundingClientRect().width), panel: !document.getElementById("fb-panel").hidden
  && getComputedStyle(document.getElementById("fb-panel")).display !== "none", feedback: document.body.classList.contains("fb-active") }));
out.chrome.folded = await barState();
await keep("#/approvals?role=manager");                           // remembered
out.chrome.foldedAfterReload = await barState();
await page.click("#fb-fold");
out.chrome.unfolded = await barState();

// ---- a red brand colour: the danger button is an outline, so Reject cannot be taken for Approve
const look = () => page.evaluate(() => ({
  outline: document.documentElement.classList.contains("danger-outline"),
  reject: getComputedStyle(document.querySelector('[data-el="button:Reject"]')).backgroundColor,
  approve: getComputedStyle(document.querySelector('[data-el="button:Approve"]')).backgroundColor,
}));
await open("#/review-application?role=manager");
out.danger = { blue: await look() };
const sizes = () => page.evaluate(() => Object.fromEntries(Object.entries({ menu: ".menu-item", table: ".datalist td", title: ".page-head h2", tools: ".fb-bar" })
  .map(([name, selector]) => [name, getComputedStyle(document.querySelector(selector)).fontSize])));
await open("#/approvals?role=manager");
out.textSize = { normal: await sizes() };
if (process.env.MOCKUP_RED_URL) {
  const red = process.env.MOCKUP_RED_URL;
  await page.goto("about:blank");
  await page.goto(red + "#/review-application?role=manager");
  await page.waitForSelector("#app > *");
  out.danger.red = await look();

  // ---- larger text, and an open mock-up that follows its spec
  await page.goto("about:blank");
  await page.goto(red + "#/approvals?role=manager");
  await page.waitForSelector('[data-el="title:Pending Approvals"]');
  out.textSize.large = await sizes();
  out.live = { before: await page.textContent(".page-head h2") };
  await page.waitForTimeout(3000);                                // the page has asked once which build it shows
  await page.click("#fb-toggle");                                 // the presenter is collecting comments
  await page.fill('[data-el="search:Employee"] input', "half-typed");
  const spec = fs.readFileSync(process.env.MOCKUP_RED_SPEC, "utf8");
  const renamed = spec.split("Pending Approvals").join("Waiting For Me");
  fs.writeFileSync(process.env.MOCKUP_RED_SPEC, renamed);
  try { await page.waitForSelector("#fb-update:not([hidden])", { timeout: 20000 }); } catch (e) { /* reported below as no button */ }
  await page.waitForTimeout(3000);                                // long enough for a reload, had there been one
  out.live.offered = {
    button: await page.isVisible("#fb-update"), title: await page.textContent(".page-head h2"),
    typed: await page.inputValue('[data-el="search:Employee"] input'),
  };
  await page.click("#fb-update");
  try {
    await page.waitForSelector('[data-el="title:Waiting For Me"]', { timeout: 20000 });
    await page.waitForSelector(".toast");
  } catch (e) { /* reported below as the old title */ }
  out.live.after = await page.textContent(".page-head h2");
  out.live.hash = await page.evaluate(() => location.hash);
  out.live.toasts = await page.evaluate(() => [...document.querySelectorAll(".toast")].map((t) => t.textContent));
  await page.waitForSelector("#fb-changes:not([hidden])", { timeout: 5000 }).catch(() => {});
  out.live.changes = await page.evaluate(() => [...document.querySelectorAll("#fb-changes .fb-wc-item .fb-text")].map((t) => t.textContent));
  out.live.feedbackOn = await page.evaluate(() => document.body.classList.contains("fb-active"));   // off after an update
  // Minimised, What changed leaves the screen free; What changed on the bar brings the list back.
  const wc = () => page.evaluate(() => ({ panel: !document.getElementById("fb-changes").hidden, on: document.getElementById("fb-changes-btn").classList.contains("on") }));
  await page.click("#wc-mini");
  out.live.wcMini = await wc();
  await page.click("#fb-changes-btn");
  out.live.wcBack = await wc();
  // A change with a mistake in it: the last good mock-up stays, and the room is told nothing.
  await page.waitForTimeout(3500);                                // the "updated" message has gone
  fs.writeFileSync(process.env.MOCKUP_RED_SPEC, renamed.replace("to: review-application", "to: nowhere"));
  await page.waitForTimeout(7000);                                // several times the page asks which build it shows
  out.live.broken = { title: await page.textContent(".page-head h2"), messages: await page.locator(".toast").count(), button: await page.isVisible("#fb-update") };
  fs.writeFileSync(process.env.MOCKUP_RED_SPEC, renamed);

  // ---- a live session: the bar says Live while the assistant is listening, and a comment shows what became of it
  const folder = process.env.MOCKUP_RED_FEEDBACK;
  const seen = async () => page.evaluate(() => ({ live: !document.querySelector(".fb-live").hidden, states: [...document.querySelectorAll("#fb-panel .fb-st")].map((s) => s.textContent),
    edits: document.querySelectorAll("#fb-panel [data-fb-edit]").length, locked: [...document.querySelectorAll("#fb-panel .fb-locked")].map((s) => s.textContent) }));
  const setStatus = (status, extra) => {
    const items = JSON.parse(fs.readFileSync(`${folder}/feedback.json`, "utf8"));
    Object.assign(items[items.length - 1], status ? { status } : {}, extra || {});
    fs.writeFileSync(`${folder}/feedback.json`, JSON.stringify(items));
  };
  const beat = () => fs.writeFileSync(`${folder}/live.json`, JSON.stringify({ started: "now", heartbeat: Date.now() / 1000, changes: [] }));
  await page.goto("about:blank");
  await page.goto(red + "#/leave-types?role=hr");
  await page.waitForSelector("#app > *");
  await page.click("#fb-toggle");
  await page.click('#app [data-el^="column:"]');
  await page.fill("#fb-text", "a comment in a live session");
  await page.click("#fb-save");
  await page.waitForTimeout(3200);
  out.session = { before: await seen() };
  beat();
  await page.waitForTimeout(3200);
  out.session.listening = await seen();
  for (const [name, status, extra] of [["working", "working"], ["applied", "applied", { note: "renamed" }], ["scope", "scope", { note: "possible CR", register_id: "R-031" }]]) {
    setStatus(status, extra);
    beat();
    await page.waitForTimeout(5600);                              // comments are asked for every five seconds
    out.session[name] = await seen();
  }
  out.session.sent = await page.evaluate(() => fetch("api/feedback").then((r) => r.text()));
}

// ---- a list that shows each role its own rows, and a row action for some roles only
out.rowsByRole = {};
for (const role of ["manager", "hr"]) {
  await open(`#/all-applications?role=${role}`);
  out.rowsByRole[role] = await listState();
}

// ---- what is waiting for whoever is signed in, read from each record's progress
out.waiting = {};
for (const role of ["manager", "hr"]) {
  await open(`#/my-tasks?role=${role}`);
  out.waiting[role] = await page.evaluate(() => ({   // a list with no rows at all has only its "empty" line
    rows: [...document.querySelectorAll("#content tbody tr[data-row]")].map((tr) => tr.innerText.replace(/\s+/g, " ").trim()),
    empty: (document.querySelector("#content tbody tr:not([data-row]):not([hidden]) td.empty") || {}).textContent,
  }));
}

// ---- status moves: a button with set_status moves the record, and everything drawn from it follows
const detailState = () => page.evaluate(() => ({
  screen: document.getElementById("app").dataset.screen,
  status: (document.querySelector(".status-bar .chip") || {}).textContent,
  chip: (document.querySelector(".status-bar .chip") || {}).className,
  buttons: [...document.querySelectorAll("#content .form-buttons .btn")].map((b) => b.textContent),
  timeline: [...document.querySelectorAll('[data-el="section:Approval Progress"] tbody tr')].map((tr) => [...tr.children].map((td) => td.textContent)),
  toasts: [...document.querySelectorAll(".toast")].map((t) => t.textContent),
}));
const visit = async (hash) => {  // moves within the page, without a reload
  await page.evaluate((h) => { location.hash = h; }, hash);
  await page.waitForTimeout(150);
};
const ids = (state) => state.rows.map((row) => row.split(" ")[0]);

await open("#/cars?role=manager");                                // the car Daniel Tan's application names
out.linkedBefore = (await listState()).rows;
await open("#/review-application?role=manager");                  // Daniel Tan's application, pending
out.moveBefore = await detailState();
await page.click('[data-el="button:Approve"]');
out.moveDialogOpen = await detailState();                         // opening the dialog moves nothing yet
await page.fill('.modal [data-el="field:comment"] textarea', "Enjoy the break");
await page.click('.modal [data-el="button:Confirm Approve"]');    // stays on the screen: it has nowhere to go
await page.waitForTimeout(150);
out.moveApproved = await detailState();
await page.click('[data-el="menu:Pending Approvals"]');
await page.waitForSelector('[data-el="title:Pending Approvals"]');
out.moveApprovalsAfter = ids(await listState());
await visit("#/cars?role=manager");                               // its car moved along (also_move)
out.linkedAfter = (await listState()).rows;
await visit("#/new-application?role=employee");                   // a car on loan leaves the filtered drop-down
out.carChoices = { ...(out.carChoices || {}), afterLoan: await carChoices() };
await visit("#/application-details?role=hr&record=LV-2026-011");  // another screen shows the same record
out.moveSeenElsewhere = await detailState();
await keep("#/review-application?role=manager");                  // a reload keeps the walk-through
out.moveAfterReload = { ...(await detailState()), reset: await page.isVisible("#fb-reset") };
await page.click("#fb-reset");                                    // Reset sample data asks first
await page.waitForSelector(".fb-ask");
out.resetAsk = await page.evaluate(() => ({ title: document.querySelector(".fb-ask .fb-title").textContent, action: document.querySelector('.fb-ask [data-ask="yes"]').textContent }));
await page.click('.fb-ask [data-ask="yes"]');
await page.waitForTimeout(200);
out.moveAfterReset = { ...(await detailState()), reset: await page.isVisible("#fb-reset") };

await open("#/review-application?role=manager&dialog=reject-dialog");
await page.fill('.modal [data-el="field:reason"] textarea', "Year-end freeze");
await page.click('.modal [data-el="button:Confirm Reject"]');     // goes to the approvals list
await page.waitForSelector('[data-el="title:Pending Approvals"]');
out.moveRejectedList = ids(await listState());
await visit("#/application-details?role=hr&record=LV-2026-011");
out.moveRejected = await detailState();

const figures = () => page.evaluate(() => Object.fromEntries([...document.querySelectorAll(".stat")].map((s) => [s.querySelector(".stat-label").textContent, s.querySelector(".stat-value").textContent])));
await open("#/my-applications?role=employee");
out.moveFiguresBefore = await figures();
await page.click('#content tbody tr[data-row] [data-el="action:View"]');   // the first row: pending
await page.waitForSelector('[data-el="button:Cancel Application"]');
await page.click('[data-el="button:Cancel Application"]');
await page.click('.modal [data-el="button:Yes, cancel it"]');     // a final status
await page.waitForSelector('[data-el="title:My Leave Applications"]');
out.moveFiguresAfter = await figures();
out.moveCancelledRow = (await listState()).rows[0];
await visit("#/application-details?role=employee&record=LV-2026-014");
out.moveCancelled = await detailState();

await open("#/approvals?role=manager");                           // an action on a row, which stays on the page
await page.click('#content tbody tr[data-row] [data-el="action:Approve now"]');
await page.waitForTimeout(150);
out.moveRowAction = { ...(await listState()), toasts: (await state()).toasts };

// A button that goes by the step the record is waiting at, and the task list that follows.
await open("#/my-tasks?role=manager");
await page.click('#content tbody tr[data-row] [data-el="action:View"]');
await page.waitForSelector('[data-el="button:Sign off"]');
await page.click('[data-el="button:Sign off"]');
await page.waitForTimeout(150);
out.waiting.signedOff = await detailState();
await page.click('[data-el="menu:My Tasks"]');
await page.waitForSelector('[data-el="title:My Tasks"]');
out.waiting.afterSignOff = { rows: await page.evaluate(() => [...document.querySelectorAll("#content tbody tr[data-row]")].map((tr) => tr.innerText)) };

// One button for several steps: where the record goes depends on the status it is in.
out.moveByStatus = {};
for (const [from, id] of [["On Hold", "LV-T-4"], ["Active Review", "LV-T-5"], ["Approved", "LV-2026-013"]]) {
  await open(`#/application-details?role=hr&record=${id}`);
  await page.click('[data-el="button:Resume"]');
  await page.waitForTimeout(150);
  out.moveByStatus[from] = await detailState();
}

// ---- a form on a record: the screen's own record, buttons that follow its status, a single tick box
const formState = () => page.evaluate(() => ({
  reason: (document.querySelector('[data-el="field:reason"] textarea') || {}).value,
  buttons: [...document.querySelectorAll("#content .form-buttons .btn")].map((b) => b.textContent),
  ticks: document.querySelectorAll('[data-el="field:urgent"] input[type=checkbox]').length,
  toasts: [...document.querySelectorAll(".toast")].map((t) => t.textContent),
}));
out.formOnRecord = {};
await open("#/edit-application?role=employee");
out.formOnRecord.byDefault = await formState();
await page.click('[data-el="field:urgent"] input[type=checkbox]');
out.formOnRecord.ticked = await page.isChecked('[data-el="field:urgent"] input[type=checkbox]');
await open("#/edit-application?role=employee&record=LV-2026-009");
out.formOnRecord.rejected = await formState();
await open("#/edit-application?role=employee");
await page.click('[data-el="button:Withdraw"]');
await page.waitForTimeout(150);
out.formOnRecord.withdrawn = await formState();
await visit("#/application-details?role=employee&record=LV-2026-014");
out.formOnRecord.statusAfter = (await detailState()).status;

// ---- Save on a form opened on a record keeps what was typed in that record, and adds no record
const countRecords = () => page.evaluate(() => window.Mockup.data.applications.length);
out.editSaved = { countBefore: await countRecords() };
await open("#/change-reason?role=employee&record=LV-2026-013");
await page.fill('[data-el="field:reason"] textarea', "Changed in the walk-through");
await page.fill('[data-el="field:note"] input', "Not a field of the list");
await page.click('[data-el="button:Save"]');
await page.waitForSelector('[data-el="title:My Leave Applications"]');
out.editSaved.countAfter = await countRecords();
out.editSaved.record = await page.evaluate(() => { const r = window.Mockup.data.applications.find((x) => x.id === "LV-2026-013"); return { reason: r.reason, note: "note" in r }; });
await visit("#/application-details?role=employee&record=LV-2026-013");
out.editSaved.shown = await page.evaluate(() => (document.querySelector('[data-el="field:reason"] .f-value') || {}).textContent);

// ---- a new form adds a record: it shows in the lists, counts and task lists it matches, and opens
const rowIds = (p) => p.evaluate(() => [...document.querySelectorAll("#content tbody tr[data-row]")].filter((tr) => !tr.hidden).map((tr) => tr.innerText.trim().split(/\s+/)[0]));
out.created = {};
await open("#/my-applications?role=employee");
out.created.figuresBefore = await figures();
await visit("#/new-application?role=employee");
await page.fill('[data-el="field:reason"] textarea', "Sister's wedding");
await page.selectOption('[data-el="field:leave_type"] select', "Emergency Leave");
await page.fill('[data-el="field:from"] input', "2026-12-01");
await page.click('[data-el="button:Next"]');                      // Submit is on the last step
await page.waitForSelector('[data-el="button:Submit"]');
await page.click('[data-el="button:Submit"]');                    // To Date is empty: pointed out first
await page.click('[data-el="button:Submit"]');                    // and the second press goes on
await page.waitForSelector('[data-el="title:My Leave Applications"]');
out.created.firstRow = (await listState()).rows[0];
out.created.figuresAfter = await figures();
out.created.toasts = (await state()).toasts;
await visit("#/application-details?role=employee&record=LV-2026-015");
out.created.detail = await detailState();
out.created.fields = await page.evaluate(() => Object.fromEntries(["reason", "leave_type", "from", "to", "employee"].map((f) => [f, (document.querySelector(`[data-el="field:${f}"] .f-value`) || {}).textContent])));
await visit("#/approvals?role=manager");
out.created.approvals = await rowIds(page);
await visit("#/my-tasks?role=manager");
out.created.tasks = await rowIds(page);
await keep("#/my-applications?role=employee");                    // kept through a reload
out.created.afterReload = (await listState()).rows[0];

// ---- the walk-through is shared: another browser sees the new record, acts on it, and both follow
const otherContext = await browser.newContext({ viewport: { width: 1280, height: 800 } });
const other = await otherContext.newPage();
other.on("pageerror", (e) => out.errors.push(String(e)));
await other.goto(base + "#/approvals?role=manager");
await other.waitForSelector('[data-el="title:Pending Approvals"]');
out.shared = { otherSees: await rowIds(other) };
await other.evaluate(() => { location.hash = "#/review-application?role=manager&record=LV-2026-015"; });
await other.waitForSelector('[data-el="button:Approve"]');
await other.click('[data-el="button:Approve"]');
await other.click('.modal [data-el="button:Confirm Approve"]');
await other.waitForTimeout(300);
try {   // the first browser, still on the employee's list, follows without a reload
  await page.waitForFunction(() => /LV-2026-015 .*Approved/.test(document.querySelector("#content tbody tr[data-row]").innerText.replace(/\s+/g, " ")), null, { timeout: 8000 });
} catch (e) { /* reported below */ }
out.shared.firstRowThere = (await listState()).rows[0];
out.shared.rolesKept = { here: await page.inputValue(".fb-bar .role-switch"), there: await other.inputValue(".fb-bar .role-switch") };
await other.click("#fb-reset");                                   // a reset is for everyone
await other.click('.fb-ask [data-ask="yes"]');
try {
  await page.waitForFunction(() => !document.querySelector("#content tbody").innerText.includes("LV-2026-015"), null, { timeout: 8000 });
} catch (e) { /* reported below */ }
out.shared.afterReset = (await listState()).rows.map((row) => row.split(" ")[0]);
await otherContext.close();

// ---- without a server, the browser tab keeps the walk-through by itself
if (process.env.MOCKUP_FILE) {
  const file = pathToFileURL(process.env.MOCKUP_FILE).href;
  await keep("#/new-application?role=employee&page=2", file);
  await page.click('[data-el="button:Submit"]');
  await page.click('[data-el="button:Submit"]');
  await page.waitForSelector('[data-el="title:My Leave Applications"]');
  out.fileOnly = { added: (await listState()).rows[0] };
  await page.reload();
  await page.waitForSelector('[data-el="title:My Leave Applications"]');
  out.fileOnly.afterReload = (await listState()).rows[0];
  await page.click("#fb-reset");
  await page.click('.fb-ask [data-ask="yes"]');
  await page.waitForTimeout(200);
  out.fileOnly.afterReset = (await listState()).rows[0];
}

// ---- custom work: tagged while presenting, hidden by the switch (remembered), never in a screenshot
const tags = () => page.evaluate(() => [...document.querySelectorAll(".cw-tag")].map((t) => ({ text: t.textContent, title: t.title })));
out.custom = {};
await open("#/my-applications?role=employee");
out.custom.dashboard = await tags();
out.custom.switchShown = await page.isVisible(".fb-custom");
await visit("#/new-application?role=employee");
out.custom.form = await tags();
await page.click(".fb-custom");                                   // off
out.custom.off = await tags();
await keep("#/my-applications?role=employee");
out.custom.offAfterReload = { tags: await tags(), checked: await page.isChecked("#fb-custom") };
await page.click(".fb-custom");                                   // on again
out.custom.onAgain = (await tags()).length;
await keep("#/my-applications?role=employee&clean=1");
out.custom.screenshot = (await tags()).length;

// ---- feedback mode: what is under the pointer is marked inside its own box, named in plain words, and Esc backs out
out.marking = {};
await open("#/approvals?role=manager");
await page.click("#fb-toggle");
await page.hover('th[data-el="column:Employee"]');
out.marking.hover = await page.evaluate(() => {
  const s = getComputedStyle(document.querySelector('th[data-el="column:Employee"]'));
  return { style: s.outlineStyle, offset: s.outlineOffset, others: document.querySelectorAll('#app [data-el]:hover:not(:has([data-el]:hover))').length };
});
await page.click('th[data-el="column:Employee"]');
await page.waitForSelector(".fb-dialog");
out.marking.box = await page.evaluate(() => ({
  title: document.querySelector(".fb-title").textContent, focus: document.activeElement.id,
  marked: [...document.querySelectorAll(".fb-target")].map((e) => e.dataset.el),
}));
await page.keyboard.press("Escape");
out.marking.afterEscape = await page.evaluate(() => ({ box: document.querySelectorAll(".fb-dialog").length, marked: document.querySelectorAll(".fb-target").length, stillOn: document.body.classList.contains("fb-active") }));
await page.click('[data-el="field:reason"], [data-el^="title:"]');
await page.waitForSelector(".fb-dialog");
out.marking.titleOfPage = await page.textContent(".fb-title");
await page.click(".fb-dialog", { position: { x: 10, y: 10 } });   // outside the box
out.marking.afterClickOutside = await page.locator(".fb-dialog").count();
// Any part of the screen, not only named fields, columns and buttons.
const titleOf = async (click) => {
  await click();
  await page.waitForSelector(".fb-dialog");
  const title = await page.textContent(".fb-title");
  await page.keyboard.press("Escape");
  return title;
};
out.anywhere = {
  sideMenu: await titleOf(() => page.click(".sidebar", { position: { x: 30, y: 500 } })),
  header: await titleOf(() => page.click(".topbar", { position: { x: 640, y: 20 } })),
  background: await titleOf(() => page.click("#content", { position: { x: 500, y: 600 } })),
  cell: await titleOf(() => page.click("#content tbody tr[data-row] td:nth-child(2)")),
};
await page.hover(".sidebar", { position: { x: 30, y: 500 } });
out.anywhere.hoverSideMenu = await page.evaluate(() => getComputedStyle(document.querySelector(".sidebar")).outlineStyle);
await page.click("#fb-toggle");
await open("#/my-applications?role=employee");
await page.click("#fb-toggle");
out.anywhere.figures = await titleOf(() => page.click('[data-el="stat:Pending"]'));
await page.click("#fb-toggle");

// ---- feedback: a comment the server does not take is kept, shown as not saved, and sent later
const feedbackState = () => page.evaluate(() => ({
  toggle: document.getElementById("fb-toggle").textContent,
  pins: document.querySelectorAll(".fb-pin").length,
  unsentPins: document.querySelectorAll(".fb-pin.unsent").length,
  panel: document.getElementById("fb-panel").innerText,
  errorToasts: [...document.querySelectorAll(".toast.error")].map((t) => t.textContent),
  kept: Object.keys(localStorage).filter((k) => k.startsWith("mock-feedback-unsent:")).flatMap((k) => JSON.parse(localStorage.getItem(k))).map((c) => c.text),
}));
const comment = async (text) => {
  if (!(await page.evaluate(() => document.body.classList.contains("fb-active")))) await page.click("#fb-toggle");
  await page.click('#app [data-el^="column:"]');
  await page.fill("#fb-text", text);
  await page.click("#fb-save");
  await page.waitForTimeout(300);
};
const serverDown = (route) => (route.request().method() === "POST" ? route.abort() : route.continue());

await open("#/approvals?role=manager");
await comment("saved while the server is up");
out.saved = await feedbackState();

await page.route("**/api/feedback", serverDown);
await comment("typed while the server is down");
out.failed = await feedbackState();

await open("#/approvals?role=manager");                           // a reload must not lose it
await page.click("#fb-toggle");
out.afterReload = await feedbackState();

await page.unroute("**/api/feedback", serverDown);
await page.click("#fb-retry");
await page.waitForTimeout(400);
out.afterRetry = await feedbackState();

// ---- a comment someone else saved (here: sent straight to the server) appears without a reload
out.numbersShown = await page.evaluate(() => [...document.querySelectorAll(".fb-pin")].map((p) => p.textContent));
await page.evaluate(() => fetch("api/feedback", { method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ screen: "approvals", element: "column:Employee", text: "from another laptop", author: "Someone else" }) }));
const pinsBefore = out.afterRetry.pins;
try {
  await page.waitForFunction((n) => document.querySelectorAll(".fb-pin").length > n, pinsBefore, { timeout: 12000 });
} catch (e) { /* reported below as no new pin */ }
out.afterOthers = await feedbackState();
out.numbersAfterOthers = await page.evaluate(() => [...document.querySelectorAll(".fb-pin")].map((p) => p.textContent));

// ---- Ctrl + Enter saves a comment, and a pin opens the comment it stands for
await page.click('#app [data-el^="column:"]');
await page.fill("#fb-text", "saved with the keyboard");
await page.keyboard.press("Control+Enter");
await page.waitForTimeout(400);
out.keyboardSave = { box: await page.locator(".fb-dialog").count(), panel: await page.evaluate(() => document.getElementById("fb-panel").innerText) };
await page.click("#fb-toggle");                                   // feedback mode off: the pins stay
await page.click(".fb-pin");
await page.waitForTimeout(150);
out.pinClick = await page.evaluate(() => ({ on: document.body.classList.contains("fb-active"), shown: document.querySelectorAll("#fb-panel .fb-item.flash").length }));
// a card in the panel is picked like a change in What changed: it stays tinted, and its element is outlined
await page.click("#fb-panel .fb-pick");
await page.waitForTimeout(150);
out.cardPick = await page.evaluate(() => ({ picked: document.querySelectorAll("#fb-panel .fb-pick.on").length,
  outlined: document.querySelectorAll("#app .fb-wc-flash, .fb-pin.fb-wc-flash, .fb-box.fb-wc-flash").length,
  dialog: document.querySelectorAll(".fb-dialog").length }));
out.pinPlaces = await page.evaluate(() => [...document.querySelectorAll(".fb-pin")].map((p) => Math.round(p.getBoundingClientRect().left)));

// ---- a comment that waits can be edited and deleted from the Feedback panel
out.commentEdits = {};
await open("#/leave-types?role=hr");
await comment("first thought");
const mineInPanel = (text) => page.locator("#fb-panel .fb-item", { hasText: text });
out.commentEdits.buttons = await mineInPanel("first thought").locator(".fb-act").allTextContents();
await mineInPanel("first thought").locator("[data-fb-edit]").click();
await page.waitForSelector(".fb-dialog");
out.commentEdits.boxText = await page.inputValue("#fb-text");
await page.fill("#fb-text", "second thought");
await page.click("#fb-save");
await page.waitForTimeout(400);
out.commentEdits.edited = await mineInPanel("second thought").innerText();
await mineInPanel("second thought").locator("[data-fb-remove]").click();
await page.waitForSelector(".fb-ask");
out.commentEdits.ask = await page.evaluate(() => ({ title: document.querySelector(".fb-ask .fb-title").textContent, action: document.querySelector('.fb-ask [data-ask="yes"]').textContent }));
await page.click('.fb-ask [data-ask="yes"]');
await page.waitForTimeout(400);
out.commentEdits.after = { panel: await page.evaluate(() => document.getElementById("fb-panel").innerText), pins: await page.locator(".fb-pin").count(),
  room: await page.evaluate(() => fetch("api/feedback").then((r) => r.json()).then((list) => list.map((c) => c.text))) };

// ---- the first load of the comments fails (the server restarting): what is typed still goes to the project,
// never into this browser for good
const roomTexts = () => page.evaluate(() => fetch("api/feedback").then((r) => r.json()).then((list) => list.map((c) => c.text)));
const loadDown = (route) => (route.request().method() === "GET" ? route.abort() : route.continue());
await page.route("**/api/feedback", loadDown);
await open("#/approvals?role=manager");
await page.waitForTimeout(300);
await page.unroute("**/api/feedback", loadDown);
await comment("typed after a failed load");
out.failedLoad = { room: await roomTexts(), errorToasts: (await feedbackState()).errorToasts,
  local: await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith("mock-feedback:"))
    .flatMap((k) => JSON.parse(localStorage.getItem(k))).map((c) => c.text)) };

// ---- two comments saved while the server is slow: each saved once, neither dropped
let slowOnce = true;
const slowServer = async (route) => {
  if (route.request().method() === "POST" && slowOnce) { slowOnce = false; await new Promise((r) => setTimeout(r, 1200)); }
  return route.continue();
};
await page.route("**/api/feedback", slowServer);
await comment("slow one");
await comment("right after");
await page.waitForTimeout(2000);
await page.unroute("**/api/feedback", slowServer);
out.slowServer = { room: await roomTexts(), kept: (await feedbackState()).kept };

// ---- a new request left half empty is not the twin of the open one at the same stage
out.fresh = {};
await open("#/new-application?role=employee");
// records an earlier check added with made-up statuses (copies of LV-2026-014) are not sample data: leave them out
await page.evaluate(() => { const list = Mockup.data.applications; for (let i = list.length - 1; i >= 0; i--) if (/^LV-T-/.test(list[i].id)) list.splice(i, 1); });
await page.fill('[data-el="field:from"] input', "2026-12-10");
await page.click('[data-el="button:Next"]');
await page.waitForSelector('[data-el="button:Submit"]');
await page.click('[data-el="button:Submit"]');
await page.click('[data-el="button:Submit"]');
await page.waitForSelector('[data-el="title:My Leave Applications"]');
out.fresh.id = (await listState()).rows[0].split(/\s+/)[0];
await visit(`#/application-details?role=employee&record=${out.fresh.id}`);
out.fresh.fields = await page.evaluate(() => Object.fromEntries(["reason", "leave_type", "from"].map((f) => [f, (document.querySelector(`[data-el="field:${f}"] .f-value`) || {}).textContent])));
out.fresh.others = await page.evaluate(() => Mockup.data.applications.map((x) => ({ id: x.id, status: x.status, reason: x.reason })));

// ---- a row action that opens a dialog: on that row's record, so its confirm button moves that row
const staffRows = () => page.evaluate(() => [...document.querySelectorAll("#content tbody tr[data-row]")].filter((tr) => !tr.hidden)
  .map((tr) => tr.innerText.replace(/\s+/g, " ").trim()));
out.rowDialog = {};
await open("#/staff?role=manager");
out.rowDialog.link = await page.evaluate(() => { const a = document.querySelector('#content tbody tr[data-row] [data-el="action:Suspend"]');
  return { go: a.dataset.go || null, dialog: a.dataset.dialog || null, record: a.dataset.record }; });
await page.click('#content tbody tr[data-row] [data-el="action:Suspend"]');
await page.waitForSelector(".modal");
out.rowDialog.opened = await state();
await page.click('.modal [data-el="button:Suspend"]');
await page.waitForTimeout(200);
out.rowDialog.after = { ...(await state()), first: (await staffRows())[0] };

// ---- a filter whose values include the word All: "All" once, as no filter; the real value is a choice of its own
out.allFilter = {};
await open("#/staff?role=manager");
out.allFilter.options = await page.evaluate(() => [...document.querySelectorAll('[data-filter="office"] option')].map((o) => [o.textContent, o.value]));
await page.selectOption('[data-filter="office"]', "All");
await page.click('[data-el="button:Search"]');
out.allFilter.picked = (await staffRows()).map((row) => row.split(" ").slice(4, 5)[0]);
await page.click('[data-el="button:Clear Filters"]');
out.allFilter.cleared = { rows: (await staffRows()).length, value: await page.inputValue('[data-filter="office"]') };
// A search box on a field that has no column: named in words, never by the field's id.
out.searchName = await page.evaluate(() => [...document.querySelectorAll('[data-el^="search:"]')].map((s) => [s.dataset.el, s.querySelector("label").textContent]));

// ---- the presenter's tools never cover what is on a page: everything can be scrolled clear of the bar and of the
// open Feedback panel, at the bottom right too (the last buttons, the last row and its action), on a computer and a phone
const covered = () => page.evaluate(() => {
  window.scrollTo(0, document.documentElement.scrollHeight);
  const parts = [...document.querySelectorAll("#content .btn, #content a.link, #content tbody tr[data-row]:last-of-type td")];
  const seen = parts.filter((el) => { const r = el.getBoundingClientRect(); return r.width && r.height && r.top >= 0 && r.bottom <= window.innerHeight && r.left >= 0 && r.right <= window.innerWidth; });
  const under = seen.filter((el) => { const r = el.getBoundingClientRect(); const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !hit || !!hit.closest(".fb-tools"); });
  const label = (el) => el.dataset.el || el.textContent.trim();
  const last = document.querySelector("#content .form-buttons .btn:last-child");
  return { under: under.map(label), lastButtonSeen: !!last && seen.includes(last), panel: !document.getElementById("fb-panel").hidden };
});
// Comments enough for a long Feedback panel, as after a session (served for this page only: the room's file is not touched).
const many = [...Array(8).keys()].map((n) => ({ id: `FB-9${n}`, screen: "staff", element: "column:Name", text: `A comment long enough to take two lines of the panel, number ${n}`,
  author: "Someone", time: "2026-11-07T10:00:00", version: "0.1" }));
many.push({ id: "FB-980", screen: "staff", element: "header:connection", text: "on the project's own part of the top bar", time: "2026-11-07T10:00:00", version: "0.1" });
many.push({ id: "FB-981", screen: "staff", element: "search:staff_no", text: "saved under the field's id", time: "2026-11-07T10:00:00", version: "0.1" });
const longPanel = (route) => (route.request().method() === "GET" ? route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(many) }) : route.continue());
out.room = {};
for (const [name, size] of [["desktop", { width: 1280, height: 800 }], ["phone", { width: 375, height: 812 }]]) {
  await page.setViewportSize(size);
  for (const hash of ["#/staff?role=manager", "#/application-details?role=employee"]) {
    await open(hash);
    out.room[`${name} ${hash}`] = await covered();
  }
  await page.route("**/api/feedback", longPanel);
  await open("#/staff?role=manager");
  await page.click("#fb-toggle");
  await page.waitForTimeout(300);
  out.room[`${name} feedback`] = await covered();
  if (name === "desktop") {
    // In Feedback mode the last row's action takes a comment like anything else.
    const actions = page.locator('#content tbody tr[data-row] [data-el="action:Suspend"]');
    await actions.last().click({ timeout: 5000 });
    await page.waitForSelector(".fb-dialog");
    out.actionComment = await page.textContent(".fb-title");
    await page.keyboard.press("Escape");
    // The Feedback panel names each comment by what it is about: a part the project's code added by its own name.
    out.panelNames = await page.evaluate(() => [...document.querySelectorAll("#fb-panel .fb-el")].map((e) => e.textContent));
    await page.click('[data-el="header:connection"]');
    await page.waitForSelector(".fb-dialog");
    out.connectionComment = await page.textContent(".fb-title");
    await page.keyboard.press("Escape");
  }
  await page.unroute("**/api/feedback", longPanel);
}

// ---- a file field on a phone says what a phone does: take a photo or choose a file
await page.setViewportSize({ width: 375, height: 812 });
await open("#/new-application?role=employee");
out.fakes.fileOnPhone = await fileText();
await page.setViewportSize({ width: 1280, height: 800 });
await page.addStyleTag({ content: ".content { flex: 0 0 390px !important; }" });  // a phone frame, drawn by a project's own code
await page.evaluate(() => window.dispatchEvent(new Event("resize")));
out.fakes.fileInPhoneFrame = await fileText();
await open("#/new-application?role=employee");
out.fakes.fileOnComputer = await fileText();

// ---- the process flow: a step that names its role and status by id shows their names
await open("#/__flow?role=manager");
out.flow = await page.evaluate(() => [...document.querySelectorAll(".flow-step")].map((s) => [s.querySelector(".flow-role").textContent,
  s.querySelector(".flow-status .chip").textContent, s.querySelector(".flow-status .chip").className]));

// ---- carrying the open record: a button to a screen of the same data opens it on the record shown
const shownRecord = () => page.evaluate(() => ({
  screen: document.getElementById("app").dataset.screen,
  record: new URLSearchParams(location.hash.split("?")[1] || "").get("record") || "",
}));
await open("#/application-details?role=manager&record=LV-2026-013");
await page.click('[data-el="button:Open Review"]');
await page.waitForTimeout(150);
out.carryButton = await shownRecord();
await open("#/application-details?role=manager&record=LV-2026-009");
await page.click('[data-el="button:Review It"]');
await page.waitForSelector(".modal");
await page.click('.modal [data-el="button:Go to Review"]');
await page.waitForTimeout(150);
out.carryDialog = await shownRecord();
await open("#/application-details?role=manager");
await page.click('[data-el="button:Open Review"]');
await page.waitForTimeout(150);
out.carryDefault = await shownRecord();
await open("#/application-details?role=employee&record=LV-2026-013");
await page.click('[data-el="button:Back"]');
await page.waitForTimeout(150);
out.carryBack = await state();

await browser.close();
console.log(JSON.stringify(out));
