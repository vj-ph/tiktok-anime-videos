"""Force-align visible B2 instructions and run independent local speech ASR."""

import argparse
from pathlib import Path

from prepare_b2 import read
from prepare_sample import atomic_json, sha256_file

VISIBLE_INSTRUCTIONS = {"instruction_1", "instruction_2", "instruction_3", "checking_instruction"}


def align(build):
    from align_words import align_build, validate_words
    timeline = read(build / "timeline.json")
    selected = [turn for turn in timeline["turns"] if turn["id"] in VISIBLE_INSTRUCTIONS]
    if {t["id"] for t in selected} != VISIBLE_INSTRUCTIONS:
        raise ValueError("Expected three B2 instructions plus the spoken checking instruction.")
    inputs = build / "alignment_inputs"
    inputs.mkdir(exist_ok=True)
    atomic_json(inputs / "timeline.json", {"language": "de", "turns": selected})
    align_build(inputs)
    measured = read(inputs / "timeline.json")
    by_id = {t["id"]: t for t in measured["turns"]}
    for turn in selected:
        source = by_id[turn["id"]]
        turn.update(words=source["words"], alignment_key=source["alignment_key"])
        validate_words(turn["words"], turn["text"], turn["wav_duration"])
    timeline["word_alignment"] = measured["word_alignment"]
    atomic_json(build / "timeline.json", timeline)
    atomic_json(build / "word_alignment.json", {
        "provenance": measured["word_alignment"],
        "scope": "Three instructions and the interview checking instruction; no task subtitles.",
        "turns": [{key: t[key] for key in ("id", "start", "words", "alignment_key")} for t in selected]})
    print(f"B2 measured instruction highlights ready: {len(selected)} recordings.", flush=True)


def review(build, model_name, ids=None):
    from faster_whisper import WhisperModel
    from review_sample_audio import tokens
    target = build / f"speech_review_{model_name}.json"
    previous = read(target).get("turns", []) if target.exists() else []
    model, results = None, []
    for ident, item in read(build / "audio_manifest.json").items():
        if not item.get("text") or (ids is not None and ident not in ids):
            continue
        if sha256_file(Path(item["audio"])) != item["sha256"]:
            raise ValueError("ASR input changed.")
        match = next((p for p in previous if p["id"] == ident
                      and p["audio_sha256"] == item["sha256"] and p["expected"] == item["text"]), None)
        if match:
            result = match
        else:
            if model is None:
                model = WhisperModel(model_name, device="cpu", compute_type="int8",
                                     cpu_threads=4, local_files_only=True)
            segments, _ = model.transcribe(item["audio"], language="de", beam_size=5, vad_filter=False)
            recognized = " ".join(s.text.strip() for s in segments)
            result = dict(id=ident, expected=item["text"], recognized=recognized,
                          matches=tokens(item["text"]) == tokens(recognized),
                          audio_sha256=item["sha256"], speaker=item["speaker"])
        results.append(result)
        atomic_json(target, {"model": f"faster-whisper-{model_name}", "complete": False,
                            "scope": "Unprompted local ASR, not human listening/accent certification.",
                            "turns": results})
        print(f"B2 ASR {ident}: {'match' if result['matches'] else 'review flag'}", flush=True)
    if not results:
        raise ValueError("No B2 speech selected for ASR.")
    report = read(target)
    report.update(complete=True, selected_ids=sorted(ids) if ids is not None else "all speech")
    atomic_json(target, report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("align", "review"))
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--model", default="small", choices=("small", "medium"))
    parser.add_argument("--ids", nargs="+")
    args = parser.parse_args()
    build = args.build.resolve()
    if args.stage == "align":
        align(build)
    else:
        review(build, args.model, set(args.ids) if args.ids else None)
