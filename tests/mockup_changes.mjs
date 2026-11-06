// Opens a built mock-up and asks its "What changed" comparison what differs between two specs, given as JSON
// files, and prints the changes as one line of JSON.
// Usage: node tests/mockup_changes.mjs <built index.html> <before.json> <after.json>
// Called by tests/test_mockup.py. Exit code 77: Edge could not be started (the test is then skipped).
import fs from "node:fs";
import { pathToFileURL } from "node:url";
import { chromium } from "playwright-core";

const [file, beforeFile, afterFile] = process.argv.slice(2);
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
const page = await browser.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await page.goto(pathToFileURL(file).href + "#/login");
await page.waitForSelector("#app > *");
const before = JSON.parse(fs.readFileSync(beforeFile, "utf8"));
const after = JSON.parse(fs.readFileSync(afterFile, "utf8"));
const changes = await page.evaluate(([a, b]) => window.MockupWhatChanged(a, b), [before, after]);
console.log(JSON.stringify({ changes, errors }));
await browser.close();
