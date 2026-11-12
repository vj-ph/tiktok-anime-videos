---
name: oeif-b1-listening-video-gen
description: Plan, generate and validate long ÖIF B1 listening practice videos and reduced-practice shorts; preserve speech and exercise pauses, revise mobile layouts and voiced openings, and prepare platform descriptions and Lea thumbnails.
---

# ÖIF B1 listening video generation

Use `listening_2d\PLAN.md` for the separate 2D template and exam-version
research. Preserve source books, recordings and approved deliveries.

## Current defaults and workflow selection

Use the latest requested presentation below; older revision recipes document
dependencies, not alternative current defaults. A documentation-only request
must not trigger synthesis/rendering. A captions/covers-only request must not
modify the videos.

The table and legacy recipes below describe **B1**. For A2, apply the separate
revision contract and sequence gate in the next section, not B1 timing defaults.

| Area | Current requirement |
| --- | --- |
| Full video | Four Teile, 20 tasks, examples and complete pauses; native landscape and portrait layouts. |
| Script review | Required independent Claude Sonnet 5.5 review of generated listening transcripts, questions and answer keys before script approval and TTS. |
| Shorts | One portrait selection per Teil, strictly under 180 seconds; reduce task count, never reading/answer time. |
| Short opening | Say only "ÖIF B1 Hören Teil N"; complete processed TTS plus 0.5 seconds, rounded up to 24 fps. |
| Shorts mobile text | MC 56/48 px, paired 42/40 px, matching 48/40 px for prompts/options; measure all scenes for overflow. |
| Persistent elements | Logo, book/Amazon cue, reduced-practice notice/subset footer on shorts, and original final voiced CTA. |
| Publishing assets | Separate full/Teil 1-4 descriptions and Lea covers for YouTube, TikTok and Instagram; no automatic upload. |

Choose the smallest applicable route:

| Request | Route |
| --- | --- |
| Reuse finished episode 1 | Full reference: `oeif_b1_listening_full_production_r1`; current shorts: `oeif_b1_listening_reduced_r5`, both under `listening_2d\builds`. Do not regenerate them. |
| Reproduce the shorter openings | Use `trim_reduced_intro.py` with verified **r3**, not already-trimmed r5, as its source; write a fresh build. |
| Recreate voiced/mobile prerequisites | `reduce_full.py`: full -> r2-style silent openings; `revise_reduced.py`: verified r2 -> r3-style voiced/mobile layouts. These are intermediate recipes. |
| Change exercise text/typography | Native composition and render; do not reuse footage containing the old text. |
| Captions/covers only | `publication_assets.py` with explicit full/short build paths and a fresh posts directory. |

The drivers are episode-1 implementations, not a generic episode CLI.
`revise_reduced.py` expects the six-second **silent** source opening;
`trim_reduced_intro.py` expects the six-second **voiced** source opening.
Do not feed their outputs back into the same transformation. For new content,
edition labels, cast or crop geometry, create a separately versioned generator
and fresh outputs rather than changing a helper pinned by an approved build.

## A2 sequence and opening revision (November 11, 2026)

Use `listening_2d\episodes\oeif_a2_listening_01_revision_r2.json` as the
revision specification. It references the unchanged reviewed episode, pins the
user-supplied `listening_2d\assets\model_oeif_a2.txt`, and separates reference
evidence from requested timing. The earlier process/checks-only request was
superseded by **"ok, regenerate the video and reduced video"**: replacement
full landscape/portrait and four reduced portrait videos are now authorized.
Use the separately versioned `*_a2_r2.py` drivers and fresh r2 build folders.
Existing
`oeif_a2_listening_full_production_r1` and reduced-r1 deliveries remain frozen.
They pass their original approved 30/8/12/3-second guided-practice contract,
not the newly requested sequence.

The supplied transcript supports the four-part/15-task structure, play counts,
30-second reading instructions and final "Ende des Testteils Hören." cue.
It contains recognition gaps, missing number/ending cues, and no timestamps or
reliable chime/silence markers. Preserve it verbatim. Exact pause lengths and
chime placement below come from the user's sequence, not a timing measurement
of this transcript. Do not copy its exercise recordings into the original episode.

For the next full-video revision:

1. The first slide's main body is only **ÖIF A2 Hören**. Remove
   "Wie viel verstehst du?" and "15 Aufgaben aus dem Alltag". Say only
   "ÖIF A2 Hören" (internal pronunciation text: `Ö I F A zwei Hören.`).
   Preserve the logo and book/Amazon promotion. The old composer hardcodes
   the extra phrases: changing episode metadata alone does not remove them.
   The old full-title WAV also cannot be reused for the shorter speech.
2. Start each Teil with its instruction, then **30 seconds of silence** for
   reading, then the listening-start chime, then the first spoken number cue.
   Do not put that chime before or inside the reading silence.
3. Teil 1: say the combined numbers 1-7; play the shared message; allow
   **five silent seconds**, play a separate chime, then replay the same WAV.
4. Teil 2: number 8, recording, **five silent seconds**, same recording again;
   complete its answer/reveal sequence, then number 9 and the same pattern.
   Do not add a replay chime here or replay the entire section as 8/9/8/9.
5. Teile 3 and 4: number 10/11/12 or 13/14/15 and the complete recording once.
   After every group's final playback, preserve **ten silent answer seconds**.
   The user explicitly retained the separate **three-second answer reveal**
   with remove sound after that pause, including the joint seven-key reveal.
   Do not count reveal/chime time as silent answer time.
