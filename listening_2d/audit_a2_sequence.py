"""Independently gate full A2 timelines against the user's revised sequence."""

import argparse
from collections import Counter
from html.parser import HTMLParser
import math
from pathlib import Path

from prepare_a2 import read
from prepare_sample import FPS, atomic_json, sha256_file

REVISION = Path(__file__).resolve().parent / "episodes" / "oeif_a2_listening_01_revision_r2.json"


def opening_headings(markup):
    class Opening(HTMLParser):
        def __init__(self):
            super().__init__()
            self.active, self.capture = False, None
            self.headings, self.words = [], []

        def handle_starttag(self, tag, attrs):
            if tag == "section":
                self.active = dict(attrs).get("id") == "scene-0"
            if self.active and tag in ("h1", "h2", "p"):
                self.capture, self.words = tag, []

        def handle_data(self, data):
            if self.capture:
                self.words.append(data)

        def handle_endtag(self, tag):
            if tag == self.capture:
                self.headings.append((tag, " ".join("".join(self.words).split())))
                self.capture = None
            if tag == "section":
                self.active = False

    parser = Opening()
    parser.feed(markup)
    return parser.headings


def expected_sequence(episode):
    numbers = [[list(range(1, 8))], [[8], [9]], [[10], [11], [12]], [[13], [14], [15]]]
    if episode.get("level") != "A2" or len(episode["sections"]) != 4:
        raise ValueError("This sequence applies to the full four-part A2 test only.")
    expected = []

    def add(ident, kind, part, audio_id=None, seconds=None):
        row = dict(id=ident, kind=kind, part=part)
        if audio_id is not None:
            row["audio_id"] = audio_id
        if seconds is not None:
            row["seconds"] = seconds
        expected.append(row)

    for part, section in enumerate(episode["sections"], 1):
        actual = [[q["number"] for q in g["questions"]] for g in section["groups"]]
        if section["part"] != part or actual != numbers[part - 1]:
            raise ValueError(f"Unexpected A2 question groups in Teil {part}.")
        add(f"instruction_{part}", "speech", part, f"instruction_{part}")
        add(f"part_{part}_read", "silence", part, seconds=30)
        add(f"part_{part}_start", "chime", part)
        for group in section["groups"]:
            ident = group["id"]
            add(ident + "_cue", "speech", part, ident + "_cue")
            for play in range(1, (2 if part < 3 else 1) + 1):
                if play == 2:
                    add(ident + "_replay_gap", "silence", part, seconds=5)
                    if part == 1:
                        add(ident + "_replay_chime", "chime", part)
                for turn in range(1, len(group["recording"]) + 1):
                    add(f"{ident}_play{play}_turn{turn}", "speech", part,
                        f"{ident}_audio_{turn}")
            add(ident + "_answer", "silence", part, seconds=10)
            add(ident + "_reveal", "reveal", part, "chime_remove", seconds=3)
        end = "end_test" if part == 4 else f"end_part_{part}"
        add(end, "speech", part, end)
        if part == 4:
            expected[-1]["text"] = read(REVISION)["endings"]["part_4"]["text"]
        if part < 4:
            add(f"after_part_{part}", "silence", part, seconds=5)
    return expected


def compare_sequence(episode, timeline):
    if timeline.get("scope") != "full" or timeline.get("fps") != FPS:
        raise ValueError("Audit a full 24-fps timeline, not a reduced-practice clip.")
    expected = expected_sequence(episode)
    events, issues = timeline["events"], []

    def issue(code, ident, **details):
        issues.append(dict(code=code, event=ident, **details))

    opening = read(REVISION)["opening"]
    for field in ("display", "text"):
        if episode["opening"].get(field) != opening[field]:
            issue("opening_content", "title", field=field, expected=opening[field],
                  actual=episode["opening"].get(field))
    titles = [e for e in events if e["id"] == "title"]
    if len(titles) != 1 or titles[0].get("text") != opening["text"]:
        issue("opening_speech", "title", expected=opening["text"],
              actual=[e.get("text") for e in titles])

    cursor = 0
    for event in events:
        start, end = event["start_frame"], event["end_frame"]
        if (type(start) is not int or type(end) is not int or start != cursor or end <= start):
            issue("frame_clock", event["id"], start_frame=start, end_frame=end,
                  expected_start_frame=cursor)
        for key, value in (("start", start / FPS), ("end", end / FPS),
                           ("duration", (end - start) / FPS)):
            if not math.isclose(event.get(key, float("nan")), value, abs_tol=1e-8):
                issue("frame_metadata", event["id"], field=key, expected=value,
                      actual=event.get(key))
        cursor = end
    if cursor != timeline["total_frames"] or not math.isclose(
            timeline["duration"], cursor / FPS, abs_tol=1e-8):
        issue("total_clock", "timeline", actual_frames=timeline["total_frames"],
              expected_frames=cursor)

    starts = [i for i, e in enumerate(events) if e["id"] == "instruction_1"]
    ends = [i for i, e in enumerate(events) if e["id"] in ("end_test", "end_part_4")]
    first, last = (starts[0] if starts else 0), (ends[-1] if ends else len(events) - 1)
    # The opening, final solution summary and CTA are outside the listening sequence.
    core = events[first:last + 1]
    counts = Counter(e["id"] for e in core)
    positions = {e["id"]: i for i, e in enumerate(core)}
    by_id = {e["id"]: e for e in core}
    expected_ids = {e["id"] for e in expected}
    for ident, count in counts.items():
        if count > 1:
            issue("duplicate_event", ident, count=count)
        if ident not in expected_ids:
            issue("unexpected_event", ident)
    previous = None
    for target in expected:
        ident = target["id"]
        actual = by_id.get(ident)
        if actual is None:
            issue("missing_event", ident, expected=target)
            continue
        if previous is not None and positions[previous] >= positions[ident]:
            issue("event_order", ident, must_follow=previous)
        previous = ident
        for field in ("kind", "part", "audio_id", "text"):
            if field in target and actual.get(field) != target[field]:
                issue("event_field", ident, field=field,
                      expected=target[field], actual=actual.get(field))
        if target["kind"] == "silence" and actual.get("audio_id"):
            issue("non_silent_pause", ident, audio_id=actual["audio_id"])
        if target["kind"] == "chime" and not actual.get("audio_id"):
            issue("missing_chime_audio", ident)
        if "seconds" in target:
            seconds = (actual["end_frame"] - actual["start_frame"]) / FPS
            if seconds != target["seconds"]:
                issue("event_duration", ident, expected_seconds=target["seconds"],
                      actual_seconds=seconds)
    for section in episode["sections"][:2]:
        for group in section["groups"]:
            for turn in range(1, len(group["recording"]) + 1):
                one = by_id.get(f"{group['id']}_play1_turn{turn}")
                two = by_id.get(f"{group['id']}_play2_turn{turn}")
                if one and two and (not one.get("sha256") or
                                    any(one.get(k) != two.get(k)
                                        for k in ("sha256", "audio_samples"))):
                    issue("changed_repeat_audio", two["id"])
    return {
        "profile": "oeif_a2_user_sequence_2026_11_11_guided",
        "reference": read(REVISION)["reference"],
        "guided_reveals": "User explicitly retained three-second reveals after complete answer pauses.",
        "opening": opening,
        "matches_requested_sequence": not issues,
        "issues": issues,
        "expected_core": expected,
        "limitations": "Sequence and opening text checks; instruction wording, pronunciation, PCM, browser and encoded checks remain separate.",
    }


