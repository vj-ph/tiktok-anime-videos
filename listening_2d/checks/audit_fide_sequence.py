"""Independently verify the fide exercise order, replay policy and practice pauses."""

import argparse
from pathlib import Path

from listening_2d.preparation.prepare_fide import approved_episode, atomic_json, read, sha256_file


def compare_sequence(timeline):
    expected = []

    def speech(ident, card=None, audio_id=None):
        expected.append((ident, "speech", card or ident, audio_id or ident, None))

    def silence(ident, card, seconds):
        expected.append((ident, "silence", card, None, seconds))

    speech("title")
    silence("opening_padding", "title", .5)
    speech("setup")
    speech("a2_instruction")
    for level, situation_ids, first in (
            ("A2", ("a2_sbb", "a2_tram"), 7),
            ("B1", ("b1_verwaltung", "b1_nachbarn"), 13)):
        if level == "B1":
            speech("transition")
            speech("b1_instruction")
        for offset, situation in enumerate(situation_ids):
            speech("context_" + situation)
            for number in range(first + offset * 3, first + offset * 3 + 3):
                card = f"item_{number}"
                speech(f"question_{number}", card)
                if level == "A2":
                    silence(f"inspect_{number}", card, 5)
                speech(f"recording_{number}", card)
                speech(f"repeat_question_{number}", card, f"question_{number}")
                silence(f"answer_{number}", card, 10 if level == "A2" else 20)
    speech("end_test")
    speech("solutions_instruction")
    for number in range(7, 19):
        speech(f"solution_{number}")
        silence(f"solution_padding_{number}", f"solution_{number}", 2)
    speech("cta")
    silence("outro", "cta", 3)
    issues, events = [], timeline["events"]
    if len(events) != len(expected):
        issues.append(f"Expected {len(expected)} events, got {len(events)}.")
    cursor, by_id = 0, {}
    for index, (event, wanted) in enumerate(zip(events, expected)):
        ident, kind, card, audio, seconds = wanted
        if (event["id"], event["kind"], event["card"], event.get("audio_id")) != wanted[:4]:
            issues.append(f"Event {index} differs from independently specified {ident}/{kind}/{card}/{audio}.")
        frames = event["end_frame"] - event["start_frame"]
        if (event["start_frame"] != cursor or frames <= 0
                or event["start"] != cursor / 24 or event["end"] != event["end_frame"] / 24
                or event["duration"] != frames / 24):
            issues.append(f"Invalid frame clock: {event['id']}.")
        if seconds is not None and (event["kind"] != "silence" or frames != seconds * 24):
            issues.append(f"Full {seconds}s silent interval missing: {ident}.")
        if event["kind"] == "speech":
            if not 0 <= frames * 2000 - event["audio_samples"] < 2000:
                issues.append(f"Truncated or overpadded speech: {event['id']}.")
        if event["id"].startswith(("question_", "repeat_question_", "recording_")) and event.get("visible"):
            issues.append(f"Exam question/transcript marked for display: {event['id']}.")
        by_id[event["id"]] = event
        cursor = event["end_frame"]
    for number in range(7, 19):
        before, after = by_id.get(f"question_{number}"), by_id.get(f"repeat_question_{number}")
        if before and after and any(before[k] != after[k] for k in ("audio", "sha256", "audio_samples", "text")):
            issues.append(f"Repeated question {number} is not the identical complete WAV.")
    if cursor != timeline["total_frames"] or timeline["duration"] != cursor / 24:
        issues.append("The root frame clock differs from the event clock.")
    return {"ok": not issues, "issues": issues, "expected_events": len(expected),
            "recording_plays": 1, "question_repetition": "Identical complete WAV",
            "answers": "Only after the final B1 response interval",
            "pause_provenance": "5/10/20 seconds are approved video-practice timings, not official fixed silences."}


def audit(build, output):
    approved_episode()
    result = compare_sequence(read(build / "timeline.json"))
    result["timeline_sha256"] = sha256_file(build / "timeline.json")
    atomic_json(output, result)
    if not result["ok"]:
        raise ValueError("\n".join(result["issues"]))
    print("Fide independent sequence gate passed.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    audit(args.build.resolve(), args.output.resolve())
