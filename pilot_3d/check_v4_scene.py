"""Blender integration checks for the full practice episode, not only rig controls."""

import json
import math
import re
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from studio_characters import StudioCharacter
from episode_config import seating_deadline


def check_entrance(scene, actors, manifest, timeline, build):
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Vector
    from render import ass_time

    plan = manifest["entrance"]
    left, right, top = plan["portal"]
    radius = plan["body_radius_m"]
    scene.frame_set(1)
    for name in ("Back wall", "Door frame", "Entrance skirting left", "Entrance skirting right"):
        obj = scene.objects[name]
        inverse = obj.matrix_world.inverted()
        for height in (.09, 1.1, 2.20):
            hit = obj.ray_cast(inverse @ Vector((-2.9, 2.8, height)),
                               inverse.to_3x3() @ Vector((0, 1, 0)), distance=1.2)[0]
            if hit:
                raise ValueError(f"{name}: solid geometry still blocks the doorway at {height}m.")
    for x, height in ((-3.65, 1.1), (-2.9, 2.7)):
        obj = scene.objects["Back wall"]
        inverse = obj.matrix_world.inverted()
        if not obj.ray_cast(inverse @ Vector((x, 2.8, height)),
                            inverse.to_3x3() @ Vector((0, 1, 0)), distance=1.2)[0]:
            raise ValueError("The doorway repair removed surrounding wall geometry.")
    report = {"actual_open_portal_checked": True, "enabled": plan["enabled"]}
    if not plan["enabled"]:
        return report
    camera = next(obj for obj in scene.objects if obj.type == "CAMERA" and obj.name.startswith("01"))

    def project(points):
        points = [world_to_camera_view(scene, camera, point) for point in points]
        return (min(p.x for p in points) * 720, min(1 - p.y for p in points) * 1280,
                max(p.x for p in points) * 720, max(1 - p.y for p in points) * 1280)

    def overlaps(a, b):
        return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]

    hook = None
    if timeline["turns"][0]["start"] > 0:
        prefix = f"Dialogue: 0,0:00:00.00,{ass_time(timeline['turns'][0]['start'])},Box,"
        panels = [line for line in (build / "preflight/captions.ass").read_text().splitlines()
                  if line.startswith(prefix)]
        if len(panels) != 1:
            raise ValueError("Cannot identify the actual preflight opening-title panel.")
        match = re.search(r"m 96 (\d+) l 504 \1 504 (\d+) 96 \2", panels[0])
        if match is None:
            raise ValueError("The preflight opening-title panel has unexpected geometry.")
        hook = (96, int(match[1]), 504, int(match[2]))
    frame = scene.objects["Door frame"]
    doorway_bounds = project([frame.matrix_world @ Vector(corner) for corner in frame.bound_box])
    if hook is not None and overlaps(doorway_bounds, hook):
        raise ValueError(f"Opening title still covers the doorway: {doorway_bounds}, {hook}")
    # Excluded rig helpers stay unevaluated at the asset origin in this depsgraph.
    geometry = {name: [obj for obj in actor.root.children_recursive
                       if obj.type == "MESH" and obj.name.startswith("GEO-")
                       and not obj.hide_render and obj.visible_get()]
                for name, actor in actors.items() if name.startswith("candidate")}
    outside = {}
    for name, objects in geometry.items():
        if not objects:
            raise ValueError(f"{name}: missing visible body geometry for entrance checks.")
        points = [obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world @ Vector(corner)
                  for obj in objects
                  for corner in obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).bound_box]
        outside[name] = min(point.y for point in points)
        if outside[name] <= 3.44:
            raise ValueError(f"{name}: visible geometry starts inside the room/wall: y={outside[name]}")
    minimum_pair, minimum_door, portal_samples, head_samples = float("inf"), float("inf"), 0, 0
    last = max(blocking["seat_end"] for blocking in plan["actors"].values())
    for frame_number in range(1, math.ceil(last * timeline["fps"]) + 1, manifest["motion_step"]):
        scene.frame_set(frame_number)
        t = (frame_number - 1) / timeline["fps"]
        a, b = (actors[name].root.matrix_world.translation for name in ("candidate_a", "candidate_b"))
        distance = math.dist(a[:2], b[:2])
        minimum_pair = min(minimum_pair, distance)
        if distance < 2 * radius:
            raise ValueError(f"Entering candidates intersect at {t:.3f}s: {distance:.3f}m.")
        door = scene.objects["Door"]
        inverse = door.matrix_world.inverted()
        for name in ("candidate_a", "candidate_b"):
            point = actors[name].root.matrix_world.translation
            local = inverse @ Vector((point.x, point.y, 1.1))
            clearance = math.hypot(max(abs(local.x) - .51, 0), max(abs(local.y) - .035, 0)) - radius
            minimum_door = min(minimum_door, clearance)
            if clearance < -.001:
                raise ValueError(f"{name}: door swings through body at {t:.3f}s: {clearance:.3f}m.")
            if point.y - radius < 3.44 and point.y + radius > 3.26:
                if point.x - radius < left or point.x + radius > right:
                    raise ValueError(f"{name}: body crosses wall beside the opening at {t:.3f}s.")
                points = [obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world @ Vector(corner)
                          for obj in geometry[name]
                          for corner in obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).bound_box]
                if min(p.x for p in points) < left or max(p.x for p in points) > right or max(p.z for p in points) > top:
                    raise ValueError(f"{name}: visible mesh misses the clear portal at {t:.3f}s.")
                portal_samples += 1
            if hook is not None and t < timeline["turns"][0]["start"]:
                heads = [obj.evaluated_get(bpy.context.evaluated_depsgraph_get()) for obj in geometry[name]
                         if "head" in obj.name.lower()]
                if not heads:
                    raise ValueError(f"{name}: missing head mesh for opening-title visibility checks.")
                bounds = project([obj.matrix_world @ Vector(corner) for obj in heads for corner in obj.bound_box])
                if overlaps(bounds, hook):
                    raise ValueError(f"Opening title covers {name}'s head at {t:.3f}s: {bounds}")
                head_samples += 1
    if portal_samples < 4:
        raise ValueError("Entrance check did not observe both candidates passing through the opening.")
    report.update(outside_mesh_minimum_y_m=outside, minimum_candidate_distance_m=minimum_pair,
                  minimum_door_to_body_clearance_m=minimum_door, actual_portal_mesh_samples=portal_samples,
                  hook_bounds_px=hook, doorway_bounds_px=doorway_bounds,
                  unobscured_candidate_head_samples=head_samples)
    return report


