# Publication TODO

Status recorded: October 26, 2026. Paths below are relative to the repository root.

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

## Nationalfeiertag: playful ÖIF B2 episode

User-selected scope: 100-120-second target, script and visual design first.
See [the draft](oeif_b2_nationalfeiertag.md). This is an explicitly requested
short comedy/practice adaptation, not a change to the full-practice default.

- [x] Draft a history/comedy introduction, linked book-based holiday discussion and book CTA, with the requested Austrian reference-voice casting. Record the selected flags, Samir's hat, examiner's coffee set and stationary backpack; no strudel. Document an opt-in reusable dressing implementation.
- [x] Obtain approval for free-first flags, hat, coffee set and backpack implementation and a few checked review frames; no strudel, paid asset, full render or publication.
- [x] Implement opt-in `scene.dressing`, pinned CC0 cup/saucer and backpack assets, procedural flags/hat/glass, native head attachment and hat-aware close-up framing. Wire validation, asset/source hashes, frozen copies and native checks without changing default episodes or runtime tooling.
- [x] Render and inspect six 720x1280 prop-review stills plus real caption overlays and a contact sheet in `pilot_3d/builds/austrian_props_review_r8/`. Check head tracking, doorway clearance, caption-safe hat framing, table/floor and cup/saucer contact, hands/routes and packed assets. Verify all 50 prior video masters unchanged. Broad regressions: 250 pass, three skip; one pre-existing Linux/Python-3.12 Windows-tool mock failure is recorded/excluded, not fixed or claimed passing.
- [x] Address placement feedback in `pilot_3d/builds/austrian_props_review_r10/`: drinks nearer the examiner, a lower fitted hat with owner-local upper-hair compression and all-pose crown clearance checks, and an annotated backpack in the real entrance shot. Preserve prior reviews, distinguish actual timeline shots from review-only views, and recheck native contact/clearance plus 75 focused regressions.
- [x] Verify each selected Austrian WAV independently and create matching 4.245/4.3/4.86-second PCM16 excerpts with exact reference text and source/crop/ASR provenance. Preserve shared originals and the misspelled original filename; do not rely on the stale voice manifest. ASR agreement is not auditory/accent certification.
- [x] Author the approved 13-turn comedy-to-discussion episode, book coverage, B2 cover, original reading summary and CTA. Keep the first five turns in the technical welcome phase and one later instruction/card. Episode validation and 81 focused regressions pass.
- [x] Check real Qwen3-TTS 1.7B audio in `pilot_3d/builds/oeif_b2_nationalfeiertag_v7_preview_r2/`: 100.833333 seconds, 2420 frames, all 13 turns match independent German ASR, and all 24 subtitle pages pass at minimum 1.916667 encoded seconds / maximum 19.948052 encoded CPS. Two clearer-wording revisions reuse the other 11 raw recordings exactly. Retain seven alignment warnings and human listening/accent review; the first take and its disagreements remain unchanged.
- [x] Catch and correct the second run's opening-pose hair/hat collision before rendering. Fit in unposed head coordinates and measure seating in hat-local coordinates without changing hat size or brim depth. Add `--tilted-fit` to the native fixture: `pilot_3d/builds/austrian_props_tilted_fit_r11/` passes 326 head/hair samples, five doorway samples and 30 caption-clear portraits; 81 focused tests pass. Preserve the failed build and start `oeif_b2_nationalfeiertag_v7_preview_r3` with all 13 verified recordings reused.
- [x] Generate and check the complete preview in `pilot_3d/builds/oeif_b2_nationalfeiertag_v7_preview_r3/`: both 100.833333-second / 2420-frame movies decode, all 13 turns match independent German ASR and all 24 caption pages meet the reading limits. Native checks pass 1210 head/hair poses, five doorway crossings and 249 caption-clear portraits (minimum crown clearance 1.505 mm). Check 27 actual encoded header/card/CTA samples, the correct B2 cover and all frozen file/source hashes. Inspect final full-size props, reading/ending frames and contact sheets. Preserve all 51 prior masters, the book and shared voice originals; prepare full posting drafts. Evidence: `episode_qa.json`, `delivery_checks.json` and `episode_review/`.
- [x] Listen to the Austrian speech for pronunciation/accent and review the seven disclosed forced-alignment warnings; independent ASR does not replace listening. Marked complete per user confirmation on October 26, 2026.
- [x] Approve the Nationalfeiertag preview before requesting a separate production render with unchanged approved speech/timing. Publication and platform/mobile placement review remain separate; posting copy is draft only. Marked complete per user confirmation on October 26, 2026; this does not separately claim publication approval.
- [x] Add the user-requested exam-prefixed main title `ÖIF B2: Neutral? Nicht bei Feiertagen!` to the authored episode, visible opening hook and posting drafts. Require exam name/level in the practice-video skill and add focused title assertions. Keep the frozen r3 preview unchanged; provide the revised-JSON production command with exact r3 audio reuse without starting another render.

