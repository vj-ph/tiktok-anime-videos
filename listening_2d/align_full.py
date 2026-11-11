"""Force-align only visible narration, preserving verified reused word intervals."""

import argparse
import json
from pathlib import Path

from compose_sample import ROOT
from align_words import align_build, validate_words
from prepare_sample import atomic_json, sha256_file


def align(build):
    build = build.resolve()
    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    pin = json.loads((build / "input_pin.json").read_text(encoding="utf-8"))
    source = Path(pin["sample_build"])
    original = json.loads((source / "timeline.json").read_text(encoding="utf-8"))
    wanted = {"title", *(f"instruction_{part}" for part in range(1, 5))}
    selected = [turn for turn in timeline["turns"] if turn["id"] in wanted]
    if {turn["id"] for turn in selected} != wanted or len(selected) != 5:
        raise ValueError("Expected title and all four Anleitung recordings.")
    pending, reused = [], []
    for turn in selected:
        match = next((item for item in original["turns"]
                      if item["text"] == turn["text"] and item["sha256"] == turn["sha256"]), None)
        if match:
            turn["words"] = validate_words(match["words"], turn["text"], turn["wav_duration"])
            turn["alignment_key"] = match["alignment_key"]
            reused.append(turn["id"])
        else:
            pending.append(turn)
    inputs = build / "alignment_inputs"
    inputs.mkdir(exist_ok=True)
    atomic_json(inputs / "timeline.json", {"language": "de", "turns": pending})
    align_build(inputs)
    measured = json.loads((inputs / "timeline.json").read_text(encoding="utf-8"))
    by_id = {turn["id"]: turn for turn in measured["turns"]}
    for turn in selected:
        if turn["id"] in by_id:
            turn.update(words=by_id[turn["id"]]["words"],
                        alignment_key=by_id[turn["id"]]["alignment_key"])
        validate_words(turn["words"], turn["text"], turn["wav_duration"])
    timeline["word_alignment"] = {
        "scope": "Title and all four Anleitung recordings; no task subtitles.",
        "new_alignment": measured["word_alignment"],
        "reused_alignment": original["word_alignment"],
    }
    atomic_json(build / "timeline.json", timeline)
    atomic_json(build / "word_alignment.json", {
        "provenance": timeline["word_alignment"], "reused_turns": reused,
        "source_timeline_sha256": sha256_file(source / "timeline.json"),
        "turns": [{"id": turn["id"], "start": turn["start"], "words": turn["words"],
                   "alignment_key": turn["alignment_key"]} for turn in selected],
    })
    print(f"Measured narration highlights ready: {len(selected)} recordings.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    align(parser.parse_args().build)
