"""Prepare three authorized B2 excerpts with adapted short-practice pauses."""

import argparse
import copy
from pathlib import Path
import shutil

from prepare_b2 import read, schedule
from prepare_sample import (
    ROOT, MODEL, atomic_json, mix_events, normalize, prepare_turn_audio,
    sha256_file, synthesize, tempo_turn_audio, write_wav,
)
from validate_b2_r3 import verify_files

SOURCE = ROOT / "builds" / "oeif_b2_listening_full_production_r3"
SELECTIONS = {1: [41, 42], 2: [49], 3: [56, 57]}
TOTALS = {1: 5, 2: 10, 3: 5}
NUMBERS = {1: "eins", 2: "zwei", 3: "drei"}
READING_TEXT = "Sie haben jetzt fünfzehn Sekunden Zeit, die Aufgaben zu lesen."
SELECTED_EVENTS = {
    1: [
        ("part_1_read", 15), ("part_1_start", None),
        ("news_theatre", None), ("news_corrections", None),
        ("b2_p1_news_answer", 10), ("b2_p1_news_reveal", None),
        ("b2_p1_news_transition", None),
    ],
    2: [
        ("part_2_read", 15), ("part_2_start", None),
        ("interview_q49", None), ("interview_49", None),
        ("b2_p2_learning_answer", 10), ("b2_p2_learning_reveal", None),
        ("b2_p2_learning_transition", None),
    ],
    3: [
        ("b2_p3_parcel_cue", None), ("short_56", None),
        ("b2_p3_parcel_answer", 15), ("b2_p3_parcel_reveal", None),
        ("b2_p3_parcel_transition", None),
        ("b2_p3_stage_cue", None), ("short_57", None),
        ("b2_p3_stage_answer", 15), ("b2_p3_stage_reveal", None),
        ("b2_p3_stage_transition", None),
    ],
}


def title_text(part):
    return f"Ö I F B zwei Hören. Teil {NUMBERS[part]}."


def verify_source():
    manifest = read(SOURCE / "delivery_manifest.json")
    assert read(SOURCE / "delivery_audit.json")["manifest_sha256"] == sha256_file(
        SOURCE / "delivery_manifest.json")
    verify_files({str(SOURCE / name): digest for name, digest in manifest["files"].items()})
    verify_files(manifest["code_inputs"])
    verify_files(manifest["inputs"]["files"])
    verify_files(manifest["inputs"]["book"])
    preserved = read(SOURCE / "source_preservation.json")
    verify_files(preserved["files"])
    verify_files(preserved["code_inputs"])
    binding = read(SOURCE / "audio_review_binding.json")
    verify_files(binding["files"])
    verify_files(binding["speech_audio_files"])
    return manifest


def planned_events(part, original, title_samples):
    lookup = {e["id"]: e for e in original["events"]}
    intro_frames = (title_samples + 24000 + 1999) // 2000
    result = [dict(id="reduced_intro", kind="speech", audio_id="reduced_intro",
                   card="title", phase="Titel", part=part, seconds=intro_frames / 24)]
    if part < 3:
        result.append(dict(id="reading_instruction", kind="speech", audio_id="reading_instruction",
                           card=lookup[f"part_{part}_read"]["card"], phase="Aufgaben lesen", part=part))
    for ident, seconds in SELECTED_EVENTS[part] + [("cta", None)]:
        source = lookup[ident]
        event = {k: copy.deepcopy(source[k]) for k in
                 ("id", "kind", "audio_id", "card", "phase", "part", "seconds") if k in source}
        event["part"] = part
        if seconds is not None:
            event["seconds"] = seconds
        if ident.endswith("_transition"):
            event["phase"] = "Nächste Aufgabe" if ident == "b2_p3_parcel_transition" else "Weiter üben"
        result.append(event)
    return result


