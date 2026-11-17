# fide A2-B1 Verstehen: full 2D simulation plan

Planning date: November 16, 2026.
Status: reviewed script approved; all Swiss speech, real alignment, ASR/rechecks,
measured dual-layout composition/browser gates and native sheet inspection are
complete. Both native full exports are validated/frozen; platform descriptions
and crop-safe thumbnails are complete. Nothing uploaded.
Use `listening_2d`, not the Blender speaking pipeline.

## Completed full/social publishing bundle (November 17, 2026)

The user subsequently authorized descriptions and Swiss-themed thumbnails.
New `publish_fide_social_assets.py` binds the frozen full chimes r1 and six
social r1 clips without changing either delivery. Fresh output:
`posts\fide_a2_b1_listening_full_social_01`.

`full` contains `youtube.txt` and `thumbnail_youtube.jpg`; `clip_1` through
`clip_6` each contain `youtube.txt`, `instagram.txt`, `tiktok.txt`,
`thumbnail_youtube.jpg`, `thumbnail_instagram.jpg` and `crop_preview.jpg`.
There are 19 descriptions and 13 covers, plus root contact sheet, measured
layout checks, safe-zone notes and publication manifest. YouTube JPEGs are
1920x1080; Instagram JPEGs are 1080x1920. All are below 2 MB.

Use Swiss flags/red accents, the existing logo/book and large Video N/6
badges (72px portrait / 86px landscape). Social essentials fit within
x=90..900, y=460..1240 and survive centered square/4:5/3:4 crops. Decorative
mountains remain outside the essential card. All 13 covers and six crop
previews were inspected, with no text overlaps or clipped essentials.
Meta's primary help pages returned login/blocked pages; these conservative
design bounds are not a verified universal current Instagram UI specification.
Keep cover positioning centered when selecting the upload crop.

Descriptions identify each task pair/topic, guided practice, unchanged short
exercise pauses, 0.8x speech, per-exercise chime then TTS, direct Amazon link,
AI voices and actual remove-SFX credit. Full YouTube chapters use the measured
timeline, omitting the three-second standalone closing chapter to keep all
seven chapters at least ten seconds. All twelve full replay targets and each
short's two targets are measured separately.

All 34 fide tests pass, followed by the final three-test publication recheck.
Independent external `posts\fide_a2_b1_listening_full_social_01_final_audit.json`
verifies 41 assets / 18 inputs / seven video hashes, dimensions/size/text
budgets, safe/crop bounds, chapter intervals and both unchanged frozen
deliveries (802 full files / 22 code pins; 839 short files / 25 code pins).
Existing full posts remain preserved. Nothing uploaded.

## Completed six-clip social selection (November 17, 2026)

User authorized six standalone portrait clips from frozen chimes r1. Delivery:
`listening_2d\builds\fide_a2_b1_listening_social_r1\clip_N\production_portrait.mp4`.
All are native 1080x1920 at 24 fps; video, audio and container each stay
strictly below 180 seconds.

| Clip | Tasks | Frames | Duration |
| --- | --- | --- | --- |
| 1 | 7-8 | 2966 | 2:03.583 |
| 2 | 9-10 | 3408 | 2:22.000 |
| 3 | 11-12 | 3065 | 2:07.708 |
| 4 | 13-14 | 3595 | 2:29.792 |
| 5 | 15-16 | 3652 | 2:32.167 |
| 6 | 17-18 | 3671 | 2:32.958 |

Preserve all twelve complete exercise blocks exactly once: original questions,
recordings, repeated questions, A2 five-second inspection and ten-second
response silence, B1 twenty-second response silence, complete remove chime,
spoken solution/model and two-second hold. Every clip retains the complete
458-frame voiced CTA/outro. Omit long setup/instructions/ending claims, not
exercise content. Start with the complete title sentence and relevant
situation sentence; introduce the new scenario between tasks in clips 2/5.

