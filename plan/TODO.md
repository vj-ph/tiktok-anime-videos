# Publication TODO

Status recorded: October 22, 2026. Paths below are relative to the repository root.

## Agreed publishing approach

- Publish full practice episodes on TikTok and Instagram, not short promotional cuts.
- Start with manual uploads; Buffer scheduling has been discussed but is not connected here.
- Keep the book CTA, independent-practice disclaimer, AI disclosure and complete character credits.

## Already prepared

- [x] Complete the Ausflug production video.
- [x] Generate the full Lerntreffen preview.
- [x] Generate and quality-check the full Teil 1 preview, including both candidates' introductions and examiner follow-ups.
- [x] Generate and quality-check the full Teil 2 preview, with separate pictures, descriptions and personal-experience follow-ups for both candidates.
- [x] Prepare TikTok captions for all four episodes.
- [x] Prepare Instagram captions for all four episodes.

## Extend DTZ speaking coverage

Ausflug and Lerntreffen cover Teil 3, jointly planning something.
The new Teil 1 format covers introductions and linked examiner follow-ups for both candidates.
Teil 2 now covers picture descriptions and linked personal-experience interviews
for both candidates, using the book's weekly-market and supermarket pictures:

- [x] Create a Teil 1 practice-video format using the existing exam room and characters: examiner invitation, candidate introduction, examiner follow-up and candidate response.
- [x] Cover Teil 1A, introducing oneself: background, birthplace, residence, work, family and languages.
- [x] Cover Teil 1B, answering examiner follow-up questions connected to the introduction, with natural model responses rather than only a prepared monologue.
- [x] Create a Teil 2 practice-video format with a clearly readable photograph, candidate description and examiner-led discussion of related personal experiences.
- [x] Cover Teil 2A, describing the photograph and the situation it shows; use an original or appropriately licensed image rather than copying an official exam picture. The user confirmed promotional reuse rights for the two book images.
- [x] Cover Teil 2B, discussing personal experiences and answering related follow-up questions, including explanations or comparisons where appropriate. Do not end the episode after the picture description.
- [ ] Adapt the new scripts from the speaking book, review a full preview of each new format, and prepare production videos and matching TikTok/Instagram captions after approval.
- [x] Prepare the book-based Teil 1 script and full-episode TikTok/Instagram caption drafts; production and publication remain pending.
- [x] Prepare the book-based Teil 2 script and full-episode TikTok/Instagram caption drafts, with image attribution and complete disclosures; production and publication remain pending.
- [ ] Review and approve the full Teil 1 preview, then render and quality-check its production video with unchanged speech and timing.
- [ ] Review and approve the full Teil 2 preview, then render and quality-check its production video with unchanged speech and timing.

## Publication tasks

- [ ] Confirm whether Ausflug has already been published manually; record each platform's publication date and post link.
- [ ] Review and approve the Lerntreffen preview.
- [ ] Render and quality-check the Lerntreffen production video, preserving the approved audio and timing.
- [ ] Create a prioritized queue of further book-based practice topics covering Teil 1, Teil 2 and Teil 3, not only planning dialogues.
- [ ] Choose a release cadence, target publication times and an explicit timezone.
- [ ] Create a dated publication calendar with the episode, platform, video path, caption path, scheduled date/time, status and published link.
- [ ] Publish Ausflug on any outstanding platform and publish Lerntreffen after production approval, using the prepared platform-specific captions.
- [ ] Record available performance results and review them to guide the next topics and publishing cadence.

## Flexible generator and TEF Canada

Development is isolated on `feat/multilingual-tef` in the
`tiktok_anime_videos_tef` worktree. Leave the original DTZ checkout and running
production jobs unchanged; do not merge or launch competing heavy work yet.

- [x] Separate language, exam metadata and pair/interview scene layout while retaining German defaults.
- [x] Add French TTS/alignment/localization, inline voice-reference text and language-aware cache/reuse checks.
- [x] Add a one-candidate interview layout, optional observer and single-candidate entrance planning.
- [x] Add the single TEF Canada Section A practice A1 script using the existing French voices and speaking-book cover.
- [x] Add independent per-turn ASR tooling and focused language/content/native-fixture checks; unit API checks use explicit mocks, not real French inference.
- [x] Prepare full-episode French posting drafts with disclosures and rig credits.
- [ ] After current DTZ jobs finish, synthesize and independently check the first real TEF A1 audio, alignment and caption readability.
- [ ] Bake and review the complete TEF entrance, full preview, encoded headers/CTA and frozen delivery.
- [ ] Obtain preview approval before production rendering; publication remains separately approved.
- [ ] Review and merge only after DTZ jobs finish; use fresh builds under changed source hashes.
- [ ] Add a TEF Section B persuasion practice and its own content tests.
- [ ] Add reviewed ÖIF/fide and TCF IRN speaking configurations.
- [ ] Design and implement explicit DTZ/ÖIF/fide listening templates, including learner response time and answer reveal; listening is not implemented by relabelling a speaking episode.

## Before each publication

- [ ] Use the approved production master, not a preview or internal acting diagnostic.
- [ ] Review the full video and captions in the platform's mobile preview.
- [ ] Confirm that the correct Amazon book link is available in the profile.
- [ ] Preserve the prepared advertising, independent-practice and AI disclosures, plus all Snow/Rain and CC BY 4.0 credits; apply the platform's disclosure controls as appropriate.

## Later: scheduling

- [ ] Decide when to move from manual uploads to Buffer scheduling.
- [ ] If adopting Buffer, connect the intended accounts and verify a reviewed post before relying on the scheduled queue.

## Current assets

| Episode | Video | Caption folder |
| --- | --- | --- |
| Ausflug | `pilot_3d/builds/v6_hold12_cta6_production/pilot.mp4` - production | `posts/dtz_b1_ausflug/` |
| Lerntreffen | `pilot_3d/builds/lerntreffen_v7_preview_r1/pilot.mp4` - preview only | `posts/dtz_b1_lerntreffen/` |
| Teil 1: Vorstellung und Nachfragen | `pilot_3d/builds/teil1_vorstellung_v7_preview_r2/pilot.mp4` - preview only | `posts/dtz_b1_teil1_vorstellung/` |
| Teil 2: Bildbeschreibung und Erfahrungen beim Einkaufen | `pilot_3d/builds/teil2_einkaufen_v7_preview_r2/pilot.mp4` - preview only | `posts/dtz_b1_teil2_einkaufen/` |

Each caption folder contains `tiktok.txt` and `instagram.txt`.
No publication dates, published-post status or performance results have been confirmed here yet.
