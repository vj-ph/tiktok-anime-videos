# DTZ speaking: reusable 3D pilot

## Project and build layout

Keep Python scripts, episode JSON, assets and tools separate from generated runs:

```text
pilot_3d/
  episodes/                         Authored episode scripts
  assets/                           Covers, logo and character sources
  .tools/                           Downloaded Blender and Rhubarb
  builds/                           Generated files; ignored by Git
    pilot_v1/                       Original pilot
    v2/                             Reusable base scene and original V2 delivery
    v6_hold12_cta6_production/       Approved full Ausflug production
    v7_acting_test/                 Internal acting diagnostic
    lerntreffen_v7_preview/         First audio-only take
    lerntreffen_v7_preview_r1/      Complete Lerntreffen preview
    teil1_vorstellung_v7_preview/   First Teil 1 audio take
    teil1_vorstellung_v7_preview_r1/ Original full Teil 1 native render
    teil1_vorstellung_v7_preview_r2/ Delivered full-rate caption correction
```

Each run keeps its audio, alignment, frames, scene, exports, logs and frozen
manifests together. Existing runs were moved, not regenerated or deleted.
There are no compatibility symlinks cluttering the project directory.
Use explicit `builds/RUN` paths in commands. A project-level output name such as
`--build new_preview` also goes to `builds/new_preview`; the old output spelling
`--build build_new_preview` maps to the same location. Explicit nested or
external output paths retain their existing meaning. Never use `builds/` itself
as an individual run.

Frozen episode/timeline/receipt files retain their original bytes and hashes,
including embedded absolute paths. Current tools resolve missing old
`pilot_3d/build_NAME/...` references to `pilot_3d/builds/NAME/...`, and old
`pilot_3d/build/...` references to `pilot_3d/builds/pilot_v1/...`, only when the
relocated file exists. This supports saved scenes, review and verified speech
reuse without rewriting delivery records. External tools such as Blender still
need the new physical path on their command line. Frozen `.blend` files also
retain their old saved render-output path: override it with Blender's `-o`
option when rendering directly. The pipeline already sets the correct output
path for every render worker.

The normal source-code hash guard still applies: this tooling change does not
make pre-change pipeline checkpoints resumable under changed code. Keep those
deliveries frozen; create a new run for new work, reusing verified audio where
appropriate. No production render is started by organizing the directories.

## Episode-driven production

Use **`pipeline.py`** for new videos. It accepts a JSON episode at any path,
including outside this project, without editing Python or replacing
`episode_v4.json`. The current scene template is the existing exam room with
two candidate slots, one speaking examiner and one observing examiner.
Content is configurable; a different cast, location or arbitrary cinematic
plot still needs another animation template. Speech and alignment currently
support German.

```bash
cd /home/ronggong/lang/german/tiktok_anime_videos/pilot_3d

# Validate content, reference files, tools, static text and cover geometry.
python3 pipeline.py validate --episode episodes/lerntreff.json

# Produce the full practice video.
python3 pipeline.py build \
  --episode episodes/lerntreff.json \
  --build builds/lerntreff \
  --profile preview --jobs 4
```

The entry point automatically uses the existing Qwen Python environment.
Override it with `--qwen-python /absolute/path/to/python` or `QWEN_PYTHON`.
It does not use Ollama. All model inference, alignment and rendering stay local.
The selected episode is saved as an immutable, asset-resolved
`BUILD/episode.json`; commands use that snapshot throughout the build.
Output is `BUILD/pilot.mp4` and `BUILD/pilot_clean.mp4`, plus the
`BUILD_promo/` pair when `--promo` is requested. Post the supplied
`publishing_caption.txt` with the video; required rig attribution remains there.

| Profile/option | Behavior |
| --- | --- |
| `--profile preview` | 360×640, two Cycles samples, animation on twos; 720×1280 captioned export |
| `--profile production` | 720×1280, 16 Cycles samples, one rendered pose per frame; slower CPU rendering |
| `--until audio` | Stop after voices, lip cues, word alignment and timed-caption preflight |
| `--until scene` | Also bake the scene and check native rigs, poses, feet and cameras; do not render the movie yet |
| `--jobs 1`, `2` or `4` | Set independent four-thread Blender rendering workers |

Use a **new build directory** for changed content, asset bytes, code or quality
profile. Repeating an unchanged command resumes completed stages using hashes.
An existing, unowned directory or a mismatched job is rejected rather than
overwritten. Rerunning an invalidated stage also invalidates its downstream
checkpoints. Rendering retains the existing saved-scene hash guard.
Per-stage logs are `pipeline_*.log`; `pipeline_state.json` records stage
durations and output hashes. Interrupted owned promo jobs can also resume.

For the full entrance/examiner/task-card version:

```bash
python3 pipeline.py build \
  --episode episode_v4.json \
  --build builds/ausflug_new \
  --profile preview --jobs 4
```

For higher-resolution/full-rate output, select `--profile production` and a
different output directory after approving the preview. This improves render
quality, not the underlying procedural acting.

### Full book-based episode: Lerntreffen

`episodes/lerntreffen_dtz.json` adapts **Teil 3, Übung 2: Lerntreffen für die
DTZ-Prüfung planen** from `b1/speaking_dtz_gpt_v1/book_no_toc.md`. This is a new
complete-topic practice dialogue, not the separate three-turn technical demo
in `episodes/lerntreff.json`; neither is an official task or a full DTZ exam.
The original book and the approved Ausflug video remain unchanged.

| Planning point | Model-dialogue decision |
| --- | --- |
| Day and time | Saturday, 10:00 outside the library; Samir is only available until 11:30 |
| Place and duration | One hour in the quiet library, then a short visit to an inexpensive café |
| Study topics | Picture descriptions, then planning together; help each other with vocabulary |
| Materials and preparation | Lea: notebook, topic cards and dialogue questions; Samir: pens, water and picture-description tasks |
| Food and budget | Something to eat afterwards; Samir wants to spend at most five euros |
| Plan B | If no library seat is available, use the quiet tables at the neighbouring café |

