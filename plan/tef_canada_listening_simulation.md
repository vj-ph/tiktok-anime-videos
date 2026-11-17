# TEF Canada: reduced all-sections 2D listening simulation

Planning/research date: November 16, 2026.
Status: revised to the user's eight instruction screenshots, official sample
silences, no chime and a strict under-15-minute complete-video limit.
Instruction text is recorded; TTS, runtime setup and rendering are not yet done.
Use `listening_2d`, not the Blender/short-video pipeline.

## Deliverable

Proposed title: **TEF Canada - Compréhension orale : 16 questions, 8 types
d’exercices**. Label the video **Entraînement réduit**, not a complete official
40-question examination. Cover all eight task families with fewer questions,
then a separately signposted correction chapter and brief book CTA.
The **entire video must be strictly shorter than 900 seconds**, including
opening, all eight spoken instructions, every full reading/response silence,
all complete recordings, transitions, corrections and CTA. Aim below 14 minutes
to retain about a minute of headroom; do not fill unused time with extra holds.
Prefer a native 1920x1080 master; plan a separate 1080x1920 layout on the same
audio clock, not a crop of four-choice question cards.

This is independent book-based preparation, not official TEF content or a
validated reproduction of its interface/difficulty. The supplied book focuses
on B2/NCLC 7-8 preparation; its selected questions do not establish the
official test's difficulty distribution or score calibration.

## Verified official process

Sources retrieved November 16, 2026:

1. Current TEF Canada passation page:
   https://www.lefrancaisdesaffaires.fr/candidat/test-evaluation-francais/tef-canada/passation/
2. Official sample booklet currently linked from the preparation resources:
   https://www.lefrancaisdesaffaires.fr/wp-content/uploads/2024/10/tef-exemples-epreuves-co.pdf
3. Current preparation page:
   https://www.lefrancaisdesaffaires.fr/candidat/test-evaluation-francais/tef-canada/preparation/
4. Linked interactive tutorial:
   https://www.lefrancaisdesaffaires.fr/documents/Tutoriel-TEF-CO/story.html
5. Linked sample recordings:
   https://www.lefrancaisdesaffaires.fr/wp-content/uploads/2024/10/tef-bandes-sons-co.zip

The current Canada page confirms:

- 40 questions, 40 minutes; 46 screens including instructions/transitions.
- Four answer choices and one correct answer per question.
- Automatic audio start, one playback, reading time before and response time
  after each recording; answer in order without going back.
- Correct answer: one raw point; incorrect/unanswered: zero.
- No paper notes/reference material during listening.

The booklet groups Q1-4 as illustrated conversations, Q5-20 as announcements,
voicemail and viewpoints, Q21-30 as radio chronicles/interviews/reportage,
and Q31-40 as varied documents. Its examples are not a complete test or a
representation of actual test difficulty. Do not equate its example numbering
with the numbering of a complete mock.

### Reading and response windows

The official sample booklet, PDF pages 3-8, gives these explicit windows:

| Task | Before audio | After audio |
| --- | --- | --- |
| Picture conversation | 5 seconds | 10 seconds |
| Public announcement | 10 seconds | 10 seconds |
| Voicemail | 10 seconds | 10 seconds |
| Street-interview viewpoint | 5 seconds | 15 seconds |
| Radio chronicle | 10 seconds | 15 seconds |
| Interview with two questions | 20 seconds | 30 seconds for the pair |
| Reportage with two questions in the sample | 10 seconds | 15 seconds for the pair |
| Varied document | 10 seconds | 15 seconds |

These are verified published sample timings, not independently measured
timings for every screen in the current live test. The passation page itself
says only a few seconds before and response time afterwards.

The user explicitly selected these task-specific windows, including complete
silence, instead of the former blanket five-second TEF practice setting.
Reduce the number of items, not these windows.

### User-supplied instructions and TTS

The eight screenshots supplied November 16 are transcribed in
`.github/skills/tef-canada-video-gen/references/listening_instructions.json`.
The updated skill requires this bank before listening-video preparation.
Each record has its source filename/attachment SHA256, exact written source
text, French `tts_text`, numeric pause settings and explicit adaptation notes.
The source image hashes are the attachment identifiers supplied in the message,
not a claim that inaccessible Windows temporary files were copied here.

Generate and use all eight complete TTS instructions, including each timing
sentence, once before the relevant family. Display the corresponding video
wording with measured highlighting; the written numbers may map to aligned
spoken number words. Complete the instruction audio before starting the first
reading silence. This is newly synthesized narration of written instructions,
not a copy or certification of the official announcer's spoken track.

