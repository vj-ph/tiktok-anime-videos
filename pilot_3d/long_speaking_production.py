"""Verified speech reuse and the approved silent card for long speaking masters."""

import copy
import json
from pathlib import Path
import shutil
import wave

from PIL import Image, ImageDraw

from build_paths import resolve_build_reference
from long_speaking import ACCENT, FORMATS, INK, PANEL, compose, text_box
from long_speaking_full_preview import resolve_full_episode
from prepare_audio import atomic_json, atomic_text, sha256_file, subtitles

APPROVED_FILES = (
    "edit_manifest.json", "delivery_checks.json", "playback_timeline.json",
    "dialogue_with_notice.wav", "auditory_review_flags.json",
    "notice_youtube.png", "notice_social.png",
)
NOTICE_TEXT = "Samirs Bildbeschreibung wird in diesem Video übersprungen."


def read_json(path):
    return Path(path).read_text(encoding="utf-8")


def approved_preview(episode):
    source = Path(episode["approved_preview"])
    manifest_path = source / "export_manifest.json"
    if sha256_file(manifest_path) != episode["approved_preview_manifest_sha256"]:
        raise ValueError("Approved silent-notice preview manifest changed.")
    manifest = json.loads(read_json(manifest_path))
    for name in APPROVED_FILES:
        if manifest["files_sha256"].get(name) != sha256_file(source / name):
            raise ValueError(f"Approved silent-notice preview changed: {name}")
    report = json.loads(read_json(source / "delivery_checks.json"))
    if (report.get("status") != "verified_postproduction_preview"
            or not report.get("visual_review", {}).get("completed")
            or report.get("new_tts") is not False
            or report.get("new_native_rendering") is not False):
        raise ValueError("Production requires the verified, visually reviewed silent-notice preview.")
    edit = json.loads(read_json(source / "edit_manifest.json"))
    notice = episode["silent_notice"]
    frames = notice["seconds"] * episode["fps"]
    if (frames != int(frames) or frames <= 0 or edit["fps"] != episode["fps"]
            or edit["notice_frames"] != frames or edit["notice_seconds"] != notice["seconds"]
            or edit["notice_text"] != notice["text"]
            or edit["spoken_text"] is not None
            or edit["speech_tempo"] != episode.get("speech_tempo", 1.0)):
        raise ValueError("Production notice or tempo differs from the approved preview.")
    return source, edit


def resolve_production(episode, path):
    if episode.get("exam", {}).get("level") == "B2":
        from b2_speaking import resolve_production as resolve_b2
        return resolve_b2(episode, path)
    episode = resolve_full_episode(episode, path)
    episode["approved_preview"] = str(
        (path.parent / episode["approved_preview"]).resolve(strict=True))
    notice = episode.get("silent_notice", {})
    if (set(notice) != {"before_turn", "seconds", "text"}
            or notice["before_turn"] != "teil3_instruction"
            or not isinstance(notice["seconds"], (int, float))
            or isinstance(notice["seconds"], bool)
            or notice["seconds"] != 6 or notice["text"] != NOTICE_TEXT):
        raise ValueError("Production requires the approved silent notice before Teil 3.")
    approved_preview(episode)
    return episode


