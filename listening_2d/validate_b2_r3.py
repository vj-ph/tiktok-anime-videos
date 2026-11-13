"""Verify B2 sequence, approved content, exact source PCM and actual exports."""

import argparse
import html
from pathlib import Path
import re
import wave

from audit_b2_sequence_r3 import compare_sequence
from compose_b2_r3 import visual_plan, word_mapping
from prepare_b2 import approved_episode, read, schedule
from prepare_b2_r3 import plan
from prepare_sample import ROOT, atomic_json, sha256_file
from process_b2 import VISIBLE_INSTRUCTIONS
from validate_full import audio_info, block, encoded_events


def verify_files(files):
    for path, digest in files.items():
        if sha256_file(Path(path)) != digest:
            raise ValueError(f"B2 pinned input changed: {path}")


def validate(build, encoded=False):
    timeline, content = read(build / "timeline.json"), read(build / "sample_content.json")
    manifest, pin = read(build / "audio_manifest.json"), read(build / "input_pin.json")
    episode = approved_episode()
    assert content["episode"] == episode
    verify_files(pin["files"])
    verify_files(pin["book"])
    verify_files(read(build / "research_input_pin.json")["files"])
    preservation = read(build / "source_preservation.json")
    assert sha256_file(Path(preservation["source"]) / "delivery_manifest.json") == preservation["manifest_sha256"]
    verify_files(preservation["code_inputs"])
    old_timeline = read(Path(preservation["source"]) / "timeline.json")
    assert timeline["total_frames"] == old_timeline["total_frames"] + 72
    for asset in read(ROOT / "assets" / "sfx" / "sources.json")["assets"]:
        verify_files({str(ROOT / "assets" / "sfx" / asset["file"]): asset["sha256"]})
    for refs in pin["voices"].values():
        for item in refs.values():
            verify_files({item["path"]: item["sha256"]})
    assert pin["voices"]["dialogue_male"]["audio"]["sha256"] != pin["voices"][
        "dialogue_female"]["audio"]["sha256"]
    sequence = compare_sequence(episode, timeline)
    assert sequence["matches_requested_sequence"], sequence["issues"]
    approved_plan = plan(episode)
    assert content["cards"] == approved_plan["cards"]
    for turn in approved_plan["turns"]:
        item = manifest[turn["id"]]
        assert item["text"] == turn["text"] and item["speaker"] == turn["speaker"]
        assert item["atempo"] == 0.8
        verify_files({item["raw_audio"]: item["raw_sha256"],
                      item["processed_audio"]: item["processed_sha256"]})
    expected = schedule(approved_plan["events"], manifest)
    assert timeline["events"] == expected["events"]
    assert len(timeline["turns"]) == len(expected["turns"])
    for actual, scheduled in zip(timeline["turns"], expected["turns"]):
        assert {k: v for k, v in actual.items() if k not in ("words", "alignment_key")} == scheduled
        if actual["id"] in VISIBLE_INSTRUCTIONS:
            from align_words import validate_words
            validate_words(actual["words"], actual["text"], actual["wav_duration"])
            old = next(t for t in old_timeline["turns"] if t["id"] == actual["id"])
            assert actual["words"] == old["words"] and actual["alignment_key"] == old["alignment_key"]
    aligned = read(build / "word_alignment.json")
    assert aligned["provenance"] == timeline["word_alignment"]
    actual_turns = {t["id"]: t for t in timeline["turns"]}
    assert {t["id"] for t in aligned["turns"]} == VISIBLE_INSTRUCTIONS
    for turn in aligned["turns"]:
        assert all(turn[k] == actual_turns[turn["id"]][k] for k in ("start", "words", "alignment_key"))
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
                assert not any(samples), f"Non-silent B2 pause: {event['id']}"
                pauses[event["id"]] = event["duration"]
            else:
                audio = Path(event["audio"])
                assert sha256_file(audio) == event["sha256"]
                with wave.open(str(audio), "rb") as clip:
                    exact = block(clip, 0, audio_info(audio))
                assert samples[:len(exact)] == exact
                assert not any(samples[len(exact):])
            cursor = event["end_frame"]
    receipt = read(build / "composition_receipt.json")
    assert receipt["timeline_sha256"] == sha256_file(build / "timeline.json")
    assert receipt["generator_sha256"] == sha256_file(ROOT / "compose_b2_r3.py")
    assert receipt["template_sha256"] == sha256_file(ROOT / "composition" / "index.html")
    texts = {f"instruction_{s['part']}": s["instruction"] for s in episode["sections"]}
    texts["checking_instruction"] = episode["sections"][1]["checking_instruction"]
    mappings = {ident: word_mapping(timeline, text, ident) for ident, text in texts.items()}
    assert receipt["instruction_mapping"] == [w for words in mappings.values() for w in words]
    all_questions = [q for s in episode["sections"] for g in s["groups"] for q in g["questions"]]
    for layout in ("landscape", "portrait"):
        expected_scenes = visual_plan(timeline, layout)
        assert receipt["scenes"][layout] == expected_scenes
        document = (build / layout / "index.html").read_text(encoding="utf-8")
        for forbidden in ("ÖIF B1", "ÖIF A2", "Geführte Hörübung", "Lösungen nach jeder Aufgabe", "{{"):
            assert forbidden not in document
        scenes = re.findall(r'<section id="scene-(\d+)"[^>]*data-start="([^"]+)"'
                            r'[^>]*data-duration="([^"]+)"[^>]*>(.*?)</section>', document, re.S)
        assert len(scenes) == len(expected_scenes)
        clock = 0
        for (index, start, duration, body), event in zip(scenes, expected_scenes):
            assert float(start) == event["start"] and float(duration) == event["duration"]
            assert event["start_frame"] == clock
            clock = event["end_frame"]
            keys = (content["cards"][event["card"]]["questions"] if event["kind"] == "reveal"
                    else all_questions if event["card"] == "summary" else [])
            if event["kind"] == "reveal" and event.get("reveal_group"):
                if event.get("page"):
                    keys = keys[(event["page"] - 1) * 5:event["page"] * 5]
                elif event["reveal_group"] == 1:
                    keys = keys[:5]
            expected_keys = [f'{q["number"]}:{"richtig" if q["answer"] else "falsch"}' for q in keys]
            assert re.findall(r'data-answer="([^"]+)"', body) == expected_keys, f"Early/wrong keys: {layout}/{index}"
            if event["card"] in content["cards"]:
                questions = content["cards"][event["card"]]["questions"]
                if event.get("page"):
                    questions = questions[(event["page"] - 1) * 5:event["page"] * 5]
                statements = re.findall(r'class="statement-text">([^<]+)</span>', body)
                assert [html.unescape(t) for t in statements] == [q["question"] for q in questions]
                assert "Deine Lösungen" not in body and "answer-board" not in body
                assert re.findall(r'data-question="(\d+)"', body) == [str(q["number"]) for q in questions]
            if event["card"] in VISIBLE_INSTRUCTIONS:
                labels = re.findall(r'class="instruction-word" id="[^"]+">([^<]*)', body)
                assert [html.unescape(t) for t in labels] == texts[event["card"]].split()
            assert f'class="phase-label">{html.escape(event["phase"])}</span>' in body
        assert clock == timeline["total_frames"]
        assert "<h1>ÖIF B2 Hören</h1>" in scenes[0][3]
        for name, digest in read(build / layout / "assets_manifest.json").items():
            assert sha256_file(build / layout / "assets" / name) == digest
    report = dict(scope="full", source_clock="passed", independent_sequence=sequence,
                  exact_pcm_placement="passed", approved_content="passed", answer_visibility="passed",
                  silences=pauses, frames=cursor, duration=timeline["duration"],
                  instruction_words=sum(len(v) for v in mappings.values()),
                  portrait_pagination="30/30 reading, item-51 speech switch, 15/15 checking, 3/3 inline reveal",
                  human_listening="not performed")
    if encoded:
        report["encoded"] = {layout: encoded_events(build, timeline, layout)
                             for layout in ("landscape", "portrait")}
    atomic_json(build / ("validation.json" if encoded else "source_validation.json"), report)
    print(f"B2 {'encoded/source' if encoded else 'source'} passed: {cursor} frames, {timeline['duration']:.3f}s.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--encoded", action="store_true")
    args = parser.parse_args()
    validate(args.build.resolve(), args.encoded)
