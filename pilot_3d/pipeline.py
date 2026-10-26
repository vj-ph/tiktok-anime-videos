#!/usr/bin/env python3
"""Validate or build an episode-driven exam-room video without editing Python."""

import argparse
from contextlib import nullcontext
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from build_paths import build_directory, resolve_build_reference
from episode_config import PROFILES, check_timeline, read_episode, validate_template
from episode_profiles import language_profile
from scene_dressing import asset_files as dressing_asset_files
from runtime_config import RENDER_DEVICES, RENDER_JOBS, check_render_device, font_path, qwen_python, tool_path
from generation_runtime import GenerationRun, generation_job, run_process, stage_completed
from prepare_audio import (DEFAULT_TTS_THREADS, atomic_json, atomic_text, content_hash, inspect_wav,
                           load_audio_cache, make_cache_payload, sha256_file)

SOURCES = ("pipeline.py", "runtime_config.py", "generation_runtime.py", "build_paths.py", "episode_config.py", "episode_profiles.py", "picture_presentation.py", "prepare_audio.py", "align_words.py", "check_speech.py",
           "produce_v4.py", "render.py", "social_captions.py", "review_social.py",
           "check_v4_scene.py", "studio_characters.py", "polish_exchange.py",
           "scene_direction.py", "scene_dressing.py", "entrance.py", "build_scene.py")
STAGES = ("audio", "alignment", "scene", "scene_checks", "frames", "export", "review")


def preflight(path):
    from PIL import Image
    from social_captions import cover_bounds, validate_layout

    episode = read_episode(path)
    if episode.get("schema_version") != 1:
        raise ValueError("The unified pipeline requires schema_version=1; use the documented episode examples.")
    validate_template(episode, check_assets=True)
    validate_layout(episode)
    for name in ("torch", "qwen_tts", "whisperx", "torchaudio", "soundfile"):
        if importlib.util.find_spec(name) is None:
            raise ValueError(f"Missing Python package {name}; select the configured TTS runtime with --qwen-python.")
    for name in ("ffmpeg", "ffprobe"):
        if shutil.which(name) is None:
            raise FileNotFoundError(f"Required executable not found: {name}")
    for name in ("blender", "rhubarb"):
        if not os.access(tool_path(name), os.X_OK):
            raise FileNotFoundError(f"Required executable not available: {tool_path(name)}")
    if episode["outro_seconds"] > 0:
        with Image.open(episode["book_cover"]) as image:
            image.verify()
        cover_bounds(episode["book_cover"])
    if episode["scene"].get("wall_logo"):
        with Image.open(episode["scene"]["wall_logo"]) as image:
            image.verify()
    return episode


def run_command(command, log):
    with log.open("w") as output:
        result = run_process(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"Stage failed ({result.returncode}); see {log}\n"
                           + "\n".join(log.read_text(errors="replace", encoding="utf-8").splitlines()[-30:]))


def caption_preflight(build, episode, with_promo):
    from produce_v4 import plan_promo
    from social_captions import audit_ass, make_ass, write_caption_timing

    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    check_timeline(episode, timeline)
    ass = make_ass(episode, timeline)
    folder = build / "preflight"
    folder.mkdir(exist_ok=True)
    atomic_text(folder / "captions.ass", ass)
    audit_ass(folder, ass)
    write_caption_timing(folder, episode, timeline)
    if with_promo:
        promo_episode, promo_timeline, *_ = plan_promo(episode, timeline)
        make_ass(promo_episode, promo_timeline)


