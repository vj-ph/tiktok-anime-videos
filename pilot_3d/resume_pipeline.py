#!/usr/bin/env python3
"""Resume a verified HIP build with bounded, lower-concurrency crash recovery."""

import argparse
from collections import deque
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from build_paths import build_directory
from generation_runtime import GenerationRun, forget_process, start_process, stop_processes
from pipeline import SOURCES
from prepare_audio import atomic_json, sha256_file
from runtime_config import RENDER_JOBS, qwen_python

ROOT = Path(__file__).resolve().parent


def verified_build(build):
    state = json.loads((build / "pipeline_state.json").read_text(encoding="utf-8"))
    spec = state["spec"]
    if spec["render_device"] != "HIP":
        raise ValueError("This recovery entry point requires an existing HIP build.")
    if set(spec["code_sha256"]) != set(SOURCES) or any(
            sha256_file(ROOT / name) != spec["code_sha256"][name] for name in SOURCES):
        raise ValueError("Pipeline sources changed; recovery cannot bypass the build's source hashes.")
    for stage in ("audio", "alignment", "scene", "scene_checks"):
        outputs = state["stages"].get(stage, {}).get("outputs")
        if not outputs or any(sha256_file(build / name) != digest for name, digest in outputs.items()):
            raise ValueError(f"Missing or changed {stage} checkpoint; recovery requires prepared audio and scene.")
    manifest = json.loads((build / "scene_manifest.json").read_text(encoding="utf-8"))
    checkpoint = json.loads((build / "render_checkpoint.json").read_text(encoding="utf-8"))
    expected = {"scene": manifest, "blend_sha256": sha256_file(build / "studio.blend"),
                "render_device": "HIP"}
    if checkpoint != expected:
        raise ValueError("Frame checkpoint does not match the saved HIP scene; recovery will not discard frames.")
    return spec


def archive_logs(build, target):
    target.mkdir()
    for path in [build / "pipeline_frames.log", *build.glob("render_*.log")]:
        if path.is_file():
            shutil.copy2(path, target / path.name)


def signature(path):
    if not path.is_file():
        return None
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


def recognized_hip_crash(output, build):
    if f"Error: Stage failed (1); see {build / 'pipeline_frames.log'}" not in output:
        return False
    log = (build / "pipeline_frames.log").read_text(encoding="utf-8", errors="replace")
    return ("Unhandled kernel integrator_init_from_camera used for path iteration" in log
            or "EXCEPTION_ACCESS_VIOLATION" in log and "amdhip64" in log)


def run_attempt(command, log):
    process = start_process(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", bufsize=1)
    tail = deque(maxlen=200)
    try:
        with log.open("w", encoding="utf-8") as output:
            for line in process.stdout:
                print(line, end="", flush=True)
                output.write(line)
                output.flush()
                tail.append(line)
        return process.wait(), "".join(tail)
    except BaseException:
        stop_processes([process])
        raise
    finally:
        process.stdout.close()
        forget_process(process)


def resume(build, *, jobs=2, max_retries=2, retry_delay=10):
    if jobs not in RENDER_JOBS or type(max_retries) is not int or not 0 <= max_retries <= 3:
        raise ValueError("Use supported worker counts and 0-3 retries.")
    if not 0 <= retry_delay <= 60:
        raise ValueError("Retry delay must be between 0 and 60 seconds.")
    build = build_directory(build).resolve(strict=True)
    spec = verified_build(build)
    runtime = qwen_python().resolve(strict=True)
    parent = build / "recovery"
    parent.mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="hip_", dir=parent))
    report = {"initial_jobs": jobs, "max_retries": max_retries, "retry_delay_seconds": retry_delay,
              "attempts": [], "complete": False}
    atomic_json(output / "recovery.json", report)
    with GenerationRun(cleanup_python=runtime):
        for attempt in range(max_retries + 1):
            verified_build(build)
            directory = output / f"attempt_{attempt + 1}"
            directory.mkdir()
            archive_logs(build, directory / "before")
            previous = signature(build / "pipeline_frames.log")
            command = [
                runtime, "-X", "utf8", "-u", ROOT / "pipeline.py", "build",
                "--episode", build / "episode.json", "--build", build,
                "--profile", spec["profile"], "--render-device", "HIP",
                "--speech-device", spec["speech_device"], "--jobs", str(jobs), "--until", "export",
            ]
            if "reuse_audio" in spec:
                command += ["--reuse-audio", spec["reuse_audio"]["source"]]
            print(f"HIP recovery attempt {attempt + 1}/{max_retries + 1}: {jobs} worker(s).", flush=True)
            code, tail = run_attempt(command, directory / "pipeline.log")
            archive_logs(build, directory / "after")
            retryable = (code not in (0, 130, 143)
                         and signature(build / "pipeline_frames.log") != previous
                         and recognized_hip_crash(tail, build))
            report["attempts"].append({"jobs": jobs, "exit_code": code,
                                       "recognized_hip_crash": retryable})
            report["complete"] = code == 0
            atomic_json(output / "recovery.json", report)
            if code == 0:
                return build
            if not retryable or attempt == max_retries:
                raise RuntimeError(f"Pipeline exited {code}; checkpoints and logs preserved in {output}. "
                                   "No further automatic retry.")
            jobs = max(1, jobs // 2)
            print(f"Recognized HIP crash; keeping saved frames. Retrying with {jobs} worker(s) "
                  f"after {retry_delay:g}s.", flush=True)
            time.sleep(retry_delay)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=RENDER_JOBS, default=2)
    parser.add_argument("--max-retries", type=int, choices=range(4), default=2)
    parser.add_argument("--retry-delay", type=float, default=10)
    args = parser.parse_args()
    try:
        resume(args.build, jobs=args.jobs, max_retries=args.max_retries, retry_delay=args.retry_delay)
    except KeyboardInterrupt:
        parser.exit(130, "Recovery cancelled; saved frames and checkpoints are preserved.\n")
    except (ValueError, OSError, RuntimeError, KeyError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
