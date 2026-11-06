// Draws a box for something new under the sign-in card of a built mock-up (opened from its folder, so the
// comment is kept in the browser) with the Feedback panel open, then measures where the box is against the
// card with the panel open, closed and in a narrower window. Then the same for a box drawn just left of the
// My Applications toolbar button, where the filters and the toolbar wrap differently at each width.
// Last, a box dragged over the empty page: nothing is marked while it is drawn and it never picks the page
// background (only a click comments on that). Prints one line of JSON.
// Usage: node tests/mockup_box.mjs <built index.html>
// Called by tests/test_mockup.py. Exit code 77: Edge could not be started (the test is then skipped).
import { pathToFileURL } from "node:url";
import { chromium } from "playwright-core";

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
const page = await browser.newPage({ viewport: { width: 1400, height: 1000 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await page.goto(pathToFileURL(process.argv[2]).href + "#/login");
await page.waitForSelector(".login-card");
await page.click("#fb-toggle");
await page.waitForTimeout(400);
const card = await page.locator(".login-card").boundingBox();
const cx = card.x + card.width / 2, y = card.y + card.height + 14;
await page.mouse.move(cx - 90, y);
await page.mouse.down();
await page.mouse.move(cx, y + 15, { steps: 4 });
await page.mouse.move(cx + 90, y + 34, { steps: 4 });
await page.mouse.up();
await page.waitForSelector(".fb-dialog");
const title = await page.textContent(".fb-title");
await page.fill("#fb-text", "A copyright line here");
await page.click("#fb-save");
await page.waitForTimeout(500);
const measure = () => page.evaluate(() => {
  const c = document.querySelector(".login-card").getBoundingClientRect();
  const b = document.querySelector(".fb-box").getBoundingClientRect();
  return { offCentre: Math.round(b.left + b.width / 2 - (c.left + c.width / 2)), gapUnderCard: Math.round(b.top - c.bottom) };
});
const out = { title, panelOpen: await measure() };
await page.click("#fb-toggle");
await page.waitForTimeout(400);
out.panelClosed = await measure();
await page.setViewportSize({ width: 1150, height: 860 });
await page.waitForTimeout(400);
out.narrower = await measure();
// A box just left of the toolbar button, drawn with the panel open in a window where the toolbar wraps
await page.setViewportSize({ width: 1120, height: 734 });
await page.goto(pathToFileURL(process.argv[2]).href + "#/my-applications?role=employee");
await page.waitForSelector(".toolbar .btn");
if (!(await page.locator("#fb-panel").isVisible())) await page.click("#fb-toggle");
await page.waitForTimeout(400);
const btn = await page.locator(".toolbar .btn").first().boundingBox();
await page.mouse.move(btn.x - 196, btn.y - 4);
await page.mouse.down();
await page.mouse.move(btn.x - 100, btn.y + 10, { steps: 4 });
const marked = () => page.evaluate(() => [...document.querySelectorAll("#app [data-el]")].filter((el) => getComputedStyle(el).outlineStyle !== "none").map((el) => el.dataset.el));
out.markedWhileDrawing = await marked();
await page.mouse.move(btn.x - 14, btn.y + btn.height + 4, { steps: 4 });
await page.mouse.up();
await page.waitForSelector(".fb-dialog");
out.toolbarTitle = await page.textContent(".fb-title");
await page.fill("#fb-text", "Export to Excel button here");
await page.click("#fb-save");
await page.waitForTimeout(500);
const beside = () => page.evaluate(() => {
  const c = document.querySelector(".toolbar .btn").getBoundingClientRect();
  const boxes = [...document.querySelectorAll(".fb-box")].map((b) => b.getBoundingClientRect()).filter((b) => b.width);
  const b = boxes[boxes.length - 1];
  return { gapLeftOfButton: Math.round(c.left - b.right), offMiddle: Math.round(b.top + b.height / 2 - (c.top + c.height / 2)) };
});
out.toolbarPanelOpen = await beside();
await page.click("#fb-toggle");
await page.waitForTimeout(400);
out.toolbarPanelClosed = await beside();
await page.setViewportSize({ width: 1600, height: 900 });
await page.waitForTimeout(400);
out.toolbarWide = await beside();
// A box over the empty page under the list (feedback on again)
await page.click("#fb-toggle");
await page.waitForTimeout(400);
const table = await page.locator("#content table").first().boundingBox();
const y0 = table.y + table.height + 70;
await page.mouse.move(table.x + 40, y0);
await page.mouse.down();
await page.mouse.move(table.x + 140, y0 + 20, { steps: 4 });
out.markedOverEmptyPage = await marked();
await page.mouse.move(table.x + 260, y0 + 40, { steps: 4 });
await page.mouse.up();
await page.waitForSelector(".fb-dialog");
out.emptyTitle = await page.textContent(".fb-title");
await page.fill("#fb-text", "A help link here");
await page.click("#fb-save");
await page.waitForTimeout(400);
out.emptyElement = await page.evaluate(() => { const k = Object.keys(localStorage).find((x) => x.startsWith("mock-feedback")); const l = JSON.parse(localStorage[k]); return l[l.length - 1].element; });
out.errors = errors;
console.log(JSON.stringify(out));
await browser.close();
