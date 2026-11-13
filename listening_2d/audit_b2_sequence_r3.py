"""Independently check the user-authored B2 event and silent-pause contract."""

import argparse
from pathlib import Path
import re

from prepare_b2 import read
from prepare_sample import atomic_json, sha256_file


def compare_sequence(episode, timeline):
    expected, issues = [], []

    def speech(ident, text, part):
        expected.append(dict(id=ident, kind="speech", audio_id=ident, text=text, part=part))

    def fixed(ident, kind, part, seconds=None, audio_id=None):
        expected.append(dict(id=ident, kind=kind, part=part, seconds=seconds, audio_id=audio_id))

    sections = episode["sections"]
    if [q["number"] for s in sections for g in s["groups"] for q in g["questions"]] != list(range(41, 61)):
        issues.append("Expected original numbering 41-60.")
    if [sum(len(g["questions"]) for g in s["groups"]) for s in sections] != [5, 10, 5]:
        issues.append("Expected 5/10/5 true/false tasks.")
    if [len(s["groups"]) for s in sections] != [1, 1, 5] or any(s["plays"] != 1 for s in sections):
        issues.append("Expected one bulletin, one interview and five once-only short texts.")
    speech("title", "Ö I F B zwei Hören.", 0)
    for section in sections:
        part = section["part"]
        speech(f"instruction_{part}", section["instruction"], part)
        if part < 3:
            fixed(f"part_{part}_read", "silence", part, 30 if part == 1 else 60)
            fixed(f"part_{part}_start", "chime", part, audio_id="chime_start")
        for group in section["groups"]:
            ident = group["id"]
            if part == 3:
                speech(ident + "_cue", group["number_cue"], part)
            for turn in group["recording"]:
                speech(turn["id"], turn["text"], part)
            if part == 2:
                speech("checking_instruction", section["checking_instruction"], part)
            fixed(ident + "_answer", "silence", part, 30 if part == 2 else 15)
            fixed(ident + "_reveal", "reveal", part, 3, "chime_remove")
            if part == 2:
                fixed(ident + "_reveal_page2", "reveal", part, 3, "chime_remove")
            fixed(ident + "_transition", "chime", part, audio_id="chime_back")
        speech("end_test" if part == 3 else f"end_part_{part}",
               "Ende des Subtests Hören." if part == 3 else f"Ende von Teil {'eins' if part == 1 else 'zwei'}.", part)
    fixed("summary_read", "silence", 0, 15)
    speech("cta", episode["promotion"]["cta"], 0)
    actual = timeline["events"]
    if len(actual) != len(expected):
        issues.append(f"Expected {len(expected)} events, got {len(actual)}.")
    cursor = 0
    for index, (event, wanted) in enumerate(zip(actual, expected)):
        for key in ("id", "kind", "part", "audio_id", "text"):
            if key in wanted and wanted[key] is not None and event.get(key) != wanted[key]:
                issues.append(f"Event {index} {key}: expected {wanted[key]!r}, got {event.get(key)!r}.")
        frames = event["end_frame"] - event["start_frame"]
        if (event["start_frame"] != cursor or event["start"] != cursor / 24
                or event["end"] != event["end_frame"] / 24 or event["duration"] != frames / 24):
            issues.append(f"Event {index} has an inconsistent or discontinuous frame clock.")
        if wanted.get("seconds") is not None and frames != wanted["seconds"] * 24:
            issues.append(f"{wanted['id']}: expected {wanted['seconds']} seconds outside speech/chimes.")
        if wanted["kind"] == "silence" and any(event.get(k) for k in ("audio", "audio_id", "audio_samples")):
            issues.append(f"{wanted['id']}: prescribed silence has audio.")
        if wanted["kind"] == "reveal" and wanted["part"] == 2:
            group = 2 if wanted["id"].endswith("_page2") else 1
            if event.get("reveal_group") != group:
                issues.append(f"{wanted['id']}: wrong or missing inline reveal group.")
        cursor = event["end_frame"]
    if cursor != timeline["total_frames"] or timeline["duration"] != timeline["total_frames"] / 24:
        issues.append("Total duration does not match the frame clock.")
    return dict(matches_requested_sequence=not issues, issues=issues,
                expected_events=len(expected), actual_events=len(actual),
                timing_provenance="User contract, not independently measured official audio timing.")


def audit(build, output):
    content, timeline = read(build / "sample_content.json"), read(build / "timeline.json")
    report = compare_sequence(content["episode"], timeline)
    for layout in ("landscape", "portrait"):
        path = build / layout / "index.html"
        if path.exists():
            document = path.read_text(encoding="utf-8")
            title = re.search(r'<section id="scene-0".*?</section>', document, re.S)
            if not title or "<h1>ÖIF B2 Hören</h1>" not in title.group():
                report["issues"].append(f"{layout}: title-only body is missing.")
    report["matches_requested_sequence"] = not report["issues"]
    report["timeline_sha256"] = sha256_file(build / "timeline.json")
    report["encoded_outputs"] = {layout: sha256_file(build / f"production_{layout}.mp4")
                                 for layout in ("landscape", "portrait")
                                 if (build / f"production_{layout}.mp4").exists()}
    atomic_json(output, report)
    if report["issues"]:
        raise ValueError("\n".join(report["issues"]))
    print(f"B2 independent sequence gate passed: {report['actual_events']} events.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    audit(args.build.resolve(), args.output.resolve())