def freeze_delivery(build):
    snapshot = build / "source_export"
    snapshot.mkdir(exist_ok=True)
    for name in SOURCES:
        shutil.copy2(ROOT / name, snapshot / name)
    outputs = ("pilot.mp4", "pilot_clean.mp4", "captions.ass", "subtitles.srt",
               "dialogue.wav", "timeline.json", "episode.json", "scene_manifest.json",
               "frames_manifest.json", "publishing_caption.txt", "CREDITS.txt",
               "subtitle_timing_report.json", "safe_zone_report.json", "delivery_checks.json")
    outputs += tuple(name for name in ("audio_reuse.json", "word_alignment.json", "scene_checks.json",
                                      "speech_asr_check.json")
                     if (build / name).is_file())
    episode = read_episode(build / "episode.json")
    for path in dressing_asset_files(episode, verify=True):
        name = f"dressing_assets/{path.name}"
        (build / "dressing_assets").mkdir(exist_ok=True)
        shutil.copy2(path, build / name)
        outputs += (name,)
    if episode.get("pictures"):
        assets = build / "picture_assets"
        assets.mkdir(exist_ok=True)
        for key, picture in episode["pictures"].items():
            name = f"picture_assets/{key}{Path(picture['path']).suffix.lower()}"
            shutil.copy2(picture["path"], build / name)
            outputs += (name,)
        outputs += ("picture_timing_report.json",)
    atomic_json(build / "export_manifest.json", {
        "files_sha256": {name: sha256_file(build / name) for name in outputs},
        "source_sha256": {name: sha256_file(snapshot / name) for name in SOURCES},
        "credits_policy": "Publish with publishing_caption.txt; rig attribution is not baked into the video.",
    })


def audio_reuse_spec(episode, source):
    from align_words import validate_words

    source = resolve_build_reference(source).resolve(strict=True)
    export = json.loads((source / "export_manifest.json").read_text(encoding="utf-8"))
    recorded = export.get("files_sha256", export.get("input_files_sha256", {}))
    timeline = json.loads((source / "timeline.json").read_text(encoding="utf-8"))
    check_timeline(episode, timeline)
    if any(episode[key] != timeline[key] for key in ("intro_seconds", "outro_seconds")):
        raise ValueError("Audio reuse requires unchanged intro/outro durations.")
    hashes = {}
    for name in ("dialogue.wav", "timeline.json"):
        digest = sha256_file(source / name)
        if recorded.get(name) != digest:
            raise ValueError(f"Audio reuse source is not a verified delivery: {source / name}")
        hashes[name] = digest
    info = inspect_wav(source / "dialogue.wav")
    if info["sample_rate"] != 48000 or info["frames"] * timeline["fps"] != timeline["total_frames"] * 48000:
        raise ValueError("Audio reuse source does not match its exact video clock.")
    alignment = json.loads((source / "word_alignment.json").read_text(encoding="utf-8"))
    if alignment.get("provenance", {}).get("language") != episode.get("language", "de"):
        raise ValueError("Audio reuse requires matching alignment language.")
    expected = {"provenance": timeline["word_alignment"], "turns": [
        {key: turn[key] for key in ("id", "start", "words", "alignment_key")} for turn in timeline["turns"]]}
    if alignment != expected:
        raise ValueError("Audio reuse alignment sidecar differs from the verified timeline.")
    hashes["word_alignment.json"] = sha256_file(source / "word_alignment.json")
    cache_hashes = {}
    for turn in timeline["turns"]:
        validate_words(turn["words"], turn["text"], turn["wav_duration"])
        raw = resolve_build_reference(turn["raw_audio"])
        metadata = raw.with_suffix(".cache.json")
        saved = json.loads(metadata.read_text(encoding="utf-8"))
        voice = episode["voices"][turn["speaker"]]
        settings = saved["payload"]["settings"]
        if settings.get("language") != language_profile(episode)["tts"]:
            raise ValueError("Audio reuse requires matching synthesis language.")
        payload = make_cache_payload(turn, Path(voice["audio"]),
                                     Path(voice["transcript"]) if "transcript" in voice else None,
                                     settings, reference_text=voice.get("reference_text"))
        if saved["payload"] != payload or load_audio_cache(raw, payload) is None:
            raise ValueError(f"Turn {turn['id']}: reused speech has different text/reference voice or corrupt audio.")
        cache_hashes[str(metadata)] = sha256_file(metadata)
    return {"source": str(source), "files_sha256": hashes, "voice_cache_sha256": cache_hashes,
            "policy": "Exact full dialogue and measured alignment copied; no resynthesis or retiming."}


