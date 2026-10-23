#!/usr/bin/env python3
"""Independent, unprompted per-turn ASR; forced alignment is not speech verification."""

import argparse
import json
from pathlib import Path
import re

from build_paths import resolve_build_reference
from episode_config import check_timeline, read_episode
from episode_profiles import language_code
from prepare_audio import atomic_json, sha256_file

MODEL = "Systran/faster-whisper-small"


def tokens(text):
    return re.findall(r"[^\W_]+", text.casefold())


def check_speech(build, *, model_dir=None, threads=4, recognizer=None):
    build = resolve_build_reference(build).resolve(strict=True)
    episode = read_episode(build / "episode.json")
    timeline = json.loads((build / "timeline.json").read_text())
    check_timeline(episode, timeline)
    code = language_code(episode)
    if recognizer is None:
        from faster_whisper import WhisperModel
        from huggingface_hub import snapshot_download

        model_dir = (str(Path(model_dir).resolve(strict=True)) if model_dir is not None else
                     snapshot_download(MODEL, local_files_only=True))
        recognizer = WhisperModel(model_dir, device="cpu", compute_type="int8", cpu_threads=threads)
    checks = []
    for turn in timeline["turns"]:
        audio = resolve_build_reference(turn["audio"]).resolve(strict=True)
        before = sha256_file(audio)
        segments, _ = recognizer.transcribe(
            str(audio), language=code, beam_size=5, vad_filter=False,
            condition_on_previous_text=False, initial_prompt=None,
        )
        recognized = " ".join(segment.text.strip() for segment in segments).strip()
        if sha256_file(audio) != before:
            raise ValueError(f"Turn {turn['id']}: source audio changed during recognition.")
        checks.append({
            "id": turn["id"], "speaker": turn["speaker"], "audio_sha256": before,
            "expected": turn["text"], "recognized": recognized,
            "matches": tokens(turn["text"]) == tokens(recognized),
        })
    report = {
        "model": MODEL, "model_path": str(model_dir) if model_dir is not None else None,
        "language": code, "device": "cpu", "compute_type": "int8", "threads": threads,
        "beam_size": 5, "vad_filter": False, "condition_on_previous_text": False, "initial_prompt": None,
        "episode_sha256": sha256_file(build / "episode.json"),
        "timeline_sha256": sha256_file(build / "timeline.json"),
        "normalization": "Case and punctuation only; numerals remain distinct.",
        "note": "Independent ASR plausibility check, not a pronunciation or accent guarantee. "
                "Disagreements require review, not edited pass flags.",
        "all_match": bool(checks) and all(check["matches"] for check in checks),
        "turns": checks,
    }
    atomic_json(build / "speech_asr_check.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, help="Existing local faster-whisper-small snapshot.")
    parser.add_argument("--threads", type=int, choices=(1, 2, 4), default=4)
    args = parser.parse_args()
    try:
        report = check_speech(args.build, model_dir=args.model_dir, threads=args.threads)
    except (ValueError, OSError, RuntimeError) as error:
        parser.exit(1, f"Speech check failed: {error}\n")
    count = sum(turn["matches"] for turn in report["turns"])
    print(f"{count}/{len(report['turns'])} turns match independent {report['language']} ASR.")
    raise SystemExit(0 if report["all_match"] else 1)


if __name__ == "__main__":
    main()
