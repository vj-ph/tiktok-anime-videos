# fide A2-B1 speaking simulation: Blender plan

Planning date: November 14, 2026.

Status: on November 14 the user requested creation of the full video first.
The five-clip social proposal is deferred, not approved for generation.
The full 66-turn / 1,566-spoken-word script is authored in
`pilot_3d\episodes\fide_a2_b1_script.json` and source-bound by `fide_content.py`.
Swiss speech and Blender contact-sheet generation have started in fresh builds.
The user rejected the Three.js visual direction and requested a return to
`pilot_3d`. Preserve that experiment and all existing Blender deliveries.

## Direction

- Title: **fide-test A2-B1 Sprechen Prüfungssimulation**.
- One continuous A2-to-B1 model conversation, not separate full A2/B1 exams,
  an ÖIF three-Teil pair exam, or two candidates taking turns.
- Return to the existing Blender room, established character rigs and
  Deutsch Kompass branding. Reuse the individual-candidate scene direction,
  not the Three.js procedural figures.
- Proposed cast: Lea as the candidate, the older male examiner leading,
  and the older female examiner observing from the side. Hide Samir.
  The active examiner sits opposite Lea.
- Use the supplied Swiss voice collection:
  `..\shared-voices\gemini_3.8_flash_tts\swiss\male_middle_aged.wav`
  and `female_young_adult.wav`, each with its own `text_<voice>.txt`.
  The observer has no spoken turns. Do not reuse the Austrian references
  or blindly follow the book manifests' old Linux voice paths.
- Produce separately composed 16:9 YouTube and 9:16 social layouts.
  Full dialogue and practice content stay the same in both.

## Official-format checks

Checked the official speaking model, pages 2-6, and the handbook currently
served at the following addresses. Despite its filename, the handbook's cover
and section headers say **May 2026**, not July 2023.

- Model: `https://fide-service.ch/doc/3091/fideDE_MV_Sprechen_A2_B1.pdf`
- Handbook: `https://fide-info.ch/doc/3151/fide_Test_Handbuch_D_Juli_2023.pdf`
  Sections: pp. 5-6 and 30-33.

The official format is an individual conversation with two examiners, about
15 minutes. A2 has picture description, a simulated appointment telephone call,
then personal conversation. Examiners recommend the next level; the candidate
chooses. B1 offers two topics and explores experience, process, advantages/
disadvantages and a hypothetical situation. Verstehen is separate.

The A2 book overview says 20 minutes for Sprechen; do not copy that timing into
the video. Use the official speaking documents for the format, and the supplied
books for practice content. Do not confuse the ordinary fide-Test with
fide-Test edu.

## Selected practices

Book roots:

- A2: `..\german\books\a2\speaking_fide_gpt_v1`
- B1: `..\german\books\b1\speaking_fide_gpt_v1`

### A2: Gesundheit, practice set 1, Beim Hausarzt

Keep all three A2 tasks in the same health scenario.
This is the first practice in the Gesundheit chapter, **not the first practice
in the whole A2 book**. The first Arbeit practice is not selected because its
role-play is a face-to-face request for work instructions, not an appointment
telephone call.

| Stage | Exact source | Planned use |
| --- | --- | --- |
| Picture | `04_gesundheit.md:93-125`; compiled book lines 2002-2031; track `fide_a2_037_picture` | Existing woman-and-doctor picture and complete model description; a short natural examiner follow-up if needed. |
| Telephone | `04_gesundheit.md:127-179`; track `fide_a2_038_roleplay`, seven segments | Symptoms, appointment request, afternoon availability, four o'clock, confirmation and farewell. Include the separately written examiner cue before the model dialogue. |
| Personal conversation | `04_gesundheit.md:181-215`; track `fide_a2_039_conversation`, twelve segments | Retain all six book questions/answers. Let the experience and behaviour answers develop through clearly tracked follow-ups rather than turning this into a rapid quiz. |
| Picture asset | `images_no\04_01.jpg`; compiled book image reference at line 2015 | Already visually inspected: woman holding her forehead opposite a male doctor, computer and medical cabinet visible. Reuse the complete image without new generation. |

