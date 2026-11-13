"""Check, review, render and freeze the three authorized B2 portrait excerpts."""

import argparse
import html
import math
from pathlib import Path
import re
import subprocess
import sys
import wave

from compose_b2_reduced import document_for
from deliver_b2_r3 import run
from prepare_b2 import read, schedule
from prepare_b2_reduced import (
    SOURCE, READING_TEXT, SELECTIONS, TOTALS, planned_events, title_text,
)
from prepare_sample import ROOT, atomic_json, mix_events, sha256_file
from review_full_frames import sheets
from validate_b2_r3 import verify_files
from validate_full import audio_info, encoded_events


def independent_sequence(part, timeline):
    expected = {
        1: ["reduced_intro", "reading_instruction", "part_1_read", "part_1_start",
            "news_theatre", "news_corrections", "b2_p1_news_answer",
            "b2_p1_news_reveal", "b2_p1_news_transition", "cta"],
        2: ["reduced_intro", "reading_instruction", "part_2_read", "part_2_start",
            "interview_q49", "interview_49", "b2_p2_learning_answer",
            "b2_p2_learning_reveal", "b2_p2_learning_transition", "cta"],
        3: ["reduced_intro", "b2_p3_parcel_cue", "short_56", "b2_p3_parcel_answer",
            "b2_p3_parcel_reveal", "b2_p3_parcel_transition", "b2_p3_stage_cue",
            "short_57", "b2_p3_stage_answer", "b2_p3_stage_reveal",
            "b2_p3_stage_transition", "cta"],
    }[part]
    assert [e["id"] for e in timeline["events"]] == expected
    expected_pauses = {
        1: {"part_1_read": 15, "b2_p1_news_answer": 10},
        2: {"part_2_read": 15, "b2_p2_learning_answer": 10},
        3: {"b2_p3_parcel_answer": 15, "b2_p3_stage_answer": 15},
    }[part]
    pauses = {e["id"]: e["duration"] for e in timeline["events"] if e["kind"] == "silence"}
    assert pauses == expected_pauses
    for event in timeline["events"]:
        if event["kind"] == "reveal":
            assert event["duration"] == 3 and event["audio_id"] == "chime_remove"
        if event["id"] == "reading_instruction":
            assert event["text"] == READING_TEXT
    if part < 3:
        cue, reading = timeline["events"][1:3]
        assert cue["kind"] == "speech" and cue["end_frame"] == reading["start_frame"]
        assert reading["end_frame"] - reading["start_frame"] == 360
    return pauses


def verify_inputs(build):
    pins = read(build / "input_pin.json")
    assert pins["source"] == str(SOURCE)
    assert sha256_file(SOURCE / "delivery_manifest.json") == pins["source_manifest_sha256"]
    verify_files(pins["files"])
    preserved = read(build / "source_preservation.json")
    for layer in (preserved, preserved["previous_preservation"]):
        verify_files(layer["files"])
        verify_files(layer["code_inputs"])
    binding = read(SOURCE / "audio_review_binding.json")
    verify_files(binding["files"])
    verify_files(binding["speech_audio_files"])


