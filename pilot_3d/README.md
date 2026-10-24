# Reusable 3D exam-practice generator

## Windows and Linux/WSL2

The same Python entry points now resolve native Windows and Linux tools, fonts
and interpreters. Run `python setup_runtime.py` from this directory to install
checksum-pinned Blender 4.5.9, Rhubarb 1.14.0, DejaVu fonts and character rigs.
FFmpeg/ffprobe must be on PATH. Recreate the Python environment using
`requirements.txt` with `-c constraints-preview.txt`; this is a bootstrap
manifest, not the original production
environment's lockfile.

See [MIGRATION.md](MIGRATION.md) for PowerShell/WSL setup, the TEF resource
checklist, GPU checks and the exact limits of destination validation.
For the tested Windows JPEG-overlay workflow, the optional
`python setup_runtime.py --only ffmpeg` installs checksum-pinned FFmpeg 6.1.1;
prepend `.tools\windows\ffmpeg` to the session's PATH as documented there.
Use separate virtual environments and build directories on each OS.
Tool downloads are separated into `.tools/windows/` and `.tools/linux/`;
the old Linux `.tools/blender/` and `.tools/rhubarb/` layout still works.

Rendering defaults to CPU. Explicitly select `--render-device HIP` for a
compatible AMD GPU, `OPTIX`/`CUDA` for NVIDIA, or `ONEAPI` for Intel.
Start with `--jobs 1` on one GPU. Speech defaults to CPU independently;
`--speech-device cuda:0` requires a compatible PyTorch runtime and separate
speech review. A requested but unavailable Blender GPU fails rather than
silently switching to CPU.

### Generation runtime controls

`pipeline.py build`, the `render.py` and `produce_v4.py` entry points, and
`benchmark_workers.py` share scoped runtime controls. Native Windows runs
prevent automatic compute sleep **only while on AC power**, without keeping
the display on or changing the power plan. AC/battery transitions are checked
once per second; requests are released on completion, failure and graceful
cancellation. Linux/WSL2 do not acquire Windows power requests.
Cancellation cleans up only the run's owned subprocess trees; completed
checkpoints and frames remain available for compatible resumes.

Notifications are disabled unless both `VIDEO_NTFY_SERVER` and
`VIDEO_NTFY_TOPIC` are configured externally. For example, in PowerShell:

```powershell
$env:VIDEO_NTFY_SERVER = "https://ntfy.example.org"
$env:VIDEO_NTFY_TOPIC = "video-generation"
# Optional: set VIDEO_NTFY_TOKEN through your environment/secret manager.
```

In Linux/WSL2, export the same variables before invoking Python. Topics use
1-64 letters, digits, underscores or hyphens. Only fixed generic run/stage
statuses and 25/50/75/100% render milestones are sent: never episode text,
file paths, media, exception details or machine identifiers. Milestones are
deduplicated per process/run and throttled to 30 seconds, except 100%.
Verified reused stages are identified as checkpoints. A single top-level
run owns start and terminal notifications; child renderers report milestones.

Delivery is best-effort: a bounded 32-message queue, no retries or HTTP
redirects, a two-second network-I/O timeout, and at most one second of sender
shutdown waiting. Slow DNS/network operations run on a daemon thread and
cannot stall generation. Terminal status takes priority when the queue fills.
Network/configuration failures produce generic local warnings, not failed
videos. Hard process termination, OS shutdown and power loss cannot guarantee
a terminal notification; Windows closes the process's power requests.

Benchmark an existing baked scene in a **new sibling directory**:

```powershell
.\.venv\Scripts\python.exe benchmark_workers.py `
  --build builds\tef_canada_a1_windows_preview_r1 `
  --output builds\tef_canada_a1_worker_benchmark_r1 `
  --render-device HIP --frame-count 48 --repeats 2