Necessary logged video adaptations:

- The announcement screenshot says "conversation" in its timing sentence;
  the video says "annonce". Preserve the original in `source_text`.
- The street-interview screenshot concerns three people and school uniforms,
  with three stance bullets. The selected book items concern three different
  topics and each has four choices. Keep those items and their original keys;
  introduce three people giving opinions on different subjects instead.
  The image has no pause sentence: add the separately verified sample's
  five-/fifteen-second timing sentence, explicitly logged as supplemental.
- The video contains one interview and one reportage with static choices.
  Use the singular for the interview and replace dropdown interaction wording
  with selecting from the displayed choices for each question. Keep both
  questions' full options available.

The currently linked tutorial shell is labelled
`Tutoriel - Compréhension orale_26-08-25`; its HTML publish timestamp is
August 26, 2025. It is not a November 2026 release merely because retrieved
in November 2026. Its text extractor returned an offline/reconnect shell;
HTML and public data assets could be retrieved, but actual interactive
playback and spoken directions remain unverified.

**No chime, reveal cue, countdown ticking, PA sound or added ambience for this
edition.** Silence means silence, not a low-level sound bed. Official chime
investigation is no longer a blocker or an active task for this edition.
A later explicit effects request would require a separately reviewed revision.

## Selected book and companion resources

Read-only manuscript:
`/home/ronggong/lang/french/french_exam_books/tef_canada/listening_v2/book.md`.
Its Chapter 4 starts at line 4279; use a subset of **Examen blanc 1**, starting
at line 4289. Candidate pages precede all review material.

`listening_v2/edition.json` explicitly identifies `../listening` as its
resource directory. Companion paths below are relative to that original
`tef_canada/listening` directory, not to the video repository:

- `content_ledger/full_mocks_01_02.jsonl`: structured questions, keys,
  explanations, source scripts and picture-set mappings.
- `audio/manifest.jsonl`: recording/segment and casting metadata.
- `audio/qwen/wav/`: all 36 full-mock WAVs, including the 14 selected, are
  present and readable.
- `images/picture_sets/`: four-option SVGs and preview PNGs exist; resolve
  each question's `visual_set_id` from the ledger before selecting artwork.
- `audio/voices/voices.json` and `audio/voices/references/`: available
  French/Québec reference roster and four Québec WAVs.

Local read-only audit found 36 unique mock-one recordings covering exactly
40 questions. All 36 manifest source transcripts match the second-edition
review after removing speaker labels, punctuation, spacing and case.
This is text correspondence and WAV readability, not an auditory comparison
between the rendered WAVs and the book.

### Selected 16-question version

Renumber video questions 1-16; preserve the original source IDs in the manifest
and review materials. The two selected picture sets are P19 and P21.

| Video questions | Mock 1 source questions | Task | Recordings | Reading / response per recording |
| --- | --- | --- | --- | --- |
| 1-2 | 1, 3 | Picture dialogues | 2 | 5 / 10 seconds |
| 3-4 | 5, 6 | Public announcements | 2 | 10 / 10 seconds |
| 5-6 | 10, 12 | Voicemail | 2 | 10 / 10 seconds |
| 7-9 | 15, 17, 20 | Street interviews | 3 | 5 / 15 seconds |
| 10 | 21 | Radio chronicle | 1 | 10 / 15 seconds |
| 11-12 | 23, 24 | Interview, intact pair | 1 | 20 / 30 seconds for the pair |
| 13-14 | 29, 30 | Reportage, intact pair | 1 | 10 / 15 seconds for the pair |
| 15-16 | 33, 40 | Varied documents | 2 | 10 / 15 seconds |

The selected subjects include library services, the traversier, delivery,
remote interviews, reusable containers, a shared garden, early registration,
repair workshops, bicycle lending, repair-café support, an apartment building
and parcel lockers. Keep Canadian vocabulary without changing answer evidence.

This reduced allocation is an editorial selection, not an official allocation.
The original 40-question bank remains unchanged and is not being expanded.

Pin the exact manuscript, selected ledger/manifest records, pictures, raw audio
and references before implementation. Preserve original French questions,
distractors and answer-critical wording; adaptations need an explicit diff.
Review all eight selected picture options, including wrong-answer panels,
for visual consistency and accidental answer hints.

## Measured recording and silence budget