def validate_clip(clip, encoded=False):
    part = int(clip.name.rsplit("_", 1)[1])
    timeline, measured = read(clip / "timeline.json"), read(clip / "audio_manifest.json")
    source_timeline, source_content = read(SOURCE / "timeline.json"), read(SOURCE / "sample_content.json")
    title = read(clip.parent / "new_audio_manifest.json")[f"title_{part}"]
    assert title["text"] == title_text(part)
    for item in read(clip.parent / "new_audio_manifest.json").values():
        assert item["atempo"] == 0.8 and item["tempo_processing"]["filter"] == "atempo=0.8"
        verify_files({item["audio"]: item["sha256"]})
        verify_files({stage["path"]: stage["sha256"] for stage in item["audio_chain"].values()})
    expected = schedule(planned_events(part, source_timeline, title["frames"]), measured)
    assert timeline["events"] == expected["events"] and timeline["turns"] == expected["turns"]
    assert timeline["scope"] == "reduced" and timeline["part"] == part
    assert timeline["selected_numbers"] == SELECTIONS[part]
    assert timeline["total_questions"] == TOTALS[part] and timeline["adapted_pauses"]
    assert timeline["total_frames"] == expected["total_frames"] < 4320
    assert timeline["duration"] == timeline["total_frames"] / 24 < 180
    padding = timeline["events"][0]["end_frame"] * 2000 - title["frames"]
    assert 24000 <= padding < 26000
    pauses = independent_sequence(part, timeline)
    content = read(clip / "sample_content.json")
    assert content["episode"] == source_content["episode"]
    assert {q["number"] for c in content["cards"].values() for q in c["questions"]} == set(SELECTIONS[part])
    for key, card in content["cards"].items():
        original = source_content["cards"][key]
        assert card == {**original, "questions": [
            q for q in original["questions"] if q["number"] in SELECTIONS[part]]}
    old_events = {e["id"]: e for e in source_timeline["events"]}
    assert audio_info(clip / "dialogue.wav") == timeline["total_frames"] * 2000
    with wave.open(str(clip / "dialogue.wav"), "rb") as track:
        actual = track.readframes(track.getnframes())
    assert actual == mix_events(timeline["events"])
    for event in timeline["events"]:
        if event.get("audio"):
            verify_files({event["audio"]: event["sha256"]})
            assert audio_info(Path(event["audio"])) == event["audio_samples"]
            if event["id"] not in ("reduced_intro", "reading_instruction"):
                old = old_events[event["id"]]
                assert event["audio"] == old["audio"] and event["sha256"] == old["sha256"]
                assert event["duration"] == old["duration"]
    document, scenes = document_for(clip)
    assert document == (clip / "portrait" / "index.html").read_text(encoding="utf-8")
    receipt = read(clip / "composition_receipt.json")
    assert receipt["timeline_sha256"] == sha256_file(clip / "timeline.json")
    assert receipt["generator_sha256"] == sha256_file(ROOT / "compose_b2_reduced.py")
    assert receipt["template_sha256"] == sha256_file(ROOT / "composition" / "index.html")
    assert receipt["scenes"] == scenes
    bodies = re.findall(r'<section id="scene-\d+"[^>]*>(.*?)</section>', document, re.S)
    assert len(bodies) == len(scenes)
    for scene, body in zip(scenes, bodies):
        questions = content["cards"].get(scene["card"], {}).get("questions", [])
        assert re.findall(r'data-question="(\d+)"', body) == [str(q["number"]) for q in questions]
        statements = re.findall(r'class="statement-text">([^<]+)</span>', body)
        assert [html.unescape(s) for s in statements] == [q["question"] for q in questions]
        keys = [f'{q["number"]}:{"richtig" if q["answer"] else "falsch"}'
                for q in questions] if scene["kind"] == "reveal" else []
        assert re.findall(r'data-answer="([^"]+)"', body) == keys
        assert "answer-board" not in body
    assert f"<h1>ÖIF B2 Hören<br>Teil {part}</h1>" in bodies[0]
    assert "Verkürzte Übung · Ausgewählte Aufgaben" in document
    assert content["episode"]["promotion"]["social_label"] in html.unescape(document)
    for name, digest in read(clip / "portrait" / "assets_manifest.json").items():
        verify_files({str(clip / "portrait" / "assets" / name): digest})
    result = {
        "part": part, "frames": timeline["total_frames"], "duration": timeline["duration"],
        "selected_numbers": SELECTIONS[part], "silences": pauses,
        "independent_sequence": "passed", "complete_selected_source_audio": "passed",
        "exact_pcm_and_silences": "passed", "inline_answer_visibility": "passed",
        "opening_padding_samples": padding, "human_listening": "not performed",
    }
    if encoded:
        result["encoded"] = encoded_events(clip, timeline, "portrait")
        metadata = read_probe(clip / "production_portrait.mp4")
        assert float(metadata["format"]["duration"]) < 180
        for stream in metadata["streams"]:
            if "duration" in stream:
                assert float(stream["duration"]) < 180
        result["container_and_stream_durations"] = metadata
    atomic_json(clip / ("validation.json" if encoded else "source_validation.json"), result)
    print(f"B2 reduced Teil {part} {'encoded' if encoded else 'source'} passed: "
          f"{timeline['duration']:.3f}s.", flush=True)
    return result


def read_probe(path):
    import json
    return json.loads(subprocess.run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,duration,width,height,r_frame_rate,nb_frames",
        "-of", "json", str(path)], check=True, capture_output=True, text=True).stdout)


def speech_review(build):
    from process_b2 import review
    atomic_json(build / "audio_manifest.json", read(build / "new_audio_manifest.json"))
    review(build, "small")
    review(build, "medium")


