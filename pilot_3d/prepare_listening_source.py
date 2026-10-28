#!/usr/bin/env python3
"""Generate one book-based listening recording without overwriting existing audio."""

import argparse
import json
from pathlib import Path

from build_paths import BUILDS
from prepare_audio import MODEL, content_hash, inspect_wav, sha256_file, synthesize


def validate_registry_voice(registry_path, voice, reference, transcript):
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    matches = [item for item in registry["voices"] if item.get("voice_id") == voice.get("voice_id")]
    if len(matches) != 1 or matches[0].get("availability") is not True:
        raise ValueError("The selected registry voice is missing or unavailable.")
    registered_audio = (registry_path.parent.parent.parent / matches[0]["reference_audio"]).resolve()
    if (registered_audio != reference
            or matches[0].get("reference_text") != transcript.read_text(encoding="utf-8").strip()):
        raise ValueError("The voice reference or its transcript does not match the registry.")
    return matches[0]


def prepare(path, model, threads=8):
    path = Path(path).resolve(strict=True)
    episode = json.loads(path.read_text(encoding="utf-8"))
    source = episode.get("source")
    voice = episode.get("source_voice", episode.get("voice"))
    if not isinstance(source, dict) or not isinstance(voice, dict):
        raise ValueError("The episode requires source and voice objects.")
    text = source.get("audio_transcript")
    if not isinstance(text, str) or not text.strip() or "\n" in text or "\r" in text:
        raise ValueError("source.audio_transcript must be one nonempty spoken paragraph.")

    def file_path(value, label):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} must be a nonempty path.")
        return (path.parent / value).resolve()

    book = file_path(source.get("book"), "source.book")
    if text not in book.read_text(encoding="utf-8"):
        raise ValueError("The exact audio transcript was not found in the source book.")
    reference = file_path(voice.get("audio"), "voice.audio")
    transcript = file_path(voice.get("transcript"), "voice.transcript")
    inspect_wav(reference)
    reference_text = transcript.read_text(encoding="utf-8").strip()
    if not reference_text:
        raise ValueError("The voice reference transcript is empty.")
    if "voice_registry" in source:
        registry_path = file_path(source["voice_registry"], "source.voice_registry")
        validate_registry_voice(registry_path, voice, reference, transcript)

    target = file_path(episode.get("audio"), "audio")
    metadata = file_path(source.get("audio_provenance"), "source.audio_provenance")
    builds = BUILDS.resolve()
    if builds not in target.parents or target.parent == builds or metadata != target.with_suffix(".cache.json"):
        raise ValueError("Use a dedicated builds subdirectory and the recording's .cache.json sidecar.")
    if target.exists() or metadata.exists():
        raise ValueError("Source recording or sidecar already exists; choose a fresh output.")
    target.parent.mkdir(parents=True, exist_ok=True)
    speech = {
        "language": episode.get("language"),
        "voices": {"announcement": {"audio": str(reference), "transcript": str(transcript)}},
        "turns": [{"id": "announcement", "speaker": "announcement", "text": text}],
    }
    results = synthesize(speech, path.parent, target.parent, model, "cpu", threads)
    generated = Path(results[0]["audio"])
    generated_metadata = generated.with_suffix(".cache.json")
    cache = json.loads(generated_metadata.read_text(encoding="utf-8"))
    payload = cache.get("payload")
    if (not isinstance(payload, dict) or payload.get("text") != text
            or payload.get("reference_audio_sha256") != sha256_file(reference)
            or payload.get("reference_transcript_sha256") != sha256_file(transcript)
            or payload.get("reference_text") != reference_text
            or cache.get("cache_key") != content_hash(payload)
            or cache.get("wav_sha256") != sha256_file(generated)
            or cache.get("audio_info") != inspect_wav(generated)):
        raise ValueError("Generated source audio does not match its provenance.")
    generated.rename(target)
    generated_metadata.rename(metadata)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, help="Local Qwen model snapshot; no model download is performed.")
    parser.add_argument("--threads", type=int, default=8, choices=(1, 2, 4, 8))
    args = parser.parse_args()
    if args.model_dir:
        model = str(args.model_dir.resolve(strict=True))
    else:
        from huggingface_hub import snapshot_download
        model = snapshot_download(MODEL, local_files_only=True)
    try:
        result = prepare(args.episode, model, args.threads)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"Error: {error}\n")
    print(f"Generated listening source: {result}")


if __name__ == "__main__":
    main()
