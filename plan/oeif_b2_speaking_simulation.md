# ÖIF B2 speaking simulation: first practice in each Teil

Planning date: November 5, 2026. **Implementation requested November 5: prepare
the full YouTube master first, then derive full portrait and under-three-minute
social versions from shared scene frames/audio.** See `TODO.md` for live status.

Preview direction, November 5: generate **only a YouTube preview**, not
production. Replace the full-reading pages with one labelled abstract. Voice
the task-preparation cards and the abstract with the examiner's Austrian TTS,
including the reference to the full book text; highlight their words using
measured alignment. On November 6 the user explicitly approved the completed
r6 YouTube preview, including its audio, as the production source and requested
the production command. Prepare/validate that command only; do not start rendering.
The source-pinned configuration and exact-byte approval bundle are documented
in `pilot_3d/README.md`. Social cuts and publication remain separate.

## Confirmed scope

Prepare an exam-paced video and a separate **strictly under-three-minute social
adaptation**. Follow the real interaction pattern, but omit a second standalone
performance of the same task. Show Lea's presentation and Samir's follow-up
questions; skip Samir's own presentation and the questions about it. Retain both
candidates throughout genuine conversations, including the contact phase,
discussion and joint planning. Keep both initial text reactions in Teil 2:
these establish the ensuing discussion, rather than repeat a solo performance.

The long version is therefore **exam-paced with an explicitly shortened Teil 1**,
not an uncut, complete pair exam. Do not pad it to claim a 15-minute examination.
The short version demonstrates all three task types, not complete exam timing.
This request authorizes separate long-form and under-180-second planning;
do not relax the existing shared under-90-second limit for unrelated episodes.

## Official format checked

Verified against the ÖIF model test **valid from October 15, 2026**, printed
pages 3, 32-34 and 45-46; checked November 5, 2026:

`https://sprachportal.at/fileadmin/user_upload/meinsprachportal-at/Materialen_zur_Pruefungsvorbereitung/B2/B2_OEIF-Test_Modelltest_ab_15.10.2026_15102026.pdf`

- Individual preparation: 20 minutes. Regular format: two candidates, two
  licensed examiners; approximately 15 minutes of conversation.
- Unassessed contact: approximately 30-60 seconds per person.
- Each Teil: approximately 2½ minutes per person. Teil 1: one of five topics,
  presentation at most 90 seconds, then partner questions; normally both present.
- Teil 2: each reacts to the prepared text for at most one minute, then discussion.
  Teil 3: joint problem-solving.
- Examiners moderate with minimal speech; candidates face each other.
  Approximately five further minutes are for examiner deliberation, not speaking.

The older 2025 landing page and the book's two-or-three-candidate summary must
not override this current PDF. This plan depicts the regular pair format, not a
three-candidate or digital-exam variant. Use the official material to verify
structure, not to replace the user's book exercises with official sample tasks.

## Book and exact exercise selection

Use **ÖIF B2 Sprechen + Schreiben – Übungsbuch**, combined v2, third edition,
October 2026. Its short introduction is not the complete speaking manuscript.
`combined_oeif_gpt_v2\assemble-book.py` includes the sibling speaking v2 manuscript.
Do not run the assembler or change any book/audio preparation files.

