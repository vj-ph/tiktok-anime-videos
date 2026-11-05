"""Audit or recover interrupted shared-frame production without changing frozen sources."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import json
import math
from pathlib import Path
import re
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
RECOVERY = "frame_recovery"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_files(root, files):
    from prepare_audio import sha256_file

    for name, digest in files.items():
        path = root / name
        if not path.is_file() or sha256_file(path) != digest:
            raise ValueError(f"Recovery input/checkpoint changed: {path}")


def ensure_stopped(build):
    import psutil

    own = psutil.Process()
    excluded = {own.pid, *(p.pid for p in own.parents())}
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if process.pid in excluded:
                continue
            command = process.info["cmdline"] or []
            targets_build = any(str(build).casefold() == arg.casefold() for arg in command)
            if "--build" in command:
                target = Path(command[command.index("--build") + 1])
                targets_build |= (Path(process.cwd()) / target).resolve() == build
            if (targets_build
                    and any(Path(arg).name in (
                        "pipeline.py", "long_speaking_preview_scene.py", Path(__file__).name)
                            for arg in command)):
                raise ValueError(f"Build is still in use by process {process.pid}; stop it first.")
        except (psutil.NoSuchProcess, psutil.AccessDenied, IndexError):
            continue


@contextmanager
def recovery_lock(build):
    folder = build / RECOVERY
    folder.mkdir(exist_ok=True)
    with (folder / "run.lock").open("a+b") as lock:
        try:
            lock.seek(0)
            if not lock.read(1):
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError("Another recovery runner holds this build's lock.") from error
        yield


def validate_build(build):
    from long_speaking_preview import SOURCES, load_preview, native_plan
    from prepare_audio import sha256_file

    state = read(build / "production_state.json")
    spec, stages = state["spec"], state["stages"]
    episode = spec["episode"]
    if (episode.get("template") != "long_speaking_production" or episode.get("render") != {
            "motion_step": 2, "native_scale": 1.0, "samples": 8, "native_source": "youtube"}):
        raise ValueError("Recovery supports only the approved shared-frame production route.")
    if set(spec["code_sha256"]) != set(SOURCES):
        raise ValueError("Recovery requires the complete frozen generation sources.")
    verify_files(ROOT, spec["code_sha256"])
    verify_files(build / "source_export", spec["code_sha256"])
    verify_files(Path(), spec["asset_sha256"])
    for stage, required in (
            ("audio_reuse", {"dialogue.wav", "timeline.json", "word_alignment.json", "audio_reuse.json",
                             "speech_asr_check.json", "auditory_review_flags.json", "subtitles.srt"}),
            ("scene", {"preview.blend", "scene_checks.json"})):
        if not required.issubset(stages.get(stage, {})):
            raise ValueError(f"Recovery requires a completed {stage} checkpoint.")
        verify_files(build, stages[stage])
    if read(build / "episode.json") != episode:
        raise ValueError("Recorded episode differs from its frozen spec.")
    candidates = []
    for name in spec["asset_sha256"]:
        path = Path(name)
        if path.suffix == ".json" and path.parent == ROOT / "episodes":
            raw = read(path)
            if raw.get("id") == episode["id"] and raw.get("template") == episode["template"]:
                candidates.append(path)
    if len(candidates) != 1:
        raise ValueError("Cannot identify the original authored episode from the frozen inputs.")
    resolved, storyboard = load_preview(candidates[0], "production")
    resolved["render_device"] = episode["render_device"]
    if resolved != episode or read(build / "storyboard_episode.json") != storyboard:
        raise ValueError("Resolved episode/storyboard differs from the original build.")
    timeline = read(build / "timeline.json")
    plan = read(build / "native_plan.json")
    if not plan or plan != native_plan(episode, storyboard, timeline):
        raise ValueError("Native plan differs from the original measured timeline.")
    names = [p["file"] for p in plan]
    if (len(set(names)) != len(names)
            or any(p["file"] != f"native/youtube_{p['frame']:05d}.png" for p in plan)):
        raise ValueError("Native plan contains duplicate or unsafe frame paths.")
    protected = {name: sha256_file(build / name) for name in (
        "episode.json", "storyboard_episode.json", "native_plan.json")}
    for stage in ("audio_reuse", "scene"):
        protected.update(stages[stage])
    return state, plan, protected, candidates[0]


def receipt_path(build, item):
    return build / RECOVERY / "receipts" / (Path(item["file"]).stem + ".json")


def validate_receipt(item, receipt, digest):
    if (any(receipt.get(key) != value for key, value in item.items())
            or receipt.get("sha256") != digest or not receipt.get("head_bounds")
            or any(not h["in_front"] or min(h["bounds"]) <= .05 or max(h["bounds"]) >= .95
                   for h in receipt["head_bounds"])):
        raise ValueError(f"Recovery frame receipt differs: {item['file']}")


def inventory(build, plan, manifest=None):
    from PIL import Image
    from prepare_audio import sha256_file

    logs = [*build.glob("frames_*.log"), *(build / RECOVERY).glob("attempt_*/worker_*.log")]
    logged = set()
    for path in logs:
        text = path.read_text(encoding="utf-8", errors="replace")
        for saved in re.findall(r"Saved: ['\"](.+?\.png)['\"]", text):
            logged.add(Path(saved).resolve())
    pinned = manifest["initial_frames_sha256"] if manifest else {}
    found, missing = {}, []
    for item in plan:
        path = build / item["file"]
        if not path.exists():
            if item["file"] in pinned or receipt_path(build, item).exists():
                raise ValueError(f"A previously verified frame is missing: {item['file']}")
            missing.append(item)
            continue
        try:
            with Image.open(path) as image:
                if image.format != "PNG" or list(image.size) != item["size"]:
                    raise ValueError("Wrong format or dimensions")
                image.verify()
            with Image.open(path) as image:
                image.load()
        except (OSError, ValueError, SyntaxError) as error:
            raise ValueError(f"Invalid saved PNG; left untouched: {item['file']}") from error
        digest = sha256_file(path)
        journal = receipt_path(build, item)
        if journal.exists():
            validate_receipt(item, read(journal), digest)
        elif path.resolve() not in logged:
            raise ValueError(f"Saved PNG lacks completed-save evidence: {item['file']}")
        if item["file"] in pinned and pinned[item["file"]] != digest:
            raise ValueError(f"Previously verified PNG changed: {item['file']}")
        found[item["file"]] = digest
    unexpected = {p.resolve() for p in (build / "native").glob("*.png")} - {
        (build / item["file"]).resolve() for item in plan}
    if unexpected:
        raise ValueError("Native folder contains PNGs outside the frozen plan.")
    return found, missing, {str(p.relative_to(build)): sha256_file(p) for p in logs}


def audit(build):
    from prepare_audio import sha256_file

    ensure_stopped(build)
    state, plan, protected, episode_path = validate_build(build)
    manifest_path = build / RECOVERY / "manifest.json"
    manifest = read(manifest_path) if manifest_path.exists() else None
    if manifest:
        if (manifest["spec"] != state["spec"] or manifest["protected_sha256"] != protected
                or manifest["runner_sha256"] != sha256_file(Path(__file__))):
            raise ValueError("Recovery settings/code changed; preserve this recovery and investigate.")
        verify_files(build, manifest["original_logs_sha256"])
        verify_files(build / RECOVERY, {"runner.py": manifest["runner_sha256"]})
    elif "frames" in state["stages"]:
        raise ValueError("Frames already have a checkpoint; use the ordinary pipeline command.")
    found, missing, logs = inventory(build, plan, manifest)
    print(f"Verified {len(found)}/{len(plan)} PNGs; {len(missing)} need rendering.", flush=True)
    return state, plan, protected, episode_path, manifest, found, logs


def worker_command(build, attempt, index, jobs):
    from runtime_config import tool_path

    return [tool_path("blender"), "-b", build / "preview.blend", "--disable-autoexec", "-t", "4",
            "--python-exit-code", "1", "--python", Path(__file__).resolve(), "--",
            "--build", build, "--native-worker", "--attempt", attempt,
            "--worker", str(index), "--jobs", str(jobs)]


def native_worker(build, attempt, index, jobs):
    import bpy
    from long_speaking_preview_scene import actors_from_scene, head_bounds, roles
    from prepare_audio import atomic_json, sha256_file
    from runtime_config import configure_cycles

    manifest = read(build / RECOVERY / "manifest.json")
    verify_files(ROOT, manifest["spec"]["code_sha256"])
    verify_files(build, manifest["protected_sha256"])
    if sha256_file(Path(__file__)) != manifest["runner_sha256"]:
        raise ValueError("Recovery runner changed before worker startup.")
    episode = manifest["spec"]["episode"]
    scene = bpy.context.scene
    configure_cycles(bpy, episode["render_device"])
    scene.cycles.samples = episode["render"]["samples"]
    scene.cycles.use_denoising = True
    timeline = read(build / "timeline.json")
    if (scene.render.engine != "CYCLES" or scene.render.fps != timeline["fps"]
            or (scene.frame_start, scene.frame_end) != (1, timeline["total_frames"])
            or scene.render.resolution_percentage != 100
            or scene.render.image_settings.file_format != "PNG" or scene.render.use_sequencer):
        raise ValueError("Saved scene render/frame settings differ from the frozen build.")
    plan = read(build / "native_plan.json")
    count = math.ceil(len(plan) / jobs)
    tasks = plan[index * count:(index + 1) * count]
    pinned = read(attempt / "inventory.json")
    actors = actors_from_scene()
    prefs = bpy.context.preferences.addons["cycles"].preferences
    atomic_json(attempt / f"settings_{index}.json", {
        "samples": scene.cycles.samples, "denoising": scene.cycles.use_denoising,
        "device": scene.cycles.device, "backend": prefs.compute_device_type,
    })
    for position, item in enumerate(tasks):
        path, journal = build / item["file"], receipt_path(build, item)
        if journal.exists():
            validate_receipt(item, read(journal), sha256_file(path))
            continue
        existing = item["file"] in pinned
        if existing:
            verify_files(build, {item["file"]: pinned[item["file"]]})
        elif path.exists():
            raise ValueError(f"Unverified frame appeared during recovery: {path}")
        scene.frame_set(item["frame"] + 1)
        scene.camera = scene.objects[f"Preview {item['format']} {item['camera']}"]
        scene.render.resolution_x, scene.render.resolution_y = item["size"]
        bpy.context.view_layer.update()
        heads = head_bounds(scene, scene.camera, [actors[name] for name in roles(item["camera"])])
        receipt = {**item, "head_bounds": heads}
        validate_receipt(item, {**receipt, "sha256": ""}, "")
        if not existing:
            path.parent.mkdir(exist_ok=True)
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
        receipt.update(sha256=sha256_file(path), recovery_origin="existing" if existing else "rendered")
        atomic_json(journal, receipt)
        if position % 20 == 0:
            print(f"Recovery worker {index}: {position + 1}/{len(tasks)} checked", flush=True)
    print(f"Recovery worker {index} complete.", flush=True)


def commit_frames(build, state, plan):
    from prepare_audio import atomic_json, sha256_file

    receipts = [read(receipt_path(build, item)) for item in plan]
    for item, receipt in zip(plan, receipts):
        validate_receipt(item, receipt, sha256_file(build / item["file"]))
    current = read(build / "production_state.json")
    if current != state:
        raise ValueError("Production state changed during recovery.")
    atomic_json(build / "native_checks.json", receipts)
    current["stages"]["frames"] = {
        name: sha256_file(build / name) for name in ["native_checks.json", *[p["file"] for p in plan]]}
    atomic_json(build / "production_state.json", current)


def export(build, state, episode_path, jobs):
    from long_speaking_preview import build_preview

    spec = state["spec"]
    build_preview(episode_path, build, jobs=jobs, profile="production",
                  reuse_audio=spec["audio_reuse"]["source"],
                  reuse_scene=spec.get("scene_reuse", {}).get("source"),
                  render_device=spec["episode"]["render_device"])


def execute(build, jobs, until):
    from generation_runtime import GenerationRun, cancel_processes, run_process, stage_completed
    from prepare_audio import atomic_json, sha256_file

    with recovery_lock(build), GenerationRun():
        state, plan, protected, episode_path, manifest, found, logs = audit(build)
        folder = build / RECOVERY
        if not manifest:
            if read(build / "production_state.json") != state:
                raise ValueError("Production checkpoint changed.")
            shutil.copy2(Path(__file__), folder / "runner.py")
            manifest = {
                "spec": state["spec"], "protected_sha256": protected,
                "initial_state": state, "original_logs_sha256": logs,
                "initial_frames_sha256": found, "runner_sha256": sha256_file(Path(__file__)),
                "policy": "Verify and retain complete logged PNGs; recompute head bounds without "
                          "rerendering them. Journal every recovered/new frame. No bake or TTS.",
            }
            atomic_json(folder / "manifest.json", manifest)
        (folder / "receipts").mkdir(exist_ok=True)
        attempt = folder / ("attempt_" + uuid.uuid4().hex)
        attempt.mkdir()
        atomic_json(attempt / "inventory.json", found)
        needs_receipts = any(not receipt_path(build, item).exists() for item in plan)
        if needs_receipts:
            def work(index):
                with (attempt / f"worker_{index}.log").open("w", encoding="utf-8") as log:
                    result = run_process(worker_command(build, attempt, index, jobs), cwd=ROOT,
                                         stdout=log, stderr=-2)
                if result.returncode:
                    raise RuntimeError(f"Recovery worker {index} failed; see {attempt}.")

            pool = ThreadPoolExecutor(max_workers=jobs)
            try:
                futures = [pool.submit(work, index) for index in range(jobs)]
                for future in as_completed(futures):
                    future.result()
            except BaseException:
                cancel_processes()
                raise
            finally:
                pool.shutdown(wait=True, cancel_futures=True)
        verify_files(build, protected)
        verify_files(ROOT, state["spec"]["code_sha256"])
        verify_files(Path(), state["spec"]["asset_sha256"])
        verify_files(ROOT, {Path(__file__).name: manifest["runner_sha256"]})
        verify_files(build, found)
        final, missing, _ = inventory(build, plan, manifest)
        if missing:
            raise ValueError("Recovery did not complete the native plan.")
        commit_frames(build, state, plan)
        atomic_json(build / "frame_recovery.json", {
            "status": "verified_frames", "runner_sha256": manifest["runner_sha256"],
            "manifest_sha256": sha256_file(folder / "manifest.json"),
            "original_spec_unchanged": True, "initial_frames_preserved": len(manifest["initial_frames_sha256"]),
            "total_frames": len(final), "new_frames_since_initial": len(final) - len(manifest["initial_frames_sha256"]),
            "new_bake": False, "new_tts": False,
            "receipt_sha256": sha256_file(build / "native_checks.json"),
        })
        stage_completed("frames", force=True)
        print(f"Frame checkpoint complete: {len(final)} images; original PNGs unchanged.", flush=True)
        if until == "export":
            export(build, state, episode_path, jobs)


def main():
    from build_paths import build_directory
    from runtime_config import RENDER_JOBS

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=RENDER_JOBS, default=2)
    parser.add_argument("--execute", action="store_true", help="Render missing frames; default is read-only audit.")
    parser.add_argument("--until", choices=("frames", "export"), default="export")
    parser.add_argument("--native-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--attempt", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--worker", type=int, default=0, help=argparse.SUPPRESS)
    native = "--native-worker" in sys.argv and "--" in sys.argv
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if native else None)
    try:
        build = build_directory(args.build)
        if native:
            native_worker(build, args.attempt, args.worker, args.jobs)
        elif args.execute:
            execute(build, args.jobs, args.until)
        else:
            audit(build)
            print("Audit only: nothing modified or started. Add --execute to recover.", flush=True)
    except KeyboardInterrupt:
        parser.exit(130, "Recovery cancelled; saved PNGs and per-frame receipts are preserved.\n")
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
