---
name: advent-video-gen
description: Plan, generate, revise, and verify portrait Advent exam explainers and their social assets in advent/ using HyperFrames.
---

# Advent exam explainer videos

Use `advent/` and run commands from the repository root. This is the short
exam explainer and Advent-series promo workflow, not an exam simulation or a
listening exercise generator. A planning, refactor, covers-only, or
documentation request does not authorize speech synthesis or video rendering.

## Plan an episode

- Start with `advent/dtz-b1.json` as a working example of the episode format.
  Supported exam IDs: `dtz-b1`, `oeif-b1`, `fide-a2-b1`, `tcf-irn`, and
  `tef-canada`. DTZ and ÖIF use German, TCF IRN and TEF Canada use French, and
  fide defaults to German with an explicit `"language": "fr"` or `"it"` override.
  Write learner-friendly narration with English translations.
- Verify the exact exam and edition against the official organizer before
  writing eligibility, section structure, timings, or results. In particular,
  do not apply DTZ's scoring or task visuals to ÖIF, fide, TCF IRN, or TEF Canada.
  Record the official sources in the episode and keep any book material separate
  from official examples. Use exercise illustrations only as requested and do
  not turn an overview into a mock test.
- Author a concrete hook, promise the answer after the walkthrough, give each
  covered skill its own title, and resolve the opening question before the CTA.
  Animate images or icons that reinforce the spoken content. Use a relaxed
  pace suitable for the target learners. State what the Advent challenges
  offer, the confirmed dates, and a follow/subscribe CTA. The 2026 DTZ, ÖIF and
  TEF series use December 1–14, 2026; confirm dates for future series.
- The `script` JSON contains `[scene_id, title, [[spoken_text, english], ...]]`
  rows, starting with `hook` and ending with `advent`. `beats` maps each scene
  ID to `[tag, visual_id, ...]`, with one visual per phrase. `graphics` points
  to a JSON map of visual IDs to trusted, local HTML/SVG fragments. Author
  localized visuals; the reserved `question` / `result-a2` score-card pair is
  DTZ-only. `visual_assets` maps filenames (including the winter background
  `market.jpg` or a local `market.svg`) to path/SHA-256 pairs, with an optional HTTPS `download`
  fallback. Input paths are relative to the episode. Link only local assets
  (by destination filename) from the artwork, and keep credits with the episode.
- Pin the Qwen model ID, approved local reference WAV, its exact transcript,
  and tempo under `voice`. Check the appropriate book's voice manifest or
  approved reference; do not silently reuse the DTZ narrator for other exams.
  For TEF Canada verify the locale and a suitable French reference (e.g. Québec
  French if requested).
  Use `spelling` for spoken-to-written forms (`B eins` → `B1`, for example);
  word highlighting must use measured intervals. For a graphic timed to speech,
  add `data-reveal-word` to the artwork element with the exact displayed token
  for that phrase; the compositor uses its measured onset. Compare encoded
  frames immediately before and at the reveal.

## Reference episodes

| Exam | Known export under `advent/build/` | Opening and reveal |
| --- | --- | --- |
| DTZ B1 | `winter-v7/dtz-b1-advent-v7.mp4` | Existing DTZ result-card example. |
| ÖIF B1 | `oeif-b1-advent-r5/advent.mp4` | A2 writing stamp with stock impact; reveal the certificate icon on „B1-Zeugnis“. Keep the separate values-section pass in the example and payoff. |
| TEF Canada | `tef-canada-advent-r3/advent.mp4` | Reveal the 2 and 4 cards on « deux » and « quatre ». Explain the distinction between immigration and citizenship at the end. |

Use the pinned listening-book narrators in `oeif-b1.json` (Austrian German) and
`tef-canada.json` (Québec French). Automated recognition of the ÖIF opening
acronym was inconsistent; retain that review note when reusing the narration.
For visual or mix-only revisions, copy only clips whose wording, voice binding
and hashes match. Use a fresh build and verify unchanged word timings and frame
count. For a visual-only change, require a byte-identical `mix.wav`.

Keep the ÖIF and TEF winter backdrops and stock tracks distinct from DTZ and
each other. Use `opening_flag: "at"` or `"ca"` for a large centered flag above
the opening badge. `opening_stamp_frame` times the `.hook-stamp` graphic and
the stock impact together; verify both on the same frame. The `stock_manifest`
follows `winter_sources.json`. Keep the music below the narration: the verified
ÖIF and TEF mixes use `music_gain` of `0.055` and `0.10`, respectively. Check
the mix rather than assuming these gains fit every track. Credit the assets in
the posting descriptions, not an end-credit slide.

## Generate and verify

Use an existing Python environment with Qwen TTS, WhisperX, NumPy, SoundFile
and Torch, plus FFmpeg/FFprobe, `advent/` npm dependencies and Chrome. Set
`CHROME_PATH` to the browser executable for `check`. Use a fresh build path
for every revision; keep the prior video, clips, and posting drafts intact.

```sh
python advent/advent_pipeline.py plan --episode "$episode"
python advent/advent_pipeline.py speech --episode "$episode" --build "$build"
python advent/advent_pipeline.py prepare --episode "$episode" --build "$build"
python advent/advent_pipeline.py check --episode "$episode" --build "$build"
python advent/advent_pipeline.py render --episode "$episode" --build "$build"
```

Set `episode=advent/dtz-b1.json` for the reference or point it at a new episode
file. Set `build` to a new directory under `advent/build/`. `plan` is read-only
and does not require the pinned media to be locally available. Only proceed with
production when requested. Review audio
for pace, omissions, and pronunciation; retry rejected zero-based clip indices
with `speech --retry ...` before preparing. Inspect the bilingual captions,
animated foreground safe-area bounds, hook and reveal, and the CTA before
rendering. Afterward fully decode `advent.mp4` with FFmpeg, check dimensions,
24 fps and measured audio/video durations, and inspect encoded frames at
scene boundaries. Browser safe-area tests do not certify in-app platform UI.

When asked for publishing assets, prepare separate localized Instagram,
TikTok, and YouTube Shorts drafts and 1080 × 1920 JPG covers. Feature the Advent
practice series and dates, not the opening question. Center the country flag
above the exam name (Germany for DTZ, Austria for ÖIF, Canada for TEF Canada).
Check the entire foreground against the safe area and square, 4:5, 3:4, and
zoomed-square crops; inspect proofs made from the exported JPEGs.

Use `advent/publishing/make_covers.py` for DTZ. For ÖIF and TEF, see
`posts/oeif_b1_advent_2026_r5/` and `posts/tef_canada_advent_2026_r3/`.
In new bundles, bind the exact export and posting assets by SHA-256 and note a
verified calendar frame for interfaces that require an in-video cover. Include
verified exam sources, stock credits, and the relevant AI narration and
book-promotion disclosures. A covers-only update must not change the video or
copy. Do not upload automatically.