6. Do not insert extra back chimes between tasks. After each of Teile 1-3,
   put its ending after the last reveal, then **five silent seconds** before
   the next instruction. The supplied text omits some endings; these cues
   follow the user's requested sequence, not invented transcript evidence.
7. After task 15's pause/reveal, use the test-ending cue
   **Ende des Testteils Hören.**, not merely "Ende von Teil vier".
   Preserve the final solutions/voiced book CTA after the test.

On the seven-question card, r1's 2-px label gap was a space-saving compromise
that the user found unclear. The revision must visibly separate `a)`, `b)`
and `c)` from their answers: use at least an 8-px portrait label gap, preserve
question/option minima of 42/40 px, and allow wrapping or adjust padding rather
than shrinking text. The 8-px test made questions 4/7 wrap and the progress
bar extend 21 px below the compact card. In r2, reduce only compact portrait
row-bottom spacing from 10 to 4 px to recover space, keeping the bar inside
the card and promotion separate. Measure every affected card again.

Do not edit generators or inputs pinned by r1. When replacement production is
requested, create versioned preparation/composition/delivery drivers and fresh
outputs, inheriting unchanged exercise review/audio hashes and measured word
alignments only where wording/references match. Review/approve substantive
script changes before TTS. Measure new speech; do not retain the old opening's
duration. Rebudget shorts from the verified replacement full version instead
of assuming old clocks or silently changing old posting descriptions.

The independent `listening_2d\audit_a2_sequence.py` gate checks frame-derived
pauses, event order, missing/extra chimes and breaks, repeat hashes, separate
reveals, the final cue, title speech metadata and **actual title HTML** in each
composed layout. Run it after composition and before rendering; stop on a
nonzero exit. The old validator's agreement with the old builder is not
evidence of matching this new sequence.

```powershell
& .\pilot_3d\.venv\Scripts\python.exe -X utf8 .\listening_2d\audit_a2_sequence.py `
  --build .\listening_2d\builds\oeif_a2_listening_full_new `
  --output .\listening_2d\builds\oeif_a2_listening_full_new\sequence_pre_render.json
if ($LASTEXITCODE -ne 0) { throw 'A2 sequence/opening gate failed.' }
```

Use a fresh report path, and place retrospective audits outside frozen builds.
The gate verifies encoded-export bindings when auditing a frozen full delivery,
but does not replace PCM, ASR, browser/geometry or post-render event/frame
validation. It is for the full test; shorts intentionally omit instructions
and need their own explicitly scoped checks.

### Authorized A2 replacement workflow

The r2 drivers derive revised episode metadata in memory, leaving the reviewed
base JSON and all r1 programs unchanged. Reuse 49 unchanged speech clips and
all 168 instruction-word intervals only after matching text, voice, WAV hash
and measured duration. Synthesize only the full title and final test-ending
cue; inspect their independent small/medium ASR receipts. Preserve inherited
pronunciation/recognition notes rather than claiming new human certification.

Use fresh build paths. Run each command separately and stop on failure:

```powershell
$py = '.\pilot_3d\.venv\Scripts\python.exe'
$full = '.\listening_2d\builds\oeif_a2_listening_full_new'
$short = '.\listening_2d\builds\oeif_a2_listening_reduced_new'
& $py -X utf8 .\listening_2d\prepare_a2_r2.py --build $full --plan-only
& $py -X utf8 .\listening_2d\prepare_a2_r2.py --build $full
& $py -X utf8 .\listening_2d\process_a2_r2.py align --build $full
& $py -X utf8 .\listening_2d\process_a2_r2.py review --build $full --model small --ids title end_test
& $py -X utf8 .\listening_2d\process_a2_r2.py review --build $full --model medium --ids title end_test
& $py -X utf8 .\listening_2d\compose_a2_r2.py --build $full
& $py -X utf8 .\listening_2d\audit_a2_sequence.py --build $full --output "$full\sequence_pre_render.json"
& $py -X utf8 .\listening_2d\deliver_a2_r2.py check --build $full
& $py -X utf8 .\listening_2d\review_a2_frames_r2.py --build $full
```

Inspect every native sheet and record `visual_approval.json`; resolve the new
speech alongside inherited notes in `audio_review_resolution.json`.
`check_a2_layout_r2.cjs` measures the actual portrait text-to-label gap as well
as font minima and 12-px card-bottom clearance. Then use
`deliver_a2_r2.py render`, `validate_a2_r2.py --encoded` and
`review_a2_frames_r2.py --encoded`, all with `--build $full`.
Inspect decoded sheets, set the separate encoded approval, and run
`deliver_a2_r2.py freeze --build $full`. Rendering alone is not delivery.

Only derive shorts from the verified frozen full:
`process_a2_r2.py shorts --source $full --build $short`. Each `teil_N` must
then complete the same compose/check/native-review/render/encoded-review/freeze
gates. Shorts retain the post-reading start chime, the Teil 1 replay chime,
all complete selected groups and the voiced CTA. They omit instructions,
section endings, section-break silences and the full-test summary, not the
exercise reading/replay/response pauses. Keep all tasks if the measured clocks
fit; verify video/audio/container are each strictly below 180 seconds.

