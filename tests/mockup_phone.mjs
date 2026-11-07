// Opens a built mock-up whose employee screens are phone screens (device: phone) and checks what the engine draws
// for a phone: the phone with its tab bar and no top bar, lists as rows, Back, a dialog as a sheet from the
// bottom, a camera field, a filter that opens on a value, a change that moves the records naming the one moved,
// a desktop screen beside them, the links of a new comment to earlier ones, and "What changed since" on a page
// opened afresh. Prints what it saw as one line of JSON.
// Usage: node tests/mockup_phone.mjs <built index.html>
// Called by tests/test_mockup.py. Exit code 77: Edge could not be started (the test is then skipped).
import { pathToFileURL } from "node:url";
import { chromium } from "playwright-core";

const [file] = process.argv.slice(2);
let browser, failure;
for (const channel of ["msedge", "chrome"]) {
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
const seen = { errors: [] };
const page = await browser.newPage({ viewport: { width: 1200, height: 1000 } });
page.on("pageerror", (e) => seen.errors.push(String(e)));
const base = pathToFileURL(file).href;
const open = async (hash) => {
  await page.goto(base + hash);
  await page.waitForSelector("#app > *");
  await page.waitForTimeout(150);
};

try {
  // A list screen on the phone.
  await open("#/my-applications?role=employee");
  seen.list = await page.evaluate(() => {
    const phone = document.querySelector(".phone");
    const r = phone && phone.getBoundingClientRect();
    return {
      phone: !!phone, width: r ? Math.round(r.width) : 0, height: r ? Math.round(r.height) : 0,
      topbar: !!document.querySelector(".topbar"), sidebar: !!document.querySelector(".sidebar"),
      tabs: [...document.querySelectorAll(".p-tab span")].map((s) => s.textContent),
      on: (document.querySelector(".p-tab.on span") || {}).textContent,
      heads: document.querySelectorAll(".p-list thead").length,
      rows: [...document.querySelectorAll(".p-list tr[data-row]")].filter((tr) => !tr.hidden).map((tr) => tr.querySelector(".p-main").textContent),
      filter: (document.querySelector('[data-filter="status"]') || {}).value,
      filtersFolded: !!document.querySelector("details.p-filters [data-filter]"),
      bodyPhone: document.body.classList.contains("on-phone"),
    };
  });
  // Opening a record from its row: Back says where it goes back to.
  await page.click('tr[data-row]:not([hidden]) .p-row-link[data-go="application-details"]');
  await page.waitForTimeout(150);
  seen.detail = await page.evaluate(() => ({
    back: (document.querySelector(".p-back") || {}).textContent || "",
    screen: document.getElementById("app").dataset.screen,
  }));
  // A dialog on the phone is a sheet from the bottom of the phone.
  await page.click('[data-el="button:Cancel Application"]');
  await page.waitForSelector(".modal");
  await page.waitForTimeout(400);
  seen.sheet = await page.evaluate(() => {
    const phone = document.querySelector(".phone").getBoundingClientRect();
    const modal = document.querySelector(".modal").getBoundingClientRect();
    return { inPhone: !!document.querySelector(".phone .modal-back"), left: Math.round(modal.left - phone.left), right: Math.round(phone.right - modal.right),
      bottom: Math.round(phone.bottom - modal.bottom), width: Math.round(modal.width), phoneWidth: Math.round(phone.width) };
  });
  await page.keyboard.press("Escape");

  // A camera field on the phone: Take a photo, never a file to drop.
  await open("#/new-application?role=employee");
  seen.camera = await page.evaluate(() => (document.querySelector('[data-el="field:photo"] .fake-view') || {}).textContent || "");
  seen.file = await page.evaluate(() => (document.querySelector('[data-el="field:attachment"] .fake-view') || {}).textContent || "");
  await page.click('[data-el="field:photo"] .file-drop');
  seen.photo = await page.evaluate(() => (document.querySelector('[data-el="field:photo"] .file-name') || {}).textContent || "");

  // A desktop screen in the same mock-up stays a web page.
  await open("#/approvals?role=manager");
  seen.desktop = await page.evaluate(() => ({ phone: !!document.querySelector(".phone"), topbar: !!document.querySelector(".topbar"),
    bodyPhone: document.body.classList.contains("on-phone") }));

  // Cancelling the plan cancels the applications in it that are still waiting.
  await open("#/plan?role=employee");
  await page.click('[data-el="button:Cancel plan"]');
  await page.waitForTimeout(150);
  seen.cascade = await page.evaluate(() => ({
    plan: Mockup.data.plans[0].status,
    applications: Object.fromEntries(Mockup.data.applications.map((a) => [a.id, a.status])),
  }));

  // A new comment is a layer on the earlier comments about the same things, not on those it merely sits near.
  seen.layers = await page.evaluate(() => {
    const earlier = [
      { id: "FB-001", element: "stat:Pending" },
      { id: "FB-002", element: "stat:Approved" },
      { id: "FB-003", element: "stat:Pending", elements: ["stat:Pending", "stat:Approved", "stat:Rejected"] },
    ];
    const ids = (list) => list.map((c) => c.id);
    return {
      boxOfThree: ids(window.MockupLayerOn(earlier, ["stat:Pending", "stat:Approved", "stat:Rejected"])),
      boxOfTwo: ids(window.MockupLayerOn(earlier, ["stat:Pending", "stat:Approved"])),
      one: ids(window.MockupLayerOn(earlier, ["stat:Pending"])),
      boxOfFour: ids(window.MockupLayerOn(earlier, ["stat:Pending", "stat:Approved", "stat:Rejected", "stat:Leave balance (days)"])),
    };
  });

  // A page opened afresh offers what changed since the version before.
  await open("#/approvals?role=manager");
  seen.since = await page.evaluate(() => {
    const b = document.getElementById("fb-changes-btn");
    return { hidden: b.hidden, label: b.textContent };
  });
  await page.click("#fb-changes-btn");
  seen.sinceList = await page.evaluate(() => [...document.querySelectorAll("#fb-changes .fb-wc-item .fb-text")].map((x) => x.textContent));
  seen.sinceHead = await page.evaluate(() => (document.querySelector("#fb-changes .fb-panel-head span") || {}).textContent || "");
} catch (e) {
  seen.failed = String(e).split("\n")[0];
}
console.log(JSON.stringify(seen));
await browser.close();