Separate `split_fide_social.py`, `check_fide_social.cjs` and
`test_fide_social.py` preserve all frozen helpers. Derive only five measured
sentence prefixes from source speech/word intervals, with no new TTS or
second tempo pass. Both local ASR models recognize all four context sentences
exactly; keep title fide/numeral spelling flags. Native replacement scenes
cover changed title/context intervals; unchanged exercise/CTA footage is
frame-cut and re-encoded with fixed Video N/6/task/subset overlays. Audio
comes from the lossless source WAVs, not decoded AAC. Promotion retains both
the bio/description cue and `amzn.eu/d/0dDgJ1ZT`, including final CTA.

All 31 fide regressions and six native geometry/browser/scope checks pass.
All 30 native and 30 decoded sheets were inspected (234 frames each),
including response/chime/TTS/hold boundaries and both scenario switches.
All 122 encoded events (80 audio / 42 silent intervals), full decoding,
strict duration caps and 234 decoded/browser/full/promotion/notice/footer
comparisons pass. Minimum event correlation is 0.9999708106; guarded silence
peak/RMS are zero and all image-region errors stay below 3.

The independent external `fide_a2_b1_listening_social_r1_final_audit.json`
rehashes 839 delivery files / 25 code pins and recursively preserves chimes
r1 (802/22), inline r1 (646/21) and original full r1 (717/19). It separately
compares each complete exercise block and full CTA/outro PCM byte-for-byte
to the full mix. Preserve inherited ASR/low-alignment/browser notes and
one-frame countdown digit rounding at exact integer boundaries; actual
pauses are unchanged. No human listening or continuous-motion certification.
Full videos and existing posts remain unchanged; no short covers/descriptions
or uploads were requested/generated by this task.

## Authorized reveal chime and promotion follow-up (November 17, 2026)

The user requests a chime first, then the existing spoken answer, and both
the direct book URL and the bio/description cue. Separate
`revise_fide_chimes.py` derives fresh `fide_a2_b1_listening_chimes_r1` from
frozen inline r1. Each complete A2 10s / B1 20s response silence remains
untouched; reveal the answer at the new remove-chime onset, play its entire
137,611-sample tail in a 69-frame event, then start the complete existing
TTS, followed by its unchanged two-second hold. All 47 speech clips and local
word intervals are reused exactly. No new TTS or tempo pass.

Restore "Link in der Beschreibung" for landscape and
"Link in der Bio / Beschreibung" for portrait, alongside the direct
`amzn.eu/d/0dDgJ1ZT` in the persistent book panel and final CTA. Native full
renders are required because the promotion text changes. Both formats add
828 frames to inline r1: **19,486 frames / 13:31.917**. All 25 fide tests,
source PCM/order and both 103-scene browser/geometry checks pass
(`ok=true`, `browserSkipped=false`, no geometry failures). All 36 native
sheets (161 frames per ratio) were inspected, covering every final response,
first/last reveal chime, first/last TTS, hold and next-task boundary. The
restored cue plus URL fits in both promotion panels and CTA phases; promotion
crops are pixel-identical. Both native full MP4s are now validated/frozen:
1920x1080 landscape and 1080x1920 portrait, each 19,486 frames at 24 fps.
All 206 encoded events pass (142 audio including 24 chimes / 64 silences),
with complete decode, minimum event/chime correlation 0.9999597429 and zero
guarded-silence peak/RMS. All 322 decoded/browser/promotion comparisons pass;
maximum RGB/promotion errors are 2.471084/2.524221. All 36 decoded sheets
were inspected, including all response/chime/TTS/hold/next-item boundaries
and both restored promotion/CTA cues.

The external `fide_a2_b1_listening_chimes_r1_final_audit.json` independently
rehashes 802 delivery files / 22 code pins, all 646 files / 21 code pins of
inline r1 and its recursively preserved original delivery. Fresh posts are
in `posts\fide_a2_b1_listening_chimes_01`: three platform descriptions,
three native JPG covers and inspected contact/crop previews. All nine inputs /
eight assets, twelve replay timestamps per platform, caption limits, decoded
cover dimensions/safe bounds and sub-2-MB sizes pass. Descriptions use the
new clocks, both link forms and remove-SFX credits. Preserve inherited
ASR/low-alignment flags, nonblocking browser warnings and disabled-motion/
no-human-listening limitations. Earlier frozen deliveries and posting bundles
remain unchanged; nothing uploaded.

