// Capture mock-up screenshots with the installed Microsoft Edge, or Google Chrome where there is no Edge
// (no browser download needed).
// Usage: node tools/screenshot.mjs <mockup index.html> <shots.json> <output dir>
// Called by: python -I tools/mockup.py screenshots <project_dir>
import { chromium } from "playwright-core";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const [index, planFile, outDir] = process.argv.slice(2);
const shots = JSON.parse(readFileSync(planFile, "utf8"));
const base = pathToFileURL(index).href;

// A screenshot is printed about 15 cm wide in the requirements document, so the narrower the window it
// is taken in, the larger the screen's text on paper: at 800 px the mock-up's 14 px text prints at about
// 7.5 pt, at 1440 px at 4 pt. The pictures leave the side menu out (menu=0), so at 800 px the screen has
// the room it had at 1000 px with the menu. Each screen is taken at the first width in which nothing is cut
// off sideways (a list with many columns needs a wider one), and at twice the pixels so it stays sharp.
const WIDTHS = [800, 1000, 1200, 1440];
const SCALE = 2;

// Edge is on every Windows machine; on a Mac or Linux it is often Chrome that is installed. Both draw the same.
let browser;
const failures = {};
for (const channel of ["msedge", "chrome"]) {
  try {
    browser = await chromium.launch({ channel, headless: true });
    break;
  } catch (e) {
    failures[channel] = e;
  }
}
if (!browser) {
  // Quote why the browser this system usually has did not start: Edge on Windows, Chrome on a Mac or Linux.
  const usual = failures[process.platform === "win32" ? "msedge" : "chrome"];
  console.error("Neither Microsoft Edge nor Google Chrome could be started, so no screenshots were taken. Install one of them."
    + `\n${String(usual).split("\n")[0]}`);
  process.exit(77);
}
const page = await browser.newPage({ viewport: { width: WIDTHS[0], height: 900 }, deviceScaleFactor: SCALE });
for (const shot of shots) {
  // The process flow's boxes need the room of the screens with their menu: narrower, their words overflow.
  const widths = shot.screen === "__flow" ? WIDTHS.slice(1) : WIDTHS;
  let width;
  for (width of widths) {
    await page.setViewportSize({ width, height: 900 });
    if (width === widths[0]) {
      await page.goto("about:blank");
      await page.goto(base + shot.hash);
      await page.waitForSelector("#app > *");
      await page.evaluate(() => document.fonts.ready);  // the fonts the mock-up carries, before the text is measured
    }
    await page.waitForTimeout(150);
    const fits = await page.evaluate(() =>
      document.documentElement.scrollWidth <= window.innerWidth + 1 &&
      ![...document.querySelectorAll(".table-wrap, .content, .modal-body")].some((el) => el.scrollWidth > el.clientWidth + 1));
    if (fits) break;
  }
  // Crop to the content, so the picture holds the screen and no empty space: a list with one row is a
  // short picture. The login card and an open dialog are centred in a window just tall enough for them.
  const height = await page.evaluate(() => {
    const bottom = (el) => el.getBoundingClientRect().bottom + window.scrollY;
    const card = document.querySelector(".login-card");
    if (card) return Math.ceil(card.getBoundingClientRect().height + 160);
    const flow = document.querySelector(".flow");
    if (flow) return Math.ceil(bottom(flow));
    const content = Math.max(0, ...[...document.querySelectorAll("#content > *")].map(bottom)) + 32;
    const modal = document.querySelector(".modal");
    return Math.ceil(Math.max(content, modal ? modal.getBoundingClientRect().height + 140 : 0));
  });
  await page.setViewportSize({ width, height });
  await page.waitForTimeout(100);
  await page.screenshot({ path: join(outDir, `${shot.name}.png`) });
  console.log(`  ${shot.name}.png${width === widths[0] ? "" : ` (taken ${width} px wide: it does not fit in ${widths[0]})`}`);
}
await browser.close();
