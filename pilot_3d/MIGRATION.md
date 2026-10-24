# Video generation on Windows and Linux/WSL2

Status: October 24, 2026. Both operating systems use `pipeline.py`; no WSL is
required for native Windows execution. The original delivered videos were
produced on Ubuntu 24.04 under WSL2 with CPU rendering.

## What has been verified on this Windows machine

- Native Blender 4.5.9 and Rhubarb 1.14.0 install and execute.
- Cycles discovers the AMD Radeon 860M through HIP. The full TEF A1 preview
  scene fits GPU memory and all 2,278 native frames have rendered with two
  HIP workers (360x640, two samples, animation on twos).
- Portable unit checks, pipeline checkpoint tests, French speech-API wiring
  with mocked models, real FFmpeg caption exports and encoded TEF
  advertisement transitions pass.
- The host reports about 55.6 GiB RAM and 16 logical processors.
- The supplied scene, cover, rigs and reference voices are installed. All
  24 French turns synthesized with Qwen3-TTS Base; French alignment, caption
  preflight and scene checks passed. The completed delivery is
  `builds/tef_canada_a1_windows_preview_r1/pilot.mp4`; the companion
  `pilot_clean.mp4` is also available.
- Both 720x1280 H.264/yuv420p masters decode successfully: 4,555 output frames,
  24 fps, 189.791667 seconds. All 19 delivery-file and 19 source-snapshot
  hashes verify. Encoded contact-sheet inspection found no obvious defects.
  All 50 caption pages pass the reading policy (minimum 1.833 seconds,
  maximum 19.84 characters/second); encoded picture transitions pass.
- Independent ASR matches 17/24 turns strictly. Secondary ASR resolves
  "formulaires"; retained disagreements include number formatting and
  homophonic spellings. `speech_review.json` records the evidence and
  limitations; this is not a listening or pronunciation certification.

The Windows/Linux GitHub Actions matrix in `.github/workflows/portability.yml`
runs the portable regressions without production assets or model downloads.
The new Linux job has not been executed locally on this Windows host.

## TEF Canada resource checklist

Git contains both `episodes/tef_canada_a1.json` and
`episodes/tef_canada_a1_short.json`, the advertisement
`assets/pictures/tef_canada_a1.jpg`, its crop/layout, the French Compass logo,
dialogue scripts, inline reference transcripts and posting drafts.

| Resource | How to obtain it |
| --- | --- |
| `builds/v2/studio.blend` | Copy the reusable, approved room scene from the original machine. This generated resource is not in Git; setup does not recreate it. |
| TEF speaking-book cover, `speaking.jpg` | Copy from `french_exam_books/tef_canada/speaking/` and point the authored episode's `book_cover` at it. The German `assets/book-cover.jpg` is not a substitute. |
| `fr_fr_conversation_f01.wav` | Copy the candidate reference from `tef_canada/listening/audio/voices/references/`. Keep the matching inline reference text unchanged. |
| `fr_fr_service_m01.wav` | Copy the examiner reference from the same location. Keep its inline reference text unchanged. |
| Snow/Rain rigs and textures | Download with `python setup_runtime.py --only characters`, or transfer the original complete `assets/studio/snow-v4/` and `rain-v3/` trees. |
| Speech environment and model caches | Recreate PyTorch/torchaudio, Qwen-TTS, WhisperX and dependencies; restore/download Qwen3-TTS 1.7B Base, its 12Hz tokenizer and French alignment model. |
| Original package versions and local patches | Export from the working WSL environment if reproducing the original speech behavior matters. `requirements.txt` is not a production lockfile. |

`book.md`, `voices.json` and the original advertisement/logo sources are useful
for provenance and the source-comparison tests, but are not read by the build
runtime: the dialogue, reference texts and approved image/logo copies are
already in this repository.