The full mock audit measured 446.7565 seconds across 36 recordings.
The selected 14 WAVs measure **186.3929167 seconds (3:06.393)** in total.
The existing ledger's estimated time slots are not measured audio timing.

The reduced selection retains **320 seconds of silence**:
125 seconds reading plus 195 seconds responding. Combined with complete
source recordings, this is **506.3929167 seconds (8:26.393)**.
Neither full source recording has been split/replayed for its question pair.

Planning allowances, not measured TTS durations:

| Component | Budget in seconds |
| --- | --- |
| Complete selected recordings, measured | 186.393 |
| Full prescribed reading/response silences | 320 |
| Eight complete instruction narrations | 180 |
| Spoken opening and independent-practice setup | 25 |
| Additional transitions outside instructions/silences | 10 |
| Final keys with concise spoken French explanations | 100 |
| Final spoken CTA and all outro hold time | 15 |
| Planned whole-video total | **836.393 (13:56.393)** |

This leaves about 63.6 seconds below the hard limit, before measured TTS and
per-event frame rounding replace estimates. Do not equate the budget with a
verified delivery. Use natural 1.0x speech; no script expansion, padding,
speech acceleration, chopped recording or shortened silence is planned.

Pre-render gate: sum the measured instruction/opening/solution/CTA WAVs,
recording samples and exact pause frames, rounding each speech event up on the
24-fps clock. Require `total_frames < 21600`. Check encoded video, audio and
container durations are all below 900 seconds too. Aim at most 840 seconds.

If needed, first shorten only newly authored setup/transitions/explanations.
If this is still insufficient, omit the second varied document (source Q40),
giving 15 questions with every family preserved and saving 37.514 seconds
before its explanation. A further optional cut is source picture Q3, saving
24.449 seconds before its explanation. Keep all three viewpoints, the two
complete paired tasks and each family's full instruction. Update numbering,
source selection, opening count, solutions and preview evidence after any cut.

## Video storyboard

1. Spoken/displayed title with measured French word highlighting. Brief
   independent-practice setup, headphone/channel check and explanation of
   one playback/no rewind. Do not suggest paper notes are allowed in the exam;
   any offline answer sheet is explicitly a video-only workaround.
2. A clearly bounded reduced-attempt start event. Never show a misleading
   40-minute exam timer. Show the selected item count and phase countdowns.
3. Follow the four broad question bands in order. Within each family:
   complete spoken instruction once per family, separate reading window with unmarked choices,
   one full recording, separate silent response window, then automatic advance.
   Do not narrate every option during reading time by default.
4. Show both questions/options before each shared interview or reportage.
   Keep both available through its single recording and response period.
   Landscape can use two columns; portrait needs a specifically reviewed
   eight-option layout, not tiny type, cropping or a replay to expose question 2.
5. No transcript captions, answer coloring, explanatory images, confirmations
   or answer-reveal sounds during the scored attempt. Highlight only setup
   and instructions, not answer-critical listening words.
6. After video Q16's complete response window, explicitly end the attempt. Only
   then show numbered solutions and concise French evidence/explanations.
   The book's English rationales require newly authored French narration,
   not an unexplained language switch. A raw /16 self-check is practice-only;
   do not convert it to an official TEF/NCLC result.
7. Final spoken book CTA. Prepare YouTube/TikTok/Instagram drafts, measured
   chapters, AI/advertising/independent-practice disclosures and asset credits.

## Canadian treatment

Use restrained maple-red/white accents, a small Canadian flag and French
Compass branding, with the correct listening-book cover. Keep illustration
space and all four answers dominant; book promotion stays in a separate
non-overlapping region. Do not reuse the German/Swiss covers or invent an
Amazon link absent a confirmed product mapping.

Retain the book's existing Canadian vocabulary and situations, such as the
traversier, autobus and garderie. Canadian branding is not a reason to alter
an answer-critical place, price, number or policy.

Propose `fr_ca_qc_narrator_f01` for opening, instructions and corrections,
and `fr_ca_qc_service_m01` as a distinct announcement voice. The registry marks
both available and their WAVs exist; verify exact reference transcripts,
provenance and listening quality before use. Preserve the existing mixed
fr-FR/fr-CA document casting when reusing clean book audio. A wholly Québec
cast would be a separately logged adaptation, not exact audio reuse or proof
that the official exam uses exclusively Canadian accents.

Reuse clean masters with no added effects/chime/music. Inspect source WAVs for
embedded labels, cues and unusually long edge silence before reuse; a manifest
word match does not establish their audible contents. Do not double-narrate old
book labels or silently cut speech; record any approved derivative edit.

