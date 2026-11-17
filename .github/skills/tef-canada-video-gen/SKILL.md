---
name: tef-canada-video-gen
description: Generate and review TEF Canada practice videos, including book-based listening exercises and Quebec French voice casting.
---

# TEF Canada video generation

Follow the `pilot-3d-dev` skill for source preservation, asset licensing,
preview checks and publication approval. Use its episode/strict-under-90-second
requirements for the 3D short-video route, not for separately requested
long-form `listening_2d` videos.

## Listening instructions and timing

Read `references/listening_instructions.json` before planning or generating
listening video speech. It preserves all eight instruction screenshots supplied
by the user on November 16, 2026, their timing contracts and explicitly labelled
video adaptations. Keep this written source evidence separate from synthesized
audio and renderer receipts.

Use TTS to speak the complete instructions, including the timing sentence,
before each task family. Show matching instructions and measured word highlights;
normalize spoken numbers without inventing timestamps. Use the bank's
`tts_text`, recording its logged adaptations rather than claiming verbatim
official narration. The screenshot text is written source evidence, not a
recording of the official announcer.

Use the official published sample's task-specific timing, including the full
silent reading and response windows:

| Family | Silent reading | Silent response |
| --- | --- | --- |
| Picture dialogue | 5 seconds | 10 seconds |
| Public announcement | 10 seconds | 10 seconds |
| Voicemail | 10 seconds | 10 seconds |
| Street interview | 5 seconds | 15 seconds |
| Radio chronicle | 10 seconds | 15 seconds |
| Two-question interview | 20 seconds | 30 seconds for both |
| Two-question reportage | 10 seconds | 15 seconds for both |
| Varied audio document | 10 seconds | 15 seconds |

These are published sample timings, not certification of every live test screen.
The street-interview screenshot has no timing sentence: the bank records the
separate official-sample timing evidence instead of attributing it to the image.
This replaces the previous blanket five-second reading instruction. Only a
separately requested practice variant may override the task-specific windows.

For each family: complete instruction narration, then for each recording show
its unmarked question/options for the full reading silence, play the complete
recording once, retain the options for the full response silence, then advance.
Instruction speech must not consume silence. Keep both questions visible around
shared interview/reportage recordings; apply each pair's windows once, not once
per question. No spoken options, music, ticking or effect tails in the silences.
No chimes or added sound effects by default; do not inherit German reveal
cues. The explicit November 17 reveal-chime variant below is an exception.
By default, keep solutions until the entire selected attempt is
finished. The user-requested immediate-correction practice variant below
explicitly overrides only that answer ordering.

### Immediate-correction practice variant

On November 17, 2026 the user requested reveals directly after each exercise.
Use `episodes/tef_canada_listening_01_inline.json` with
`answer_reveal: after_exercise`; the original episode defaults to
`after_attempt` and its frozen exports remain unchanged. After each recording,
keep its complete response silence, then reveal and explain the correct answer
before the next exercise. Keep the existing task-specific 10/15/30-second
response windows; the user's ten-second example is not a request to shorten
the other families' pauses.

For interview/reportage pairs, finish the shared response pause before showing
either answer. Show both answers together while their explanations are spoken
in order; do not replay the recording or insert a second answer pause.
Update and re-synthesize the setup so it promises corrections after each
exercise, not at the end. Omit the final-corrections introduction/chapter.
Label this guided practice, not an unaltered exam simulation. Keep all eight
family instructions, source recordings, default no-chime policy and under-15-minute
limit. Reuse unchanged verified speech/alignment, and measure/align any changed
setup narration. Check decoded frames immediately before and at every reveal.

