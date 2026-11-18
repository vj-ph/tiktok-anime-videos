const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const puppeteer = require("puppeteer-core");

(async () => {
  const browser = await puppeteer.launch({
    executablePath: process.env.HYPERFRAMES_BROWSER_PATH ||
      path.join(process.env.PROGRAMFILES || "C:\\Program Files",
        "Google", "Chrome", "Application", "chrome.exe"),
    headless: true,
    args: ["--disable-gpu", "--allow-file-access-from-files"],
  });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1080, height: 1920, deviceScaleFactor: 1 });
    await page.goto(pathToFileURL(path.resolve(process.argv[2])).href);
    await page.evaluate(() => document.fonts.ready);
    const results = await page.evaluate(() => {
      const failures = [];
      const scenes = [...document.querySelectorAll(".scene")].map(scene => {
        const bounds = scene.getBoundingClientRect();
        const nodes = [...scene.querySelectorAll(
          ".eyebrow, h1, h2, p, .option, .solution, .phase, .progress")];
        const details = nodes.map(node => {
          const box = node.getBoundingClientRect();
          const font = parseFloat(getComputedStyle(node).fontSize);
          if (box.left < bounds.left || box.right > bounds.right ||
              box.top < bounds.top || box.bottom > bounds.bottom - 12) {
            failures.push(`${scene.id}: ${node.className || node.tagName} exceeds card spacing`);
          }
          if (node.scrollWidth > node.clientWidth + 1) {
            failures.push(`${scene.id}: horizontal text overflow`);
          }
          if ((node.matches(".option") && font < 40) ||
              (node.matches("h2") && font < 42)) {
            failures.push(`${scene.id}: question/option font below mobile minimum`);
          }
          return { tag: node.tagName, className: node.className, font,
            top: box.top, bottom: box.bottom, height: box.height };
        });
        return { id: scene.id, classes: scene.className, nodes: details,
          remainingBottomSpace: bounds.bottom - Math.max(...details.map(n => n.bottom)) };
      });
      return { viewport: [1080, 1920], optionMinimumPx: 40,
        questionMinimumPx: 42, failures, scenes };
    });
    fs.writeFileSync(process.argv[3], JSON.stringify(results, null, 2));
    if (results.failures.length) {
      throw new Error(results.failures.join("\n"));
    }
    console.log(`Mobile layout: ${results.scenes.length} scenes fit; options >=40px, questions >=42px.`);
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