## Linux readiness and implementation plan

Read-only inventory on this host:
Python 3.12.3, Node 25.9.0, npm 11.12.1, FFmpeg/ffprobe 6.1.1 are on PATH.
No `.venv`, `pilot_3d/.venv` or `listening_2d/node_modules` is present.
No supported Chrome/Chromium executable was found on PATH; other locations
have not been exhaustively checked. No packages/models were installed.

The project pins HyperFrames 0.9.2 and GSAP 3.15.0 in
`listening_2d/package.json`/lockfile. Existing Linux availability of Node and
FFmpeg alone does not establish rendering readiness.

Portability work identified:

- `hyperframes_local.py` unconditionally launches `hyperframes.cmd`; resolve
  the platform-specific local executable and explicit browser path.
- `check_fide_layout.cjs` hardcodes the Windows Chrome executable; use a
  common validated browser selection approach for the new TEF checker.
- `compose_full.py`, `compose_fide.py` and `review_full_frames.py` contain
  Windows Arial paths; use resolved, licensed fonts with French glyphs and
  record font metrics before checking layouts.
- `deliver_fide.py` includes a backslash-bearing composition path in its code
  pins. Audit selected helpers, episode inputs and source-manifest paths for
  POSIX/Windows portability without rewriting frozen delivery receipts.
- Existing fide/ÖIF drivers contain German/Swiss text, timing, ASR language,
  locale and approval contracts. Reuse mechanisms, not their exam constants.
  French alignment/ASR must explicitly select `fr`.

Implementation stages:

1. Use the screenshot-linked instruction bank and selected 16-question list.
   Pin selected source records and export the complete readable candidate/review
   script, exact instruction adaptations and measured timing budget.
2. Create an isolated Linux Python environment from existing applicable
   manifests; use `npm ci` in `listening_2d`, not a latest-version upgrade.
   Validate package engine requirements from the lock/runtime before selecting
   a supported Node version. Resolve browser/font prerequisites and local
   French TTS/alignment/ASR model caches; restore only missing assets.
3. Add narrowly scoped cross-platform helpers and regression coverage while
   preserving Windows behavior, existing source guards and old deliveries.
   No Blender, Rhubarb or 3D assets are needed for this 2D job.
4. Add a separate proposed `episodes/tef_canada_listening_01.json` and
   TEF-specific prepare/process/compose/check/deliver entry points as needed.
   Do not retrofit TEF into the frozen fide/ÖIF episode schema.
5. Review a small native Linux fixture first: spoken title, picture item,
   announcement and hardest paired-question card in both layouts, including
   instruction/reading/audio/response boundaries with no chime. Load the HyperFrames authoring skill
   before implementation; it is not installed among this session's listed
   skills. Do not install/update it merely to write this planning document.
6. Only after script/layout/audio preview review, generate the full measured
   build under a fresh ignored `listening_2d/builds/tef_canada_listening_01_r1`.
   Keep production and publication approvals separate.

## Acceptance checks

- Exactly 16 sequential video question IDs mapped to the selected source IDs,
  four options and one key each; 14 unique listening documents. Recalculate
  counts if the documented whole-item fallback is used.
- One shared interview pair plus one reportage pair; complete playback
  once per unique recording, with no mid-recording page-change loss.
- Book text/provenance and any expansion diff pinned; correct picture/option
  mappings; no exposed key/transcript in candidate screens or accessibility
  text before the solutions chapter.
- All eight complete TTS instructions present, source/adaptation provenance
  retained, no mismatched school-uniform/dropdown narration.
- Separate frame-exact instruction/reading/listening/response events; no
  speech consuming protected silence, no added chime/effect/music and no
  shortened official sample windows. Every silence has zero pre-encode PCM;
  check AAC windows with a documented codec-boundary guard.
- Real French speech/number/pronunciation and reference checks, independent
  ASR flags retained, measured opening/instruction highlights and human audio
  review. Automated ASR/locale tags do not establish accent quality.
- Pinned HyperFrames browser checks, all native card geometry in both ratios,
  French glyph/long-option/paired-question fit, forward/reverse seeking and
  actual countdown/word-boundary frames.
- Complete MP4 decode, exact encoded frame clocks/dimensions, speech versus
  lossless-mix checks, silent-window checks and decoded contact-sheet review.
  Verify solution onset after the last selected response, promotion/CTA
  containment and strict whole-video duration below 900 seconds in both layouts.
