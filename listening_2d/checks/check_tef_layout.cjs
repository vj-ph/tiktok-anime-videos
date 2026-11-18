const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { pathToFileURL } = require("node:url");
const puppeteer = require("puppeteer-core");

function browserPath() {
  if (process.env.HYPERFRAMES_BROWSER_PATH) return process.env.HYPERFRAMES_BROWSER_PATH;
  const windows = path.join(process.env.PROGRAMFILES || "C:\\Program Files",
    "Google", "Chrome", "Application", "chrome.exe");
  if (fs.existsSync(windows)) return windows;
  const cache = path.join(os.homedir(), ".cache", "hyperframes", "chrome", "chrome-headless-shell");
  for (const version of fs.readdirSync(cache).sort().reverse()) {
    const candidate = path.join(cache, version, "chrome-headless-shell-linux64", "chrome-headless-shell");
    if (fs.existsSync(candidate)) return candidate;
  }
  throw new Error("Set HYPERFRAMES_BROWSER_PATH to a verified headless browser.");
}

async function main() {
  const build = path.resolve(process.argv[2]);
  const layout = process.argv[3];
  if (!["landscape", "portrait"].includes(layout)) throw new Error("Choose a native layout.");
  const timeline = JSON.parse(fs.readFileSync(path.join(build, "timeline.json")));
  const content = JSON.parse(fs.readFileSync(path.join(build, "content.json")));
  const receipt = JSON.parse(fs.readFileSync(path.join(build, "composition_receipt.json")));
  const visualPath = path.join(build, "visual_assets.json");
  const visual = fs.existsSync(visualPath) ? JSON.parse(fs.readFileSync(visualPath)) : null;
  const output = path.join(build, `contact_${layout}`);
  fs.mkdirSync(output, { recursive: true });
  const width = layout === "landscape" ? 1920 : 1080;
  const height = layout === "landscape" ? 1080 : 1920;
  const browser = await puppeteer.launch({ executablePath: browserPath(), headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"] });
  const results = [], captures = [], highlights = [];
  let promotion;
  try {
    const page = await browser.newPage();
    await page.setViewport({ width, height, deviceScaleFactor: 1 });
    const errors = [];
    page.on("pageerror", e => errors.push(String(e)));
    await page.goto(pathToFileURL(path.join(build, layout, "index.html")).href, { waitUntil: "networkidle0" });
    await page.evaluate(() => document.fonts.ready);
    await page.evaluate(() => Promise.all([...document.images].map(image => image.decode())));
    promotion = await page.evaluate(({ visual, cards }) => {
      const aside = document.querySelector("aside");
      const parent = aside.getBoundingClientRect();
      const violations = [];
      for (const node of aside.querySelectorAll("img,h2,p,a")) {
        const r = node.getBoundingClientRect();
        if (r.x < parent.x - 2 || r.y < parent.y - 2 || r.right > parent.right + 2 ||
            r.bottom > parent.bottom + 2 || node.scrollHeight > node.clientHeight + 3 ||
            node.scrollWidth > node.clientWidth + 3) {
          violations.push({ message: "Book promotion overflow", tag: node.tagName, text: node.textContent });
        }
      }
      if (visual) {
        if (aside.querySelector(".amazon a")?.href !== visual.amazon_url) {
          violations.push({ message: "Incorrect or missing supplied book URL" });
        }
        for (const item of Object.values(cards)) {
          const sheet = visual.picture_sets[item.visual_set_id];
          if (!sheet) continue;
          const names = "ABCD".split("").map(c => sheet.panels[c].split(/[\\/]/).pop());
          const nodes = [...document.querySelectorAll(`[data-question="${item.number}"] .picture img`)];
          if (!nodes.length || nodes.some((node, i) => !node.src.endsWith("/" + names[i % 4]))) {
            violations.push({ message: "Book illustration order/source mismatch", question: item.number });
          }
          if (sheet.labels_embedded &&
              document.querySelector(`[data-question="${item.number}"] .picture .letter`)) {
            violations.push({ message: "Duplicated book panel labels", question: item.number });
          }
          const answer = document.querySelector(`[data-event-id="solution_${item.number}"] .correct-picture`);
          if (!answer?.src.endsWith("/" + names["ABCD".indexOf(item.answer)])) {
            violations.push({ message: "Correct-answer book panel mismatch", question: item.number });
          }
        }
      }
      return { bounds: { x: parent.x, y: parent.y, width: parent.width, height: parent.height },
        text: aside.innerText, cover_alt: aside.querySelector("img").alt, violations };
    }, { visual, cards: content.cards });
    if (receipt.derivative) {
      const violations = await page.evaluate(() => {
        const failures = [];
        for (const [id, expected] of [["part-badge", [80, 224, 920, 36]], ["short-footer", [80, 1730, 920, 70]]]) {
          const node = document.getElementById(id);
          const box = node?.getBoundingClientRect();
          if (!box || [box.x, box.y, box.width, box.height].some((value, i) => value !== expected[i])) {
            failures.push({ message: "Missing, clipped or misplaced derivative label", id });
          }
        }
        return failures;
      });
      promotion.violations.push(...violations);
    }
    await page.evaluate(() => {
      window.__tefSeek = at => {
        window.__timelines.main.seek(at, false);
        document.querySelectorAll(".scene").forEach(s => {
          const begin = Number(s.dataset.start);
          const first = Math.round(begin * 24), end = Math.round((begin + Number(s.dataset.duration)) * 24);
          const frame = Math.round(at * 24);
          s.style.visibility = frame >= first && frame < end ? "visible" : "hidden";
        });
      };
    });
    for (let index = 0; index < timeline.events.length; index++) {
      const event = timeline.events[index];
      const at = event.start + Math.min(.25, event.duration / 2);
      const result = await page.evaluate(({ at, event, width, height }) => {
        window.__tefSeek(at);
        const scene = document.querySelector(`[data-event-id="${event.id}"]`);
        const violations = [];
        for (const node of scene.querySelectorAll(".main,.question,.questions,.option,h1,h2,p,.picture,img,.phase")) {
          const r = node.getBoundingClientRect();
          const parent = scene.getBoundingClientRect();
          if (r.x < parent.x - 2 || r.y < parent.y - 2 || r.right > parent.right + 2 ||
              r.bottom > parent.bottom + 2 || r.right > width || r.bottom > height ||
              node.scrollHeight > node.clientHeight + 3 || node.scrollWidth > node.clientWidth + 3) {
            violations.push({ text: node.textContent.slice(0, 100), tag: node.tagName,
              className: node.className, x: r.x, y: r.y, width: r.width, height: r.height,
              scrollHeight: node.scrollHeight, clientHeight: node.clientHeight });
          }
        }
        const numbers = [...scene.querySelectorAll("[data-question]")].map(n => Number(n.dataset.question));
        if (event.numbers && JSON.stringify(numbers) !== JSON.stringify(event.numbers)) {
          violations.push({ message: "Missing/extra visible shared questions", numbers });
        }
        const solutions = scene.querySelectorAll(".solution-answer,.correct-picture");
        if (event.numbers && solutions.length) violations.push({ message: "Premature answer reveal" });
        const counter = scene.querySelector(".countdown");
        return { id: event.id, time: at, violations, questions: numbers,
          countdown: counter ? counter.textContent : null };
      }, { at, event, width, height });
      results.push(result);
      if (event.id === "title" || event.id === "setup" || event.id.startsWith("instruction_") ||
          event.id.startsWith("read_") || event.id.startsWith("solution_") || event.kind === "sfx" ||
          ["solutions_intro", "cta", "outro"].includes(event.id)) {
        const name = `frame-${String(index).padStart(3, "0")}.png`;
        await page.screenshot({ path: path.join(output, name) });
        captures.push({ file: name, event: event.id, time: at });
      }
    }
    for (const [index, event] of timeline.events.entries()) {
      if (event.kind !== "silence" || event.id === "outro") continue;
      for (const frame of [event.start_frame, event.end_frame - 1, event.end_frame]) {
        const at = frame / 24;
        const state = await page.evaluate(at => {
          window.__tefSeek(at);
          const scene = [...document.querySelectorAll(".scene")].find(s => s.style.visibility === "visible");
          return { event: scene.dataset.eventId, countdown: scene.querySelector(".countdown")?.textContent ?? null };
        }, at);
        const inside = frame < event.end_frame;
        const expected = inside ? event.id : timeline.events[index + 1].id;
        if (state.event !== expected || (inside && state.countdown !== `${Math.ceil((event.end_frame - frame) / 24)} s`)) {
          throw new Error(`Countdown/frame boundary mismatch at ${frame}, expected ${expected}: ${JSON.stringify(state)}`);
        }
        const name = `boundary-${frame}.png`;
        await page.screenshot({ path: path.join(output, name) });
        captures.push({ file: name, event: state.event, time: at, frame, countdown: state.countdown });
      }
    }
    if (timeline.answer_reveal === "after_exercise") {
      for (const event of timeline.events.filter(e => e.id.startsWith("answer_"))) {
        const boundary = [];
        for (const frame of [event.end_frame - 1, event.end_frame]) {
          const state = await page.evaluate(at => {
            window.__tefSeek(at);
            const scene = [...document.querySelectorAll(".scene")].find(s => s.style.visibility === "visible");
            const nodes = [...scene.querySelectorAll("[data-reveal-question],.solution-answer,.correct-picture")];
            return { event: scene.dataset.eventId,
              revealed: [...scene.querySelectorAll("[data-reveal-question]")].map(n => Number(n.dataset.revealQuestion)),
              regions: nodes.map(node => {
                const r = node.getBoundingClientRect();
                return [Math.floor(r.x), Math.floor(r.y), Math.ceil(r.right), Math.ceil(r.bottom)];
              }) };
          }, frame / 24);
          const expected = frame < event.end_frame ? [] : event.numbers;
          if (JSON.stringify(state.revealed) !== JSON.stringify(expected)) {
            throw new Error(`Premature, missing or incomplete paired answer at frame ${frame}.`);
          }
          const name = `reveal-${frame}.png`;
          await page.screenshot({ path: path.join(output, name) });
          boundary.push({ file: name, event: state.event, time: frame / 24, frame,
            reveal_boundary: true, revealed_questions: state.revealed, regions: state.regions });
        }
        for (const capture of boundary) {
          capture.reveal_regions = boundary[1].regions;
          delete capture.regions;
          captures.push(capture);
        }
      }
      for (const event of timeline.events.filter(e => e.kind === "sfx")) {
        for (const frame of [event.end_frame - 1, event.end_frame]) {
          const state = await page.evaluate(at => {
            window.__tefSeek(at);
            const scene = [...document.querySelectorAll(".scene")].find(s => s.style.visibility === "visible");
            return { event: scene.dataset.eventId,
              revealed: [...scene.querySelectorAll("[data-reveal-question]")].map(n => Number(n.dataset.revealQuestion)) };
          }, frame / 24);
          if (JSON.stringify(state.revealed) !== JSON.stringify(event.reveal_numbers)) {
            throw new Error(`Answer changed or disappeared between chime and TTS at frame ${frame}.`);
          }
          const name = `chime-boundary-${frame}.png`;
          await page.screenshot({ path: path.join(output, name) });
          captures.push({ file: name, event: state.event, time: frame / 24, frame,
            chime_boundary: true, revealed_questions: state.revealed });
        }
      }
    }
    const words = Object.values(receipt.word_mappings).flat();
    for (const word of [...words, ...words.slice().reverse()]) {
      const first = Math.ceil(word.start * 24);
      if (first / 24 >= word.end) continue;
      const at = first / 24 + .00001;
      const result = await page.evaluate(({ word, at }) => {
        window.__timelines.main.seek(at, false);
        const node = document.querySelector(word.selector);
        return { selector: word.selector, time: at, color: getComputedStyle(node).backgroundColor };
      }, { word, at });
      if (result.color !== "rgb(210, 233, 223)") throw new Error(`Missing seek-safe highlight: ${JSON.stringify(result)}`);
      highlights.push(result);
    }
    for (const word of receipt.word_mappings.title || []) {
      const frame = Math.ceil(word.start * 24);
      if (frame / 24 >= word.end) continue;
      await page.evaluate(at => window.__tefSeek(at), frame / 24);
      const name = `title-word-${word.index}.png`;
      await page.screenshot({ path: path.join(output, name) });
      captures.push({ file: name, event: "title", time: frame / 24, frame, selector: word.selector });
    }
    if (receipt.derivative) {
      const edit = receipt.derivative;
      const cta = timeline.events.find(e => e.id === "cta");
      for (const frame of new Set([0, edit.output_start_frame - 1, edit.output_start_frame,
        edit.output_end_frame - 1, edit.output_end_frame, cta.end_frame - 1, cta.end_frame,
        timeline.total_frames - 1])) {
        const expected = timeline.events.find(e => e.start_frame <= frame && frame < e.end_frame);
        const state = await page.evaluate(at => {
          window.__tefSeek(at);
          return [...document.querySelectorAll(".scene")].find(s => s.style.visibility === "visible")?.dataset.eventId;
        }, frame / 24);
        if (state !== expected.id) throw new Error(`Derivative edit boundary is shifted at frame ${frame}.`);
        const name = `edit-${frame}.png`;
        await page.screenshot({ path: path.join(output, name) });
        captures.push({ file: name, event: state, time: frame / 24, frame, edit_boundary: true });
      }
    }
    if (errors.length) throw new Error(errors.join("\n"));
  } finally {
    await browser.close();
  }
  const report = { layout, width, height, events: results, captures, promotion,
    measured_word_seek_checks: highlights.length, question_count: Object.keys(content.cards).length,
    violations: [...promotion.violations, ...results.flatMap(r => r.violations)],
    note: "Direct native DOM/GSAP checks; HyperFrames check is a separate required gate." };
  fs.writeFileSync(path.join(build, `geometry_${layout}.json`), JSON.stringify(report, null, 2) + "\n");
  if (report.violations.length) throw new Error(`${report.violations.length} TEF layout violations; inspect geometry_${layout}.json`);
  console.log(`${layout}: ${results.length} events, ${highlights.length} measured highlight seeks, ${captures.length} contact frames passed.`);
}

main().catch(error => { console.error(error); process.exitCode = 1; });