## Publication tasks

Items marked closed at the user's request on October 26, 2026 were not independently verified; closure alone does not establish production, publication or approval.

- [x] Record the [seasonal publication proposal for 2026-2027](seasonal_publication_plan_2026_2027.md), including all ten suggested occasions plus Halloween as the recommended next topic. Distinguish verified event dates from proposed release windows and unconfirmed publication status.
- [ ] Select a real book exercise and script scope for `DTZ B1: Süßes oder Prüfungsangst?`; proposed release window October 29-30, 2026, ahead of Halloween on October 31. Keep `ÖIF B2: Halloween – Tradition oder Kommerz?` as an alternative, not a second approved production. No Halloween script, props, media or posting drafts have been generated.
- [x] Confirm whether Ausflug has already been published manually; record each platform's publication date and post link. Marked complete per user confirmation on October 26, 2026; platform dates and links were not supplied in this conversation.
- [x] Review and approve the Lerntreffen preview. Closed at user request.
- [x] Render and quality-check the Lerntreffen production video, preserving the approved audio and timing. Closed at user request.
- [x] Create a prioritized queue of further book-based practice topics covering Teil 1, Teil 2 and Teil 3, not only planning dialogues. Closed at user request.
- [ ] Choose a release cadence, target publication times and an explicit timezone.
- [x] Create a dated seasonal editorial proposal with event dates, publication windows, target exam/audience, priorities and tracking fields; see the linked plan. Windows are proposals, not scheduled uploads.
- [ ] Turn selected rows into a confirmed upload calendar with actual approved master/caption paths, exact date/time and timezone, platform status and published links. Leave unknown values unconfirmed.
- [x] Publish Ausflug on any outstanding platform and publish Lerntreffen after production approval, using the prepared platform-specific captions. Closed at user request; publication dates and links were not supplied.
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
- [x] Listen to the real French speech and approve the TEF A1 preview, including pronunciation and accent. Closed at user request on October 26, 2026; not independently verified.
- [x] Obtain TEF A1 preview approval before production rendering. Closed at user request on October 26, 2026; approval was not independently verified. Production still requires confirmed preview approval, and publication requires separate approval.
- [x] Complete pre-merge review with no active DTZ renders; compare five German episode plans against main on identical synthetic clocks. Existing previews remain frozen; use fresh builds under changed source hashes.
- [x] Author TEF Section B practice B1 (vegetarian cooking workshop) as a nine-turn short excerpt with the original book ad, skeptical friend, price/tutorial and lunch-conflict objections, tailored concessions, book CTA and separate posting drafts. Add portable content, provenance, caption/layout, strict-duration and French/German prompt-isolation tests to both-platform CI. Real-asset validation and 81 focused tests pass.
- [x] Generate and independently check Section B B1 speech, French alignment, caption readability and measured total duration: 72.833333 seconds / 1748 frames, strictly below 90 including entrance, reading pause and CTA. All 15 pages pass (minimum 2.375 encoded seconds, maximum 19.5693 CPS). Small-model ASR matches 6/9 strictly; medium-model review supports the closing imperative and confirms two numeral-formatting differences. Raw mismatch flags and two low-confidence alignment words remain disclosed; no auditory certification is claimed.
- [x] Render and inspect `pilot_3d/builds/tef_canada_b1_short_windows_preview_r1/` on October 26, 2026: 874 native preview poses, four HIP workers, no recovery retry. Both 720x1280 masters fully decode at 72.833333 seconds / 1748 frames; native scene checks, eight encoded advertisement-boundary checks and all frozen delivery/source hashes pass. Inspect contact sheet and full-size reading/compact-ad/CTA frames; preserve five earlier masters and all 50 Python sources. Preview only.
- [x] Listen to and approve Section B B1 pronunciation/accent and the completed rendered preview before any production run; publication remains separately approved. Closed at user request on October 26, 2026; not independently verified.
- [x] Add opt-in Canadian room decor to TEF Canada Section A/B configurations: original 2:1 wall/desk flag geometry with pinned Wikimedia PNG/SVG artwork, separate provenance and packed offline texture. All 51 focused tests, real B1 asset validation, full native placement checks and three one-pose distortion/UV/texture rejection regressions pass. Inspect three actual-camera captioned before/after views and a labelled inspection-only flag detail in `pilot_3d/builds/tef_canada_b1_canada_decor_review_r2/`; the whole wall flag fits above the candidate header, with Austrian placement unchanged. Preserve seven earlier movies, 116 frozen files and byte-identical 72.833333-second audio/timeline/alignment. Review stills only; the earlier full B1 preview remains unchanged and no decorated full movie has been exported.
- [ ] Add reviewed ÖIF/fide and TCF IRN speaking configurations.
- [ ] Design and implement explicit DTZ/ÖIF/fide listening templates, including learner response time and answer reveal; listening is not implemented by relabelling a speaking episode.

