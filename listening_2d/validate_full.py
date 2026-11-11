"""Check complete content, exact PCM timing, hidden keys and final encoded events."""

import argparse
import html
import json
import math
from pathlib import Path
import re
import subprocess
import wave

from compose_sample import ROOT, instruction_intervals, title_intervals
from prepare_sample import atomic_json, sha256_file


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def audio_info(path):
    with wave.open(str(path), "rb") as handle:
        assert (handle.getframerate(), handle.getnchannels(), handle.getsampwidth()) == (48000, 1, 2)
        return handle.getnframes()


def block(handle, start, end):
    handle.setpos(start)
    result = handle.readframes(end - start)
    assert len(result) == (end - start) * 2
    return result


def check_structure(timeline, content):
    events, cards = timeline["events"], content["cards"]
    scored = [q for card in cards.values() for q in card["questions"] if "number" in q]
    assert len(scored) == 20
    numbers = {str(q["number"]): q["answer"] for card in cards.values()
               for q in card["questions"] if "number" in q}
    assert set(numbers) == {str(number) for number in range(1, 21)}
    assert numbers == content["episode"]["review"]["answer_key"]
    assert len([name for name in cards if "example" in name]) == 3
    assert len([event for event in events if event["kind"] == "reveal"]) == 19
    assert len({event["id"] for event in events}) == len(events)
    approved = {}
    for section in content["episode"]["sections"]:
        if section["part"] == 3:
            for conversation in section["conversations"]:
                approved.update({q["number"]: q for q in conversation["questions"]})
        elif section["part"] == 4:
            approved.update({task["number"]: {
                "number": task["number"], "question": section["topic"],
                "options": section["options"], "answer": task["answer"],
            } for task in section["tasks"]})
        else:
            approved.update({task["number"]: task for task in section["tasks"]})
    assert all(question == approved[question["number"]] for question in scored)
    pauses = {}
    for name, card in cards.items():
        if name == "p4_statements":
            continue
        part, example = card["part"], "example" in name
        first = next((q.get("number") for q in card["questions"]), None)
        pre = (1 if part == 4 else 10) if example else (
            12 if part == 1 else 10 if part == 2 else
            (10 if first == 10 else 12) if part == 3 else 1)
        post = 10 if example and part in (1, 3) else 12
        for suffix, seconds in (("_read", pre), ("_answer", post)):
            event = next(e for e in events if e["id"] == name + suffix)
            assert event["kind"] == "silence" and event["duration"] == seconds
            pauses[event["id"]] = seconds
        answer_index = next(i for i, e in enumerate(events) if e["id"] == name + "_answer")
        assert events[answer_index - 1]["card"] == name
        assert events[answer_index - 1]["kind"] == "speech"
        reveal = events[answer_index + 1]
        assert (reveal["id"], reveal["kind"], reveal["duration"], reveal["audio_id"]) == (
            name + "_reveal", "reveal", 3, "chime_remove")
    pauses.update(p4_statements_read=60, summary_read=10)
    assert {e["id"] for e in events if e["kind"] == "silence"} == set(pauses)
    for event in events:
        if event["kind"] == "silence":
            assert event["duration"] == pauses[event["id"]]
    minute = next(i for i, e in enumerate(events) if e["id"] == "p4_statements_read")
    assert events[minute - 1]["id"] == "instruction_4"
    for index, event in enumerate(events):
        if event["kind"] == "chime" and event["id"] != "back_at_end":
            following = events[index + 1]
            assert following["id"].startswith(("cue_", "example_cue_"))
            assert event["audio_id"] == ("chime_start" if event["id"] == "start_before_example"
                                         else "chime_back")
    matching = content["episode"]["sections"][3]
    assert set(matching["options"]) == set("abcdef")
    chosen = [matching["example"]["answer"], *(task["answer"] for task in matching["tasks"])]
    assert len(set(chosen)) == 4 and len(set(matching["options"]) - set(chosen)) == 2
    return pauses