Refresh directly dependent posting drafts with `publish_a2_assets_r2.py`,
explicit `--full`, `--short`, and a fresh `--output` under `posts`.
Its captions use 30/5/10-second pauses, five-second full-test section breaks
and actual start/remove credits. Do not bind revised videos to unchanged r1
captions. Keep the existing Lea cover design; verify all publication input,
asset and layout hashes and the measured chapter starts. Nothing is uploaded.

Verified A2 episode-1 references are now
`listening_2d\builds\oeif_a2_listening_full_production_r2` (both ratios,
11:12.375) and `oeif_a2_listening_reduced_r2\teil_N\production_portrait.mp4`
(2:21.250 / 2:46.125 / 2:21.792 / 2:43.417). Preserve these frozen builds and
their pinned r2 programs; reuse rather than regenerate them for a lookup.
The reduced-root cross-audit verifies 642 delivery files, 246 encoded events,
56 silences, 173 frame comparisons and eight exact short opening boundaries,
plus all 781 preserved r1 delivery files. Retain the inherited ASR notes and
documented one-frame countdown rounding; this is not human listening approval.
Current A2 posts are in `posts\oeif_a2_listening_2026_11_ep01_r2`:
49 pinned inputs, 33 assets, 15 checked descriptions and 15 decoded Lea covers.
These counts are recorded results, not substitutes for fresh revision checks.

## Instruction template

Use `listening_2d\instruction_templates.json` as the draft instruction/cue
template. It adapts the structure in `listening_2d\assets\model.txt` without
copying official task/example recordings. Preserve that source transcript;
its recognition errors, missing cues and lack of timestamps are documented
in the template. Obtain script approval before synthesizing its draft text.

Use the proposed independent-practice title, not an opening that presents
Deutsch Kompass material as the official DTÖ Modelltest. Any exam-name mention
identifies the preparation target, not authorship or endorsement. The draft
wording is not legal clearance for official branding or recordings.

## Section timing

For the first full listening episode, follow
`listening_2d\episodes\oeif_b1_listening_01.json`: use fresh adapted content,
not the book test verbatim. The user requested existing speaker-reference
voices, FFmpeg `atempo=0.8` for synthesized speech and discrete sound effects
without background music or ambience. Verify concrete voice references before
synthesis; measure processed speech. The user subsequently requested
`atempo=0.8` and subtle reverb for chimes as well. Preserve downloaded originals;
measure derived chimes including their full tails. Never shorten exercise
reading/answer pauses. Surplus opening padding is separate and follows the
current short-opening rule.

For the sample, use Software interface start before the initial example cue.
Place Software interface back after an exercise's complete response silence,
immediately before the next exercise number. In guided practice, insert the
answer reveal after that silence and before back. Do not put back immediately
after the recording or inside the silent interval. Ending the short sample
is a preview transition, not a claim that the complete Teil 1 has finished.

### Current guided-practice presentation (November 9, 2026)

The user requested a light, relaxed palette, word highlighting for Anleitung,
and a few seconds to reveal each correct answer after the full answer pause.
Episode 1 now selects guided practice with `answer_reveal_seconds: 3`.
Keep the base timing sequences below unchanged, adding a separate
three-second reveal scene after each complete answer pause, then back and
the next spoken cue. On November 9, the user additionally selected Software
interface remove to play at the exact start of each reveal, including the
example. Apply the existing `atempo=0.8` and subtle reverb treatment; measure
the complete tail and require it to fit inside the reveal without shortening
the answer pause or overlapping back. Reveal paired-task keys together;
do not replay audio or add answer narration. The revised sample gives its example a separate
three-second reveal, rather than revealing it during the answer pause.

Describe this version as guided practice in metadata/post descriptions, not
an uninterrupted exam simulation. The user subsequently requested removing
"Geführte Hörübung · von Deutsch Kompass" and "Lösungen nach jeder Aufgabe"
from every slide, including the title and persistent footer. Do not replace
them with another on-screen mode/byline message. Keep the logo, book promotion,
preview scope and final CTA. Use a distinct warm, readable accent for lower
phase labels (Titel, Anleitung, Beispiel, Lesen, Antwort notieren and so on),
separate from the main dark text and green countdown/highlight styling.

Hide answers throughout reading, listening and the full answer pause. Retain
an uninterrupted mode only when selected explicitly; in that mode, put scored
solutions after the full test.

Use cream/off-white cards, a pale sage background and dark readable text.
Anleitung word highlights must use the actual speech's forced-aligned intervals;
reject changed display text or missing timings. Do not add task-recording
transcripts or listening subtitles. Preserve earlier previews when revising;
reuse unchanged speech and local word timings, rescheduling later turn starts
when reveal scenes extend the timeline.

The following timing reference was supplied by the user on November 8, 2026.
Do not describe it as independently verified official audio timing. Preserve
the approximate qualifiers below; record the actual chosen durations in the
episode timeline. Do not substitute DTZ or TEF countdown defaults.

All pauses are silence measured from the end of the preceding spoken cue or
recording to the start of the next event. Spoken cues have their own measured
duration and are not included in the silence. "Beispiel" and task numbers are
spoken cues, separate from the example or task recording, not generic beeps.

### Teil 1: tasks 1-4

1. Spoken instruction.
2. Spoken "Beispiel" cue.
3. 10 seconds silence.
4. Example recording.
5. 10 seconds silence.
6. Spoken "Nummer 1" cue.
7. Approximately 12 seconds silence.
8. Task 1 recording.
9. 12 seconds silence.
10. Spoken "Nummer 2" cue; repeat the numbered-task sequence through task 4,
    retaining approximately 12 seconds before each recording and 12 seconds
    after it.