The user subsequently requested `assets/sfx/mixkit-software-interface-remove-2576.wav`
before the answer TTS. Use the separate
`episodes/tef_canada_listening_01_inline_chime.json` with `reveal_chime: true`.
Show the answer and play one complete cue only after the response pause ends;
start TTS after the complete cue, including its tail and frame padding. For
paired questions, use one cue before the two unchanged explanations and keep
both answers visible throughout. Keep the original cue speed, add no reverb,
and use half amplitude. This explicitly overrides the earlier no-chime request
only for this new edition, not the instruction bank or frozen deliveries.
Preserve the original sound/hash and Mixkit provenance; verify its license,
decoded cue/speech placement, silent windows and strict duration. No new TTS
is needed when narration is unchanged.

Preserve the screenshot source separately when adapting task wording. Do not
read the school-uniform example for unrelated book viewpoints, describe three
people when the selected count differs, or instruct viewers to click dropdowns
in a noninteractive video. Log all changes; do not silently change book choices
to fit the three stance bullets in the street-interview example.

Use a fresh preview for timing changes and verify encoded boundaries and actual
silence, not just timeline metadata.

## Reduced all-sections 2D video

The current user-requested edition must be **strictly shorter than 15 minutes
(900 seconds)** including every instruction, silence, recording, transition,
solution and CTA. Retain all eight task families but reduce question counts,
never shorten official sample pauses, accelerate or truncate speech, or replay
shared audio to fit a layout. Label it reduced practice covering all task types,
not a complete 40-question/40-minute official exam.

The current source-linked plan is `plan/tef_canada_listening_simulation.md`:
16 questions / 14 unique recordings, including one intact interview pair and
one intact reportage pair. Measure the complete final speech/timeline before
rendering and check video, audio and container durations afterwards. At 24 fps,
require `total_frames < 21600`; exactly 15 minutes fails. If the measured budget
overruns, drop a whole optional single-question item while retaining all
families, update numbering/instructions/solutions and regenerate a fresh review.

The implemented 2D route uses `listening_2d/episodes/tef_canada_listening_01.json`,
`prepare_tef.py`, `compose_tef.py`, `check_tef_layout.cjs` and `deliver_tef.py`.
Run preparation, French alignment and ASR before composing and checking both
native layouts. Inspect the native capture sheets before rendering, then check
the complete encoded video, countdown boundaries and actual silence before
freezing. A `--layout-only` mockup is not timing evidence or a deliverable.
Preparation uses cached local Qwen3-TTS 12Hz 1.7B Base; a fresh build can import
only matching content-addressed raw clips with `--speech-cache-from`.

The original book WAVs include `spoken_label_fr` question-number introductions.
Keep those complete recordings and show their source-book numbers above the
sequential video questions. Explain the two numberings in posting drafts.
Compare ASR against the source label as well as the exercise transcript, retain
raw disagreements and do not mistake numeric spelling or a source label for
an independently verified speech error. Human listening remains separate.

## Book artwork and promotion

Use the finished book illustrations from
`listening/images/picture_sets/google_ai_studio/`, not the simpler SVG variants
or their preview sheets. For the current selection these are `P19.jpg` and
`P21.jpg`. Inspect each sheet, retain its A/B/C/D ordering, and use lossless
quadrant crops for the attempt and corresponding correct-answer panel.
The sheet already contains answer letters: do not add a second label.
Preserve the complete sheets, crop coordinates and file hashes in the build.

The user supplied the actual cover at
`C:\Users\ronggong\OneDrive - Microsoft\devbox\cover\french\tef_ca\listening.jpg`
(accessible through `/mnt/c/Users/ronggong/` on this host), with purchase link
`https://a.co/d/013rkncS`. Copy the supplied cover into the new build and pin
its original bytes; do not substitute a title page when the actual cover is
available. Use the same cover and link in the video promotion, posting drafts
and derived thumbnails. Inspect both native aspect ratios for clipping.

`compose_tef.py` accepts a build-local `visual_assets.json` with pinned cover,
purchase URL and panel paths. A visual-only revision must preserve the previous
frozen build and reuse its exact speech, alignment, frame clock and full silent
windows; it does not need new TTS.

## Six portrait Reels from the complete practice edition