def check_layouts(build, timeline, content):
    receipt = read_json(build / "composition_receipt.json")
    assert receipt["timeline_sha256"] == sha256_file(build / "timeline.json")
    assert receipt["title_mapping"] == title_intervals(timeline)
    expected_words = []
    for section in content["instructions"]["sections"]:
        part = section["part"]
        words = instruction_intervals(timeline, section["instruction"], f"instruction_{part}")
        for word in words:
            word["selector"] = f'#instruction-{part}-word-{word["index"]}'
        expected_words.extend(words)
    assert receipt["instruction_mapping"] == expected_words
    aligned = read_json(build / "word_alignment.json")
    turns = {turn["id"]: turn for turn in timeline["turns"]}
    assert {turn["id"] for turn in aligned["turns"]} == {"title", *(f"instruction_{p}" for p in range(1, 5))}
    for turn in aligned["turns"]:
        assert turn["start"] == turns[turn["id"]]["start"]
        assert turn["words"] == turns[turn["id"]]["words"]
    assert [ident for scene in receipt["scenes"] for ident in scene["event_ids"]] == [
        event["id"] for event in timeline["events"]]
    for layout in ("landscape", "portrait"):
        document = (build / layout / "index.html").read_text(encoding="utf-8")
        for forbidden in ("VORSCHAU", "Geführte Hörübung", "Lösungen nach jeder Aufgabe",
                          "von Deutsch Kompass", "{{"):
            assert forbidden not in document
        scenes = re.findall(r'<section id="scene-(\d+)"[^>]*data-start="([^"]+)"'
                            r'[^>]*data-duration="([^"]+)"[^>]*>(.*?)</section>', document, re.S)
        assert len(scenes) == len(receipt["scenes"])
        for (index, start, duration, body), event in zip(scenes, receipt["scenes"]):
            assert float(start) == event["start"] and float(duration) == event["duration"]
            visible = re.findall(r'data-answer="([^"]+)"', body)
            expected = ([q["answer"] for q in content["cards"][event["card"]]["questions"]]
                        if event["kind"] == "reveal" else [])
            assert visible == expected, f"Wrong/early keys: {layout}, scene {index}"
            assert ('class="solution"' in body) == (event["kind"] == "reveal")
            assert f'class="phase-label">{html.escape(event["phase"])}</span>' in body
            if event["card"].startswith("instruction_"):
                part = event["part"]
                labels = re.findall(fr'class="instruction-word" id="instruction-{part}-word-\d+">([^<]*)', body)
                assert [html.unescape(label) for label in labels] == [
                    w["word"] for w in turns[f"instruction_{part}"]["words"]]
        for name, digest in read_json(build / layout / "assets_manifest.json").items():
            assert sha256_file(build / layout / "assets" / name) == digest
    return {"visual_scenes": len(receipt["scenes"]), "anleitung_words": len(expected_words),
            "answer_visibility": "Only dedicated reveals and final summary",
            "real_narration_highlight_mapping": "passed"}


def encoded_events(build, timeline, layout):
    import numpy as np
    path = build / f"production_{layout}.mp4"
    metadata = json.loads(subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
        "stream=width,height,nb_frames,r_frame_rate", "-of", "json", str(path)],
        check=True, capture_output=True, text=True).stdout)["streams"][0]
    assert (metadata["width"], metadata["height"]) == (
        (1920, 1080) if layout == "landscape" else (1080, 1920))
    assert metadata["r_frame_rate"] == "24/1"
    assert int(metadata["nb_frames"]) == timeline["total_frames"]
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
                    "-f", "null", "NUL"], check=True)
    decoded = build / f"_validation_decoded_{layout}.wav"
    checks, sums = [], [0.0] * 6
    try:
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(path), "-vn",
                        "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(decoded)], check=True)
        source_size = timeline["total_frames"] * 2000
        decoded_size = audio_info(decoded)
        assert source_size - 2000 <= decoded_size <= source_size + 2048
        with wave.open(str(build / "dialogue.wav"), "rb") as source, wave.open(str(decoded), "rb") as output:
            for event in timeline["events"]:
                start, end = event["start_frame"] * 2000, event["end_frame"] * 2000
                end = min(end, decoded_size)
                expected = np.frombuffer(block(source, start, end), dtype="<i2").astype(np.float64)
                actual = np.frombuffer(block(output, start, end), dtype="<i2").astype(np.float64)
                totals = [len(actual), expected.sum(), actual.sum(), expected @ expected,
                          actual @ actual, expected @ actual]
                sums = [a + float(b) for a, b in zip(sums, totals)]
                if event["kind"] == "silence":
                    interior = actual[2048:-2048]
                    assert len(interior) > 0
                    peak = float(np.max(np.abs(interior)))
                    rms = float(np.sqrt(np.mean(interior ** 2)))
                    assert peak <= 32 and rms <= 1, f"Encoded pause contains sound: {event['id']}"
                    detail = {"silence_peak_pcm16": peak, "silence_rms_pcm16": rms,
                              "codec_boundary_guard_samples": 2048}
                else:
                    correlation = float(np.corrcoef(expected, actual)[0, 1])
                    assert correlation > 0.99, f"Shifted/changed encoded cue: {event['id']}"
                    detail = {"audio_correlation": correlation}
                checks.append({"id": event["id"], "start_frame": event["start_frame"],
                               "end_frame": event["end_frame"], **detail})
        count, x, y, xx, yy, xy = sums
        correlation = (xy - x * y / count) / math.sqrt((xx - x * x / count) * (yy - y * y / count))
        assert correlation > 0.99
    finally:
        decoded.unlink(missing_ok=True)
    return {**metadata, "full_decode": "passed", "audio_correlation": correlation,
            "timeline_events": checks, "sha256": sha256_file(path)}