The six personal questions cover waiting before visiting a doctor, behaviour
when ill, preferred appointment time, what matters in a practice, previous
Swiss doctor visits and healthy everyday habits.

### B1: Thema 1, Wohnen und Nachbarschaft, Set 1

Source: `book_no_toc.md:287-356`.

Offer **Wohnen und Nachbarschaft** and **Arbeit und Arbeitssuche** as the two
practice topics. Both are present in this B1 book (topic starts at lines 287
and 416). Lea chooses Wohnen; do not perform both topics.

| Function | Book question focus | Exact track |
| --- | --- | --- |
| Experience | A particularly positive or difficult housing situation | `fide_b1_002_answer`, source line 309 |
| Process | Finding a home in Switzerland, step by step | `fide_b1_003_answer`, source line 318 |
| Positive/negative aspects | Advantages and disadvantages of city living | `fide_b1_004_answer`, source line 327 |
| Hypothetical situation | Where the candidate would live if free to choose | `fide_b1_005_answer`, source line 336 |
| Follow-ups | Viewing priorities, good neighbours, comparison with home country | `fide_b1_006_followups`, source line 345 |

Keep all four full model answers. Distribute the three existing follow-ups at
appropriate points in the conversation, rather than appending a separate quiz.
Do not include the calibration answer or Set 2 as extra exam sections.

## Proposed on-screen sequence

| Order | Scene / content | Treatment |
| --- | --- | --- |
| 1 | Spoken title and short welcome | Speak the exact displayed title, with measured opening-word highlights; brief name exchange, not a long self-presentation. |
| 2 | A2 Aufgabe 1: Situationsbeschreibung | Examiner introduces Gesundheit and the existing picture; Lea describes it. Keep the picture legible while the model answer plays. |
| 3 | A2 Aufgabe 2: Telefonat | Examiner explains the role-play, then answers as the doctor's practice; candidate requests and confirms the appointment. No extra receptionist character. |
| 4 | A2 Aufgabe 3: Gespräch | Return clearly from the telephone role to personal questions addressed to Lea. |
| 5 | Transition to B1 | Examiner explains the continuation, recommends B1 and explicitly asks whether Lea wants to attempt it; wait for her agreement before introducing the two topics. No invented mark, pass result or certificate. |
| 6 | B1 Themenwahl | Examiner says both topic names; show two simple topic cards. Lea chooses Wohnen. These are practice-video overlays, not reproduced official cards. |
| 7 | B1 Gespräch | Four complete book answers plus related follow-ups; keep it a conversation, not four memorised presentations. |
| 8 | Farewell and book CTA | Examiner closes the simulation; a distinct final book screen follows. |

Use level-specific navigation such as `A2 · Aufgabe 2 · Telefonat` and
`B1 · Gespräch · Wohnen`. Do not label B1 as an official fourth A2 task.
Instructions and choice text are spoken; do not rely on silent reading slides.
Subtitles/task overlays are learning aids, not claims about official test papers.

### Explicit level-choice exchange

November 14 user clarification: the examiner must explicitly ask the candidate
whether she wants to try B1, rather than automatically moving on.

The official procedure is recommendation plus candidate decision, after
explaining the consequences of the next-level choice. This selects the A1-A2
or A2-B1 route; it is not a choice between stopping at A2 and taking B1.
The full transcript must include that brief explanation before the decision.

Proposed original dialogue, not an official examiner-script quotation:

- **Prüfer:** Vielen Dank. Wir empfehlen Ihnen, mit dem Niveau B1
  weiterzumachen. Möchten Sie das versuchen?
- **Lea:** Ja, ich möchte gerne B1 versuchen.
- **Prüfer:** Gut. Sie können zwischen zwei Themen wählen:
  Wohnen und Nachbarschaft oder Arbeit und Arbeitssuche.
  Welches Thema möchten Sie?