## Authorized per-exercise revision (November 17, 2026)

The user now requests each answer immediately after its exercise and confirms
the complete **10-second A2 / 20-second B1 response silence**, followed by the
existing spoken explanation/model answer and its **two-second silent hold**.
This is guided practice rather than uninterrupted exam presentation.
Preserve the frozen original and its publishing bundle.

Separate `revise_fide_inline.py` / `review_fide_inline.py` derive
`listening_2d\builds\fide_a2_b1_listening_inline_r1` from the frozen full r1.
All questions, recordings, solutions, accepted information and voices remain
unchanged. Remove only the setup's final sentence promising solutions at the
end and retain only the complete first sentence of the closing cue, using
sample-exact prefixes at measured sentence boundaries. Omit the old post-test
solution instruction; do not generate TTS or apply tempo processing again.
Measured revised clock: **18,658 frames / 777.416667 seconds (12:57.417)**.

The user also supplies the new visible book link **amzn.eu/d/0dDgJ1ZT**.
Show it beside Amazon in the persistent panel and final CTA, in both ratios;
use its HTTPS form in the revised posting descriptions. Keep the same cover.
The original book-link delivery remains unchanged.

Preparation and source PCM/independent sequence gates pass; 20 focused fide
regressions pass, including every response/reveal boundary, direct-link markup
and revised caption/chapter/replay timestamps. Both native browser/layout
gates pass with zero runtime/layout/contrast/audio errors. All 28 native sheets
were inspected (125 frames per ratio), including each final response/first
reveal and spoken-solution/two-second-hold/next-item boundary. Promotion crops
are pixel-identical throughout. Retain 94 lint / 54 craft warnings per ratio
and the disabled-motion limitation.

Both small and medium ASR recognize the shortened complete closing sentence
exactly and the complete setup through "Video." without any removed trailing
words. Keep the setup's inherited Hörübung spelling/vowel uncertainty and
medium fide/FIDET recognition, plus all unchanged source speech notes and
low alignment scores. No human listening or accent certification claimed.
Both native MP4s are now validated and frozen at 18,658 frames / 12:57.417:
`production_landscape.mp4` (1920x1080) and `production_portrait.mp4`
(1080x1920), both at 24 fps. All 182 encoded events pass (118 speech /
64 silent intervals); minimum event correlation is 0.9999713941 and guarded
silence peak/RMS are zero. All 250 decoded/browser comparisons and separate
promotion checks pass; maximum RGB/promotion errors are 2.447126/2.331752.
All 28 decoded sheets were inspected, including all twelve response/reveal
and solution/hold/next-item boundaries.

The external `fide_a2_b1_listening_inline_r1_final_audit.json` independently
rehashes 646 delivery files / 21 code pins, all original 717 files / 19 code
pins, and eight publication inputs / eight assets. Revised posting assets
are in `posts\fide_a2_b1_listening_inline_01`: three platform descriptions,
three decoded native JPG covers and an inspected contact/crop preview sheet.
Descriptions use the new link, per-exercise solutions and measured timestamps;
all twelve replay timestamps per platform, caption limits, cover bounds and
sub-2-MB sizes pass. Nothing uploaded; original delivery/posts unchanged.

## Original agreed scope (answer placement superseded above)

- Full A2-B1 listening sequence, using exercises in the user's complete book.
- One scheduled playback per recording. Viewers may rewind the complete
  recording once if needed, representing the optional second listening.
- Swiss Standard German at 0.8x, explicitly slower practice, not a claim of
  official test speed. Preserve pitch and apply tempo processing only once.
- Keep all answers/model responses until after the complete listening test.
- Plan native 1920x1080 and 1080x1920 layouts using the same audio/timeline.
  No short-video generation is included.
- Approved title: **fide A2-B1 Verstehen Prüfungssimulation**.
  Speak the complete displayed opening title and highlight its measured words.
  Mention slower playback and the optional rewind in the setup, not as extra
  opening-title narration.

## Official process and evidence

This is the standard **fide-Test**, not fide edu or another provider's exam.
The listening part belongs to the oral module and uses the level combination
already selected in speaking. Do not introduce a new A1/B1 choice halfway
through listening, or import the speaking section's three tasks.

