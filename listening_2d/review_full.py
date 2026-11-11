"""Review new production speech locally; retain verified unchanged ASR receipts."""

import argparse
import json
from pathlib import Path

from prepare_sample import atomic_json, sha256_file
from review_sample_audio import tokens


def review(build):
    build = build.resolve()
    manifest = json.loads((build / "audio_manifest.json").read_text(encoding="utf-8"))
    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    pin = json.loads((build / "input_pin.json").read_text(encoding="utf-8"))
    source_receipt = Path(pin["sample_build"]) / "speech_review.json"
    cached = []
    if source_receipt.is_file():
        previous = json.loads(source_receipt.read_text(encoding="utf-8"))
        if previous["model"] == "faster-whisper-small":
            cached.extend(previous["turns"])
    target = build / "speech_review.json"
    if target.is_file():
        previous = json.loads(target.read_text(encoding="utf-8"))
        if previous["model"] == "faster-whisper-small":
            cached.extend(previous["turns"])
    recognizer, results = None, []
    for turn in timeline["turns"]:
        item = manifest[turn["id"]]
        if sha256_file(Path(item["audio"])) != item["sha256"]:
            raise ValueError(f"Changed ASR input: {turn['id']}")
        match = next((row for row in cached if row["expected"] == turn["text"]
                      and row["audio_sha256"] == item["sha256"]), None)
        if match:
            recognized = match["recognized"]
        else:
            if recognizer is None:
                from faster_whisper import WhisperModel
                recognizer = WhisperModel("small", device="cpu", compute_type="int8",
                                          cpu_threads=4, local_files_only=True)
            segments, _ = recognizer.transcribe(item["audio"], language="de",
                                                beam_size=5, vad_filter=False)
            recognized = " ".join(segment.text.strip() for segment in segments)
        results.append({"id": turn["id"], "expected": turn["text"], "recognized": recognized,
                        "matches": tokens(turn["text"]) == tokens(recognized),
                        "audio_sha256": item["sha256"], "start": turn["start"], "end": turn["end"],
                        "speaker": turn["speaker"], "reused_verified_asr": bool(match)})
        atomic_json(target, {"model": "faster-whisper-small", "device": "cpu",
                            "scope": "Independent unprompted ASR; not human listening/accent certification.",
                            "complete": len(results) == len(timeline["turns"]), "turns": results})
        print(f"ASR {turn['id']}: {'match' if results[-1]['matches'] else 'review flag'}"
              f"{' (verified reuse)' if match else ''}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    review(parser.parse_args().build)