- **Lea:** Ich möchte über Wohnen und Nachbarschaft sprechen.

Only proceed to the B1 topic choice after Lea's explicit agreement.
The recommendation is part of the fictional simulation, not an announced
pass or certified result for the A2 tasks.

## Script fidelity and adaptation register

The selected manifests contain **34 segments / 722 spoken words** before
examiner instructions, title, welcome, routing, topic choice, extra follow-ups,
farewell and CTA. Track IDs and segment IDs must remain attached to the review
transcript. Preserve complete source models; record every changed or added line.

Required original/adapted lines:

- Title, welcome, name exchange, transitions, B1 recommendation and choice,
  farewell and book CTA.
- The source phone model calls the candidate **Nadia Hoxha**. Keep this as the
  fictional telephone role and introduce it once in the examiner cue; the
  candidate outside that role remains Lea. Do not accidentally rename Lea
  halfway through the personal conversation.
- The book cue says the examiner is a female practice assistant. For the
  male examiner, use a neutral introduction such as working at the practice.
  Keep the appointment dialogue itself unchanged.
- Any expansion of the short personal-experience answer is original video
  continuation, not a quotation attributed to the book.
- Keep personal history and housing details consistent across all answers.
  Review the existing Lea profile before drafting new biographical details.
- Expand the spoken title abbreviations only for TTS and map the readable
  title to actual measured word groups. Never invent subtitle timestamps.

The books' `audio` folders contain manifests/indexes and explicitly say that
model audio has **not yet been synthesized**. They are text/provenance inputs,
not available finished recordings. Do not mutate the source books or manifests.

## Pace and viewer practice

Plan for approximately **8-11 minutes**, not a promised encoded duration.
That is a modelling estimate for the selected book material plus natural
instructions/follow-ups; it is not a measured TTS timeline or a claim that the
real exam lasts eight minutes.

Use clear conversational Swiss Standard German. Do not inherit the Austrian
episode's `atempo=0.8` automatically; select any slowdown only after reviewing a
new Swiss voice sample. Keep the full responses and natural turn-taking.
No music beneath speech and no artificial long silence to stretch the runtime.

This version demonstrates the complete chosen route, but is a model-answer
learning video, not a duration-identical recording of an examination.
Viewers can pause to answer before Lea. Do not insert repeated 30/60-second
answer countdowns into the exam conversation; a response-gap practice edition
would be a separate later derivative.

The user explicitly requested a long simulation. When implementing it, add an
explicit episode-level long-form bound and keep ordinary under-90-second
preview/short guards unchanged. Do not shorten the full script to fit the
ordinary promotional-preview limit.

## Proposed under-three-minute social series

November 14: user asked how to split the full model video for Instagram and
TikTok, with every clip strictly shorter than three minutes, then rejected
five clips as too many. **Defer all social cuts and revisit a smaller set only
after the full video is complete.** The following five-clip proposal is
historical, not the current generation scope.

Recommend **five numbered clips**, split at task boundaries rather than
arbitrary timestamps. These are editorial duration estimates, including a
brief spoken clip title and final CTA, not measured promises:

| Clip | Content | Target duration |
| --- | --- | --- |
| 1 | A2 picture description: Beim Hausarzt; show the matching picture and complete model answer | 1:00-1:30 |
| 2 | A2 telephone simulation: complete appointment setup, dialogue and confirmation | 1:00-1:30 |
| 3 | A2 personal conversation; then the explicit B1 recommendation/decision and two-topic choice | 1:45-2:30 |
| 4 | B1 Wohnen: experience and step-by-step apartment search, with the related viewing follow-up | 2:10-2:45 |
| 5 | B1 Wohnen: city-life advantages/disadvantages and hypothetical ideal home, with the remaining neighbour/home-country follow-ups | 2:10-2:45 |

- Keep all selected core questions/model answers across the series. These
  are consecutive excerpts of one simulation, not five complete exams.