Official evidence retrieved November 16:

1. The handbook linked from the official professional test page is labelled
   **May 2026**. Printed pages 33-34 describe an individually administered,
   examiner-paced listening part of approximately 15 minutes. There is no
   universal fixed-pause audio track. Each level has two groups of three
   items in a shared scenario/field, and each recording may be heard twice
   on request. A2 uses three illustrated choices; B1 requires oral answers.
2. The currently linked **July 2023 model**, PDF pages 2-4 and 12-14,
   specifies easier level first and confirms the item sequence:
   situation introduction, spoken question, recording, repeated question,
   then the participant's answer. It uses A2 numbers **7-12** and B1
   numbers **13-18**, not 1-12 or an ÖIF 20-question structure.
   Its source-text ranges are A2 30-45 words and B1 35-55 words.
   Original candidate materials do not contain written questions; written
   explanatory text in the model is preparation information.

Reference links:

- https://fide-info.ch/de/test/fideTest/
- https://fide-info.ch/doc/3151/fide_Test_Handbuch_D.pdf
- https://fide-service.ch/de/sprachnachweise/fide-test
- https://fide-service.ch/doc/3090/fideDE_MV_Verstehen_A2_B1.pdf

Keep the two downloaded PDFs, extracted text and hashes in
`listening_2d\builds\fide_a2_b1_listening_research_r1`.
`research_input_pin.json` records versions, URLs, source hashes and user choices.
The July 2023 model is not relabelled as a new 2026 model.
Use these official materials for process evidence, not copied test recordings,
questions, illustrations, branding or answer keys.

## Book provenance and selection

The supplied directory is a combined publication:
`..\german\books\a2_b1\complete_fide`.
Its `book.json` identifies the actual listening components as
`a2\listening_fide_v2` and `b1\listening_fide`. The combined paperback was
extracted locally to verify that the proposed exercises really appear there.
Source files stay read-only.

Choose **Mobilität** for the two A2 situations and **Wohnen/Nachbarschaft**
for the two B1 situations. Each level therefore stays within one coherent
field, rather than combining unrelated three-question blocks.

| Video item | Source in complete book | Question focus | Key / essential information |
| --- | --- | --- | --- |
| A2 7 | A2 Übungssatz 5, Situation 1, Aufgabe 1 | Delayed transport | A: train |
| A2 8 | Same situation, Aufgabe 2 | Correct platform | B: platform 3 |
| A2 9 | Same situation, Aufgabe 3 | What must be purchased? | C: ticket |
| A2 10 | A2 Übungssatz 5, Situation 2, Aufgabe 4 | Tram not going to station | B: tram 7 |
| A2 11 | Same situation, Aufgabe 5 | Reason for changed route | A: construction work |
| A2 12 | Same situation, Aufgabe 6 | Alternative transport | C: bus |
| B1 13 | B1 Übungssatz 2, Situation 1, Aufgabe 1 | Housing problem | Entrance lighting is not working |
| B1 14 | Same situation, Aufgabe 2 | Why particularly inconvenient? | Child/bags make using the phone difficult, or rain increases the urgency of getting inside; one supported reason suffices |
| B1 15 | Same situation, Aufgabe 3 | Expected action from management | Check/repair the light; inform her of a necessary visit |
| B1 16 | B1 Übungssatz 5, Situation 1, Aufgabe 1 | Why the neighbour contacts residents | Advance information about a child's birthday celebration |
| B1 17 | Same situation, Aufgabe 2 | Consideration for neighbours | Quiet music, cleaning afterwards and/or finishing early |
| B1 18 | Same situation, Aufgabe 3 | Why inform neighbours beforehand? | Maintain good relations and prevent problems/conflict |

Item 18's proposed question is a concrete adaptation of the book's broader
question about the speaker's attitude; retain its original recording meaning.
Final questions, accepted information units and alternative answers require
script review. Do not insist on a memorised sentence or penalise grammar as
though this were a speaking-performance task. The official model accepts
short information answers: one to three complete sentences is a book-learning
suggestion, not a universal official B1 answer-length rule.