For unchanged speech, optionally copy the complete verified TEF build from the
old `tiktok_anime_videos_tef` worktree, including raw audio/cache sidecars,
timeline, alignment and export manifest. Copying only `dialogue.wav` is not
enough for `--reuse-audio`. Historical absolute Linux paths are not generally
remapped to Windows: keep frozen records intact, and use fresh synthesis if
the exact reuse checks cannot resolve their dependencies.

## Shared setup

Use Python 3.12 and FFmpeg/ffprobe with libass and libx264. Keep a separate
virtual environment for each OS; never copy a Linux environment to Windows.
For an already tested production environment, recreate its recorded versions
and patches instead of silently upgrading.

### FFmpeg compatibility on this Windows machine

The preinstalled January 31, 2026 FFmpeg git build propagates full-range JPEG
metadata through the TEF picture overlays: requesting `-pix_fmt yuv420p`
still produces a stream probed as `yuvj420p`. The strict delivery review
rejects this; do not weaken that check or merely relabel the encoded range.
A 12-frame reproduction with the same PNG/JPEG overlay passes using FFmpeg
6.1.1. Install the optional compatibility build and select it for this
PowerShell session:

```powershell
python setup_runtime.py --only ffmpeg
$env:PATH = (Join-Path (Get-Location) ".tools\windows\ffmpeg") + ";" + $env:PATH
ffmpeg -version
```

The archive is SHA-256 pinned against Microsoft's WinGet manifest and comes
from its publisher, GyanD/codexffmpeg. This does not replace the system FFmpeg
or change pipeline source/asset hashes. Resume the same build command to
reuse completed stages and verified frames. Keep rejected outputs/logs in
`qa` when invalidating an unsuccessful export; do not edit checkpoint hashes.
Linux uses the separately installed FFmpeg/ffprobe; its new CI configuration
has not been executed on this Windows host.

New environments can use `requirements.txt` with `constraints-preview.txt` as
a bootstrap. The pinned Qwen 0.1.1 / WhisperX 3.8.6 / torch 2.8 combination
retains torchaudio's alignment pipeline API; the transitive constraints avoid
incompatible or unavailable upgrades. This is not the original WSL lockfile.
Install matching
PyTorch/torchaudio wheels for the intended hardware first if needed. The
pipeline preserves float32/SDPA speech defaults; FlashAttention is not required
by this project's synthesis code. New model/package/device combinations need
audio review. Model downloads require internet access unless caches are restored.

### Shared model caches

Model weights belong outside the checkout and virtual environment so other
projects can reuse them. This Windows user's shared locations are:

| Setting | Location |
| --- | --- |
| `HF_HOME` | `%USERPROFILE%\.cache\huggingface` |
| Hugging Face snapshots | `%USERPROFILE%\.cache\huggingface\hub` |
| `TORCH_HOME` | `%USERPROFILE%\.cache\torch` |
| French alignment checkpoint | `%USERPROFILE%\.cache\torch\hub\checkpoints\wav2vec2_voxpopuli_base_10k_asr_fr.pt` |

`HF_HOME` and `TORCH_HOME` are configured as Windows **user** environment
variables, not project-specific settings. New terminals inherit them; existing
terminals can set them explicitly before importing Hugging Face/PyTorch:

```powershell
$env:HF_HOME = Join-Path $env:USERPROFILE ".cache\huggingface"
$env:TORCH_HOME = Join-Path $env:USERPROFILE ".cache\torch"
```

Qwen Base and its standalone tokenizer use their normal Hub IDs:
`Qwen/Qwen3-TTS-12Hz-1.7B-Base` and
`Qwen/Qwen3-TTS-Tokenizer-12Hz`. Keep the Base model's bundled
`speech_tokenizer/` files too. The shared Hub cache has a
`tef_model_downloads.json` manifest under `HF_HOME` recording downloaded
revisions, paths, sizes and file hashes. The Torch checkpoint has a
corresponding download receipt beside it.