def validate(build, encoded=False):
    build = build.resolve()
    timeline, content = read_json(build / "timeline.json"), read_json(build / "sample_content.json")
    assert timeline["scope"] == "full" and timeline["practice_mode"] == "guided"
    assert timeline["answer_reveal_seconds"] == 3
    assert timeline["duration"] == timeline["total_frames"] / 24
    pauses = check_structure(timeline, content)
    pin = read_json(build / "input_pin.json")
    assert sha256_file(ROOT / "prepare_full.py") == pin["generator_sha256"]
    assert sha256_file(ROOT / "prepare_sample.py") == pin["sample_helper_sha256"]
    assert sha256_file(ROOT.parent / "pilot_3d" / "prepare_audio.py") == pin["audio_helper_sha256"]
    assert sha256_file(ROOT / "episodes" / "oeif_b1_listening_01.json") == pin["episode_sha256"]
    assert sha256_file(ROOT / "instruction_templates.json") == pin["instructions_sha256"]
    assert content["episode"] == read_json(ROOT / "episodes" / "oeif_b1_listening_01.json")
    assert content["instructions"] == read_json(ROOT / "instruction_templates.json")
    assert read_json(build / "voice_references.json") == pin["voice_references"]
    for files in pin["voice_references"].values():
        for entry in files.values():
            assert sha256_file(Path(entry["path"])) == entry["sha256"]
    for name, digest in pin["source_hashes"].items():
        assert sha256_file(Path(pin["sample_build"]) / name) == digest
    for asset in read_json(ROOT / "assets" / "sfx" / "sources.json")["assets"]:
        assert sha256_file(ROOT / "assets" / "sfx" / asset["file"]) == asset["sha256"]
    assert audio_info(build / "dialogue.wav") == timeline["total_frames"] * 2000
    manifest = read_json(build / "audio_manifest.json")
    speech = [event for event in timeline["events"] if event["kind"] == "speech"]
    assert [event["id"] for event in speech] == [turn["id"] for turn in timeline["turns"]]
    for turn, event in zip(timeline["turns"], speech):
        assert turn["atempo"] == 0.8
        assert turn["text"] == manifest[event["audio_id"]]["text"] == event["text"]
        assert turn["speaker"] == manifest[event["audio_id"]]["speaker"] == event["speaker"]
        assert turn["start"] == event["start"] and turn["end"] == event["end"]
    cursor = 0
    with wave.open(str(build / "dialogue.wav"), "rb") as track:
        for event in timeline["events"]:
            assert event["start_frame"] == cursor and event["end_frame"] > cursor
            assert event["start"] == cursor / 24 and event["end"] == event["end_frame"] / 24
            samples = block(track, cursor * 2000, event["end_frame"] * 2000)
            if event["kind"] == "silence":
                assert not any(samples), f"Non-silent source pause: {event['id']}"
            else:
                audio = Path(event["audio"])
                assert sha256_file(audio) == event["sha256"]
                with wave.open(str(audio), "rb") as clip:
                    exact = block(clip, 0, audio_info(audio))
                assert len(exact) <= len(samples) and samples[:len(exact)] == exact
                assert not any(samples[len(exact):]), f"Non-silent source frame padding: {event['id']}"
                if event["kind"] == "reveal":
                    assert audio.name == "chime_remove.wav"
            cursor = event["end_frame"]
    assert cursor == timeline["total_frames"]
    report = {"source_clock": "passed", "source_pcm_placement": "passed", "exact_silences": pauses,
              "tasks": 20, "examples": 3, "reveal_scenes": 19, "original_sources_preserved": "passed",
              "frames": cursor, "fps": 24, "duration": timeline["duration"],
              "practice_mode": "guided", "answer_reveal_seconds": 3,
              "layouts": check_layouts(build, timeline, content), "human_listening": "not performed"}
    if encoded:
        report["encoded"] = {layout: encoded_events(build, timeline, layout)
                             for layout in ("landscape", "portrait")}
    atomic_json(build / "validation.json", report)
    print(f"Full {'encoded and source' if encoded else 'source'} validation passed: "
          f"20 tasks, {len(timeline['events'])} events, {timeline['duration']:.3f}s.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--encoded", action="store_true")
    args = parser.parse_args()
    validate(args.build, args.encoded)
