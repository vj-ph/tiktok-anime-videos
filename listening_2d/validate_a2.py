"""Verify A2 task/repeat structure, exact PCM placement and encoded deliveries."""

import argparse
import html
from pathlib import Path
import re
import subprocess
import wave

from compose_a2 import word_mapping
from prepare_a2 import EPISODE, plan, read, schedule
from prepare_sample import ROOT, atomic_json, sha256_file
from process_a2 import short_plan
from validate_full import audio_info, block, encoded_events


def verify_files(files):
    for path, digest in files.items():
        if sha256_file(Path(path)) != digest:
            raise ValueError(f"Pinned input changed: {path}")


def validate(build, encoded=False):
    timeline, content = read(build / "timeline.json"), read(build / "sample_content.json")
    manifest, pin = read(build / "audio_manifest.json"), read(build / "input_pin.json")
    episode = read(EPISODE)
    assert content["episode"] == episode
    short = timeline["scope"] == "short"
    if short:
        parent_pin = read(Path(pin["parent_pin"]))
        assert sha256_file(Path(pin["parent_pin"])) == pin["source_pin_sha256"]
        assert sha256_file(ROOT / "process_a2.py") == parent_pin["generator_sha256"]
        verify_files(parent_pin["files"])
        source = Path(pin["source"])
        full = read(source / "timeline.json")
        original_content = read(source / "sample_content.json")
        section = episode["sections"][timeline["part"] - 1]
        selected = [g for g in section["groups"]
                    if any(q["number"] in timeline["selected"] for q in g["questions"])]
        assert timeline["selected"] == [q["number"] for g in selected for q in g["questions"]]
        assert manifest == read(source / "audio_manifest.json")
        planned = short_plan(full, section, selected)
        expected_cards = {g["id"]: original_content["cards"][g["id"]] for g in selected}
        overview = f"overview_{timeline['part']}"
        expected_cards[overview] = {**original_content["cards"][overview],
                                   "questions": [q for g in selected for q in g["questions"]]}
        assert content["cards"] == expected_cards
        assert timeline["duration"] < 180
        title = timeline["events"][0]
        padding = title["end_frame"] * 2000 - title["audio_samples"]
        assert 24000 <= padding < 26000
    else:
        verify_files(pin["files"])
        verify_files(pin["book"])
        for voice in pin["voices"].values():
            for entry in voice.values():
                verify_files({entry["path"]: entry["sha256"]})
        approved_plan = plan(episode)
        planned = approved_plan["events"]
        assert content["cards"] == approved_plan["cards"]
        for turn in approved_plan["turns"]:
            item = manifest[turn["id"]]
            assert item["text"] == turn["text"] and item["speaker"] == turn["speaker"]
            assert item["atempo"] == 0.8
        assert pin["voices"]["service_female"]["audio"]["sha256"] != pin["voices"][
            "announcement_female"]["audio"]["sha256"]
    expected = schedule(planned, manifest, timeline["scope"], timeline.get("part"), timeline.get("selected"))
    assert timeline["events"] == expected["events"]
    assert len(timeline["turns"]) == len(expected["turns"])
    for actual, scheduled in zip(timeline["turns"], expected["turns"]):
        assert {k: v for k, v in actual.items() if k not in ("words", "alignment_key")} == scheduled
        if actual["id"].startswith("instruction_"):
            from align_words import validate_words
            validate_words(actual["words"], actual["text"], actual["wav_duration"])
    if not short:
        aligned = read(build / "word_alignment.json")
        assert aligned == read(build / "alignment_inputs" / "word_alignment.json")
        assert aligned["provenance"] == timeline["word_alignment"]
        actual = {t["id"]: t for t in timeline["turns"]}
        assert {t["id"] for t in aligned["turns"]} == {f"instruction_{p}" for p in range(1, 5)}
        for turn in aligned["turns"]:
            assert turn["start"] == actual[turn["id"]]["start"]
            assert turn["words"] == actual[turn["id"]]["words"]
            assert turn["alignment_key"] == actual[turn["id"]]["alignment_key"]
    assert timeline["total_frames"] == expected["total_frames"]
    assert timeline["duration"] == timeline["total_frames"] / 24
    assert len({e["id"] for e in timeline["events"]}) == len(timeline["events"])
    assert audio_info(build / "dialogue.wav") == timeline["total_frames"] * 2000
    pauses, cursor = {}, 0
    with wave.open(str(build / "dialogue.wav"), "rb") as track:
        for event in timeline["events"]:
            assert event["start_frame"] == cursor
            samples = block(track, cursor * 2000, event["end_frame"] * 2000)
            if event["kind"] == "silence":
                assert not any(samples), f"Non-silent pause: {event['id']}"
                pauses[event["id"]] = event["duration"]
            else:
                audio = Path(event["audio"])
                assert sha256_file(audio) == event["sha256"]
                with wave.open(str(audio), "rb") as clip:
                    exact = block(clip, 0, audio_info(audio))
                assert samples[:len(exact)] == exact
                assert not any(samples[len(exact):])
                if event["kind"] == "reveal":
                    assert event["duration"] == 3 and event["audio_id"] == "chime_remove"
            cursor = event["end_frame"]
    receipt = read(build / "composition_receipt.json")
    assert receipt["timeline_sha256"] == sha256_file(build / "timeline.json")
    assert receipt["generator_sha256"] == sha256_file(ROOT / "compose_a2.py")
    assert receipt["template_sha256"] == sha256_file(ROOT / "composition" / "index.html")
    expected_words = []
    if not short:
        for section in episode["sections"]:
            part = section["part"]
            expected_words.extend(word_mapping(
                timeline, section["instruction"], f"instruction_{part}",
                f"#instruction-{part}-word-{{i}}"))
    assert receipt["instruction_mapping"] == expected_words
    assert [i for s in receipt["scenes"] for i in s["event_ids"]] == [e["id"] for e in timeline["events"]]
    for layout in receipt["layouts"]:
        document = (build / layout / "index.html").read_text(encoding="utf-8")
        for forbidden in ("ÖIF B1", "Geführte Hörübung", "Lösungen nach jeder Aufgabe", "{{"):
            assert forbidden not in document
        scenes = re.findall(r'<section id="scene-(\d+)"[^>]*data-start="([^"]+)"'
                            r'[^>]*data-duration="([^"]+)"[^>]*>(.*?)</section>', document, re.S)
        assert len(scenes) == len(receipt["scenes"])
        for (index, start, duration, body), event in zip(scenes, receipt["scenes"]):
            assert float(start) == event["start"] and float(duration) == event["duration"]
            visible_keys = re.findall(r'data-answer="([^"]+)"', body)
            keys = ([q["answer"] for q in content["cards"][event["card"]]["questions"]]
                    if event["kind"] == "reveal" else [])
            assert visible_keys == keys, f"Early/wrong keys: {layout}, scene {index}"
            assert f'class="phase-label">{html.escape(event["phase"])}</span>' in body
            if event["card"].startswith("instruction_"):
                labels = re.findall(r'class="instruction-word" id="[^"]+">([^<]*)', body)
                assert [html.unescape(label) for label in labels] == episode["sections"][
                    event["part"] - 1]["instruction"].split()
        for name, digest in read(build / layout / "assets_manifest.json").items():
            assert sha256_file(build / layout / "assets" / name) == digest
    report = {"scope": timeline["scope"], "source_clock": "passed", "exact_pcm_placement": "passed",
              "unchanged_approved_content": "passed", "answer_visibility": "passed",
              "repeats": "Exact same normalized WAVs reused for each approved playback",
              "silences": pauses, "frames": cursor, "duration": timeline["duration"],
              "instruction_words": len(expected_words), "human_listening": "not performed"}
    if encoded:
        report["encoded"] = {layout: encoded_events(build, timeline, layout) for layout in receipt["layouts"]}
        if short:
            metadata = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=duration",
                 "-of", "json", str(build / "production_portrait.mp4")],
                check=True, capture_output=True, text=True)
            import json
            values = json.loads(metadata.stdout)
            assert float(values["format"]["duration"]) < 180
            assert all(float(s["duration"]) < 180 for s in values["streams"])
    atomic_json(build / ("validation.json" if encoded else "source_validation.json"), report)
    print(f"A2 {'encoded/source' if encoded else 'source'} passed: {cursor} frames, "
          f"{timeline['duration']:.3f}s.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--encoded", action="store_true")
    args = parser.parse_args()
    validate(args.build.resolve(), args.encoded)