Other native Windows projects using the same cache settings can load these
IDs without separate model copies. For WSL to reuse the **same physical
files**, explicitly point its `HF_HOME` and `TORCH_HOME` at the corresponding
Windows cache directories through `/mnt/c/Users/...`; Windows environment
variables and cache paths are not automatically valid Linux paths. Keep Python
environments separate, even when weights are shared. Do not let concurrent
downloads from different OSes write the same cache entry.
Offline Hub cache discovery is verified. However, Qwen 0.1.1 with Transformers
4.57.3 requests model metadata during tokenizer initialization even when all
weights are cached. Do not set `HF_HUB_OFFLINE=1` for the current pipeline's
model-ID loading path; successful offline file discovery is not an end-to-end
offline inference test. The metadata request does not perform remote synthesis.

The Qwen model cards declare Apache-2.0. The existing French VoxPopuli
alignment checkpoint is documented by torchaudio as **CC BY-NC 4.0**.
Downloading it does not establish that it is suitable for this project's
commercial promotional workflow; do not treat it as commercially cleared.

Native Windows, from the repository root:

```powershell
Set-Location pilot_3d
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -c constraints-preview.txt
.\.venv\Scripts\python.exe setup_runtime.py
.\.venv\Scripts\python.exe runtime_config.py --render-device HIP
```

Linux/WSL2, from the repository root:

```bash
cd pilot_3d
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -c constraints-preview.txt
.venv/bin/python setup_runtime.py
.venv/bin/python runtime_config.py --render-device CPU
```

The installer is standard-library Python and selects Windows x64 or Linux x64
archives with pinned SHA-256 checksums. Use `--only tools`, `--only fonts` or
`--only characters` to install one group. It does not install FFmpeg, drivers,
Python packages, the room scene or private voice/cover assets.
If the original `assets/studio/snow-v4.zip` and `rain-v3.zip` are supplied,
the installer checks their pinned hashes and uses them without downloading.

Tools are stored separately under `.tools/windows/` and `.tools/linux/`.
Existing Linux tools under `.tools/blender/` and `.tools/rhubarb/` remain valid.
The old Bash installers also remain available on Linux.
DejaVu fonts and their license install under `.tools/fonts/`; the same fonts
are used for Pillow measurement and staged into each build for FFmpeg/libass.
No substitution with Arial or another metrically different font is made.

| Override | Purpose |
| --- | --- |
| `QWEN_PYTHON` or `--qwen-python` | Select the speech/alignment Python interpreter. Otherwise local `.venv`, legacy Linux environment, then current interpreter. |
| `BLENDER_EXE` | Full native Blender executable path; overrides downloaded tools/PATH. |
| `RHUBARB_EXE` | Full native Rhubarb executable path. |
| `DEJAVU_FONT_DIR` | Directory containing both `DejaVuSans.ttf` and `DejaVuSans-Bold.ttf`. |

## Portable TEF asset paths

The authored TEF episodes still reference the original sibling French-book
tree. Those relative paths do not match this checkout's new location.
Do not rewrite historical build snapshots to fix them.

Create a new authored copy **in the same `episodes` directory**, for example
`tef_canada_a1.local.json`, and change just these runtime asset references:

- `book_cover` to `../assets/tef/speaking.jpg`.
- `voices.candidate_a.audio` to `../assets/tef/fr_fr_conversation_f01.wav`.
- `voices.examiner.audio` to `../assets/tef/fr_fr_service_m01.wav`.

Copy the supplied files to those locations. Keep
`scene.base_scene: "../builds/v2/studio.blend"` and restore the scene there.
JSON asset paths use `/` as in the shipped episodes; Python resolves them
relative to the episode on either OS. No machine-specific absolute paths are
needed in this authored copy. Source/provenance metadata remains unchanged.

Use different new build directories per OS and backend. A single live build
must not be written by Windows and WSL simultaneously. Builds freeze resolved
absolute paths, source hashes, font hashes and selected devices, so switching
OS, content, code, font bytes or devices requires a fresh directory.

After supplying the missing assets and ML environment, on Windows:

