"""Verify source/sample clocks and optionally the encoded HyperFrames previews."""

import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import wave

ROOT = Path(__file__).resolve().parent
EXPECTED_SILENCES = {
    "example_read": 10, "example_answer": 10,
    "task1_read": 12, "task1_answer": 12,
}


def pcm(path):
    with wave.open(str(path), "rb") as handle:
        if handle.getframerate() != 48000 or handle.getnchannels() != 1:
            raise ValueError("Expected 48 kHz mono PCM.")
        return handle.readframes(handle.getnframes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_guided_layouts(build, timeline):
    content = json.loads((build / "sample_content.json").read_text(encoding="utf-8"))
    section = content["episode"]["sections"][0]
    questions = {"example": section["example"], "task1": section["tasks"][0]}
    receipt = json.loads((build / "composition_receipt.json").read_text(encoding="utf-8"))
    instruction = next(turn for turn in timeline["turns"] if turn["id"] == "instruction")
    alignment = json.loads((build / "word_alignment.json").read_text(encoding="utf-8"))
    turns = {turn["id"]: turn for turn in timeline["turns"]}
    for aligned in alignment["turns"]:
        assert aligned["start"] == turns[aligned["id"]]["start"]
        assert aligned["words"] == turns[aligned["id"]]["words"]
    mapping = receipt["instruction_mapping"]
    assert len(mapping) == len(instruction["words"])
    for entry, word in zip(mapping, instruction["words"]):
        assert entry["label"] == word["word"]
        assert entry["start"] == instruction["start"] + word["start"]
        assert entry["end"] == instruction["start"] + word["end"]
    for layout in ("landscape", "portrait"):
        document = (build / layout / "index.html").read_text(encoding="utf-8")
        scenes = re.findall(
            r'<section id="scene-(\d+)"[^>]*data-start="([^"]+)"'
            r'[^>]*data-duration="([^"]+)"[^>]*>(.*?)</section>', document, re.S)
        assert len(scenes) == len(timeline["events"])
        for (index, start, duration, body), event in zip(scenes, timeline["events"]):
            assert int(index) == timeline["events"].index(event)
            assert float(start) == event["start"] and float(duration) == event["duration"]
            correct = re.findall(r'class="option correct"><span class="letter">([^<]+)', body)
            expected = [questions[event["card"]]["answer"]] if event["kind"] == "reveal" else []
            assert correct == expected, f"Early or incorrect solution in {layout}: {event['id']}"
            assert ("Richtige Antwort:" in body) == (event["kind"] == "reveal")
            if event["id"] == "instruction":
                labels = re.findall(r'class="instruction-word" id="instruction-word-\d+">([^<]*)', body)
                assert [html.unescape(label) for label in labels] == [w["label"] for w in mapping]
        assert "Geführte Hörübung" not in document
        assert "Lösungen nach jeder Aufgabe" not in document
        phase_labels = re.findall(r'class="phase-label">([^<]*)', document)
        assert [html.unescape(label) for label in phase_labels] == [
            event["phase"] for event in timeline["events"]]
    return {"answer_visibility": "only separate reveal scenes",
            "anleitung_words": len(mapping), "measured_highlight_mapping": "passed"}


def validate(build, encoded=False):
    build = build.resolve()
    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    dialogue = pcm(build / "dialogue.wav")
    assert len(dialogue) // 2 == timeline["total_frames"] * 2000
    silence_ids = set()
    cursor = 0
    for event in timeline["events"]:
        assert event["start_frame"] == cursor
        assert event["end_frame"] > cursor
        start, end = cursor * 4000, event["end_frame"] * 4000
        block = dialogue[start:end]
        if event["kind"] == "reveal":
            assert event["duration"] == timeline["answer_reveal_seconds"]
            if event.get("audio"):
                assert event["sfx_id"] == "chime_remove"
                assert Path(event["audio"]).name == "chime_remove.wav"
        if event["kind"] == "silence":
            silence_ids.add(event["id"])
            assert event["duration"] == EXPECTED_SILENCES[event["id"]]
        if event["kind"] == "silence" or (event["kind"] == "reveal" and not event.get("audio")):
            assert not any(block), f"Sound leaked into {event['id']}"
        else:
            source = Path(event["audio"])
            assert digest(source) == event["sha256"]
            exact = pcm(source)
            assert block[:len(exact)] == exact
            assert not any(block[len(exact):]), "Non-silent frame padding"
        cursor = event["end_frame"]
    assert silence_ids == set(EXPECTED_SILENCES)
    assert cursor == timeline["total_frames"]
    ids = [event["id"] for event in timeline["events"]]
    offset = 2 if timeline.get("practice_mode") == "guided" else 1
    if offset == 2:
        assert ids[ids.index("example_answer") + 1] == "example_reveal"
        assert ids[ids.index("task1_answer") + 1] == "task1_reveal"
    assert ids.index("example_answer") + offset == ids.index("chime_back")
    assert ids[ids.index("chime_back") + 1] == "number1"
    assert ids[ids.index("task1_answer") + offset] == "chime_back"
    pin = json.loads((build / "input_pin.json").read_text(encoding="utf-8"))
    if "source_build" in pin:
        source = Path(pin["source_build"])
        for name, expected_hash in pin["source_hashes"].items():
            assert digest(source / name) == expected_hash, f"Previous preview changed: {name}"
    manifest = json.loads((ROOT / "assets" / "sfx" / "sources.json").read_text())
    for asset in manifest["assets"]:
        assert digest(ROOT / "assets" / "sfx" / asset["file"]) == asset["sha256"]
    report = {
        "source_clock": "passed", "exact_silences": EXPECTED_SILENCES,
        "speech_and_chime_pcm_placement": "passed", "original_sfx_hashes": "passed",
        "frames": timeline["total_frames"], "fps": 24,
        "duration": timeline["duration"], "human_listening": "not performed",
        "practice_mode": timeline.get("practice_mode", "exam"),
        "answer_reveal_seconds": timeline.get("answer_reveal_seconds", 0),
    }
    if timeline.get("practice_mode") == "guided":
        report["guided_layouts"] = validate_guided_layouts(build, timeline)
    if encoded:
        import numpy as np
        report["encoded"] = {}
        expected = np.frombuffer(dialogue, dtype="<i2").astype(float)
        for layout, dimensions in (("landscape", (1920, 1080)), ("portrait", (1080, 1920))):
            path = build / f"preview_{layout}.mp4"
            metadata = json.loads(subprocess.run([
                "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                "stream=width,height,nb_frames,r_frame_rate", "-of", "json", str(path)
            ], check=True, capture_output=True, text=True).stdout)["streams"][0]
            assert (metadata["width"], metadata["height"]) == dimensions
            assert metadata["r_frame_rate"] == "24/1"
            assert int(metadata["nb_frames"]) == timeline["total_frames"]
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
                            "-f", "null", "NUL"], check=True)
            decoded = subprocess.run([
                "ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
                "-vn", "-ar", "48000", "-ac", "1", "-f", "s16le", "-"
            ], check=True, capture_output=True).stdout
            actual = np.frombuffer(decoded, dtype="<i2").astype(float)
            assert len(actual) >= len(expected) - 2000
            size = min(len(actual), len(expected))
            correlation = float(np.corrcoef(expected[:size], actual[:size])[0, 1])
            assert correlation > 0.99, f"Encoded audio shifted or changed: {correlation}"
            event_checks = []
            for event in timeline["events"]:
                start = event["start_frame"] * 2000
                end = event["end_frame"] * 2000
                if event["kind"] == "silence" or not event.get("audio"):
                    # AAC can ring at a boundary; examine the silence beyond its transform window.
                    interior = actual[start + 2048:end - 2048]
                    assert len(interior) > 0
                    peak = float(np.max(np.abs(interior)))
                    rms = float(np.sqrt(np.mean(interior ** 2)))
                    assert peak <= 32 and rms <= 1, f"Encoded sound leaked into {event['id']}"
                    detail = {"silence_peak_pcm16": peak, "silence_rms_pcm16": rms,
                              "codec_boundary_guard_samples": 2048}
                else:
                    end = min(end, size)
                    event_correlation = float(np.corrcoef(
                        expected[start:end], actual[start:end])[0, 1])
                    assert event_correlation > 0.99, f"Encoded event shifted: {event['id']}"
                    detail = {"audio_correlation": event_correlation}
                event_checks.append({"id": event["id"], "start_frame": event["start_frame"],
                                     "end_frame": event["end_frame"], **detail})
            report["encoded"][layout] = {
                **metadata, "full_decode": "passed", "audio_correlation": correlation,
                "timeline_events": event_checks, "sha256": digest(path),
            }
    (build / "validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--encoded", action="store_true")
    args = parser.parse_args()
    validate(args.build, args.encoded)