- Keep B1 consent and topic selection visible in clip 3 before the B1 content
  starts in clip 4. Brief clip-specific titles can restore context without
  replaying the complete opening or previous conversation.
- Preserve the approved full-video speech, conversational pauses and local
  word timings inside excerpts. Reuse verified native Blender frames where
  compatible; recompose portrait graphics and add only short voiced titles/
  endings as needed. Do not accelerate speech to meet the cap.
- Aim for at most 2:45 per clip, leaving a 15-second margin below the requested
  strict three-minute ceiling. Check the complete encoded frame clock,
  including all new opening/closing material, before delivery.
- If measured B1 speech plus follow-ups exceeds the budget, split that pair
  into two single-question clips; do not silently omit responses or cut a
  sentence. The final count may therefore exceed five after actual timing.
- Use clear series numbering (for example `Video 4/5`), not invented official
  exam-section numbering. Retain the relevant book promotion, word highlights,
  final CTA and exercise-specific Instagram/TikTok drafts.
- The full 8-11-minute estimate remains separate. Total series runtime may
  be longer because each social clip has its own opening and ending.
- No 30/60-second learner-response holds are planned in these model clips.
  Viewers can pause; a timed self-response edition remains a separate option.

## Blender layout and book promotion

- Reuse the established individual-exam Blender room/rigs and downward hair.
  Verify opposite seating, silent observer, gaze and all head/hair bounds in
  the actual cameras before animation.
- Landscape: room/conversation as the main scene, compact book promotion
  vertically centred on the right, and legible task picture/captions.
- Portrait: independently position scene, full picture/topic cards, captions
  and compact promotion; do not crop a finished landscape composition.
- Show the A2 book cover during A2 and the B1 cover during B1; retain one
  compact relevant cover/Amazon cue throughout, including transitions.
  The final CTA can show both covers once, without a duplicate side panel.
- Use the combined **Sprechen + Schreiben** covers: A2
  `a2\combined_fide_gpt_v1\fide_a2_combined.jpg` and B1
  `b1\combined_fide_gpt_v1\fide_b1_combined.jpg`, relative to the books root.
  The user clarified that both supplied links are for these combined books;
  do not promote the speaking-only covers.
- User-supplied Amazon links, November 14: A2 `https://amzn.eu/d/05ZjsyvD`;
  B1 `https://amzn.eu/d/0dBQqMFu`. Do not reuse the ÖIF links.
  Use description wording on YouTube and bio wording on social.
  The links are supplied by the user, not independently certified product metadata.
- Final CTA message: more tasks and model dialogues in the fide A2/B1
  Sprechen + Schreiben books, followed by the appropriate Amazon description/bio cue.
  Keep independent-practice and AI/asset disclosures in the post drafts.

## Implementation and review order

1. Draft a source-linked, speaker-labelled complete German transcript from
   the practices above, with visible versus spoken title text and the
   adaptation register. Obtain text approval.
2. Produce Blender contact sheets for both layouts using the existing room,
   selected doctor picture, covers, choice cards, subtitle examples and final
   CTA. Obtain visual approval; illustrative highlights are not measured speech.
3. Generate/review a short Swiss voice sample, then prepare approved full
   speech, word alignment and lip cues in a fresh build. Report the measured
   duration and retained ASR/low-confidence flags.
4. Implement a fide-specific episode/dispatch path through `pipeline.py`.
   Existing A2 individual-exam components are reusable implementation
   references, not proof that changing the exam title gives correct fide support.
   Keep old B1/B2/A2 and short routes unchanged.
5. After approval, render a complete preview; inspect actual encoded title,
   role transitions, picture/topic choice, word boundaries, pauses and both
   aspect ratios before production.
6. Production should use the existing shared-frame default: 24 fps,
   eight Cycles samples, native motion on twos, full-resolution overlays,
   1920x1080 and 1080x1920 output, with portrait-safe native scene frames.
   Prepare matching platform drafts and obtain separate publication approval.

