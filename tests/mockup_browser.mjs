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