The user approved six standalone portrait parts on November 17, 2026, each
**strictly below 180 seconds**, including its own spoken opening, CTA and hold.
This explicit limit applies to these 2D derivatives, not the 3D short route.
Use `episodes/tef_canada_listening_01_social_six.json` and
`derive_tef_social.py`; preserve the frozen full-length source.

Keep complete, consecutive families: pictures plus announcements (questions
1–4), voicemail (5–6), street interviews (7–9), chronicle plus interview
(10–12), reportage (13–14), varied documents (15–16). Retain original video
numbers and source-book labels. Never split a shared pair, shorten silence,
trim instructions/recordings/explanations, change speed or overlap a chime
with speech. Do not retain the general sixteen-question spoken setup in
each short.

Synthesize each numbered title and the brief shared CTA with the approved
Québec narrator. Force-align the new words; retain independent ASR flags.
Use the existing native composition for wrappers and source-linked checking.
Reuse exact source video frame intervals and byte-identical lossless exercise
audio; never use keyframe-only stream-copy cuts or crop the portrait layout.
Show a persistent part/question badge and replace the old full-video scope
footer without obscuring questions, the cover or promotion.

Run `speech`, `prepare`, `check`, then inspect native captures before `export`.
Run `encoded` and inspect the six encoded openings, all edit boundaries,
countdowns/reveals and paired cards. `sheets --mode native|encoded` prepares
review sheets; `posts` creates six separate Instagram/TikTok drafts and
source-linked numbered covers. `freeze` requires all six encoded inspections
and rechecks the original full delivery. Preserve full raw ASR evidence;
automated speech/frame checks do not certify human listening or publication.

If HyperFrames 0.9.2 fails a fractional wrapper range with a `[chunkAudio]`
AAC packet-count error, preserve its logs and use
`render_tef_wrapper.py --build <part-build> --kind closing` (or `opening`).
This captures every exact native frame from the already checked composition
and encodes video only with explicit BT.709 conversion. Resume `export`,
then `encoded`; the complete authoritative WAV is muxed separately, so no
speech or silence is removed. Keep the helper snapshot and frame provenance.

### Instagram cover safety

Do not treat the whole central square as UI-safe or audit only selected title
text. Include every foreground element: all text, part badges, panels, logos,
the complete Canadian flag and the book cover. No informative bottom banner
may bypass the audit as noncritical decoration.

The corrected six-part covers are in
`posts/tef_canada_listening_01_instagram_safe_r3/`. Their conservative project
region is `(100, 480, 850, 1130)` on a 1080x1920 canvas, leaving extra bottom
and right clearance. This is a project design policy, not an official or
universal Instagram specification. Preserve requested title wording and
Canadian elements; keep descriptions and frozen videos unchanged.

Audit the complete foreground alpha mask, not just text bounding boxes.
Require pixel-preserving central square, 4:5 and 3:4 crops, a 10% zoomed-square
stress crop, and zero foreground overlap with conservative UI masks. Inspect
proof crops and UI overlays made from the actual encoded cover JPEGs. Keep
proofs separate from upload images and preserve earlier publishing revisions.
Record inaccessible primary references honestly; an overlay test is not an
in-app upload or platform certification.

## Voice casting and effects

For TEF Canada listening videos, use a `fr_ca_qc` voice for the opening question
and answer narration, and a different `fr_ca_qc` voice for the announcement.
Select available references from the book's voice registry, verify each
reference and its exact transcript, and record the role and provenance of each
voice. Do not imply that a generated announcement is a book recording.
Registry locale and automated checks do not certify accent, pronunciation or
commercial rights; obtain human audio review and verify rights before release.

Do not add chimes or other effects except the explicitly requested reveal
variant above. For other future editions only when requested, add sound effects appropriate to the
recording and its context, such as a PA cue and subtle room echo.
Keep speech intelligible and preserve its words; do not apply the effect to the
opening or answer narration. Record the effect's source and rights, verify its
timing and level, and include it in human audio review.