The `source.coverage` map links each visible task point to dialogue turn IDs.
`test_lerntreffen_episode.py` checks those links, concrete decisions, source
identity, shared voices, speaker cameras and preserved pacing. The six task
points include the five source-book points plus its food/budget role constraint.
The episode uses V7 acting with the approved entrance, examiner hold, full
eight-second task card, candidate pauses and six-second CTA; there is no tips
card and no requested promotional cut. Speech settings are unchanged.

```bash
# New preview in a fresh directory, reusing matching raw speech from r1.
python3 pipeline.py build \
  --episode episodes/lerntreffen_dtz.json \
  --build builds/lerntreffen_v7_preview_r2 \
  --speech-cache-from builds/lerntreffen_v7_preview_r1 \
  --profile preview --jobs 4

# Only after approving the delivered r1 preview: production with identical speech/timing.
python3 pipeline.py build \
  --episode builds/lerntreffen_v7_preview_r1/episode.json \
  --build builds/lerntreffen_v7_production \
  --reuse-audio builds/lerntreffen_v7_preview_r1 \
  --profile production --jobs 4
```

The full preview is `builds/lerntreffen_v7_preview_r1/pilot.mp4`: **103 seconds,
2,472 output frames at 24 fps**, with 1,236 native preview poses. The clean review
version is alongside it. Copy-ready posting text is in
`../posts/dtz_b1_lerntreffen/tiktok.txt` and `instagram.txt`, including the
disclosure and complete character attribution. The generated
`publishing_caption.txt` remains part of each frozen build. The unsuffixed
`builds/lerntreffen_v7_preview/` contains the first audio-only take; `_r1`
makes the café location proposal explicit and reuses the other recordings.

### Book-based Teil 1: introductions and follow-up questions

`episodes/teil1_vorstellung.json` adapts the book's **Teil 1, Übungen 1–3** into
an original, shortened practice episode. Both candidates participate: Lea
introduces herself and answers a question about working in retail; Samir
introduces himself and explains how he practises German alongside childcare.
Their fictional biographies cover name, birthplace, residence, work, family
and languages. The examiner closes **the first part**, not the entire exam.
The original book and all previous deliveries remain unchanged.

The episode retains the real entrance, shared 1.7B voices, existing synthesis
settings, 1.2-second examiner hold, eight-second learning card, 1.2-second
dialogue gaps and six-second book CTA. The learning pause is pedagogical, not
an official exam time allowance. There is no tips card or promotional cut.

```bash
# Validate the script, tools, assets and all section-header labels.
python3 pipeline.py validate --episode episodes/teil1_vorstellung.json

# Fresh full preview; reuse only raw recordings with matching text/voice/settings.
python3 pipeline.py build \
  --episode episodes/teil1_vorstellung.json \
  --build builds/teil1_vorstellung_v7_preview_r3 \
  --speech-cache-from builds/teil1_vorstellung_v7_preview_r2 \
  --profile preview --jobs 4

# After approval only: preserve the preview's exact speech and timing.
python3 pipeline.py build \
  --episode builds/teil1_vorstellung_v7_preview_r2/episode.json \
  --build builds/teil1_vorstellung_v7_production \
  --reuse-audio builds/teil1_vorstellung_v7_preview_r2 \
  --profile production --jobs 4
```

Copy-ready, full-episode caption drafts are in
`../posts/dtz_b1_teil1_vorstellung/tiktok.txt` and `instagram.txt`.
Approval, production rendering and manual publication are separate steps;
creating the preview does not publish anything.

The delivered preview is `builds/teil1_vorstellung_v7_preview_r2/pilot.mp4`:
**115.375 seconds, 2,769 output frames at 24 fps**, using 1,385 native preview
poses. The clean video, contact sheet and review reports are alongside it.
All ten turns matched independent, unprompted ASR after case/punctuation
normalization; this is a plausibility check, not a pronunciation guarantee.
The 28 subtitle pages have at least 2.375 encoded seconds each and stay below
20 characters per second.

`_r2` reuses the verified `_r1` scene, controls, cameras, frames and audio
byte-for-byte; only FFmpeg compositing/export was rerun to correct output-frame
caption updates. The complete native-file hashes, original source hashes and
reuse policy are recorded in the frozen `audio_reuse.json`. Neither the first
full render nor earlier episode masters were overwritten.
`encoded_section_checks.json` checks actual decoded frames immediately before
and at each header transition and both ends of the full 144-frame CTA.

Optional `exam_part` identifies part 1, 2 or 3. Optional `sections` maps IDs to
short, measured header labels, and each turn can select a `section`:

```json
"sections": {
  "1A": "Teil 1A · Vorstellung",
  "1B": "Teil 1B · Nachfragen"
}
```

These labels describe the exam task, **not animation phases**. The entrance,
instruction and dialogue phases still run once in that order, while section
labels can repeat for the second candidate. A turn without `section` restores
the base topic; the CTA also restores it. Episodes without section metadata
keep their existing static header. All labels, including unused declarations,
are checked for fit before synthesis, then audited as rendered libass pixels.

ASS timestamps have centisecond precision. New social exports preserve frame
boundaries when serializing subtitle windows, headers and cards, rather than
rounding a boundary upward and losing its first encoded frame. In particular,
an odd-frame episode still receives all **144 frames** of its six-second CTA at
24 fps. Arbitrary aligned-word timings retain their existing centisecond
rounding. Previously frozen videos/captions are not rewritten; regenerating
an older episode can now correct boundary timestamps without changing its
caption text, layout or acting.
The compositor expands held native poses to the output frame rate **before**
rendering ASS, so headers, word highlights and cards update at 24 fps even
when preview animation is rendered on twos. Applying `fps` only after ASS
would duplicate old caption states over odd-frame transitions. An encoded
synthetic regression checks that case, not just the filter command.

The `introduce`, `ask` and `answer` actions support examiner-led interaction.
Introductions select up to three restrained, speech-aligned gestures spread
across the monologue. Questions use at most one smaller gesture; answers use
up to two. Candidates address the examiner, who selectively acknowledges the
end of their contribution before speaking again. Existing Teil 3 gesture and
attention plans are unchanged.

`test_teil1_episode.py` covers both candidate sequences, source coverage,
repeatable section labels, exact header windows, metadata rejection, CTA reset,
preserved pacing, gesture distribution, attention and publishing credits.

### V5 acting and room direction

