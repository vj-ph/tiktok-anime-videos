"""Persist B2 browser gates, native renders and a hash-verified full delivery."""

import argparse
from pathlib import Path
import subprocess
import sys

from audit_b2_sequence import audit
from prepare_b2 import read
from prepare_sample import ROOT, atomic_json, sha256_file
from validate_b2 import validate, verify_files


def run(command, log):
    with log.open("w", encoding="utf-8") as output:
        subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, check=True)


def check(build):
    validate(build)
    audit(build, build / "sequence_pre_render.json")
    receipts = {}
    for layout in ("landscape", "portrait"):
        folder = build / layout
        run(["node", str(ROOT / "check_b2_layout.cjs"), str(folder / "index.html"),
             str(build / f"geometry_{layout}.json"), layout], build / f"geometry_{layout}.log")
        run([sys.executable, "-X", "utf8", str(ROOT / "hyperframes_local.py"), "check",
             str(folder), "--json", "--at-transitions", "--snapshots", "--no-browser-gpu",
             "--timeout", "4m"], build / f"check_{layout}.log")
        reports = list((folder / ".hyperframes" / "artifacts" / "checks").glob("*.json"))
        report_path = max(reports, key=lambda p: p.stat().st_mtime_ns)
        report = read(report_path)
        if not report["ok"] or report.get("browserSkipped", False):
            raise ValueError(f"B2 browser gate failed: {report_path}")
        receipts[layout] = {
            "report": str(report_path), "sha256": sha256_file(report_path),
            "summary": {key: {k: v for k, v in report.get(key, {}).items()
                              if k in ("ok", "errorCount", "warningCount", "enabled")}
                        for key in ("lint", "runtime", "layout", "contrast", "motion", "craft", "audio")},
            "geometry_sha256": sha256_file(build / f"geometry_{layout}.json"),
            "html_sha256": sha256_file(folder / "index.html"),
            "assets_manifest_sha256": sha256_file(folder / "assets_manifest.json")}
        print(f"B2 browser gates passed: {layout}.", flush=True)
    atomic_json(build / "pre_render_checks.json", dict(
        source_validation_sha256=sha256_file(build / "source_validation.json"), browser=receipts,
        note="Retain nonblocking craft/static warnings; motion-disabled is not a motion pass."))


def render(build, only_layout=None):
    validation = read(build / "pre_render_checks.json")
    if sha256_file(build / "source_validation.json") != validation["source_validation_sha256"]:
        raise ValueError("Source gate changed after browser check.")
    if read(build / "audio_review_resolution.json")["status"] != "pass_with_asr_notes":
        raise ValueError("Resolve audio review before rendering.")
    if not read(build / "visual_approval.json")["contact_sheets_inspected"]:
        raise ValueError("Inspect native B2 sheets before rendering.")
    duration = read(build / "timeline.json")["duration"]
    for layout, receipt in validation["browser"].items():
        if only_layout and layout != only_layout:
            continue
        if (sha256_file(Path(receipt["report"])) != receipt["sha256"]
                or sha256_file(build / layout / "index.html") != receipt["html_sha256"]
                or sha256_file(build / layout / "assets_manifest.json") != receipt["assets_manifest_sha256"]):
            raise ValueError("Checked B2 composition changed.")
        final, master = build / f"production_{layout}.mp4", build / f"render_{layout}.mp4"
        if final.exists() or master.exists():
            raise ValueError("Refusing to overwrite an existing export; use a fresh revision.")
        run([sys.executable, "-X", "utf8", str(ROOT / "hyperframes_local.py"), "render",
             str(build / layout), "--fps", "24", "--quality", "delivery", "--workers", "2",
             "--no-browser-gpu", "--output", str(master)], build / f"render_{layout}.log")
        run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(master), "-i", str(build / "dialogue.wav"),
             "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
             "-b:a", "192k", "-ar", "48000", "-ac", "1", "-t", str(duration),
             "-movflags", "+faststart", str(final)], build / f"mux_{layout}.log")
        print(f"B2 native export ready: {final}", flush=True)


def freeze(build):
    validate(build, encoded=True)
    audit(build, build / "sequence_encoded.json")
    approval = read(build / "visual_approval.json")
    if not approval["contact_sheets_inspected"] or not approval["encoded_contact_sheets_inspected"]:
        raise ValueError("Both native and decoded B2 sheets require inspection.")
    visual, report = read(build / "export_visual_review.json"), read(build / "validation.json")
    assert set(visual["layouts"]) == set(report["encoded"]) == {"landscape", "portrait"}
    for layout, details in visual["layouts"].items():
        for name, digest in details["browser_frames"].items():
            assert sha256_file(build / f"contact_{layout}" / name) == digest
        for index, item in enumerate(details["export_comparisons"], 1):
            assert item["mean_absolute_rgb_error"] < 4
            assert sha256_file(build / f"encoded_{layout}" / f"frame-{index:03d}.png") == item["export_sha256"]
    files = {str(p.relative_to(build)): sha256_file(p) for p in build.rglob("*")
             if p.is_file() and p.name not in ("delivery_manifest.json", "delivery_audit.json")
             and ".hyperframes" not in p.parts}
    code = [ROOT / name for name in (
        "prepare_b2.py", "process_b2.py", "compose_b2.py", "validate_b2.py",
        "audit_b2_sequence.py", "review_b2_frames.py", "deliver_b2.py", "check_b2_layout.cjs",
        "prepare_sample.py", "prepare_full.py", "compose_full.py", "compose_sample.py",
        "review_full_frames.py", "validate_full.py", "review_sample_audio.py",
        "hyperframes_local.py", "composition\\index.html")]
    code.extend(ROOT.parent / "pilot_3d" / name for name in (
        "prepare_audio.py", "align_words.py", "episode_profiles.py", "build_paths.py"))
    code_pins = {str(p): sha256_file(p) for p in code}
    atomic_json(build / "delivery_manifest.json", {
        "scope": "full", "files": files, "inputs": read(build / "input_pin.json"),
        "code_inputs": code_pins, "duration": report["duration"], "frames": report["frames"],
        "outputs": {name: {"sha256": details["sha256"]} for name, details in report["encoded"].items()},
        "human_listening": "Not performed; retain raw independent ASR and resolution notes.",
        "publication": "Local delivery only; nothing uploaded."})
    verify_files({str(build / name): digest for name, digest in files.items()})
    verify_files(code_pins)
    atomic_json(build / "delivery_audit.json", {
        "manifest_sha256": sha256_file(build / "delivery_manifest.json"),
        "file_count": len(files), "all_manifest_files_rehashed": True, "source_pins_rehashed": True,
        "browser_reports": read(build / "pre_render_checks.json")["browser"],
        "encoded_boundary_frames": "Reading/chime, all reveals/endings and portrait interview page boundaries.",
        "publication": "Not uploaded"})
    print(f"B2 frozen delivery audited: {build}.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("check", "render", "freeze"))
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--layout", choices=("landscape", "portrait"))
    args = parser.parse_args()
    build = args.build.resolve()
    if args.stage == "render":
        render(build, args.layout)
    else:
        {"check": check, "freeze": freeze}[args.stage](build)
