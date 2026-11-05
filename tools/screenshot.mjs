// Capture mock-up screenshots with the installed Microsoft Edge (no browser download needed).
// Usage: node tools/screenshot.mjs <mockup index.html> <shots.json> <output dir>
// Called by: python -I tools/mockup.py screenshots <project_dir>
import { chromium } from "playwright-core";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const [index, planFile, outDir] = process.argv.slice(2);
const shots = JSON.parse(readFileSync(planFile, "utf8"));
const base = pathToFileURL(index).href;

const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1.5 });
for (const shot of shots) {
  await page.goto("about:blank");
  await page.goto(base + shot.hash);
  await page.waitForSelector("#app > *");
  await page.waitForTimeout(150);
  const file = join(outDir, `${shot.name}.png`);
  // Crop to the content (and any open dialog) so screenshots fit a Word page without empty space.
  const height = await page.evaluate(() => {
    const bottoms = [...document.querySelectorAll("#content > *, .modal, .login-card, .flow")]
      .map((el) => el.getBoundingClientRect().bottom + window.scrollY);
    return Math.ceil(Math.max(520, ...bottoms) + 32);
  });
  await page.setViewportSize({ width: 1440, height: Math.max(900, height) });
  await page.screenshot({ path: file, clip: { x: 0, y: 0, width: 1440, height } });
  await page.setViewportSize({ width: 1440, height: 900 });
  console.log(`  ${shot.name}.png`);
}
await browser.close();
