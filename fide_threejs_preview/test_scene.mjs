import test from 'node:test';
import assert from 'node:assert/strict';
import {turnAt, activeWord, mouthAt, blinkAt, titleWords} from './scene_logic.mjs';
import {startServer} from './serve.mjs';

const turn = {id: 'one', start: 1, end: 2, mouth_envelope: [0, 0.8, 0.4],
  words: [{word: 'Guten', start: 0.1, end: 0.3}, {word: 'Tag.', start: 0.4, end: 0.7}]};

test('speech and word windows exclude pauses and end boundaries', () => {
  const timeline = {turns: [turn]};
  assert.equal(turnAt(timeline, 0.9), null);
  assert.equal(turnAt(timeline, 1), turn);
  assert.equal(turnAt(timeline, 2), null);
  assert.equal(activeWord(turn, 1.15), 0);
  assert.equal(activeWord(turn, 1.35), -1);
  assert.equal(activeWord(turn, 1.5), 1);
  assert.equal(activeWord(turn, 1.8), -1);
  assert.equal(activeWord(null, 1.5), -1);
});

test('RMS mouth sampling is deterministic and closes outside speech', () => {
  const before = mouthAt(turn, 1 + 1.5 / 24);
  mouthAt(turn, 1.9);
  assert.equal(mouthAt(turn, 1 + 1.5 / 24), before);
  assert.ok(Math.abs(before - 0.6) < 1e-10);
  assert.equal(mouthAt(null, 1.2), 0);
  assert.equal(mouthAt(turn, 0.9), 0);
  assert.equal(mouthAt(turn, 2), 0);
});

test('readable title groups only measured spoken words', () => {
  const words = 'fide Test A zwei B eins Sprechen Prüfungssimulation.'.split(' ')
    .map((word, i) => ({word, start: i * 0.4, end: i * 0.4 + 0.3}));
  const mapped = titleWords({words});
  assert.equal(mapped.map(word => word.word).join(' '), 'fide-test A2-B1 Sprechen Prüfungssimulation');
  assert.equal(mapped[1].start, words[2].start);
  assert.equal(mapped[1].end, words[5].end);
  assert.throws(() => titleWords({words: words.slice(1)}));
});

test('blink sampling does not depend on sampling order', () => {
  const expected = blinkAt(12.37, 0.7);
  blinkAt(90, 0.7);
  assert.equal(blinkAt(12.37, 0.7), expected);
  for (let i = 0; i < 100; i++) assert.ok(blinkAt(i / 10, 0.7) >= 0.12);
});

test('local server serves modules and rejects files outside the isolated folder', async () => {
  const {server, url} = await startServer();
  try {
    const response = await fetch(`${url}/scene_logic.mjs`);
    assert.equal(response.status, 200);
    assert.match(response.headers.get('content-type'), /javascript/);
    assert.equal((await fetch(`${url}/..%5cpackage.json`)).status, 403);
    assert.equal((await fetch(`${url}/index.html`, {method: 'POST'})).status, 405);
  } finally { await new Promise(resolve => server.close(resolve)); }
});