New scene builds use speech-aligned content-word beats rather than the same
first-word gesture on every line. Proposals use open-palmed offers; reservations
are smaller and inward; agreements include restrained nods. Gestures alternate
hands and have anticipation, a brief hold and a soft release. Partner attention
continues through turn gaps, listeners acknowledge phrase endings, and occasional
thinking/note glances are tied to actual pauses/turns. Breathing remains subtle;
hands and feet retain their contact constraints. Close-ups use partner-side
coverage while retaining the speaker through the complete turn.
Resting hand placement checks the native finger tips against the actual tabletop
height, including between gesture beats. This remains stylized procedural acting,
not motion capture or automatic cinematic choreography.

The reusable room now has a sage feature wall, light-oak furniture, acoustic
felt/slats, tidy closed storage and balanced daylight. Optional `scene.wall_logo`
places the supplied image in a physical frame beside the entrance, packed into
the Blender file. The shipped episodes use the existing, unmodified
`german_exam_books/logo.png`, copied to `assets/deutschkompass-logo.png`.
It is set-dressing, not a floating video watermark; it is visible in the room and
Lea's coverage, not forced into every camera angle. Omit this field for an
unbranded room or provide your own image. Source/asset hashes track these changes.

### V7 conversational acting

New scene builds coordinate the eye target and head turn instead of snapping the
eyes to a partner before the head has moved. Eyes lead gently, with at most
0.16 radians of planned head-relative yaw; both tracks are continuous functions
of speech time, independent of bake sampling. This prevents preview and
production profiles from accumulating different gaze poses. The limit is a
project animation choice, not an exam requirement or a substitute for checking
rendered iris visibility.

Blink spacing varies by actor, with a blink near a major attention change.
Peaks land on the actual pose grid so both profiles retain full eyelid closure.
Listener acknowledgements are selective and finish before that listener starts
speaking. Proposals/explanations have at most two emphasis gestures; the
original welcome/consider/agreement actions have at most one. The interview
actions use the limits described above. Reach and anticipation/hold/release timing vary across
turns, while fingertip/table contact constraints remain enforced. Speaker
cameras, mouth cues, subtitle timing and learner pauses are unchanged.

`builds/v7_acting_test/pilot.mp4` is a **12.417-second internal acting test**, not
a short promotional cut or a replacement publication video. It uses complete
turns 03–04 and their original pauses, with an exact PCM crop from
`builds/v6_hold12_cta6_production/`. Its newly baked animation runs on every frame
at 24 fps; native 360×640, four-sample diagnostic renders are upscaled for
review. `DIAGNOSTIC.json` records the source crop; `scene_checks.json` records
native rig, contact, blink and gaze-continuity checks. Review the moving
transition and listener poses, not only a settled still. `comparison.mp4`
shows the same dialogue side by side (original V6 / refined V7);
`encoded_eye_transition.jpg` shows 24 consecutive encoded transition frames.

The approved 103.917-second full production remains unchanged at
`builds/v6_hold12_cta6_production/pilot.mp4`. Future full episodes use V7 acting
when built into a **fresh directory**. Do not resume a pre-V7 scene build with
changed source files; use the existing verified speech-reuse options instead.
No promotional cut is needed for this workflow.

### Shared German voices and V6 entrance

The shipped episode files now use the existing references in
`../../shared-voices/qwen3-tts-german/`, with the matching `reference_text.txt`:

| Speaking slot | Reference profile |
| --- | --- |
| Examiner | `male_middle_aged.wav` |
| Lea (`candidate_a`) | `female_young_adult.wav` |
| Samir (`candidate_b`) | `male_young_adult.wav` |

References remain in the shared folder; they are not duplicated or regenerated.
The default clone model is **`Qwen/Qwen3-TTS-12Hz-1.7B-Base`**, using the existing
local model cache. `VoiceDesign` made the reference voices; `Base` clones them
for the actual dialogue. No 0.6B fallback is used. Changing reference audio or its
transcript invalidates the speech cache and requires fresh lip cues, word
alignment and animation timing. Do **not** use `--reuse-audio` with an older
delivery made with different references.
Speech uses seeded sampling (`do_sample=true`, seed 0), matching the model's
recommended decoding mode. These settings are part of every voice-cache key.
Token-limit failures remain explicit errors, never cached as finished speech.

New room builds have a real opening through the wall, an open U-shaped frame,
interrupted skirting and a lit corridor. Candidates start outside, enter
single-file and take separate aisles. The inward-opening door waits until they
clear its sweep before closing. Path speeds are checked before scene baking;
short welcomes fail explicitly rather than speeding characters through walls.
A longer welcome does not slow the entrance beyond its eight-second blocking.
Native scene checks verify actual mesh starts/portal clearance, body/door
separation, stance contacts and title visibility.

The full and promo openings explicitly identify DTZ B1. Their measured hook
panels are compact and bottom-anchored near the subtitle position, not across
the doorway or arriving heads. Existing subtitle highlights, reading limits,
stable speaker cameras, Amazon CTA and publishing-caption credits are retained.

The current `episode_v4.json` adds a learner-paced `pause_after: 1.2` seconds
after each candidate turn. The examiner's 3-second seating pause is unchanged.
After the instruction, the camera and final subtitle hold on the examiner for
1.2 seconds, then the task card appears for a full 8 seconds before Lea begins.
The instruction turn uses `task_card_delay_seconds: 1.2` within a total
`pause_after: 9.2`; the delay is part of that total, not an additional hidden gap.
The tips card is disabled (`takeaway: []`, `takeaway_seconds: 0`), leaving only
a 6-second book CTA (`outro_seconds: 6`).
This adds silence between turns, not slower speech;
it is a study-video editing choice, not an official exam timing rule. At 24fps,
1.2 seconds is rounded up to 29 frames (about 1.208 seconds). Preserved deliveries
keep their original timing.

Generate a new pacing preview using the verified 1.7B speech:

```bash
python3 pipeline.py build \
  --episode episode_v4.json --build builds/v6_hold12_cta6_preview \
  --speech-cache-from builds/v6_qwen17b_release \
  --profile preview --jobs 4
```

