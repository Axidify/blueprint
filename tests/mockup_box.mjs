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
// A box just left of the toolbar button, whose place the open panel covers: minimised, the panel is a small tab,
// Feedback stays on and the button can be reached. Then the window changes width and the toolbar wraps.
await page.setViewportSize({ width: 748, height: 734 });  // narrow enough that the toolbar wraps under the filters
await page.goto(pathToFileURL(process.argv[2]).href + "#/my-applications?role=employee");
await page.waitForSelector(".toolbar .btn");
if (!(await page.locator("#fb-panel").isVisible())) await page.click("#fb-toggle");
await page.waitForTimeout(200);
await page.click("#fb-mini");
await page.waitForTimeout(200);
out.mini = await page.evaluate(() => ({ width: Math.round(document.getElementById("fb-panel").getBoundingClientRect().width),
  feedback: document.body.classList.contains("fb-active"), cards: document.querySelectorAll("#fb-panel .fb-item").length,
  cardsShown: [...document.querySelectorAll("#fb-panel .fb-item")].filter((x) => x.getBoundingClientRect().width).length,
  commentsButton: !document.getElementById("fb-list").hidden }));
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
// A box drawn around two things, one of which is then hidden (a folded section): the box stays round the one on
// show; a hidden thing says it is at the page's corner, and the box once stretched from there across the screen.
const parts = await page.evaluate(() => [...document.querySelectorAll('#app [data-el^="search:"], #app [data-el^="filter:"]')]
  .filter((el) => el.getBoundingClientRect().width).slice(0, 2).map((el) => { const r = el.getBoundingClientRect(); return { el: el.dataset.el, x: r.x, y: r.y, w: r.width, h: r.height }; }));
if (parts.length === 2) {
  const left = Math.min(parts[0].x, parts[1].x) - 8, top = Math.min(parts[0].y, parts[1].y) - 8;
  const right = Math.max(parts[0].x + parts[0].w, parts[1].x + parts[1].w) + 8, bottom = Math.max(parts[0].y + parts[0].h, parts[1].y + parts[1].h) + 8;
  await page.mouse.move(left, top);
  await page.mouse.down();
  await page.mouse.move(right, bottom, { steps: 6 });
  await page.mouse.up();
  await page.waitForSelector(".fb-dialog");
  await page.fill("#fb-text", "these two together");
  await page.click("#fb-save");
  await page.waitForTimeout(400);
  out.hiddenPart = await page.evaluate((hide) => {
    document.querySelector(`#app [data-el="${CSS.escape(hide)}"]`).style.display = "none";
    window.dispatchEvent(new Event("resize"));
    return new Promise((done) => setTimeout(() => {
      const boxes = [...document.querySelectorAll(".fb-box")].map((b) => b.getBoundingClientRect()).filter((b) => b.width);
      const b = boxes[boxes.length - 1];
      done({ left: Math.round(b.left), top: Math.round(b.top), width: Math.round(b.width) });
    }, 300));
  }, parts[1].el);
  out.shownPart = { left: Math.round(parts[0].x), top: Math.round(parts[0].y), width: Math.round(parts[0].w) };
  // Both hidden: no box at all (one at its old place would point at something else); its card says why.
  if (await page.isVisible("#fb-list")) await page.click("#fb-list");  // the list, minimised earlier, back
  out.allHidden = await page.evaluate((first) => {
    const before = document.querySelectorAll(".fb-box").length;
    document.querySelector(`#app [data-el="${CSS.escape(first)}"]`).style.display = "none";
    window.dispatchEvent(new Event("resize"));
    return new Promise((done) => setTimeout(() => done({ boxesBefore: before, boxesAfter: document.querySelectorAll(".fb-box").length,
      note: [...document.querySelectorAll("#fb-panel .fb-away")].map((x) => x.textContent) }), 300));
  }, parts[0].el);
}
// A comment made as another role about something drawn only for that role, and an applied box for something
// new: neither is marked on the page, and each card says why.
await page.evaluate(() => {
  const k = Object.keys(localStorage).find((x) => x.startsWith("mock-feedback"));
  const list = JSON.parse(localStorage[k]);
  const screen = document.getElementById("app").dataset.screen;
  const time = new Date().toISOString();
  list.push({ screen, role: "manager", element: "button:Only for managers", text: "role only", x: 10, y: 10, time });
  list.push({ screen, role: "employee", element: "", box: { x: 23, y: 27, w: 51, h: 31 }, text: "built since", state: "applied", x: 74, y: 27, time });
  localStorage[k] = JSON.stringify(list);
});
await page.reload();
await page.waitForSelector("#app > *");
if (!(await page.isVisible("#fb-panel")) && !(await page.isVisible("#fb-list"))) await page.click("#fb-toggle");
if (await page.isVisible("#fb-list")) await page.click("#fb-list");
await page.waitForTimeout(300);
out.away = await page.evaluate(() => ({
  notes: [...document.querySelectorAll("#fb-panel .fb-pick")].map((c) => [c.querySelector(".fb-text").textContent, (c.querySelector(".fb-away") || {}).textContent || ""]),
  done: [...document.querySelectorAll("#fb-panel .fb-pick.fb-done .fb-text")].map((t) => t.textContent),
  doneHead: !!document.querySelector("#fb-panel .fb-done-head"),
  keys: [...document.querySelectorAll("#fb-panel .fb-pick")].map((c) => c.dataset.fb),
  oldBox: [...document.querySelectorAll(".fb-box")].some((b) => { const r = b.getBoundingClientRect(); return Math.round(r.width) === 51 && Math.round(r.height) === 31; }),
}));
// Done comments come back, faded, when asked; a box never takes a click (what is inside it can be commented on);
// a new comment on something commented on before shows the earlier ones and is saved as following them.
await page.click("#fb-show-done");
await page.waitForTimeout(200);
out.shownDone = await page.evaluate(() => [...document.querySelectorAll(".fb-box.done")].some((b) => Math.round(b.getBoundingClientRect().width) === 51));
const target = await page.evaluate((name) => {  // the first of the two things boxed together earlier, under its box
  const r = document.querySelector(`#app [data-el="${CSS.escape(name)}"]`).getBoundingClientRect();
  const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return { x: r.left + r.width / 2, y: r.top + r.height / 2, under: el && el.closest(".fb-box") ? "box" : (el && el.closest("[data-el]") || {}).dataset?.el || "" };
}, parts[0].el);
out.clickThrough = target.under;
await page.mouse.click(target.x, target.y);
await page.waitForSelector(".fb-dialog");
out.earlier = await page.evaluate(() => [...document.querySelectorAll(".fb-earlier-item")].map((x) => x.textContent));
await page.fill("#fb-text", "and now a bit smaller");
await page.click("#fb-save");
await page.waitForTimeout(300);
out.follows = await page.evaluate(() => { const k = Object.keys(localStorage).find((x) => x.startsWith("mock-feedback")); const l = JSON.parse(localStorage[k]); return l[l.length - 1].follows || null; });
out.errors = errors;
console.log(JSON.stringify(out));
await browser.close();