Location evidence:

- A2 question pages: combined PDF pages 406 onward, beginning at printed
  page 384; component `book_with_images.md:835-876`.
- A2 recordings/keys: same component, lines 1383-1419.
- B1 question overviews: combined PDF pages 667 and 669.
- B1 models/transcripts: combined PDF pages 676 onward and 686-687;
  component `book_no_toc.md:892-924` and `1123-1156`.

### Original script-adaptation requirements

- A2 source item 1 already says platform 3, giving away source item 2's key.
  Remove/replace that sentence in the video adaptation without changing item
  1's train-delay answer. Retain 30-45 words and log the exact change.
- Draft four concise situation introductions and all spoken pre/post
  questions, including the B1 question-18 adaptation.
- Selected original text counts are A2 **32/33/33/34/31/35** and B1
  **55/50/41/42/45/37** words. These are source-text counts, not measured TTS
  durations. Recount after adaptations and spoken-number normalisation.
- Check answer independence, source/model consistency, natural Swiss usage
  and genuine B1 information demands. Generic decorative art must not
  disclose the answer. Preserve legitimate numeric information in A2 choices.

## Pictures and audio inventory

A2 image triplets already exist and are hash-pinned:

- `trimmed_images\E042.png`, `E043.png`, `E044.png`;
- `regenerated_images\backlog-20261106-trimmed\E045.png`;
- `trimmed_images\E046.png`, `E047.png`.

These are relative to `..\german\books\a2\listening_fide_v2`.
All six files decode and have now been visually inspected, including all 18
derived option crops in the labelled native layout fixtures.
Retain the corrected E045, not an earlier tram-number illustration.

The B1 `audio\manifest_swiss.jsonl` maps the six selections to
`uebungssatz_02_aufgabe_01` through `_03` and
`uebungssatz_05_aufgabe_01` through `_03`.
Their referenced output WAVs are **not present locally**. A manifest is not
completed audio. It also contains old POSIX reference paths and book-label
segments; bind valid Windows inputs and author the simulation's 13-18 cues
separately instead of reading those old labels aloud.

Use the existing Swiss voice bank under
`..\shared-voices\gemini_3.8_flash_tts\swiss`:
middle-aged male narrator, middle-aged female service/neighbour voice,
and young adult female resident voice are bound with concrete Windows reference
paths and transcript/WAV hashes before TTS.
Keep the voice of a continuing character consistent. Use Swiss **Standard**
German rather than unintelligible dialect as a decorative effect.

## Proposed event sequence

The structural order below follows the official process. The numeric pauses
are **proposed video-practice settings**, not official mandated intervals and
not yet separately approved. The viewer can pause for additional response time.

1. Spoken title, short setup and A2 instruction.
2. Spoken introduction to the SBB situation.
3. For each of items 7-9: show its three unmarked pictures; ask the question;
   allow **five seconds** to inspect; play its complete recording **once**;
   repeat the question; allow **ten silent seconds** to point/say A, B or C;
   advance without showing the key.
4. Introduce the tram situation and use the same sequence for items 10-12.
5. Introduce B1 oral answering and the housing-management situation.
6. For each of items 13-15: ask the question; play its complete recording once;
   repeat the question; allow **twenty silent seconds** for an oral response.
   Do not add a written question-reading test or multiple-choice alternatives.
7. Introduce the neighbour situation; same sequence for items 16-18.
8. Say the listening simulation is finished. Only now show the six A2 keys
   and six B1 model/accepted-information answers in a clearly separate
   **Lösungen und Modellantworten** chapter.
9. Final voiced CTA for the complete book.

Offer clear chapter/navigation guidance so an optional replay can return to
the whole current recording without revealing its solution. A normal MP4
cannot enforce the maximum two hearings or accept an interactive replay
request; describe rewind honestly rather than simulating a guaranteed branch.
No automatic double playback, fictional examinee answers during the test,
or per-item correct-answer reveals.

Do not copy the ÖIF 30/60-second reading periods, section-end sounds,
three-second inline reveals or once-only broadcast sequencing. There is no
official basis here for extra task chimes. Prefer silent visual transitions,
with no background music, station ambience, cowbells or yodelling.