def production_reuse_spec(episode, source):
    if episode.get("exam", {}).get("level") == "B2":
        from b2_speaking import production_reuse_spec as b2_reuse
        return b2_reuse(episode, source)
    from pipeline import audio_reuse_spec

    if source is None:
        raise ValueError("Long-speaking production requires --reuse-audio from its verified base delivery.")
    source = resolve_build_reference(source).resolve(strict=True)
    approved, edit = approved_preview(episode)
    if source != resolve_build_reference(edit["source"]).resolve(strict=True):
        raise ValueError("Audio source differs from the approved silent-notice edit.")
    if sha256_file(source / "export_manifest.json") != edit["source_export_manifest_sha256"]:
        raise ValueError("Approved base delivery manifest changed.")
    receipt = audio_reuse_spec(episode, source)
    manifest = json.loads(read_json(source / "export_manifest.json"))
    for name in ("speech_asr_check.json", "delivery_checks.json"):
        digest = sha256_file(source / name)
        if manifest["files_sha256"].get(name) != digest:
            raise ValueError(f"Unverified inherited speech check: {name}")
        receipt["files_sha256"][name] = digest
    assets = json.loads(read_json(source / "delivery_checks.json"))["asset_sha256"]
    for name, digest in assets.items():
        if sha256_file(Path(name)) != digest:
            raise ValueError(f"An approved preview input changed: {name}")
    receipt["approved_assets_sha256"] = assets
    timeline = json.loads(read_json(source / "timeline.json"))
    if edit["source_frames"] != timeline["total_frames"]:
        raise ValueError("Approved base frame clock differs from the measured dialogue.")
    before = next(t for t in timeline["turns"] if t["id"] == episode["silent_notice"]["before_turn"])
    if before["start_frame"] != edit["insert_before_source_frame"]:
        raise ValueError("Approved notice does not meet the measured Teil 3 boundary.")
    playback = json.loads(read_json(approved / "playback_timeline.json"))
    shifted = copy.deepcopy(timeline)
    for turn in shifted["turns"]:
        if turn["start_frame"] >= before["start_frame"]:
            for key in ("start_frame", "end_frame"):
                turn[key] += edit["notice_frames"]
            for key in ("start", "end"):
                turn[key] += edit["notice_seconds"]
    if (playback["turns"] != shifted["turns"]
            or playback["total_frames"] != timeline["total_frames"] + edit["notice_frames"]
            or playback["duration"] != playback["total_frames"] / episode["fps"]):
        raise ValueError("Approved playback changed speech or measured word timing.")
    with wave.open(str(source / "dialogue.wav"), "rb") as wav:
        params = wav.getparams()
        original = wav.readframes(wav.getnframes())
    with wave.open(str(approved / "dialogue_with_notice.wav"), "rb") as wav:
        if wav.getparams()[:3] != params[:3]:
            raise ValueError("Approved notice audio format differs.")
        final = wav.readframes(wav.getnframes())
    if params[:3] != (1, 2, 48000):
        raise ValueError("Production reuse requires mono 48-kHz PCM16 dialogue.")
    if 48000 % episode["fps"]:
        raise ValueError("Notice insertion requires an exact integer audio sample clock.")
    stride = 48000 // episode["fps"] * 2
    cut, hold = edit["insert_before_source_frame"] * stride, edit["notice_frames"] * stride
    if final != original[:cut] + bytes(hold) + original[cut:]:
        raise ValueError("Approved notice audio is not exact speech plus digital silence.")
    receipt.update(approved_preview=str(approved), notice=edit,
                   approved_manifest_sha256=episode["approved_preview_manifest_sha256"],
                   policy="Exact verified speech and local word intervals; only the approved silent "
                          "card shifts subsequent absolute timestamps. No synthesis or realignment.")
    return receipt


def production_inputs(episode, receipt):
    if episode.get("exam", {}).get("level") == "B2":
        source = Path(receipt["source"])
        timeline = json.loads(read_json(source / "timeline.json"))
        paths = [source / name for name in receipt["files_sha256"]]
        paths += [Path(name) for name in receipt["voice_cache_sha256"]]
        for turn in timeline["turns"]:
            paths += [Path(turn["raw_audio"]), Path(turn["audio"]),
                      Path(turn["tempo_processing"]["input_audio"])]
        return paths
    approved, source = Path(episode["approved_preview"]), Path(receipt["source"])
    paths = [approved / "export_manifest.json", source / "export_manifest.json"]
    paths += [approved / name for name in APPROVED_FILES]
    paths += [source / name for name in receipt["files_sha256"]]
    paths += [Path(name) for name in receipt["voice_cache_sha256"]]
    paths += [Path(name) for name in receipt["approved_assets_sha256"]]
    timeline = json.loads(read_json(source / "timeline.json"))
    for turn in timeline["turns"]:
        paths += [Path(turn["raw_audio"]), Path(turn["audio"]),
                  Path(turn["tempo_processing"]["input_audio"])]
    return paths


def production_timeline(episode, receipt):
    if episode.get("exam", {}).get("level") == "B2":
        from episode_config import check_timeline
        timeline = json.loads(read_json(Path(receipt["source"]) / "timeline.json"))
        check_timeline(episode, timeline)
        return timeline
    timeline = json.loads(read_json(Path(receipt["approved_preview"]) / "playback_timeline.json"))
    edit = receipt["notice"]
    timeline["silent_notices"] = [{
        "id": "silent_samir_notice", "text": episode["silent_notice"]["text"],
        "start_frame": edit["insert_before_source_frame"],
        "end_frame": edit["insert_before_source_frame"] + edit["notice_frames"],
    }]
    from episode_config import check_timeline

    check_timeline(episode, timeline)
    if timeline["total_frames"] / timeline["fps"] >= episode["source"]["duration_limit_seconds"]:
        raise ValueError("Production with its notice exceeds the long-form safety ceiling.")
    return timeline