- Freeze manifests/source snapshots and verify unchanged older deliveries.
  No uploads or claims of official scoring/certification.

## Generated review delivery — November 16, 2026

The approved reduced selection is generated in
`listening_2d/builds/tef_canada_listening_01_r4/`:
`preview_landscape.mp4` (1920x1080) and `preview_portrait.mp4` (1080x1920).
Both contain 17,558 frames at 24 fps: **12:11.583**, including all instructions,
320 seconds of reading/response silence, corrections, book CTA and outro.
Earlier r1-r3 attempts and original book resources are preserved.

New narration uses local Qwen3-TTS 12Hz 1.7B Base and the approved Québec
narrator. All 14 book recordings are reused completely, including their
original spoken question labels. The video displays those book numbers above
the sequential 1-16 video questions; all posting drafts explain the distinction.
The library correction concerns collecting a reserved book, and the final
correction explains that the app's code opens the locker. Source choices are
preserved. The actual v2 title page is used rather than an invented cover.

Verification includes 28 focused regressions, real French word alignment,
independent ASR, full native HyperFrames checks, 71 geometry events and 706
forward/reverse word seeks per layout. Both MP4s fully decode. Per layout,
136 native/encoded frame comparisons, nine opening-word boundary checks and
29 silent intervals pass; decoded silence peaks are zero and audio correlation
is 0.999986. All 43 native cards, representative decoded scenes and all 84
encoded countdown boundary frames per format were visually inspected.

`delivery_manifest.json` freezes 1,218 verified files. `delivery_notes.txt`,
`visual_review.json`, `encoded_checks_*.json` and `speech_assessment.json`
distinguish actual checks from pending human listening. Raw ASR disagreements
are retained; numeric spelling/source-label equivalence matches 27/42 clips,
not a human accent or pronunciation certificate. No publication has occurred.
French post drafts, measured chapters and native-title covers are in
`posts/tef_canada_listening_01/`.

## Book-artwork and cover revision — November 16, 2026

Latest review exports are in
`listening_2d/builds/tef_canada_listening_01_r5/`:
`preview_landscape.mp4` and `preview_portrait.mp4`.
The original r4 delivery remains unchanged; all 1,218 frozen files were rehashed.

The user clarified that the finished book artwork is in
`listening/images/picture_sets/google_ai_studio/`. This revision replaces the
simpler SVG variants with the existing `P19.jpg` and `P21.jpg` illustrations.
All eight panels are pixel-exact quadrant crops, preserving A/B/C/D order and
embedded labels, including correct panels B and A in the solutions.
Complete sheets, crops, coordinates and hashes are retained in
`source_artwork/` and `visual_assets.json`.

The supplied Windows cover was accessible through `/mnt/c/` and is now copied
into the build, replacing the title-page fallback. Both promotion layouts show
the user-supplied link `https://a.co/d/013rkncS`; the three post drafts and
native-opening thumbnails are updated accordingly. No new image or speech
generation was needed.

Content, timeline, lossless audio, audio manifest and word alignment match r4
byte for byte. Both final AAC soundtracks also match r4 byte for byte.
Both native-resolution exports remain 17,558 frames at 24 fps / **12:11.583**.
The full silent reading/response windows, single playbacks and corrections
after the attempt are unchanged.

All 30 focused regressions pass. Each format passes native HyperFrames checks,
71 scene geometry/promotion checks, 706 forward/reverse highlight seeks,
136 native/encoded frame comparisons, nine opening-word boundary checks and
29 decoded silent intervals with zero peak. Maximum frame MAE is below 2.32.
All 43 native cards, nine representative decoded cards, full-size revised
artwork and all 84 encoded countdown-boundary frames per format were inspected.
The r5 manifest freezes 1,147 verified files. Speech review status and pending
human listening/publication approval are unchanged; nothing has been uploaded.

## Immediate-correction practice edition — November 17, 2026

The user's requested exercise-by-exercise correction edition is delivered in
`listening_2d/builds/tef_canada_listening_01_inline_r1/`:
`preview_landscape.mp4` (1920x1080) and `preview_portrait.mp4` (1080x1920).
Both contain 17,560 frames at 24 fps: **12:11.667**. The original r5 is
preserved; all 1,147 of its frozen files were reverified.

