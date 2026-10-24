#!/usr/bin/env python3
"""Compare worker counts using an unchanged baked scene and isolated outputs."""

import argparse
from contextlib import ExitStack
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from generation_runtime import (forget_process, generation_job, stage_completed,
                                start_process, stop_processes)
from episode_config import PROFILES
from prepare_audio import atomic_json, sha256_file
from runtime_config import RENDER_DEVICES, RENDER_JOBS, configure_cycles, tool_path


def select_frames(total, step, count):
    available = list(range(1, total + 1, step))
    if count < 2 or count > len(available):
        raise ValueError("Frame count must fit the scene and include at least two frames.")
    return [available[round(i * (len(available) - 1) / (count - 1))] for i in range(count)]


def summarize_trial(records, started, finished, samples):
    warm = [frame for record in records for frame in record["frames"][1:]]
    if not warm or any(len(record["frames"]) < 2 for record in records):
        raise ValueError("Each worker needs at least one cold and one warm frame.")
    warm_start = min(frame["started"] for frame in warm)
    warm_stop = max(frame["finished"] for frame in warm)
    warm_samples = [sample for sample in samples if warm_start <= sample["at"] <= warm_stop]
    metrics = {}
    for key in ("cpu_percent", "gpu_busiest_engine_percent", "gpu_owned_engine_activity_index",
                "worker_resident_bytes", "system_available_bytes",
                "gpu_dedicated_bytes", "gpu_shared_bytes"):
        values = [sample[key] for sample in warm_samples if sample.get(key) is not None]
        metrics[key] = {"mean": statistics.mean(values), "peak": max(values),
                        "minimum": min(values)} if values else None
    return {
        "cold_start_seconds_until_all_first_frames": max(r["frames"][0]["finished"] for r in records) - started,
        "end_to_end_seconds": finished - started,
        "end_to_end_frames_per_minute": sum(len(r["frames"]) for r in records) * 60 / (finished - started),
        "warm_frames": len(warm), "warm_elapsed_seconds": warm_stop - warm_start,
        "warm_frames_per_minute": len(warm) * 60 / (warm_stop - warm_start),
        "warm_frame_seconds_median": statistics.median(f["finished"] - f["started"] for f in warm),
        "warm_metrics": metrics,
    }


def recommendation(trials, jobs, repeats):
    candidates = []
    for count in jobs:
        matches = [trial for trial in trials if trial["jobs"] == count]
        if len(matches) == repeats and all(trial.get("verified") for trial in matches):
            rates = [trial["summary"]["warm_frames_per_minute"] for trial in matches]
            candidates.append({"jobs": count, "median_warm_frames_per_minute": statistics.median(rates),
                               "minimum_warm_frames_per_minute": min(rates),
                               "maximum_warm_frames_per_minute": max(rates)})
    candidates.sort(key=lambda item: (-item["median_warm_frames_per_minute"], item["jobs"]))
    return {"jobs": candidates[0]["jobs"] if candidates else None, "candidates": candidates,
            "policy": "Highest median aggregate warm throughput; all trials must pass. Defaults unchanged."}


def render_worker(args):
    import bpy

    configure_cycles(bpy, args.render_device)
    scene = bpy.context.scene
    scene.render.use_persistent_data = True
    settings = {"engine": scene.render.engine, "width": scene.render.resolution_x,
                "height": scene.render.resolution_y, "resolution_percentage": scene.render.resolution_percentage,
                "samples": scene.cycles.samples, "denoising": scene.cycles.use_denoising,
                "threads": scene.render.threads, "threads_mode": scene.render.threads_mode,
                "adaptive_sampling": scene.cycles.use_adaptive_sampling,
                "denoiser": scene.cycles.denoiser,
                "denoising_use_gpu": getattr(scene.cycles, "denoising_use_gpu", None)}
    args.output.mkdir(parents=True, exist_ok=True)
    frames = []
    for frame in args.frames:
        started = time.monotonic()
        scene.frame_set(frame)
        updated = time.monotonic()
        scene.render.filepath = str(args.output / f"frame_{frame:04d}.png")
        bpy.ops.render.render(write_still=True)
        frames.append({"frame": frame, "started": started, "finished": time.monotonic(),
                       "scene_update_seconds": updated - started})
    atomic_json(args.output / "measurements.json", {"settings": settings, "frames": frames})


def check_limits(started, timeout_seconds, min_free_gib):
    import psutil

    if time.monotonic() - started > timeout_seconds:
        raise RuntimeError("Trial time limit exceeded; owned workers stopped.")
    if psutil.virtual_memory().available < min_free_gib * 2 ** 30:
        raise RuntimeError("Free RAM fell below the safety reserve; owned workers stopped.")