Use a fresh build directory when changing pauses. Do not use `--reuse-audio`
for this revision: its exact mixed-audio timing no longer matches. Add
`--until audio` to listen to the new `dialogue.wav` before baking/rendering,
then repeat without that option to finish the preview. The new timeline,
captions and animation must be rebuilt; existing videos remain untouched.

When changing pauses, copy or visual code, `--speech-cache-from PREVIOUS_BUILD`
avoids regenerating unchanged utterances. It copies only raw WAV/cache pairs
whose text, reference bytes, model, decoding settings and actual WAV hashes
match the new request. The source is read-only; other-model/voice matches are
not accepted. Gaps, lip cues, alignment, captions and visuals are rebuilt.
This is an optional performance hint, not exact mixed-audio reuse, and can be
omitted when resuming an already prepared build.

To revise visuals without changing an approved voice performance, use an
episode whose voice references and spoken timing still match the source:

```bash
python3 pipeline.py build \
  --episode builds/v5_final/episode.json --build builds/visual_revision \
  --reuse-audio builds/v5_final --profile preview
```

`--reuse-audio` requires a previously verified delivery with its original
raw-voice cache metadata available. It checks screenplay, timing, reference-voice
hashes, exact PCM duration and measured words, then copies the full mixed audio
and alignment byte-for-byte. Changed dialogue, voice references or audio timing
are rejected; omit this option when new speech is required. Visuals are baked
and rendered again, never passed off as old reusable frames. `audio_reuse.json`
records the source hashes. Source masters are not modified.

### Episode fields

`episodes/lerntreff.json` is a short, original, dialogue-only example with
arbitrary IDs (`propose-time`, `offer-place`, `confirm-plan`), no entrance or
task card, different headings and its own promo settings.
`episode_v4.json` demonstrates the complete entrance/instruction/dialogue
structure. Copy either JSON file and edit:

| Fields | Purpose |
| --- | --- |
| `schema_version: 1`, `id`, `title`, `label`, `branding`, `disclaimer` | Episode identity and descriptive metadata |
| `scene.template: "exam_room"`, `scene.base_scene`, `scene.entrance` | Reusable room asset and optional entrance/seating sequence |
| Optional `scene.wall_logo` | Real logo image mounted beside the entrance; omitted for no logo |
| `header.brand`, `header.topic`, `hook` | Actual visible header and opening hook; no fixed topic text |
| Optional `exam_part`, `sections`, turn `section` | Part 1/2/3 metadata and timed section headers, independent of animation phases; omit a turn's section to restore the base topic |
| `voices` | Reference WAV/transcript pairs for the speaking actor slots |
| `turns` | Arbitrary unique IDs, speaker slot, display name, spoken text, camera, acting action, gaze target and pause |
| `phase` on a turn | `welcome`, `instruction` or `dialogue`; without it, `welcome`/`explain` actions imply the first two phases |
| Optional `task_card_delay_seconds` on the instruction turn | Quiet examiner-camera/subtitle hold before the task card; defaults to zero and is included within that turn's total `pause_after`. Both timings round up to whole frames; the remaining card window must be positive |
| `task_title`, `task_summary`, `task_card`, `task_hint` | Optional instruction card, displayed in the pause after the instruction phase |
| `takeaway_title`, `takeaway`, `takeaway_seconds` | Optional teaching card within `outro_seconds`; set `takeaway: []` to disable it and let the CTA fill the outro |
| `cta`, `book_cover` | Up to three configured CTA lines and the actual portrait book cover |
| `publication.intro`, `publication.disclosure`, `publication.hashtags` | Publishing copy; mandatory character/license credits are appended |
| `promo.hook`, `intro_seconds`, `outro_seconds`, `min_seconds`, `max_seconds` | Promo-specific bookends, copy and duration limits |
| Optional `promo.turn_ids` | An exact consecutive sequence of dialogue turns; no interior audio cuts |

Asset paths in schema-version-1 episodes are relative to **the episode file**,
not the working directory or build. This applies to voice WAVs/transcripts,
the cover, base scene and wall logo. Moving a JSON into another directory requires
adjusting its relative paths, or using absolute paths.

Actor slots remain `candidate_a`, `candidate_b` and `examiner`; their display
names are freely editable. Supported cameras are `wide`, `candidates`,
`candidate_a`, `candidate_b` and `examiner`; a selected shot must include its
speaker. Acting actions are `welcome`, `explain`, `propose`, `consider`,
`agree`, `introduce`, `ask` and `answer`. Turn IDs and the number of dialogue turns are not fixed.
Episode/turn IDs use filename-safe ASCII letters, digits, underscores and
hyphens, begin with a letter or digit, and are at most 64 characters long.
Entrance-enabled episodes need enough welcome/intro time for seating.
A task card needs an instruction turn with a positive pause before dialogue.

The conservative layout supports up to six task points, three takeaways and
three CTA lines, subject to actual measured wrapping. Overlong content fails
instead of silently shrinking, truncating or overlapping. After synthesis,
timed caption pages must meet the reading limits **before** Blender baking
and rendering. Review `preflight/` alongside `dialogue.wav` when stopping at
the audio stage. A requested promo must also fit its whole-turn duration and
caption limits before rendering begins.

The finished export includes automatic media decoding, safe-area and camera
checks, review sheets, required publishing copy, a `source_export/` snapshot
and `export_manifest.json` hashes. Existing delivered masters remain untouched.

Focused regression suite:

```bash
/home/ronggong/lang/german/.venvs/qwen-tts-test/bin/python \
  -m unittest test_build_paths test_episode_config test_teil1_episode test_lerntreffen_episode test_entrance test_direction test_social test_audio test_render test_exchange
```

## Preserved productions

**Latest production: V6 entrance and 1.7B shared-voice preview.** All dialogue
uses Qwen3-TTS 1.7B Base with the shared German reference profiles. Candidates
enter through a real open doorway from a lit corridor, clear the frame before
turning, and sit down in sequence. The lower opening panel explicitly identifies
DTZ B1 without covering the doorway or arriving heads. Speech-timed gestures,
partner attention, native finger/table contact, the Deutsch Kompass wall sign,
stable speaker cameras and the Amazon-book CTA remain in place. Lip cues and
word highlighting were regenerated for the new speech.

