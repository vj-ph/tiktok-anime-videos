"""Native speech-led performance for dual-format previews and production."""

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import bpy

from entrance import entrance_plan
from listening_scene import freeze_source_animation
from long_speaking_scene import correct_hair, head_bounds, hair_drop
from prepare_audio import atomic_json, sha256_file
from produce_v4 import animate
from runtime_config import configure_cycles
from scene_direction import configure_cameras, room_design
from studio_characters import StudioCharacter


def actors_from_scene():
    return {name: StudioCharacter.from_scene(name)
            for name in ("candidate_a", "candidate_b", "examiner", "observer")}


def roles(camera):
    return (["candidate_a", "candidate_b", "examiner", "observer"] if camera == "wide" else
            ["candidate_a", "candidate_b"] if camera == "candidates" else [camera])


def bake(build, episode, storyboard, timeline, plan):
    scene = bpy.context.scene
    scene.frame_set(storyboard["scene"]["contact_pose_frame"])
    freeze_source_animation(scene)
    actors = actors_from_scene()
    for actor in actors.values():
        actor.restore_native_drivers()
        correct_hair(actor)
    room_design(scene, storyboard)
    for index, actor in enumerate(actors.values()):
        animate(actor, timeline, index, episode, episode["render"]["motion_step"], entrance_plan(episode, timeline))
        print(f"Baked {actor.name}", flush=True)
    original = configure_cameras(scene)
    cameras = {}
    for item in plan:
        name = f"Preview {item['format']} {item['camera']}"
        if name not in cameras:
            camera = original[item["camera"]].copy()
            camera.data = camera.data.copy()
            camera.name = name
            scene.collection.objects.link(camera)
            cameras[name] = camera
    scene.timeline_markers.clear()
    scene.render.engine = "CYCLES"
    configure_cycles(bpy, episode.get("render_device", "CPU"))
    scene.cycles.samples = episode["render"]["samples"]
    scene.cycles.use_denoising = True
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.use_sequencer = False
    scene.render.use_persistent_data = True
    scene.render.fps = timeline["fps"]
    scene.frame_start, scene.frame_end = 1, timeline["total_frames"]
    for item in plan:
        scene.frame_set(item["frame"] + 1)
        scene.render.resolution_x, scene.render.resolution_y = item["size"]
        camera = cameras[f"Preview {item['format']} {item['camera']}"]
        scene.camera = camera
        visible = [actors[name] for name in roles(item["camera"])]
        for attempt in range(50):
            bounds = head_bounds(scene, camera, visible)
            if all(h["in_front"] and min(h["bounds"]) > .05 and max(h["bounds"]) < .95 for h in bounds):
                break
            camera.data.lens *= .95
            bpy.context.view_layer.update()
        else:
            raise ValueError("Cannot frame animated heads and hair.")
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
        if name != "observer" and motion[name]["jaw_range"] < .01:
            raise ValueError(f"{name}: no measured lip-sync animation.")
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(build / "preview.blend"), compress=True)
    atomic_json(build / "scene_checks.json", {
        "motion": motion, "hair_hangs_down_all_sampled_frames": True,
        "all_planned_head_and_hair_bounds_fit": True,
        "camera_lenses": {name: camera.data.lens for name, camera in cameras.items()},
        "source_scene_saved": False, "preview_scene_sha256": sha256_file(build / "preview.blend"),
    })


def render(build, episode, plan, worker, jobs):
    scene = bpy.context.scene
    configure_cycles(bpy, episode.get("render_device", "CPU"))
    actors = actors_from_scene()
    count = math.ceil(len(plan) / jobs)
    tasks = plan[worker * count:(worker + 1) * count]
    checks = []
    for index, item in enumerate(tasks):
        scene.frame_set(item["frame"] + 1)
        scene.camera = scene.objects[f"Preview {item['format']} {item['camera']}"]
        scene.render.resolution_x, scene.render.resolution_y = item["size"]
        bpy.context.view_layer.update()
        heads = head_bounds(scene, scene.camera, [actors[name] for name in roles(item["camera"])])
        if any(not h["in_front"] or min(h["bounds"]) <= .05 or max(h["bounds"]) >= .95 for h in heads):
            raise ValueError("Rendered frame fails head/hair clearance.")
        path = build / item["file"]
        path.parent.mkdir(exist_ok=True)
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        checks.append({**item, "head_bounds": heads, "sha256": sha256_file(path)})
        if index % 20 == 0:
            print(f"Worker {worker}: {index + 1}/{len(tasks)}", flush=True)
    atomic_json(build / f"native_checks_{worker}.json", checks)


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
