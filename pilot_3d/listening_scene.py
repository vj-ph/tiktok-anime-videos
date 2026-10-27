"""Render a silent, attentive listener and tabletop radio."""

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from listener_motion import listener_offsets


def corners(obj):
    return [obj.matrix_world @ Vector(point) for point in obj.bound_box]


def freeze_source_animation(scene):
    saved = []
    for obj in scene.objects:
        if not obj.animation_data:
            continue
        if obj.animation_data.nla_tracks:
            raise ValueError(f"Unexpected NLA animation on {obj.name}.")
        if obj.animation_data.action:
            bones = ({bone.name: bone.matrix_basis.copy() for bone in obj.pose.bones}
                     if obj.type == "ARMATURE" else {})
            saved.append((obj, obj.matrix_basis.copy(), bones))
    for obj, _, _ in saved:
        obj.animation_data.action = None
    for obj, matrix, bones in saved:
        obj.matrix_basis = matrix
        for name, basis in bones.items():
            obj.pose.bones[name].matrix_basis = basis
    bpy.context.view_layer.update()
    return [obj.name for obj, _, _ in saved]


def bake_listener_animation(scene, rig, count):
    head, chest, eyes = (rig.pose.bones[name] for name in ("FK-Head", "FK-Chest", "TGT-Eyes"))
    eyelids = [rig.pose.bones[f"ACT-Eyelid_Upper.{side}"] for side in ("L", "R")]
    base = {"head": head.rotation_euler.copy(), "chest": chest.rotation_euler.copy(),
            "eyes": eyes.location.copy(), "eyelids": [bone.location.copy() for bone in eyelids]}
    for index in range(count):
        offsets = listener_offsets(index, count)
        head.rotation_euler = base["head"].copy()
        head.rotation_euler.y += offsets["head_yaw"]
        chest.rotation_euler = base["chest"].copy()
        chest.rotation_euler.y += offsets["chest_yaw"]
        eyes.location = base["eyes"].copy()
        eyes.location.x += offsets["eye_horizontal"]
        for eyelid, position in zip(eyelids, base["eyelids"]):
            eyelid.location = position.copy()
            eyelid.location.y -= offsets["blink"]
        for bone, channel in ((head, "rotation_euler"), (chest, "rotation_euler"),
                              (eyes, "location"), *((bone, "location") for bone in eyelids)):
            bone.keyframe_insert(data_path=channel, frame=index + 1)
    for curve in rig.animation_data.action.fcurves:
        for key in curve.keyframe_points:
            key.interpolation = "LINEAR"
    scene.frame_set(1)
    return base


