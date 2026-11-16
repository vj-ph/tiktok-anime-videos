"""Verify reviewed fide content, exact source audio, hidden exam text and encoded exports."""

import argparse
import html
from pathlib import Path
import re
import wave

from audit_fide_sequence import compare_sequence
from compose_fide import word_mapping
from prepare_fide import ROOT, approved_episode, atomic_json, plan, read, schedule, sha256_file, verify_files
from validate_full import audio_info, block, encoded_events


def validate(build, encoded=False):
    timeline, content = read(build / "timeline.json"), read(build / "sample_content.json")
    if timeline.get("fixture_only"):
        raise ValueError("A synthetic layout fixture cannot be validated or rendered as a delivery.")
    episode = approved_episode()
    assert content["episode"] == episode
    inputs = read(build / "input_pin.json")
    for key in ("files", "research", "official"):
        verify_files(inputs[key])
    for role in inputs["voices"].values():
        verify_files({ref["path"]: ref["sha256"] for ref in role.values()})
    planned, manifest = plan(episode), read(build / "audio_manifest.json")
    assert content["cards"] == planned["cards"]
    assert set(manifest) == {turn["id"] for turn in planned["turns"]}
    for turn in planned["turns"]:
        actual = manifest[turn["id"]]
        assert all(actual[key] == value for key, value in turn.items())
        assert actual["atempo"] == .8
        verify_files({actual["raw_audio"]: actual["raw_sha256"],
                      actual["processed_audio"]: actual["processed_sha256"],
                      actual["audio"]: actual["sha256"]})
        assert audio_info(Path(actual["audio"])) == actual["frames"]
    sequence = compare_sequence(timeline)
    assert sequence["ok"], sequence["issues"]
    expected = schedule(planned["events"], manifest)
    assert timeline["events"] == expected["events"]
    assert len(timeline["turns"]) == len(expected["turns"])
    for actual, scheduled in zip(timeline["turns"], expected["turns"]):
        assert {k: v for k, v in actual.items() if k not in ("words", "alignment_key")} == scheduled
    mappings = {t["id"]: word_mapping(t) for t in timeline["turns"] if t["visible"]}
    alignment = read(build / "word_alignment.json")
    assert alignment["provenance"] == timeline["word_alignment"]
    assert set(mappings) == {t["id"] for t in alignment["turns"]}
    for selected in alignment["turns"]:
        actual = next(t for t in timeline["turns"] if t["id"] == selected["id"])
        assert all(actual[key] == value for key, value in selected.items())
    assert timeline["duration"] == timeline["total_frames"] / 24
    assert audio_info(build / "dialogue.wav") == timeline["total_frames"] * 2000
    silences = {}
    with wave.open(str(build / "dialogue.wav"), "rb") as track:
        for event in timeline["events"]:
            samples = block(track, event["start_frame"] * 2000, event["end_frame"] * 2000)
            if event["kind"] == "silence":
                assert not any(samples), f"Source pause contains sound: {event['id']}"
                silences[event["id"]] = event["duration"]
            else:
                audio = Path(event["audio"])
                with wave.open(str(audio), "rb") as clip:
                    original = block(clip, 0, audio_info(audio))
                assert samples[:len(original)] == original
                assert not any(samples[len(original):])
    receipt = read(build / "composition_receipt.json")
    assert receipt["timeline_sha256"] == sha256_file(build / "timeline.json")
    assert receipt["generator_sha256"] == sha256_file(ROOT / "compose_fide.py")
    assert receipt["template_sha256"] == sha256_file(ROOT / "composition" / "index.html")
    assert receipt["word_mappings"] == mappings
    for layout in ("landscape", "portrait"):
        folder = build / layout
        document = (folder / "index.html").read_text(encoding="utf-8")
        assert sha256_file(folder / "index.html") == receipt["layouts"][layout]["html_sha256"]
        for forbidden in ("ÖIF", "Österreich", "Geführte Hörübung", "{{"):
            assert forbidden not in document
        scenes = re.findall(r'<section id="scene-(\d+)"[^>]*data-start="([^"]+)"'
                            r'[^>]*data-duration="([^"]+)"[^>]*data-event-id="([^"]+)"[^>]*>(.*?)</section>',
                            document, re.S)
        assert len(scenes) == len(timeline["events"])
        final_answer = next(e["end"] for e in timeline["events"] if e["id"] == "answer_18")
        for (index, start, duration, ident, body), event in zip(scenes, timeline["events"]):
            assert (float(start), float(duration), ident) == (event["start"], event["duration"], event["id"])
            keys = re.findall(r'data-answer="([^"]+)"', body)
            if ident.startswith("solution_") and ident != "solutions_instruction":
                number = int(event["card"].split("_")[-1])
                item = content["cards"][f"item_{number}"]
                assert keys == [f'{number}:{item.get("answer", "model")}']
                assert event["start"] >= final_answer
            else:
                assert not keys, f"Early answer in {layout}/{ident}"
            if event["card"].startswith("item_"):
                item = content["cards"][event["card"]]
                assert html.escape(item["question"]) not in body
                assert html.escape(item["recording"]) not in body
                assert 'class="instruction-word"' not in body
                assert body.count('class="picture-option"') == (3 if item["level"] == "A2" else 0)
            if event.get("visible"):
                labels = re.findall(r'class="instruction-word" id="[^"]+">([^<]+)</span>', body)
                assert [html.unescape(label) for label in labels] == [w["label"] for w in mappings[ident]]
        verify_files({str(folder / "assets" / name): digest
                      for name, digest in read(folder / "assets_manifest.json").items()})
        for picture in receipt["layouts"][layout]["picture_crops"].values():
            verify_files({picture["source"]: picture["source_sha256"]})
    report = {"scope": "full", "source_clock": "passed", "independent_sequence": sequence,
              "reviewed_script": "passed", "exact_pcm_placement": "passed",
              "exam_questions_transcripts_and_answers_hidden": "passed",
              "frames": timeline["total_frames"], "duration": timeline["duration"],
              "silences": silences, "human_listening": "not performed"}
    if encoded:
        report["encoded"] = {layout: encoded_events(build, timeline, layout)
                             for layout in ("landscape", "portrait")}
    atomic_json(build / ("validation.json" if encoded else "source_validation.json"), report)
    print(f"Fide {'encoded and source' if encoded else 'source'} validation passed.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--encoded", action="store_true")
    args = parser.parse_args()
    validate(args.build.resolve(), args.encoded)
