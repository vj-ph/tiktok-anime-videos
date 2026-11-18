"""Gate, render and freeze the separate full fide listening delivery."""

import argparse
from pathlib import Path
import subprocess
import sys

from listening_2d.checks.audit_fide_sequence import audit
from listening_2d.preparation.prepare_fide import ROOT, atomic_json, read, sha256_file, verify_files
from listening_2d.checks.validate_fide import validate


def run(command, log):
    if log.exists():
        number = 2
        while log.with_name(f"{log.stem}_attempt_{number}{log.suffix}").exists():
            number += 1
        log = log.with_name(f"{log.stem}_attempt_{number}{log.suffix}")
    print("Running: " + subprocess.list2cmdline(list(map(str, command))), flush=True)
    with log.open("w", encoding="utf-8") as output:
        subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, check=True)


def check(build):
    validate(build)
    audit(build, build / "sequence_pre_render.json")
    receipts = {}
    for layout in ("landscape", "portrait"):
        folder = build / layout
        run(["node", str(ROOT / "checks/check_fide_layout.cjs"), str(folder / "index.html"),
             str(build / f"geometry_{layout}.json"), layout], build / f"geometry_{layout}.log")
        run([sys.executable, "-X", "utf8", str(ROOT / "hyperframes_local.py"), "check",
             str(folder), "--json", "--at-transitions", "--snapshots", "--no-browser-gpu",
             "--timeout", "4m"], build / f"check_{layout}.log")
        reports = list((folder / ".hyperframes" / "artifacts" / "checks").glob("*.json"))
        report_path = max(reports, key=lambda p: p.stat().st_mtime_ns)
        report = read(report_path)
        if not report["ok"] or report.get("browserSkipped", False):
            raise ValueError(f"Fide browser gate failed: {report_path}")
        receipts[layout] = {
            "report": str(report_path), "sha256": sha256_file(report_path),
            "geometry_sha256": sha256_file(build / f"geometry_{layout}.json"),
            "html_sha256": sha256_file(folder / "index.html"),
            "assets_manifest_sha256": sha256_file(folder / "assets_manifest.json"),
            "summary": {key: {k: v for k, v in report.get(key, {}).items()
                              if k in ("ok", "errorCount", "warningCount", "enabled")}
                        for key in ("lint", "runtime", "layout", "contrast", "motion", "craft", "audio")}}
    atomic_json(build / "pre_render_checks.json", {
        "source_validation_sha256": sha256_file(build / "source_validation.json"),
        "browser": receipts, "note": "Disabled motion checks are not a motion pass."})
    print("Fide source, sequence and both browser gates passed.", flush=True)


def render(build, only_layout=None):
    validate(build)
    checks = read(build / "pre_render_checks.json")
    if sha256_file(build / "source_validation.json") != checks["source_validation_sha256"]:
        raise ValueError("Source gate changed after browser checks.")
    audio = read(build / "audio_review_resolution.json")
    if (audio["status"] != "pass_with_asr_notes"
            or audio["audio_manifest_sha256"] != sha256_file(build / "audio_manifest.json")):
        raise ValueError("Resolve ASR findings against this exact audio manifest before rendering.")
    verify_files(audio["review_files_sha256"])
    visual = read(build / "visual_approval.json")
    if (not visual["contact_sheets_inspected"]
            or visual["browser_visual_review_sha256"] != sha256_file(build / "browser_visual_review.json")):
        raise ValueError("Inspect native fide contact sheets before rendering.")
    duration = read(build / "timeline.json")["duration"]
    for layout, receipt in checks["browser"].items():
        if only_layout and layout != only_layout:
            continue
        verify_files({receipt["report"]: receipt["sha256"],
                      str(build / f"geometry_{layout}.json"): receipt["geometry_sha256"],
                      str(build / layout / "index.html"): receipt["html_sha256"],
                      str(build / layout / "assets_manifest.json"): receipt["assets_manifest_sha256"]})
        final, master = build / f"production_{layout}.mp4", build / f"render_{layout}.mp4"
        if final.exists() or master.exists():
            raise ValueError("An export exists; use a fresh revision rather than overwrite it.")
        run([sys.executable, "-X", "utf8", str(ROOT / "hyperframes_local.py"), "render",
             str(build / layout), "--fps", "24", "--quality", "delivery", "--workers", "2",
             "--no-browser-gpu", "--output", str(master)], build / f"render_{layout}.log")
        run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(master), "-i", str(build / "dialogue.wav"),
             "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
             "-b:a", "192k", "-ar", "48000", "-ac", "1", "-t", str(duration),
             "-movflags", "+faststart", str(final)], build / f"mux_{layout}.log")
        print(f"Fide native export ready: {final}", flush=True)


