"""Inspect native/encoded B2 boundaries, portrait pages and persistent promotion."""

import argparse
import math
from pathlib import Path
import subprocess
import sys

from compose_b2_r3 import visual_plan
from prepare_b2 import read
from prepare_sample import ROOT, atomic_json, sha256_file
from process_b2 import VISIBLE_INSTRUCTIONS
from review_full_frames import sheets


def frame_plan(timeline):
    selected = {}

    def add(frame, label):
        frame = max(0, min(timeline["total_frames"] - 1, int(frame)))
        selected.setdefault(frame, []).append(label)

    for event in timeline["events"]:
        if event["kind"] == "silence":
            add((event["start_frame"] + event["end_frame"]) // 2, event["id"])
        if event["kind"] in ("chime", "reveal") or event["id"] in VISIBLE_INSTRUCTIONS:
            add(event["start_frame"] - 1, event["id"] + " preceding frame")
            add(event["start_frame"], event["id"] + " first frame")
        if event["kind"] == "reveal":
            add(event["end_frame"] - 1, event["id"] + " last frame")
        if event["id"] in ("title", "end_part_1", "end_part_2", "end_test", "cta", "news_theatre") \
                or event["id"].startswith("short_"):
            add((event["start_frame"] + event["end_frame"]) // 2, event["id"])
    for event in visual_plan(timeline, "portrait"):
        if event.get("page"):
            add(event["start_frame"] - 1, f"portrait interview page {event['page']} preceding frame")
            add(event["start_frame"], f"portrait interview page {event['page']} first frame")
            add((event["start_frame"] + event["end_frame"]) // 2, f"portrait interview page {event['page']} middle")
    for turn in timeline["turns"]:
        if turn["id"] in VISIBLE_INSTRUCTIONS:
            word = max(turn["words"], key=lambda w: w["end"] - w["start"])
            add((turn["start"] + (word["start"] + word["end"]) / 2) * 24,
                turn["id"] + " measured highlight")
    return [dict(frame=f, seconds=f / 24, snapshot_seconds=math.ceil(f / 24 * 1000 - 1e-7) / 1000,
                 labels=labels) for f, labels in sorted(selected.items())]


def review(build, encoded=False):
    from PIL import Image
    import numpy as np
    timeline = read(build / "timeline.json")
    plan = frame_plan(timeline)
    atomic_json(build / "review_frame_plan.json", plan)
    receipt = dict(frames=plan, layouts={})
    for layout in ("landscape", "portrait"):
        destination = build / f"contact_{layout}"
        destination.mkdir(exist_ok=True)
        stamps = [f'{p["snapshot_seconds"]:.3f}'.rstrip("0").rstrip(".") for p in plan]
        subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "hyperframes_local.py"),
                        "snapshot", str(build / layout), "--at", ",".join(stamps), "--no-end",
                        "--keep", "--output", str(destination), "--no-browser-gpu",
                        "--timeout", "120000", "--json"], check=True)
        images = [destination / f"at-{stamp}s.png" for stamp in stamps]
        assert all(p.is_file() for p in images)
        details = dict(browser_contact_sheets=sheets(images, plan, destination, layout),
                       browser_frames={p.name: sha256_file(p) for p in images})
        box = (1444, 232, 1848, 932) if layout == "landscape" else (80, 1420, 1000, 1696)
        with Image.open(images[0]) as image:
            baseline = np.asarray(image.convert("RGB").crop(box))
        for path in images[1:]:
            with Image.open(path) as image:
                assert np.array_equal(baseline, np.asarray(image.convert("RGB").crop(box)))
        details["persistent_promotion"] = dict(box=box, frames=len(images), pixel_identical=True)
        if encoded:
            output = build / f"encoded_{layout}"
            output.mkdir(exist_ok=True)
            selector = "+".join(f'eq(n\\,{item["frame"]})' for item in plan)
            subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i",
                            str(build / f"production_{layout}.mp4"), "-vf", "select=" + selector,
                            "-fps_mode", "vfr", "-frames:v", str(len(plan)),
                            str(output / "frame-%03d.png")], check=True)
            exported = [output / f"frame-{i + 1:03d}.png" for i in range(len(plan))]
            comparisons = []
            for item, expected, actual in zip(plan, images, exported):
                with Image.open(expected) as reference, Image.open(actual) as candidate:
                    assert reference.size == candidate.size
                    error = float(np.mean(np.abs(np.asarray(reference.convert("RGB"), dtype=float) -
                                                 np.asarray(candidate.convert("RGB"), dtype=float))))
                assert error < 4, f"B2 export mismatch: {layout}, frame {item['frame']}, {error}"
                comparisons.append({**item, "mean_absolute_rgb_error": error,
                                    "export_sha256": sha256_file(actual)})
            details.update(export_comparisons=comparisons,
                           encoded_contact_sheets=sheets(exported, plan, output, layout))
        receipt["layouts"][layout] = details
    atomic_json(build / ("export_visual_review.json" if encoded else "browser_visual_review.json"), receipt)
    print(f"B2 review: {len(plan)} frames per native layout.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--encoded", action="store_true")
    args = parser.parse_args()
    review(args.build.resolve(), args.encoded)