11. Spoken "Ende von Teil 1" cue.

### Teil 2: tasks 5-9

1. Spoken instruction.
2. Spoken "Nummer 5" cue.
3. 10 seconds silence.
4. Task 5 recording.
5. 12 seconds silence.
6. Spoken "Nummer 6" cue; repeat the numbered-task sequence through task 9,
    retaining 10 seconds before each recording and 12 seconds after it.

### Teil 3: task pairs 10/11, 12/13, 14/15 and 16/17

1. Spoken instruction.
2. Spoken "Beispiel" cue.
3. 10 seconds silence.
4. Example recording.
5. 10 seconds silence.
6. Spoken "Nummer 10 und 11" cue.
7. 10 seconds silence.
8. One conversation recording for tasks 10 and 11.
9. 12 seconds silence.
10. Spoken "Nummer 12 und 13" cue.
11. 12 seconds silence.
12. One conversation recording for tasks 12 and 13.
13. 12 seconds silence.
14. Repeat the subsequent-pair sequence for 14/15 and 16/17, retaining
    12 seconds before and after each conversation. Do not replace the first
    pair's 10-second pre-recording pause with 12 seconds.

### Teil 4: tasks 18-20

1. Spoken instruction.
2. 60 seconds silence for reading.
3. Spoken "Beispiel" cue.
4. 1 second silence.
5. Example recording.
6. Approximately 12 seconds silence.
7. Spoken "Nummer 18" cue.
8. 1 second silence.
9. Task 18 recording.
10. Approximately 12 seconds silence.
11. Repeat the numbered-task sequence for tasks 19 and 20, retaining 1 second
    before each recording and approximately 12 seconds after it.

## Authoring and validation

- Keep instructions, examples, task cues, recordings and pauses as separate
  timeline events. Do not replay a task recording merely because a sequence
  says "repeat"; that means advance to the next task or pair.
- Display the relevant questions/options during reading and listening.
  Do not reveal answers or listening transcripts during uninterrupted exam
  simulation. Put solutions and optional transcript replay after the test.
  In the current guided mode, reveal only in the dedicated post-pause scene;
  keep optional transcript replay separate.
- Do not invent example-answer narration, extra end cues or additional
  repetition rules. Check the selected reference audio for anything not
  specified above and preserve its provenance and applicable exam version.
  The supplied transcript supports end-of-section cues for Teile 2 and 3 and
  the end of the listening subtest; the instruction template rewords them.
- Validate every encoded cue/recording boundary and silence interval against
  the authored timeline. Use measured audio durations, not estimated speech
  timing; retain approximate timing decisions in the delivery report.
- Keep script review, human audio review, preview approval and publication
  approval separate. Do not generate or publish merely because this skill
  records a timing reference.

## Shared production setup

Work in `listening_2d`, separately from the frozen `pilot_3d` speaking videos.
Run the examples below from the repository root in one PowerShell session;
redefine variables when a tool starts a fresh shell. Use Windows paths.

```powershell
$py = '.\pilot_3d\.venv\Scripts\python.exe'
$hf = '.\listening_2d\hyperframes_local.py'
```

Check `$LASTEXITCODE` after each native command before advancing; PowerShell
does not automatically stop a multi-command block on a nonzero native exit.
Stop at a failed gate, diagnose it, and preserve the failed run's receipts.

Reuse the existing Python environment, local HyperFrames/GSAP installation,
FFmpeg/FFprobe and installed Chrome. Install/restore dependencies only after
a missing-dependency failure or a manifest change. Use `hyperframes_local.py`
for browser work: it selects system Chrome and disables telemetry, updates,
automatic skill installation and orphan cleanup. Pass `--no-browser-gpu`.
Keep synthesis/alignment/ASR local; do not upload recordings for optional review
without separate authorization.

Use fresh named build directories. Preserve approved previews, production
MP4s, source books/transcripts, raw reference voices and original SFX. Never
change pinned inputs to make an old build pass; resume only with identical
inputs, otherwise create a new build/version. The current drivers target
episode 1, not arbitrary episode files: `prepare_full.py` reads the fixed
episode/instruction paths, and `reduce_full.py` has fixed selections/counts.
New content requires coordinated, reviewed changes to those plans/validators;
do not silently reinterpret an existing frozen episode.

## Long-video workflow

### 1. Approve content and bind inputs

Adapt the book's task structure into fresh scenarios, questions, distractors
and recordings; do not reproduce the book test verbatim. Check all 20 question
numbers, answer keys, paired questions and matching options. Pin the applicable
exam-version evidence separately from the user's pause reference.

**Required independent script review:** before user script approval and TTS,
have another model, Claude Sonnet 5.5 (`claude-sonnet-5.5`), review the complete
generated listening transcripts together with instructions, examples, questions,
options and answer keys. This is a standing requirement for new listening
scripts, not an optional step requiring a fresh request each time. Use a
separate reviewer context; self-review by the author does not satisfy it.
If the requested reviewer is unavailable, report the blocker and obtain the
user's choice of replacement rather than silently skipping or substituting.