def production_scene_reuse_spec(episode, storyboard, audio, source):
    from long_speaking_preview import ROOT, SOURCES, native_plan, shared_native

    if not shared_native(episode) or episode["render"] != {
            "motion_step": 2, "native_scale": 1.0, "samples": 8, "native_source": "youtube"}:
        raise ValueError("--reuse-scene requires shared-frame long-speaking production.")
    source = resolve_build_reference(source).resolve(strict=True)
    state = json.loads(read_json(source / "production_state.json"))
    spec = state["spec"]
    original = spec["episode"]
    if (original.get("template") != "long_speaking_production"
            or original.get("render") != {"motion_step": 1, "native_scale": 1.0, "samples": 16}):
        raise ValueError("Scene reuse requires a completed full-quality production bake.")
    ignored = {"id", "source", "render", "render_device"}
    if ({k: v for k, v in original.items() if k not in ignored}
            != {k: v for k, v in episode.items() if k not in ignored}):
        raise ValueError("Baked scene animation/episode settings differ.")
    if spec.get("audio_reuse") != audio:
        raise ValueError("Baked scene uses different approved audio.")
    files = {"production_state.json", "episode.json", "storyboard_episode.json", "native_plan.json"}
    for stage, required in (
            ("scene", {"preview.blend", "scene_checks.json"}),
            ("audio_reuse", {"dialogue.wav", "timeline.json", "word_alignment.json", "audio_reuse.json",
                             "speech_asr_check.json", "auditory_review_flags.json", "subtitles.srt"})):
        outputs = state.get("stages", {}).get(stage, {})
        if set(outputs) != required:
            raise ValueError(f"Baked source lacks a complete {stage} checkpoint.")
        for name, digest in outputs.items():
            if sha256_file(source / name) != digest:
                raise ValueError(f"Baked source checkpoint changed: {name}")
        files.update(required)
    if set(spec["code_sha256"]) != set(SOURCES):
        raise ValueError("Baked scene has an incompatible source snapshot.")
    orchestration = {"pipeline.py", "long_speaking_preview.py", "long_speaking_production.py"}
    for name, digest in spec["code_sha256"].items():
        if sha256_file(source / "source_export" / name) != digest:
            raise ValueError(f"Baked source snapshot changed: {name}")
        if name not in orchestration and sha256_file(ROOT / name) != digest:
            raise ValueError(f"Baked scene implementation differs: {name}")
        files.add(str(Path("source_export") / name))
    for name, digest in spec["asset_sha256"].items():
        if sha256_file(Path(name)) != digest:
            raise ValueError(f"Baked scene input changed: {name}")
    timeline = production_timeline(episode, audio)
    if (json.loads(read_json(source / "episode.json")) != original
            or json.loads(read_json(source / "storyboard_episode.json")) != storyboard
            or json.loads(read_json(source / "timeline.json")) != timeline
            or sha256_file(source / "dialogue.wav") != sha256_file(
                Path(audio["approved_preview"]) / "dialogue_with_notice.wav")):
        raise ValueError("Baked scene storyboard, measured timeline or PCM differs.")
    original_plan = json.loads(read_json(source / "native_plan.json"))
    if original_plan != native_plan(original, storyboard, timeline):
        raise ValueError("Baked scene native plan differs from its episode.")
    planned = native_plan(episode, storyboard, timeline)
    coverage = {(p["format"], p["camera"], p["frame"], tuple(p["size"])) for p in original_plan}
    checks = json.loads(read_json(source / "scene_checks.json"))
    if (checks.get("preview_scene_sha256") != sha256_file(source / "preview.blend")
            or checks.get("hair_hangs_down_all_sampled_frames") is not True
            or checks.get("all_planned_head_and_hair_bounds_fit") is not True
            or any((p["format"], p["camera"], p["frame"], tuple(p["size"])) not in coverage
                   or checks.get("camera_lenses", {}).get(f"Preview {p['format']} {p['camera']}", 0) <= 0
                   for p in planned)):
        raise ValueError("Baked scene checks do not cover the requested cameras/frames.")
    return {
        "source": str(source),
        "files_sha256": {name: sha256_file(source / name) for name in sorted(files)},
        "assets_sha256": spec["asset_sha256"],
        "source_render": original["render"], "requested_render": episode["render"],
        "policy": "Byte-identical copy of a verified full bake; scene checks are inherited. "
                  "Only render sampling/backend and native-frame selection change; no rebaking.",
    }


