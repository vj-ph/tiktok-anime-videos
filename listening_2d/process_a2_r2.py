"""Align, independently transcribe and budget complete A2 exercise groups."""

import argparse
import copy
from pathlib import Path

from prepare_a2_r2 import SOURCE, read, schedule
from prepare_sample import atomic_json, mix_events, sha256_file, write_wav


def align(build):
    from align_words import validate_words
    timeline = read(build / "timeline.json")
    original = read(SOURCE / "timeline.json")
    inherited = read(SOURCE / "word_alignment.json")
    provenance = copy.deepcopy(inherited["provenance"])
    selected = [t for t in timeline["turns"] if t["id"].startswith("instruction_")]
    if len(selected) != 4:
        raise ValueError("Expected four A2 instructions.")
    inputs = build / "alignment_inputs"
    inputs.mkdir(exist_ok=True)
    measured = {t["id"]: t for t in original["turns"]}
    for turn in selected:
        old = measured[turn["id"]]
        if any(turn[key] != old[key] for key in ("text", "sha256", "wav_duration", "speaker")):
            raise ValueError("Only byte-identical instruction audio may inherit word timings.")
        turn.update(words=measured[turn["id"]]["words"],
                    alignment_key=measured[turn["id"]]["alignment_key"])
        validate_words(turn["words"], turn["text"], turn["wav_duration"])
    alignment = {"provenance": provenance, "turns": [
        {key: turn[key] for key in ("id", "start", "words", "alignment_key")}
        for turn in selected]}
    timeline["word_alignment"] = provenance
    atomic_json(build / "timeline.json", timeline)
    atomic_json(build / "word_alignment.json", alignment)
    atomic_json(inputs / "word_alignment.json", alignment)
    atomic_json(inputs / "timeline.json", {"language": "de", "turns": selected,
                                         "word_alignment": provenance})
    atomic_json(build / "alignment_inheritance.json", {
        "source": str(SOURCE / "word_alignment.json"),
        "sha256": sha256_file(SOURCE / "word_alignment.json"),
        "new_starts": {turn["id"]: turn["start"] for turn in selected},
        "method": "Verified identical text, voice, WAV hash and duration; relative measured intervals unchanged.",
    })


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
                            "scope": "Local unprompted ASR, not human listening/accent certification.",
                            "turns": results})
        print(f"ASR {ident}: {'match' if result['matches'] else 'review flag'}", flush=True)
    report = read(target)
    report["complete"] = True
    report["selected_ids"] = sorted(ids) if ids is not None else "all speech"
    atomic_json(target, report)


def short_plan(timeline, section, selected):
    part = section["part"]
    ids = {g["id"] for g in selected}
    opening = {"id": f"short_title_{part}", "kind": "speech", "audio_id": f"short_title_{part}",
               "card": "short_title", "phase": "Titel", "part": part, "title_padding": True}
    reading = next(e for e in timeline["events"] if e["id"] == f"part_{part}_read")
    start = next(e for e in timeline["events"] if e["id"] == f"part_{part}_start")
    body = [e for e in timeline["events"] if e["card"] in ids]
    return [opening, copy.deepcopy(reading), copy.deepcopy(start), *copy.deepcopy(body),
            copy.deepcopy(next(e for e in timeline["events"] if e["id"] == "cta"))]


def shorts(source, build):
    if build.exists():
        raise ValueError("Use a fresh A2 short build.")
    content = read(source / "sample_content.json")
    timeline, manifest = read(source / "timeline.json"), read(source / "audio_manifest.json")
    budgets = {}
    for section in content["episode"]["sections"]:
        part, selected, candidates = section["part"], [], []
        for group in section["groups"]:
            candidate = [*selected, group]
            numbered = [q["number"] for g in candidate for q in g["questions"]]
            clock = schedule(short_plan(timeline, section, candidate), manifest, "short", part, numbered)
            candidates.append({"groups": [g["id"] for g in candidate], "seconds": clock["duration"]})
            if clock["duration"] >= 180:
                break
            selected = candidate
        if not selected:
            raise ValueError(f"Teil {part}'s complete first recording/repeats/pauses do not fit: {candidates}")
        numbered = [q["number"] for g in selected for q in g["questions"]]
        budgets[str(part)] = {"groups": [g["id"] for g in selected], "numbers": numbered,
                             "candidates": candidates}
    build.mkdir(parents=True)
    source_files = ["timeline.json", "dialogue.wav", "audio_manifest.json",
                    "sample_content.json", "input_pin.json", "voice_references.json"]
    if (source / "delivery_manifest.json").exists():
        source_files.append("delivery_manifest.json")
    atomic_json(build / "input_pin.json", {
        "source": str(source), "files": {str(source / p): sha256_file(source / p) for p in source_files},
        "generator_sha256": sha256_file(Path(__file__)),
    })
    for section in content["episode"]["sections"]:
        part = section["part"]
        chosen = [g for g in section["groups"] if g["id"] in budgets[str(part)]["groups"]]
        clock = schedule(short_plan(timeline, section, chosen), manifest,
                         "short", part, budgets[str(part)]["numbers"])
        folder = build / f"teil_{part}"
        folder.mkdir()
        cards = {key: copy.deepcopy(card) for key, card in content["cards"].items()
                 if key in budgets[str(part)]["groups"] or key == f"overview_{part}"}
        cards[f"overview_{part}"]["questions"] = [q for g in chosen for q in g["questions"]]
        atomic_json(folder / "timeline.json", clock)
        atomic_json(folder / "audio_manifest.json", manifest)
        atomic_json(folder / "sample_content.json", {**content, "cards": cards})
        atomic_json(folder / "input_pin.json", {"source": str(source),
                    "source_pin_sha256": sha256_file(build / "input_pin.json"),
                    "parent_pin": str(build / "input_pin.json")})
        write_wav(folder / "dialogue.wav", mix_events(clock["events"]))
        budgets[str(part)].update(duration=clock["duration"], frames=clock["total_frames"])
        print(f"A2 short Teil {part}: {clock['duration']:.3f}s; tasks {clock['selected']}.", flush=True)
    atomic_json(build / "budgets.json", budgets)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("align", "review", "shorts"))
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--model", default="small", choices=("small", "medium"))
    parser.add_argument("--ids", nargs="+", help="Targeted independent ASR recheck IDs.")
    args = parser.parse_args()
    build = args.build.resolve()
    if args.stage == "align":
        align(build)
    elif args.stage == "review":
        review(build, args.model, set(args.ids) if args.ids else None)
    else:
        if not args.source:
            parser.error("--source is required for shorts.")
        shorts(args.source.resolve(), build)