Check natural, coherent German and Austrian usage where relevant; B1-level
vocabulary, sentence complexity and listening demands; plausible distractors;
unambiguous questions; exactly one supported answer per item; and consistency
across paired questions, matching options, task numbering and transcripts.
Flag exercises that are too easy for B1, including answers obtainable without
listening, and suggest substantive improvements rather than merely longer text.

Evaluate the findings, fix valid issues and have the reviewer recheck materially
changed items before presenting the final script for approval. Retain the
reviewed script version/hash, actual reviewer model, findings and their
resolution in the build's review records. Repeat this gate for substantive new
or revised exercise content; unchanged cuts and layout-only revisions can
inherit the original review. Model review does not replace user approval,
post-synthesis ASR/audio checks or human listening certification.

Verify the book cover/link, concrete Austrian voice WAVs and their reference
transcripts. Episode 1 uses nine roles bound to five references, different
voices within dialogues and three different opinion voices. Compatible sample
audio may be reused only when text, reference binding and WAV hashes match.
Keep the approved sample build available: preparation and validation depend on
its receipts, recordings and both preview MP4s.

Choose a new full build. `--plan-only` writes the plan and input pins without
synthesizing; inspect it before the authorized audio run.

```powershell
$sample = '.\listening_2d\builds\oeif_b1_listening_sample_r4'
$full = '.\listening_2d\builds\oeif_b1_listening_full_new'
& $py -X utf8 .\listening_2d\prepare_full.py --build $full --reuse-sample $sample --plan-only
```

### 2. Generate, measure and align audio

Synthesize only missing speech with the bound local Qwen references. Apply
`atempo=0.8` once, normalize and measure each processed WAV; retain raw audio.
Reuse/derive start, back and remove chimes with the approved 0.8x/reverb filter,
keeping their full tails. Do not force `HF_HUB_OFFLINE=1`: the production Qwen
loader previously required a metadata lookup despite cached weights.

Schedule separate events on the 24-fps / 48-kHz mono PCM16 clock:
2,000 samples per frame, speech rounded up to whole frames with zero padding.
Keep prescribed pauses exact; reveals and chimes are outside them. Measure
total duration rather than imposing an estimated exam-length target.

```powershell
& $py -X utf8 .\listening_2d\prepare_full.py --build $full --reuse-sample $sample
& $py -X utf8 .\listening_2d\align_full.py --build $full
& $py -X utf8 .\listening_2d\review_full.py --build $full
```

`align_full.py` aligns the title and all four instructions, reusing verified
matching word intervals where possible. Reject changed displayed wording or
missing timings. Never display task transcripts. Preparation rewrites the
timeline, so rerunning it after alignment requires rerunning dependent stages.

Review ASR disagreements without treating strict matches as accent or human
listening certification. Recheck substantive disagreements with an independent,
unprompted cached model where available; retain original flags and unresolved
readings in review notes rather than deleting them.

### 3. Compose and pass pre-render gates

Compose native 1920x1080 and 1080x1920 layouts, not a crop of one layout. Include
the opening/setup, four instructions, examples, every task, end cues, complete
20-key review and final voiced CTA. Show MC, paired true/false-plus-MC and
six-option matching cards. Keep the logo and book/Amazon cue visible throughout,
including the title and CTA. Use the approved light palette, warm lower phase
labels and measured narration highlighting; do not reintroduce removed bylines.

Run each stage separately and stop on a nonzero exit or failed acceptance gate.

```powershell
& $py -X utf8 .\listening_2d\compose_full.py --build $full
& $py -X utf8 -m unittest discover -s .\listening_2d -p 'test_*.py'
& $py -X utf8 .\listening_2d\validate_full.py --build $full
Copy-Item "$full\validation.json" "$full\source_validation.json"
& $py -X utf8 $hf check "$full\landscape" --json --at-transitions --snapshots --no-browser-gpu --timeout 4m
& $py -X utf8 $hf check "$full\portrait" --json --at-transitions --snapshots --no-browser-gpu --timeout 4m
& $py -X utf8 .\listening_2d\review_full_frames.py --build $full
```

Require browser `ok=true`, `browserSkipped=false` and zero runtime/layout/
contrast/audio errors. Save report paths/hashes in the pre-render receipt.
Inspect native contact sheets, especially dense paired/matching cards,
instruction highlights, answer boundaries, summary and CTA. Verify constant
promotion regions numerically; image-view deduplication can hide repeated
regions. A disabled motion checker is not a motion pass. Keep nonblocking
static/craft recommendations documented; do not shorten pauses or add
distracting motion merely to silence stillness/repeated-card warnings.

### 4. Render, validate actual exports and freeze delivery

Only render after source, browser and visual gates pass. Use delivery quality,
24 fps and two CPU browser workers per layout.

```powershell
& $py -X utf8 $hf render "$full\landscape" --fps 24 --quality delivery --workers 2 --no-browser-gpu --output "$full\production_landscape.mp4"
& $py -X utf8 $hf render "$full\portrait" --fps 24 --quality delivery --workers 2 --no-browser-gpu --output "$full\production_portrait.mp4"
& $py -X utf8 .\listening_2d\validate_full.py --build $full --encoded
& $py -X utf8 .\listening_2d\review_full_frames.py --build $full --encoded
```