| Video | Path | Duration |
| --- | --- | --- |
| Full book-based Ausflug practice | `builds/v6_qwen17b_release/pilot.mp4` | 97.625 s |
| Promotional cut | `builds/v6_qwen17b_release_promo/pilot.mp4` | 42.917 s |

These are preview-profile renders, not native-resolution/full-rate production
renders: native 360×640, two Cycles samples and animation on twos, exported at
720×1280/24fps. The promo uses an exact-PCM excerpt of complete dialogue turns.
The shortest encoded subtitle pages are 1.917s in the full video and 2.125s in
the promo. Required posting credits remain in each directory's
`publishing_caption.txt`, not a permanent footer.

Known preview issue: the promo's opening freezes Lea during an eye-gaze
transition. Choose a calmer opening hold before treating the promo as
publication-ready; the complete dialogue and exact-PCM edit are unaffected.

V5 remains preserved in `builds/v5_final/` (98.625s) and
`builds/v5_final_promo/` (44.792s), with its original V4-readable audio unchanged.
V4 readable and all earlier masters are also preserved. The approved V3 study
has a separate safe-area/word-highlight re-export; the original pilot description follows.

A **stylized animated practice excerpt**, not a photorealistic film or a
complete examination. Version 2 replaces the primitive characters with Blender
Studio's licensed Snow and Rain rigs, including modeled faces, hands, clothing,
native skeletal deformation, purposeful gestures and facial-bone lip-sync.
Two candidates enter a room with two examiners. After an
examiner prompt, they start planning a day trip. The video ends by inviting the
viewer to finish the plan and showing the real book cover.

Both versions run **39.25 seconds** and use the same approved Qwen dialogue,
so visual comparisons do not depend on a different script or voice performance.
Version 1's outputs remain untouched in `builds/pilot_v1/`; version 2 uses `builds/v2/`.
The old generator scripts are saved in `builds/pilot_v1/source_v1/`.

The original shortened dialogue is inspired by **Teil 3, Übung 4** in
`german_exam_books/b1/speaking_dtz_gpt_v1/book_no_toc.md`. It demonstrates proposing,
responding to a budget constraint and agreeing on a departure time. It deliberately
does **not** cover every task point or present a complete assessed B1 performance.
The video labels this clearly as an independent practice excerpt.

## V4: complete-topic social animatic

New work is isolated from all previous masters:

| Directory | Length | Purpose |
| --- | --- | --- |
| `builds/v3_social/` | 10.000s | Approved V3 acting study, re-exported with safe-area word highlights and no rig-credit footer |
| `builds/v4_readable/` | 98.625s | Preserved readable V4 practice: stable speaker cameras, readable subtitles, clearer takeaway and Amazon CTA |
| `builds/v4_readable_promo/` | 44.792s | Preserved readable V4 promo, using a whole-turn exact-PCM excerpt |
| `builds/v4/` | 98.625s | Preserved initial V4: entrance/seating, examiner prompt, six-point task card, eight-second learner pause, compact dialogue, useful phrases and book CTA |
| `builds/v4_promo/` | 44.792s | Preserved initial promotional edit |

Watch `pilot.mp4` in either preserved V4-readable directory. The readable revision does not cut
to a listener before a speaker finishes or briefly cut back afterward: the
speaker's camera stays selected until the next turn begins. The original audio,
word alignment and total durations are unchanged. The takeaway now says
**“Tipps für euren Dialog”**. The CTA has no “Dein nächster Schritt” heading
and reads **“Amazon-Buchlink im Profil”**, with no sample-link claim.

Readable captions use up to **three measured lines**, combine short sentences
rather than flashing a separate page for each, and hold the last page until
the next turn. Instruction captions stop before the learner task card.
Every page must last at least **1.8 seconds**, including 24fps frame
quantization, and stay below **20 characters/second**. These are project
reading-policy limits, not official exam or platform requirements. Actual
shortest pages are 1.917s in the full video and 1.958s in the promo.
Text remains visible during short pauses, but amber highlighting stops at each
word's measured end. Candidate subtitles are 31px; the lower-framed examiner
uses 29px with a lower panel so its mouth stays visible.
`subtitles.srt` follows the same stable pages.
`subtitle_timing_report.json` and `delivery_checks.json` record the timing,
reading rate and actual encoded speaking-frame camera checks.

Only camera markers and the render-output path were edited in the copied
Blender scene. Animation-curve coordinates and handles were hashed before and
after. `camera_revision_report.json` records the old/new camera selections:
1,064 camera-identical source poses were reused with individual PNG hashes;
120 changed-camera poses were rerendered. Existing saved-scene hash guards
remain active. Original V4 and earlier masters/scenes are untouched.

V4 is a **low-resolution timing/acting animatic**, not the expensive final-quality
film. Animation is rendered at 360×640 with two Cycles samples, denoised, at
12 distinct poses/sec. Exports are 720×1280 at 24 fps, with sharp captions added
after upscaling. The script completes the chosen planning points, **not an entire
DTZ speaking examination or its official duration**. Its learner pause belongs
to the teaching video, not to the examination procedure.

`episode_v4.json` covers destination/programme, meeting/departure, return,
food/budget, bad weather and responsibilities. It retains the approved cast,
local voice references and fluent proposal/agreement exchange. The new
performance reuses V3's native lip closures, rounded vowels, real eyelid
controls, downward ponytails and restrained gestures. All four actors retain
native rig drivers. Walking uses world-space foot-stance holds, a separate turn,
and a pelvis settle with the final feet planted; this is procedural blocking,
not motion capture. Fine weight transfer and turn transitions remain
final-acting polish work, not a claim of photorealistic performance.

`check_v4_scene.py` verifies all four actors' native drivers and actual eyelid
deformation, tabletop fingertip heights, downward hair, planted-foot drift
below 2mm, stable feet while sitting, and sampled speaker/listener mouths.
The build's `source_v4/` preserves its baked generator and isolated
door-parenting repair; original actor actions and earlier source scenes remain
untouched. Export-source snapshots and hashes accompany the final masters.

### Text safe area and word highlighting

