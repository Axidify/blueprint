// Draws a box for something new under the sign-in card of a built mock-up (opened from its folder, so the
// comment is kept in the browser) with the Feedback panel open, then measures where the box is against the
// card with the panel open, closed and in a narrower window. Prints one line of JSON.
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
out.errors = errors;
console.log(JSON.stringify(out));
await browser.close();