```

The command compares 1, 2 and 4 workers, each with four CPU threads, on the
same evenly spaced native frames. Repeat order reverses to reduce order bias.
It does not change scene quality or rendering defaults. `benchmark.json`
records source/code hashes, exact frames/settings, startup and aggregate warm
throughput, sampled CPU/GPU/memory and the fastest fully verified worker count
by median warm throughput. Every PNG is decoded and checked for size. Failed
or cancelled trials retain their isolated logs/outputs and never alter the
source delivery. Windows GPU counters cover the owned worker PIDs, but their
engine activity can overlap: `gpu_owned_engine_activity_index` is a raw sum,
not physical GPU utilization, and may exceed 100. Physical utilization stays
null on Windows rather than inventing a capacity percentage. Linux AMD sysfs
counters are device-wide. Other unavailable metrics, including unsupported
WSL counters, remain null.

Use `--jobs 2 4 8` to test the larger configuration. Benchmarks reserve at
least 4 GiB of free system RAM and limit each trial to 600 seconds by default
(`--min-free-memory-gib`, `--trial-timeout`). A guard failure stops only that
trial's owned workers; remaining trials continue, failed trials cannot win,
and the final command reports partial failure rather than inventing a rate.
Use `--expect-profile production` to reject accidentally selected preview
scenes. Native scene dimensions, sample count and fixed CPU threads are
checked against the actual rendered worker settings.

The October 24, 2026 AMD Radeon 860M **preview-only** run used 48 frames per
trial, two trials per configuration, 360x640, two samples and four CPU threads
per worker:

| Workers | Median warm frames/min | Peak worker resident RAM |
| --- | --- | --- |
| 1 | 27.47 | 3.24 GiB |
| 2 | 45.95 | 6.47 GiB |
| 4 | 67.03 | 13.46 GiB |

Four workers were fastest among those tested, about 46% faster than two.
Use `--jobs 4` for this measured preview workload. Results, measured-code
snapshots and 288 verified images are in
`builds/tef_canada_a1_worker_benchmark_r1/`. Original delivery hashes still
match; the maximum mean RGB difference from the original native frames is
0.000064 on a 0-255 scale.

This is **not a production-quality benchmark**. Production uses 720x1280,
16 samples and every frame, versus animation on twos for preview; measure a
production-baked scene independently. The current CLIs support 1/2/4/8
workers; 16/32 are not supported or tested.

The genuine **production** benchmark used the 86.583333-second TEF short
episode: 720x1280, 16 samples, per-frame animation, the same 24 native frames
per trial, two reversed-order rounds and four CPU threads per worker.

| Workers | Median warm frames/min | Peak combined worker resident RAM |
| --- | --- | --- |
| 2 | 7.36 | 7.51 GiB |
| 4 | 9.47 | 15.56 GiB |
| 8 | Unverified: both attempts hit the 4 GiB free-RAM reserve | Not a completed trial |

Four workers were about 29% faster than two on this production workload.
Median end-to-end throughput, including startup, was 7.22/9.10 frames/minute
for 2/4 workers. Eight workers were stopped safely, not measured as slower or
recommended. The command returned partial failure because both requested
8-worker trials were unverified; the recommendation uses only complete,
verified configurations. Defaults are unchanged.

Results, 96 decoded production PNGs, hashes and measured-code snapshots are
in `builds/tef_canada_a1_short_production_worker_benchmark_r1/`. Their maximum
mean RGB difference between trials is 0.000066 on a 0-255 scale (maximum
single-channel error 1). The original 19 delivery hashes, 19 frozen source
hashes and all 288 preview-benchmark PNG hashes remain unchanged.
The measured code predates the GPU-counter labeling correction above:
the saved `gpu_busiest_engine_percent` sums are **not valid physical GPU
utilization**. This caveat is recorded in `verification.json`; throughput
and RAM measurements are unaffected. Archived measured code is preserved.

For the under-90-second TEF promotional excerpt, select
`episodes/tef_canada_a1_short.json` (10 turns), not the full 24-turn
`tef_canada_a1.json`. An authored `source.duration_limit_seconds` is enforced
strictly against the measured encoded frame clock during timeline validation,
before scene baking. The short episode declares 90 seconds, including its
entrance, reading pause and CTA. It is not acceptable to infer this duration
from the filename or an older machine's timing.

### Qwen TTS CPU thread benchmark

The Windows comparison used Qwen3-TTS 1.7B Base on CPU with the existing
float32/SDPA settings, one speech worker and **four fixed inter-op threads**.
Only intra-op threads varied. Three identical French TEF excerpts (6/19/25
words, candidate and examiner voices) generated 17.760 seconds of raw audio
per trial. Six fresh processes ran in order 2/4/8, then 8/4/2, each with an
empty speech cache and one warmup. Timed synthesis excludes imports, model
loading, voice-prompt setup, warmup and file I/O; those costs are recorded
separately.

| Intra-op threads | Median synthesis seconds | Median audio-seconds per wall second |
| --- | --- | --- |
| 2 | 152.23 | 0.1167 |
| 4 | 143.55 | 0.1237 |
| 8 | 136.63 | 0.1300 |

Eight threads had about 5.1% higher synthesis throughput than four on this
workload, not a twofold improvement. This controlled comparison fixes inter-op
threads at four; the ordinary two-thread CLI configuration uses two inter-op
threads and was not measured here.

**Qwen now defaults to eight intra-op threads and four inter-op threads** in
both `pipeline.py build` and standalone `prepare_audio.py`. Standalone
`--threads N` overrides Qwen's count. Lip-sync analysis remains independently
at four threads (`--rhubarb-threads N`), and Blender worker/thread settings
are unchanged.

All 24 raw WAVs (18 measured clips plus six warmups) decode and validate.
Measured clips have identical sample counts and differ from the four-thread
reference by at most one PCM16 quantization step; this is waveform comparison,
not a new listening/pronunciation certification. Original delivery, frozen
source and production-benchmark image hashes still match.

The default update changes hashed pipeline sources. Use a **fresh build
directory** for the next generation; the earlier prepared four-thread TEF
build cannot resume with the updated code. Do not edit its state/source
hashes to bypass this check. Existing audio/scenes are not rewritten.
Thread counts also participate in raw-speech cache keys, so four-thread
recordings are not silently relabelled as eight-thread synthesis.

Reports, raw WAVs, source snapshots and the reproducible benchmark helper are
in `builds/tef_canada_a1_qwen_cpu_threads_benchmark_r1/`. One-thread synthesis
and multiple speech workers were not tested. Existing production speech
was not regenerated or replaced.

## Development workflow

The project-local `pilot-3d-dev` skill in
`.github/skills/pilot-3d-dev/SKILL.md` (relative to the repository root) covers
development, testing and build-preservation rules. Record project tasks in
[`plan/TODO.md`](../plan/TODO.md), not only a session-internal todo list.

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
    teil2_einkaufen_v7_preview/    First Teil 2 audio take
    teil2_einkaufen_v7_preview_r1/ Second Teil 2 audio take
    teil2_einkaufen_v7_preview_r2/ Full Teil 2 picture-led practice build
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
plot still needs another animation template. Speech and alignment support
German and French. The default layout retains both DTZ candidates; the
optional interview layout uses one candidate and one examiner.

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

The entry point selects `QWEN_PYTHON`, then the local `.venv`, then the original
Linux Qwen environment if present, otherwise the current Python interpreter.
Override it with `--qwen-python` or `QWEN_PYTHON`.
It does not use Ollama. All model inference, alignment and rendering stay local.
The selected episode is saved as an immutable, asset-resolved
`BUILD/episode.json`; commands use that snapshot throughout the build.
Output is `BUILD/pilot.mp4` and `BUILD/pilot_clean.mp4`, plus the
`BUILD_promo/` pair when `--promo` is requested. Post the supplied
`publishing_caption.txt` with the video; required rig attribution remains there.

| Profile/option | Behavior |
| --- | --- |
| `--profile preview` | 360×640, two Cycles samples, animation on twos; 720×1280 captioned export |
| `--profile production` | 720×1280, 16 Cycles samples, one rendered pose per frame |
| `--until audio` | Stop after voices, lip cues, word alignment and timed-caption preflight |
| `--until scene` | Also bake the scene and check native rigs, poses, feet and cameras; do not render the movie yet |
| `--jobs 1`, `2` or `4` | Set independent four-thread Blender rendering workers |
| `--render-device CPU`, `HIP`, `CUDA`, `OPTIX`, `ONEAPI` | Explicit Cycles backend; default CPU |
| `--speech-device cpu` | Preserve the original speech device; independent of Blender |

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

### Language, exam identity and scene layout

These are separate choices, not a growing list of DTZ-specific code paths:

```json
{
  "language": "fr",
  "exam": {"family": "tef_canada", "skill": "speaking", "section": "A"},
  "scene": {
    "template": "exam_room",
    "layout": "interview",
    "observer": false,
    "entrance": true,
    "base_scene": "../builds/v2/studio.blend"
  }
}
```

`episode_profiles.py` selects the Qwen language, WhisperX alignment model,
speaker/picture prompts, publishing disclosures and gesture function-word list.
French uses `French` and `VOXPOPULI_ASR_BASE_10K_FR`; German retains its original
settings/model. Language is part of the speech-cache fingerprint, prepared
timeline and alignment provenance. Exact audio reuse rejects a language change.
`fr` selects the language, not a guaranteed regional accent: cast an existing
French/Quebec reference voice and review the actual result.

Omitting the new fields preserves `language: "de"`, `layout: "pair"` and the
silent observer. Existing DTZ scripts need no migration. `exam_part` still
accepts legacy numeric DTZ parts; new `exam.family`, `exam.skill` and
`exam.section` identify other exams without pretending that section A is
DTZ Teil 1. Semantic headers remain configured through `sections` and turns.

The interview layout uses internal slots `candidate_a` and `examiner`, with
freely chosen display names. It hides the second candidate, unused seating,
personal props and, by default, the observer. Native visibility drivers on
inactive objects are muted so they cannot undo hiding; active native drivers
are preserved. `scene.observer: true` optionally retains the observer and chair.
The candidate can enter alone. Learning cards and the CTA use the wide camera,
not the two-candidate shot; turn shots still retain the speaking actor.

Voice references accept **exactly one** of a transcript-file path or inline
reference text:

```json
"examiner": {
  "audio": "/path/to/existing/reference.wav",
  "reference_text": "The exact words spoken in that reference recording."
}
```

Inline text is hashed into the cache and frozen episode; it is not a replacement
for checking the actual recording. Existing `audio`/`transcript` pairs retain
their original cache payload. Both forms require nonempty, matching text.

Current implementations are German/French **speaking** in the pair/interview
exam room. DTZ, ÖIF and fide listening need an explicit listening presentation,
including prompt, response and answer-reveal behavior; they are **not**
implemented by changing an exam label. Other speaking exams similarly require
their own reviewed tasks/configurations. Unsupported languages, layouts and
`exam.skill: "listening"` fail rather than quietly producing the wrong format.

### First TEF Canada configuration: Section A, practice A1

`episodes/tef_canada_a1.json` adapts only **Practice set A1: Neighbourhood digital
workshop** from `french_exam_books/tef_canada/speaking/book.md`. Its 24-turn
French script covers the schedule, free registration, shared computers,
practical activities, accessible room/transport, clarification of “quelques
places”, the full Thursday group, waiting-list alternative and natural close.
The examiner plays the service contact; the fictional telephone situation is
performed face-to-face, not presented as two people in separate locations.

The configuration uses the existing `fr_fr_conversation_f01.wav` and
`fr_fr_service_m01.wav` with their exact `voices.json` reference texts, plus
the speaking book's own cover. The revised configuration includes the book's
original A1 advertisement and the French Compass wall logo, with explicit
commercial reuse permission confirmed October 24, 2026. Source copies and
hashes are recorded under `assets/`; no official stimulus is copied.
Full-episode posting **drafts** are in
`../posts/tef_canada_a1/`; the full preview is delivered below for approval.
The learning pause and adapted length are not claims about official test timing.
Framework and language-model references, checked October 22, 2026:

- TEF Canada: https://www.lefrancaisdesaffaires.fr/candidat/test-evaluation-francais/tef-canada/passation/
- Qwen3-TTS French voice cloning: https://github.com/QwenLM/Qwen3-TTS
- WhisperX French alignment: https://github.com/m-bain/whisperX/blob/main/whisperx/alignment.py

TEF previews and historical review artifacts remain in the separate
`../tiktok_anime_videos_tef` worktree, even when the shared code is merged into
main. Its `builds/` root is independent; only existing tools, rig sources and
the reusable base scene are linked for read-only use. Do not install/update
tools through those links, or change shared source while a build is running.
Keep heavy CPU jobs sequential rather than competing with DTZ production.

The delivered full preview is
`builds/tef_canada_a1_preview_r2/pilot.mp4`, with an uncaptioned
`pilot_clean.mp4` alongside it: **189.7917 seconds, 4,555 output frames at 24 fps,
720x1280**, from 2,278 native preview poses. Both masters decode successfully.
The candidate enters alone through the real doorway; the examiner then plays
the service contact. The observer/second candidate and 142 unused objects stay
hidden. Native rigs, walking/foot contact, door clearance, gaze, gestures and
speaker-camera coverage pass.

Real French Qwen3-TTS 1.7B Base speech and French forced alignment are used.
There are 50 subtitle pages: minimum encoded display **1.8333 seconds** and
maximum **19.84 characters/second**. Actual decoded frames verify both header
changes, the 29-frame examiner hold, 192-frame learning card and 144-frame CTA.
`episode_content_checks.json`, `delivery_checks.json`, `scene_checks.json`,
`contact_sheet.jpg` and `qa/encoded_boundary_contact_sheet.jpg` retain evidence;
the frozen export/source hashes and exact audio-reuse eligibility also verify.
All 50 video masters that existed before this work remain unchanged.

The first audio take, `tef_canada_a1_preview_r1`, stopped at caption preflight
because turn 17 was too dense. The new clarification keeps the Thursday
availability question; r2 reuses the other 23 raw recordings byte-for-byte.
No fonts, timing limits, dialogue gaps or synthesis settings were relaxed.

Independent unprompted ASR checks all 24 turns. Seventeen match the strict
case/punctuation comparison; `speech_review.json` explicitly reviews seven
numerical/homophonic spelling differences, with no unresolved textual omissions.
The strict `speech_asr_check.json` remains unchanged, including its nonmatching
result. Twelve low-confidence alignment tokens remain disclosed: nine standalone
question marks and the words `à`, `et`, `des`. **No auditory listening or
pronunciation/accent certification is claimed.** Review the actual audio and
preview before approving production. No production render or publication was
started for TEF.

The completed image/logo revision is
**`builds/tef_canada_a1_preview_r3/pilot.mp4`**, with `pilot_clean.mp4` alongside
it: **189.7917 seconds, 4,555 frames, 720x1280 at 24 fps**. Its fresh run
imports all 24 raw/prepared recordings from r2 byte-for-byte; combined dialogue,
word alignment, lip cues and timing are unchanged. The advertisement replaces
the text card with the same 29-frame hold and 192-frame reading pause, appears
beside the candidate's opening question, and is packed onto the physical task
sheet. Later questions use normal close-ups with the French Compass wall
plaque, verified against the original packed logo bytes and actual decoded
frames.

All 182 Python tests pass. Native image/head/logo checks, both complete movie
decodes, eight decoded image-boundary frames, 18 decoded header samples and
nine reading-prompt/CTA samples pass. The 50 subtitle pages retain the same
1.8333-second minimum and 19.84 characters/second maximum. All **52** prior
masters and **33** original German pipeline sources remain unchanged.
`qa/check_delivery.py`, `qa/evidence_manifest.json`,
`qa/encoded_boundary_contact_sheet.jpg` and `qa/wall_logo_closeup.png` retain
the additional checks and visible evidence. Fresh independent ASR reproduces
the seven reviewed spelling/numeral ambiguities; the 12 alignment warnings
and lack of auditory pronunciation/accent review still apply. This is a
preview for approval, not production or a published video.

The commands used for r3 are below. Its completed run is frozen; use a new
unused build directory for any further revision.

```bash
python3 pipeline.py validate --episode episodes/tef_canada_a1.json
python3 pipeline.py build \
  --episode episodes/tef_canada_a1.json \
  --build builds/tef_canada_a1_preview_r3 \
  --speech-cache-from builds/tef_canada_a1_preview_r2 \
  --profile preview --jobs 4 --until audio

