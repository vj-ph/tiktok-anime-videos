#!/usr/bin/env python3
"""Inventory builds and optionally remove rendered frames from completed runs."""

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

from build_paths import BUILDS

RUN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
FRAME_NAMES = {
    "frames": re.compile(r"frame_\d+\.png\Z"),
    "listener_frames": re.compile(r"listener_\d+\.png\Z"),
}
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def checked_stat(path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & REPARSE_POINT:
        raise ValueError(f"Refusing a symbolic link or junction: {path}")
    return info


def hash_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checked_file(path):
    info = checked_stat(path)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"Expected a regular file: {path}")
    return info


def checked_dir(path):
    info = checked_stat(path)
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError(f"Expected a directory: {path}")


def selected_run(root, name):
    if not RUN_NAME.fullmatch(name) or name in (".", ".."):
        raise ValueError("Select exactly one build name, not a path or wildcard.")
    checked_dir(root)
    run = root / name
    checked_dir(run)
    return run


def inventory(root):
    checked_dir(root)
    runs = []
    def fail_walk(error):
        raise error

    for run in root.iterdir():
        info = checked_stat(run)
        if not stat.S_ISDIR(info.st_mode):
            continue
        total, frame_bytes, count = 0, 0, 0
        for parent, directories, files in os.walk(run, followlinks=False, onerror=fail_walk):
            for name in directories:
                checked_dir(Path(parent) / name)
            for name in files:
                path = Path(parent) / name
                size = checked_file(path).st_size
                total += size
                if path.parent.parent == run and path.parent.name in FRAME_NAMES:
                    if FRAME_NAMES[path.parent.name].fullmatch(path.name):
                        frame_bytes += size
                        count += 1
        runs.append((run.name, total, frame_bytes, count))
    return sorted(runs, key=lambda row: (-row[1], row[0]))


def completed_delivery(run):
    report_path = run / "delivery_checks.json"
    checked_file(report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    state = run / "pipeline_state.json"
    if state.exists():
        checked_file(state)
        stages = json.loads(state.read_text(encoding="utf-8")).get("stages", {})
        if not all(name in stages for name in ("frames", "export", "review")):
            raise ValueError("Speaking run is not marked as fully exported and reviewed.")
        files = report.get("files", {})
        if not isinstance(files, dict):
            raise ValueError("Invalid speaking delivery report.")
        if not all(name in files for name in ("pilot.mp4", "pilot_clean.mp4")):
            raise ValueError("Speaking delivery does not contain both verified videos.")
        for name in ("pilot.mp4", "pilot_clean.mp4"):
            entry = files[name]
            output = run / name
            checked_file(output)
            if not isinstance(entry, dict) or entry.get("decoded") is not True or hash_file(output) != entry.get("sha256"):
                raise ValueError(f"Delivery video is missing or differs from its report: {output}")
        return "frames"
    state = run / "listening_state.json"
    checked_file(state)
    if json.loads(state.read_text(encoding="utf-8")).get("profile") not in ("preview", "production"):
        raise ValueError("Invalid listening delivery state.")
    output = run / "pilot.mp4"
    checked_file(output)
    receipt = run / "listener_frames.json"
    checked_file(receipt)
    if (hash_file(output) != report.get("output_sha256")
            or json.loads(receipt.read_text(encoding="utf-8")) != report.get("listener_frames_sha256")):
        raise ValueError("Listening delivery video differs from its report.")
    return "listener_frames"


def frame_files(run, directory):
    folder = run / directory
    checked_dir(folder)
    results = []
    for path in folder.iterdir():
        if not FRAME_NAMES[directory].fullmatch(path.name):
            raise ValueError(f"Unexpected item in frame directory; refusing cleanup: {path}")
        info = checked_file(path)
        if info.st_nlink != 1:
            raise ValueError(f"Refusing a multiply linked frame: {path}")
        results.append((path, info))
    if not results:
        raise ValueError(f"No rendered frames found: {folder}")
    return sorted(results, key=lambda pair: pair[0].name)


def active_generators():
    try:
        import psutil
    except ImportError as error:
        raise RuntimeError("psutil is required for cleanup; install the existing project requirements.") from error
    found = []
    names = ("pipeline.py", "resume_pipeline.py", "listening_scene.py",
             "produce_v4.py", "render.py", "benchmark_workers.py")
    for process in psutil.process_iter(["pid", "name"]):
        if process.pid == os.getpid():
            continue
        try:
            name = (process.info["name"] or "").lower()
            if name in ("blender", "blender.exe", "ffmpeg", "ffmpeg.exe"):
                found.append(f"{process.pid} ({name})")
            elif name.startswith(("python", "py.exe")):
                command = process.cmdline()
                if any(Path(arg).name.lower() in names for arg in command):
                    found.append(f"{process.pid} ({name})")
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied as error:
            raise RuntimeError(f"Cannot inspect process {process.pid}; refusing cleanup.") from error
    return found


def plan_run(run):
    directory = completed_delivery(run)
    files = frame_files(run, directory)
    if directory == "listener_frames":
        receipt = json.loads((run / "listener_frames.json").read_text(encoding="utf-8"))
        if set(receipt) != {path.name for path, _ in files}:
            raise ValueError("Listener frames do not match the delivery receipt.")
    return directory, files


def check_unchanged(files):
    for path, old in files:
        current = checked_file(path)
        if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns, current.st_nlink) != (
                old.st_dev, old.st_ino, old.st_size, old.st_mtime_ns, old.st_nlink):
            raise ValueError(f"Frame changed during cleanup: {path}")