The new episode `tef_canada_listening_01_inline.json` opts into
`answer_reveal: after_exercise`; existing episodes retain final-only corrections.
Every exercise follows reading silence, complete recording, full response
silence, then answer reveal and spoken explanation before the next exercise.
The task-specific 10/15/30-second response windows are unchanged. Interview
and reportage pairs show both answers together after their shared pause and
keep both visible throughout the two sequential explanations. No recording or
pause is duplicated. All eight instruction families and all 320 seconds of
reading/response silence remain, without chimes, music or accelerated speech.

Forty unchanged clips are reused with verified hashes. Only the new setup
was synthesized using local Qwen3-TTS 12Hz 1.7B Base and measured with French
forced alignment. It explains the immediate corrections and simultaneous
paired reveals. The final-corrections introduction is omitted. Raw ASR flags
and a separate assessment remain available; no human listening is claimed.
The finished P19/P21 book artwork, actual cover and supplied link are retained.

All 34 targeted regressions pass. Both native HyperFrames checks pass all
70 scenes and 712 word-highlight seeks per format. Each MP4 fully decodes
and passes 163 native/encoded frame comparisons, nine opening-word boundary
checks, 28 answer-region before/first-reveal checks and 29 silent intervals
with zero decoded PCM peak. Audio correlation is 0.999987; maximum whole-frame
MAE is below 2.32 and answer-region MAE below 3.75. Video/container duration
is 731.666667 seconds; audio duration is 731.666 seconds.

All 42 native and encoded cards, all 84 encoded countdown-boundary frames,
all 28 encoded reveal-boundary frames and full-size paired corrections were
visually inspected per format. The final answer-silence frame remains unmarked;
the following frame reveals exactly the relevant single answer or pair.
Inspection artifacts and hashes are recorded in `visual_review.json`.

The verified delivery manifest freezes 1,299 files, including generator
snapshots, speech/alignment provenance, source artwork and episode-specific
posts. Separate French TikTok/Instagram/YouTube drafts, measured chapters and
three native-opening thumbnails are in `posts/tef_canada_listening_01_inline/`.
This is guided reduced practice, not an uninterrupted official exam.
Human listening and publication approval remain separate; nothing was uploaded.

## Reveal chime before correction TTS — November 17, 2026

The user explicitly superseded the earlier no-chime request for this new
edition, selecting `mixkit-software-interface-remove-2576.wav`. Fresh review
exports are in
`listening_2d/builds/tef_canada_listening_01_inline_chime_r1/`:
`preview_landscape.mp4` (1920x1080) and `preview_portrait.mp4` (1080x1920).
Both contain 18,288 frames at 24 fps: **12:42.000**. Video, audio and container
durations are all 762.000 seconds, strictly under 15 minutes.

Use the separate episode `tef_canada_listening_01_inline_chime.json` with
`reveal_chime: true`; other episodes retain their no-chime default. After each
complete response pause, show the answer and play the full cue, then start
the unchanged answer TTS. There are 14 cues for 14 recordings. Shared
interview/reportage pairs use one cue before their two explanations, with
both answers continuously visible. All 320 seconds of prescribed
reading/response silence, complete recordings and the silent outro remain.

The original 2.155646-second Mixkit cue is preserved and hash-checked. Only
48-kHz mono conversion and half amplitude are applied: no trimming, tempo
change or added reverb. Its 103,472 normalized samples occupy 52 frames
(2.166667 seconds), including 528 samples of frame-padding silence. TTS starts
after this full interval. All 41 speech/recording clips match the source
edition byte for byte; measured local word timings and ASR evidence are reused,
not approximated or resynthesized.

All 38 focused tests pass. Each format passes native HyperFrames checks,
84 scenes, 712 highlight seeks, complete video decoding, 205 native/encoded
frame comparisons, nine opening-word boundaries, 28 before/first-reveal frames,
28 chime-to-TTS handoff frames and 29 decoded silent intervals with zero PCM
peak. Whole-mix correlation is .999986; minimum individual cue correlation is
.999954 and following-TTS correlation .999975. Maximum whole-frame MAE is
below 2.31 and answer-region MAE below 3.75.

All 56 native and encoded cards, all 84 encoded countdown boundaries and all
reveal/handoff pairs per format were visually inspected. Single and paired
answers remain displayed throughout each cue and explanation. Actual book
illustrations, cover and purchase link are unchanged.

Official Mixkit license and sound-effects FAQ pages were checked; the FAQ
permits commercial/personal video and social-media use without mandatory
attribution. Source/hash, processing and retrieval details are recorded in
`chime_provenance.json`; direct urllib HTML archiving returned HTTP 403, so no
raw-page archive is claimed. New posting drafts nevertheless credit Mixkit.

