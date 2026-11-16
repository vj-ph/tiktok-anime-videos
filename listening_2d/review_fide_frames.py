"""Capture fide instruction, picture, response and solution boundaries in both ratios."""

import argparse
import math
from pathlib import Path
import subprocess
import sys

from prepare_fide import ROOT, atomic_json, read, sha256_file
from review_full_frames import sheets


def frame_plan(timeline):
    selected = {}

    def add(frame, label):
        frame = max(0, min(timeline["total_frames"] - 1, int(frame)))
        selected.setdefault(frame, []).append(label)

    for event in timeline["events"]:
        ident = event["id"]
        if event.get("visible"):
            turn = next(t for t in timeline["turns"] if t["id"] == ident)
            word = max(turn["words"], key=lambda w: w["end"] - w["start"])
            add((turn["start"] + (word["start"] + word["end"]) / 2) * 24, ident + " measured highlight")
        if ident.startswith(("inspect_", "answer_", "solution_")) or ident == "cta":
            add((event["start_frame"] + event["end_frame"]) // 2, ident)
        if ident in ("transition", "end_test", "solution_7"):
            add(event["start_frame"] - 1, ident + " preceding frame")
            add(event["start_frame"], ident + " first frame")
    return [{"frame": frame, "seconds": frame / 24,
             "snapshot_seconds": math.ceil(frame / 24 * 1000 - 1e-7) / 1000, "labels": labels}
            for frame, labels in sorted(selected.items())]


def review(build, encoded=False):
    from PIL import Image
    import numpy as np
    timeline = read(build / "timeline.json")
    plan = frame_plan(timeline)
    atomic_json(build / "review_frame_plan.json", plan)
    receipt = {"frames": plan, "layouts": {}}
    for layout in ("landscape", "portrait"):
        destination = build / f"contact_{layout}"
        destination.mkdir(exist_ok=True)
        stamps = [f'{item["snapshot_seconds"]:.3f}'.rstrip("0").rstrip(".") for item in plan]
        subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "hyperframes_local.py"),
                        "snapshot", str(build / layout), "--at", ",".join(stamps), "--no-end",
                        "--keep", "--output", str(destination), "--no-browser-gpu",
                        "--timeout", "120000", "--json"], check=True)
        images = [destination / f"at-{stamp}s.png" for stamp in stamps]
        assert all(path.is_file() for path in images)
        box = (1444, 230, 1848, 850) if layout == "landscape" else (80, 1420, 1000, 1696)
        with Image.open(images[0]) as source:
            baseline = np.asarray(source.convert("RGB").crop(box))
        for path in images[1:]:
            with Image.open(path) as source:
                assert np.array_equal(baseline, np.asarray(source.convert("RGB").crop(box)))
        details = {"browser_contact_sheets": sheets(images, plan, destination, layout),
                   "browser_frames": {path.name: sha256_file(path) for path in images},
                   "persistent_promotion": {"box": box, "pixel_identical": True, "frames": len(images)}}
        if encoded:
            output = build / f"encoded_{layout}"
            output.mkdir(exist_ok=True)
            selector = "+".join(f'eq(n\\,{item["frame"]})' for item in plan)
            subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i",
                            str(build / f"production_{layout}.mp4"), "-vf", "select=" + selector,
                            "-fps_mode", "vfr", "-frames:v", str(len(plan)),
                            str(output / "frame-%03d.png")], check=True)
            exported = [output / f"frame-{index + 1:03d}.png" for index in range(len(plan))]
            comparisons = []
            for item, expected, actual in zip(plan, images, exported):
                with Image.open(expected) as reference, Image.open(actual) as candidate:
                    assert reference.size == candidate.size
                    reference, candidate = reference.convert("RGB"), candidate.convert("RGB")
                    error = float(np.mean(np.abs(np.asarray(reference, dtype=float) -
                                                 np.asarray(candidate, dtype=float))))
                    promotion_error = float(np.mean(np.abs(np.asarray(reference.crop(box), dtype=float) -
                                                           np.asarray(candidate.crop(box), dtype=float))))
                assert error < 4 and promotion_error < 4, f"Fide export/browser mismatch: {layout}/{item['frame']}"
                comparisons.append({**item, "mean_absolute_rgb_error": error,
                                    "promotion_mean_absolute_rgb_error": promotion_error,
                                    "export_sha256": sha256_file(actual)})
            details.update(export_comparisons=comparisons,
                           encoded_contact_sheets=sheets(exported, plan, output, layout))
        receipt["layouts"][layout] = details
    atomic_json(build / ("export_visual_review.json" if encoded else "browser_visual_review.json"), receipt)
    print(f"Fide review frames ready: {len(plan)} per native layout.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--encoded", action="store_true")
    args = parser.parse_args()
    review(args.build.resolve(), args.encoded)
