# fide A2-B1 Verstehen: full 2D simulation plan

Planning date: November 16, 2026.
Status: complete script independently reviewed/rechecked and approved by the
user; local Swiss TTS started. Full measured composition/rendering and delivery
validation remain pending. Labelled silent native geometry fixtures are checked.
Use `listening_2d`, not the Blender speaking pipeline.

## Agreed scope

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

## Generation started

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
- Production audio build: `listening_2d\builds\fide_a2_b1_listening_full_production_r1`.
  This prepares 48 unique speech clips and 92 timeline events, with identical
  complete question WAVs reused after each recording.
- Native geometry evidence: `listening_2d\builds\fide_a2_b1_listening_layout_fixture_r2`.
  All 92 scenes pass in each ratio; six contact sheets inspected. The fixture
  has no audio or measured word highlighting and cannot substitute for real
  production/audio/browser/encoded gates. Failed r1 geometry is preserved.
- Early real title probe: `listening_2d\builds\fide_a2_b1_listening_title_probe_r1`.
  4.080-second raw title becomes 5.089 seconds at 0.8x. Both local ASR models
  recognize the complete intended title; strict number-format flags remain.
  This is not human listening or accent certification.

The approved script's adaptation fields and independent review records resolve
advance-answer cues, ambiguous tram directions, the single-journey ticket,
the platform question and overly narrow oral-response rubrics. Original book
manuscripts, images, voices and frozen speaking/listening deliveries are unchanged.
No new final listening videos or publishing thumbnails exist yet.
