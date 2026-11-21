"""Inspect every per-exercise response/reveal boundary in native and encoded fide video."""

import argparse
import math
import subprocess
import sys
from pathlib import Path

from listening_2d.preparation.prepare_fide import ROOT, atomic_json, read, sha256_file
from listening_2d.checks.review_fide_frames import frame_plan as source_plan
from listening_2d.checks.review_full_frames import sheets


def frame_plan(timeline):
    selected = {p["frame"]: p["labels"] for p in source_plan(timeline)}
    for event in timeline["events"]:
        if event["id"].startswith("solution_"):
            for frame, suffix in ((event["start_frame"] - 1, "preceding"),
                                  (event["start_frame"], "first"),
                                  (event["end_frame"] - 1, "last"),
                                  (event["end_frame"], "following")):
                if 0 <= frame < timeline["total_frames"]:
                    selected.setdefault(frame, []).append(event["id"] + " " + suffix)
    return [{"frame": frame, "seconds": frame / 24,
             "snapshot_seconds": math.ceil(frame / 24 * 1000 - 1e-7) / 1000, "labels": labels}
            for frame, labels in sorted(selected.items())]


def review(build, encoded=False):
    import numpy as np
    from PIL import Image
    timeline = read(build / "timeline.json")
    plan = frame_plan(timeline)
    atomic_json(build / "review_frame_plan.json", plan)
    result = {"frames": plan, "layouts": {}}
    for layout in ("landscape", "portrait"):
        destination = build / f"contact_{layout}"
        destination.mkdir(exist_ok=True)
        stamps = [f'{p["snapshot_seconds"]:.3f}'.rstrip("0").rstrip(".") for p in plan]
        subprocess.run([sys.executable, "-B", "-X", "utf8", str(ROOT / "hyperframes_local.py"),
                        "snapshot", str(build / layout), "--at", ",".join(stamps), "--no-end",
                        "--keep", "--output", str(destination), "--no-browser-gpu",
                        "--timeout", "180000", "--json"], check=True)
        images = [destination / f"at-{stamp}s.png" for stamp in stamps]
        box = (1444, 230, 1848, 850) if layout == "landscape" else (80, 1420, 1000, 1696)
        with Image.open(images[0]) as first:
            baseline = np.asarray(first.convert("RGB").crop(box))
        for image in images:
            with Image.open(image) as actual:
                assert np.array_equal(baseline, np.asarray(actual.convert("RGB").crop(box)))
        details = {"browser_contact_sheets": sheets(images, plan, destination, layout),
                   "browser_frames": {p.name: sha256_file(p) for p in images},
                   "persistent_promotion": {"box": box, "pixel_identical": True, "frames": len(images)}}
        if encoded:
            folder = build / f"encoded_{layout}"
            folder.mkdir(exist_ok=True)
            selector = "+".join(f'eq(n\\,{p["frame"]})' for p in plan)
            subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i",
                            str(build / f"production_{layout}.mp4"), "-vf", "select=" + selector,
                            "-fps_mode", "vfr", "-frames:v", str(len(plan)),
                            str(folder / "frame-%03d.png")], check=True)
            exported = [folder / f"frame-{i:03d}.png" for i in range(1, len(plan) + 1)]
            comparisons = []
            for item, expected, actual in zip(plan, images, exported):
                with Image.open(expected) as reference, Image.open(actual) as candidate:
                    reference, candidate = reference.convert("RGB"), candidate.convert("RGB")
                    assert reference.size == candidate.size
                    error = float(np.mean(np.abs(np.asarray(reference, dtype=float) -
                                                 np.asarray(candidate, dtype=float))))
                    promotion = float(np.mean(np.abs(np.asarray(reference.crop(box), dtype=float) -
                                                     np.asarray(candidate.crop(box), dtype=float))))
                assert error < 4 and promotion < 4, (layout, item["frame"], error, promotion)
                comparisons.append({**item, "mean_absolute_rgb_error": error,
                                    "promotion_mean_absolute_rgb_error": promotion,
                                    "export_sha256": sha256_file(actual)})
            details.update(export_comparisons=comparisons,
                           encoded_contact_sheets=sheets(exported, plan, folder, layout))
        result["layouts"][layout] = details
    atomic_json(build / ("export_visual_review.json" if encoded else "browser_visual_review.json"), result)
    print(f"Inline fide review ready: {len(plan)} frames per layout.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--encoded", action="store_true")
    args = parser.parse_args()
    review(args.build.resolve(), args.encoded)