@generation_job
def build_episode(path, build, profile="preview", jobs=4, with_promo=False, until="export",
                  reuse_audio=None, speech_cache_from=None, render_device="CPU", speech_device="cpu"):
    from render import valid_frame

    episode = preflight(path)
    if render_device != "CPU":
        check_render_device(render_device)
    build = build_directory(build)
    if build == ROOT or build in ROOT.parents:
        raise ValueError("Use a dedicated output directory, not the project or an ancestor.")
    if speech_cache_from is not None:
        speech_cache_from = resolve_build_reference(speech_cache_from).resolve(strict=True)
        if speech_cache_from == build or not (speech_cache_from / "audio").is_dir():
            raise ValueError("--speech-cache-from must name another build containing an audio directory.")
        if reuse_audio is not None:
            raise ValueError("Choose either exact --reuse-audio or raw --speech-cache-from, not both.")
    spec = {"episode": episode, "profile": profile,
            "render_device": render_device, "speech_device": speech_device,
            "base_scene_sha256": sha256_file(resolve_build_reference(episode["scene"]["base_scene"])),
            "asset_sha256": {value: sha256_file(Path(value)) for value in (
                [voice[field] for voice in episode["voices"].values() for field in ("audio", "transcript")
                 if field in voice]
                + ([episode["book_cover"]] if episode["outro_seconds"] > 0 else [])
                + [str(font_path()), str(font_path(bold=True))]
                + [picture["path"] for picture in episode.get("pictures", {}).values()]
                + ([episode["scene"]["wall_logo"]] if episode["scene"].get("wall_logo") else [])
                + [str(value) for value in dressing_asset_files(episode, verify=True)])},
            "code_sha256": {name: sha256_file(ROOT / name) for name in SOURCES}}
    if reuse_audio is not None:
        spec["reuse_audio"] = audio_reuse_spec(episode, reuse_audio)
    state_path = build / "pipeline_state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state["spec"] != spec:
            raise ValueError("Build belongs to different episode/settings/source code. Use a new build directory.")
        if read_episode(build / "episode.json") != episode:
            raise ValueError("Build episode snapshot changed. Use a new build directory.")
    else:
        if build.exists() and any(build.iterdir()):
            raise ValueError("Output directory is nonempty and is not a matching pipeline build; choose a new directory.")
        build.mkdir(parents=True, exist_ok=True)
        state = {"spec": spec, "episode_file": str(resolve_build_reference(path)), "stages": {},
                 "speech_cache_from": str(speech_cache_from) if speech_cache_from is not None else None}
        atomic_json(build / "episode.json", episode)
        atomic_json(state_path, state)
    snapshot = build / "episode.json"
    python = sys.executable
    blender = tool_path("blender")

    def step(name, action, outputs, *, force=False):
        previous = state["stages"].get(name)
        if not force and previous is not None and all(
                (build / value).is_file() and sha256_file(build / value) == digest
                for value, digest in previous["outputs"].items()):
            print(f"{name}: using verified checkpoint", flush=True)
            stage_completed(name, reused=True, force=True)
            return
        print(f"{name}: running", flush=True)
        started = time.monotonic()
        for downstream in STAGES[STAGES.index(name):]:
            state["stages"].pop(downstream, None)
        atomic_json(state_path, state)
        action()
        state["stages"][name] = {"seconds": time.monotonic() - started,
                                "outputs": {value: sha256_file(build / value) for value in outputs}}
        atomic_json(state_path, state)
        stage_completed(name, force=True)

    def command(name, args):
        return lambda: run_command(args, build / f"pipeline_{name}.log")

    def copy_reused_audio():
        receipt = spec["reuse_audio"]
        source = Path(receipt["source"])
        for name in ("dialogue.wav", "timeline.json"):
            if sha256_file(source / name) != receipt["files_sha256"][name]:
                raise ValueError(f"Audio source changed during reuse: {source / name}")
        shutil.copy2(source / "dialogue.wav", build / "dialogue.wav")
        shutil.copy2(source / "timeline.json", build / "audio_timeline.json")
        for source_name, target_name in (("dialogue.wav", "dialogue.wav"), ("timeline.json", "audio_timeline.json")):
            if sha256_file(build / target_name) != receipt["files_sha256"][source_name]:
                raise ValueError(f"Audio changed while copying: {source / source_name}")
        atomic_json(build / "audio_reuse.json", receipt)

    def align():
        if reuse_audio is not None:
            receipt = spec["reuse_audio"]
            source = Path(receipt["source"])
            if sha256_file(source / "word_alignment.json") != receipt["files_sha256"]["word_alignment.json"]:
                raise ValueError("Source alignment changed during reuse.")
            shutil.copy2(source / "word_alignment.json", build / "word_alignment.json")
            shutil.copy2(build / "audio_timeline.json", build / "timeline.json")
            return
        shutil.copy2(build / "audio_timeline.json", build / "timeline.json")
        run_command([python, ROOT / "align_words.py", "--build", build], build / "pipeline_alignment.log")

    if reuse_audio is not None:
        step("audio", copy_reused_audio, ("dialogue.wav", "audio_timeline.json", "audio_reuse.json"))
    else:
        audio_args = [python, ROOT / "prepare_audio.py", "--episode", snapshot,
                      "--output-dir", build, "--threads", str(DEFAULT_TTS_THREADS), "--device", speech_device]
        if speech_cache_from is not None:
            audio_args += ["--speech-cache-from", speech_cache_from]
        step("audio", command("audio", audio_args),
             ("dialogue.wav", "audio_timeline.json"))
    step("alignment", align, ("timeline.json", "word_alignment.json"))
    caption_preflight(build, episode, with_promo)
    if until == "audio":
        return build
    step("scene", command("scene", [blender, "-b", "--disable-autoexec",
                                   resolve_build_reference(episode["scene"]["base_scene"]),
                                   "-t", "4", "--python-exit-code", "1", "--python", ROOT / "produce_v4.py",
                                   "--", "scene", "--episode", snapshot, "--build", build, "--profile", profile]),
         ("studio.blend", "scene_manifest.json"))
    step("scene_checks", command("scene_checks", [blender, "-b", "--disable-autoexec", build / "studio.blend",
                                                 "-t", "2", "--python-exit-code", "1", "--python",
                                                 ROOT / "check_v4_scene.py", "--", build]), ("scene_checks.json",))
    if until == "scene":
        return build
    manifest = json.loads((build / "scene_manifest.json").read_text(encoding="utf-8"))
    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    incomplete = any(not valid_frame(build / "frames" / f"frame_{frame:04d}.png",
                                     manifest["width"], manifest["height"])
                     for frame in range(1, timeline["total_frames"] + 1, manifest["motion_step"]))
    step("frames", command("frames", [python, ROOT / "render.py", "frames", "--episode", snapshot,
                                      "--build", build, "--jobs", str(jobs), "--render-device", render_device]),
         ("frames_manifest.json",), force=incomplete)
    if any(sha256_file(ROOT / name) != digest for name, digest in spec["code_sha256"].items()):
        raise ValueError("Pipeline code changed during this build; use a new build directory.")
    if any(sha256_file(Path(name)) != digest for name, digest in spec["asset_sha256"].items()):
        raise ValueError("An episode asset changed during this build; use a new build directory.")
    step("export", command("export", [python, ROOT / "render.py", "mux", "--episode", snapshot, "--build", build]),
         ("pilot.mp4", "pilot_clean.mp4", "captions.ass", "subtitles.srt", "publishing_caption.txt",
          "CREDITS.txt", "media_report.json", "media_report_clean.json"))
    step("review", command("review", [python, ROOT / "review_social.py", "--build", build]),
         ("delivery_checks.json", "contact_sheet.jpg", "safe_zone_review.png"))
    if any(sha256_file(ROOT / name) != digest for name, digest in spec["code_sha256"].items()):
        raise ValueError("Pipeline code changed before delivery; use a new build directory.")
    freeze_delivery(build)
    if with_promo:
        promo_build = build.with_name(build.name + "_promo")
        owner_path = promo_build / "pipeline_promo.json"
        owner = {"source": str(build), "source_scene_sha256": sha256_file(build / "studio.blend"),
                 "episode_sha256": content_hash(episode), "code_sha256": spec["code_sha256"]}
        if promo_build.exists() and any(promo_build.iterdir()):
            if not owner_path.is_file() or json.loads(owner_path.read_text(encoding="utf-8")) != owner:
                raise ValueError(f"Promo directory belongs to another job: {promo_build}; choose a new build directory.")
        promo_build.mkdir(exist_ok=True)
        atomic_json(owner_path, owner)
        if (promo_build / "export_manifest.json").exists():
            export = json.loads((promo_build / "export_manifest.json").read_text(encoding="utf-8"))
            edit = json.loads((promo_build / "scene_manifest.json").read_text(encoding="utf-8"))["derived_edit"]
            if edit["source"] != str(build) or edit["scene_sha256"] != sha256_file(build / "studio.blend"):
                raise ValueError("Existing promo belongs to a different source.")
            if any(sha256_file(promo_build / name) != digest for name, digest in export["files_sha256"].items()):
                raise ValueError("Existing promo artifacts changed; use a new output directory.")
            print("promo: using verified checkpoint", flush=True)
        else:
            run_command([python, ROOT / "produce_v4.py", "promo", "--source", build, "--build", promo_build],
                        build / "pipeline_promo.log")
            run_command([python, ROOT / "review_social.py", "--build", promo_build], build / "pipeline_promo_review.log")
            freeze_delivery(promo_build)
        stage_completed("promo", force=True)
    print(f"Ready: {build / 'pilot.mp4'}", flush=True)
    return build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "build"))
    parser.add_argument("--episode", type=Path, required=True)
    parser.add_argument("--build", type=Path,
                        help="Run directory; a project-level name is placed under builds/.")
    parser.add_argument("--profile", choices=tuple(PROFILES), default="preview")
    parser.add_argument("--jobs", type=int, choices=RENDER_JOBS, default=4)
    parser.add_argument("--render-device", choices=RENDER_DEVICES, default="CPU")
    parser.add_argument("--speech-device", default="cpu", help="PyTorch device, independent of the Blender backend.")
    parser.add_argument("--promo", action="store_true")
    parser.add_argument("--until", choices=("audio", "scene", "export"), default="export")
    parser.add_argument("--reuse-audio", type=Path, help="Reuse exact audio/alignment from a verified prior delivery.")
    parser.add_argument("--speech-cache-from", type=Path,
                        help="Read-only previous build: reuse only matching, verified raw speech.")
    parser.add_argument("--qwen-python", type=Path, default=qwen_python())
    args = parser.parse_args()
    runtime = args.qwen_python.resolve()
    if not runtime.is_file():
        parser.error(f"TTS Python not found: {runtime}")
    if Path(sys.executable).resolve() != runtime:
        with GenerationRun(cleanup_python=runtime) if args.command == "build" else nullcontext():
            result = run_process([runtime, Path(__file__).resolve(), *sys.argv[1:]])
            raise SystemExit(result.returncode)
    os.environ.setdefault("LP_NUM_THREADS", "4")
    try:
        if args.command == "validate":
            episode = preflight(args.episode)
            if args.render_device != "CPU":
                check_render_device(args.render_device)
            print(f"Valid: {episode['id']}; {len(episode['turns'])} turns; assets and static text fit.")
        elif args.build is None:
            parser.error("--build is required for build")
        else:
            build_episode(args.episode, args.build, args.profile, args.jobs, args.promo, args.until,
                          args.reuse_audio, args.speech_cache_from, args.render_device, args.speech_device)
    except KeyboardInterrupt:
        parser.exit(130, "Generation cancelled; verified checkpoints are preserved.\n")
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
