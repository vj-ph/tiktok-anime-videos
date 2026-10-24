# Moving video generation to another machine

Status checked October 24, 2026. The current tested environment is Ubuntu
24.04.4 LTS under WSL2, using CPU rendering. Native Windows end-to-end execution
and GPU rendering of this project have not been validated.

## Windows and Linux compatibility

| Destination | Recommendation |
| --- | --- |
| Windows 11 with WSL2 and Ubuntu 24.04 | Preferred Windows route; matches the existing Linux workflow. Recreate its dependencies and asset paths. |
| Native Ubuntu 24.04 | Uses the same Linux workflow, with machine-specific setup and validation. |
| Native Windows, directly from PowerShell/CMD | Requires a portability pass and end-to-end testing; not ready out of the box. |

Blender itself supports Windows. The obstacles are in our surrounding setup,
not a need to rewrite the animation:

- `setup_tools.sh` and `setup_characters.sh` use Bash; the tool installer
  downloads Linux Blender and Rhubarb archives.
- `pipeline.py`, `render.py` and `prepare_audio.py` expect Linux-style executable
  locations, rather than Windows `blender.exe`/`rhubarb.exe`.
- `social_captions.py` measures text using fonts under
  `/usr/share/fonts/truetype/dejavu/`.
- The default Qwen interpreter is under `/home/ronggong/...`; external asset
  paths and worktree symlinks also need resolving on the destination.

For WSL, install/update WSL2 and select Ubuntu 24.04 using Microsoft's
installation instructions. Run the Linux pipeline inside Ubuntu, not directly
in PowerShell. Keep the working repository and rendered frames inside the
Linux filesystem, such as `/home/<user>/...`, rather than `/mnt/c/...`, for
Linux filesystem performance. Check `free -h` and `nproc` inside Ubuntu:
WSL's configured memory/CPU allocation can differ from the host's resources.

## Hardware planning

These are practical planning targets, not measured minimum requirements or
promised render speeds for our scene.

| Resource | Suggested target |
| --- | --- |
| CPU | Modern 8-core CPU or better |
| RAM | 32 GB recommended; 64 GB provides more parallel-work/Windows-host headroom |
| GPU | Optional; NVIDIA RTX with 16 GB VRAM is a preferred GPU-rendering target |
| Storage | 500 GB-1 TB SSD, with roughly 100 GB free for active work, tools and caches |

CPU-only generation already works. The current machine exposes 16 logical
processors and about 31.3 GiB RAM to Linux. GPU memory usage for this scene has
not been measured; do not treat 16 GB as a proven minimum or fit guarantee.
Blender's general recommendation is 32 GB RAM and 8 GB VRAM, rather than a
project-specific measurement.

For scale, the existing short TEF preview directory occupies about 674 MiB,
the reusable base scene about 330 MiB, and the local assets directory about
346 MiB. These are current examples, not total migration sizes: production
frames, model caches and multiple retained builds need additional storage.

## Code and assets to transfer

A Git clone alone is insufficient. Restore:

- The intended source commit. The TEF/layout merge is `f698e75`; use that
  commit or a later reviewed revision containing it. Verify the destination
  receives the chosen code; a remote clone cannot include unpushed local changes.
- `builds/v2/studio.blend`, the reusable room scene, and the original Snow/Rain
  character libraries/textures under `assets/studio/`.
- The chosen episode's covers, pictures, logo, voice-reference WAVs/transcripts
  and any other declared external dependencies. Preserve their permissions
  and attribution records.
- Selected verified build/audio/alignment files if reusing speech, plus any
  historical deliveries that should be available on the new machine.

`builds/`, tools and downloaded rig libraries are ignored/generated resources.
TEF deliveries remain in the separate `tiktok_anime_videos_tef` worktree;
merging its code did not copy those builds into the main checkout.

Do not copy a linked worktree's `.git` pointer or machine-specific symlinks
and assume it is a standalone installation. Restore real files or recreate
valid links. Preserve the German/French sibling-directory structure expected
by authored episode paths, or adjust a new authored episode to the destination.

Keep frozen deliveries unchanged, including their manifests, recorded paths
and hashes. The current relocation helpers are not a general cross-machine
path remapper. Use a fresh build directory for changed source, configuration
or asset paths; do not rewrite frozen receipts to make an old run resume.
Verified audio reuse must pass the existing consistency checks.

## Software environment

Match the current pipeline before introducing upgrades:

- Python 3.12, FFmpeg/ffprobe with libass and libx264, and DejaVu Sans fonts.
- Portable Blender 4.5.9 LTS and Rhubarb 1.14.0. On Linux/WSL,
  `bash setup_tools.sh` restores pinned, checksum-verified tools;
  `bash setup_characters.sh` restores pinned, checksum-verified rig libraries.
  These scripts do not restore the reusable base room scene or voice assets.
- A recreated Python environment matching the working Qwen/PyTorch,
  WhisperX, audio and image dependencies. Record source-machine package
  versions and preserve any local package patches; installing the latest
  packages is not an equivalent environment.

Select the recreated interpreter using `QWEN_PYTHON` or `--qwen-python`.
Do not copy an old virtual environment and assume its embedded paths and
binaries work on another OS.

Render-only work can reuse prepared speech without loading the Qwen model.
However, the unified pipeline still checks its audio Python packages and
declared reference assets, even when reusing audio. New speech additionally
needs Qwen3-TTS 1.7B Base, its tokenizer, the required alignment/ASR models and
the original reference voices. Preserve the approved speech settings; changing
speech device or precision requires a separate audio check.

## GPU rendering is a separate setup step

Cycles supports NVIDIA CUDA/OptiX, including RTX ray-tracing acceleration.
Our current render workers do not expose a GPU-backend selection option.
Buying a GPU or installing WSL does not automatically make this pipeline use
it: explicitly configure the backend and selected devices, then verify actual
device use in Blender's render logs.

For NVIDIA under WSL2, install the supported NVIDIA driver on the Windows
host. NVIDIA documents CUDA access through that driver; do not install a Linux
display driver inside WSL. CUDA availability is not proof that this scene's
OptiX/rendering configuration has passed.

The existing default is four Blender workers with four CPU threads each.
For a single GPU, start validation with one render worker rather than blindly
running four processes that compete for VRAM. Measure representative wide,
entrance and dialogue frames before choosing worker count or estimating cost.
The earlier sphere benchmark is not a render-time prediction for this episode.

## Destination acceptance

Validate the selected authored episode with `pipeline.py validate` using the
new interpreter, run the focused episode tests, and bake/check a fresh scene.
Inspect a few rendered frames before starting a full movie. Check rig/textures,
logo, physical task sheet, notice crop, captions and image transitions.

Keep the initial migration render-only where possible, reusing checked speech
and timing. Recheck audio consistency, encoded duration, subtitles and exports
on the destination. No new machine, GPU or native-Windows performance claim is
established until that destination has actually passed these checks.

## Official references

Checked October 24, 2026:

- [Blender requirements](https://www.blender.org/download/requirements/)
- [Blender 4.5 GPU rendering](https://docs.blender.org/manual/en/4.5/render/cycles/gpu_rendering.html)
- [Microsoft WSL commands](https://learn.microsoft.com/en-us/windows/wsl/basic-commands)
- [Microsoft WSL filesystem guidance](https://learn.microsoft.com/en-us/windows/wsl/filesystems)
- [Microsoft WSL resource configuration](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)
- [NVIDIA CUDA on WSL](https://docs.nvidia.com/cuda/wsl-user-guide/)
- [Qwen3-TTS environment and model setup](https://github.com/QwenLM/Qwen3-TTS)
