"""Capture measured full-layout contact sheets and compare final exported frames."""

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

from compose_sample import ROOT
from prepare_sample import atomic_json, sha256_file


def frame_plan(timeline):
    selected = {}

    def add(frame, label):
        frame = max(0, min(timeline["total_frames"] - 1, int(frame)))
        selected.setdefault(frame, []).append(label)

    for turn in timeline["turns"]:
        if turn["id"] == "title" or turn["id"].startswith("instruction_"):
            word = max(turn["words"], key=lambda entry: entry["end"] - entry["start"])
            add((turn["start"] + (word["start"] + word["end"]) / 2) * 24, turn["id"] + " highlight")
    for event in timeline["events"]:
        if event["kind"] == "silence" and event["phase"] == "Lesen":
            add((event["start_frame"] + event["end_frame"]) // 2, event["card"] + " reading")
        if event["kind"] == "reveal" and event["part"] in (3, 4):
            add(event["start_frame"] + 24, event["card"] + " reveal")
        if event["id"] in ("summary_read", "cta"):
            add((event["start_frame"] + event["end_frame"]) // 2, event["id"])
        if event["id"] == "p1_task_1_answer":
            add(event["end_frame"] - 1, "task 1 final silent answer frame")
            add(event["end_frame"], "task 1 first reveal frame")
    return [{"frame": frame, "seconds": frame / 24, "labels": labels}
            for frame, labels in sorted(selected.items())]


def sheets(paths, plan, destination, layout):
    from PIL import Image, ImageDraw, ImageFont
    size = (480, 270) if layout == "landscape" else (300, 533)
    font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 16)
    result = []
    for page in range((len(paths) + 8) // 9):
        image = Image.new("RGB", (3 * (size[0] + 16), 3 * (size[1] + 50)), "#f2f6f1")
        draw = ImageDraw.Draw(image)
        for offset, path in enumerate(paths[page * 9:page * 9 + 9]):
            item = plan[page * 9 + offset]
            x, y = (offset % 3) * (size[0] + 16), (offset // 3) * (size[1] + 50)
            with Image.open(path) as source:
                image.paste(source.convert("RGB").resize(size, Image.Resampling.LANCZOS), (x, y))
            label = f'{item["seconds"]:.2f}s | {item["labels"][0]}'
            while draw.textbbox((0, 0), label, font=font)[2] > size[0]:
                label = label[:-4] + "..."
            draw.text((x + 4, y + size[1] + 8), label, font=font, fill="#283e3c")
        target = destination / f"contact-sheet-{page + 1:02d}.jpg"
        image.save(target, quality=93)
        result.append(str(target))
    return result


def review(build, encoded=False):
    build = build.resolve()
    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    plan = frame_plan(timeline)
    # Keep millisecond snapshot names while seeking inside, not before, the selected frame.
    for item in plan:
        item["snapshot_seconds"] = math.ceil(item["seconds"] * 1000 - 1e-7) / 1000
    atomic_json(build / "review_frame_plan.json", plan)
    stamps = [f'{item["snapshot_seconds"]:.3f}'.rstrip("0").rstrip(".") for item in plan]
    receipt = {"frames": plan, "layouts": {}}
    for layout in ("landscape", "portrait"):
        destination = build / f"contact_{layout}"
        destination.mkdir(exist_ok=True)
        subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "hyperframes_local.py"),
                        "snapshot", str(build / layout), "--at", ",".join(stamps),
                        "--no-end", "--keep", "--output", str(destination),
                        "--no-browser-gpu", "--timeout", "120000", "--json"], check=True)
        images = [destination / f"at-{stamp}s.png" for stamp in stamps]
        assert all(path.is_file() for path in images)
        details = {"browser_contact_sheets": sheets(images, plan, destination, layout),
                   "browser_frames": {path.name: sha256_file(path) for path in images}}
        if encoded:
            import numpy as np
            from PIL import Image
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
                    error = float(np.mean(np.abs(np.asarray(reference.convert("RGB"), dtype=float) -
                                                 np.asarray(candidate.convert("RGB"), dtype=float))))
                assert error < 4, f"Export/browser mismatch: {layout}, frame {item['frame']}, {error}"
                comparisons.append({**item, "mean_absolute_rgb_error": error,
                                    "export_sha256": sha256_file(actual)})
            details.update(export_comparisons=comparisons,
                           encoded_contact_sheets=sheets(exported, plan, output, layout))
        receipt["layouts"][layout] = details
    atomic_json(build / ("export_visual_review.json" if encoded else "browser_visual_review.json"), receipt)
    print(f"{len(plan)} measured review frames per native layout verified.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--encoded", action="store_true")
    args = parser.parse_args()
    review(args.build, args.encoded)
