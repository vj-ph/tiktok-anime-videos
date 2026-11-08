"""Native A2 preview performance using the reviewed three-person room."""

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import bpy

from a2_speaking_contacts import setup_scene, visible_head_bounds
from b2_speaking import shared_head_fits
from entrance import entrance_plan
from long_speaking_scene import hair_drop
from prepare_audio import atomic_json, sha256_file
from produce_v4 import animate
from runtime_config import configure_cycles
from studio_characters import StudioCharacter


def bake(build, episode, storyboard, timeline, plan):
    scene = bpy.context.scene
    actors, cameras, cast, hair = setup_scene(storyboard)
    for name, camera in cameras.items():
        camera.name = f"A2 preview youtube {name}"
    for index, actor in enumerate(actors.values()):
        animate(actor, timeline, index, episode, episode["render"]["motion_step"],
                entrance_plan(episode, timeline))
        print(f"Baked A2 {actor.name}", flush=True)
    configure_cycles(bpy, episode.get("render_device", "CPU"))
    scene.cycles.samples = episode["render"]["samples"]
    scene.render.fps = timeline["fps"]
    scene.frame_start, scene.frame_end = 1, timeline["total_frames"]
    for item in plan:
        scene.frame_set(item["frame"] + 1)
        scene.render.resolution_x, scene.render.resolution_y = item["size"]
        camera = cameras[item["camera"]]
        scene.camera = camera
        visible = list(actors.values()) if item["camera"] == "wide" else [actors[item["camera"]]]
        for _ in range(50):
            if all(shared_head_fits(head) for head in visible_head_bounds(scene, camera, visible)):
                break
            camera.data.lens *= .95
            bpy.context.view_layer.update()
        else:
            raise ValueError("Cannot frame animated A2 heads/hair inside the portrait crop.")
    motion = {}
    for name, actor in actors.items():
        jaws, heads = [], []
        for frame in range(1, timeline["total_frames"] + 1, episode["render"]["motion_step"]):
            scene.frame_set(frame)
            jaws.append(float(actor.bones[actor.jaw_name].rotation_euler.x))
            heads.append(float(actor.head.rotation_euler.y))
            if actor.kind == "rain" and hair_drop(actor) < .15:
                raise ValueError(f"{name}: animated ponytail rises.")
        motion[name] = {"jaw_range": max(jaws) - min(jaws), "head_yaw_range": max(heads) - min(heads)}
        if any(turn["speaker"] == name for turn in timeline["turns"]) and motion[name]["jaw_range"] < .01:
            raise ValueError(f"{name}: missing measured mouth-cue animation.")
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(build / "preview.blend"), compress=True)
    atomic_json(build / "scene_checks.json", {
        "motion": motion, "cast": cast, "hair": hair,
        "candidate_examiner_angle_degrees": 180,
        "all_planned_head_and_hair_bounds_fit": True,
        "hair_hangs_down_all_sampled_frames": True, "baked_frames": timeline["total_frames"],
        "checked_native_frames": len(plan),
        "camera_lenses": {name: camera.data.lens for name, camera in cameras.items()},
        "source_scene_saved": False, "preview_scene_sha256": sha256_file(build / "preview.blend"),
    })


def render(build, episode, plan, worker, jobs):
    scene = bpy.context.scene
    configure_cycles(bpy, episode.get("render_device", "CPU"))
    scene.cycles.samples = episode["render"]["samples"]
    actors = {name: StudioCharacter.from_scene(name) for name in ("candidate_a", "examiner", "observer")}
    size = math.ceil(len(plan) / jobs)
    tasks = plan[worker * size:(worker + 1) * size]
    receipt = build / f"native_checks_{worker}.json"
    prior = json.loads(receipt.read_text(encoding="utf-8")) if receipt.is_file() else []
    cached = {record["file"]: record for record in prior}
    scene_digest = sha256_file(build / "preview.blend")
    checks = []
    for index, item in enumerate(tasks):
        path = build / item["file"]
        record = cached.get(item["file"], {})
        if (record.get("scene_sha256") == scene_digest
                and all(record.get(key) == value for key, value in item.items())
                and record.get("render_settings") == {
                    "samples": episode["render"]["samples"], "device": episode.get("render_device", "CPU")}
                and path.is_file() and sha256_file(path) == record.get("sha256")):
            checks.append(record)
            continue
        scene.frame_set(item["frame"] + 1)
        scene.camera = scene.objects[f"A2 preview youtube {item['camera']}"]
        scene.render.resolution_x, scene.render.resolution_y = item["size"]
        bpy.context.view_layer.update()
        visible = list(actors.values()) if item["camera"] == "wide" else [actors[item["camera"]]]
        heads = visible_head_bounds(scene, scene.camera, visible)
        if not all(shared_head_fits(head) for head in heads):
            raise ValueError("A2 rendered frame fails head/hair clearance.")
        path.parent.mkdir(exist_ok=True)
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        checks.append({**item, "head_bounds": heads, "sha256": sha256_file(path),
                       "scene_sha256": scene_digest,
                       "render_settings": {"samples": episode["render"]["samples"],
                                           "device": episode.get("render_device", "CPU")}})
        cached[item["file"]] = checks[-1]
        atomic_json(receipt, list(cached.values()))
        if index % 20 == 0:
            print(f"A2 worker {worker}: {index + 1}/{len(tasks)}", flush=True)
    atomic_json(receipt, checks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--bake", action="store_true")
    parser.add_argument("--worker", type=int, default=0)
    parser.add_argument("--jobs", type=int, default=1)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    build = args.build.resolve()
    episode = json.loads((build / "episode.json").read_text(encoding="utf-8"))
    storyboard = json.loads((build / "storyboard_episode.json").read_text(encoding="utf-8"))
    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    plan = json.loads((build / "native_plan.json").read_text(encoding="utf-8"))
    if args.bake:
        bake(build, episode, storyboard, timeline, plan)
    else:
        render(build, episode, plan, args.worker, args.jobs)
