// Drives a served mock-up in the installed Microsoft Edge and prints what it saw as one line of JSON.
// Usage: node tests/mockup_browser.mjs <mock-up URL, e.g. http://127.0.0.1:8765/>
// Called by tests/test_mockup.py, which makes the project, serves it and checks the result.
// Exit code 77: Edge could not be started (the test is then skipped).
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

const open = async (hash) => {
  await page.goto("about:blank");
  await page.goto(base + hash);
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
await visit("#/application-details?role=hr&record=LV-2026-011");  // another screen shows the same record
out.moveSeenElsewhere = await detailState();
await open("#/review-application?role=manager");                  // a reload puts the sample data back
out.moveAfterReload = await detailState();

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

await browser.close();
console.log(JSON.stringify(out));
