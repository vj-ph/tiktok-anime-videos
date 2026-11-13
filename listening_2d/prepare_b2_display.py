"""Prepare unchanged B2 audio and measured words for the display-only revision."""

import argparse
import copy
from pathlib import Path
import shutil

from prepare_b2 import read
from prepare_sample import ROOT, atomic_json, sha256_file
from validate_b2_r3 import verify_files

FULL = ROOT / "builds" / "oeif_b2_listening_full_production_r3"
SHORT = ROOT / "builds" / "oeif_b2_listening_reduced_r1"
READING_TEXT = "Sie haben jetzt fünfzehn Sekunden Zeit, die Aufgaben zu lesen."


def verify_sources():
    layers = []
    for source in (FULL, SHORT, ROOT / "builds" / "oeif_b2_listening_full_production_r2"):
        manifest = read(source / "delivery_manifest.json")
        audit = read(source / "delivery_audit.json")
        assert audit["manifest_sha256"] == sha256_file(source / "delivery_manifest.json")
        files = {str(source / name): digest for name, digest in manifest["files"].items()}
        files.update({str(source / name): sha256_file(source / name)
                      for name in ("delivery_manifest.json", "delivery_audit.json")})
        verify_files(files)
        verify_files(manifest["code_inputs"])
        verify_files(manifest["inputs"]["files"])
        verify_files(manifest["inputs"].get("book", {}))
        layers.append(dict(source=str(source), files=files, code_inputs=manifest["code_inputs"],
                           input_files=manifest["inputs"]["files"]))
    return layers


def align_reading(build):
    from align_words import align_build, validate_words
    inputs = build / "alignment_inputs"
    inputs.mkdir(exist_ok=True)
    turn = copy.deepcopy(next(t for t in read(SHORT / "teil_1" / "timeline.json")["turns"]
                              if t["id"] == "reading_instruction"))
    assert turn["text"] == READING_TEXT and sha256_file(Path(turn["audio"])) == turn["sha256"]
    path = inputs / "timeline.json"
    if not path.exists():
        atomic_json(path, {"language": "de", "turns": [turn]})
    align_build(inputs)
    measured = read(path)
    aligned = measured["turns"][0]
    assert all(aligned[k] == turn[k] for k in ("audio", "sha256", "text", "wav_duration"))
    validate_words(aligned["words"], READING_TEXT, turn["wav_duration"])
    atomic_json(build / "reading_alignment.json", {
        "audio": turn["audio"], "audio_sha256": turn["sha256"], "text": READING_TEXT,
        "words": aligned["words"], "alignment_key": aligned["alignment_key"],
        "provenance": measured["word_alignment"],
        "minimum_score": min(w["score"] for w in aligned["words"]),
        "note": "Locally measured on the existing processed WAV; no synthesis or estimated timing.",
    })


def prepare(build):
    if build.exists():
        raise ValueError("Choose a fresh display-revision build.")
    layers = verify_sources()
    build.mkdir(parents=True)
    atomic_json(build / "source_preservation.json", {"layers": layers})
    atomic_json(build / "input_pin.json", {
        "files": {str(Path(__file__).resolve()): sha256_file(Path(__file__)),
                  str(SHORT / "audio_review_resolution.json"): sha256_file(SHORT / "audio_review_resolution.json"),
                  str(FULL / "audio_review_binding.json"): sha256_file(FULL / "audio_review_binding.json")},
        "request": "Separate highlighted 15-second reading-instruction slide in shorts; different Richtig/Falsch colors in shorts and both full ratios.",
        "audio_contract": "No new speech, tempo processing, timeline edits, silence changes or source overwrites.",
    })
    jobs = {}
    for name, source, relative, layout in (
        ("full_landscape", FULL, "full", "landscape"),
        ("full_portrait", FULL, "full", "portrait"),
        *((f"teil_{p}", SHORT / f"teil_{p}", f"teil_{p}", "portrait") for p in (1, 2, 3)),
    ):
        clip = build / relative
        clip.mkdir(exist_ok=True)
        for filename in ("timeline.json", "sample_content.json", "audio_manifest.json", "dialogue.wav",
                         "word_alignment.json", "audio_review_resolution.json", "audio_review_binding.json",
                         "inherited_audio_review_resolution.json", "research_input_pin.json"):
            if (source / filename).exists() and not (clip / filename).exists():
                shutil.copyfile(source / filename, clip / filename)
        shutil.copytree(source / layout / "assets", clip / layout / "assets")
        for filename in ("hyperframes.json", "assets_manifest.json"):
            shutil.copyfile(source / layout / filename, clip / layout / filename)
        receipt = read(source / "composition_receipt.json")
        scenes = receipt["scenes"][layout] if relative == "full" else receipt["scenes"]
        jobs[name] = dict(name=name, clip=relative, layout=layout, source=str(source),
                          source_video=str(source / f"production_{layout}.mp4"),
                          source_html=str(source / layout / "index.html"), scenes=scenes)
    atomic_json(build / "jobs.json", jobs)
    align_reading(build)
    print("Prepared five source-bound layouts; existing reading cue aligned without TTS.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "align"))
    parser.add_argument("--build", required=True, type=Path)
    args = parser.parse_args()
    {"prepare": prepare, "align": align_reading}[args.stage](args.build.resolve())
