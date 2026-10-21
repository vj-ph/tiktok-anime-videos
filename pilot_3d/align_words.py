#!/usr/bin/env python3
"""Locally force-align the exact prepared Qwen WAVs; never estimate word timing."""

import argparse
import importlib.metadata
import json
import math
from pathlib import Path

from prepare_audio import atomic_json, content_hash, inspect_wav, sha256_file

MODEL = "VOXPOPULI_ASR_BASE_10K_DE"


def validate_words(words, text, duration):
    expected = text.split()
    if not isinstance(words, list) or len(words) != len(expected):
        raise ValueError("Forced alignment must time every transcript word; no interpolation is permitted.")
    previous = 0.0
    for token, word in zip(expected, words):
        if word.get("word") != token:
            raise ValueError(f"Alignment changed transcript token {token!r}: {word!r}")
        start, end = word.get("start"), word.get("end")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
               for v in (start, end)):
            raise ValueError(f"Missing/non-finite word interval: {word!r}")
        if start < previous or end <= start or end > duration + 0.001:
            raise ValueError(f"Overlapping/out-of-bounds word interval: {word!r}")
        score = word.get("score")
        if not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError(f"Missing/invalid measured alignment confidence: {word!r}")
        previous = end
    return words


def align_build(build):
    import torch
    import torchaudio
    import whisperx

    torch.set_num_threads(4)
    model, metadata = whisperx.load_align_model(language_code="de", device="cpu", model_name=MODEL)
    checkpoint = Path(torch.hub.get_dir()) / "checkpoints" / Path(
        getattr(torchaudio.pipelines, MODEL)._path
    ).name
    provenance = {
        "model": MODEL, "model_sha256": sha256_file(checkpoint),
        "language": "de", "device": "cpu", "interpolate_method": "ignore",
        "reuse_reference": "/home/ronggong/lang/german/bildbeschreibung/bildbeschreibung_video/tts.py",
        "packages": {name: importlib.metadata.version(name) for name in ("whisperx", "torch", "torchaudio")},
    }
    path = build / "timeline.json"
    timeline = json.loads(path.read_text())
    cache = build / "alignment"
    cache.mkdir(exist_ok=True)
    for turn in timeline["turns"]:
        audio = Path(turn["audio"])
        info = inspect_wav(audio)
        if abs(info["wav_duration"] - turn["wav_duration"]) > 1e-9:
            raise ValueError(f"Turn {turn['id']}: source WAV and timeline disagree.")
        payload = {**provenance, "text": turn["text"], "wav_sha256": sha256_file(audio)}
        key = content_hash(payload)
        sidecar = cache / f"{turn['id']}-{key[:20]}.words.json"
        if sidecar.exists():
            saved = json.loads(sidecar.read_text())
            if saved["cache_key"] != key or saved["payload"] != payload:
                raise ValueError(f"Corrupt alignment cache: {sidecar}")
            words = saved["words"]
        else:
            result = whisperx.align(
                [{"start": 0.0, "end": info["wav_duration"], "text": turn["text"]}],
                model, metadata, str(audio), "cpu", interpolate_method="ignore",
            )
            words = [
                {field: str(item[field]) if field == "word" else float(item[field])
                 for field in ("word", "start", "end", "score") if field in item}
                for item in result["word_segments"]
            ]
            validate_words(words, turn["text"], turn["wav_duration"])
            atomic_json(sidecar, {"cache_key": key, "payload": payload, "words": words})
        turn["words"] = validate_words(words, turn["text"], turn["wav_duration"])
        turn["alignment_key"] = key
        print(f"Aligned {turn['id']}: {len(words)} words; min confidence "
              f"{min(word['score'] for word in words):.3f}", flush=True)
    timeline["word_alignment"] = provenance
    atomic_json(path, timeline)
    atomic_json(build / "word_alignment.json", {
        "provenance": provenance,
        "turns": [{"id": turn["id"], "start": turn["start"], "words": turn["words"],
                   "alignment_key": turn["alignment_key"]} for turn in timeline["turns"]],
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    align_build(parser.parse_args().build.resolve())