def run_trial(source, output, frames, jobs, threads, backend, *,
              min_free_gib=4.0, timeout_seconds=600):
    from PIL import Image
    from render import valid_frame
    from resource_metrics import ResourceSampler

    manifest = json.loads((source / "scene_manifest.json").read_text(encoding="utf-8"))
    processes, folders, samples = [], [], []
    sampler = None
    started = time.monotonic()
    try:
        with ExitStack() as stack:
            for index in range(jobs):
                check_limits(started, timeout_seconds, min_free_gib)
                folder = output / f"worker_{index}"
                folder.mkdir(parents=True)
                folders.append(folder)
                log = stack.enter_context((folder / "render.log").open("w", encoding="utf-8"))
                command = [tool_path("blender"), "-b", "--disable-autoexec", source / "studio.blend",
                           "-t", threads, "--python-exit-code", 1, "--python", Path(__file__).resolve(),
                           "--", "--worker", "--output", folder, "--render-device", backend,
                           "--frames", ",".join(map(str, frames[index::jobs]))]
                processes.append(start_process(command, stdout=log, stderr=subprocess.STDOUT))
            sampler = ResourceSampler([process.pid for process in processes])
            next_sample = started + 1
            while any(process.poll() is None for process in processes):
                check_limits(started, timeout_seconds, min_free_gib)
                if any(process.poll() not in (None, 0) for process in processes):
                    raise RuntimeError("Benchmark worker failed; inspect the isolated render logs.")
                now = time.monotonic()
                if now >= next_sample:
                    samples.append({"at": now, **sampler.sample()})
                    next_sample = now + 1
                time.sleep(0.1)
            finished = time.monotonic()
            if any(process.returncode for process in processes):
                raise RuntimeError("Benchmark worker failed; inspect the isolated render logs.")
        records = [json.loads((folder / "measurements.json").read_text(encoding="utf-8")) for folder in folders]
        if any(record["settings"] != records[0]["settings"] for record in records):
            raise ValueError("Workers used inconsistent scene settings.")
        settings = records[0]["settings"]
        if ((settings["width"], settings["height"], settings["resolution_percentage"])
                != (manifest["width"], manifest["height"], 100)
                or "samples" in manifest and settings["samples"] != manifest["samples"]
                or settings["engine"] != "CYCLES"
                or settings["threads"] != threads or settings["threads_mode"] != "FIXED"):
            raise ValueError("Worker render settings differ from the requested baked-scene quality.")
        for index, (folder, record) in enumerate(zip(folders, records)):
            if [frame["frame"] for frame in record["frames"]] != frames[index::jobs]:
                raise ValueError("Worker did not render the requested identical workload.")
            for frame in record["frames"]:
                path = folder / f"frame_{frame['frame']:04d}.png"
                if not valid_frame(path, manifest["width"], manifest["height"]):
                    raise ValueError("Benchmark output has an incomplete or wrong-sized PNG.")
                with Image.open(path) as image:
                    image.load()
        return {"jobs": jobs, "verified": True, "scene_settings": records[0]["settings"],
                "summary": summarize_trial(records, started, finished, samples),
                "samples": samples, "workers": records}
    except BaseException:
        stop_processes(processes)
        raise
    finally:
        if sampler is not None:
            sampler.close()
        for process in processes:
            forget_process(process)


