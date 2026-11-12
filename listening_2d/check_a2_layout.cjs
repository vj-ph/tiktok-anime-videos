const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const puppeteer = require("puppeteer-core");

(async () => {
  const portrait = process.argv[4] !== "landscape";
  const browser = await puppeteer.launch({
    executablePath: path.join(process.env.PROGRAMFILES || "C:\\Program Files",
      "Google", "Chrome", "Application", "chrome.exe"),
    headless: true,
    args: ["--disable-gpu", "--allow-file-access-from-files"],
  });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: portrait ? 1080 : 1920, height: portrait ? 1920 : 1080 });
    await page.goto(pathToFileURL(path.resolve(process.argv[2])).href);
    await page.evaluate(() => document.fonts.ready);
    const result = await page.evaluate((mobile) => {
      const failures = [];
      const scenes = [...document.querySelectorAll(".scene")].map(scene => {
        const bounds = scene.getBoundingClientRect();
        const nodes = [...scene.querySelectorAll(
          ".eyebrow, h1, h2, p, .option, .compact-option, .phase, .progress")];
        const details = nodes.map(node => {
          const box = node.getBoundingClientRect();
          const font = parseFloat(getComputedStyle(node).fontSize);
          if (box.left < bounds.left || box.right > bounds.right ||
              box.top < bounds.top || box.bottom > bounds.bottom - 12) {
            failures.push(`${scene.id}: ${node.className || node.tagName} exceeds card spacing`);
          }
          if (node.scrollWidth > node.clientWidth + 1) {
            failures.push(`${scene.id}: horizontal overflow in ${node.className || node.tagName}`);
          }
          if (mobile && ((node.matches(".option, .compact-option") && font < 40) ||
              (node.matches("h2") && font < 42))) {
            failures.push(`${scene.id}: mobile question/option font below 42/40px`);
          }
          return { tag: node.tagName, className: node.className, font,
            left: box.left, right: box.right, top: box.top, bottom: box.bottom };
        });
        return { id: scene.id, classes: scene.className, nodes: details,
          remainingBottomSpace: bounds.bottom - Math.max(...details.map(n => n.bottom)) };
      });
      for (const selector of ["header", "aside", "footer", ".scope-notice"]) {
        const node = document.querySelector(selector);
        if (!node) continue;
        const box = node.getBoundingClientRect();
        if (box.left < 0 || box.top < 0 || box.right > innerWidth || box.bottom > innerHeight ||
            node.scrollWidth > node.clientWidth + 1) {
          failures.push(`${selector}: persistent element overflow`);
        }
      }
      return { portrait: mobile, failures, scenes };
    }, portrait);
    fs.writeFileSync(process.argv[3], JSON.stringify(result, null, 2));
    if (result.failures.length) throw new Error(result.failures.join("\n"));
    console.log(`A2 geometry: ${result.scenes.length} scenes fit (${portrait ? "portrait 42/40px minimum" : "landscape"}).`);
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
