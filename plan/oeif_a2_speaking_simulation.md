# ÖIF A2 long speaking video: doctor appointment

Planning date: November 8, 2026. The user subsequently authorized still-only
contact sheets after the full transcript and Polish-background revision.
Verified revised dual-format contact delivery: `pilot_3d\builds\oeif_a2_speaking_contacts_r11\`
(19 panels per format, three shared room stills). The revision uses the combined
book, opposite examiner seating and larger unnumbered stacked social choices.
The original r9 exports remain unchanged. No TTS, alignment, animated
preview or production was generated. The still entry point is not A2 video
pipeline support. Preserve all completed B1/B2 deliveries and source pins.

## Confirmed direction

- Use `..\german\books\a2\speaking_oeif_gpt_v1` and a coherent doctor topic.
- Lea is the only candidate throughout. The existing older male examiner
  leads and plays the practice receptionist during the role-play. The older
  female examiner observes. Samir is absent, not a second candidate or
  picture-description speaker.
- Use the first contact exercise and first everyday dialogue. The user
  accepted the matching third picture instead of the unrelated first
  family-meal picture. Do not claim every selected task is the first task
  in its chapter.
- Latest user-selected promotion: combined **ÖIF A2 Sprechen + Schreiben**
  cover and `https://amzn.eu/d/0eC3q7T3`, replacing the standalone cover/link.
- Seat the active examiner directly opposite Lea, not beside her, per the
  November 8 visual revision. This intentionally differs from the official
  model's preferred right-angle arrangement recorded below.
- Social picture choice: stack the three full images vertically, without
  numbers, inside a taller board. Keep YouTube's numbered horizontal choices.
- November 8: user selected **FFmpeg `atempo=0.8` for all TTS speech**.
  Apply after speech preparation and before forced alignment/lip-sync;
  keep pauses on their separately authored frame clock.
- Full 55-turn transcript for review:
  [A2 transcript](oeif_a2_speaking_transcript_review.md). It preserves the
  selected source models, tracks Lea's rename and book/author additions,
  and includes the spoken title, every examiner/candidate turn and final CTA.
  Text review is not audio or preview approval.
- Proposed spoken/displayed title: **ÖIF A2 Sprechen mit Lea**.
  Proposed publication title: **ÖIF A2 Sprechen - Prüfungssimulation**,
  with **Mit Lea · November 2026 · Episode 1**. No paired Lea/Samir title.
  Final thumbnail wording requires review; avoid claiming an official exam.

## Verified official process

Primary reference, retrieved November 8, 2026:

`https://sprachportal.at/fileadmin/user_upload/meinsprachportal-at/Materialen_zur_Pruefungsvorbereitung/A2/OEIF-TEST_neu_Modelltest.pdf`

This is the official **ÖIF-Test Neu – Kommentierter Modelltest A2**.
HTTP Last-Modified was January 16, 2026; that is a server timestamp, not a
claimed examination-effective date or proof of a newly issued format.
The reference was downloaded and read using `pdftotext`, not inferred from
B1/B2 materials. Exact printed page references:

| Pages | Rules relevant to the video |
| --- | --- |
| 9 | About ten minutes overall; one candidate, active examiner and second examiner/assessor; no preparation time or dictionaries. Examiner speaks slowly and clearly. Avoid frontal exam seating; prefer a right-angle table arrangement. |
| 10, 27–28 | Examiner introduction and explanation of recording, followed by S1 contact conversation using prompt words. Candidate also asks the examiner questions. Follow-ups are open questions. Stages form a connected conversation, not three disconnected performances. |
| 10, 29 | Examiner offers three picture cards selected from five; candidate chooses one and identifies the situation. Examiner must not name it before the candidate identifies it. The remaining conversation stays on that topic. |
| 30 | Brief situation description, then role-play with the examiner. Candidate asks at least two relevant questions, supported by situation prompts. Examiner follows up and responds conversationally. |
| 31 | S2B personal experience on the same picture topic, optionally supported by prompts on the reverse of the card. |