The user supplied both fide Amazon links and authorized the full video before
short adaptations. Full-length preview generation is authorized; final
production and publication still require separate approval.

Combined-cover revision: use `episodes\fide_a2_b1_combined_full_preview.json`
and fresh `builds\fide_a2_b1_combined_full_preview_r1`. Keep the original episode
and raw-speech pins unchanged; the 66 spoken turns, Swiss references and tempo
are identical. Both revised contact sheets are verified in
`builds\fide_a2_b1_contacts_r3`; no room rerender or speech restart is required.

Full preview delivery is complete in
`pilot_3d\builds\fide_a2_b1_combined_full_preview_r1`: both MP4s run 9:32.04
(13,729 frames at 24 fps), including authored pauses and final CTA. The
separate final audit and compact decoded-frame sheets are in
`pilot_3d\builds\fide_a2_b1_combined_full_review_r1`. All encoded checks and
source/native/audio-chain hashes pass. Human listening/user approval remains
pending; 13 primary-ASR differences, five low-confidence aligned words and
16 caption reading-speed warnings are retained without changing pass flags.
This is reduced-quality preview output, not production or publication.

## Approved revision after full-preview feedback

On November 14 the user selected the recommended targeted trim and requested
0.8x speech plus Swiss flags on the table and wall. The revised episode is
`episodes\fide_a2_b1_trimmed_08_preview.json`, with a separate 48-turn script.
A2 Aufgabe 3 has three main pairs on preferences, one doctor's visit and the
appointment procedure. Remove the duplicated picture follow-up and the three
authored paragraph-length B1 follow-ups, while retaining the complete telephone
task, all four main B1 models and the three short source follow-ups.
Shorten the routing explanation but preserve level/result choice, Verstehen
context and Lea's explicit consent. This intentionally selects 24 unchanged
source segments rather than claiming to retain all 34 original ones.

The new generation path preserves raw recordings and applies pitch-preserving
0.8x tempo before measured lip/word alignment; authored pauses stay unchanged.
Native flag contacts and source/compatibility tests pass. The wall flag is on
the visible side wall so it and the desk flag fit the portrait-safe wide crop.
Recorded public-domain/CC0 sources and downloaded hashes accompany the assets.
Completed output: `builds\fide_a2_b1_trimmed_08_preview_r1`; previous deliveries
remain frozen. Both formats contain 12,241 frames at 24 fps = 8:30.04.
Full decodes and 57 encoded boundary/highlight checks per format pass, with
audio correlation above .99999. Verify 3,529 native, 182 export and 288
speech-chain hashes, current generation/asset pins and all 217 unchanged
original-delivery hashes. Inspect both decoded sheets and final CTAs.
The separate `builds\fide_a2_b1_trimmed_08_review_r1` retains 14 ASR
disagreements and two low-confidence words; all 122 caption pages fit and
none has a reading-speed warning. Measured chapters are in the new YouTube
draft. Human listening and user approval remain pending; no production/publication.

## Production command after revised-preview approval

The user subsequently approved the revised previews and requested the production
command, not execution. `episodes\fide_a2_b1_trimmed_08_production.json` pins the
approved manifest, unchanged script/voices/assets and inherited speech flags.
Use `pipeline.py build --profile production --reuse-audio` as documented in the
README, with a fresh `builds\fide_a2_b1_trimmed_08_production_r1`. Produce
1920x1080 and 1080x1920 at 24 fps, eight samples and motion on twos from shared
full-size native images, baking the complete scene afresh.

102 tests and real audio-only production validation pass: the six reused files
are byte-identical, the frame clock stays at 12,241, and the plan contains 5,285
full-size native frames. Verification is in
`builds\fide_a2_b1_production_audio_validation_r1\command_validation.json`.
No full production render has started; human listening is not certified and
publication approval remains separate.

## November 16: one complete A2-B1 book

