"""Run persisted browser gates, native renders, 192-kbps audio mux and final audit."""

import argparse
from pathlib import Path
import subprocess
import sys

from prepare_a2 import read
from prepare_sample import ROOT, atomic_json, sha256_file
from validate_a2 import validate, verify_files


def run(command, log):
    with log.open("w", encoding="utf-8") as output:
        subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, check=True)


def check(build):
    validate(build)
    layouts = read(build / "composition_receipt.json")["layouts"]
    receipts = {}
    for layout in layouts:
        folder = build / layout
        run(["node", str(ROOT / "check_a2_layout.cjs"), str(folder / "index.html"),
             str(build / f"geometry_{layout}.json"), layout], build / f"geometry_{layout}.log")
        run([sys.executable, "-X", "utf8", str(ROOT / "hyperframes_local.py"), "check",
             str(folder), "--json", "--at-transitions", "--snapshots", "--no-browser-gpu",
             "--timeout", "4m"], build / f"check_{layout}.log")
        reports = list((folder / ".hyperframes" / "artifacts" / "checks").glob("*.json"))
        report_path = max(reports, key=lambda p: p.stat().st_mtime_ns)
        report = read(report_path)
        if not report["ok"] or report.get("browserSkipped", False):
            raise ValueError(f"Browser gate failed: {report_path}")
        receipts[layout] = {"report": str(report_path), "sha256": sha256_file(report_path),
                            "summary": {key: {k: v for k, v in report.get(key, {}).items()
                                              if k in ("ok", "errorCount", "warningCount", "enabled")}
                                        for key in ("lint", "runtime", "layout", "contrast",
                                                    "motion", "craft", "audio")},
                            "geometry_sha256": sha256_file(build / f"geometry_{layout}.json"),
                            "html_sha256": sha256_file(folder / "index.html"),
                            "assets_manifest_sha256": sha256_file(folder / "assets_manifest.json")}
        print(f"A2 browser gates passed: {layout}.", flush=True)
    atomic_json(build / "pre_render_checks.json", {
        "source_validation_sha256": sha256_file(build / "source_validation.json"),
        "browser": receipts,
        "note": "Review nonblocking craft/static warnings; motion-disabled is not a motion pass.",
    })


def render(build):
    validation = read(build / "pre_render_checks.json")
    if sha256_file(build / "source_validation.json") != validation["source_validation_sha256"]:
        raise ValueError("Source gate changed after browser check.")
    source = build if read(build / "timeline.json")["scope"] == "full" else Path(
        read(build / "input_pin.json")["source"])
    notes = read(source / "audio_review_resolution.json")
    if notes["status"] != "pass_with_asr_notes":
        raise ValueError("Resolve audio review before rendering.")
    if not read(build / "visual_approval.json")["contact_sheets_inspected"]:
        raise ValueError("Inspect native contact sheets before rendering.")
    duration = read(build / "timeline.json")["duration"]
    for layout, receipt in validation["browser"].items():
        if (sha256_file(Path(receipt["report"])) != receipt["sha256"]
                or sha256_file(build / layout / "index.html") != receipt["html_sha256"]
                or sha256_file(build / layout / "assets_manifest.json") != receipt["assets_manifest_sha256"]):
            raise ValueError("Checked composition changed.")
        final = build / f"production_{layout}.mp4"
        master = build / f"render_{layout}.mp4"
        if final.exists() or master.exists():
            raise ValueError("Refusing to overwrite an existing export; use a fresh revision.")
        run([sys.executable, "-X", "utf8", str(ROOT / "hyperframes_local.py"), "render",
             str(build / layout), "--fps", "24", "--quality", "delivery", "--workers", "2",
             "--no-browser-gpu", "--output", str(master)], build / f"render_{layout}.log")
        run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(master), "-i", str(build / "dialogue.wav"),
             "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
             "-b:a", "192k", "-ar", "48000", "-ac", "1", "-t", str(duration),
             "-movflags", "+faststart", str(final)], build / f"mux_{layout}.log")
        print(f"A2 native export ready: {final}", flush=True)