# Run with the configured Qwen runtime, after audio/alignment have succeeded.
"${QWEN_PYTHON:-/home/ronggong/lang/german/.venvs/qwen-tts-test/bin/python}" \
  check_speech.py --build builds/tef_canada_a1_preview_r3

# Only after speech, alignment warnings and caption preflight are reviewed:
python3 pipeline.py build \
  --episode episodes/tef_canada_a1.json \
  --build builds/tef_canada_a1_preview_r3 \
  --speech-cache-from builds/tef_canada_a1_preview_r2 \
  --profile preview --jobs 4
```

`check_speech.py` independently transcribes every prepared turn using cached
faster-whisper-small, the episode's language, CPU int8, no initial prompt and
no prior-text conditioning. It writes `speech_asr_check.json`, records source
hashes and exits nonzero on any normalized difference. Names/numeral differences
need review, not edited pass flags; matching ASR is not a pronunciation/accent
guarantee. It does not download missing models automatically. A supplied report
is included in the frozen manifest; this command is separate from forced
alignment and is not automatically run by `pipeline.py`.

### Short TEF A1 excerpt: under 90 seconds

`episodes/tef_canada_a1_short.json` is the user-requested short adaptation,
not a complete model answer. It keeps ten turns: entrance and task prompt,
formal opening, two linked question/answer exchanges on schedule and price,
and a brief polite close. Equipment, activities, accessibility, transport,
availability and alternative-group questions remain in the source book and
the separate full episode. The source book and earlier full previews are
unchanged.

The opening title is **Atelier informatique**. One fixed
**Section A · Se renseigner** header remains throughout; there is no switch
to “Jeu de rôle”. The six-second ending explicitly reads **Réponse modèle
complète / dans notre livre TEF Canada / Lien Amazon dans le profil**.
The advertisement, printed sheet, French Compass wall plaque, original
reference voices, eight-second reading pause, dialogue gaps and caption
readability limits are retained. Runtime is reduced by removing exchanges,
not speeding up voices or cutting readability/pause time.

The new preview uses `builds/tef_canada_a1_short_preview_r1/`, importing nine
unchanged recordings from r3 and synthesizing only the concise candidate
closing. `source.duration_limit_seconds: 90` records the user's strict limit:
the owned build's `qa/check_delivery.py --audio` must verify
`total_frames < 90 * fps` before Blender. Final checks also require **both
actual encoded movie durations** below 90 seconds, including intro, entrance,
all pauses and the CTA. A production run must reuse the approved short
preview's exact audio/timeline, not the 24-turn full episode.
Short-excerpt posting drafts are in `../posts/tef_canada_a1_short/`.
The delivered preview is
**`builds/tef_canada_a1_short_preview_r1/pilot.mp4`**, with
`pilot_clean.mp4` alongside it. Both actual exports measure
**86.5833 seconds / 2,078 frames, 720x1280 at 24 fps**, with 19
subtitle pages (minimum 1.9167 encoded seconds, maximum 19.5254 characters per
second). This is **54.4% fewer production frames** than the 4,555-frame full
version, with no speed-up of speech. Both movies decode completely. Native
entrance, rigs, speaker cameras, packed desk advertisement, face framing and
wall-logo checks pass. Actual decoded pixels verify the advertisement at both
window boundaries, one fixed header at 25 sampled frames, and the opening
title/reading instructions/CTA at ten samples. The full-size title, book
ending and logo plus both contact sheets were visually inspected.

All 54 earlier masters and 33 original German pipeline sources remain
unchanged. The nine reused recordings retain identical prepared audio,
alignment and lip cues. Fresh independent ASR checks all ten turns; the new
closing matches exactly, while the inherited schedule homophone and numeral
formatting differences remain separately reviewed. Four low-confidence
question-mark tokens remain disclosed; no auditory pronunciation/accent
review is claimed. Frozen export/source hashes, future exact-audio reuse and
the supplementary `qa/evidence_manifest.json` verify. This is a preview for
approval, not production or publication. The full episode and old previews
remain available.

The requested enlarged-image **frame-only** review is in
`builds/tef_canada_a1_image_size_frames_r1/`. `comparison.jpg` shows the old
layouts beside three 720x1280 sample PNGs: `01_full_ad_larger.png` keeps the
whole original at 608px wide instead of 392px; `02_notice_closeup.png` adds
an explicitly labelled detail of all printed notice text; and
`03_dialogue_larger_reference.png` shows that detail beside a same-frame
candidate portrait, with the original subtitle pixels unchanged. The detail
omits only decorative photo/background; the whole-ad sample is uncropped.
These are composited from frozen rendered backgrounds, not newly rendered
cameras or a revised video. The wider graphic/portrait positions are layout
proposals, not approved platform-safe placements. `render_samples.py` and
`review_manifest.json` record crop coordinates, sizes and preservation of
all 56 video masters. No TTS, Blender or full-video job was run, and shared
pipeline/episode behavior stays unchanged pending visual review.

The follow-up frame review is in
`builds/tef_canada_a1_image_size_frames_r2/`. `01_notice_closeup.png` retains
the user-selected reading detail byte-for-byte.
`02_dialogue_notice_below_subtitles.png` places the 608px-wide notice below
the subtitle panel with a 24px gap, removes the old thumbnail and portrait
inset, and retains the original candidate face/framing. Face, subtitle and
header pixels are checked against the original frame. `comparison.jpg`
shows the retained reading detail, previous dialogue proposal and revised
dialogue. Both 720x1280 samples were inspected; all 56 masters, earlier
review files, frozen inputs and live Python sources remain unchanged.
This is still a frame-only proposal, not a revised video or a platform-safe
placement certification; no shared compositor/episode changes were made.

The smaller lower-reference review is in
`builds/tef_canada_a1_image_size_frames_r3/`.
`02_dialogue_compact_notice.png` reduces the notice from 608px to 320px wide,
below the unchanged subtitles and aligned left. Its panel leaves 266px below
and 288px to the right; the selected reading close-up is unchanged.
`comparison.jpg` and `clearance_review.png` show the size change and design
margins. The latter is explicitly not an official platform safe-zone template.
TikTok's current guidance says safe zones depend on captions and format;
Meta's help page required login, so no current Meta geometry was verified.
The reference/check date and limitation are recorded in `review_manifest.json`.
Actual Instagram/TikTok placement review is still needed, particularly for
expanded captions or ad CTA/anchor overlays. Frame/source/master checks pass;
this remains sample-only with no video, speech or shared pipeline changes.
The user selected the 320px lower reference on October 24, 2026. Both authored
TEF episodes now opt into the implemented `notice_detail` layout: the reading
detail is 608x412 at `(56,370)`, and the dialogue detail is 320x216 at
`(104,790)`, below the unchanged subtitles with the original face unobscured.
The source crop is `[236,44,966,538]`; it retains every printed notice line
and removes only decoration. The physical task sheet still uses the whole
original. Default whole-image behavior and German caption output are unchanged.

All 192 Python regressions pass, including actual FFmpeg encoding/decoded
odd-frame transitions, cropped-source comparisons, face visibility and scoped
caption-bound checks. Both TEF configurations validate, and the native
interview fixture passes without synthesizing speech or rendering a movie.
`builds/tef_canada_a1_live_layout_check_20261024/` contains two inspected
720x1280 frames produced by the current ASS/picture compositor on unchanged
rendered backgrounds and the real 86.5833-second speech clock. These are
frame probes, not a new full preview. Earlier movies remain frozen with their
old sizing; any revised full video requires a fresh build. The approved
graphic placement is not a platform safe-zone certification.

The commands below document this now-frozen run. Choose an unused directory
for any further revision.

```bash
python3 pipeline.py validate --episode episodes/tef_canada_a1_short.json
python3 pipeline.py build \
  --episode episodes/tef_canada_a1_short.json \
  --build builds/tef_canada_a1_short_preview_r1 \
  --speech-cache-from builds/tef_canada_a1_preview_r3 \
  --profile preview --jobs 4 --until audio