Verify full decode, native dimensions/frame rate, exact frame count, every
encoded cue/recording/reveal and silent interval. Require audio-event
correlation above 0.99; encoded silent interiors use the validator's documented
2,048-sample AAC boundary guard. Require sampled export/browser mean RGB error
below 4 and inspect decoded sheets, not only browser stills. Countdown digits
may differ for one frame at exact integer boundaries due to seek rounding;
this is not permission to shift an audio pause or reveal.

Preserve `source_validation.json` before the encoded run overwrites
`validation.json`. Collect output hashes, sizes, dimensions, measured durations,
source preservation and supporting receipt hashes into `delivery_manifest.json`,
then verify all referenced hashes. The full-stage scripts do not automatically
assemble that final manifest. Retain source/ASR notes, browser and encoded
contact sheets; clean up only temporary decoded WAVs.

Prepare separate posting drafts with measured chapters, book link, independent
guided-practice wording, AI disclosure and used-SFX credits. Delivery is not
upload/publication approval. Episode 1's frozen reference is
`listening_2d\builds\oeif_b1_listening_full_production_r1`: both MP4s are
31,810 frames / 22:05.417. These are measured results, not future duration targets.

## Under-three-minute reduced-practice workflow

### 1. Budget complete exercise groups, not shortened pauses

The approved short format reduces exercise count, not silence or speech speed.
Derive it from a completed, verified full portrait production. Measure each
candidate group including spoken numbers, back chimes, reading and answer
silences, three-second remove reveals, opening and final voiced CTA. Keep
conversation pairs together. Reduce the selection if the complete budget
does not fit; do not accelerate speech, trim recordings, nearly eliminate
response time or merge away the final CTA to force all exercises under the cap.

Episode 1's current r5 selection and measured clocks are:

| Clip | Original tasks | Selected/full questions | Opening | Duration |
| --- | --- | --- | --- | --- |
| Teil 1 | 1-2 | 2 of 4 | 3.5 s | 2:21 |
| Teil 2 | 5-6 | 2 of 5 | 3.291667 s | 2:12.291667 |
| Teil 3 | 10/11 and 12/13, two conversations | 4 of 8 | 3.291667 s | 2:35.75 |
| Teil 4 | 18-19 | 2 of 3 | 3.5 s | 2:49.5 |

Preserve Teil 4's initial 60-second reading pause and all six matching options,
as well as each selected task's own pauses. Omit instructions, examples,
full-test summary and whole-section ending claims. Keep original numbering;
this is a subset, not a complete exam section. Recalculate for other content;
these counts/durations are not a generic three-minute guarantee.

### 2. Build the baseline selection when needed

Every screen must explicitly say
"Verkürzte Übung · Ausgewählte Aufgaben", with original task numbers and
selected/full counts. This requested scope notice is distinct from the removed
guided-practice/byline text. Do not say that pauses were shortened.

This is the historical r2-style prerequisite, not the current finished opening.
`reduce_full.py` adds a six-second silent scope introduction and preserves the
original voiced CTA. It copies normalized source WAVs byte-for-byte, reschedules
them on the same frame/sample clock and never applies tempo processing again.
It cuts exact frame ranges from the approved portrait MP4 instead of rerendering
every exercise. Native browser snapshots supply the opening and constant
notice, book/Amazon and subset-footer overlays. The cue
"Amazon: Bio / Beschreibung" plus pointing-down emoji serves both platforms.

Source-footage reuse assumes unchanged scene geometry outside those overlay
boxes. If other layout elements change, render a matching native composition
instead of claiming that an overlay updated the underlying footage.

```powershell
$source = '.\listening_2d\builds\oeif_b1_listening_full_production_r1'
$short = '.\listening_2d\builds\oeif_b1_listening_reduced_new'
& $py -X utf8 .\listening_2d\reduce_full.py prepare --source $source --build $short
& $py -X utf8 .\listening_2d\reduce_full.py check --build $short
& $py -X utf8 .\listening_2d\reduce_full.py review --build $short
& $py -X utf8 .\listening_2d\reduce_full.py render --build $short
& $py -X utf8 .\listening_2d\reduce_full.py verify --build $short
```

`prepare` requires a fresh build and pins the original long exports/inputs;
`render` refuses to overwrite an existing MP4. Inspect the browser sheets and
pass checks before rendering. Keep `input_pin.json`, per-clip timelines,
composition/asset receipts, exact source ranges and overlay boxes in
`render_command.json`. Do not modify the long timeline or weaken its validator
to accommodate a reduced selection.

### 3. Verify and freeze each reduced build

Require **strictly below 180 seconds for video, audio and container**, not
only the planned clock. Verify full decode, exact 24-fps frame counts, selected
numbering/keys, unchanged source PCM and every silence, complete chime tails,
hidden answers until reveal, persistent scope/promotion and final CTA.
`verify` runs event-wise encoded audio checks, compares sampled export/browser
frames and writes the reduced build's `delivery_manifest.json`.

Inspect decoded sheets, including each final response frame and first reveal
frame. Verify manifest/source hashes again after rendering. Carry inherited
speech-review notes forward: unchanged audio does not acquire a new human
listening/accent certification. Preserve warnings and temporary-WAV cleanup
rules from the long workflow.

Outputs are `teil_1` through `teil_4`, each containing
`production_portrait.mp4`, its validation and browser/encoded review sheets.
For current publishing assets, complete the opening/typography revisions first
and use step 6. Describe reduced practice with selected tasks and unchanged
pauses; retain the book link, AI/independent
practice disclosures and credits for the SFX actually used (back/remove here).
Do not overwrite long-version drafts or publish automatically.