The verified manifest freezes 1,561 files. Separate French TikTok, Instagram
and YouTube drafts, recalculated chapters and source-linked title thumbnails
are in `posts/tef_canada_listening_01_inline_chime/`. The prior immediate
edition's 1,299 frozen files were reverified and preserved. No new speech was
synthesized; raw ASR flags remain. Human listening and publication approval
remain separate, and nothing was uploaded.

## Approved six-part portrait series — November 17, 2026

The user approved the six-part plan after requesting portrait videos strictly
under three minutes. The derivative configuration is
`listening_2d/episodes/tef_canada_listening_01_social_six.json`; generation uses
`listening_2d/derive_tef_social.py` in a separate
`listening_2d/builds/tef_canada_listening_01_social_six_r2/` directory.
The source manifest digest is
`f4620637d65e4fc12ce2fea7cd811d66a2c2846765277b089ec341df77dd46ef`.

| Part | Original video questions | Complete source families | Source frames (24 fps, end exclusive) | Complete frames | Measured duration |
|---|---|---|---|---|---|
| 1/6 | 1–4 | Pictures and public announcements | 521–4446 | 4055 | 2:48.958 |
| 2/6 | 5–6 | Voicemail | 4446–6636 | 2320 | 1:36.667 |
| 3/6 | 7–9 | Street interviews | 6636–9855 | 3349 | 2:19.542 |
| 4/6 | 10–12 | Radio chronicle and interview | 9855–13825 | 4106 | 2:51.083 |
| 5/6 | 13–14 | Reportage | 13825–15610 | 1919 | 1:19.958 |
| 6/6 | 15–16 | Varied audio documents | 15610–18043 | 2575 | 1:47.292 |

Each short replaces the full general title/setup with a new spoken
“TEF Canada. Partie … sur six.” opening, measured French word highlights,
a two-second shared spoken book CTA and a one-second silent end hold.
Every family instruction, whole recording, original reading/response window,
complete reveal cue and explanation is retained. Original video numbering
and source-book labels remain; pairs are not divided or replayed.

The main picture sequence is reused with frame-accurate cuts, not keyframe-only
stream copying. Exercise PCM must match the frozen lossless source byte for
byte. Persistent numbered badges and a revised scope footer identify each
short without changing the existing question/promotion layout. Native
compositions and encoded captures check the new wrappers, labels, cuts,
word-highlight boundaries, answer reveals, chime handoffs and silent windows.
Separate part-specific post drafts and numbered source-linked covers are
required before freezing. Human listening and publication remain separate.

The initial r1 export exposed a missing color-matrix tag after RGB overlays:
an answer-region comparison reached MAE 5.069749. The preserved r2 revision
keeps source YUV values, converts the badge/footer explicitly to BT.709, and
tags both encodes consistently; the isolated reproduction drops to MAE
1.869252. No timing, layout, text or waveform changed. All fresh r2 native
captures are byte-identical to their inspected r1 counterparts.

HyperFrames 0.9.2 also rejects part 3's fractional three-second closing range
with a 140-versus-141 AAC-packet guard, including with one worker. The separate
`render_tef_wrapper.py` recovery route takes all 72 native PNG frames from
the checked composition and encodes video only; `derive_tef_social.py export`
then resumes and muxes the unchanged authoritative WAV. The helper archives
its own source, commands, frame hashes and provenance. No pause, recording,
cue or narration is cut to work around an encoder packet boundary.

### Completed delivery

The r2 delivery is frozen and all **1,562 files** verify against
`delivery_manifest.json`. All 1,561 frozen full-source files were also
reverified unchanged. Convenient top-level files are
`reel_01_portrait.mp4` through `reel_06_portrait.mp4`; each is a hash-verified
hardlink to its corresponding `part_XX/preview_portrait.mp4`. `reels.json`
records exact frame-clock durations, question ranges, source intervals,
export hashes and aggregate checks.

All six 1080x1920, 24-fps H.264/YUV420p videos pass complete decoding and
strict video/audio/container duration checks below 180 seconds. Exercise PCM
matches the frozen full source byte for byte, preserving all 320 seconds of
reading/response silence, 14 recordings and cues, eight instruction families
and 16 questions with intact pairs. Checks cover 294 native/encoded frame
comparisons, 36 opening-word boundaries, 28 reveal frames, 14 cue/following-TTS
audio checks and 34 decoded silent intervals. Maximum frame MAE is 2.324540;
maximum answer-region MAE is 3.637180. Minimum whole-mix correlation is
0.999984693; minimum cue/following-TTS correlations are 0.999957280 and
0.999978535. Every checked silent interval has zero decoded PCM peak after
the documented codec-edge guard.