```

This is an original book-based promotional excerpt, not an official TEF task
or a claim that a full examination lasts under 90 seconds. The Section A
information-seeking framework was checked against the official reference on
October 24, 2026; its wording and official tasks are not reproduced.

`test_profiles.py` checks French TTS/alignment/ASR API wiring using explicit
mocks, cache separation, inline references, localization and inactive-cast
rules. `test_tef_episode.py` checks actual book/voice/cover references, content,
turn-taking and pacing. `test_interview_scene.py` is a tiny **synthetic native
fixture**, not a preview: it bakes nine frames, checks native controls and
hidden objects, and never synthesizes speech or renders images:

```bash
.tools/blender/blender -b --disable-autoexec builds/v2/studio.blend \
  -t 1 --python-exit-code 1 --python test_interview_scene.py \
  -- builds/tef_native_fixture_new
```

Use a new empty fixture directory. The delivered r2 preview also passes the
full entrance and encoded-pixel checks, beyond this synthetic fixture.
Listening/preview approval, production rendering, merging into the DTZ checkout
and publication remain separate later steps.

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

### Book-based Teil 2: pictures and personal experiences

`episodes/teil2_einkaufen.json` adapts **Teil 2, Übung 1: Auf dem Wochenmarkt
einkaufen** and **Übung 7: Angebote im Supermarkt vergleichen**. Lea describes
the market picture, explains her shopping habits and compares her experiences
in Poland with life in Cologne. Samir describes a customer at a supermarket
refrigerator, explains how his family plans purchases and gives a concrete
example of buying more fruit than they could eat. Each candidate receives two
linked follow-ups, not only a picture-description monologue.

The 14-turn script uses the existing cast and 1.7B voices, one corridor
entrance, restrained `describe` gestures, 1.2-second dialogue gaps and the
six-second book CTA. Before **each** description the examiner holds for
1.2 seconds, followed by an eight-second picture-reading card. These learning
pauses are part of the video, not an official examination time allowance.
There is no tips card or requested promotional cut.

```bash
python3 pipeline.py validate --episode episodes/teil2_einkaufen.json