def prepare(build):
    if build.exists():
        raise ValueError("Choose a fresh reduced B2 build, separate from frozen deliveries.")
    source_manifest = verify_source()
    build.mkdir(parents=True)
    pins = dict(source=str(SOURCE), source_manifest_sha256=sha256_file(SOURCE / "delivery_manifest.json"),
                files={str(SOURCE / n): sha256_file(SOURCE / n) for n in
                       ("delivery_manifest.json", "delivery_audit.json", "timeline.json",
                        "sample_content.json", "audio_manifest.json", "audio_review_binding.json",
                        "audio_review_resolution.json", "voice_references.json")},
                narrator=read(SOURCE / "voice_references.json")["narrator"])
    pins["files"][str(Path(__file__).resolve())] = sha256_file(Path(__file__))
    for item in pins["narrator"].values():
        pins["files"][item["path"]] = item["sha256"]
    atomic_json(build / "input_pin.json", pins)
    atomic_json(build / "source_preservation.json", {
        "source": str(SOURCE),
        "files": {str(SOURCE / n): h for n, h in source_manifest["files"].items()},
        "code_inputs": source_manifest["code_inputs"],
        "previous_preservation": read(SOURCE / "source_preservation.json"),
    })
    atomic_json(build / "user_authorization.json", {
        "date": "2026-11-13", "request": "ok, generate the videos",
        "scope": "Three portrait reduced-practice clips with intact selected recordings, not complete Teile.",
        "selections": SELECTIONS, "pauses": {"1": [15, 10], "2": [15, 10], "3": [0, 15]},
        "part_3_response": "15 seconds after each selected recording.",
        "omissions": "Full instructions, six-report introduction, unrelated reports/interview turns, "
                     "30-second checking instruction, whole-section ending claims and final full-test overview.",
        "retain": "Original wording, numbering, recording speed, separate three-second inline reveals, "
                  "complete chimes, persistent logo/book/Amazon cue, voiced CTA.",
        "reading_instruction": READING_TEXT,
        "reading_instruction_request": "before reading silence, use TTS says something in german like "
                                       "you have 15 seconds to read the questions",
        "publication": "Local production only; no upload.",
    })
    turns = [dict(id=f"title_{part}", part=part, speaker="narrator", name="narrator",
                  text=title_text(part), pause_after=0) for part in SELECTIONS]
    turns.append(dict(id="reading_instruction", speaker="narrator", name="narrator",
                      text=READING_TEXT, pause_after=0))
    atomic_json(build / "title_speech_plan.json", {"turns": turns, "atempo": 0.8})
    audio = build / "title_audio"
    audio.mkdir()
    binding = {key: item["path"] for key, item in pins["narrator"].items()}
    raw = synthesize({"language": "de", "voices": {"narrator": binding}, "turns": turns},
                     ROOT, audio, MODEL, "cpu", 8)
    generated_audio = {}
    for turn, generated in zip(turns, raw):
        cleaned = prepare_turn_audio(turn["id"], generated, audio)
        slowed = tempo_turn_audio(turn["id"], cleaned, audio, 0.8)
        target = audio / f"{turn['id']}.wav"
        generated_audio[turn["id"]] = {
            **turn, **normalize(Path(slowed["audio"]), target), "audio": str(target),
            "sha256": sha256_file(target), "atempo": 0.8,
            "tempo_processing": slowed["tempo_processing"],
            "audio_chain": {stage: {"path": item["audio"], "sha256": sha256_file(Path(item["audio"]))}
                            for stage, item in (("raw", generated), ("prepared", cleaned), ("slowed", slowed))},
        }
    atomic_json(build / "new_audio_manifest.json", generated_audio)
    original, content = read(SOURCE / "timeline.json"), read(SOURCE / "sample_content.json")
    inherited = read(SOURCE / "audio_manifest.json")
    for part, numbers in SELECTIONS.items():
        clip = build / f"teil_{part}"
        clip.mkdir()
        title = generated_audio[f"title_{part}"]
        measured = copy.deepcopy(inherited)
        measured["reduced_intro"] = title
        measured["reading_instruction"] = generated_audio["reading_instruction"]
        events = planned_events(part, original, title["frames"])
        needed = {e["audio_id"] for e in events if "audio_id" in e}
        measured = {key: value for key, value in measured.items() if key in needed}
        timeline = schedule(events, measured)
        timeline.update(scope="reduced", part=part, selected_numbers=numbers,
                        total_questions=TOTALS[part], adapted_pauses=True)
        assert timeline["total_frames"] < 4320
        selected = copy.deepcopy(content)
        used_cards = {e["card"] for e in events}
        selected["cards"] = {key: value for key, value in selected["cards"].items() if key in used_cards}
        for card in selected["cards"].values():
            card["questions"] = [q for q in card["questions"] if q["number"] in numbers]
        atomic_json(clip / "sample_content.json", selected)
        atomic_json(clip / "audio_manifest.json", measured)
        atomic_json(clip / "timeline.json", timeline)
        write_wav(clip / "dialogue.wav", mix_events(timeline["events"]))
        shutil.copyfile(SOURCE / "audio_review_resolution.json", clip / "inherited_audio_review_resolution.json")
        print(f"Teil {part}: {numbers}, {timeline['total_frames']} frames / {timeline['duration']:.3f}s; "
              f"opening {timeline['events'][0]['duration']:.3f}s.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    prepare(parser.parse_args().build.resolve())