`social_captions.py` uses a deliberately conservative **project safe rectangle**
of **x=88…512, y=200…752 on a 720×1280 canvas**. All headings, speaker labels,
subtitle phrases, every highlighted-word state, task points, useful phrases,
CTA and the whole book cover must fit. Wrapping uses DejaVu Sans font metrics,
not character counts. The exporter also rasterizes **every unique text,
highlight and panel state through the actual FFmpeg/libass renderer** and
checks its non-black pixel bounds. Results are in `safe_zone_report.json`;
simultaneously visible text is also checked for overlap, and the book cover's
full image rectangle is checked separately. `contact_sheet.jpg` reviews the
whole edit, while `safe_zone_review.png` shades the excluded areas; neither
review overlay is baked into the delivered masters.

Sources checked on October 20, 2026:

- TikTok official specifications and downloadable standard left-to-right
  safe-zone template:
  <https://ads.tiktok.com/help/article/tiktok-auction-in-feed-ads?lang=en>
- Official TikTok template archive:
  <https://lf-tt4b.tiktokcdn.com/obj/i18nblog/tt4b_cms/en-US/5jqet0ab9qci-10e7f5Vig4uhAscNP8XPB0.zip>
- Meta's official Reels creative page:
  <https://www.facebook.com/business/ads/facebook-instagram-reels-ads>
- Meta's detailed checker redirected to login during this audit:
  <https://www.facebook.com/business/help/980593475366490>

The downloaded 2880×5120 TikTok template scales exactly to 720×1280. Pixel
inspection confirms **internal** 80px side gutters, a 160px top exclusion and
440px bottom exclusion. An additional 120px lower-right obstruction starts at
x=520, y=560. The shared rectangle is inset from all of these regions: it
reserves the lower 41.25% and approximately 29% on the right.
**This is not certification of every Instagram/TikTok placement.** Device UI,
expanded post captions, anchors, advertisements and feed/profile cropping vary.
Check the actual in-app placement preview before posting; do not automatically
crop these vertical exports to square.

`align_words.py` reuses the local WhisperX approach found in
`../bildbeschreibung/bildbeschreibung_video/tts.py`, running in the already
installed Qwen environment. No Windows-mounted code was required. The exact
prepared per-turn WAV and its original transcript are aligned locally using
German `VOXPOPULI_ASR_BASE_10K_DE`. The model checkpoint hash, package versions,
audio hash, transcript, measured confidence scores and word intervals are saved.
Interpolation is disabled; incomplete, reordered or overlapping words fail
instead of falling back to guessed timings. The current word is amber;
between measured word intervals, no word is highlighted. Display timing is
quantized by ASS centiseconds and the 24fps export, not sample-accurate text
animation. Low confidence is retained explicitly for review, not replaced by
invented boundaries.

### No permanent rig-credit footer

Only the new **explicitly opted-in social exports** omit baked-in rig credits.
V1/V2/V3 originals and legacy rendering defaults are unchanged. Both new masters
must be published with the supplied **`publishing_caption.txt`**, which includes
the requested Snow/Rain credits, source links, CC BY 4.0 link, changes and
non-endorsement notice. `CREDITS.txt` accompanies each delivery as well.
Do not share these masters without the accompanying attribution. See the
license's medium/context provisions in section 3(a)(2):
<https://creativecommons.org/licenses/by/4.0/legalcode.en>.
The publishing caption also identifies the AI voices/animation and the
independent, shortened exercise; use the platform's applicable disclosure
controls when publishing.

### Reproduce the new outputs

Run from this directory; `QPY` below names the existing local runtime.

To derive the readable revision from the preserved initial V4, start with an
empty revision directory. The camera-preparation stage is intentionally
one-time; interrupted rendering resumes with the `frames` command.

```bash
QPY=/home/ronggong/lang/german/.venvs/qwen-tts-test/bin/python
.tools/blender/blender -b --disable-autoexec -t 4 --python-exit-code 1 \
  --python produce_v4.py -- revise-cameras --source builds/v4 --build builds/v4_readable
python3 render.py frames --episode builds/v4_readable/episode.json --build builds/v4_readable --jobs 4
$QPY render.py mux --episode builds/v4_readable/episode.json --build builds/v4_readable
$QPY produce_v4.py promo --source builds/v4_readable --build builds/v4_readable_promo
$QPY review_social.py --build builds/v4_readable
$QPY review_social.py --build builds/v4_readable_promo
$QPY -m unittest test_social test_audio test_render test_exchange
```

The earlier baseline-generation commands below are retained for reference.
Current generators produce the corrected camera/caption behavior; exact earlier
sources are preserved with their deliveries. Do not run these commands over
masters you want to retain unchanged.

```bash
QPY=/home/ronggong/lang/german/.venvs/qwen-tts-test/bin/python
$QPY produce_v4.py v3 --build builds/v3_social
$QPY prepare_audio.py --episode episode_v4.json --output-dir builds/v4 --threads 4
$QPY align_words.py --build builds/v4
.tools/blender/blender -b --disable-autoexec builds/v2/studio.blend -t 4 \
  --python-exit-code 1 --python produce_v4.py -- scene --episode episode_v4.json --build builds/v4
.tools/blender/blender -b --disable-autoexec builds/v4/studio.blend -t 2 \
  --python-exit-code 1 --python check_v4_scene.py -- builds/v4
python3 render.py frames --episode episode_v4.json --build builds/v4 --jobs 4
$QPY render.py mux --episode episode_v4.json --build builds/v4
$QPY produce_v4.py promo --source builds/v4 --build builds/v4_promo
$QPY review_social.py --build builds/v4
$QPY review_social.py --build builds/v4_promo
$QPY -m unittest test_social test_audio test_render test_exchange
```

The promo preserves whole turns and all interior speech samples; only silent
bookends and held first/last poses are added. Its `studio.blend` is explicitly
the **full source scene**: the promo edit and pose sampling are described by
`scene_manifest.json`, not represented as a separately retimed Blender scene.

## Earlier outputs

Current generated production files live in `builds/v2/`:

| File | Purpose |
| --- | --- |
| `pilot.mp4` | Vertical H.264/AAC video with German captions, branding and book end card |
| `pilot_clean.mp4` | Same animation/audio without teaching/brand overlays; character credits retained |
| `studio.blend` | Editable room, licensed studio characters, five cameras, animation and packed audio/textures |
| `dialogue.wav` | Full timed dialogue, including entrance, turn gaps and outro |
| `subtitles.srt` | Separate German dialogue subtitles |
| `captions.ass` | Styled editorial/caption layout used in the branded video |
| `timeline.json` | Measured turn timings and Rhubarb mouth cues |
| `scene_manifest.json` | Episode/timeline snapshot and render configuration |
| `frames_manifest.json` | Saved-scene hash tying the rendered frames to their source |
| `media_report.json` | Encoded video/audio stream information |
| `media_report_clean.json` | Separate media check for the clean master |
| `audio/` | Per-turn audio cache, created when running the audio stage in this build directory |
| `render_checkpoint.json` | Scene-hash checkpoint allowing interrupted renders to resume safely |
| `still_*.png` | Camera-review images produced by the `stills` stage |
| `contact_sheet.jpg` | Eight-shot visual review sheet of this version |
| `before_after.jpg` | V1/V2 visual comparison using the same dialogue moment |

The default is **720 × 1280 at 24 fps**, with animation rendered **on twos**
(12 poses per second). This is an explicit CPU-friendly animation choice, not
24 distinct rendered poses per second. Use `--motion-step 1` when building the
scene for full-rate animation. No frame interpolation is used.

## Setup on this machine

System prerequisites: Python 3.12, FFmpeg with libass and libx264, DejaVu Sans,
curl, tar, unzip, and the libraries required by the official Linux Blender build.

```bash
cd /home/ronggong/lang/german/tiktok_anime_videos/pilot_3d
bash setup_tools.sh
bash setup_characters.sh
```

This downloads **Blender 4.5.9 LTS** and **Rhubarb 1.14.0** into `.tools/`,
without changing the system installation. Downloads are pinned and SHA-256
checked. The Blender hash comes from the official release checksum file; the
Rhubarb archive hash was recorded from the pinned GitHub release download.
The second script downloads pinned **Snow v4.2** and **Rain v3.2** character files
from the official Blender Studio v4/v3 release archives, with their textures.
It verifies the recorded archive SHA-256 checksums on every invocation.
The original character assets remain unmodified. Their CC BY 4.0 attribution
and source links are in `assets/studio/CREDITS.txt`. Legacy V1–V3 video exports
retain visible credits; the explicitly opted-in social exports above instead
require the accompanying publishing-caption credits.

Qwen uses the already installed environment:

```text
/home/ronggong/lang/german/.venvs/qwen-tts-test/bin/python
```

Override it with `QWEN_PYTHON` or `--qwen-python`. Voice WAV/transcript paths
in `episode.json` point to the existing local `simple-tts/voices` directory.
Those files must remain available for regenerating speech. Existing production
audio can be rendered without loading Qwen. Models and synthesis stay local;
no book text or voice recordings are uploaded to an external service.
The first v2 build reuses `builds/pilot_v1/dialogue.wav` and its measured timeline; the
packed `studio.blend` is self-contained for texture/audio playback. Running
`audio` or `all` creates a new audio cache inside the selected build directory.

## Production commands

Run stages separately to review the audio and cameras before a long render:

```bash
python3 render.py audio
python3 render.py scene
python3 render.py stills
python3 render.py frames
python3 render.py mux
```

Frame rendering defaults to two independent Blender workers, each using four
CPU threads. Use `python3 render.py frames --jobs 1` on a busy host, or
`--jobs 4` when CPU capacity is available. Each worker writes a separate
`builds/v2/render_*.log`; failure in any worker stops the pipeline.
The command reports a completed-frame count approximately every minute.
Rendering enables Cycles persistent-data caching so textures are not reloaded
from scratch for every animation frame.
Rerunning `frames` after an
interruption reuses valid PNGs only when the saved-scene hash and configuration
match the checkpoint. A different scene causes all required frames to rerender.

Or run the complete pipeline:

```bash
python3 render.py all
```

Lower-resolution development scene:

```bash
python3 render.py scene --width 360 --height 640
python3 render.py frames
python3 render.py mux
```

The v2 default is **Cycles CPU rendering with 16 samples and denoising**;
the first full v2 film uses 12 samples. Use `--samples 24` on `scene` to trade
longer rendering for less noise. `--engine workbench` is available for fast
pose/framing checks, not as an automatic fallback when Cycles fails.
The scene uses soft daylight/fill/rim lights, AgX color management, and subtle
wood-grain materials. Character asset UI scripts are disabled in all project
Blender commands; animation uses native pose controls without running those scripts.

Full-rate 1080p scene (substantially slower on this CPU-only host):

```bash
python3 render.py scene --width 1080 --height 1920 --motion-step 1
python3 render.py frames
python3 render.py mux
```

Frame rendering uses the saved scene configuration. After changing the
episode/audio, rebuild the scene and rerender frames before muxing. The
pipeline refuses known stale episode/timeline snapshots and incomplete frame
sequences; it does not substitute silence, alternative TTS, or guessed timings.
Keep the source scene with the audio alongside it when moving deliverables.

## How animation and timing work

1. `episode.json` is the director's script: German lines, speaker, camera,
   acting cue, gaze target, pauses, task points, branding and cover.
2. `prepare_audio.py` generates per-turn German Qwen voice-clone audio and uses
   measured WAV duration, not reading-speed estimates, for the film clock.
   Excessive edge quiet is conservatively shortened at -45 dBFS only when longer
   than 0.5 s at the start or 0.8 s at the end, retaining 180 ms padding.
   Raw WAVs and exact trimmed sample bounds are retained; interior pauses are
   never removed or time-stretched.
3. Rhubarb's **phonetic** recognizer analyzes each WAV. Its A–H/X mouth cues
   drive native jaw and mouth controls on the characters. This is coarse audio-derived
   mouth animation, **not** German phoneme forced alignment or word highlighting.
4. `build_scene.py` builds the room, furniture, soft lighting and five cameras.
   `studio_characters.py` appends the licensed character collections and animates
   their native IK, head, gaze, facial and jaw controls. All performance is baked
   into the saved scene: no runtime frame handlers or external rig UI add-ons are
   needed. Candidate and examiner clothes/hair colors distinguish the four actors.
5. `render.py` assembles frames on the measured timeline, adds captions and the
   book cover, and applies -16 LUFS audio normalization with a -1.5 dB true-peak
   target. These are encoding targets, not a guarantee of every playback device's
   perceived loudness.