## Development workflow

- [x] Create the project-local `pilot-3d-dev` skill at `.github/skills/pilot-3d-dev/SKILL.md`, covering implementation entry points, build/audio preservation, focused validation and persistent task tracking in this file rather than only a session-internal list.

## Video generation runtime

- [x] Add bounded recovery for the Windows HIP production crash without invalidating the existing build: `resume_pipeline.py` verifies original source/stage/frame receipts, starts with two workers, retries only fresh recognized HIP frame-stage crashes at lower concurrency (default 2/1/1), archives logs and preserves saved frames. No silent CPU fallback, quality changes, hash bypass or unlimited retries. All 291 saved production PNGs decode; 35 focused mocked recovery/runtime tests pass. No video generation was rerun at the user's request.
- [x] Verify sustained completion using the HIP recovery entry point when the user reruns the production build. Marked complete per user confirmation on October 26, 2026, without a new independent artifact check. The earlier four-worker throughput benchmark did not prove long-run stability; the exact crash trigger and a driver-level fix remain unconfirmed.
- [x] Attempt production benchmarking with 2, 4 and 8 HIP workers on the genuine 720x1280/16-sample/per-frame bake of the 10-turn TEF short excerpt. Its measured timeline is 86.583333 seconds, strictly below 90; the authored cap is now enforced before baking. Two reversed-order 24-frame trials measured 7.36/9.47 median warm frames/min for 2/4 workers. Both 8-worker attempts hit the 4 GiB free-RAM reserve and were safely stopped, so eight remains unverified, not recommended. All 96 successful PNGs and original delivery/preview hashes verify. Reports, measured-code snapshots and the overlapping-GPU-counter caveat are in `pilot_3d/builds/tef_canada_a1_short_production_worker_benchmark_r1/`; defaults are unchanged.
- [x] Benchmark the requested Qwen TTS CPU synthesis with 2, 4 and 8 intra-operation threads, one speech worker and four fixed inter-operation threads. Six fresh processes (2/4/8, then 8/4/2) generated identical 6/19/25-word French excerpts and voices with no speech-cache hits, separating model loading, voice-prompt setup, warmup and measured synthesis. Median synthesis times for 17.760 seconds of audio were 152.23/143.55/136.63 seconds; eight threads had about 5.1% higher throughput than four. All 24 WAVs validate; measured waveforms differ by at most one PCM16 step, without a new listening/pronunciation certification. Timings, memory samples, WAV hashes and measured-source snapshots are in `pilot_3d/builds/tef_canada_a1_qwen_cpu_threads_benchmark_r1/`. Existing deliveries and production source hashes were verified unchanged at benchmark completion, before the subsequent default update below.
- [x] Adopt eight intra-operation threads for Qwen CPU synthesis in both the pipeline and standalone audio CLI, retaining four inter-operation threads. Keep Rhubarb independently at four threads with `--rhubarb-threads`, and leave Blender settings unchanged. CLI default/override/validation and pipeline-forwarding regressions pass; the portable suite ran 175 tests (174 passed, one opt-in GPU smoke skipped). Preserve existing audio/scenes and hash guards: the code update requires a fresh build directory, not a forced resume of the earlier prepared four-thread TEF build.
- [x] Extend the controlled Qwen CPU thread comparison to one intra-operation thread, then evaluate multiple speech workers separately. Keep model/voices/text/settings fixed, bypass speech-cache hits, separate startup/prompt/warmup from synthesis, repeat trials, and compare speed, memory and speech quality without altering existing deliveries. Marked complete per user confirmation on October 26, 2026; no additional benchmark results were supplied or measured here. The ordinary two-thread CLI uses two inter-operation threads; its native policy was not covered by the earlier fixed-four-inter-op comparison.
- [x] Benchmark 1, 2 and 4 HIP render workers on identical representative frames with unchanged preview settings and CPU threads per worker. Two 48-frame trials per configuration measured median warm throughput of 27.47/45.95/67.03 frames per minute; four workers are fastest for this preview workload. All 288 PNGs decode and closely match the original frames; original delivery/source hashes verify. Startup, CPU/GPU/memory, measured-code snapshots and output hashes are recorded in `pilot_3d/builds/tef_canada_a1_worker_benchmark_r1/`. GPU process-counter sums are raw activity indices, not physical utilization; see the production benchmark caveat. 16/32 workers remain unsupported and untested.
- [x] On Windows while plugged into AC power, prevent automatic compute sleep during video generation while allowing the display to turn off. Scoped system/execution requests track AC/battery transitions, release on completion/failure/cancellation, and leave permanent settings untouched. Native request-handle and execution-state tests verify acquisition/release with no display-required flag; mocked tests cover battery transitions and terminal outcomes.
- [x] Add optional ntfy notifications for generation start, stage completion, render milestones, completion, failure and cancellation. External server/topic/token settings, fixed generic messages, bounded daemon delivery and throttled milestones are implemented across the generation entry points. Local HTTP/error/blocked-delivery, lifecycle and throttling tests pass; setup is documented. No external notification service is configured.

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
| ÖIF B2: Neutral? Nicht bei Feiertagen! | `pilot_3d/builds/oeif_b2_nationalfeiertag_v7_preview_r3/pilot.mp4` - 1:40.83, preview only | `posts/oeif_b2_nationalfeiertag/` |
| TEF Canada: Section A, pratique A1 | `pilot_3d/builds/tef_canada_a1_preview_r3/pilot.mp4` - image/logo preview only, in the isolated TEF worktree | `posts/tef_canada_a1/` |
| TEF Canada: Atelier informatique, short A1 excerpt | `pilot_3d/builds/tef_canada_a1_short_preview_r1/pilot.mp4` - 1:26.58, preview only, in the isolated TEF worktree | `posts/tef_canada_a1_short/` |

Each caption folder contains `tiktok.txt` and `instagram.txt`.
No publication dates, published-post status or performance results have been confirmed here yet.