The historical baseline reference is
`listening_2d\builds\oeif_b1_listening_reduced_r2`; caption drafts are in
`posts\oeif_b1_listening_reduced_01\teil_1` through `teil_4`. Its four native
1080x1920/24-fps videos passed 70 encoded event checks, 21 silent intervals and
54 export/browser comparisons. Use those receipts as examples, not as evidence
that a future build has passed.

### 4. Build the voiced/mobile prerequisite when needed

The user subsequently requested a cleaner opening with TTS saying only
"ÖIF B1 Hören Teil 1" (or 2, 3, 4), using the existing narrator at 0.8x.
Use `revise_reduced.py` in a fresh build derived from the verified reduced r2.
Synthesize only these four titles, preserve their raw/prepared/slowed WAVs and
voice-reference hashes, and require each complete title to fit the existing
six-second intermediate opening. Then apply the shorter-opening step below
before delivering a new current-format short. Do not truncate or accelerate
speech to fit.

Remove the opening card's task-count paragraph and the sentence about retained
reading/answer pauses. Keep its title, "Verkürzte Übung", persistent scope
notice, footer, book/Amazon panel and logo. The voiced title contains no extra
instructions, disclaimer or promotional narration. Exercise audio, reading/
answer pauses, reveal cues and final CTA remain unchanged and at the same times.

For mobile, enlarge the actual question and option text, not the whole video:
MC prompts/options use 56/48 px, paired tasks 42/40 px, matching tasks 48/40 px.
Adjust option padding/gaps to fit, rather than clipping or reducing the content.
`check_reduced_mobile.cjs` uses the existing local Puppeteer/Chrome to measure
every scene, enforce question/option minima of 42/40 px, reject horizontal
overflow and preserve at least 12 px below the final card element.

```powershell
$approvedShort = '.\listening_2d\builds\oeif_b1_listening_reduced_r2'
$revised = '.\listening_2d\builds\oeif_b1_listening_reduced_voiced_new'
& $py -X utf8 .\listening_2d\revise_reduced.py prepare --source $approvedShort --build $revised
& $py -X utf8 .\listening_2d\revise_reduced.py speech-review --build $revised
& $py -X utf8 .\listening_2d\revise_reduced.py check --build $revised
& $py -X utf8 .\listening_2d\revise_reduced.py render --build $revised
& $py -X utf8 .\listening_2d\revise_reduced.py verify --build $revised
```

Inspect the independent title ASR results and native contact sheets before
rendering. This revision must use native HyperFrames rendering: larger text
changes the exercise cards outside the old constant-overlay regions, so reusing
the old smaller-text footage would not implement the request. Validate every
encoded event and exported review frame again. Require byte-identical mixed
PCM after the opening, unchanged frame counts/durations below 180 seconds,
complete title speech, preserved earlier source hashes and a new delivery
manifest. Do not alter the pinned original `reduce_full.py` to retrofit r2.

The completed voiced/mobile reference is
`listening_2d\builds\oeif_b1_listening_reduced_r3`, with the same four durations
as r2. It passes 57 scene measurements, 70 encoded events/17 silent intervals
and 54 export/browser comparisons; the 53-file manifest preserves source and
title-audio receipts. Minimum measured card-bottom clearance is 101.4375 px.
These results do not replace fresh validation for another revision.

### 5. Finish the current short-opening format

The latest opening-duration request supersedes the fixed six seconds for new
revisions: use the complete processed title WAV plus 0.5 seconds, rounded
**up** to the next 24-fps frame. Do not synthesize or tempo-process it again.
`trim_reduced_intro.py` derives a fresh build from verified voiced/mobile r3.
It preserves the entire title and removes only surplus opening silence/frames.
Every later event shifts earlier by the same frame delta; all task recordings,
reading/answer pauses, reveals, larger typography and the final CTA keep their
original content and duration.

On the existing 48-kHz mono PCM16 / 24-fps clock, calculate from exact samples,
not the rounded duration printed in a log:

```python
intro_frames = (title_samples + 24000 + 1999) // 2000
padding_samples = intro_frames * 2000 - title_samples
assert 24000 <= padding_samples < 26000
```

Thus the requested half-second is never shortened; the excess is less than
one frame. Do not count the following exercise's reading silence as padding.

```powershell
$voiced = '.\listening_2d\builds\oeif_b1_listening_reduced_r3'
$trimmed = '.\listening_2d\builds\oeif_b1_listening_reduced_trimmed_new'
& $py -X utf8 .\listening_2d\trim_reduced_intro.py prepare --source $voiced --build $trimmed
& $py -X utf8 .\listening_2d\trim_reduced_intro.py check --build $trimmed
& $py -X utf8 .\listening_2d\trim_reduced_intro.py render --build $trimmed
& $py -X utf8 .\listening_2d\trim_reduced_intro.py verify --build $trimmed
```

Because only a static opening's duration changes, this step may reuse the r3
video frames: retain frames before the new opening end, skip surplus opening
frames, then retain every original post-opening frame. The current cutter
re-encodes retained video frames; it is not a lossless video stream copy.
Encode audio from newly mixed lossless source WAVs, not decoded AAC.
Validate exact frame counts and
byte-identical PCM after the two differently sized openings. Retime every HTML
scene, root/audio duration, animation clock and countdown start together.
Repeat browser/mobile, encoded event, silence and export/browser checks.
Do not use this shortcut for changed exercise text or geometry.
Use 192-kbps AAC: the first 128-kbps export distorted two title waveforms below
the 0.99 correlation gate despite correct timing. Higher-quality probes and a
fresh revision fixed this; do not lower the validation threshold or reuse the
rejected r4 exports.