The five action labels (`welcome`, `explain`, `propose`, `consider`, `agree`)
drive a small gesture vocabulary: timed hand accents, a thinking tilt, and an
agreement nod, with restrained listener reactions and eyes aimed toward the
conversation. It is still procedural animation, not motion capture. The entrance,
finger articulation and Rhubarb lip-sync remain simplified; no claim is made
that this is final character acting or phoneme-accurate German articulation.

## Changing the episode

Edit `episode.json`, then run audio → scene → stills → frames → mux.
Use the supported speaker IDs `examiner`, `candidate_a`, `candidate_b`;
`observer` is the second examiner and remains silent. Supported cameras:
`wide`, `examiner`, `candidates`, `candidate_a`, `candidate_b`.

Keep one short speaking turn per entry. Do not change a speaker's voice reference
mid-episode. Leave budget/compromise questions for both candidates to answer;
do not replace interaction with two independent monologues.

The entrance and sitting sequence currently expects the first turn to be a
short examiner welcome, followed by the task introduction. This is a pilot
template, not an arbitrary screenplay engine. For longer scenarios, extend the
template deliberately rather than changing turn order blindly.

## Checks and review

```bash
python3 -m unittest test_audio test_render -v
.tools/blender/blender -b --disable-autoexec builds/v2/studio.blend --python-exit-code 1 \
  --python test_scene.py -- builds/v2
```

### V3: short character-acting study

`builds/v3_exchange/` is a separate **10-second** proposal/agreement exchange,
using turns 05–06 from the completed V2 scene. It is an acting review, not a new
complete promotional film: no entrance, task presentation or book end card.
V1 and V2 outputs are not overwritten. The original Qwen audio is cropped at
exact PCM sample boundaries; speech, internal pauses and playback speed are
unchanged. Source SHA-256 fingerprints are recorded in `source_excerpt.json`.

The study adds a downward-curved ponytail pose, softer eyelids, asymmetric
question/acknowledgment expressions, listener nods and a brief task-sheet glance.
The loader now preserves the native rig drivers when clearing source animation;
V3 also restores the drivers absent from the saved V2 rigs, so the expression and
blink controls reach the actual deformation actions. The pinned Rain asset has
one dangling spine-easing driver pointing to nonexistent `STR-Spine4`; the
adapter explicitly omits only that obsolete driver, retains the authored fixed
easing value, logs the repair, and records it in `scene_checks.json`.
Mouth animation uses native upper/lower lips and forward rounding as well as
the jaw, with short transitions between Rhubarb cues. These remain phonetic
recognizer cues, not verified German phoneme/word alignment or hair simulation.
The portrait cameras are closer, listener cutaways are explicitly scheduled,
and the caption layout omits the large title and promotional end card.
Speaker labels say "Es spricht" so listener cutaways are not mistaken for the
on-screen character's speech.
All **24 frames per second are rendered distinctly**, rather than on twos.

```bash
python3 polish_exchange.py prepare
.tools/blender/blender -b --disable-autoexec -t 4 --python-exit-code 1 \
  builds/v2/studio.blend --python polish_exchange.py -- scene
.tools/blender/blender -b --disable-autoexec -t 4 --python-exit-code 1 \
  builds/v3_exchange/studio.blend --python polish_exchange.py -- check
python3 render.py frames --build builds/v3_exchange \
  --episode builds/v3_exchange/episode.json --jobs 4
python3 render.py mux --build builds/v3_exchange \
  --episode builds/v3_exchange/episode.json
python3 -m unittest test_audio test_render test_exchange -v
.tools/blender/blender -b --disable-autoexec -t 2 --python-exit-code 1 \
  --python test_native_loader.py
```

The exports are `builds/v3_exchange/pilot.mp4` (compact German captions) and
`pilot_clean.mp4` (without teaching overlays). Both retain the character credits.
`before_after.jpg` compares the same audio moment in V2 and V3;
`contact_sheet.jpg` shows the final shot sequence.
Keep `episode.json`, `timeline.json`, `source_excerpt.json`, `scene_manifest.json`,
`scene_checks.json`, the audio and editable `.blend` with the review deliverables.
`source_v3/` archives the exact producer-script versions recorded in the saved
scene manifest, independently of subsequent source fixes.
`export_manifest.json` records the final caption/credit and MP4 hashes, with
the corresponding mux script archived as `source_v3/render_export.py`.
When using a custom episode, pass its path explicitly with `render.py --episode`;
the original full-pilot episode remains the renderer's default.

Before publishing, listen to all generated German, check pronunciation and
turn-taking, inspect every camera cut and the entrance/sitting transition, and
review captions on a phone. Confirm the linked book/sample is actually in the
profile before using the CTA. Follow the destination platform's synthetic-media
labeling requirements. Do not imply official DTZ endorsement or a guaranteed
score.

## Sources and assets

- Exam structure reference: [g.a.s.t. DTZ FAQ](https://www.gast.de/de/forschung-entwicklung/entwicklung/auftraege/deutsch-test-fuer-zuwanderer-dtz/faq).
  No official exam questions, task cards or dialogue were copied.
- [Blender 4.5 releases and checksums](https://download.blender.org/release/Blender4.5/).
- [Rhubarb Lip Sync](https://github.com/DanielSWolf/rhubarb-lip-sync), including its
  distributed licenses in `.tools/rhubarb/`.
- Existing local TTS/timing reference:
  `bildbeschreibung/bildbeschreibung_video/tts.py`. This pilot uses Rhubarb,
  not that project's WhisperX word-highlighting pipeline.
- Room and furniture: generated by `build_scene.py`.
- Snow and Rain rigs: Blender Foundation / Blender Studio, **CC BY 4.0**.
  Clothing/hair recolored, scaled, duplicated, posed and animated for this film.
  See `assets/studio/CREDITS.txt` for exact source URLs, archive hashes and
  attribution. This replaces v1's original primitive characters. No stock
  footage, music or third-party motion libraries are used.
- `assets/book-cover.jpg`: copied from the user's
  `speaking_dtz_gpt_v1/speaking_chatgpt_v1.jpg`, retaining the actual cover.
- Voice references: existing user-provided/generated local voice assets.
  Verify rights to any replacement voices or commercial assets before use.