def prepare_reused_scene(build, receipt):
    source = Path(receipt["source"])
    if build == source or build.is_relative_to(source) or source.is_relative_to(build):
        raise ValueError("Production output must be separate from the baked scene source.")
    for name, digest in receipt["files_sha256"].items():
        if sha256_file(source / name) != digest:
            raise ValueError(f"Baked scene source changed before copying: {name}")
    for name, digest in receipt["assets_sha256"].items():
        if sha256_file(Path(name)) != digest:
            raise ValueError(f"Baked scene input changed before copying: {name}")
    for name in ("preview.blend", "scene_checks.json"):
        shutil.copy2(source / name, build / name)
        if sha256_file(build / name) != receipt["files_sha256"][name]:
            raise ValueError(f"Baked scene copy differs: {name}")
    atomic_json(build / "scene_reuse.json", receipt)
    print("Reused verified baked scene; no animation bake.", flush=True)


def prepare_production_audio(build, episode, receipt):
    if episode.get("exam", {}).get("level") == "B2":
        source = Path(receipt["source"])
        for name in ("dialogue.wav", "timeline.json", "word_alignment.json",
                     "speech_asr_check.json", "subtitles.srt", "b2_timing_checks.json"):
            shutil.copy2(source / name, build / name)
        atomic_json(build / "audio_reuse.json", receipt)
        atomic_json(build / "auditory_review_flags.json", {
            "inherited_speech_checks": json.loads(read_json(source / "speech_asr_check.json")),
            "preview_approval": episode["preview_approval"],
            "human_listening_performed_by_generator": False,
        })
        return
    source, approved = Path(receipt["source"]), Path(receipt["approved_preview"])
    timeline = production_timeline(episode, receipt)
    shutil.copy2(approved / "dialogue_with_notice.wav", build / "dialogue.wav")
    shutil.copy2(approved / "auditory_review_flags.json", build / "auditory_review_flags.json")
    shutil.copy2(source / "speech_asr_check.json", build / "speech_asr_check.json")
    atomic_json(build / "timeline.json", timeline)
    atomic_json(build / "word_alignment.json", {
        "provenance": timeline["word_alignment"],
        "turns": [{key: turn[key] for key in ("id", "start", "words", "alignment_key")}
                  for turn in timeline["turns"]],
    })
    readable = copy.deepcopy(timeline)
    for turn in readable["turns"]:
        turn["text"] = turn.get("display_text", turn["text"])
    atomic_text(build / "subtitles.srt", subtitles(readable))
    atomic_json(build / "audio_reuse.json", receipt)


def notice_at(timeline, frame):
    return next((notice for notice in timeline.get("silent_notices", [])
                 if notice["start_frame"] <= frame < notice["end_frame"]), None)


def notice_overlay(storyboard, mode, notice):
    if notice.get("panel_id"):
        from long_speaking import compile_script, panels
        panel = next(p for p in panels(storyboard, compile_script(storyboard)) if p["id"] == notice["panel_id"])
        box = FORMATS[mode]["scene"]
        native = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), PANEL)
        image, check = compose(storyboard, panel, mode, native, sample_highlights=False)
        check.update(silent=True, spoken_text=None, notice_text=panel.get("card_text", panel["body"]))
        return image, check
    layout = FORMATS[mode]
    x0, y0, x1, y1 = layout["scene"]
    width, height = x1 - x0, y1 - y0
    native = Image.new("RGB", (width, height), PANEL)
    draw = ImageDraw.Draw(native)
    title = text_box(draw, "Samirs\nBildbeschreibung", (70, 65, width - 70, 260),
                     size=72 if mode == "youtube" else 61, minimum=52,
                     color=ACCENT, bold=True)
    message = text_box(draw, "wird in diesem Video\nübersprungen.",
                       (70, 285, width - 70, height - 45), size=46, minimum=38, color=INK)
    panel = {"id": notice["id"], "part": 2, "heading": "Teil 2 · Hinweis",
             "body": "Weiter geht's mit Teil 3:\nGemeinsam etwas planen.",
             "picture": False, "camera": None}
    image, check = compose(storyboard, panel, mode, native, sample_highlights=False)
    check.update(silent=True, spoken_text=None, notice_text=notice["text"],
                 notice_typography=[title, message])
    return image, check
