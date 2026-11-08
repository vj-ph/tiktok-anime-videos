"""Exact speech reuse from the approved complete A2 preview."""

import json
from pathlib import Path
import shutil

from build_paths import resolve_build_reference
from prepare_audio import atomic_json, load_audio_cache, sha256_file


def resolve_production(episode, path, storyboard):
    approval = episode.get("preview_approval", {})
    if approval.get("approved_by") != "user" or not approval.get("approved_on"):
        raise ValueError("A2 production requires explicit user preview/audio approval.")
    source = (path.parent / episode["approved_preview"]).resolve(strict=True)
    episode["approved_preview"] = str(source)
    manifest_path = source / "export_manifest.json"
    if sha256_file(manifest_path) != episode["approved_preview_manifest_sha256"]:
        raise ValueError("Approved A2 preview manifest changed.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = {"preview_youtube.mp4", "episode.json", "storyboard_episode.json", "dialogue.wav",
                "timeline.json", "audio_timeline.json", "word_alignment.json", "subtitles.srt",
                "delivery_checks.json", "speech_asr_check.json", "preview_state.json"}
    if not required <= manifest["files_sha256"].keys():
        raise ValueError("A2 production requires a complete verified YouTube preview.")
    for name, digest in manifest["files_sha256"].items():
        if sha256_file(source / name) != digest:
            raise ValueError(f"Approved A2 preview file changed: {name}")
    report = json.loads((source / "delivery_checks.json").read_text(encoding="utf-8"))
    if report.get("status") != "preview_only" or "youtube" not in report.get("exports", {}):
        raise ValueError("A2 production requires the complete YouTube preview, not contact sheets.")
    original = json.loads((source / "episode.json").read_text(encoding="utf-8"))
    if original.get("template") != "a2_speaking_full_preview":
        raise ValueError("A2 production requires an A2 full-preview source.")
    allowed = {"id", "template", "render", "render_device", "output_formats",
               "approved_preview", "approved_preview_manifest_sha256", "preview_approval"}
    if ({k: v for k, v in original.items() if k not in allowed}
            != {k: v for k, v in episode.items() if k not in allowed}
            or json.loads((source / "storyboard_episode.json").read_text(encoding="utf-8")) != storyboard):
        raise ValueError("A2 production content differs from its approved preview.")
    for name, digest in report["source_sha256"]["asset_sha256"].items():
        if sha256_file(Path(name)) != digest:
            raise ValueError(f"Approved A2 asset changed: {name}")
    for name, digest in manifest["generation_source_sha256"].items():
        if sha256_file(source / "source_export" / name) != digest:
            raise ValueError(f"Approved A2 source snapshot changed: {name}")
    return episode


def production_reuse_spec(episode, source):
    from pipeline import audio_reuse_spec

    if (source is None
            or resolve_build_reference(source).resolve(strict=True) != Path(episode["approved_preview"])):
        raise ValueError("A2 production requires --reuse-audio from its exact approved preview.")
    source = Path(episode["approved_preview"])
    receipt = audio_reuse_spec(episode, source)
    receipt["files_sha256"].update({
        name: sha256_file(source / name)
        for name in ("export_manifest.json", "episode.json", "storyboard_episode.json",
                     "audio_timeline.json", "subtitles.srt", "delivery_checks.json", "speech_asr_check.json")
    })
    clips = {}
    timeline = json.loads((source / "timeline.json").read_text(encoding="utf-8"))
    for turn in timeline["turns"]:
        tempo = turn["tempo_processing"]
        payload = {k: v for k, v in tempo.items() if k not in ("cache_key", "input_audio")}
        audio, input_audio = Path(turn["audio"]), Path(tempo["input_audio"])
        if (sha256_file(input_audio) != tempo["input_sha256"]
                or load_audio_cache(audio, payload) is None):
            raise ValueError(f"A2 turn {turn['id']}: processed speech cache changed.")
        for path in (audio, input_audio, Path(turn["raw_audio"]), audio.with_suffix(".cache.json")):
            clips[str(path)] = sha256_file(path)
    receipt.update(approved_manifest_sha256=episode["approved_preview_manifest_sha256"],
                   clip_sha256=clips, preview_approval=episode["preview_approval"])
    return receipt


def production_inputs(receipt):
    source = Path(receipt["source"])
    return ([source / name for name in receipt["files_sha256"]]
            + [Path(name) for name in receipt["voice_cache_sha256"]]
            + [Path(name) for name in receipt["clip_sha256"]])


def prepare_production_audio(build, receipt):
    source = Path(receipt["source"])
    for name in ("dialogue.wav", "timeline.json", "audio_timeline.json", "word_alignment.json",
                 "subtitles.srt", "speech_asr_check.json"):
        if sha256_file(source / name) != receipt["files_sha256"][name]:
            raise ValueError(f"Approved A2 speech changed before copying: {name}")
        shutil.copy2(source / name, build / name)
    atomic_json(build / "audio_reuse.json", receipt)
    speech = json.loads((build / "speech_asr_check.json").read_text(encoding="utf-8"))
    atomic_json(build / "auditory_review_flags.json", {
        "asr_disagreements": [turn for turn in speech["turns"] if not turn["matches"]],
        "preview_approval": receipt["preview_approval"], "human_listening_performed": False,
        "note": "Inherited ASR flags are unchanged. User approval does not certify pronunciation.",
    })