def audit(build, output):
    build, output = build.resolve(), output.resolve()
    if output.exists():
        raise ValueError("Preserve earlier audits; choose a fresh report path.")
    frozen = (build / "delivery_manifest.json").is_file()
    if frozen and output.is_relative_to(build):
        raise ValueError("Write this audit outside the frozen delivery.")
    report = compare_sequence(read(build / "sample_content.json")["episode"],
                              read(build / "timeline.json"))
    reference = (REVISION.parent / report["reference"]["path"]).resolve()
    if sha256_file(reference) != report["reference"]["sha256"]:
        raise ValueError("Reference transcript changed; reconcile and pin the new version.")
    evidence = {"build": str(build), "timeline_sha256": sha256_file(build / "timeline.json"),
                "revision_request_sha256": sha256_file(REVISION),
                "audit_code_sha256": sha256_file(Path(__file__)),
                "transcript": str(reference), "transcript_sha256": sha256_file(reference),
                "encoded_binding_checked": False}
    layouts = (read(build / "composition_receipt.json")["layouts"]
               if (build / "composition_receipt.json").is_file() else [])
    for layout in layouts:
        headings = opening_headings((build / layout / "index.html").read_text(encoding="utf-8"))
        if headings != [("h1", report["opening"]["display"])]:
            report["issues"].append(dict(code="opening_visual", event="title", layout=layout,
                                         actual=headings,
                                         expected=[("h1", report["opening"]["display"])]))
    evidence["opening_layouts_checked"] = layouts
    if frozen:
        manifest = read(build / "delivery_manifest.json")
        if read(build / "delivery_audit.json")["manifest_sha256"] != sha256_file(
                build / "delivery_manifest.json"):
            raise ValueError("Frozen manifest no longer matches its delivery audit.")
        for name in ("timeline.json", "sample_content.json", "validation.json"):
            if sha256_file(build / name) != manifest["files"][name]:
                raise ValueError(f"Changed frozen input: {name}")
        for path, digest in manifest["code_inputs"].items():
            if sha256_file(Path(path)) != digest:
                raise ValueError(f"Changed frozen code: {path}")
        validation = read(build / "validation.json")
        for layout, details in manifest["outputs"].items():
            export = build / f"production_{layout}.mp4"
            if not (sha256_file(export) == details["sha256"] ==
                    manifest["files"][export.name] == validation["encoded"][layout]["sha256"]):
                raise ValueError(f"Export no longer matches encoded validation: {layout}")
        evidence.update(encoded_binding_checked=True, layouts=list(manifest["outputs"]),
                        delivery_manifest_sha256=sha256_file(build / "delivery_manifest.json"),
                        encoded_validation_sha256=sha256_file(build / "validation.json"))
    report["evidence"] = evidence
    report["matches_requested_sequence"] = not report["issues"]
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(output, report)
    print(f"A2 sequence {'PASS' if report['matches_requested_sequence'] else 'MISMATCH'}: "
          f"{len(report['issues'])} findings; {output}", flush=True)
    for item in report["issues"]:
        print(f"  {item['code']}: {item['event']}", flush=True)
    return report["matches_requested_sequence"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    raise SystemExit(0 if audit(args.build, args.output) else 1)