### 6. Prepare descriptions and native platform covers

For episode-1 publishing assets, explicitly bind the chosen full and **final**
short build, then generate into a fresh posts directory. `$trimmed` below must
already have passed `verify`; do not bind publishing assets to a rejected or
intermediate export.

```powershell
$full = '.\listening_2d\builds\oeif_b1_listening_full_production_r1'
$trimmed = '.\listening_2d\builds\oeif_b1_listening_reduced_r5'
$assets = '.\posts\oeif_b1_listening_2026_11_ep01_new'
& $py -X utf8 .\listening_2d\publication_assets.py --full $full --short $trimmed --output $assets
```

This creates `full` and `teil_1` through `teil_4`, each with separate
`youtube.txt`, `tiktok.txt` and `instagram.txt`:

| Cover filename | Native size | Ratio |
| --- | --- | --- |
| `thumbnail_youtube.png` | 1920x1080 | 16:9 |
| `thumbnail_tiktok.png` | 1080x1920 | 9:16 |
| `thumbnail_instagram.png` | 1080x1350 | 4:5 |

There are 15 descriptions and 15 covers for this five-video scope.
Also retain `avatar_lea.png` and `thumbnail_contact_sheet.jpg`. Use the existing
smiling Lea (candidate_a) render as a locally cropped avatar; preserve its
source/cast hashes. Include "ÖIF B1 Hören", "Prüfungssimulation", "November 2026"
and "Episode 1" legibly, but qualify the full version as guided practice and
each short as "Teil N · Verkürzte Übung". Never imply a new official exam paper.
The current generator hardcodes November 2026 / Episode 1 and Lea's source/crop;
do not assume it accepts date, episode or avatar CLI flags. Another edition
requires a versioned generator, reviewed labels and fresh assets.

Use current measured chapter starts, the listening book's own link, unchanged
pause/subset wording, AI voice disclosure and actual SFX credits. Read the
Amazon link from the listening episode's promotion data, not a speaking book.
Keep task numbers, selected/full counts and the initial Teil 4 reading time
accurate. Use back/remove credits for shorts and start/back/remove for the full
episode. "Prüfungssimulation" is a requested cover keyword; descriptions must
still explain guided practice and short covers must identify the subset.
Inspect the contact sheet; require non-overlapping in-bounds text and verified
image sizes.
Keep `layout_checks.json` and `publication_manifest.json`. Generation is not
upload approval; preserve earlier captions, covers and long-video exports.

## Final acceptance and persistence audit

The stage commands do not implement every delivery check automatically.
In particular, `trim_reduced_intro.py verify` writes its delivery manifest,
but does **not** create `intro_boundary_review.json` or `delivery_audit.json`.
Perform these supplemental checks explicitly rather than claiming that a
successful `verify` completed them:

1. **Exact opening cut:** let N be the new opening frame count and O the old
   one. Extract zero-based output frames N-1/N and source frames N-1/O with
   FFmpeg frame selection. Require each paired mean RGB error below 4 and
   inspect that the opening actually changes to the first exercise at N.
   Save frame indices, images/hashes and comparisons in each clip's
   `intro_boundary_review.json`; an opening snapshot at one second is not
   boundary validation.
2. **Audio preservation:** compare complete title samples and lossless mixed
   PCM after the two differently sized openings. For this clock, compare
   `current[N * 4000:]` with `previous[O * 4000:]` in PCM bytes, not WAV headers.
   Retain complete chime tails, all reading/answer silences and inherited
   speech-review notes. Require every encoded audio correlation above 0.99;
   never lower that gate to excuse an encoder artifact.
3. **Publication binding:** rehash every `publication_manifest.json` input
   and asset, decode every PNG at its declared size, inspect the contact
   sheet and check text bounds/overlap. The generator enforces title/description
   budgets but does not check the completed videos or approve publication.
   Verify that its `short_build` points to the final successful revision.
4. **Freeze delivery:** rehash every `delivery_manifest.json["files"]` entry,
   validate the recursive source/code/reference pins and boundary image
   hashes, then write `delivery_audit.json` binding both manifests and boundary
   receipts. Clean up only temporary decoded WAVs/AAC probes. Preserve failed
   run logs, approved originals and the successful export/review receipts.

Inspect decoded exercise/reveal/CTA sheets, not just browser images. Preserve
nonblocking warnings and state when motion checks or human listening were not
performed. Recorded scene/event/hash counts are results for a particular build,
not acceptance shortcuts for new content. Report final video and posts paths
clearly; distinguish generated assets, validated delivery and actual upload.

## Latest verified episode-1 references

Completed reference: `listening_2d\builds\oeif_b1_listening_reduced_r5`, with
84/79/79/84-frame openings and 141/132.291667/155.75/169.5-second exports.
Its 70 encoded events, 17 silent intervals, 54 export/browser comparisons and
eight exact opening-boundary frames pass. Final posting assets are in
`posts\oeif_b1_listening_2026_11_ep01_r2`; inspect its contact sheet and manifest.
These are validated local deliverables, not uploaded posts.
