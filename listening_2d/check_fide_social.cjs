const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const puppeteer = require("puppeteer-core");

(async () => {
  const browser = await puppeteer.launch({
    executablePath: path.join(process.env.PROGRAMFILES || "C:\\Program Files",
      "Google", "Chrome", "Application", "chrome.exe"),
    headless: true,
    args: ["--disable-gpu", "--allow-file-access-from-files"],
  });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1080, height: 1920 });
    await page.goto(pathToFileURL(path.resolve(process.argv[2])).href);
    await page.evaluate(() => document.fonts.ready);
    const report = await page.evaluate(part => {
      const failures = [];
      const details = [];
      for (const [selector, bounds] of [
        ["#short-notice", [80, 254, 1000, 300]], ["footer", [80, 1710, 1000, 1766]],
      ]) {
        const node = document.querySelector(selector);
        const box = node.getBoundingClientRect();
        const range = document.createRange();
        range.selectNodeContents(node);
        const text = range.getBoundingClientRect();
        if (box.left < bounds[0] || box.top < bounds[1] ||
            box.right > bounds[2] || box.bottom > bounds[3] ||
            text.left < box.left || text.right > box.right || text.bottom > box.bottom ||
            node.scrollWidth > node.clientWidth) failures.push(`${selector}: scope overflow`);
        details.push({ selector, text: node.textContent, font: getComputedStyle(node).fontSize,
          left: box.left, top: box.top, right: box.right, bottom: box.bottom });
      }
      if (!document.querySelector("#short-notice").textContent.startsWith(`Video ${part}/6`)) {
        failures.push("Incorrect clip numbering");
      }
      if (document.querySelector("footer").textContent !==
          "Verkürzte Übung · Ausgewählte Aufgaben · 2 von 12") failures.push("Incorrect subset notice");
      for (const scene of document.querySelectorAll(".scene")) {
        if (scene.querySelectorAll(".instruction-word").length &&
            scene.textContent.includes("Sie hören drei")) failures.push("Obsolete three-part context");
      }
      const words = [...document.querySelectorAll(".instruction-word")].map(node => node.id);
      if (words.length !== new Set(words).size) failures.push("Duplicate word IDs");
      return { failures, details, narrationWords: words.length };
    }, Number(process.argv[4]));
    fs.writeFileSync(process.argv[3], JSON.stringify(report, null, 2));
    if (report.failures.length) throw new Error(report.failures.join("\n"));
    console.log("Social clip scope and safe-region layout passed.");
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