All 16 encoded review sheets and six covers were visually inspected,
including complete paired attempt/reveal cards at full size. The native PNG
recovery preserves all 72 closing frames for part 3. All 44 focused unit tests,
the wrapper helper's Python syntax check, JavaScript syntax and Git whitespace
checks pass. No validation threshold was relaxed.

Six separate Instagram/TikTok caption and numbered-cover sets are in
`posts/tef_canada_listening_01_social_six/` and copied into the frozen parts.
The seven new local Qwen 1.7B clips retain measured French alignment, raw
independent ASR flags and the separate contextual ASR review. Human listening,
accent certification and publication approval are not claimed. Nothing was
uploaded, and the original full videos remain unchanged.

### Revised Canadian publishing assets — November 17, 2026

The full YouTube video and all six Instagram parts already had descriptions
and basic source-linked thumbnails. The requested title/cover revision is
separate in `posts/tef_canada_listening_01_publishing_r2/`; earlier posting
assets and both frozen video deliveries remain unchanged.

`youtube_full/` contains `title.txt`, `youtube.txt` and a 1280x720
`thumbnail_youtube.jpg`. Each `part_01/` through `part_06/` contains a title,
Instagram and YouTube descriptions, a 1080x1920 Instagram cover and a
1280x720 YouTube thumbnail. The title pattern is
“TEF Canada | Compréhension orale | Simulation d’examen corrigée” followed
by “16 questions” or “Partie N/6”. Descriptions clearly retain the reduced,
guided-practice qualification, immediate corrections, exercise-specific
content, book link, advertising/AI disclosures and asset credits. Full-video
chapters are unchanged.

The 13 new cover compositions use the supplied book cover and French Compass
logo, existing complete Canadian flag artwork, red/white accents, prominent
exam wording and numbered parts. All primary portrait title/topic/number text
fits within a conservative central square. All cover sizes, JPEG decodes,
text bounds and description/title checks pass; all 13 covers were visually
inspected using `review_youtube.jpg` and `review_instagram.jpg`. Seven video
hashes and all original source/posting inputs were reverified unchanged.
`publishing_manifest.json` freezes 54 files, including source assets, the
generation script and `publishing_index.json`. Pillow was installed only in
the session-local runtime after the existing interpreters lacked it; shared
Python environments were not changed. No speech, video or upload changed.

### Instagram safe-zone correction — November 17, 2026

The user reported that the r2 Instagram covers violate the safe zone. The
previous generator checked selected primary text against a central square,
but excluded the logo, flag, book and bottom banner from that audit. Thus a
central-crop assertion did not establish UI clearance for the complete cover.

The six corrected upload covers are
`posts/tef_canada_listening_01_instagram_safe_r3/part_01/thumbnail_instagram.jpg`
through `part_06/thumbnail_instagram.jpg`. All informative foreground pixels,
including artwork and panels, now occupy `(120,500,841,1113)` within the
conservative `(100,480,850,1130)` project region on each 1080x1920 image.
The bottom banner is replaced by protected in-block wording. Requested
exam-simulation titles, Canadian flags, original book cover, part numbers,
question ranges and complete topic labels remain.

The archived generator audits the full foreground alpha mask, tests four
negative controls for old unsafe placements, and verifies no pixel loss in
24 central crop tests: 3:4, 4:5, square and 10% zoomed square per part.
Twenty-four UI-mask intersection checks pass. Crops and conservative UI
overlays use the actual encoded JPEGs; all upload/proof images decode.
`review_full.jpg`, `review_ui.jpg`, `review_crops_01.jpg` and
`review_crops_02.jpg` were visually inspected. Upload images and proofs are
stored separately.

`publishing_manifest.json` freezes and verifies 63 files, including unchanged
titles/captions, the generator, source assets and safety receipts. All 54 r2
publishing files and all seven source video hashes were reverified unchanged;
YouTube assets were not revised. Meta's primary pages redirected to login or
returned HTTP 429 during reference checks. Accordingly these are explicit
conservative project-owned crop/UI stress tests, not a claim of exact current
official margins, an in-app upload or universal UI certification. No video was
rerendered or published.
