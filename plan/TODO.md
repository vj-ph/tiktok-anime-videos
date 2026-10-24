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

TEF previews and historical build artifacts remain in the
`tiktok_anime_videos_tef` worktree independently of shared-code merges into main.
Leave running production jobs unchanged; keep heavy CPU builds sequential.

- [x] Separate language, exam metadata and pair/interview scene layout while retaining German defaults.
- [x] Add French TTS/alignment/localization, inline voice-reference text and language-aware cache/reuse checks.
- [x] Add a one-candidate interview layout, optional observer and single-candidate entrance planning.
- [x] Add the single TEF Canada Section A practice A1 script using the existing French voices and speaking-book cover.
- [x] Add independent per-turn ASR tooling and focused language/content/native-fixture checks; unit API checks use explicit mocks, not real French inference.
- [x] Prepare full-episode French posting drafts with disclosures and rig credits.
- [x] Synthesize and independently check real TEF A1 audio, French alignment and caption readability: 24 turns, 50 pages, minimum 1.8333 encoded seconds and maximum 19.84 characters/second. Seven numerical/homophonic ASR differences are explicitly reviewed; 12 low-confidence alignment tokens remain disclosed. No auditory listening is claimed.
- [x] Bake and verify the complete one-candidate entrance, full preview, encoded headers/eight-second card/six-second CTA and frozen delivery: `pilot_3d/builds/tef_canada_a1_preview_r2/`, 189.7917 seconds. All 50 pre-existing masters remain unchanged.
- [x] Add the commercially cleared A1 advertisement as a task stimulus, physical desk sheet and compact opening-question reference, plus the original French Compass wall plaque. All 182 Python regressions pass; r3 preserves every raw/prepared recording, word alignment, lip cue and dialogue timing.
- [x] Finish and inspect the separate r3 image/logo preview: `pilot_3d/builds/tef_canada_a1_preview_r3/`, 189.7917 seconds. Native desk/head/logo checks, actual decoded image/header/CTA boundaries and both movie decodes pass; all 52 earlier masters and 33 original sources remain unchanged. Audio and alignment are byte-identical to r2; existing ASR/alignment caveats remain.
- [x] Author the user-requested ten-turn A1 short excerpt, concrete Atelier informatique title, consistent Section A · Se renseigner header and explicit full-model book CTA. Keep the full episode and book intact; use separate short-excerpt posting drafts. Real-asset validation and 59 focused tests pass.
- [x] Independently check the short excerpt's speech/audio/captions: 86.5833 seconds / 2078 frames including entrance, reading pause and ending; 19 pages, min1.9167s and max19.5254CPS. Nine recordings are unchanged and the new closing matches independent ASR. The two inherited ASR spelling/numeral differences and four low-confidence question-mark tokens remain disclosed; no auditory certification is claimed.
- [x] Render and inspect `pilot_3d/builds/tef_canada_a1_short_preview_r1/pilot.mp4` and clean master: both exports 86.5833 seconds / 2078 frames, strictly below 90 seconds. Actual decoded picture boundaries, 25 fixed-header samples and ten title/instruction/CTA samples pass. Full-size title, ending, logo and contact sheets inspected; all 54 earlier masters and 33 original sources preserved. Preview only.
- [x] Generate only three enlarged-advertisement review frames and a before/after sheet in `pilot_3d/builds/tef_canada_a1_image_size_frames_r1/`: whole ad 608px wide, labelled notice close-up, and larger dialogue detail with visible candidate and unchanged subtitle pixels. All 56 masters preserved; no new TTS, Blender or full video. Shared pipeline/layout remains unchanged pending review.
- [x] Revise frame samples in `pilot_3d/builds/tef_canada_a1_image_size_frames_r2/`: retain the selected reading notice detail exactly; place the 608px dialogue notice below unchanged subtitles with a 24px gap, no thumbnail or portrait inset, and the original unobscured candidate face. Inspect both 720x1280 samples/comparison and verify exact face/header/subtitle pixels plus preservation of all 56 masters, earlier review files, frozen inputs and live Python sources. No video/audio or shared pipeline changes.
- [x] Make the lower reference smaller in `pilot_3d/builds/tef_canada_a1_image_size_frames_r3/`: 320px notice, left-aligned below unchanged subtitles, with 266px bottom and 288px right panel clearance. Retain the reading close-up; inspect frame, comparison and explicitly non-official clearance guide. Pixel/source/master preservation checks pass. Platform-specific preview remains required; no blanket safe-zone certification or full video/audio/shared-code changes.
- [x] Assess merge readiness on October 24, 2026: refreshed remote main remains an ancestor of the TEF branch; original checkout is clean and no renders are active. All 188 Python regressions pass, 33 original German source hashes are unchanged, and five German episode plans match main on identical synthetic clocks. No merge performed.
- [x] Integrate the user-selected large reading detail and 320px lower reference into the live compositor, both TEF episodes and actual encoded layout tests. All 192 Python regressions, both episode validations and the native interview fixture pass. Inspect two current-compositor frames under `pilot_3d/builds/tef_canada_a1_live_layout_check_20261024/` using frozen backgrounds and unchanged real speech timing; this is not a newly rendered full video. Keep normal subtitle bounds/fonts and German defaults; stage intended TEF source/docs/tests, short episode/posts and image/logo/provenance, not ignored generated artifacts.
- [ ] Listen to the real French speech and approve the TEF A1 preview, including pronunciation and accent.
- [ ] Obtain preview approval before production rendering; publication remains separately approved.
- [x] Complete pre-merge review with no active DTZ renders; compare five German episode plans against main on identical synthetic clocks. Existing previews remain frozen; use fresh builds under changed source hashes.
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
| TEF Canada: Section A, pratique A1 | `pilot_3d/builds/tef_canada_a1_preview_r3/pilot.mp4` - image/logo preview only, in the isolated TEF worktree | `posts/tef_canada_a1/` |
| TEF Canada: Atelier informatique, short A1 excerpt | `pilot_3d/builds/tef_canada_a1_short_preview_r1/pilot.mp4` - 1:26.58, preview only, in the isolated TEF worktree | `posts/tef_canada_a1_short/` |

Each caption folder contains `tiktok.txt` and `instagram.txt`.
No publication dates, published-post status or performance results have been confirmed here yet.