def require_idle():
    active = active_generators()
    if active:
        raise ValueError("Active rendering/generation processes detected: " + ", ".join(active))


def clean_frames(run, *, apply=False):
    directory, files = plan_run(run)
    size = sum(info.st_size for _, info in files)
    print(f"Selected: {run / directory}")
    print(f"Rendered frames: {len(files)}; {size / 1024**3:.3f} GiB")
    print("Removing frames breaks frame-level verification and resume/re-export; keep backups if needed.")
    if not apply:
        print("Dry run: no files deleted.")
        return
    require_idle()
    plan_run(run)
    check_unchanged(files)
    for path, _ in files:
        path.unlink()
    print(f"Deleted {len(files)} frame files; preserved videos, audio, scenes and metadata.")


def bulk_plan(root):
    checked_dir(root)
    plans, skipped = [], []
    for run in sorted(root.iterdir(), key=lambda path: path.name):
        try:
            info = checked_stat(run)
            if not stat.S_ISDIR(info.st_mode):
                continue
            selected_run(root, run.name)
            if not any(os.path.lexists(run / directory) for directory in FRAME_NAMES):
                skipped.append((run.name, "No recognized frame directory."))
                continue
            directory, files = plan_run(run)
            plans.append((run, directory, files))
        except (OSError, ValueError) as error:
            skipped.append((run.name, str(error)))
    return plans, skipped


def plan_token(root, plans, skipped):
    entries, proofs = [], []
    for run, directory, files in plans:
        metadata = ("delivery_checks.json", "pipeline_state.json") if directory == "frames" else (
            "delivery_checks.json", "listening_state.json", "listener_frames.json")
        for name in metadata:
            path = run / name
            checked_file(path)
            proofs.append([run.name, name, hash_file(path)])
        for path, info in files:
            entries.append([run.name, directory, path.name, info.st_dev, info.st_ino,
                            info.st_size, info.st_mtime_ns, info.st_nlink])
    encoded = json.dumps({"root": str(root.resolve()), "frames": entries, "proofs": proofs, "skipped": skipped},
                         ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def clean_all(root, *, apply=False, confirm=None):
    plans, skipped = bulk_plan(root)
    token = plan_token(root, plans, skipped)
    for run, directory, files in plans:
        size = sum(info.st_size for _, info in files)
        print(f"Eligible: {run.name}\\{directory} ({len(files)} frames, {size / 1024**3:.3f} GiB)")
    for name, reason in skipped:
        print(f"Skipped: {name} - {reason}")
    count = sum(len(files) for _, _, files in plans)
    size = sum(info.st_size for _, _, files in plans for _, info in files)
    print(f"Total: {len(plans)} eligible builds, {count} frames, {size / 1024**3:.3f} GiB; "
          f"{len(skipped)} builds skipped.")
    print("Removing frames breaks frame-level verification and resume/re-export; keep backups if needed.")
    if not apply:
        if plans:
            print(f"To apply this exact plan: --all --apply --confirm {token}")
        print("Dry run: no files deleted.")
        return
    if not plans:
        raise ValueError("No eligible builds to clean.")
    if confirm != token:
        raise ValueError("Confirmation token does not match the current plan; run --all again.")
    require_idle()
    refreshed, refreshed_skipped = bulk_plan(root)
    if plan_token(root, refreshed, refreshed_skipped) != token:
        raise ValueError("Builds changed during cleanup planning; run --all again.")
    for _, _, files in refreshed:
        check_unchanged(files)
    deleted = 0
    try:
        for run, directory, files in refreshed:
            checked_dir(root)
            checked_dir(run)
            checked_dir(run / directory)
            for path, _ in files:
                path.unlink()
                deleted += 1
    except OSError as error:
        raise OSError(f"Cleanup stopped after deleting {deleted} frames: {error}") from error
    print(f"Deleted {deleted} frame files; preserved videos, audio, scenes and metadata.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--run", help="Exact build directory name; inspect its frames without deleting.")
    selection.add_argument("--all", action="store_true", help="Inspect eligible completed builds.")
    parser.add_argument("--apply", action="store_true", help="Delete only selected rendered frame files.")
    parser.add_argument("--confirm", help="Repeat the run name, or use the bulk dry-run token.")
    args = parser.parse_args(argv)
    if args.apply and not (args.all and args.confirm or args.run and args.confirm == args.run):
        parser.error("--apply requires --run NAME --confirm NAME or --all --confirm TOKEN")
    if args.confirm and not args.apply:
        parser.error("--confirm requires --apply")
    try:
        if args.all:
            clean_all(BUILDS, apply=args.apply, confirm=args.confirm)
        elif args.run:
            clean_frames(selected_run(BUILDS, args.run), apply=args.apply)
        else:
            runs = inventory(BUILDS)
            print("Build                                      Total GiB  Frame GiB  Frames")
            for name, total, frames, count in runs:
                print(f"{name:42} {total / 1024**3:9.3f} {frames / 1024**3:10.3f} {count:7}")
            print(f"Total: {sum(item[1] for item in runs) / 1024**3:.3f} GiB")
            print("Frame totals are not eligibility checks. Nothing was deleted.")
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