def check(build):
    verify_inputs(build)
    receipts = {}
    for part in SELECTIONS:
        clip = build / f"teil_{part}"
        validate_clip(clip)
        run(["node", str(ROOT / "check_b2_layout_r3.cjs"), str(clip / "portrait" / "index.html"),
             str(clip / "geometry_portrait.json"), "portrait"], clip / "geometry_portrait.log")
        run([sys.executable, "-X", "utf8", str(ROOT / "hyperframes_local.py"), "check",
             str(clip / "portrait"), "--json", "--at-transitions", "--snapshots",
             "--no-browser-gpu", "--timeout", "4m"], clip / "check_portrait.log")
        report_path = max((clip / "portrait" / ".hyperframes" / "artifacts" / "checks").glob("*.json"),
                          key=lambda p: p.stat().st_mtime_ns)
        report = read(report_path)
        assert report["ok"] and not report.get("browserSkipped", False)
        receipts[str(part)] = {
            "report": str(report_path), "sha256": sha256_file(report_path),
            "geometry_sha256": sha256_file(clip / "geometry_portrait.json"),
            "html_sha256": sha256_file(clip / "portrait" / "index.html"),
            "source_validation_sha256": sha256_file(clip / "source_validation.json"),
        }
        print(f"B2 reduced Teil {part} browser/geometry passed.", flush=True)
    atomic_json(build / "pre_render_checks.json", receipts)


def frame_plan(timeline):
    selected = {}
    for event in timeline["events"]:
        for frame, label in (
            (event["start_frame"] - 1, "preceding"),
            (event["start_frame"], "first"),
            ((event["start_frame"] + event["end_frame"]) // 2, "middle"),
            (event["end_frame"] - 1, "last"),
        ):
            frame = max(0, min(timeline["total_frames"] - 1, frame))
            selected.setdefault(frame, []).append(event["id"] + " " + label)
    return [dict(frame=f, seconds=f / 24, snapshot_seconds=math.ceil(f / 24 * 1000 - 1e-7) / 1000,
                 labels=labels) for f, labels in sorted(selected.items())]


def review_frames(build, encoded=False):
    import numpy as np
    from PIL import Image
    for part in SELECTIONS:
        clip = build / f"teil_{part}"
        plan = frame_plan(read(clip / "timeline.json"))
        atomic_json(clip / "review_frame_plan.json", plan)
        destination = clip / "contact_portrait"
        destination.mkdir(exist_ok=True)
        stamps = [f'{p["snapshot_seconds"]:.3f}'.rstrip("0").rstrip(".") for p in plan]
        run([sys.executable, "-X", "utf8", str(ROOT / "hyperframes_local.py"), "snapshot",
             str(clip / "portrait"), "--at", ",".join(stamps), "--no-end", "--keep",
             "--output", str(destination), "--no-browser-gpu", "--timeout", "120000", "--json"],
            clip / ("snapshot_encoded.log" if encoded else "snapshot_native.log"))
        images = [destination / f"at-{stamp}s.png" for stamp in stamps]
        receipt = {"frames": plan, "browser_contact_sheets": sheets(images, plan, destination, "portrait"),
                   "browser_frames": {p.name: sha256_file(p) for p in images}}
        box = (80, 1420, 1000, 1696)
        with Image.open(images[0]) as image:
            baseline = np.asarray(image.convert("RGB").crop(box), dtype=float)
        for path in images:
            with Image.open(path) as image:
                assert np.array_equal(baseline, np.asarray(image.convert("RGB").crop(box), dtype=float))
        receipt["persistent_promotion"] = dict(box=box, pixel_identical=True, frames=len(images))
        if encoded:
            output = clip / "encoded_portrait"
            output.mkdir(exist_ok=True)
            selector = "+".join(f'eq(n\\,{item["frame"]})' for item in plan)
            run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(clip / "production_portrait.mp4"),
                 "-vf", "select=" + selector, "-fps_mode", "vfr", "-frames:v", str(len(plan)),
                 str(output / "frame-%03d.png")], clip / "extract_review.log")
            exported = [output / f"frame-{i + 1:03d}.png" for i in range(len(plan))]
            comparisons = []
            for item, expected, actual in zip(plan, images, exported):
                with Image.open(expected) as reference, Image.open(actual) as candidate:
                    assert reference.size == candidate.size == (1080, 1920)
                    error = float(np.mean(np.abs(np.asarray(reference.convert("RGB"), dtype=float) -
                                                 np.asarray(candidate.convert("RGB"), dtype=float))))
                    promotion_error = float(np.mean(np.abs(
                        np.asarray(candidate.convert("RGB").crop(box), dtype=float) - baseline)))
                assert error < 4 and promotion_error < 4, (part, item["frame"], error, promotion_error)
                comparisons.append({**item, "mean_absolute_rgb_error": error,
                                    "promotion_mean_rgb_error": promotion_error,
                                    "export_sha256": sha256_file(actual)})
            receipt.update(export_comparisons=comparisons,
                           encoded_contact_sheets=sheets(exported, plan, output, "portrait"))
        atomic_json(clip / ("export_visual_review.json" if encoded else "browser_visual_review.json"), receipt)
        print(f"B2 reduced Teil {part}: {len(plan)} {'decoded/browser' if encoded else 'native'} frames.", flush=True)