Source root: `..\german\books\b2\`

| Teil | First actual exercise | Speaking manuscript lines | Audio manifest track |
| --- | --- | --- | --- |
| 1: Präsentation | Ein Buch, das Sie beeindruckt hat | 156-189; model heading 175 | `oeif_b2_v2_001_praesentation` |
| 2: Diskussion | Soll die Sommerzeit abgeschafft werden? | 593-646; model heading 626 | `oeif_b2_v2_026_diskussion` |
| 3: Problemlösung | Betriebsausflug organisieren | 1238-1279; model heading 1258 | `oeif_b2_v2_047_planung` |

Speaking source: `speaking_oeif_gpt_v2\book_no_toc.md`.
Manifest: `speaking_oeif_gpt_v2\audio\manifest.jsonl`.
Selected segment IDs end in `_seg_001` for track 001 and `_seg_001` through
`_seg_010` for tracks 026 and 047.

Exclude introductory planning track **046**, “Ausflug mit einer Einschränkung”.
“Ein Nachbarschaftsfest planen” is the second actual planning exercise.
Do not substitute the book's later full-simulation sets for this selection.

Source models contain **110 + 195 + 255 = 560 whitespace-delimited words**
across 21 segments; the discussion reading has **361 words**. These are text
counts, not measured durations. Follow-up questions/answers and the reading are
outside those 21 manifest segments.

## Long-version storyboard

Title revised November 6: **ÖIF B2 Sprechen mit Lea und Samir**.
All three preparation headings explicitly name Teil 1, Teil 2 or Teil 3,
both visually and in their examiner narration.
Show a descriptor such as “3 Teile · Mit Lea und Samir”; identify the omission
in the video and description rather than calling this a complete uncut exam.

| Sequence | Planned content |
| --- | --- |
| Opening / preparation | Speak the displayed title, preparation introduction, Teil 1 task card, one reading abstract and Teil 3 task card. Keep each card visible throughout its measured narration, with direct word highlights and a brief pause. Do not film 20 minutes of waiting or use a misleading countdown. |
| Contact | Natural Lea/Samir exchange about learning German and preparing; both respond to each other. No two disconnected B1-style examiner interviews. |
| Teil 1 | Lea presents the first book model, then Samir asks the three supplied partner questions and Lea gives the supplied example answers. No examiner-led replacement interview. |
| Omission notice | “Samirs Präsentation und die Rückfragen dazu werden übersprungen.” A short, readable card; no second presentation or invented answer variant. |
| Teil 2 | Both react to the same reading, then discuss summer versus standard time, affected groups and European coordination. Preserve the ten book turns and extend the exchange naturally. |
| Teil 3 | Both organize the company outing, compare options and constraints, allocate responsibilities and reach a conditional decision. Preserve the ten book turns and expand genuine negotiation. |
| Ending | Brief examiner close, then the separate promotional final CTA. Do not invent grades, examiner deliberation or a pass result. |

**Planning envelope:** roughly 12-14 minutes including contact, cards and CTA,
with roughly 4-5 minutes for each shared dialogue. These are editorial targets,
not official prescribed video timings or audio measurements. The omitted
presentation should reduce the runtime, not be replaced with filler. Confirm
the actual duration only after recording, alignment and frame-clock checks.

**Adaptations to author and track explicitly:**

- Contact, examiner transitions, opening/ending and dialogue extensions are
  original video material, not quotations from the book. Preserve original
  segment IDs/text alongside any adapted wording and new segment IDs.
- Teil 2's final book turn is an unanswered question about whose needs to
  consider and how to assess them. Answer it and give the discussion a natural
  ending; agreement on every policy preference is unnecessary. Add meaningful
  examples, follow-up questions and reactions, not repeated speeches.
- Teil 3 concerns **32 people in Linz in September**, two colleagues requiring
  step-free access, and **€55/person** for travel/program. Preserve the provisional
  calculation: €800 bus + €640 program + €256 lunches = **€1,696**, or **€53/person**,
  against a **€1,760** group limit. Confirm access before choosing an option;
  survey/quotes by Wednesday, compare Thursday, book only after agreement.
- Treat venues, prices and accessibility as hypothetical planning, not verified
  travel offers. Treat the reading as a book-based practice stimulus, not news
  about a newly enacted time-change policy; verify any added current claims.
- *Zwischen zwei Wegen* by Nora Stein is the book's fictional presentation
  example. It is not the real workbook being promoted. Keep these distinct.

Show just one card headed **Kurzfassung des Lesetexts**:

> Helle Abende oder hellere Morgen? Familien, Berufstätige und
> Schichtarbeitende haben unterschiedliche Bedürfnisse. Eine gemeinsame
> europäische Lösung ist wichtig.

Show and voice **Den vollständigen Lesetext findest du im Buch.** The abstract
must not masquerade as the full 361-word stimulus. The examiner also voices
both task-preparation cards. These learning cards are separate from the exam
conversation; the original dialogue and source models remain unchanged.

## Under-three-minute social adaptation

Plan this alongside the master, not after rendering. Use the same spoken title
and add **“Kurzfassung”** visibly. Target **170-178 seconds**, enforce
`total_frames / fps < 180` including every card, pause and CTA. At 24 fps the
largest valid integer frame count is 4,319; it is a ceiling, not a target.

Provisional allocation: opening/labels 8 seconds; Teil 1 40; Teil 2 60;
Teil 3 60; final CTA 8 = **176 seconds**. Replace these estimates with measured
edit decisions before approval.

Select a coherent presentation excerpt plus one partner question/answer,
a balanced discussion excerpt, and a short planning negotiation with a clear
conditional outcome. Both dialogue participants must remain. Label shortened
sections honestly; the other candidate's solo presentation stays omitted here too.

Design natural, self-contained summary exchanges inside the long script so
the short cut can reuse master speech and frames without new 3D rendering.
Cut at complete speech/sentence boundaries, rebase measured word timing and
document source-to-output ranges. Do not accelerate voices, fake timestamps,
or cut away constraints in a way that changes the agreed outcome. If the
measured selection does not fit, revise the selection before production.

## Visuals, voices and promotion

Reuse suitable approved room/character assets, but verify B2 seating and camera
direction rather than importing a B1 task sequence. Lea and Samir converse
with each other; one examiner moderates and the second mostly observes.
Group thumbnails may separately pose all four smiling toward the camera.

Plan a shared native-frame source for **1920×1080 YouTube** and **1080×1920
social** composition; derive the short social edit from the approved master.
Check actual crop/framing and platform UI margins. Provide a separate
Instagram cover with essential title/flag/logo/faces inside the centered square;
crop checks do not certify every upload setting.

Retain the smaller, vertically centered YouTube book panel and portrait-safe
social promotion. Keep the correct combined-book cover and platform-specific
Amazon cue visible throughout. On the final CTA use one main cover, not a
duplicate sidebar: “Mehr Aufgaben und Modelldialoge im Buch”, with
“Amazon: Link in der Beschreibung” for YouTube or “Amazon: Link in der Bio”
for social. Reuse the approved licensed pointing-down cue where applicable.
Keep advertising/AI/independent-practice disclosures and credits in the posts,
not as the previously removed on-screen disclaimer block.

**Promotion confirmed November 5:** the user selected the displayed combined-v1
cover dated October 6, 2026, for the newer third-edition content, and supplied
`https://amzn.eu/d/06Ob92VW`. Its GET redirect reaches Amazon product
`B0GX37V8F5`; the destination returns 503, so product metadata was not verified.
The B1 link and standalone speaking cover remain excluded. No usable generated
selected recordings were found in the book's audio folders.