def freeze(build):
    validate(build, encoded=True)
    visual = read(build / "export_visual_review.json")
    if not visual["layouts"] or not read(build / "visual_approval.json")["encoded_contact_sheets_inspected"]:
        raise ValueError("Encoded contact sheets must be inspected.")
    report = read(build / "validation.json")
    if set(visual["layouts"]) != set(report["encoded"]):
        raise ValueError("Encoded visual/audio layout sets differ.")
    pin = read(build / "input_pin.json")
    if "parent_pin" in pin:
        parent = Path(pin["parent_pin"])
        assert sha256_file(parent) == pin["source_pin_sha256"]
        verify_files(read(parent)["files"])
        source_pin = read(Path(pin["source"]) / "input_pin.json")
        research = Path(pin["source"]) / "research_input_pin.json"
    else:
        source_pin = pin
        research = build / "research_input_pin.json"
    verify_files(source_pin["files"])
    verify_files(source_pin["book"])
    verify_files(read(research)["files"])
    for refs in source_pin["voices"].values():
        for item in refs.values():
            verify_files({item["path"]: item["sha256"]})
    for layout, details in visual["layouts"].items():
        for name, digest in details["browser_frames"].items():
            assert sha256_file(build / f"contact_{layout}" / name) == digest
        for index, item in enumerate(details["export_comparisons"], 1):
            assert item["mean_absolute_rgb_error"] < 4
            assert sha256_file(build / f"encoded_{layout}" / f"frame-{index:03d}.png") == item["export_sha256"]
    files = {str(p.relative_to(build)): sha256_file(p)
             for p in build.rglob("*") if p.is_file()
             and p.name not in ("delivery_manifest.json", "delivery_audit.json")
             and ".hyperframes" not in p.parts}
    code = [ROOT / name for name in (
        "prepare_a2.py", "process_a2.py", "compose_a2.py", "validate_a2.py",
        "review_a2_frames.py", "deliver_a2.py", "check_a2_layout.cjs",
        "prepare_sample.py", "prepare_full.py", "compose_full.py",
        "compose_sample.py", "review_full_frames.py", "validate_full.py",
        "hyperframes_local.py", "composition\\index.html")]
    code.extend(ROOT.parent / "pilot_3d" / name for name in (
        "prepare_audio.py", "align_words.py", "episode_profiles.py", "build_paths.py"))
    code_pins = {str(p): sha256_file(p) for p in code}
    atomic_json(build / "delivery_manifest.json", {
        "scope": read(build / "timeline.json")["scope"], "files": files,
        "inputs": source_pin, "code_inputs": code_pins,
        "duration": report["duration"], "frames": report["frames"],
        "outputs": {name: {"sha256": details["sha256"]} for name, details in report["encoded"].items()},
        "human_listening": "not performed; retain raw independent ASR and resolution notes",
        "publication": "Local delivery only; nothing uploaded.",
    })
    for name, digest in files.items():
        assert sha256_file(build / name) == digest
    verify_files(code_pins)
    atomic_json(build / "delivery_audit.json", {
        "manifest_sha256": sha256_file(build / "delivery_manifest.json"),
        "file_count": len(files), "all_manifest_files_rehashed": True,
        "source_pins_rehashed": True, "browser_reports": read(build / "pre_render_checks.json")["browser"],
        "encoded_boundary_frames": "Every reveal and each short's exact title cut included",
        "publication": "Not uploaded",
    })
    print(f"A2 frozen delivery audited: {build}.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("check", "render", "freeze"))
    parser.add_argument("--build", type=Path, required=True)
    args = parser.parse_args()
    {"check": check, "render": render, "freeze": freeze}[args.stage](args.build.resolve())
