import path from 'node:path';
import {readFile, mkdir, writeFile, access} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';
import puppeteer from 'puppeteer-core';
import {startServer, root} from './serve.mjs';
import {activeWord, titleWords} from './scene_logic.mjs';

const buildName = process.argv.find(arg => arg.startsWith('--build='))?.split('=')[1] ?? 'preview_swiss_r1';
if (!/^[\w-]+$/.test(buildName)) throw new Error('Invalid build name');
const build = path.join(root, 'builds', buildName);
const checkOnly = process.argv.includes('--check-only');
const fixture = process.argv.includes('--fixture');
if (fixture) {
  assert.equal(buildName, 'layout_fixture', 'Fixtures cannot replace speech builds');
  await mkdir(build, {recursive: true});
  const texts = [
    'fide Test A zwei B eins Sprechen Prüfungssimulation.',
    'Ich sehe eine Frau an einer Bushaltestelle. Sie schaut auf den Fahrplan.',
  ];
  await writeFile(path.join(build, 'timeline.json'), JSON.stringify({fps: 24, duration: 12, total_frames: 288,
    turns: texts.map((text, i) => ({id: i ? 'description' : 'title', text, speaker: i ? 'candidate' : 'examiner',
      start: i * 6, end: i * 6 + 5.5, phase: i ? 'A2 · Bild beschreiben' : 'Technikvorschau',
      mouth_envelope: Array.from({length: 132}, (_, k) => Math.abs(Math.sin(k))),
      words: text.split(' ').map((word, k, all) => ({word, start: k * 5 / all.length, end: (k + 0.8) * 5 / all.length}))}))}));
}
assert.ok(!fixture || checkOnly, 'A synthetic layout fixture cannot be exported as a voiced preview');
const timeline = JSON.parse(await readFile(path.join(build, 'timeline.json'), 'utf8'));
assert.ok(timeline.total_frames / timeline.fps < 90);
const chrome = process.env.CHROME_PATH ?? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const {server, url} = await startServer();
let browser;
const formats = [{name: 'youtube', width: 960, height: 540}, {name: 'social', width: 540, height: 960}];
const hash = buffer => createHash('sha256').update(buffer).digest('hex');
const audit = {build: buildName, fps: timeline.fps, duration: timeline.duration, fixture, formats: []};
try {
  assert.equal((await fetch(url)).status, 200);
  browser = await puppeteer.launch({executablePath: chrome, headless: true,
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--hide-scrollbars',
      '--disable-background-timer-throttling', '--force-color-profile=srgb']});
  for (const format of formats) {
    const output = path.join(build, `${format.name}.mp4`);
    if (!checkOnly) {
      try { await access(output); throw new Error(`Refusing to overwrite ${output}`); }
      catch (error) { if (error.code !== 'ENOENT') throw error; }
    }
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    await page.setViewport({width: format.width, height: format.height, deviceScaleFactor: 1});
    await page.setRequestInterception(true);
    page.on('request', request => {
      if (request.url().startsWith(url) || request.url().startsWith('data:')) request.continue();
      else request.abort();
    });
    await page.goto(`${url}/?capture=1&build=${buildName}`, {waitUntil: 'networkidle0'});
    await page.waitForFunction(() => window.preview?.ready, {timeout: 30000});
    const frames = [...new Set([0, ...timeline.turns.flatMap(turn => [
      turn.start_frame ?? Math.round(turn.start * timeline.fps),
      Math.round((turn.start + (turn.end - turn.start) * 0.55) * timeline.fps),
    ])])].sort((a, b) => a - b);
    const referenceDir = path.join(build, `reference_${format.name}`);
    await mkdir(referenceDir, {recursive: true});
    let wordChecks = 0, stats;
    for (const turn of timeline.turns) {
      const displayed = {...turn, words: turn.id === 'title' ? titleWords(turn) : turn.words};
      for (const word of turn.words) {
        for (const local of [word.start, (word.start + word.end) / 2, word.end]) {
          const time = turn.start + local;
          stats = await page.evaluate(t => window.preview.seek(t), time);
          assert.equal(stats.word, activeWord(displayed, time), 'Visible word must follow measured speech');
          const layout = await page.evaluate(() => window.preview.bounds());
          for (const box of layout) {
            assert.ok(!box.overflow, `${format.name}: text overflow ${box.selector} at ${time}`);
            assert.ok(box.x >= -1 && box.y >= -1 &&
              box.x + box.width <= format.width + 1 && box.y + box.height <= format.height + 1,
            `${format.name}: offscreen ${box.selector}`);
          }
          assert.equal(stats.mouths.observer, 0.012, 'Observer must never speak');
          const inactive = turn.speaker === 'candidate' ? 'examiner' : 'candidate';
          assert.equal(stats.mouths[inactive], 0.012, 'Listeners must not mouth the speech');
          for (const head of stats.heads) {
            assert.ok(head.x > 0.06 && head.x < 0.94 && head.y > 0.12 && head.y < 0.88,
              `${format.name}: unsafe head ${head.id}: ${JSON.stringify(head)}`);
          }
          wordChecks++;
        }
      }
    }
    for (const frame of frames) {
      await page.evaluate(f => window.preview.setFrame(f), frame);
      await page.screenshot({path: path.join(referenceDir, `${String(frame).padStart(6, '0')}.png`), optimizeForSpeed: true});
    }
    const checks = frames.slice(0, 4);
    const hashes = [];
    for (const frame of [...checks, ...checks.toReversed()]) {
      await page.evaluate(f => window.preview.setFrame(f), frame);
      hashes.push(hash(await page.screenshot({optimizeForSpeed: true})));
    }
    assert.deepEqual(hashes.slice(0, checks.length), hashes.slice(checks.length).toReversed(),
      'Backward seek must reproduce identical pixels');
    let elapsed = 0;
    if (!checkOnly) {
      const start = performance.now();
      const encoder = spawn('ffmpeg', ['-nostdin', '-v', 'error', '-f', 'image2pipe', '-framerate', String(timeline.fps),
        '-vcodec', 'png', '-i', 'pipe:0', '-i', path.join(build, 'dialogue.wav'), '-map', '0:v:0', '-map', '1:a:0',
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '19', '-threads', '4', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-af', 'apad', '-t', String(timeline.duration),
        '-frames:v', String(timeline.total_frames), '-movflags', '+faststart', output],
      {stdio: ['pipe', 'ignore', 'pipe']});
      let stderr = '';
      encoder.stderr.on('data', data => { stderr += data.toString(); });
      const finished = new Promise((resolve, reject) => {
        encoder.on('error', reject);
        encoder.on('exit', code => code === 0 ? resolve() : reject(new Error(stderr || `ffmpeg exit ${code}`)));
      });
      finished.catch(() => {});
      try {
        for (let frame = 0; frame < timeline.total_frames; frame++) {
          await page.evaluate(f => window.preview.setFrame(f), frame);
          const png = await page.screenshot({optimizeForSpeed: true});
          await new Promise((resolve, reject) => encoder.stdin.write(png, error => error ? reject(error) : resolve()));
          if (frame % 120 === 0) console.log(`${format.name}: ${frame}/${timeline.total_frames} frames`);
        }
        encoder.stdin.end();
        await finished;
      } catch (error) { encoder.kill(); throw error; }
      elapsed = (performance.now() - start) / 1000;
    }
    assert.deepEqual(errors, [], 'Browser errors');
    audit.formats.push({...format, reference_frames: frames, measured_word_boundary_checks: wordChecks,
      backward_seek_pixel_matches: checks.length, triangles: stats.triangles,
      geometries: stats.geometries, render_seconds: elapsed, exported: !checkOnly});
    await page.close();
    console.log(`${format.name}: ${wordChecks} word checks; deterministic seek passed${checkOnly ? '' : `; exported in ${elapsed.toFixed(1)}s`}`);
  }
  await writeFile(path.join(build, checkOnly ? 'browser_checks.json' : 'render_receipt.json'), JSON.stringify(audit, null, 2));
} finally {
  if (browser) await browser.close();
  await new Promise(resolve => server.close(resolve));
}
