import {createRoom} from './room.mjs';
import {turnAt, activeWord, titleWords} from './scene_logic.mjs';

const params = new URLSearchParams(location.search);
const build = params.get('build') ?? 'preview_swiss_r1';
if (!/^[\w-]+$/.test(build)) throw new Error('Invalid build name');
document.body.classList.toggle('capture', params.has('capture'));
const response = await fetch(`builds/${build}/timeline.json`);
if (!response.ok) throw new Error('Prepare speech first: timeline.json is missing.');
const timeline = await response.json();
const room = createRoom(document.querySelector('#scene'));
const caption = document.querySelector('#caption');
let currentId, spans = [], displayTurn, lastFrame = 0;
const audio = new Audio();
audio.preload = 'none';
if (!params.has('capture')) audio.src = `builds/${build}/dialogue.wav`;
let running = false;
function seek(time) {
  const t = Math.max(0, Math.min(time, timeline.duration - 1 / timeline.fps));
  const turn = turnAt(timeline, t);
  const previous = [...timeline.turns].reverse().find(item => t >= item.start);
  const shown = turn ?? previous;
  if (shown?.id !== currentId) {
    currentId = shown?.id;
    const words = shown?.id === 'title' ? titleWords(shown) : (shown?.words ?? []);
    displayTurn = shown ? {...shown, words} : null;
    caption.replaceChildren(...words.map(word => {
      const span = document.createElement('span');
      span.className = 'word';
      span.textContent = word.word;
      return span;
    }));
    spans = [...caption.children];
  }
  const index = turn ? activeWord(displayTurn, t) : -1;
  spans.forEach((span, i) => span.classList.toggle('active', i === index));
  document.querySelector('#phase').textContent = shown?.phase ?? 'Technikvorschau';
  document.querySelector('#speaker').textContent = shown?.speaker === 'candidate' ? 'Kandidatin · Modellantwort' : 'Prüfer';
  document.querySelector('#time').textContent = `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(Math.floor(t % 60)).padStart(2, '0')}`;
  document.querySelector('#seek').value = t / timeline.duration;
  const state = room.draw(t, turn);
  lastFrame = Math.round(t * timeline.fps);
  return {time: t, frame: lastFrame, turn: turn?.id ?? null, word: index, ...state};
}
window.preview = {
  timeline,
  seek,
  setFrame: frame => seek(frame / timeline.fps),
  bounds() {
    return ['header', '.phase', '.people', '.task', '.speech', '#caption', 'footer'].map(selector => {
      const element = document.querySelector(selector);
      const r = element.getBoundingClientRect();
      return {selector, x: r.x, y: r.y, width: r.width, height: r.height,
        overflow: element.scrollHeight > element.clientHeight + 1 || element.scrollWidth > element.clientWidth + 1};
    });
  },
};
document.querySelector('#play').addEventListener('click', async () => {
  if (running) { audio.pause(); running = false; }
  else { audio.currentTime = lastFrame / timeline.fps; await audio.play(); running = true; tick(); }
  document.querySelector('#play').textContent = running ? 'Pause' : 'Abspielen';
});
document.querySelector('#seek').addEventListener('input', event => {
  const t = Number(event.target.value) * timeline.duration;
  audio.currentTime = t;
  seek(t);
});
function tick() {
  if (!running) return;
  seek(audio.currentTime);
  if (audio.ended) {
    running = false;
    document.querySelector('#play').textContent = 'Abspielen';
  } else requestAnimationFrame(tick);
}
seek(0);
window.preview.ready = true;