def freeze(build):
    validate(build, encoded=True)
    audit(build, build / "sequence_encoded.json")
    approval = read(build / "visual_approval.json")
    if (not approval["contact_sheets_inspected"] or not approval["encoded_contact_sheets_inspected"]
            or approval["export_visual_review_sha256"] != sha256_file(build / "export_visual_review.json")):
        raise ValueError("Native and encoded fide contact sheets require recorded inspection.")
    visual = read(build / "export_visual_review.json")
    for layout, details in visual["layouts"].items():
        verify_files({str(build / f"contact_{layout}" / name): digest
                      for name, digest in details["browser_frames"].items()})
        for index, frame in enumerate(details["export_comparisons"], 1):
            assert frame["mean_absolute_rgb_error"] < 4 and frame["promotion_mean_absolute_rgb_error"] < 4
            verify_files({str(build / f"encoded_{layout}" / f"frame-{index:03d}.png"): frame["export_sha256"]})
    files = {str(p.relative_to(build)): sha256_file(p) for p in build.rglob("*")
             if p.is_file() and p.name not in ("delivery_manifest.json", "delivery_audit.json")
             and ".hyperframes" not in p.parts}
    programs = [ROOT / name for name in (
        "preparation/prepare_fide.py", "preparation/process_fide.py", "rendering/compose_fide.py", "checks/audit_fide_sequence.py",
        "checks/check_fide_layout.cjs", "checks/validate_fide.py", "checks/review_fide_frames.py", "rendering/deliver_fide.py",
        "preparation/prepare_sample.py", "checks/review_full_frames.py", "checks/validate_full.py", "checks/review_sample_audio.py",
        "hyperframes_local.py", "composition\\index.html")]
    programs.extend(ROOT.parent / "pilot_3d" / name for name in (
        "prepare_audio.py", "align_words.py", "episode_profiles.py", "build_paths.py", "generation_runtime.py"))
    code = {str(path): sha256_file(path) for path in programs}
    report = read(build / "validation.json")
    atomic_json(build / "delivery_manifest.json", {
        "scope": "Full fide A2-B1 listening, both native aspect ratios",
        "files": files, "inputs": read(build / "input_pin.json"), "code_inputs": code,
        "frames": report["frames"], "duration": report["duration"],
        "outputs": {layout: {"sha256": details["sha256"]} for layout, details in report["encoded"].items()},
        "human_listening": "Not performed; retain model-review and ASR uncertainties.",
        "publication": "Local delivery; nothing uploaded."})
    verify_files({str(build / name): digest for name, digest in files.items()})
    verify_files(code)
    atomic_json(build / "delivery_audit.json", {
        "manifest_sha256": sha256_file(build / "delivery_manifest.json"), "file_count": len(files),
        "all_manifest_files_rehashed": True, "source_and_code_pins_rehashed": True,
        "human_listening": False, "publication": "Not uploaded"})
    print(f"Fide delivery frozen and rehashed: {build}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("check", "render", "freeze"))
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--layout", choices=("landscape", "portrait"))
    args = parser.parse_args()
    if args.stage == "render":
        render(args.build.resolve(), args.layout)
    else:
        {"check": check, "freeze": freeze}[args.stage](args.build.resolve())