The official example set is bank, parent/teacher meeting, course, market
and mobile-phone shop. The doctor's picture is a **book-based adaptation
of the process**, not a card reproduced from the official model.
Do not add B1 planning or B2 presentation/discussion sections to A2.
Do not introduce a twenty-minute preparation countdown or pre-exam narrated
preparation cards. Candidate task prompts appear when the examiner presents
them during the conversation.

Do not fake an examination institution, recording of a real exam or a real
assessment. A brief original examiner explanation of the simulation is
sufficient; any filming/audio-recording explanation must be labelled as
part of the fictional practice scene.

## Source selection and provenance

Manuscript: `..\german\books\a2\speaking_oeif_gpt_v1\book_no_toc.md`.
Audio inventory: same directory, `audio\manifest.jsonl` (69 model tracks).
No selected synthesized recordings were found; `audio\README.md` labels
the inventory as not yet synthesized.

| Stage | Exact source | Selected content |
| --- | --- | --- |
| S1 contact | Chapter 1, lines 182–205; `oeif_a2_001_kontakt_beispiel`, `oeif_a2_002_kontakt_fragen` | First exercise, “Kontaktgespräch 1: Über mich”; Name, Heimat, Wohnort, Sprachen; model introduction and three examiner questions/answers. |
| S2 picture choice | Chapter 4, `images\01.jpg`, `images\02.jpg`, `images\03.jpg` | Offer family meal, shopping and doctor waiting room as three untitled picture choices. Lea chooses the doctor's image. These are original book images, not official model cards. |
| S2A identify situation | Chapter 4, “Arztpraxis / Wartezimmer”, lines 1443–1485; `oeif_a2_038_beispiel` | Existing picture and model description; no new illustration or invented picture exercise is necessary. Identify the waiting room briefly; do not turn this into a separate B1-style long description. |
| S2A role-play | Chapter 2, “Einen Arzttermin ausmachen”, lines 314–382; `oeif_a2_011_dialog` | First everyday dialogue: symptoms, available appointment times, selection, E-Card and farewell. Examiner acts as the practice receptionist. |
| S2B personal experience | Chapter 4, same doctor task; `oeif_a2_039_uber-die-eigene-situation-sprechen`, selected personal questions from `oeif_a2_037_bild_fragen` | Existing personal-experience answer, telephone/online booking preference, documents taken to appointments. Maintain one doctor-related topic. |

Manifest `source_line` values are retained as inventory provenance but do
not all equal current manuscript heading/model line numbers. Record both
the current manuscript span and exact manifest track/segment IDs.
Do not replace author-supplied `text_original` with derived text.

Chapter 3's first “Öffis oder Auto?” opinion task is extra training, not
an independent official A2 exam stage. Omit it from this simulation.
The Chapter 2 doctor's personal-experience extension can be supplementary,
but the main S2B model should be the matching Chapter 4 answer.

### Explicit adaptations to record

1. Adapt source “Samira Hassan” to Lea in the spoken introduction and
   display. November 8 user revision: Lea comes from Warsaw, Poland
   (German: Warschau, Polen), and speaks Polish at home. Keep the fictional
   background consistent across contact answers: Warsaw/Poland, Graz,
   two years in Austria, Polish/English/German.
   These are fictional character details, not claims about a real person.
2. Add natural examiner opening, choice instructions and stage transitions.
3. Add candidate-to-examiner questions for S1 because the contact source
   supplies only examiner follow-ups. For example, Lea asks where the
   examiner lives or which languages he speaks; original fictional replies
   must be consistent and A2-level.
4. Integrate the Chapter 2 “Zwei gute Fragen im Dialog”:
   “Wann ist der nächste Termin frei?” and “Muss ich meine E-Card mitbringen?”
   into the appropriate places before the corresponding model replies.
   The eight-turn original dialogue alone contains no candidate question
   sentences and does not satisfy the official two-question requirement.
   Keep original model segments and record additions separately.
5. Use short, A2-level examiner follow-ups only where needed to make
   the contact and personal-experience phases genuine interaction.
   Avoid padding, duplicated answers, advanced vocabulary or forcing ten
   minutes from these short models.

Medical content is fictional appointment-booking language, not diagnosis
or treatment guidance. Do not add medical advice to extend the scene.

## Proposed running order

