"""Approval-bound exact speech reuse for full-resolution fide production."""

import json
from pathlib import Path

from a2_speaking_production import (
    prepare_production_audio, production_inputs,
    production_reuse_spec as exact_audio_reuse_spec,
)
from prepare_audio import sha256_file


def resolve_production(episode, path):
    approval = episode.get("preview_approval", {})
    if approval.get("approved_by") != "user" or not approval.get("approved_on"):
        raise ValueError("Fide production requires explicit user preview/audio approval.")
    source = (path.parent / episode["approved_preview"]).resolve(strict=True)
    episode["approved_preview"] = str(source)
    manifest_path = source / "export_manifest.json"
    if sha256_file(manifest_path) != episode["approved_preview_manifest_sha256"]:
        raise ValueError("Approved fide preview manifest changed.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = {"preview_youtube.mp4", "preview_social.mp4", "episode.json", "storyboard_episode.json",
                "dialogue.wav", "timeline.json", "audio_timeline.json", "word_alignment.json",
                "subtitles.srt", "delivery_checks.json", "speech_asr_check.json",
                "speech_chain_hashes.json", "preview_state.json"}
    if not required <= manifest["files_sha256"].keys():
        raise ValueError("Fide production requires both complete verified preview exports.")
    for name, digest in manifest["files_sha256"].items():
        if sha256_file(source / name) != digest:
            raise ValueError(f"Approved fide preview file changed: {name}")
    report = json.loads((source / "delivery_checks.json").read_text(encoding="utf-8"))
    if (report.get("status") != "full_length_preview_only"
            or set(report.get("exports", {})) != {"youtube", "social"}):
        raise ValueError("Fide production requires the full fide preview, not contact sheets.")
    allowed = {"id", "template", "render", "render_device", "approved_preview",
               "approved_preview_manifest_sha256", "preview_approval"}
    expected = {k: v for k, v in episode.items() if k not in allowed}
    for name in ("episode.json", "storyboard_episode.json"):
        original = json.loads((source / name).read_text(encoding="utf-8"))
        if (original.get("template") != "fide_speaking_full_preview"
                or {k: v for k, v in original.items() if k not in allowed} != expected):
            raise ValueError("Fide production content differs from its approved preview.")
    for name, digest in report["source_sha256"]["asset_sha256"].items():
        if sha256_file(Path(name)) != digest:
            raise ValueError(f"Approved fide asset changed: {name}")
    for name, digest in manifest["generation_source_sha256"].items():
        if sha256_file(source / "source_export" / name) != digest:
            raise ValueError(f"Approved fide source snapshot changed: {name}")
    return episode


def production_reuse_spec(episode, source):
    receipt = exact_audio_reuse_spec(episode, source)
    chain_path = Path(receipt["source"]) / "speech_chain_hashes.json"
    chain = json.loads(chain_path.read_text(encoding="utf-8"))
    for name, digest in chain.items():
        if sha256_file(Path(name)) != digest:
            raise ValueError(f"Approved fide speech chain changed: {name}")
    receipt["files_sha256"][chain_path.name] = sha256_file(chain_path)
    receipt["clip_sha256"].update(chain)
    return receipt
