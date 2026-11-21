"""Keep independent local ASR disagreements without rewriting approved speech."""

import argparse
import json
from pathlib import Path
import re


def tokens(text):
    return re.findall(r"\w+", text.casefold())


def review(build):
    from faster_whisper import WhisperModel

    build = build.resolve()
    manifest = json.loads((build / "audio_manifest.json").read_text(encoding="utf-8"))
    recognizer = WhisperModel("small", device="cpu", compute_type="int8",
                             cpu_threads=4, local_files_only=True)
    results = []
    for ident, item in manifest.items():
        if not item.get("text"):
            continue
        segments, _ = recognizer.transcribe(item["audio"], language="de",
                                            beam_size=5, vad_filter=False)
        recognized = " ".join(segment.text.strip() for segment in segments)
        row = {"id": ident, "expected": item["text"], "recognized": recognized,
               "matches": tokens(item["text"]) == tokens(recognized),
               "audio_sha256": item["sha256"]}
        results.append(row)
        print(f"ASR {ident}: {'match' if row['matches'] else 'review flag'}", flush=True)
    report = {"model": "faster-whisper-small", "device": "cpu",
              "scope": "Independent ASR, not human listening or accent certification.",
              "turns": results}
    (build / "speech_review.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    review(parser.parse_args().build)