| Order | On-screen and spoken action |
| --- | --- |
| Opening | TTS speaks the displayed title; measured word highlights. Brief book promotion remains visible. |
| Introduction | Introduce the two examiners and Lea; examiner explains the practice conversation in natural German. No Samir or preparation countdown. |
| S1 | Prompt card appears when presented. Lea introduces herself; examiner asks follow-ups; Lea asks examiner questions. |
| Picture choice | Show three book pictures without topic labels; examiner offers the choice without revealing the doctor topic. Lea selects picture 3. |
| S2A identification | Enlarge the doctor's image; Lea briefly identifies/describes the situation. Show the picture while she speaks. |
| S2A role-play | Examiner sets the patient/receptionist roles. Situational prompt words appear. Lea asks at least two questions during the appointment dialogue. |
| S2B | Transition directly to Lea's own doctor-appointment habits. Keep the same picture/topic, using optional personal-experience prompts. |
| Closing | Examiner closes the conversation. No fabricated score or assessor deliberation. |
| Final CTA | Separate book CTA: more tasks and model dialogues, Amazon description/bio cue. Do not duplicate the regular promotion sidebar on this screen. |

Use unobtrusive navigation **S1 · S2A · S2B**. Labels aid the viewer but the
examiner should transition naturally, not announce unrelated “Teil 1/2/3”
performances. No preview or production duration is claimed yet.

## Timing, voice and delivery approach

- This user-requested long-form episode is an explicit exception to the
  ordinary under-90-second policy, not a change to the default. Set a
  separate measured ceiling when the full script is approved.
- Official conversation duration is approximately ten minutes, not a
  compulsory ten-minute clip. These models may yield a shorter simulation.
  Report a script-based estimate first, then actual speech/frame timing;
  do not promise exam-length pacing or fill time with repeated speech.
- Reuse approved Austrian examiner and young-adult female reference voices
  only after checking current paths, transcript and user approval for Lea.
  The book inventory's reference paths are historical Linux paths and
  different voice IDs; do not blindly execute them on Windows.
- User-selected tempo overrides the manifest's 0.90×/0.95× defaults:
  use **`atempo=0.8` for every TTS turn**, including opening, examiner,
  candidate and CTA. Confirm natural A2 pacing in the preview, measure
  alignment on the processed speech, and never accelerate it to fit.
- Speak the title, instructions/transitions, candidate answers and CTA.
  Purely optional reading pauses should be short and disclosed as learning
  aids, not official preparation time. Do not add duplicate task narration.
- Force-align actual speech; map displayed “ÖIF”, “A2”, “15 Uhr” and “9 Uhr”
  to their real spoken tokens. No estimated word times.
- YouTube master first: 1920×1080. Full social: 1080×1920 from the same
  lossless native scene frames/audio, recomposing overlays rather than
  cropping the completed YouTube video.
- Default production: 24-fps output, native animation images on twos,
  full native scale, eight Cycles samples, native YouTube source.
  Verify the user-selected opposite three-person exam seating and portrait-safe head/hair
  framing. The four-person B1/B2 thumbnail is not suitable for this cast.
- Prefer contact sheets/script review first; generate a preview only after
  the next explicit go-ahead. Production requires approved preview/audio.
  Missing-frame recovery must preserve verified completed PNGs.
- An under-three-minute derivative is optional, not requested here. If later
  requested, use complete-turn cuts and label it `Kurzfassung`.

## Book promotion and publication drafts

Latest supplied short link: `https://amzn.eu/d/0eC3q7T3`.
GET redirected to Amazon product **B0H3TJYBRG** on November 8; the response
was a robot-check page, not independently verified product metadata.

The user explicitly selected the combined cover rather than the standalone
speaking book:
`..\german\books\a2\combined_oeif_gpt_v1\oeif_a2_combined.jpg`.
Visually inspected: **ÖIF A2 Sprechen + Schreiben Übungsbuch**, 54 exercises,
dated October 6, 2026. Keep source exercises from the agreed speaking chapter;
change the displayed promotion, final spoken CTA and all post links to the
combined book. The transcript now has 55 turns and 686 display words.

