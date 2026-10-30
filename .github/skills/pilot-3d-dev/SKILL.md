---
name: pilot-3d-dev
description: Develop, debug, test and maintain the pilot_3d exam-practice video generator, including episode configuration, Qwen speech, WhisperX alignment, Blender scenes/rendering, captions, runtime controls and delivery checks. Use for pilot_3d development and its TODO tracking.
---

# pilot_3d Development

Maintain the existing episode-driven generator without disrupting running jobs,
frozen deliveries or approved speech and timing. Paths below are relative to the
repository root unless a command explicitly changes directory.

## Start with the current repository

- Read `pilot_3d/README.md`, the relevant implementation/tests and
  `plan/TODO.md`. Read `pilot_3d/MIGRATION.md` for platform/runtime changes.
- Check the worktree before editing. Integrate existing edits and do not revert
  unrelated work. Inspect current files rather than assuming a previously
  discussed feature is still missing.
- Use `pilot_3d/pipeline.py` for new episode-driven work. Preserve standalone
  entry points when changing shared behavior.

## Persistent TODO tracking

**Write project TODOs to `plan/TODO.md`, not only a session-internal todo list.**

- When asked to add or remember development work, update that repository file
  in the same task. A session list may supplement it, but never replace it.
- Read the relevant section first; update matching items rather than duplicating
  them. Keep existing entries and their status.
- Use `- [ ]` for pending work and `- [x]` only for completed, verified work.
  Include the expected behavior and meaningful acceptance checks.
- Group tasks under the existing relevant heading; add a heading only when
  needed. Do not mark an implementation complete merely because it was planned.
- Report the file updated. Do not commit unless requested.

## Implementation map

| Area | Start here |
| --- | --- |
| Orchestration, checkpoints, frozen source exports | `pilot_3d/pipeline.py` |
| Episode schema, language and exam profiles | `pilot_3d/episode_config.py`, `pilot_3d/episode_profiles.py`, `pilot_3d/episodes/` |
| Speech synthesis, caching and measured timelines | `pilot_3d/prepare_audio.py` |
| Forced word alignment and independent ASR checks | `pilot_3d/align_words.py`, `pilot_3d/check_speech.py` |
| Scenes, rigs and animation | `pilot_3d/build_scene.py`, `pilot_3d/studio_characters.py`, `pilot_3d/scene_direction.py`, `pilot_3d/entrance.py` |
| Rendering and exports | `pilot_3d/render.py`, `pilot_3d/produce_v4.py` |
| Captions, pictures and delivery review | `pilot_3d/social_captions.py`, `pilot_3d/picture_presentation.py`, `pilot_3d/review_social.py`, `pilot_3d/check_v4_scene.py` |
| Paths, tools, runtime lifecycle and benchmarking | `pilot_3d/build_paths.py`, `pilot_3d/runtime_config.py`, `pilot_3d/generation_runtime.py`, `pilot_3d/benchmark_workers.py`, `pilot_3d/resource_metrics.py` |

Trace the affected path end-to-end before editing. Update directly related tests
and documentation; keep changes focused.

For TEF Canada videos, also follow `.github/skills/tef-canada-video-gen/SKILL.md`,
including its Québec French listening-voice casting requirements.

## Spoken opening title

- For every future video, including previews and production, use TTS to speak
  the displayed title at the start. This applies to speaking and listening
  exercises alike, including titles phrased as questions.
- Display the spoken title like a subtitle and highlight each word in sync
  with its measured forced-alignment timing. Preserve the intended readable
  title when abbreviations or numbers are spoken differently; map them only
  to their actual aligned speech, never to estimated timestamps.
- Fit the complete narration into the opening without truncating, speeding up
  or overlapping other speech. Include it in the strict duration limit.
  Verify the encoded opening, highlighted word boundaries, speech and
  readability; independent ASR does not replace human listening.
- For existing approved or frozen videos, create a fresh preview rather than
  altering their audio or delivery. Obtain separate preview and publication
  approval as usual.

## Posts for every video

- For every video, including a preview, prepare exercise-specific TikTok and
  Instagram post drafts in `posts/<episode>/tiktok.txt` and `instagram.txt`.
  A generic caption inside a build directory is not a substitute.
- Match the video's content and language, include the book CTA, advertising
  and AI disclosures, independent-practice disclaimer and applicable asset
  credits. Verify any required third-party attribution before publication.
- Update the drafts when the video content changes, preserving existing
  approved materials. Treat drafts, preview approval and publication approval
  as separate; never publish without explicit approval.

## DTZ listening book

- The user has confirmed that the content and audio in
  `../german_exam_books/b1/listening_dtz_v2/` may be used to create videos.
  Preserve the originals and record the source of reused material.
- Check any separately sourced third-party components, such as sound effects,
  for the intended use and required attribution.
- Open listening videos by speaking the displayed title or question; do not
  leave the opening hook silent. Measure the narration and fit it into the
  actual hook without truncation or speeding it up.
- Set the pre-listening reading countdown to five seconds for every DTZ
  listening section; keep the response countdown separate. Viewers can pause
  to read. Generate a fresh preview for timing changes and verify its encoded
  countdown boundaries.
