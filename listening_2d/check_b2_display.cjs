const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const puppeteer = require("puppeteer-core");

(async () => {
  const plan = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
  const portrait = plan.job.layout === "portrait";
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
    const report = await page.evaluate((input) => {
      const failures = [];
      const expected = {
        richtig: { color: "rgb(33, 86, 64)", background: "rgb(224, 241, 231)" },
        falsch: { color: "rgb(140, 38, 53)", background: "rgb(253, 233, 235)" },
      };
      function luminance(rgb) {
        const channels = rgb.match(/\d+/g).slice(0, 3).map(n => {
          const value = Number(n) / 255;
          return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
        });
        return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
      }
      const answers = [...document.querySelectorAll("[data-answer]")].map(node => {
        const key = node.dataset.answer.split(":")[1];
        const style = getComputedStyle(node);
        const target = expected[key];
        if (!target || style.color !== target.color || style.backgroundColor !== target.background) {
          failures.push(`Wrong truth color: ${node.dataset.answer}`);
        }
        const a = luminance(style.color);
        const b = luminance(style.backgroundColor);
        const contrast = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
        if (contrast < 4.5) failures.push(`Low truth-label contrast: ${node.dataset.answer}`);
        return { answer: node.dataset.answer, color: style.color,
          background: style.backgroundColor, contrast };
      });
      const mapping = input.reading_words;
      const sections = [...document.querySelectorAll(".reading-instruction")];
      let soughtFrames = 0;
      const coverage = new Set();
      if (mapping.length) {
        if (sections.length !== 1) failures.push("Missing separate reading instruction slide");
        const section = sections[0];
        if (section.querySelector("[data-question],.statement-board,.countdown")) {
          failures.push("Reading cue must not show the question board or silence countdown");
        }
        const spans = [...section.querySelectorAll(".instruction-word")];
        if (spans.map(n => n.textContent).join(" ") !== mapping.map(w => w.label).join(" ")) {
          failures.push("Instruction text or tokenization differs from measured audio");
        }
        if (parseFloat(getComputedStyle(section.querySelector(".instruction")).fontSize) < 42) {
          failures.push("Instruction mobile font below 42px");
        }
        const range = input.changed_ranges.find(r => r.label === "separate reading instruction");
        const frames = Array.from({ length: range.end_frame - range.start_frame },
          (_, i) => range.start_frame + i);
        for (const frame of frames.concat([...frames].reverse())) {
          const seconds = frame / 24;
          window.__timelines.main.seek(seconds, false);
          for (const word of mapping) {
            const node = document.querySelector(word.selector);
            const active = seconds >= word.start && seconds < word.end;
            const actual = getComputedStyle(node).backgroundColor === "rgb(210, 233, 223)";
            if (actual !== active) failures.push(`Word highlight mismatch: ${word.index} at frame ${frame}`);
            if (actual) coverage.add(word.index);
          }
          soughtFrames++;
        }
        if (coverage.size !== mapping.length) failures.push("Some measured words never highlight at 24fps");
      } else if (sections.length) {
        failures.push("Unexpected new reading slide outside shorts 1/2");
      }
      const patchCrops = {};
      for (const patch of input.patches.filter(p => p.crop_selector)) {
        const index = input.job.scenes.findIndex(s => s.id === patch.label);
        const board = document.querySelector(`#scene-${index} ${patch.crop_selector}`);
        const box = board.getBoundingClientRect();
        const x = Math.floor(box.left) - 2;
        const y = Math.floor(box.top) - 2;
        patchCrops[patch.label] = [x, y, Math.ceil(box.right) + 2 - x, Math.ceil(box.bottom) + 2 - y];
        if (x < 0 || y < 0 || box.right + 2 > innerWidth || box.bottom + 2 > innerHeight) {
          failures.push(`Replacement crop out of bounds: ${patch.label}`);
        }
      }
      return { failures, answers, patchCrops, readingSoughtFrames: soughtFrames,
        highlightedWords: [...coverage].sort((a, b) => a - b) };
    }, plan);
    fs.writeFileSync(process.argv[4], JSON.stringify(report, null, 2));
    if (report.failures.length) throw new Error(report.failures.join("\n"));
    console.log(`Display checks: ${report.answers.length} colored labels; ${report.readingSoughtFrames} forward/reverse word-frame seeks.`);
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