Keep the correct small book cover and Amazon description/bio cue persistent
outside the final CTA; use the established vertically centered YouTube
promotion and portrait-safe placement. Show Deutsch Kompass branding.
Publication covers should use the three actual participants, Austrian flag,
correct A2 title and reviewed episode label. All essential portrait content
must survive the established centered square/4:5/3:4 crop tests.

Planning-stage platform drafts are in `posts\oeif_a2_speaking_long_01`.
Keep advertising/AI disclosures, independent book-practice explanation,
explicit process/topic/name adaptations and reused rig/image credits in
posts, not a restored full-screen disclaimer. No upload or publication
approval is implied.

## Implementation and acceptance gates

**November 8 preview authorization:** the user requested the complete preview
after the r11 contact corrections. The separate
`episodes\oeif_a2_speaking_full_preview.json` route now validates all 55
reviewed turns and pins the transcript/contact hashes. The full YouTube preview
is complete in `builds\oeif_a2_speaking_full_preview_r1`: 960x540, 24 fps,
CPU/two-sample/quarter-scale native scenes every three frames; all speech uses
the established Austrian references at `atempo=0.8`. Forty-nine focused tests
and native animation/recovery diagnostics pass. All 55 slowed clips, measured
alignment and the 1789-frame native bake/render are complete. The final
7067-frame video is 294.458 seconds; full decode, audio correlation 0.99964,
65 initial and 95 additional encoded highlight/transition frames pass.
Both encoded contact sheets and representative full-size frames were inspected;
source/export/native/approved-contact hashes remain unchanged.
Ten independent ASR disagreements remain flagged, including abbreviations/
numerals and possible wording differences; human listening is not claimed.
The user subsequently approved the existing preview/audio as the production
source and requested implementation of the command, not the full render.
`episodes\oeif_a2_speaking_production.json` now pins that exact source and
supports full-resolution/eight-sample/on-twos native rendering, explicit HIP/CPU,
exact audio reuse and completed-frame recovery. The configured command exports
YouTube first; both full-size encoders share the same native PNGs when selected.
Eighty-three tests, real HIP/source validation, byte-identical audio-only reuse,
both-layout full-dialogue caption preflight and a 41-frame native opening/
encoded/resume diagnostic pass. The user subsequently completed YouTube
production and authorized both social versions on November 8.
`builds\oeif_a2_speaking_social_delivery_r1` now contains verified full
294.458-second and Kurzfassung 178-second portrait videos, both 1080x1920/24 fps.
The short retains 32 complete turns, all doctor-picture/role-play turns, one
personal model and CTA. No new TTS/Blender/alignment, no acceleration.
Exact PCM/local-word/lip-cue preservation, PNG/portrait bounds, full decode,
100/77 encoded samples, 95 extra short-cut boundary frames and all delivery/
production preservation hashes pass; representative encoded frames inspected.
Publication remains unapproved and human listening unclaimed.

1. Review this selection and cast; confirm cover/link and title. Approve
   the full script, additions and proposed measured duration ceiling.
2. Add a separate A2 long-speaking profile with S1/S2A/S2B and three-person
   exam scene. Existing `long_speaking` validation supports B1/B2 only;
   changing the level string is not sufficient. Keep existing frozen
   generation sources/deliveries intact and require fresh reviewed builds
   for any new generator changes.
3. Make contact/picture-choice/role prompts and contact sheets for both
   layouts; verify no examiner topic reveal before picture identification,
   one candidate throughout and same topic across S2A/S2B.
4. Validate source fidelity and tracked identity/extra lines, candidate
   questions in S1 and at least two in S2A, digit speech mappings, all
   picture assets, full/native shared-crop layout and source hashes.
5. Following preview authorization, generate/cache approved speech,
   force-align and measure the exact frame clock. Check timing before
   expensive bake/render; preserve ASR disagreements and low-confidence
   words for human review.
6. Verify encoded stage transitions, picture selection, subtitles/highlights,
   persistent promotion, final CTA, full decode/audio correlation and
   exact source preservation. User listening/preview approval remains a
   separate gate before production.
7. Build full-resolution YouTube once, then derive portrait from its
   lossless native frames/audio. Verify both exports and crop-safe covers;
   require separate publication approval.
