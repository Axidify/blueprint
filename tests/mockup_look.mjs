// Opens a built mock-up from its folder (as the shared folder's shortcut and the screenshots do) in the
// installed Microsoft Edge and prints, as one line of JSON, how the client's look came out on the sign-in
// page and on a list screen.
// Usage: node tests/mockup_look.mjs <built index.html> <list screen id> <role>
// Called by tests/test_mockup.py. Exit code 77: Edge could not be started (the test is then skipped).
import { pathToFileURL } from "node:url";
import { chromium } from "playwright-core";

const [file, screen, role] = process.argv.slice(2);
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
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
const out = { errors: [] };
page.on("pageerror", (e) => out.errors.push(String(e)));
const base = pathToFileURL(file).href;

await page.goto(base + "#/login?clean=1");
await page.waitForSelector("#app > *");
await page.evaluate(() => document.fonts.ready);
out.login = await page.evaluate(() => {
  const logo = document.querySelector(".login-brand .brand-logo");
  return {
    data: { ...document.documentElement.dataset },
    logo: logo ? { loaded: logo.complete && logo.naturalWidth > 0, alt: logo.alt } : null,
    letters: !!document.querySelector(".login-brand .brand-mark"),
    cardCorners: getComputedStyle(document.querySelector(".login-card")).borderTopLeftRadius,
    fonts: [...document.fonts].filter((f) => f.status === "loaded").map((f) => f.family.replace(/"/g, "")),
    bodyFont: getComputedStyle(document.body).fontFamily,
  };
});

await page.goto("about:blank");
await page.goto(base + `#/${screen}?role=${role}&clean=1`);
await page.waitForSelector("#app > *");
out.list = await page.evaluate(() => ({
  topbar: getComputedStyle(document.querySelector(".topbar")).backgroundColor,
  sidebar: getComputedStyle(document.querySelector(".sidebar")).backgroundColor,
  logo: !!document.querySelector(".topbar .brand-logo"),
  buttonCorners: getComputedStyle(document.querySelector(".btn")).borderTopLeftRadius,
  people: [...document.querySelectorAll(".person")].map((p) => ({
    text: p.textContent, initials: p.dataset.initials, tone: p.dataset.tone, tint: getComputedStyle(p, "::before").backgroundColor })),
}));
await browser.close();
console.log(JSON.stringify(out));