def add_playback_device(scene, camera, model, x, y, rig, count, base):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(model))
    imported = set(bpy.data.objects) - before
    roots = [obj for obj in imported if obj.parent not in imported]
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if len(roots) != 1 or not meshes:
        raise ValueError("Expected one radio model root and its meshes.")
    device = roots[0]
    device.name = "Listening radio"
    device.scale *= 0.76
    bpy.context.view_layer.update()
    points = [point for mesh in meshes for point in corners(mesh)]
    table = corners(scene.objects["Exam table"])
    tabletop = max(p.z for p in table)
    device.location += Vector((x - (min(p.x for p in points) + max(p.x for p in points)) / 2,
                               y - (min(p.y for p in points) + max(p.y for p in points)) / 2,
                               tabletop - min(p.z for p in points)))
    bpy.context.view_layer.update()
    points = [point for mesh in meshes for point in corners(mesh)]
    low = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    high = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    if (low.x < min(p.x for p in table) or high.x > max(p.x for p in table)
            or low.y < min(p.y for p in table) or high.y > max(p.y for p in table)):
        raise ValueError("Playback device overhangs the tabletop.")
    projected = [world_to_camera_view(scene, camera, p) for p in points]
    bounds = [min(p.x for p in projected) * 792 - 36,
              min(1 - p.y for p in projected) * 1408 - 120,
              max(p.x for p in projected) * 792 - 36,
              max(1 - p.y for p in projected) * 1408 - 120]
    if not (30 <= bounds[0] < bounds[2] <= 690 and 755 <= bounds[1] < bounds[3] <= 1230):
        raise ValueError(f"Playback device is not visible below the answer cards: {bounds}")
    names = [name for name in rig.pose.bones.keys()
             if name.startswith(("FK-Index3.", "FK-Middle3.", "FK-Finger_Index3.", "FK-Finger_Middle3."))]
    if len(names) != 4:
        raise ValueError("Expected four candidate fingertip controls.")
    clearance = float("inf")
    yaw, pitch, eye_vertical, blink = [], [], [], []
    for index in range(count):
        scene.frame_set(index + 1)
        head = rig.pose.bones["FK-Head"]
        yaw.append(head.rotation_euler.y)
        pitch.append(head.rotation_euler.x)
        eye_vertical.append(rig.pose.bones["TGT-Eyes"].location.z)
        blink.append(rig.pose.bones["ACT-Eyelid_Upper.L"].location.y)
        for name in names:
            point = rig.matrix_world @ rig.pose.bones[name].tail
            clearance = min(clearance, math.sqrt(sum(
                max(low[i] - point[i], 0, point[i] - high[i]) ** 2 for i in range(3))))
    if clearance < .012:
        raise ValueError(f"Playback device intersects a hand: {clearance:.4f}m.")
    if (max(abs(value - base["head"].x) for value in pitch) > 1e-5
            or max(abs(value - base["eyes"].z) for value in eye_vertical) > 1e-5
            or max(yaw) - min(yaw) < .03 or max(blink) - min(blink) < .03):
        raise ValueError("Listener animation does not preserve the alert pose and intended movement.")
    return {"tabletop_z_m": tabletop, "device_bounds_m": [list(low), list(high)],
            "support_error_m": abs(low.z - tabletop), "projected_bounds_px": bounds,
            "minimum_fingertip_clearance_m": clearance, "checked_frames": count,
            "model_meshes": len(meshes), "head_pitch_range_radians": [min(pitch), max(pitch)],
            "eye_target_vertical_range": [min(eye_vertical), max(eye_vertical)],
            "head_yaw_range_radians": [min(yaw), max(yaw)],
            "eyelid_range": [min(blink), max(blink)]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--camera-prefix", required=True)
    parser.add_argument("--pose-frame", type=int, required=True)
    parser.add_argument("--cycle-frames", type=int, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--samples", type=int, required=True)
    parser.add_argument("--device", type=Path, required=True)
    parser.add_argument("--device-x", type=float, required=True)
    parser.add_argument("--device-y", type=float, required=True)
    parser.add_argument("--device-report", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    scene = bpy.context.scene
    cameras = [obj for obj in scene.objects
               if obj.type == "CAMERA" and obj.name.startswith(args.camera_prefix)]
    if len(cameras) != 1:
        raise ValueError(f"Expected one listening camera, found {len(cameras)}.")
    if (args.pose_frame < 1 or args.cycle_frames < 5
            or min(args.width, args.height, args.samples) < 1):
        raise ValueError("Invalid listener pose, cycle or render settings.")
    args.output.mkdir(parents=True, exist_ok=True)
    scene.timeline_markers.clear()
    scene.camera = cameras[0]
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = args.samples
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.use_persistent_data = True
    scene.frame_set(args.pose_frame)
    frozen_objects = freeze_source_animation(scene)
    rigs = [obj for obj in scene.objects if obj.type == "ARMATURE" and obj.get("actor") == "candidate_a"]
    if len(rigs) != 1:
        raise ValueError("Expected one candidate rig.")
    rig = rigs[0]
    base = bake_listener_animation(scene, rig, args.cycle_frames)
    checks = add_playback_device(scene, scene.camera, args.device, args.device_x, args.device_y,
                                 rig, args.cycle_frames, base)
    checks["listener_pose_frame"] = args.pose_frame
    checks["head_pitch_radians"] = base["head"].x
    checks["eye_target_vertical"] = base["eyes"].z
    checks["frozen_source_objects"] = frozen_objects
    checks["render"] = {"width": args.width, "height": args.height, "samples": args.samples}
    args.device_report.write_text(json.dumps(checks, indent=2) + "\n", encoding="utf-8")
    for index in range(args.cycle_frames):
        scene.frame_set(index + 1)
        scene.render.filepath = str(args.output / f"listener_{index:03d}.png")
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
