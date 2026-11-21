"""Full-resolution TEF speaking delivery from an approved frozen preview."""

import json
import os
from pathlib import Path

from build_paths import build_directory, resolve_build_reference
from episode_config import read_episode
from prepare_audio import atomic_json, sha256_file

RENDER = {"motion_step": 2, "native_scale": 1.0, "samples": 8, "native_source": "youtube"}
REQUIRED = {"preview_youtube.mp4", "episode.json", "dialogue.wav", "timeline.json",
            "word_alignment.json", "speech_asr_check.json", "delivery_checks.json",
            "preview_inputs.json", "subtitles.srt"}


def load_production(path):
    from tef_speaking_preview import load_preview

    path = Path(path).resolve(strict=True)
    config = json.loads(path.read_text(encoding="utf-8"))
    approval = config.get("preview_approval", {})
    if (config.get("template") != "tef_speaking_full_production"
            or config.get("render") != RENDER
            or approval.get("approved_by") != "user" or not approval.get("approved_on")):
        raise ValueError("TEF production requires approved preview audio and the full-resolution preset.")
    source = (path.parent / config["approved_preview"].replace("\\", os.sep)).resolve(strict=True)
    manifest_path = source / "export_manifest.json"
    if sha256_file(manifest_path) != config["approved_preview_manifest_sha256"]:
        raise ValueError("Approved TEF preview manifest changed.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not REQUIRED <= manifest["files_sha256"].keys() or not manifest.get("source_sha256"):
        raise ValueError("TEF production requires a complete frozen preview, not layout diagnostics.")
    for name, digest in manifest["files_sha256"].items():
        if sha256_file(source / name) != digest:
            raise ValueError(f"Approved TEF preview file changed: {name}")
    for name, digest in manifest["source_sha256"].items():
        if sha256_file(source / "source_export" / name) != digest:
            raise ValueError(f"Approved TEF source snapshot changed: {name}")
    inputs = json.loads((source / "preview_inputs.json").read_text(encoding="utf-8"))
    for name, digest in inputs.items():
        if sha256_file(Path(name)) != digest:
            raise ValueError(f"Approved TEF input changed: {name}")
    episode = load_preview(source / "episode.json")
    if episode["template"] != "tef_speaking_full_preview":
        raise ValueError("TEF production requires a complete two-section preview.")
    if sha256_file(Path(episode["scene"]["base_scene"])) != config["approved_base_scene_sha256"]:
        raise ValueError("Approved TEF base scene changed.")
    checks = json.loads((source / "delivery_checks.json").read_text(encoding="utf-8"))
    if not checks.get("preview_only") or not checks.get("encoded_checks"):
        raise ValueError("TEF production requires completed encoded preview checks.")
    episode.update(id=config["id"], template=config["template"], render=dict(RENDER),
                   approved_preview=str(source),
                   approved_preview_manifest_sha256=config["approved_preview_manifest_sha256"],
                   approved_base_scene_sha256=config["approved_base_scene_sha256"],
                   preview_approval=approval, production_config=str(path))
    return episode


def production_reuse_spec(episode, source):
    from pipeline import audio_reuse_spec

    approved = Path(episode["approved_preview"])
    if source is None or resolve_build_reference(source).resolve(strict=True) != approved:
        raise ValueError("TEF production requires --reuse-audio from its exact approved preview.")
    receipt = audio_reuse_spec(episode, approved)
    manifest = json.loads((approved / "export_manifest.json").read_text(encoding="utf-8"))
    names = ("speech_asr_check.json", "speech_medium_review.json", "subtitles.srt")
    receipt["files_sha256"].update({name: manifest["files_sha256"][name]
                                   for name in names if name in manifest["files_sha256"]})
    receipt.update(approved_manifest_sha256=episode["approved_preview_manifest_sha256"],
                   approved_base_scene_sha256=episode["approved_base_scene_sha256"],
                   preview_approval=episode["preview_approval"])
    return receipt


def build_production(path, build, *, reuse_audio, jobs=4, until="export", render_device="CPU"):
    from tef_speaking_preview import build_preview

    episode = load_production(path)
    production_reuse_spec(episode, reuse_audio)
    build = build_directory(build)
    source = Path(episode["approved_preview"])
    if build == source or build in source.parents or source in build.parents:
        raise ValueError("Production must use a separate sibling build, preserving the approved preview.")
    compiled = build.with_name(build.name + "_episode.json")
    if compiled.exists():
        if read_episode(compiled) != episode:
            raise ValueError("Production inputs changed; use a fresh build directory.")
    else:
        compiled.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(compiled, episode)
    return build_preview(compiled, build, jobs=jobs, until=until, reuse_audio=reuse_audio,
                         profile="production", render_device=render_device)
