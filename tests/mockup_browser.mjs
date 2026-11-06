// Drives a served mock-up in the installed Microsoft Edge and prints what it saw as one line of JSON.
// Usage: node tests/mockup_browser.mjs <mock-up URL, e.g. http://127.0.0.1:8765/>
// Called by tests/test_mockup.py, which makes the project, serves it and checks the result.
// Exit code 77: Edge could not be started (the test is then skipped).
import { chromium } from "playwright-core";

const base = process.argv[2];
let browser;
try {
  browser = await chromium.launch({ channel: "msedge", headless: true });
} catch (e) {
  console.error(String(e));
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

await browser.close();
console.log(JSON.stringify(out));