The user resumed the production after the documented stops. Both full-size
exports and the production manifest were complete by November 16. The user
then supplied a new complete A2-B1 Sprechen + Schreiben + Hören cover and
`https://amzn.eu/d/0cFUP7BV`, replacing both level-specific promotions.

Keep the completed production immutable. The new standalone derivative
`revise_fide_book.py` reads `episodes\fide_a2_b1_single_book.json` and writes
`builds\fide_a2_b1_single_book_r1`. It verifies all source delivery files,
source snapshots, source speech-chain hashes and 5,285 shared native PNGs.
No live manuscript or source scene is needed because no exam speech or
native animation is regenerated; the reused picture, emoji and Swiss voice
references are checked against the recorded source pins.

Both layouts show the one complete cover from the opening through the final
CTA. Rewrite the spoken CTA to singular, explicitly mentioning Sprechen,
Schreiben und Hören and one Amazon link; synthesize only this ending at 0.8x.
The first 47 turns and all PCM before frame 11,840 stay exactly unchanged.
Fresh forced alignment and independent ASR cover the new ending. The measured
new duration is 12,284 frames / 24 fps = 511.833333 seconds (8:31.83).
Both contact sheets and full-size final CTA panels have been visually inspected.
All 122 caption pages fit with zero reading warnings and two low-confidence
words. The CTA ASR uses digit/hyphen spelling for the level and is retained as
an automated disagreement, not relabelled as a passed human listening check.
Updated post drafts use one link in `posts\fide_a2_b1_single_book`.
Both full-size recompositions are complete: `production_youtube.mp4`
(1920x1080) and `production_social.mp4` (1080x1920). Full decodes, 130 encoded
highlight/cover checks per format and encoded/reference audio correlation
.999696 pass. Verify the single new cover/link in every sampled turn and
confirm exact preservation of 23,680,000 pre-CTA PCM samples, all 5,285 native
images, 372 derivative hashes and all 340 original-production hashes.
Inspect both encoded openings/final CTAs. Fourteen ASR disagreements and two
low-confidence words remain recorded, without human-listening claims.
Independent verification and visual inspection receipts are in
`builds\fide_a2_b1_single_book_review_r1`. No publication approval.

## Three approved social excerpts

The user approved three cohesive cuts, each strictly below 180 seconds,
then requested the generation command, not full execution. Use
`pilot_3d\derive_fide_social.py` with
`episodes\fide_a2_b1_social_three.json` and the separate destination
`builds\fide_a2_b1_social_three_r1`. Each clip folder will contain
`production_social.mp4` at 1080x1920 for TikTok and Instagram.

1. `video_1_a2`: picture, complete telephone task and three personal pairs;
   3,999 frames / 24 fps = 166.625 seconds.
2. `video_2_b1_erfahrung_ablauf`: recommendation, explicit consent, choice,
   experience and procedure; 4,250 frames / 24 fps = 177.083333 seconds.
3. `video_3_b1_meinung`: opinions, neighbours, ideal living and farewell;
   2,872 frames / 24 fps = 119.666667 seconds.

Keep the spoken/measured opening in each and label Video 1/3 through 3/3,
not exam Teile. Keep complete selected turns and their following pauses.
Only the CTA uses a within-turn cut: the complete final Amazon-link sentence,
starting at measured source-local frame 284, after the previous aligned word
and before the next. Rebase real alignment and lip cues without estimating
timestamps. Append the original outro, retaining one combined book cover.
All speech remains 0.8x; no synthesis, time-stretching or Blender rendering.

Preparation-only validation verifies the three clocks, byte-exact PCM,
4,684 native mappings/hashes, preserved source delivery and 110 caption pages
without reading warnings. Sixteen focused tests pass. The 278-frame
opening/CTA diagnostic passes decoding, 24 encoded checks and .997021 audio
correlation; inspect its contact sheet. No complete short export, new ASR,
human listening or publication approval is claimed. Post drafts are in
`posts\fide_a2_b1_social_three`.