At 0.8x, total length must be measured after synthesis. A preliminary
**12-18 minute** overall budget including the separate solution chapter is
only an estimate, not a target to force or an official duration claim.

## Swiss 2D art direction

Keep `listening_2d`'s cream cards, relaxed light background and large dark text,
adding restrained Swiss-red accents and the existing public-domain square
Swiss flag. Use the Deutsch Kompass logo, not an official fide/SEM logo.
Subtle mountain silhouettes or a transport-line motif belong outside the
answer area and must not cue an answer. Swiss identity should come mainly
from the voices, situations, spelling and transport/housing vocabulary.

Use one current item per screen:

- A2: three genuine pictures, clearly separated A/B/C labels and no answer
  marking. No written transcript or lexical caption that replaces the picture.
  Keep the spoken question oral, as in the actual process.
- B1: a neutral microphone/oral-response card and item number, not written
  listening text, question subtitles, model answers or a speaking character
  answering on the viewer's behalf.
- Highlight measured words only for the title, general instructions and
  context/setup where appropriate; never subtitle the target recordings or
  silently introduce written questions into the test.
- Reserve a small persistent complete-book/Amazon panel, with the supplied
  `pilot_3d\assets\fide_a2_b1_complete.png` and
  `https://amzn.eu/d/0cFUP7BV`. Landscape cue: description; portrait cue: bio.
  Keep it visually subordinate to the task. Retain one final CTA.

Landscape may show the picture triplet in one row. Portrait needs native
reflow into three legible picture choices, not a squeezed full-width raster
or a crop of landscape. Derive and verify each panel's crop/option mapping;
retain all labels and numeric distinctions. Aim for at least 42px general
mobile prompts/labels and 40px supporting text, with readable numeric choices.
Check actual browser geometry rather than declaring safety from a CSS value.

## Template work needed after approval

Existing ÖIF generators hardcode their exam structures and guided reveals.
Do not relabel an ÖIF episode or modify generators pinned by frozen deliveries.
Add a separate fide episode/schema, planner and compositor under `listening_2d`
with dedicated `picture_choice` and `oral_response` cards. Reuse verified
audio-clock, local browser, alignment and validation helpers where appropriate.

The fide-specific sequence gate must assert:

- exactly 7-18, four situations and 3+3 items per level;
- complete pre-question / one recording / identical post-question order;
- six mapped A2 picture triplets and six oral B1 tasks;
- no automatic second play, transcript leak or solution before test end;
- exact configured silence after the complete repeated question;
- one 0.8x processing pass, concrete reference/PCM hashes and full audio tails;
- persistent promotion, complete voiced opening/CTA and correct locale;
- native 16:9/9:16 text/picture geometry and accurate optional-replay guidance.

Use the existing 24fps/48kHz clock, measured clips and separate speech/silence
events. Future HTML work must follow the composition instructions and pass
the full local HyperFrames check, native snapshots and encoded checks.
Do not claim the current ÖIF validators already implement these fide gates.

## Approval and delivery stages

1. Approve this content/pause/layout plan, then draft the complete script,
   exact source/adaptation ledger, illustration mappings and answer rubric.
2. Independent **Claude Sonnet 5.5** review of the complete script, questions,
   keys and changed items, including Swiss usage and B1 level. Resolve valid
   findings and recheck changed content; bind the reviewed hash.
3. User script approval before any TTS. This gate is complete for the exact
   reviewed episode hash below.
4. Generate/measure local Swiss speech, align instructions, inspect independent
   ASR and unresolved audio flags, and produce both-layout contact sheets.
5. Native layout/process/visual gates, then full exports under the user's
   generation approval. Validate complete decoding, every
   audio/pause boundary, hidden answers, dimensions and source preservation.
6. Full YouTube/TikTok/Instagram descriptions and separate crop-safe covers
   under a fresh `posts\fide_a2_b1_listening_01` bundle, with measured chapters,
   combined-book CTA and accurate slower-practice/AI/independent-material
   wording. Do not infer publication approval or a certified exam result.

## Verified delivery