- Show numbered answers with digits (for example, 10 and 11) and present each
  answer once in the reveal. Do not duplicate the answer list by also
  displaying a verbatim copy of the spoken explanation. Keep narration clear
  and aligned with the visible solution.
- Verify the rendered opening, answer display and audio placement, not merely
  the script. Keep human listening and preview approval separate from
  automated checks.

## 3D objects

- Reuse suitable existing assets. If an object is missing, search online for a
  suitable 3D asset before drawing or modeling it from scratch.
- Check compatibility and commercial-use licensing, and record source,
  license and any required attribution. Create the object only if a suitable,
  appropriately licensed asset cannot be found.

## Video duration

- Preview and production videos must be **strictly shorter than 1 minute
  30 seconds (90 seconds)**. Exactly 90 seconds is not acceptable.
- The limit includes the entire video: intro, entrance, speech, reading pauses,
  transitions, outro and book CTA.
- Select a suitably short episode before generation. For TEF Canada, use
  `pilot_3d/episodes/tef_canada_a1_short.json`, not the full 24-turn episode.
  Preview quality changes rendering settings, not script duration.
- Set `source.duration_limit_seconds: 90` in the episode and verify the measured
  encoded frame clock (`total_frames / fps < 90`) before scene baking/rendering.
  Confirm the final exported video's duration too. Do not rely on an older
  run's timing or silently relax the limit or accelerate speech to fit.

## Build and compatibility invariants

- Keep authored episodes/assets separate from ignored generated runs under
  `pilot_3d/builds/`. Never use `builds/` itself as an individual run.
- Preserve existing deliveries, frozen manifests, source snapshots, cached
  recordings and saved scenes. Do not rewrite historical paths or hashes.
- For disk cleanup, use `pilot_3d/cleanup_builds.py` to inventory first.
  Remove rendered frames only from explicitly approved completed runs, after
  explaining that resume and frame-level verification may require rerendering.
  Review the bulk dry-run plan and token before applying it. Never prune active
  runs or delete entire builds automatically.
- Use a fresh, dedicated build directory when content, assets, code or quality
  changes. Resume only matching checkpoints; never bypass hash guards.
- Use `--reuse-audio` only for exact reuse from a verified delivery, with
  unchanged speech/timing. Use `--speech-cache-from` for compatible raw speech
  reuse when rebuilding timing or visuals. Consult the current CLI/docs.
- Keep language, exam identity and scene layout separate. Preserve German/pair
  defaults when adding French/interview behavior.
- Do not approximate missing word timestamps or silently change transcript
  words. Keep alignment confidence, validation and provenance checks.
- CPU speech and CPU rendering are independent defaults. Select accelerators
  explicitly and verify availability; do not assume GPU/NPU compatibility.
- Qwen CPU synthesis defaults to eight intra-operation and four inter-operation
  threads. Keep Rhubarb's four-thread default and Blender settings independent;
  standalone `--threads` selects Qwen threads, `--rhubarb-threads` selects lip-sync
  analysis threads.
- Keep native Windows and Linux/WSL behavior working. Resolve tools/fonts
  through existing helpers and use the appropriate platform path conventions.
- If changing frozen source dependencies, inspect `pipeline.py`'s `SOURCES`,
  snapshot/hash generation and corresponding checkpoint tests.
- Preserve scoped AC-only Windows compute-sleep prevention without forcing
  the display on or changing permanent power settings.
- Keep ntfy optional, externally configured, generic and best-effort. Do not
  include episode content, paths, credentials or exception details in messages.
  Preserve owned-process cancellation and bounded notification shutdown.

## Validation

Run the smallest existing test selection covering the change, then broaden only
when needed. Inspect `.github/workflows/portability.yml` for the current portable
test selection. Do not install dependencies unless required by manifest changes
or a missing-dependency failure.

Example PowerShell commands from the repository root:

```powershell
Set-Location pilot_3d
.\.venv\Scripts\python.exe -X utf8 -m unittest test_audio test_render
.\.venv\Scripts\python.exe -X utf8 -m unittest test_runtime test_generation_runtime test_benchmark_workers
.\.venv\Scripts\python.exe pipeline.py validate --episode episodes\tef_canada_a1_short.json
```

Choose relevant modules rather than always running both example suites.
Use the configured interpreter on Linux/WSL; do not copy Windows paths there.
Episode validation needs the documented local assets and runtime dependencies.

- Distinguish mocked unit tests, real model inference, native Blender checks,
  encoded-frame checks, visual inspection and auditory review in reports.
- For timing/layout changes, test exact frame boundaries, dimensions, word
  coverage and caption limits, not just successful process exit.
- Prefer tiny native fixtures or representative frames to a full render.
  Run heavyweight inference, downloads, benchmarks or full preview/production
  only when needed for the requested outcome; do not disrupt running jobs.
- Production rendering requires preview approval; publication is separately
  approved. Never treat a preview or diagnostic as a production delivery.
- Report what changed, commands/checks run and any unverified behavior honestly.
  Update matching `plan/TODO.md` items only when acceptance checks are satisfied.