def verify_pre_render(build):
    verify_inputs(build)
    assert read(build / "audio_review_resolution.json")["status"] == "pass_with_asr_notes"
    assert read(build / "visual_approval.json")["contact_sheets_inspected"]
    for part, receipt in read(build / "pre_render_checks.json").items():
        clip = build / f"teil_{part}"
        verify_files({
            receipt["report"]: receipt["sha256"],
            str(clip / "geometry_portrait.json"): receipt["geometry_sha256"],
            str(clip / "portrait" / "index.html"): receipt["html_sha256"],
            str(clip / "source_validation.json"): receipt["source_validation_sha256"],
        })
    for item in read(build / "audio_review_resolution.json")["files"].items():
        verify_files(dict([item]))


def render(build, part):
    verify_pre_render(build)
    clip = build / f"teil_{part}"
    validate_clip(clip)
    master, final = clip / "render_portrait.mp4", clip / "production_portrait.mp4"
    if master.exists() or final.exists():
        raise ValueError("Refusing to overwrite an export; choose a fresh revision.")
    run([sys.executable, "-X", "utf8", str(ROOT / "hyperframes_local.py"), "render",
         str(clip / "portrait"), "--fps", "24", "--quality", "delivery", "--workers", "2",
         "--no-browser-gpu", "--output", str(master)], clip / "render_portrait.log")
    run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(master), "-i", str(clip / "dialogue.wav"),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-ar", "48000", "-ac", "1", "-t", str(read(clip / "timeline.json")["duration"]),
         "-movflags", "+faststart", str(final)], clip / "mux_portrait.log")
    print(f"B2 reduced native export ready: {final}", flush=True)


def freeze(build):
    verify_pre_render(build)
    assert read(build / "visual_approval.json")["encoded_contact_sheets_inspected"]
    reports = {}
    for part in SELECTIONS:
        clip = build / f"teil_{part}"
        reports[str(part)] = validate_clip(clip, encoded=True)
        visual = read(clip / "export_visual_review.json")
        for name, digest in visual["browser_frames"].items():
            verify_files({str(clip / "contact_portrait" / name): digest})
        for index, item in enumerate(visual["export_comparisons"], 1):
            assert item["mean_absolute_rgb_error"] < 4 and item["promotion_mean_rgb_error"] < 4
            verify_files({str(clip / "encoded_portrait" / f"frame-{index:03d}.png"): item["export_sha256"]})
    atomic_json(build / "validation.json", {"status": "pass", "clips": reports})
    files = {str(p.relative_to(build)): sha256_file(p) for p in build.rglob("*")
             if p.is_file() and p.name not in ("delivery_manifest.json", "delivery_audit.json")
             and ".hyperframes" not in p.parts}
    code = dict(read(SOURCE / "delivery_manifest.json")["code_inputs"])
    code.update({str(ROOT / n): sha256_file(ROOT / n) for n in
                 ("prepare_b2_reduced.py", "compose_b2_reduced.py", "deliver_b2_reduced.py",
                  "test_b2_reduced.py")})
    atomic_json(build / "delivery_manifest.json", {
        "scope": "Three portrait reduced-practice B2 clips with adapted pauses",
        "files": files, "code_inputs": code, "inputs": read(build / "input_pin.json"),
        "outputs": {p: dict(file=f"teil_{p}\\production_portrait.mp4",
                            duration=r["duration"], frames=r["frames"], sha256=r["encoded"]["sha256"])
                    for p, r in reports.items()},
        "human_listening": "Not performed; new independent ASR and inherited notes retained.",
        "publication": "Nothing uploaded.",
    })
    verify_files({str(build / n): digest for n, digest in files.items()})
    verify_files(code)
    atomic_json(build / "delivery_audit.json", {
        "status": "pass", "manifest_sha256": sha256_file(build / "delivery_manifest.json"),
        "delivery_files_rehashed": len(files), "code_inputs_rehashed": len(code),
        "source_preservation_rehashed": True, "browser_and_audio_review_bindings_rehashed": True,
        "all_native_and_encoded_sheets_inspected": True,
        "video_audio_container_each_strictly_under_180_seconds": True,
    })
    print(f"B2 reduced delivery frozen and audited: {build}.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("speech-review", "check", "review", "render", "validate", "freeze"))
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--part", type=int, choices=tuple(SELECTIONS))
    parser.add_argument("--encoded", action="store_true")
    args = parser.parse_args()
    build = args.build.resolve()
    if args.stage == "render":
        if args.part is None:
            parser.error("--part is required for rendering")
        render(build, args.part)
    elif args.stage == "review":
        review_frames(build, args.encoded)
    elif args.stage == "validate":
        verify_inputs(build)
        for part in SELECTIONS:
            validate_clip(build / f"teil_{part}", args.encoded)
    else:
        {"speech-review": speech_review, "check": check, "freeze": freeze}[args.stage](build)
