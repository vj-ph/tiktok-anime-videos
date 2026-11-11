# 2D listening videos: ÖIF B1 simulation

Planning date: November 8, 2026.
Status: full production and four reduced-practice portrait cuts complete and
validated, with earlier previews preserved. Human listening remains separate.
No publication.

## Goal and scope

Create a reusable graphics-and-text listening template without Blender or
3D characters. Start with ÖIF B1 / Deutsch-Test für Österreich (DTÖ).
Use simple 2D motion, spoken instructions, reading time, listening recordings
and answer marking. The November 9 revision selects guided practice with a
separate three-second answer reveal after each full answer pause.

Keep this implementation separate from `pilot_3d` and preserve its active jobs,
approved audio, frozen builds and deliveries. Suitable speech/alignment helpers
may be reused later without depending on Blender.

## Official process and version

The official B1 DTÖ Übungstest 1 lists approximately 25 minutes for listening,
four sections and 20 questions:

| Section | Listening content | Tasks |
| --- | --- | --- |
| Teil 1 | Telephone and public announcements | 1-4: four multiple-choice tasks |
| Teil 2 | Radio announcements | 5-9: five multiple-choice tasks |
| Teil 3 | Everyday conversations | 10-17: four true/false and four multiple-choice tasks |
| Teil 4 | Opinions about one topic | 18-20: three matching tasks using statements a-f |

Teil 4 explicitly provides one minute to read statements a-f.
The other reading intervals, examples, recording repetitions and
answer-marking pauses must be checked against the corresponding official audio
before authoring an exam-paced timeline. Do not invent a common five-second
pause or import DTZ timing defaults without checking the ÖIF source.

User-supplied section timing was recorded on November 8, 2026 in
`.github\skills\oeif-b1-listening-video-gen\SKILL.md`. Use that reference for
the specified cue/pause sequences; its approximate pauses are not independently
verified official timings. Check the selected official audio for remaining
rules and preserve the chosen durations in the measured episode timeline.

**Version caveat:** the Modelltest PDF linked on the official site during
research states that it is valid from **February 1, 2027**. Do not silently
treat that future-dated document as the November 2026 exam specification.
Übungstest 1 was also checked and has the structure above. Pin the applicable
PDF/audio version and record the evidence for each timing/repetition rule.

### Verified version comparison (November 8, 2026)

Compared the official current A2/B1 DTÖ Modelltest with the B1 Modelltest
valid from February 1, 2027. The effective date labels the whole language
model test, not listening alone; it does not establish changes to the separate
values-and-orientation test.

- The task-format table, listening/reading/writing/speaking task pages,
  listening transcripts and answer key are unchanged in normalized extracted
  text. Listening remains four sections, 20 tasks and approximately 25 minutes.
- The material change is certification (printed pages 38-40). The future
  model removes the A2-certificate route. B1 requires speaking at B1, one of
  the combined listening/reading or writing result blocks at B1, and the other
  block at least A2. The current model also allows B1 with the latter block
  below A2; those two combinations are removed.
- The user's `..\german\books\b1\listening_oeif` task structure remains
  compatible. The combined speaking/writing paperback also retains compatible
  core practice: the official writing task is still 30 minutes, an A/B choice,
  at least 100 words and four content points. Its single-task mocks and shorter
  examples need the already documented expansion for a full simulation.
- The current B2 model is valid from October 15, 2026. Its writing task uses
  a choice of two essays, at least 200 words and 40 minutes (printed page 23);
  do not import B1 writing rules into B2.
- The current A2 model has a January 15, 2026 update marker in its PDF metadata,
  but no February 2027 effective-date notice was found. Metadata identifies a
  document revision, not proof of a newly changed exam format.

Official sources:

- [B1 DTÖ Übungstest 1](https://sprachportal.at/kurse-und-pruefungen/pruefungsmaterialien/uebungstests/b1-dtoe-uebungstest-1/)
- [B1 DTÖ Modelltest](https://sprachportal.at/kurse-und-pruefungen/pruefungsmaterialien/uebungstests/b1-dtoe-modelltest/)
- [Current A2/B1 DTÖ Modelltest](https://sprachportal.at/fileadmin/user_upload/meinsprachportal-at/Materialen_zur_Pruefungsvorbereitung/A2/A2-B1_Deutsch-Test_fuer_Oesterreich_Modelltest.pdf)
- [A2 ÖIF-Test neu Modelltest](https://sprachportal.at/fileadmin/user_upload/meinsprachportal-at/Materialen_zur_Pruefungsvorbereitung/A2/OEIF-TEST_neu_Modelltest.pdf)
- [B2 ÖIF-Test Modelltest, valid from October 15, 2026](https://sprachportal.at/kurse-und-pruefungen/pruefungsmaterialien/uebungstests/b2-oeif-test-modelltest/)

These are process references, not permission to republish official questions,
recordings or artwork. Select the user's appropriate listening-book exercises
or other permitted content later; record transcript, question, answer and audio
provenance.

### Episode 1 content and audio decisions (November 9, 2026)

The user selected the B1 listening book as a reference, not material to copy
directly. `episodes\oeif_b1_listening_01.json` is a fresh full-test script draft
using Übungstest 1's task structure and everyday listening skills. It changes
scenarios, questions, distractors, answer positions and recordings rather than
only substituting names or numbers. It includes all 20 tasks and original
examples for Teile 1, 3 and 4. The book and official transcript remain unchanged.

- Promotion: `https://amzn.eu/d/09gWva0w`, supplied by the user for this book;
  use its `oeif_b1_hoeren.jpg` cover.
- Synthesize from the existing speaker-reference voices after verifying and
  binding exact reference files/transcripts. Do not claim they have been
  checked or generated merely because voice roles are drafted.
- Apply FFmpeg `atempo=0.8` to synthesized speech. Preserve pitch and measure
  the processed recordings before scheduling pauses or highlights.
- Use discrete sound-effect cues only. No background music or environmental
  ambience. The user subsequently requested `atempo=0.8` and subtle reverb for
  chimes; preserve originals and measure derived files including full tails.
  Software interface start precedes the initial example cue; back follows
  an exercise's complete answer silence, immediately before the next number.
  Neither chime nor its tail may overlap the prescribed silence.
- The original simulation mode kept scored answers/transcripts hidden until
  a separate review chapter. The later guided-mode revision below adds
  post-pause answer reveals; listening transcripts stay hidden. A score out
  of 20 is practice feedback, not an exam certification decision.
- The user approved the revised script and short sample work with "ok, carry on"
  on November 9. Audio and preview approval remain separate. Duration is
  measured for the sample only; a complete 20-task practice set is not proof
  of official pacing.

The November 9 editorial revision resolves supported option/question
ambiguities, strengthens paraphrased distractors and tests changed plans and
conditions. The course and celebration dialogues are replaced with bicycle
buying and moving; the sports dialogue no longer reuses the book's rain-driven
schedule change. Teil 4 explicitly uses each statement at most once and leaves
two unused statements. The 20 scored keys remain consistent; the 0.8 speech
setting and pause reference are unchanged. Structural checks passed for tasks,
options, examples, matching assignments and file links. Difficulty is targeted
at B1 but has not been formally calibrated; human script/audio review remains
separate from those checks. Subsequent script approval is recorded above.

## Two explicit learning modes

### Exam simulation

This remains an optional mode, not Episode 1's current selected presentation.

1. Spoken section instruction and any required example.
2. Question/options visible during the verified reading interval.
3. Listening recording with the task card remaining visible.
4. Verified answer-marking interval, then the next task.
5. After the complete simulation, show the answer key and optional learning review.

Do not reveal answers between tasks in an uninterrupted simulation.
Do not show the listening transcript or word-highlighted listening subtitles
during the exam portion: these would provide reading assistance.
Avoid graphics that reveal the answer indirectly.

### Guided practice

Instruction -> reading interval -> listening -> answer interval -> solution
and short explanation for each exercise. Label this as guided practice rather
than an uninterrupted official exam simulation.

On November 9, the user selected this presentation for Episode 1, requesting
brief answer reveals after each complete answer silence. The chosen duration
is three seconds, with the correct option highlighted and "Richtige Antwort"
shown; no added narration or explanation is needed for the preview.
Place back after the reveal, immediately before the next task number.
The base reading/answer pauses remain untouched, including their original
approximate-timing provenance.

An optional transcript replay belongs in the review phase, with word-level
highlighting based on measured alignment of the actual audio. Spoken opening
titles and Anleitung should likewise use measured highlights. Keep
display-to-speech mappings for numbers and abbreviations explicit; never
estimate missing timestamps or display a changed instruction against old audio.

Full listening simulation is a long-form project, not a forced under-90-second
clip. Set an explicit measured duration budget after selecting the content.
Separate shorter lessons or social derivatives must retain a clear scope label.

## Visual direction

**Ending cue:** user selected Mixkit "Software interface back" on November 8,
2026. Use `assets\sfx\mixkit-software-interface-back-2575.wav` (1.329433 seconds);
source, license and SHA256 are recorded in `assets\sfx\sources.json`.
Treat the processed chime as a separate timeline event, not part of a silent
pause. The November 9 placement and slowed/reverberant processing decisions
are recorded above and in `assets\sfx\sources.json`.

**Instruction draft:** `instruction_templates.json` adapts the supplied
`assets\model.txt` transcript into four section instructions, example/number/end
cues and a separate solution transition. It includes a proposed independent
practice title and documents missing/garbled source cues. The source remains
unchanged; wording, examples, naming and audio still require review.

- Large, readable question text and numbered answer options.
- Light, relaxed sage/cream palette with dark text; preserve contrast and
  native phone-safe layouts rather than merely reducing text opacity.
- Stable cards during reading and listening; restrained fades/slides at transitions.
- Reading countdown and quiet "Jetzt hören" / answer-marking indicators.
- No background music or distracting motion during listening.
- Deutsch Kompass branding and a small persistent book/Amazon panel once the
  correct book is selected; retain a distinct final CTA.
- Native 1920x1080 YouTube and 1080x1920 portrait compositions, with phone-safe
  typography and promotion placement.

Use one measured audio timeline for both layouts, but reflow the cards,
captions, promotion and CTA separately. Do not crop the completed YouTube video
to create the social layout. The reduced-Cycles/on-twos production preset is
for 3D and does not determine this browser-rendered template's motion policy.

## HyperFrames evaluation

HyperFrames supports HTML/CSS/JavaScript video compositions, browser preview,
snapshots and local rendering. It is the proposed rendering layer for cards,
text, icons, progress indicators and light animation.

Documented dependencies: Node.js 22+, FFmpeg and an available supported browser.
Environment check on November 8 found Node.js 25.8.0, FFmpeg and FFprobe.
Neither `hyperframes` nor `anycap` was found on PATH during that initial check.
On November 9, installed HyperFrames 0.9.2 and GSAP 3.15.0 as pinned local
dependencies with a lockfile. CLI diagnostics found system Chrome, Node and
FFmpeg. No global HyperFrames install or skills install was performed.
`hyperframes_local.py` sets telemetry, update/auto-install and skill opt-outs
in the process environment; the project `.env` supplies only supported
telemetry opt-outs. The wrapper selects installed system Chrome when available,
while preserving an explicit browser-path override. This avoided a browser-cache
installation race during rendering. AnyCap remains uninstalled.

Keep authored data separate from rendering: exercise IDs, question/options,
answer key, audio references, source provenance and phase rules should produce
an explicit frame/sample-clock timeline. The renderer should consume that
timeline rather than guess durations from text length.

Use local assets/fonts and pinned dependencies for reproducible delivery.
Keep cloud rendering, remote TTS, telemetry and auto-update behavior explicit;
do not upload project media as a side effect of a local validation step.

Documented starter workflow, for later approved implementation:

```powershell
npx hyperframes init oeif-b1-listening --resolution landscape --non-interactive --skip-skills
Set-Location .\oeif-b1-listening
npx hyperframes preview
npx hyperframes check --json
npx hyperframes snapshot --at 0,5,10
npx hyperframes render --quality delivery --output preview.mp4
```

These commands have not been run. Check the selected installed version's help
before using its flags; pin the project version rather than relying on a
changing `npx` resolution for final production.

References:

- [CLI guide](https://hyperframes.heygen.com/developers/cli)
- [CLI reference](https://hyperframes.heygen.com/packages/cli)

### Validated Teil 1 preview (November 9, 2026)

Run: `builds\oeif_b1_listening_sample_r1`.
This is a 154-second preview, not the full test: opening, Teil 1 instruction,
example, task 1, preview-only ending and CTA. Nine actual Qwen speech clips
use the pinned Austrian male/female references and measured WhisperX alignment.
Speech and derived start/back chimes use `atempo=0.8`; chimes include subtle
decaying reflections. No background sounds were added.

- `preview_landscape.mp4`: native 1920x1080, 24 fps, 3696 frames.
- `preview_portrait.mp4`: native 1080x1920, 24 fps, 3696 frames.
- `contact_landscape` and `contact_portrait`: eleven browser frames and two
  contact sheets each, regenerated after the portrait-footer spacing fix.
- `encoded_landscape\contact-sheet.jpg` and
  `encoded_portrait\contact-sheet.jpg`: inspected actual export frames,
  including measured title highlights, task phases, the final answer-pause
  frame, back-cue boundary, preview ending and CTA.

Both final browser checks passed runtime/layout/contrast/audio checks.
Seventeen static composition-structure recommendations remain per layout;
the motion checker was disabled, not a verified motion pass.
Two focused alignment-mapping tests and modified-helper syntax checks passed.
`validation.json` records full MP4 decode, native dimensions, frame counts,
export hashes, all sixteen encoded audio-event checks and audio correlation
0.99676 against the source timeline in both formats.

The four source silences are exactly 10/10/12/12 seconds of zero PCM.
Encoded silent interiors passed peak/RMS limits, with a documented 2048-sample
AAC boundary guard; chimes and their full tails remain outside those intervals.
Original SFX hashes and measured speech placement are unchanged. Task 1's answer
and transcript remain hidden; the example solution is confined to its answer phase.

Human listening has not been performed. Independent small-Whisper review retained
seven flags, mainly numeral/orthographic differences. The standalone "Beispiel"
cue was not reliably recognized, and possible "welcher"/"welche" and
"Startpark"/"Stadtpark" differences need listening review. These are not confirmed
pronunciation errors or automatic clearance. Full-test synthesis, preview approval
and publication remain separate pending stages.

### Light-theme guided preview r2 (November 9, 2026)

Run: `builds\oeif_b1_listening_sample_r2`. The user's visual/learning revision
is implemented in native YouTube and portrait layouts with pale sage/cream,
dark readable text and actual word highlighting for all 42 Anleitung words.
Both `preview_landscape.mp4` and `preview_portrait.mp4` are 160 seconds,
3840 frames at 24 fps; dimensions remain 1920x1080 and 1080x1920.

After each complete response pause, a separate silent three-second scene
highlights the correct option and shows "Richtige Antwort". The example also
uses this sequence. Back follows the reveal, before the next spoken cue;
the original 10/10/12/12-second silences and processed chime tails are unchanged.
The opening/footer and post drafts identify guided practice, not uninterrupted
exam simulation. No task transcripts or extra answer narration were added.

The nine original speech clips and measured local word intervals are reused.
Later timeline and alignment-receipt turn starts are retimed by the added
scenes. `input_pin.json` binds the source build and original video/timeline
hashes, which pass preservation checks. Do not regenerate r1 with changed inputs.
The approved full script's mode setting now records guided practice and
`answer_reveal_seconds: 3`; no recording/question text changed.

Nine focused tests pass, including instruction timing/text rejection, solution
gating, exact pause preservation and alignment-receipt retiming. Both final
browser checks pass runtime/layout/contrast/audio checks, with 19 static
structure recommendations per layout; the motion checker remains disabled.
`validation.json` passes full decode, native dimensions, frame counts and all
18 encoded audio/reveal events, with overall audio correlation 0.99673.
Original source silences are zero PCM; encoded silence/reveal interiors pass
the documented AAC-guarded peak/RMS checks.

`contact_landscape` / `contact_portrait` contain 17 browser frames and two
contact sheets each. `encoded_landscape\contact-sheet.jpg` and
`encoded_portrait\contact-sheet.jpg` contain inspected export frames, including
Anleitung highlighting, the final answer-pause frame, first/last reveal frames,
back after the complete reveal and the CTA. Seven export-to-browser pixel
comparisons per layout pass; results are in `export_visual_review.json`.
Human audio flags remain unchanged because speech was reused. Full-test
generation, human preview approval and publication remain pending.

### Reveal sound revision r3 (November 9, 2026)

Run: `builds\oeif_b1_listening_sample_r3`. Software interface remove now begins
at both correct-answer reveal starts, using the existing `atempo=0.8` and subtle
reverb filter. Its measured duration including the full tail is 2.866896 seconds,
inside each unchanged three-second reveal. The original 10/10/12/12-second
silences, speech, back cues, word highlights and 160-second timeline are unchanged.

Both MP4s reuse r2's compressed video streams without re-encoding.
`video_reuse.json` verifies matching video-stream hashes and identical HTML/
visual assets; the existing r2 contact sheets therefore remain applicable.
Only the audio tracks are replaced. Eleven focused tests pass, including exact
PCM placement at reveal onset and rejection of oversized tails. Full decode,
3840 frames at 24 fps, all eighteen encoded audio events and silence checks pass
in both ratios. `validation.json` records the output hashes; source hashes verify
r2 preservation. Original Mixkit assets remain unchanged. No new speech,
background audio, full-test generation or publication was added.

### Presentation cleanup r4 (November 9, 2026)

Run: `builds\oeif_b1_listening_sample_r4`. Removed the guided-practice/byline
and solutions-after-each-task lines from the title and persistent footer.
The remaining preview-scope label, logo, book/Amazon panel and CTA stay visible.
Lower phase labels now use a bold warm brown accent (`#875a3b`), distinct from
the main dark text and green countdown/highlight styling. Guided mode remains
documented in metadata/post descriptions rather than as another on-screen line.

Both native 160-second/3840-frame/24-fps MP4s were re-rendered. The complete
source WAV is byte-identical to r3; final exports also copy r3's encoded audio
stream, verified in `audio_preservation.json`. Speech, all chimes, three-second
reveals, 10/10/12/12-second silences and measured highlights are unchanged.
Source hashes verify preservation of the previous preview.

Twelve focused tests pass, including generated-slide regression checks for
removed text and phase-label markup. Both browser/layout/contrast checks pass.
Full decode, frame counts, all eighteen encoded audio-event/silence checks and
eight export-to-browser pixel comparisons per layout pass. The motion checker
remains disabled; static structure recommendations are not playback failures.
Inspected native title/instruction/reading images and exported contact sheets.

`contact_landscape` / `contact_portrait` contain eleven browser frames and two
contact sheets each. `encoded_landscape\contact-sheet.jpg` and
`encoded_portrait\contact-sheet.jpg` show the final exports; comparison metrics
are in `export_visual_review.json`. No full-test generation or publication.

### Completed full production (November 9, 2026)

The user accepted r4 and requested the full production video. Build:
`builds\oeif_b1_listening_full_production_r1`. This authorizes generation in both
native ratios, not publication. Preserve the approved inputs and all previews.

`prepare_full.py` plans 81 speech turns, 160 audio/timing events, all 20 scored
questions and three example groups. Nine roles are bound to five verified
Austrian references, with distinct dialogue partners and three opinion voices.
Compatible approved sample speech is reused by exact text/reference/PCM hashes.
New speech is synthesized locally and processed at atempo=0.8.

The initial synthesis attempt stopped before generating new speech because
the model loader's metadata request was incompatible with HF_HUB_OFFLINE.
Removing that process-only setting restored model loading; the attached
`listening-full-speech-retry` job subsequently completed all recordings.

`compose_full.py` adds paired true/false-plus-MC and six-option matching cards,
all four Anleitung mappings, a final 20-key summary, persistent promotion and
the existing CTA. Consecutive dialogue turns share a visual card, producing
129 visual scenes without changing audio events or pauses. `align_full.py`
reuses verified matching sample word intervals and force-aligns the remaining
visible instructions; task transcripts are never shown.

`validate_full.py` checks exact source PCM, all 40 prescribed/authored silence
intervals, reveal/cue order, source preservation, keys and narration mappings.
Its event-wise encoded checker avoids loading long float audio arrays.
Twenty-one focused tests pass; the new encoded checker also passes all 18
existing r4 events in both native formats without changing either source.
This diagnostic is not a full production export.

The complete measured track is 31,810 frames at 24 fps: 1,325.416667 seconds
(22:05.417), including all pauses, reveals, summary and CTA. `audio_ready.json`
records its WAV hash. All 196 Anleitung words plus the title use measured
alignment. Full source validation passes all 160 events and 40 silence intervals.
The final closing back follows task 20's reveal before the end-of-listening cue.

Both real browser/runtime/layout/contrast/audio checks pass. Inspected five
contact sheets per layout, containing 38 measured native frames each; all
reading cards, paired/matching reveals, instructions, summary and CTA fit.
The persistent book/Amazon panels are pixel-identical across those frames.
`pre_render_checks.json` records these gates and the actual report paths.

Each layout retains 130 static structure recommendations (129 nested-scene
recommendations and one dense-track warning) and 48 craft recommendations:
22 intentional still stretches, 25 short repeated-card exposure warnings and
one text-floor warning. The same questions remain visible across cue, reading,
listening and answer phases; do not shorten the requested pauses or add
distracting motion merely to silence these heuristics. Small secondary labels
and landscape matching text are below the generic 28-pixel craft floor.
The motion checker remains disabled, not a verified motion pass.

Primary local ASR covers all 81 turns, with 35 strict token matches. Many
disagreements are number spelling or orthography; an unprompted cached medium
model rechecks substantive differences. Keep original disagreements and
unresolved pronoun/name readings; this is not human listening certification.
The medium recheck covers eight turns, resolving both final-section flags too.
Unconfirmed readings remain documented in `speech_review_notes.json`.

Both delivery-quality native exports are complete:

- `production_landscape.mp4`: 1920x1080, 24 fps, 31,810 frames; 43,702,683 bytes.
- `production_portrait.mp4`: 1080x1920, 24 fps, 31,810 frames; 43,859,090 bytes.

Each passes full decode, all 160 encoded event checks and all 40 encoded
silence checks. Silent interiors are exactly zero PCM beyond the documented
2048-sample AAC boundary guard. Audio correlation is 0.998306 overall and at
least 0.994975 for every individual audio-bearing event.

All 38 export/browser frame comparisons pass in each format, including the
last answer-pause/first reveal frames, four Anleitung highlights, paired and
matching cards, final solution grid and CTA. Maximum mean absolute RGB error
is 2.429 landscape / 2.472 portrait, below the existing threshold of 4.
Inspected exported sheets 1/3/5 landscape and 3/4/5 portrait after the complete
native-browser sheet review. Both `encoded_landscape` and `encoded_portrait`
contain 38 native decoded PNGs and five contact sheets.

`delivery_manifest.json` records final MP4 hashes, sizes, dimensions, event/
frame metrics and hashes of all supporting receipts. `source_validation.json`
preserves the original pre-render report and matches its recorded hash;
`validation.json` includes final encoded checks. All original previews, source
books, voice references and downloaded SFX remain unchanged. Human listening
is not certified; ASR notes remain in `speech_review_notes.json`.

Full posting drafts with measured chapters are in
`posts\oeif_b1_listening_full_01`. This is a local production delivery only;
no upload or publication is authorized or performed.

### Reduced-practice portrait cuts (November 9, 2026)

The user approved four under-three-minute selections with fewer exercises,
not shortened pauses. Separate build: `builds\oeif_b1_listening_reduced_r2`.
The original full production and earlier previews remain unchanged.

| Clip | Original task numbers | Questions retained | Measured clock |
| --- | --- | --- | --- |
| Teil 1 | 1-2 | 2 of 4 | 3444 frames / 143.5 seconds |
| Teil 2 | 5-6 | 2 of 5 | 3240 frames / 135 seconds |
| Teil 3 | 10-13, two complete conversations | 4 of 8 | 3803 frames / 158.458333 seconds |
| Teil 4 | 18-19 | 2 of 3 | 4128 frames / 172 seconds |

`reduce_full.py` copies approved per-turn WAVs unchanged, preserves every
selected cue, reading interval, answer pause and three-second remove reveal,
and retains the original final voiced CTA. Teil 4 also retains its initial
60-second reading pause and all six matching options. It omits instructions,
examples, whole-section ending claims and the full-test answer summary.
No new synthesis, audio-edge trimming or additional tempo processing is used.

Each 1080x1920/24-fps composition has a six-second silent scope introduction,
the persistent notice "Verkürzte Übung · Ausgewählte Aufgaben", original task
numbers and selected/full counts. The book panel says
"Amazon: Bio / Beschreibung" with the pointing-down cue, allowing one portrait
delivery to serve TikTok and YouTube Shorts. No removed byline/mode text returns.

The video cutter reuses exact frame ranges from the approved portrait MP4.
Browser-captured constant overlays replace only the notice, book/Amazon panel
and subset footer; the new opening is a native browser still. The source WAVs
are mixed on the unchanged 2000-sample frame clock, avoiding a second lossy
audio decode of the long export. Original/source frame ranges and overlay
boxes are saved in each `teil_N\render_command.json`.

All 26 listening tests pass, including five reduced-mode regressions for
selection/pair integrity, unchanged pauses, strict duration rejection, frame
range completeness, persistent labels and reveal gating. All four native
browser checks pass runtime/layout/contrast/audio with no errors; motion
checking remains disabled. Static/craft recommendations remain nonblocking.
The 54 browser snapshots verify constant book/notice/footer regions and sample
every retained recording, reading screen, final answer frame, first reveal
frame and final CTA.

All four `teil_N\production_portrait.mp4` deliveries pass full decode, exact
frame counts and strict under-180-second video/audio/container duration checks.
All 70 encoded events and 21 silent intervals pass, including the silent
openings and the complete 60-second reading interval. Overall audio correlation
is at least 0.999820; the minimum individual audio-event correlation is 0.999462.
All 54 export/browser comparisons pass with maximum mean RGB error 2.330555
(threshold 4). Nine encoded contact sheets were visually inspected, including
opening/subset labels, dense paired questions, all matching options, hidden
answers before reveals, the promotion and final CTA. The 48-file receipt/export
hash manifest is `delivery_manifest.json`; source preservation passes again
after encoding. Inherited speech-review flags remain linked from that manifest;
this cut does not claim a new human listening or accent review.

Reproduce in a fresh build with `reduce_full.py prepare --source <full-build>
--build <new-build>`, followed by `check`, `review`, `render` and `verify`, each
with the same `--build`. Use `..\pilot_3d\.venv\Scripts\python.exe -X utf8` from
the listening workspace. Existing render paths are rejected rather than
overwritten. The earlier reduced r1 is a layout-only iteration with a shorter
opening, not a video delivery.

YouTube/TikTok drafts are in `posts\oeif_b1_listening_reduced_01\teil_N\`.
They explicitly describe selected tasks, preserved pauses and independent
guided practice, retaining the book link, AI disclosure and Mixkit credits.
Generation approval is not publication approval; nothing has been uploaded.

### Voiced openings and mobile typography revision (November 9, 2026)

The user requested title-only speech on the four reduced opening cards and
removal of their task-count/pause-explanation paragraphs. They also requested
larger mobile question/option text without overflowing the cards. Separate
build: `builds\oeif_b1_listening_reduced_r3`; preserve reduced r2 and full
production, including their pinned generators.

`revise_reduced.py` synthesizes only four titles with the original Austrian
male narrator: "ÖIF B1 Hören Teil 1" through "Teil 4". The pronunciation text
spells out the abbreviation/numbers as in the approved long opening. Each new
recording is prepared once, slowed once with atempo=0.8, measured and fitted
without truncation into the unchanged six-second opening. The new WAVs measure
approximately 2.98/2.78/2.78/2.99 seconds. Raw/prepared/slowed audio hashes,
reference pins and independent unprompted small-ASR results are retained.
All four transcriptions identify the correct section; abbreviation and
Hören/Hörn spelling variants are not claimed as human pronunciation clearance.

The title, "Verkürzte Übung", persistent scope notice, subset footer and book/
Amazon panel remain. Remove only the two explanatory paragraphs from the
opening body; all task text, keys, numbering, pauses, reveal cues and final CTA
stay unchanged. The mixed WAV after the opening must remain byte-identical to
reduced r2, with no change to any event boundary or total duration.

Portrait MC prompts/options now use 56/48 px; paired prompts/options 42/40 px;
matching prompts/options 48/40 px. Tighter option padding/gaps preserve space.
`check_reduced_mobile.cjs` measures every scene with existing Puppeteer/Chrome:
questions must be at least 42 px, options at least 40 px, with no horizontal
overflow and at least 12 px clearance below the last card element. All 57
scenes fit in the initial typography preflight; all 29 listening tests pass.

This revision uses native HyperFrames delivery rendering, not the previous
frame-cut shortcut: changing task typography requires new task visuals.
Commands: `revise_reduced.py prepare --source <reduced-r2> --build <fresh-build>`,
then `speech-review`, `check`, `render` and `verify`, each with `--build`.
Browser/encoded review sheets, source-preservation checks and final encoded
audio/duration/frame validation remain required.

All four revised native 1080x1920/24-fps deliveries are complete in
`oeif_b1_listening_reduced_r3\teil_N\production_portrait.mp4`. The clocks remain
3444/3240/3803/4128 frames (143.5/135/158.458333/172 seconds). All browser gates,
70 encoded event checks, 17 remaining silent intervals and 54 export/browser
frame comparisons pass. All 57 measured cards fit; minimum bottom clearance
is 101.4375 px. Overall encoded audio correlation is at least 0.996539, the
minimum individual audio-event correlation is 0.994936, and maximum mean RGB
error is 2.389960 (threshold 4).

Inspected the native clean opening, enlarged MC, dense paired reveal and
matching reveal, then encoded sheets covering all four clips and their CTA.
The reduced-practice notice, correct keys, book/Amazon panel and logo persist.
Post-opening mixed PCM is byte-identical to reduced r2. The 53-file
`delivery_manifest.json` binds outputs/receipts, title review and source pins;
earlier reduced/full deliveries and voice references remain unchanged.
Existing reduced YouTube/TikTok drafts still describe these same tasks/timing.
No upload, publication or human listening certification.

### Shorter voiced openings and November publication assets (November 9, 2026)

The user requested each short's first slide to last only its title speech plus
0.5 seconds. `trim_reduced_intro.py` derives fresh
`builds\oeif_b1_listening_reduced_r5` from frozen voiced/mobile r3, without new
TTS or tempo processing. Round up to the 24-fps frame grid:

| Clip | Title WAV | New opening | New video |
| --- | --- | --- | --- |
| Teil 1 | 2.981417 s | 84 frames / 3.5 s | 3384 frames / 141 s |
| Teil 2 | 2.781292 s | 79 frames / 3.291667 s | 3175 frames / 132.291667 s |
| Teil 3 | 2.783333 s | 79 frames / 3.291667 s | 3738 frames / 155.75 s |
| Teil 4 | 2.984792 s | 84 frames / 3.5 s | 4068 frames / 169.5 s |

Only 60/65/65/60 surplus opening frames are removed. Shift all subsequent
events, browser scenes, audio/root duration, animation clock and countdowns
equally; preserve every later event duration and all post-opening PCM.
The title-to-next-event silence is at least 0.5 seconds and less than one
additional frame beyond that. No task, reveal, promotion, reduced-practice
notice, font size or final CTA changes. Reuse r3 video frames only because the
static opening is the sole visual timing change; mix the original WAVs anew.
All 31 listening tests pass, including frame-rounding and browser-clock
regressions. All four final r5 MP4s are complete and pass full decode, strict
under-180-second stream/container clocks, all 70 encoded events and 17 silent
intervals. All 57 mobile scene measurements and 54 export/browser comparisons
pass; maximum mean RGB error is 2.425297. Overall audio correlation is at least
0.999969 and minimum individual audio-event correlation is 0.999963.

The eight exact exported last-opening/first-exercise boundary frames match the
corresponding r3 frames, with maximum mean RGB error 0.289153. The actual
post-title padding is 0.518583/0.510375/0.508333/0.515208 seconds. Inspected
the boundary stills and encoded paired/matching/CTA sheets. Keep per-clip
`intro_boundary_review.json`, the 50-file `delivery_manifest.json` and the
cross-delivery/publication `delivery_audit.json`. Post-opening PCM and previous
approved source hashes remain unchanged; no new human listening certification.

The earlier r4 export was rejected, not delivered: native AAC at 128 kbps
produced title-event correlations of 0.983756/0.984305 in Teile 1/4 despite
zero sample lag. Independent 192/256-kbps probes preserve both titles above
0.999992. R5 therefore uses 192-kbps AAC from the same lossless WAVs, without
weakening the >0.99 encoded gate. Keep the failed export log and original
generator snapshot in r4; previous approved r2/r3/full deliveries stay frozen.

`publication_assets.py` creates the full episode and all four selected parts
in `posts\oeif_b1_listening_2026_11_ep01_r2`, preserving earlier posting drafts.
Each folder contains German YouTube/TikTok/Instagram descriptions and native
1920x1080/1080x1920/1080x1350 thumbnail PNGs. The concise title includes
"ÖIF B1 Hören", "Prüfungssimulation", "November 2026" and "Episode 1", with
guided/full or numbered reduced-practice scope visibly qualified.

The smiling Lea avatar is a local circular crop from the established native
group pose (`candidate_a`, second from left), not a newly invented character.
Its crop/cast source hashes, logo/fonts, all captions and geometry checks are
bound in `publication_manifest.json` and `layout_checks.json`. Visually
inspected all 15 covers on the contact sheet and representative full-size
landscape/portrait covers. All text is in bounds and non-overlapping; every PNG
decodes at its intended dimensions and is below 2 MB. All 15 captions include
the correct listening-book link, original task scope, AI disclosure and
appropriate Mixkit credits; the longest is 1250 characters. Full YouTube
chapters come from measured original event starts. No upload or publication.

## Validation and optional AnyCap

Local deterministic checks are the primary acceptance gate:

- Exercise completeness, correct numbering/options/answers and exact source text.
- No transcript/answer leakage before the review phase.
- Correct instruction, reading, playback/repetition and answer-marking order.
- Exact frame/sample-clock timing, intentional silence and no speech overlap.
- Browser/layout/contrast checks and transition-boundary snapshots in both ratios.
- Encoded dimensions, frame rate/duration, full decode and audio synchronization.
- Measured word highlights for opening/review only, with number mappings checked.
- Human listening and phone-layout review before delivery approval.
- Source/export hashes and preserved independent ASR disagreements.

HyperFrames `check` offers browser/layout/motion/contrast checks, but sampled
checks are not proof that every frame or exam rule is correct. Add targeted
boundary checks from the episode timeline and inspect the encoded output.

AnyCap is an optional model-based second opinion for visible defects, event
ordering or timestamped observations, not a frame-accurate pass/fail authority.
Its documented `video-read` command uploads local input for cloud analysis:

```powershell
anycap actions video-read --file .\preview.mp4 `
  --instruction "Identify clipped text, premature answer reveals and incorrect scene ordering. Give timestamps."
```

Research-time documentation lists a 100 MB local-video limit and 10 credits
per successful video-read request. Verify current limits, price and installed
help before use. A full simulation may exceed the size limit.
AnyCap requires authentication; any upload/billed request is a separate,
explicitly chosen action. No media was uploaded during this research.
Spot-check its findings locally and retain human listening separately.

References:

- [Video analysis](https://anycap.ai/capabilities/video-analysis)
- [CLI reference](https://docs.anycap.ai/reference/cli/)
- [Installation](https://docs.anycap.ai/getting-started/install/)

## Implementation stages and acceptance

1. Confirm applicable exam version and audio-based timing/repetition rules;
   select a permitted first announcement exercise, book promotion and initial mode.
2. Set up an isolated, pinned HyperFrames project and validate its Windows runtime.
3. Build one exercise: spoken opening/instruction, task card, reading interval,
   listening, answer interval and separate review/CTA. Produce both layouts.
4. Review contact sheets and the complete small preview, including actual speech,
   transitions, solution gating and encoded checks.
5. Expand to all four sections with the verified rules and explicit long-form
   duration budget; provide an answer-key/review chapter after the simulation.
6. Consider AnyCap only if its optional cloud review adds value. Production
   approval and publication remain separate from prototype generation.

Implementation tasks are tracked in `..\plan\TODO.md`.
