const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const puppeteer = require("puppeteer-core");

(async () => {
  const portrait = process.argv[4] === "portrait";
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
    await page.waitForFunction(() => [...document.images].every(img => img.complete && img.naturalWidth > 0));
    const result = await page.evaluate((mobile) => {
      const failures = [];
      const rect = node => {
        const r = node.getBoundingClientRect();
        return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height };
      };
      const overlap = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
      const scenes = [...document.querySelectorAll(".scene")].map(scene => {
        const bounds = rect(scene);
        const eyebrow = rect(scene.querySelector(".eyebrow"));
        const phase = rect(scene.querySelector(".phase"));
        const details = [...scene.querySelectorAll(".eyebrow,h1,h2,p,.picture-option,.option-label,.option-number,.correct-picture,.phase,.progress,svg")]
          .map(node => {
            const box = rect(node);
            const font = parseFloat(getComputedStyle(node).fontSize);
            if (box.left < bounds.left || box.right > bounds.right + 1 ||
                box.top < bounds.top || box.bottom > bounds.bottom - 12) {
              failures.push(`${scene.id}/${node.className || node.tagName}: exceeds card spacing`);
            }
            if (node.scrollWidth > node.clientWidth + 1) {
              failures.push(`${scene.id}/${node.className || node.tagName}: horizontal overflow`);
            }
            if (node.closest(".main") && box.bottom > phase.top - 8) {
              failures.push(`${scene.id}/${node.className || node.tagName}: overlaps phase footer`);
            }
            if (node.closest(".main") && box.top < eyebrow.bottom + 8) {
              failures.push(`${scene.id}/${node.className || node.tagName}: overlaps scene heading`);
            }
            if (mobile && node.matches(".instruction,.solution-answer,.option-label,.option-number") && font < 42) {
              failures.push(`${scene.id}: mobile content below 42px`);
            }
            return { tag: node.tagName, className: String(node.className), font, ...box };
          });
        const ident = scene.dataset.eventId;
        const match = /^(?:question|recording|repeat_question|inspect|answer)_(\d+)$/.exec(ident);
        if (match) {
          const number = Number(match[1]);
          const main = scene.querySelector(".main");
          if (main.querySelector("h2").textContent !== `Aufgabe ${number}` ||
              main.querySelectorAll(".solution-answer,.instruction-word").length) {
            failures.push(`${scene.id}: exam question/transcript/answer text leaked`);
          }
          const options = main.querySelectorAll(".picture-option");
          if ((number < 13 && options.length !== 3) || (number >= 13 && options.length !== 0)) {
            failures.push(`${scene.id}: wrong A2/B1 picture presentation`);
          }
          if (mobile && options.length) {
            const boxes = [...options].map(rect);
            if (!(boxes[0].bottom <= boxes[1].top && boxes[1].bottom <= boxes[2].top)) {
              failures.push(`${scene.id}: portrait picture options not natively stacked`);
            }
          }
        }
        return { id: scene.id, event: ident, nodes: details };
      });
      const persistent = {};
      for (const selector of ["header", "aside", "footer"]) {
        const node = document.querySelector(selector);
        const box = rect(node);
        persistent[selector] = box;
        if (box.left < 0 || box.top < 0 || box.right > innerWidth || box.bottom > innerHeight ||
            node.scrollWidth > node.clientWidth + 1) failures.push(`${selector}: persistent overflow`);
        for (const child of node.querySelectorAll("img,h2,p,.series,.brand")) {
          const childBox = rect(child);
          if (childBox.bottom > box.bottom + 1 || childBox.right > box.right + 1) {
            failures.push(`${selector}: child content overflow`);
          }
        }
      }
      if (overlap(persistent.aside, rect(document.querySelector(".scene")))) {
        failures.push("Book/Amazon panel overlaps exercise card");
      }
      const flag = rect(document.querySelector(".flag"));
      if (flag.width !== flag.height) failures.push("Swiss flag is not square");
      return { portrait: mobile, failures, scenes, persistent, swissFlag: flag };
    }, portrait);
    fs.writeFileSync(process.argv[3], JSON.stringify(result, null, 2));
    if (result.failures.length) throw new Error(result.failures.join("\n"));
    console.log(`Fide geometry passed: ${result.scenes.length} scenes, ${portrait ? "native stacked pictures" : "native landscape"}.`);
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