The user approved the plan/pause settings and the A2-to-B1 transition, then
explicitly approved the reviewed complete script with "Approve and start
generation" before TTS. The transition retains the approved wording, with
pronunciation-only `A zwei` / `B eins` mapped to displayed `A2-Teil` / `B1`.

- Script: `listening_2d\episodes\fide_a2_b1_listening_01.json`.
- Reviewed SHA256: `c2115b131cbfcd6f3c9234db5ad337be5624dff6a309ae096caf6cde024371aa`.
- Independent reviewer: **Claude Sonnet 5.5**, full script/image review and
  changed-item recheck; all mandatory findings resolved.
- Complete readable script, original findings, recheck, resolution and user
  approval: `listening_2d\builds\fide_a2_b1_listening_script_review_r1`.
- Production build: `listening_2d\builds\fide_a2_b1_listening_full_production_r1`.
  All 48 unique speech clips and 92 timeline events are prepared, with identical
  complete question WAVs reused after each recording. The measured clock is
  **19,333 frames / 805.541667 seconds (13:25.542)**, including post-test solutions
  and the CTA. All 32 silent intervals and the independent sequence pass.
- Native geometry evidence: `listening_2d\builds\fide_a2_b1_listening_layout_fixture_r2`.
  All 92 scenes pass in each ratio; six contact sheets inspected. The fixture
  has no audio or measured word highlighting and cannot substitute for real
  production/audio/browser/encoded gates. Failed r1 geometry is preserved.
- Early real title probe: `listening_2d\builds\fide_a2_b1_listening_title_probe_r1`.
  4.080-second raw title becomes 5.089 seconds at 0.8x. Both local ASR models
  recognize the complete intended title; strict number-format flags remain.
  This is not human listening or accent certification.
- Measured production alignment covers all 11 visible narrations. Small ASR
  reviews all 48 clips (10 strict matches); medium rechecks nine flagged clips.
  Keep the original flags and three noncritical uncertainties in Hörübung, the
  SBB app acronym and Halbtax, plus word-alignment scores 0.327/0.421. The medium
  model resolves the question-14 number cue and the Er-hält word-boundary flag.
  No human listening or Swiss-accent certification is claimed.
- Both source/sequence/geometry/native browser gates pass; all 14 measured
  contact sheets were inspected (60 frames per layout, unchanged promotion).
  Retain 95 lint / 54 craft warnings per layout and disabled motion checking,
  not a fabricated motion pass. Both two-worker-per-layout renders are complete.
- Final `production_landscape.mp4` (1920x1080) and
  `production_portrait.mp4` (1080x1920) have 19,333 frames at 24 fps each.
  Complete decoding and all 184 encoded events pass (120 audio / 64 silences).
  Minimum audio-event correlation is 0.9999785527; all guarded silence interiors
  have zero PCM peak/RMS. All 120 decoded/browser comparisons and separate
  promotion crops pass, with maximum errors 2.501109 / 2.310966 respectively.
  All 14 decoded contact sheets were inspected and approval bound to the exact
  encoded review hash before freezing.
- The external
  `listening_2d\builds\fide_a2_b1_listening_full_production_r1_final_audit.json`
  independently rehashes all 717 delivery files / 19 code pins and all seven
  publication inputs / eight assets, binding both final video hashes.
- `publish_fide_assets.py` generated the final
  `posts\fide_a2_b1_listening_01` bundle; all 14 combined fide regressions pass. Captions
  preserve all 12 complete-recording replay timestamps and explain the adapted
  pauses; Swiss covers retain essential text/flag/book in the social crop-safe
  area. YouTube/TikTok/Instagram descriptions contain 1843/1583/1583 characters.
  All three native JPEGs decode below 2 MB; the final contact sheet and
  square/4:5/3:4 crop previews were inspected.

The approved script's adaptation fields and independent review records resolve
advance-answer cues, ambiguous tram directions, the single-journey ticket,
the platform question and overly narrow oral-response rubrics. Original book
manuscripts, images, voices and frozen speaking/listening deliveries are unchanged.
Final listening videos and publishing assets are verified local deliverables,
not uploaded posts or human listening/accent certification. Preserve this
delivery and its pinned programs; use a fresh version for future revisions.
