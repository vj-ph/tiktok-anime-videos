"""Align only visible fide narration and review all unique speech locally."""

import argparse
from pathlib import Path

from prepare_fide import atomic_json, read, sha256_file


def align(build):
    from align_words import align_build, validate_words
    timeline = read(build / "timeline.json")
    selected = [turn for turn in timeline["turns"] if turn["visible"]]
    wanted = {turn["id"] for turn in read(build / "speech_plan.json")["turns"] if turn["visible"]}
    if {t["id"] for t in selected} != wanted:
        raise ValueError("Visible fide narration is missing or includes unapproved question/transcript text.")
    inputs = build / "alignment_inputs"
    inputs.mkdir(exist_ok=True)
    atomic_json(inputs / "timeline.json", {"language": "de", "turns": selected})
    align_build(inputs)
    measured = read(inputs / "timeline.json")
    aligned = {turn["id"]: turn for turn in measured["turns"]}
    for turn in selected:
        source = aligned[turn["id"]]
        turn.update(words=source["words"], alignment_key=source["alignment_key"])
        validate_words(turn["words"], turn["text"], turn["wav_duration"])
    timeline["word_alignment"] = measured["word_alignment"]
    atomic_json(build / "timeline.json", timeline)
    atomic_json(build / "word_alignment.json", {
        "provenance": measured["word_alignment"],
        "scope": "Opening, setup, instructions, situation introductions, transition and test/solution instructions. No question/recording subtitles.",
        "turns": [{key: t[key] for key in ("id", "start", "words", "alignment_key")} for t in selected]})
    print(f"Fide real word alignment complete: {len(selected)} narration clips.", flush=True)


def review(build, model_name, ids=None):
    from faster_whisper import WhisperModel
    from review_sample_audio import tokens
    target = build / f"speech_review_{model_name}.json"
    previous = read(target).get("turns", []) if target.exists() else []
    model, results = None, []
    for ident, item in read(build / "audio_manifest.json").items():
        if ids is not None and ident not in ids:
            continue
        if sha256_file(Path(item["audio"])) != item["sha256"]:
            raise ValueError(f"ASR input changed: {ident}")
        saved = next((p for p in previous if p["id"] == ident
                      and p["audio_sha256"] == item["sha256"] and p["expected"] == item["text"]), None)
        if saved is None:
            if model is None:
                model = WhisperModel(model_name, device="cpu", compute_type="int8",
                                     cpu_threads=4, local_files_only=True)
            segments, _ = model.transcribe(item["audio"], language="de", beam_size=5, vad_filter=False)
            recognized = " ".join(segment.text.strip() for segment in segments)
            saved = {"id": ident, "expected": item["text"], "recognized": recognized,
                     "matches": tokens(item["text"]) == tokens(recognized),
                     "audio_sha256": item["sha256"], "speaker": item["speaker"]}
        results.append(saved)
        atomic_json(target, {"model": f"faster-whisper-{model_name}", "complete": False,
                            "human_listening": False, "turns": results})
        print(f"Fide ASR {ident}: {'match' if saved['matches'] else 'review flag'}", flush=True)
    if not results:
        raise ValueError("No fide speech selected for local ASR.")
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
    if args.stage == "align":
        align(args.build.resolve())
    else:
        review(args.build.resolve(), args.model, set(args.ids) if args.ids else None)