@generation_job
def benchmark(source, output, jobs=(1, 2, 4), frame_count=24, repeats=2, threads=4, backend="HIP",
              min_free_gib=4.0, timeout_seconds=600, expected_profile=None):
    source, output = source.resolve(strict=True), output.resolve()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("Benchmark output must be separate from the source build.")
    if output.exists():
        raise ValueError("Use a new, empty benchmark output path.")
    if not jobs or any(job not in RENDER_JOBS for job in jobs) or len(set(jobs)) != len(jobs):
        raise ValueError("Worker counts must be distinct supported values: " + ", ".join(map(str, RENDER_JOBS)))
    if repeats < 1 or threads < 1 or frame_count < 3 * max(jobs):
        raise ValueError("Use positive repeats/threads and at least three frames per largest worker group.")
    if (not math.isfinite(min_free_gib) or min_free_gib <= 0
            or not math.isfinite(timeout_seconds) or timeout_seconds <= 0):
        raise ValueError("Memory reserve and trial timeout must be positive and finite.")
    manifest = json.loads((source / "scene_manifest.json").read_text(encoding="utf-8"))
    timeline = json.loads((source / "timeline.json").read_text(encoding="utf-8"))
    if manifest["timeline"] != timeline:
        raise ValueError("Baked scene and timeline disagree.")
    if expected_profile is not None:
        if expected_profile not in PROFILES or any(
                manifest.get(key) != value for key, value in PROFILES[expected_profile].items()):
            raise ValueError("The baked scene does not match the expected quality profile.")
    frames = select_frames(timeline["total_frames"], manifest["motion_step"], frame_count)
    hashes = {name: sha256_file(source / name) for name in ("studio.blend", "scene_manifest.json", "timeline.json")}
    code_hashes = {name: sha256_file(ROOT / name) for name in
                   ("benchmark_workers.py", "resource_metrics.py", "generation_runtime.py", "runtime_config.py")}
    output.mkdir(parents=True)
    report = {"source": str(source), "source_sha256": hashes, "code_sha256": code_hashes, "frames": frames,
              "render_device": backend, "threads_per_worker": threads, "repeats": repeats,
              "quality": {key: manifest.get(key) for key in ("quality", "width", "height", "samples", "motion_step")},
              "limits": {"min_free_memory_gib": min_free_gib, "trial_timeout_seconds": timeout_seconds},
              "host": {"platform": platform.system(), "machine": platform.machine(), "logical_cpus": os.cpu_count()},
              "gpu_scope": ("Owned-process engine activity index; overlapping sums are NOT physical utilization. "
                            "Allocation totals are not VRAM capacity."
                            if sys.platform == "win32" else
                            "AMD sysfs device-wide counters, including other processes; null if unavailable in WSL."),
              "trials": [], "complete": False}
    try:
        for repeat in range(repeats):
            for count in jobs if repeat % 2 == 0 else tuple(reversed(jobs)):
                print(f"Benchmark: {count} workers, trial {repeat + 1}/{repeats}", flush=True)
                try:
                    trial = run_trial(source, output / f"jobs_{count}_trial_{repeat + 1}",
                                      frames, count, threads, backend,
                                      min_free_gib=min_free_gib, timeout_seconds=timeout_seconds)
                except (ValueError, OSError, RuntimeError) as error:
                    trial = {"jobs": count, "verified": False, "error": str(error)}
                trial["repeat"] = repeat + 1
                report["trials"].append(trial)
                atomic_json(output / "benchmark.json", report)
                if trial["verified"]:
                    print(f"  {trial['summary']['warm_frames_per_minute']:.2f} warm frames/min", flush=True)
                else:
                    print(f"  Unverified: {trial['error']}", flush=True)
        if any(sha256_file(source / name) != digest for name, digest in hashes.items()):
            raise ValueError("Source build changed during benchmarking.")
        if any(sha256_file(ROOT / name) != digest for name, digest in code_hashes.items()):
            raise ValueError("Benchmark code changed during measurement.")
        valid = [trial for trial in report["trials"] if trial["verified"]]
        baseline = valid[0]["scene_settings"] if valid else None
        if any(trial["scene_settings"] != baseline for trial in valid):
            raise ValueError("Scene quality settings changed between configurations.")
        report.update(complete=True, all_trials_verified=all(t["verified"] for t in report["trials"]),
                      recommendation=recommendation(report["trials"], jobs, repeats))
        print(f"Recommended workers: {report['recommendation']['jobs']}; {output / 'benchmark.json'}", flush=True)
        if not report["all_trials_verified"]:
            raise RuntimeError("Some requested configurations could not be verified; see benchmark.json and trial logs.")
        stage_completed("benchmark")
        return report
    finally:
        atomic_json(output / "benchmark.json", report)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, nargs="+", choices=RENDER_JOBS, default=[1, 2, 4])
    parser.add_argument("--frame-count", type=int, default=24)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--min-free-memory-gib", type=float, default=4.0)
    parser.add_argument("--trial-timeout", type=int, default=600)
    parser.add_argument("--expect-profile", choices=tuple(PROFILES))
    parser.add_argument("--render-device", choices=RENDER_DEVICES, default="HIP")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--frames", type=lambda value: [int(frame) for frame in value.split(",")],
                        help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        render_worker(args)
    elif args.build is None:
        parser.error("--build is required")
    else:
        try:
            benchmark(args.build, args.output, args.jobs, args.frame_count,
                      args.repeats, args.threads, args.render_device,
                      args.min_free_memory_gib, args.trial_timeout, args.expect_profile)
        except KeyboardInterrupt:
            parser.exit(130, "Benchmark cancelled; isolated outputs are preserved.\n")
        except (ValueError, OSError, RuntimeError) as error:
            parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