```powershell
.\.venv\Scripts\python.exe pipeline.py validate --episode episodes\tef_canada_a1.local.json --render-device HIP
.\.venv\Scripts\python.exe pipeline.py build --episode episodes\tef_canada_a1.local.json --build builds\tef_windows_preview --profile preview --render-device HIP --speech-device cpu --jobs 1 --until scene
.\.venv\Scripts\python.exe pipeline.py build --episode episodes\tef_canada_a1.local.json --build builds\tef_windows_preview --profile preview --render-device HIP --speech-device cpu --jobs 1
```

On Linux/WSL2:

```bash
.venv/bin/python pipeline.py validate --episode episodes/tef_canada_a1.local.json
.venv/bin/python pipeline.py build --episode episodes/tef_canada_a1.local.json --build builds/tef_wsl_preview --profile preview --render-device CPU --speech-device cpu --jobs 1
```

These commands are a destination procedure, not a claim that a full TEF video
has already been generated here. Approve audio, scene checks and a preview
before selecting `--profile production` in another new build.

## GPU rendering versus GPU speech

`--render-device` selects Cycles `CPU` (default), `HIP`, `CUDA`, `OPTIX` or
`ONEAPI`. A requested unavailable GPU raises an error; there is no silent CPU
fallback. Workers print selected backend/device names into their render logs
and use an explicit output path rather than a saved scene's old location.
Backend changes invalidate direct-render checkpoints.

For this machine, native Windows HIP has passed a small rendering check.
Start with one worker; do not assume the same memory fit or speed for the
full scene. The graphics adapter is integrated; Windows' reported AdapterRAM
is not a reliable measurement of available dedicated VRAM.

`--speech-device cpu` remains independent of HIP and is the initial choice
here. Blender's HIP success does not establish AMD PyTorch/Qwen acceleration.
Do not use `cuda:0` on this machine merely because Blender sees a GPU.
On a compatible NVIDIA/PyTorch setup, `--speech-device cuda:0` is explicit and
becomes part of build/cache identity; recheck the resulting speech.
Alignment and independent ASR checks retain their existing CPU behavior.

For WSL GPU use, install the vendor-supported Windows host driver and check
support inside that WSL distribution. A successful native Windows HIP test
does not prove HIP is available under WSL. NVIDIA documents its separate WSL
CUDA setup; do not install a Linux display driver inside WSL.

## Validation without private assets

Install `requirements-test.txt`, restore fonts, then run:

```powershell
python -X utf8 -m unittest test_runtime test_audio test_direction test_entrance test_build_paths test_render test_social test_profiles test_episode_config.PipelineCheckpointTests test_tef_episode.TefEpisodeTests.test_real_encoded_task_card_and_reference_change_on_exact_odd_frames
```

The same command works in Linux. The existing full test discovery also
includes production-asset and Blender-scene tests; those need their original
resources and cannot all pass in a bare clone.

Optional actual Blender frame check, using the local environment on Windows:

```powershell
$env:BLENDER_SMOKE_TEST = "1"
$env:BLENDER_TEST_DEVICE = "HIP"
.\.venv\Scripts\python.exe -X utf8 -m unittest test_runtime.BlenderSmokeTests
```

## Official references

- [Blender 4.5 GPU rendering](https://docs.blender.org/manual/en/4.5/render/cycles/gpu_rendering.html)
- [Blender 4.5.9 checksums](https://download.blender.org/release/Blender4.5/blender-4.5.9.sha256)
- [Rhubarb 1.14.0](https://github.com/DanielSWolf/rhubarb-lip-sync/releases/tag/v1.14.0)
- [DejaVu 2.37 fonts](https://github.com/dejavu-fonts/dejavu-fonts/releases/tag/version_2_37)
- [Qwen3-TTS environment and models](https://github.com/QwenLM/Qwen3-TTS)
- [PyTorch installation](https://pytorch.org/get-started/locally/)
- [NVIDIA CUDA on WSL](https://docs.nvidia.com/cuda/wsl-user-guide/)
- [Microsoft WSL filesystem guidance](https://learn.microsoft.com/en-us/windows/wsl/filesystems)
