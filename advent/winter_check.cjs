const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const puppeteer = require("puppeteer-core");

async function main() {
  const dir = process.argv[2] ? path.resolve(process.argv[2]) : path.join(__dirname, "build/winter-v7");
  const { safe_rect: safe } = JSON.parse(fs.readFileSync(path.join(dir, "alignment.json"), "utf8"));
  const browser = await puppeteer.launch({
    executablePath: process.env.CHROME_PATH,
    args: ["--no-sandbox", "--allow-file-access-from-files"],
  });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1080, height: 1920 });
    await page.goto(pathToFileURL(path.join(dir, "index.html")).href);
    await page.evaluate(() => document.fonts.ready);
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    const result = await page.evaluate(([left, top, right, bottom]) => {
      const failures = [];
      const nodes = [...document.querySelectorAll(".tag,h1,.artwork,.artwork svg,.artwork img,.caption,.trail,.result-card,.grade")];
      const bounds = node => {
        const { x, y, right: r, bottom: b } = node.getBoundingClientRect();
        return x >= left && y >= top && r <= right && b <= bottom;
      };
      for (const node of nodes) {
        const parent = node.closest("[data-start]");
        const start = +parent.dataset.start, duration = +parent.dataset.duration;
        for (const offset of [0, .12, .28, .5, .8, duration / 2, duration - .04]
          .filter(offset => offset >= 0 && offset < duration)) {
          window.__timelines.root.seek(start + offset, false);
          if (!bounds(node)) failures.push(`${parent.id} ${node.className} outside at ${start + offset}s`);
        }
      }
      const words = [...document.querySelectorAll("[data-word-start]")];
      for (const node of words) {
        window.__timelines.root.seek((+node.dataset.wordStart + +node.dataset.wordEnd) / 2, false);
        if (getComputedStyle(node).backgroundColor !== "rgb(255, 212, 126)") failures.push(node.textContent);
      }
      const pairs = [...document.querySelectorAll(".caption")];
      const language = document.documentElement.lang;
      if (!pairs.length || !words.length || pairs.some(node =>
        node.querySelector(".spoken, .de")?.lang !== language ||
        !node.querySelector(".en[lang=en]")?.textContent.trim())) {
        failures.push("Missing bilingual caption");
      }
      for (const caption of pairs) {
        const art = document.querySelector(caption.id.replace("phrase-", "#art-"));
        const frame = +caption.dataset.start + Math.min(.7, +caption.dataset.duration / 2);
        const beat = [...document.querySelectorAll(".beat")].find(el =>
          +el.dataset.start <= frame && frame < +el.dataset.start + +el.dataset.duration);
        window.__timelines.root.seek(frame, false);
        const artwork = art.getBoundingClientRect();
        if (beat.querySelector("h1").getBoundingClientRect().bottom > artwork.top ||
            artwork.bottom > caption.getBoundingClientRect().top) failures.push(`${art.id}: overlaps text`);
        for (const node of art.children) {
          if (!bounds(node)) failures.push(`${art.id}: artwork overflows safe area`);
        }
      }
      const opening = document.querySelector(".result-cards.opening");
      const reveal = document.querySelector(".result-cards.reveal");
      if (Boolean(opening) !== Boolean(reveal)) failures.push("Missing result-card counterpart");
      if (opening && reveal) {
        const timeline = window.__timelines.root;
        const opacity = node => Number(getComputedStyle(node).opacity);
        const grades = [...opening.querySelectorAll(".grade")];
        timeline.seek(.50, false);
        if (grades.some(node => opacity(node) !== 0)) failures.push("Opening stamps appear before the cards settle");
        timeline.seek(.92, false);
        if (grades.map(opacity).join(",") !== "1,0,0") failures.push("First B1 stamp is not held on its own");
        timeline.seek(1.55, false);
        if (grades.map(opacity).join(",") !== "1,1,0") failures.push("Opening stamps are not staggered");
        timeline.seek(2.25, false);
        if (opacity(grades[2]) !== 1 || opacity(opening.querySelector(".result-card:last-child svg")) !== 0) {
          failures.push("Opening A2 stamp or hidden icon is wrong");
        }
        const revealStart = Number(reveal.closest("[data-start]").dataset.start);
        const writing = reveal.querySelector(".result-card:last-child svg");
        timeline.seek(revealStart + .4, false);
        if (opacity(writing) !== 0) failures.push("Writing icon appears before the reveal");
        timeline.seek(revealStart + 1.15, false);
        if (opacity(writing) !== 1 || opacity(reveal.querySelector(".mystery")) !== 0) {
          failures.push("Writing icon does not replace the mystery mark");
        }
      }
      return { bounds: nodes.length, words: words.length, pairs: pairs.length, failures };
    }, safe);
    result.failures.push(...errors);
    console.log(JSON.stringify(result, null, 2));
    if (result.failures.length) process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
