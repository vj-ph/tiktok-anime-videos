export function turnAt(timeline, time) {
  return timeline.turns.find(turn => time >= turn.start && time < turn.end) ?? null;
}

export function activeWord(turn, time) {
  if (!turn) return -1;
  const local = time - turn.start;
  return turn.words.findIndex(word => local >= word.start && local < word.end);
}

export function mouthAt(turn, time) {
  if (!turn || time < turn.start || time >= turn.end) return 0;
  const samples = turn.mouth_envelope;
  const position = (time - turn.start) * 24;
  const index = Math.floor(position);
  const amount = position - index;
  return (samples[index] ?? 0) * (1 - amount) + (samples[index + 1] ?? 0) * amount;
}

export function blinkAt(time, offset) {
  const phase = ((time + offset) % 4.7 + 4.7) % 4.7;
  return phase < 0.14 ? 0.12 + 0.88 * Math.abs(phase - 0.07) / 0.07 : 1;
}

export function titleWords(turn) {
  const groups = [
    {text: 'fide-test', from: 0, to: 1},
    {text: 'A2-B1', from: 2, to: 5},
    {text: 'Sprechen', from: 6, to: 6},
    {text: 'Prüfungssimulation', from: 7, to: 7},
  ];
  if (turn.words.length !== 8) throw new Error('Unexpected aligned title: map actual words explicitly.');
  return groups.map(group => ({
    word: group.text,
    start: turn.words[group.from].start,
    end: turn.words[group.to].end,
  }));
}