def check(build):
    scene = bpy.context.scene
    timeline = json.loads((build / "timeline.json").read_text())
    manifest = json.loads((build / "scene_manifest.json").read_text())
    episode = manifest["episode"]
    step = manifest["motion_step"]
    if (scene.frame_start, scene.frame_end, scene.render.fps) != (1, timeline["total_frames"], timeline["fps"]):
        raise ValueError("Saved scene and final audio clock differ.")
    actors = {name: StudioCharacter.from_scene(name)
              for name in ("candidate_a", "candidate_b", "examiner", "observer")}
    closed = max(4, manifest.get("entrance", {}).get("door", {}).get("close_end", 0) + .1)
    scene.frame_set(1 + math.ceil(closed * timeline["fps"]))
    for name, expected in (("Door", (-2.9, 3.09, 1.15)), ("Door handle", (-2.53, 3.0, 1.12))):
        actual = tuple(scene.objects[name].matrix_world.translation)
        if math.dist(actual, expected) > 0.0001:
            raise ValueError(f"{name}: hinge parenting moved the closed door: {actual}")
    scene.frame_set(round((seating_deadline(episode, timeline) + 0.1) * timeline["fps"]) + 1)
    report = {"frames": timeline["total_frames"], "fps": timeline["fps"], "actors": {}}
    for name, actor in actors.items():
        drivers = actor.rig.animation_data.drivers
        expected = 514 if actor.kind == "rain" else 1070
        invalid = [curve.data_path for curve in drivers if not curve.driver.is_valid]
        if len(drivers) != expected or invalid:
            raise ValueError(f"{name}: invalid native drivers: {len(drivers)}, {invalid[:5]}")
        prefix = "FK-" if actor.kind == "rain" else "FK-Finger_"
        fingers = [(actor.rig.matrix_world @ actor.bones[f"{prefix}{finger}3.{side}"].tail).z
                   for finger in ("Index", "Middle") for side in ("L", "R")]
        if not all(0.884 < value < 0.903 for value in fingers):
            raise ValueError(f"{name}: actual fingertips miss the tabletop: {fingers}")
        entry = {"native_drivers": len(drivers), "resting_fingertip_heights_m": fingers}
        if actor.kind == "rain":
            drop = (actor.rig.matrix_world @ actor.bones["FK-Hair_Ponytail1"].head).z - (
                actor.rig.matrix_world @ actor.bones["FK-Hair_Ponytail4"].tail).z
            if drop < 0.15:
                raise ValueError(f"{name}: ponytail does not hang down.")
            entry["hair_tip_drop_m"] = drop
        report["actors"][name] = entry
    blink_max = {name: 0 for name in actors}
    for frame in range(1, min(timeline["total_frames"], round(4.7 * timeline["fps"])) + 1, step):
        scene.frame_set(frame)
        for name, actor in actors.items():
            if actor.kind == "rain":
                mesh = next(obj for obj in actor.root.children_recursive
                            if obj.type == "MESH" and obj.name.startswith("GEO-rain-head"))
                closure = mesh.data.shape_keys.key_blocks["EyelidsClose.L"].value
            else:
                constraint = next(item for item in actor.bones["Eyelid_Upper3.L"].constraints
                                  if item.type == "ACTION" and "CloseOpen" in item.name)
                closure = constraint.eval_time
            blink_max[name] = max(blink_max[name], closure)
    if timeline["duration"] >= 4.7 and any(value < 0.80 for value in blink_max.values()):
        raise ValueError(f"Blinks fail to reach actual facial deformation: {blink_max}")
    report["actual_eyelid_closure_maxima"] = blink_max
    drift = {}
    for index, name in enumerate(("candidate_a", "candidate_b")):
        actor = actors[name]
        blocking = json.loads(actor.root["blocking"])
        if not blocking.get("entrance", True):
            previous = {}
            for frame in range(1, timeline["total_frames"] + 1, max(step, timeline["fps"] // 2)):
                scene.frame_set(frame)
                for side in ("L", "R"):
                    point = actor.rig.matrix_world @ actor.bones["IK-Foot." + side].matrix.translation
                    if side in previous and (point - previous[side]).length > 0.002:
                        raise ValueError(f"{name}: seated foot slides.")
                    previous[side] = point.copy()
            drift[name] = {"entrance": False, "seated_feet_checked": True}
            continue
        previous = {}
        maximum = 0.0
        samples = 0
        walk_start = blocking.get("walk_start", 0 if index == 0 else .35)
        for frame in range(1, round(blocking["walk_end"] * timeline["fps"]) + 1, step):
            scene.frame_set(frame)
            t = (frame - 1) / timeline["fps"]
            for side in ("L", "R"):
                clock = max(0, t - walk_start) + (0 if side == "L" else 0.45)
                cycle, phase = math.floor(clock / 0.90), (clock / 0.90) % 1
                point = actor.rig.matrix_world @ actor.bones["IK-Foot." + side].matrix.translation
                if phase >= 0.43 and side in previous and previous[side][0] == cycle:
                    maximum = max(maximum, (point - previous[side][1]).length)
                    samples += 1
                if phase >= 0.43:
                    previous[side] = (cycle, point.copy())
                else:
                    previous.pop(side, None)
        if samples < 10 or maximum > 0.002:
            raise ValueError(f"{name}: planted foot drifts {maximum:.6f}m across {samples} stance samples.")
        # Both feet remain fixed while the root moves back and the hips lower.
        settled = {}
        first = round(blocking["seat_start"] * timeline["fps"]) + 2
        first = 1 + math.ceil((first - 1) / step) * step
        for frame in range(first, round(blocking["seat_end"] * timeline["fps"]) + 1, step):
            scene.frame_set(frame)
            for side in ("L", "R"):
                point = actor.rig.matrix_world @ actor.bones["IK-Foot." + side].matrix.translation
                if side in settled and (point - settled[side]).length > 0.002:
                    raise ValueError(f"{name}: foot slides while sitting.")
                settled[side] = point.copy()
        drift[name] = {"maximum_stance_drift_m": maximum, "checked_stance_samples": samples}
    report["foot_contacts"] = drift
    if manifest.get("visual_version", 0) >= 6:
        report["entrance"] = check_entrance(scene, actors, manifest, timeline, build)
    if manifest.get("visual_version", 0) >= 5:
        from bpy_extras.object_utils import world_to_camera_view
        from mathutils import Vector
        from prepare_audio import sha256_file

        design = manifest["room_design"]
        if design["logo"]:
            logo = design["logo"]
            plane = scene.objects[logo["object"]]
            image = bpy.data.images[logo["packed_image"]]
            if not image.packed_file or plane.get("original_logo_sha256") != sha256_file(Path(logo["path"])):
                raise ValueError("The original wall logo is missing, changed or not packed into the scene.")
            camera = next(obj for obj in scene.objects if obj.type == "CAMERA" and obj.name.startswith("04"))
            projected = [world_to_camera_view(scene, camera, plane.matrix_world @ Vector(corner))
                         for corner in plane.bound_box]
            bounds = (min(p.x for p in projected) * 720, min(1 - p.y for p in projected) * 1280,
                      max(p.x for p in projected) * 720, max(1 - p.y for p in projected) * 1280)
            if not (88 <= bounds[0] < bounds[2] <= 512 and 275 <= bounds[1] < bounds[3] <= 566):
                raise ValueError(f"Wall logo misses the clear social-safe background in the Lea camera: {bounds}")
            report["wall_logo"] = {"sha256": plane["original_logo_sha256"],
                                  "packed": True, "candidate_a_projected_bounds_px": bounds}
        checked, minimum, maximum = 0, float("inf"), 0
        for gesture in manifest["performance"]["gestures"]:
            for offset in (-.18, 0, .40, .80):
                frame = 1 + round((gesture["peak"] + offset) * timeline["fps"])
                scene.frame_set(min(frame, timeline["total_frames"]))
                actor = actors[gesture["actor"]]
                prefix = "FK-" if actor.kind == "rain" else "FK-Finger_"
                heights = [(actor.rig.matrix_world @ actor.bones[f"{prefix}{finger}3.{side}"].tail).z
                           for finger in ("Index", "Middle") for side in ("L", "R")]
                if not all(.884 < value < 1.09 for value in heights):
                    raise ValueError(f"{actor.name}: speech gesture intersects table or rises too far: {heights}")
                minimum, maximum = min(minimum, *heights), max(maximum, *heights)
                checked += 1
        report["speech_gestures"] = {"anticipation_peak_release_poses_checked": checked,
                                    "fingertip_height_range_m": [minimum, maximum] if checked else None}
        gap_samples = 0
        for turn, following in zip(timeline["turns"], timeline["turns"][1:]):
            if not turn["speaker"].startswith("candidate") or following["start"] - turn["end"] < .15:
                continue
            scene.frame_set(1 + round((turn["end"] + .10) * timeline["fps"]))
            for name, actor in actors.items():
                if (name.startswith("candidate") and turn.get("look_at") in ("candidate_a", "candidate_b")
                        and turn["look_at"] != turn["speaker"]):
                    yaw = actor.bones["FK-Head"].rotation_euler.y
                    if abs(yaw) < .43:
                        raise ValueError(f"{name}: attention resets during the pause after {turn['id']}.")
                    gap_samples += 1
        report["attention_during_turn_gaps"] = {"candidate_poses_checked": gap_samples}
    if manifest.get("visual_version", 0) >= 7:
        from scene_direction import gaze_at

        previous = {}
        maximum_head_step, maximum_eye_step, maximum_eye_lead = 0.0, 0.0, 0.0
        samples = 0
        for frame in range(1, timeline["total_frames"] + 1, step):
            scene.frame_set(frame)
            t = (frame - 1) / timeline["fps"]
            for name, actor in actors.items():
                gaze = gaze_at(manifest["performance"], name, t)
                yaw = actor.bones["FK-Head"].rotation_euler.y
                eyes = actor.bones["TGT-Eyes"].matrix.translation.copy()
                if abs(yaw - gaze["head"]) > .0001:
                    raise ValueError(f"{name}: baked head does not match the continuous attention plan at frame {frame}.")
                lead = abs(gaze["eyes"] - gaze["head"])
                if lead > .160001:
                    raise ValueError(f"{name}: eye lead exceeds the head-relative limit at frame {frame}.")
                maximum_eye_lead = max(maximum_eye_lead, lead)
                if name in previous:
                    last_yaw, last_eyes = previous[name]
                    head_step, eye_step = abs(yaw - last_yaw), (eyes - last_eyes).length
                    if head_step > .055 * step or eye_step > .17 * step:
                        raise ValueError(f"{name}: gaze snaps at frame {frame}: {head_step:.4f}rad, {eye_step:.4f}m.")
                    maximum_head_step = max(maximum_head_step, head_step)
                    maximum_eye_step = max(maximum_eye_step, eye_step)
                previous[name] = (yaw, eyes)
                samples += 1
        report["continuous_attention"] = {
            "native_control_samples": samples, "maximum_head_step_radians": maximum_head_step,
            "maximum_eye_target_step_m": maximum_eye_step, "maximum_planned_eye_lead_radians": maximum_eye_lead,
            "note": "Control-space continuity and eye-lead bounds; iris visibility also requires rendered review.",
        }
    for frame in range(1, timeline["total_frames"] + 1, 38):
        scene.frame_set(frame)
        t = (frame - 1) / timeline["fps"]
        turn = next((turn for turn in timeline["turns"] if turn["start"] <= t < turn["end"]), None)
        for name, actor in actors.items():
            jaw = actor.bones[actor.jaw_name].rotation_euler.x
            if not math.isfinite(jaw) or not 0 <= jaw <= 0.15:
                raise ValueError(f"{name}: invalid jaw at frame {frame}.")
            if (not turn or turn["speaker"] != name) and abs(jaw) > 0.0001:
                raise ValueError(f"{name}: listener mouth moves at frame {frame}.")
    (build / "scene_checks.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    check(Path(sys.argv[sys.argv.index("--") + 1]).resolve())