# New preview; stop after alignment first if reviewing voices separately.
python3 pipeline.py build \
  --episode episodes/teil2_einkaufen.json \
  --build builds/teil2_einkaufen_v7_preview_r2 \
  --speech-cache-from builds/teil2_einkaufen_v7_preview_r1 \
  --profile preview --jobs 4 --until audio

# Resume the same unchanged job through rendering and delivery checks.
python3 pipeline.py build \
  --episode episodes/teil2_einkaufen.json \
  --build builds/teil2_einkaufen_v7_preview_r2 \
  --speech-cache-from builds/teil2_einkaufen_v7_preview_r1 \
  --profile preview --jobs 4
```

Posting drafts are in `../posts/dtz_b1_teil2_einkaufen/`. They include the
book-image attribution, advertising and AI disclosures, independent-practice
disclaimer, and full character credits. Production rendering and publication
remain separate approval steps.

The delivered full preview is
`builds/teil2_einkaufen_v7_preview_r2/pilot.mp4`: **153.167 seconds, 3,676
output frames at 24 fps**, using 1,838 native preview poses. The clean review
movie, contact sheet, frozen source snapshots and reports are alongside it.
Independent, unprompted ASR matched all 14 turns after case/punctuation
normalization; this is a plausibility check, not a pronunciation guarantee.
All 36 subtitle pages have at least 1.917 encoded seconds and stay below
19.295 characters per second. The export audits 443 distinct caption states;
actual decoded pixels verify both pictures' reading/description windows,
section changes and the complete 144-frame CTA. Eight low-confidence
word-alignment warnings remain explicitly recorded in `delivery_checks.json`.

The unsuffixed run and `_r1` preserve the earlier audio takes. Two lines were
shortened to satisfy measured subtitle readability; voice settings, speech
rate and approved pause lengths were not changed. Matching recordings were
reused rather than resynthesized. All 45 pre-existing videos remain
byte-identical, and the previous Ausflug, Lerntreffen and Teil 1 caption/acting
plans are unchanged. The final audio is verified for exact reuse in a future
production build, but no production version, promo cut or upload was made.

#### Reusable picture stimuli

Optional `pictures` maps safe IDs to `path`, `candidate`, `label`, `credit`
and `permission`. Paths resolve relative to the authored episode, including
episodes outside this project. This room template supports one assigned
picture per candidate:

```json
"pictures": {
  "wochenmarkt": {
    "candidate": "candidate_a",
    "path": "../assets/pictures/wochenmarkt.jpg",
    "label": "Wochenmarkt",
    "credit": "Your picture attribution",
    "permission": "Your documented reuse permission or license basis"
  }
}
```

An examiner prompt selects `picture` and `picture_card_delay_seconds`; its
`pause_after` must leave positive reading time after that delay. The following
turn must use the same `picture`, action `describe`, the assigned candidate,
and camera `picture_a` or `picture_b`. The repeated reading cards are
independent of animation phases: the second card does not restart the entrance
or require a second instruction phase. Do not combine the initial picture card
with the ordinary text `task_card`.

The default `purpose: "description"` preserves that DTZ behavior. For a
role-play advertisement, set `purpose: "task"`: one examiner reading-card
prompt must immediately precede the assigned candidate's genuine response,
such as `action: "ask"`, using the same picture and picture camera. Do not
label a role-play question as `describe`. Additional candidate references are
optional, must follow the reveal, and use the picture camera. Unmarked turns
retain their normal speaker shot. By default, the task card uses the larger whole-image
box `(104,334)–(496,628)` and localized question-preparation instructions,
not picture-description or personal-experience prompts.

The reading card shows the **whole** image within `(104,344)–(496,558)` on the
720×1280 canvas. During the description, a labelled reference image fits within
`(104,310)–(324,430)`. Separate picture cameras frame the candidate's head to
its right, inside `(336,284)–(504,570)`, clear of both the image and unchanged
31px subtitles. The close speaker cameras return for personal answers.
Default pictures are aspect-fitted, not cropped; dimensions and positions are rounded
to even pixels to match the 4:2:0 overlay grid. Portrait stimuli are letterboxed
within the same rectangles. Full reading cards intentionally cover the room;
description layouts do not cover the candidate's head.

Task advertisements can explicitly opt into `"layout": "notice_detail"` with
`"crop": [left, top, right, bottom]`. The TEF advertisement uses
`[236,44,966,538]`, a labelled 608x412 reading detail and a 320x216 lower
reference. Crop coordinates must be even integers within the source, and the
selected region must be at least 392px in both dimensions. This is not available
for DTZ description pictures; omitting `layout` keeps the whole-image defaults.
Only the named notice graphic/label styles get their own measured audit
rectangles. Ordinary headings, speaker labels, subtitles and CTA retain the
original conservative text-safe bounds and fonts. Source images are not edited.

The exact same source bytes are packed onto the physical table sheets.
Preflight checks image decodability, resolution, metadata references and
measured labels. Build specs hash every picture and the shared
`picture_presentation.py`; frozen deliveries also preserve image copies under
`picture_assets/`. `picture_timing_report.json` records image hashes, bounds
and end-exclusive output-frame windows. The compositor expands native poses
to 24 fps before ASS and timed image overlays.

`review_social.py` compares actual decoded picture pixels with the intended
source at each window's first, middle and final frames, plus both outside
boundary frames. Wrong images, late changes and pictures that fail to clear
are errors, not a successful manifest-only check. Native checks verify packed
image bytes and projected head visibility. `test_teil2_episode.py` also covers
both candidate sequences, preserved pacing, caption holds, image ownership
references, corrupt/missing assets, immutable asset hashes, frozen copies,
portrait fitting and real odd-frame image transitions.

The supplied photographs are unchanged copies of the book's `01.jpg` and
`07.jpg`. On October 22, 2026, the user confirmed rights for promotional
reuse; `assets/pictures/README.md` records the sources and hashes. This does
**not** grant public reuse or put the photographs under the rigs' CC BY 4.0
license. No official exam pictures or official task texts are reproduced.

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
  -m unittest test_build_paths test_episode_config test_teil1_episode test_teil2_episode test_lerntreffen_episode test_entrance test_direction test_social test_audio test_render test_exchange test_profiles test_tef_episode
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

The opt-in `notice_detail` task layout has explicitly scoped exceptions for
its reading graphic and lower reference label/panel. Its audit report records
those rectangles separately, without widening the ordinary text-safe area.
Those user-approved graphics are not certified platform-safe placements.

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

For another computer, see [the migration guide](MIGRATION.md): hardware targets,
Windows/WSL2 versus native-Windows compatibility, external assets, Python
environment recreation and the separate GPU-enablement/validation step.

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