Propose the familiar Austrian candidate voices, explicitly recasting the
manifest's middle-aged dialogue voice IDs to the young Lea/Samir roles.
The manifest requests 0.90× playback; choose/review a natural B2 pace rather than
silently inheriting B1's 0.85×. Its Linux reference paths require Windows
resolution before use. Preserve reference recordings/transcripts and the
book manifest; do not claim that manifest entries are existing audio files.

Use measured word highlights, including the spoken opening. Review German
umlauts, number pronunciation, captions and natural Austrian speech.
Do not infer timestamps from word counts.

## Next implementation and acceptance gates

- Confirm the correct B2 promotion assets; approve the adapted long script and
  the coherent under-three-minute selection separately.
- Build one dedicated authored episode with explicit long/short contracts;
  preserve other episode duration guards. Create contact sheets for both
  layouts before expensive video rendering. The user has now requested a
  YouTube preview with voiced preparation/summary cards, not production.
- Measure speech/alignment, presentation and reaction limits, turn balance,
  total duration and short-cut feasibility before baking production scenes.
- Validate the encoded opening, captions/highlights, voiced task/summary cards,
  explicit full-reading book reference, omission notice, dialogue endings,
  arithmetic, frame boundaries, aspect ratios,
  crop-safe cover, persistent promotion and final CTA. Separate automated
  checks from visual inspection, human listening and approval.
- On generation, prepare content-matched YouTube/Instagram/TikTok drafts for
  the applicable versions, with source/adaptation and independent-practice
  disclosure. Obtain preview/production/publication approvals at their actual
  stages; planning is not publication approval.
- Keep original book files, B1 deliveries and the unrelated Nationalfeiertag
  episode unchanged. Keep old build snapshots; use a fresh revision for the
  content/audio change and reuse compatible raw recordings.
