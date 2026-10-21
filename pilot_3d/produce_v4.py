#!/usr/bin/env python3
"""Non-destructive social re-export, full practice animatic, and exact-PCM promo edit."""

import argparse
import copy
import hashlib
import json
import math
import os
import shutil
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from prepare_audio import atomic_json, ceil_frames, sha256_file, subtitles
from episode_config import (ACTORS, CAMERA_PREFIXES, PROFILES, check_timeline, entrance_enabled,
                            promo_settings, read_episode, seating_deadline, task_window, turn_phase)
from entrance import HINGE, door_angle, doorway_geometry, entrance_plan, path_at, walk_pose


def isolated(source, build):
    if source == build or source in build.parents or build in source.parents:
        raise ValueError("Derived output must use a separate sibling build directory.")
    build.mkdir(parents=True, exist_ok=True)


def link_frame(source, target):
    if target.exists():
        if sha256_file(source) != sha256_file(target):
            raise ValueError(f"Conflicting existing derived frame: {target}")
    else:
        os.link(source, target)


def camera_shots(episode, timeline):
    initial = "wide" if entrance_enabled({**episode, "turns": timeline["turns"]}) else timeline["turns"][0]["camera"]
    shots = [(0, initial)]
    shots += [(turn["start"], turn["camera"]) for turn in timeline["turns"]]
    window = task_window(timeline)
    if window is not None:
        shots.append((window[0], "candidates"))
    if episode["outro_seconds"] > 0:
        shots.append((timeline["duration"] - episode["outro_seconds"], "candidates"))
    return sorted(shots)


def camera_at_frame(markers, frame):
    eligible = [marker for marker in markers if marker["frame"] <= frame]
    if not eligible:
        raise ValueError(f"No camera selected for frame {frame}.")
    return max(eligible, key=lambda marker: marker["frame"])["camera"]


def verify_speaker_cameras(markers, timeline):
    checked = 0
    for turn in timeline["turns"]:
        expected = CAMERA_PREFIXES[turn["camera"]]
        for frame in range(turn["start_frame"] + 1, turn["end_frame"] + 1):
            actual = camera_at_frame(markers, frame)
            if not actual.startswith(expected):
                raise ValueError(f"Camera leaves {turn['name']} during turn {turn['id']}, frame {frame}: {actual}")
            checked += 1
    return {"speaking_frames_checked": checked, "all_turns_hold_their_camera": True}


def action_digest():
    import array
    import bpy

    digest = hashlib.sha256()
    for action in sorted(bpy.data.actions, key=lambda item: item.name):
        digest.update(action.name.encode())
        for curve in action.fcurves:
            digest.update(f"{curve.data_path}:{curve.array_index}:{curve.extrapolation}".encode())
            for field in ("co", "handle_left", "handle_right"):
                values = array.array("f", [0]) * (len(curve.keyframe_points) * 2)
                curve.keyframe_points.foreach_get(field, values)
                digest.update(values.tobytes())
    return digest.hexdigest()


def revise_cameras(build, source, episode_path=None):
    """Change only camera markers and reuse only camera-identical source frames."""
    import bpy
    from render import scene_hash, valid_frame

    isolated(source, build)
    if any(build.iterdir()):
        raise ValueError("Prepare a camera revision in an empty directory; use render.py to resume it.")
    source_manifest = json.loads((source / "scene_manifest.json").read_text())
    source_hash = scene_hash(source)
    receipt = json.loads((source / "frames_manifest.json").read_text())
    if receipt != {"scene": source_manifest, "blend_sha256": source_hash}:
        raise ValueError("Source frames are not verified against their saved scene.")
    episode = copy.deepcopy(source_manifest["episode"])
    updated = read_episode(episode_path) if episode_path is not None else episode
    if episode["turns"] != updated["turns"]:
        raise ValueError("A camera-only revision cannot change the spoken screenplay.")
    episode.update(subtitle_mode="readable", cta=updated["cta"])
    timeline = json.loads((source / "timeline.json").read_text())
    if timeline != source_manifest["timeline"]:
        raise ValueError("Source timeline is stale for its scene.")
    bpy.ops.wm.open_mainfile(filepath=str(source / "studio.blend"))
    scene = bpy.context.scene
    old_markers = [{"frame": marker.frame, "camera": marker.camera.name}
                   for marker in scene.timeline_markers if marker.camera]
    before_actions = action_digest()
    cameras = {key: next(obj for obj in scene.objects
                        if obj.type == "CAMERA" and obj.name.startswith(prefix))
               for key, prefix in CAMERA_PREFIXES.items()}
    shots = camera_shots(episode, timeline)
    scene.timeline_markers.clear()
    for seconds, name in shots:
        marker = scene.timeline_markers.new(name, frame=1 + round(seconds * timeline["fps"]))
        marker.camera = cameras[name]
    new_markers = [{"frame": marker.frame, "camera": marker.camera.name}
                   for marker in scene.timeline_markers if marker.camera]
    camera_check = verify_speaker_cameras(new_markers, timeline)
    if action_digest() != before_actions:
        raise RuntimeError("Camera revision unexpectedly changed actor animation.")
    scene.render.filepath = str(build / "frames" / "frame_")
    scene.frame_set(1)
    for name in ("dialogue.wav", "word_alignment.json"):
        shutil.copy2(source / name, build / name)
    for name, value in (("episode.json", episode), ("timeline.json", timeline)):
        atomic_json(build / name, value)
    bpy.ops.wm.save_as_mainfile(filepath=str(build / "studio.blend"), compress=True)
    manifest = copy.deepcopy(source_manifest)
    manifest.update(episode=episode, shots=shots, camera_revision_from={
        "source": str(source), "source_scene_sha256": source_hash,
        "script_sha256": sha256_file(Path(__file__)),
        "actor_action_sha256": before_actions,
        "change": "Camera markers only; all actor action coordinates and curve handles unchanged. "
                  "No mid-turn reaction shots; original dialogue PCM and alignment unchanged.",
    })
    atomic_json(build / "scene_manifest.json", manifest)
    (build / "frames").mkdir()
    reused, changed = [], []
    for frame in range(1, timeline["total_frames"] + 1, manifest["motion_step"]):
        old, new = camera_at_frame(old_markers, frame), camera_at_frame(new_markers, frame)
        original = source / "frames" / f"frame_{frame:04d}.png"
        if not valid_frame(original, manifest["width"], manifest["height"]):
            raise ValueError(f"Invalid source frame: {original}")
        if old == new:
            link_frame(original, build / "frames" / original.name)
            reused.append({"frame": frame, "camera": new, "sha256": sha256_file(original)})
        else:
            changed.append({"frame": frame, "old_camera": old, "new_camera": new})
    if scene_hash(source) != source_hash:
        raise RuntimeError("Source scene changed during revision preparation.")
    atomic_json(build / "camera_revision_report.json", {
        **camera_check, "source": str(source), "source_scene_sha256": source_hash,
        "revised_scene_sha256": scene_hash(build), "actor_action_sha256": before_actions,
        "old_markers": old_markers, "new_markers": new_markers,
        "reused_frames": reused, "rerender_frames": changed,
        "proof": "Only camera-marker edits. Every reused pose has the same active camera, "
                 "same source scene/actor actions and recorded PNG hash. Different-camera poses must rerender.",
    })
    atomic_json(build / "render_checkpoint.json", {"scene": manifest, "blend_sha256": scene_hash(build)})
    print(f"Stable-camera revision: {len(reused)} verified unchanged poses, {len(changed)} poses to render.", flush=True)


def social_exchange(build):
    from align_words import align_build
    from render import mux, scene_hash

    source = ROOT / "build_v3_exchange"
    isolated(source, build)
    episode = json.loads((source / "episode.json").read_text())
    episode.update(presentation="social", social_kind="exchange", credit_policy="publishing_caption")
    timeline = json.loads((source / "timeline.json").read_text())
    for name, value in (("episode.json", episode), ("timeline.json", timeline)):
        atomic_json(build / name, value)
    for name in ("dialogue.wav", "studio.blend"):
        shutil.copy2(source / name, build / name)
    (build / "frames").mkdir(exist_ok=True)
    for frame in (source / "frames").glob("frame_*.png"):
        link_frame(frame, build / "frames" / frame.name)
    align_build(build)
    timeline = json.loads((build / "timeline.json").read_text())
    manifest = json.loads((source / "scene_manifest.json").read_text())
    manifest.update(episode=episode, timeline=timeline, caption_revision_from={
        "source": str(source), "scene_sha256": scene_hash(source),
        "change": "Caption-only re-export: original 3D poses, frames and exact dialogue unchanged.",
    })
    atomic_json(build / "scene_manifest.json", manifest)
    atomic_json(build / "frames_manifest.json", {"scene": manifest, "blend_sha256": scene_hash(build)})
    (build / "subtitles.srt").write_text(subtitles(timeline), encoding="utf-8")
    mux(build, build / "episode.json")


def animate(actor, timeline, index, episode, motion_step, entrance_direction):
    import bpy
    from mathutils import Matrix, Vector
    from polish_exchange import MOUTH_POSES, mouth_pose, pulse, smooth
    from studio_characters import key
    from scene_direction import blink_at, gaze_at, performance_at, performance_plan

    candidate = actor.name.startswith("candidate")
    rain = actor.kind == "rain"
    side_sign = 1 if actor.name in ("candidate_a", "examiner") else -1
    entrance = entrance_enabled(episode)
    window = task_window(timeline)
    blocking = entrance_direction["actors"].get(actor.name, {})
    seat_start, seat_end = blocking.get("seat_start", 0), blocking.get("seat_end", 0)
    walk_start, walk_end = blocking.get("walk_start", 0), blocking.get("walk_end", 0)
    x = actor.pos.x
    front = (x, actor.pos.y - 0.35, 0)
    for obj in (actor.root, actor.rig):
        if obj.animation_data:
            obj.animation_data.action = None
    top = "MSTR-UpperLip" if rain else "MSTR-Lip_Top"
    bottom = "MSTR-LowerLip" if rain else "MSTR-Lip_Bottom"
    upper = "ACT-Eyelid_Upper" if rain else "MSTR-Eyelid_Upper"
    lower = "ACT-Eyelid_Lower" if rain else "MSTR-Eyelid_Lower"
    plan = performance_plan(timeline)
    maximum_contact_correction = 0.0

    def offset(name, delta, frame):
        bone = actor.bones[name]
        bone.location = actor.rest[name].to_3x3().inverted() @ Vector(delta)
        key(bone, frame)

    def walking_foot(t, side):
        period = 0.90
        shift = 0 if side == "L" else period / 2
        clock = max(0, min(t, walk_end) - walk_start) - shift
        cycle = math.floor(clock / period)
        phase = clock / period - cycle

        def anchor(moment):
            point, angle = walk_pose(blocking, moment)
            if moment >= walk_end:
                angle = 0
            offset_x = (0.115 if side == "L" else -0.115) * actor.scale
            return Vector((point[0] + math.cos(angle) * offset_x,
                           point[1] + math.sin(angle) * offset_x,
                           actor.rest["IK-Foot." + side].translation.z * actor.scale)), angle

        a, angle_a = anchor(walk_start + (cycle - 1) * period + shift + .65 * period)
        b, angle_b = anchor(walk_start + cycle * period + shift + .65 * period)
        weight = smooth(phase / 0.43)
        position = a.lerp(b, weight)
        if phase < 0.43:
            position.z += 0.065 * math.sin(math.pi * phase / 0.43)
        angle_delta = (angle_b - angle_a + math.pi) % (2 * math.pi) - math.pi
        angle = angle_a + angle_delta * weight
        if t > walk_end:
            settle = smooth((t - walk_end) / .35)
            final, _angle = anchor(walk_end)
            position = position.lerp(final, settle)
            position.z += .035 * math.sin(math.pi * settle)
            angle *= 1 - settle
        return position, angle

    for frame in range(1, timeline["total_frames"] + 1, motion_step):
        t = (frame - 1) / timeline["fps"]
        turn = next((item for item in timeline["turns"] if item["start"] <= t < item["end"]), None)
        speaking = turn is not None and turn["speaker"] == actor.name
        phase = t - turn["start"] if speaking else 0
        direction = performance_at(plan, actor.name, t)
        gesture = direction["accent"]
        seated = smooth((t - seat_start) / 1.15) if candidate and entrance else 1.0
        if candidate and entrance:
            point, angle = walk_pose(blocking, t)
            actor.root.location = Vector(point) + Vector((0, 0.35 * seated, 0))
            actor.root.rotation_euler.z = angle
        else:
            actor.root.location = actor.pos
            actor.root.rotation_euler.z = actor.angle
        for prop in ("location", "rotation_euler"):
            actor.root.keyframe_insert(data_path=prop, frame=frame)
        actor.position(actor.torso_name, actor.rest[actor.torso_name].translation + Vector((
            0, -0.045 * math.sin(seated * math.pi) - 0.006 * gesture,
            -(0.23 if rain else 0.25) * seated + 0.0012 * math.sin(t * 1.55 + index * 1.7),
        )), frame)
        attention = gaze_at(plan, actor.name, t)
        gaze = attention["head"]
        reading = direction["glance"]
        if window is not None and window[0] <= t < window[1]:
            reading = pulse(t, window[0] + 0.3 + index * 0.24, 3)
        nod = direction["nod"] * seated
        thinking = speaking and turn["action"] == "consider"
        actor.rotate("FK-Chest", (0.018 * gesture, gaze * 0.24, 0.006 * gesture if thinking else 0), frame)
        actor.rotate("FK-Head", (nod + 0.18 * reading + 0.003 * math.sin(t * .85 + index),
                                gaze, side_sign * (0.025 if thinking else 0.012) * gesture), frame)
        bpy.context.view_layer.update()
        eye_height = (1.47 if rain else 1.62) - (0.23 if rain else 0.25) * seated
        if candidate:
            eye_height += (0.05 if rain else -0.05) / actor.scale * min(1, abs(gaze) / .48)
        eye_target = Vector((math.sin(attention["eyes"]) * 1.65,
                             -math.cos(attention["eyes"]) * 1.65, eye_height - 0.015))
        eye_target = eye_target.lerp(Vector((side_sign * 0.15, -0.95, eye_height - 0.30)), min(1, reading))
        actor.position("TGT-Eyes", eye_target, frame)
        jaw, width, rounding, seal = mouth_pose(turn["mouth_cues"], phase) if speaking else MOUTH_POSES["X"]
        actor.rotate(actor.jaw_name, (jaw, 0, 0), frame)
        actor.bones["MSTR-Mouth"].scale = (width, 1, 1)
        key(actor.bones["MSTR-Mouth"], frame)
        offset("MSTR-Mouth", (0, -0.004 * rounding, 0), frame)
        offset(top, (0, -0.0015 * rounding, -0.0011 * seal), frame)
        offset(bottom, (0, -0.0018 * rounding, 0.0017 * seal), frame)
        blink = blink_at(plan, actor.name, t, timeline["fps"], motion_step)
        hand_poses = {}
        for side, sign in (("L", 1), ("R", -1)):
            smile = 0.08 if speaking else 0.18 + 0.24 * nod / 0.065
            offset("ACT-Lips_Corner." + side, (sign * 0.0015 * smile, 0, 0.003 * smile), frame)
            offset("MSTR-Eyebrow." + side, (0, 0, 0.0016 * gesture * (1 if side == "L" else .72)), frame)
            lid = -((0.004 + 0.007 * reading) * (1 - blink) + 0.040 * blink) if rain else -0.003 - 0.027 * blink
            offset(upper + "." + side, (0, 0, lid), frame)
            offset(lower + "." + side, (0, 0, 0.0008 - 0.001 * reading + 0.003 * blink), frame)
            if rain:
                for region in ("Upper", "Lower"):
                    offset(f"MSTR-Eyering_{region}.{side}", (0, 0, 0), frame)
            wrist = 0.902 if rain else 0.91
            hand_gesture = direction["hands"][side]
            hand_reach = direction["reach"][side] * hand_gesture
            action = direction["actions"][side]
            reflect = action == "consider"
            lift = .038 if reflect else .055 if action in ("welcome", "explain") else .066
            hand = Vector((sign * (.24 + (-.018 if reflect else .032) * hand_reach),
                           -.38 - (.008 if reflect else .035) * hand_reach,
                           wrist / actor.scale + lift * hand_reach))
            hanging = Vector((sign * 0.24, -0.02, 0.82 / actor.scale))
            hand = hanging.lerp(hand, seated)
            rotation = Matrix.Rotation(sign * hand_gesture * (.32 if reflect else .85), 4, "Y") @ Matrix.Rotation(-sign * math.pi / 2, 4, "Z")
            standing = Matrix.Rotation(sign * math.pi / 2, 4, "Y")
            rotation = standing.to_quaternion().slerp(rotation.to_quaternion(), seated).to_matrix().to_4x4()
            actor.position(actor.hand_name + "." + side, hand, frame, rotation)
            hand_poses[side] = (hand.copy(), rotation.copy())
            if candidate and entrance:
                world, angle = walking_foot(t, side)
                if t >= seat_start:
                    world = Vector((x + sign * 0.115 * actor.scale, front[1],
                                    actor.rest["IK-Foot." + side].translation.z * actor.scale))
                    angle = 0
                local = actor.rig.matrix_world.inverted() @ world
                actor.position("IK-Foot." + side, local, frame,
                               Matrix.Rotation(angle - actor.root.rotation_euler.z, 4, "Z"))
            else:
                foot = actor.rest["IK-Foot." + side].translation.copy()
                foot.y = front[1] - actor.pos.y if candidate else -0.34
                actor.position("IK-Foot." + side, foot, frame)
            if actor.knee_name:
                pole = actor.rest[actor.knee_name + "." + side].translation.copy()
                pole.y = -0.8
                actor.position(actor.knee_name + "." + side, pole, frame)
        if seated > .999:
            bpy.context.view_layer.update()
            prefix = "FK-" if rain else "FK-Finger_"
            for side, (hand, rotation) in hand_poses.items():
                lowest = min((actor.rig.matrix_world @ actor.bones[f"{prefix}{finger}3.{side}"].tail).z
                             for finger in ("Index", "Middle"))
                # Native finger curvature varies by hand; constrain actual tips, not just the wrist.
                correction = max(0.0, .889 - lowest)
                if correction > .025:
                    raise ValueError(f"{actor.name}: hand pose requires excessive table clearance: {correction:.4f}m.")
                if correction:
                    maximum_contact_correction = max(maximum_contact_correction, correction)
                    hand.z += correction / actor.scale
                    actor.position(actor.hand_name + "." + side, hand, frame, rotation)
        if rain:
            for hair, angle in enumerate((-0.70, -0.48, -0.12, 0.10), 1):
                actor.rotate(f"FK-Hair_Ponytail{hair}", (angle + .006 * nod if hair > 1 else angle, 0, 0), frame)
    for obj in (actor.root, actor.rig):
        for curve in obj.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "LINEAR"
    actor.root["blocking"] = json.dumps({
        **blocking,
        "entrance": candidate and entrance,
        "walk_start": walk_start,
        "walk_end": walk_end, "seat_start": seat_start, "seat_end": seat_end,
        "foot_method": "World-space stance holds; swing-only lift; final turn/shuffle, then planted feet while pelvis settles.",
        "maximum_fingertip_contact_correction_m": maximum_contact_correction,
    })


def scene_build(build, episode_path=None, profile="preview"):
    import bpy
    from mathutils import Vector
    from studio_characters import StudioCharacter
    from scene_direction import VERSION, configure_cameras, performance_plan, room_design

    episode = read_episode(episode_path or build / "episode.json")
    timeline = json.loads((build / "timeline.json").read_text())
    check_timeline(episode, timeline)
    if "word_alignment" not in timeline:
        raise ValueError("Align final speech before building performance.")
    scene = bpy.context.scene
    design = room_design(scene, episode)
    design["doorway"] = doorway_geometry(scene)
    entrance_direction = entrance_plan(episode, timeline)
    scene.frame_set(1 + 10 * timeline["fps"])
    actors = []
    quality = PROFILES[profile]
    for index, name in enumerate(ACTORS):
        actor = StudioCharacter.from_scene(name)
        actor.restore_native_drivers()
        animate(actor, timeline, index, episode, quality["motion_step"], entrance_direction)
        actors.append(actor)
        print(f"V4 performance baked: {name}", flush=True)
    hinge = bpy.data.objects.new("V4 door hinge", None)
    scene.collection.objects.link(hinge)
    hinge.location = HINGE
    bpy.context.view_layer.update()
    for name in ("Door", "Door handle"):
        obj = scene.objects[name]
        world = obj.matrix_world.copy()
        obj.parent = hinge
        obj.matrix_world = world
    door_end = entrance_direction.get("door", {}).get("close_end", 0) + .1
    for frame in range(1, math.ceil(door_end * timeline["fps"]) + 2):
        t = (frame - 1) / timeline["fps"]
        hinge.rotation_euler.z = door_angle(entrance_direction, t)
        hinge.keyframe_insert(data_path="rotation_euler", frame=frame)
    for curve in hinge.animation_data.action.fcurves:
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR"
    cameras = configure_cameras(scene)
    scene.timeline_markers.clear()
    shots = camera_shots(episode, timeline)
    for t, name in shots:
        marker = scene.timeline_markers.new(name, frame=1 + round(t * timeline["fps"]))
        marker.camera = cameras[name]
    scene.camera = cameras[shots[0][1]]
    editor = scene.sequence_editor_create()
    for strip in list(editor.sequences):
        editor.sequences.remove(strip)
    sound = editor.sequences.new_sound("V4 final Qwen dialogue", str(build / "dialogue.wav"), channel=1, frame_start=1)
    scene.render.use_sequencer = False
    scene.frame_start, scene.frame_end = 1, timeline["total_frames"]
    scene.render.fps = timeline["fps"]
    scene.render.resolution_x, scene.render.resolution_y = quality["width"], quality["height"]
    scene.render.resolution_percentage = 100
    scene.render.engine = "CYCLES"
    scene.cycles.samples = quality["samples"]
    scene.cycles.use_denoising = True
    scene.render.use_persistent_data = True
    scene["render_note"] = f"exam_room template; {profile} profile; measured local speech."
    scene["notice"] = episode["disclaimer"]
    (build / "frames").mkdir(exist_ok=True)
    scene.render.filepath = str(build / "frames" / "frame_")
    scene.frame_set(1)
    bpy.ops.file.pack_all()
    sound.sound.filepath = "//dialogue.wav"
    bpy.ops.wm.save_as_mainfile(filepath=str(build / "studio.blend"), compress=True)
    manifest = {
        "episode": episode, "timeline": timeline, "width": quality["width"], "height": quality["height"],
        "output_width": 720, "output_height": 1280, "motion_step": quality["motion_step"],
        "visual_version": VERSION, "engine": "cycles", "samples": quality["samples"],
        "room_design": design, "performance": performance_plan(timeline), "entrance": entrance_direction,
        "quality": profile,
        "source_sha256": {name: sha256_file(ROOT / name) for name in
                          ("produce_v4.py", "episode_config.py", "studio_characters.py", "polish_exchange.py", "scene_direction.py", "entrance.py", "build_scene.py")},
        "blocking": {actor.name: json.loads(actor.root["blocking"]) for actor in actors},
        "shots": shots,
        "camera_markers": [{"frame": marker.frame, "camera": marker.camera.name}
                           for marker in scene.timeline_markers if marker.camera],
    }
    verify_speaker_cameras(manifest["camera_markers"], timeline)
    atomic_json(build / "scene_manifest.json", manifest)


def repair_door(build):
    """Correct an already-baked pilot without rebaking any actor performance."""
    import bpy

    source_world = {name: bpy.context.scene.objects[name].matrix_world.copy()
                    for name in ("Door", "Door handle")}
    before = sha256_file(build / "studio.blend")
    bpy.ops.wm.open_mainfile(filepath=str(build / "studio.blend"))
    scene = bpy.context.scene
    scene.frame_set(1 + 4 * scene.render.fps)
    bpy.context.view_layer.update()
    for name, world in source_world.items():
        scene.objects[name].matrix_world = world
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(build / "studio.blend"), compress=True)
    manifest_path = build / "scene_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["door_parenting_repair"] = {
        "before_scene_sha256": before,
        "repair_script_sha256": sha256_file(Path(__file__)),
        "change": "Preserve original world transforms after evaluating the new hinge parent. Actor actions unchanged.",
    }
    atomic_json(manifest_path, manifest)


def plan_promo(source_episode, original):
    episode = copy.deepcopy(source_episode)
    settings = promo_settings(episode)
    intro_frames = ceil_frames(settings["intro_seconds"], original["fps"])
    outro_frames = ceil_frames(settings["outro_seconds"], original["fps"])
    selected = None
    ids = settings.get("turn_ids")
    turns = original["turns"]
    if ids is not None:
        indexes = [next((i for i, turn in enumerate(turns) if turn["id"] == value), -1) for value in ids]
        if not indexes or indexes[0] < 0 or indexes != list(range(indexes[0], indexes[-1] + 1)):
            raise ValueError("Promo turn_ids must select consecutive existing turns in order.")
        selected = [turns[index] for index in indexes]
    else:
        for first in range(len(turns)):
            options = []
            for stop in range(first + 1, len(turns) + 1):
                option = turns[first:stop]
                if any(not turn["speaker"].startswith("candidate") or turn_phase(turn) != "dialogue" for turn in option):
                    break
                duration = (option[-1]["end_frame"] - option[0]["start_frame"] + intro_frames + outro_frames) / original["fps"]
                if settings["min_seconds"] <= duration <= settings["max_seconds"]:
                    options.append(option)
            if options:
                selected = options[-1]
                break
    if selected is None:
        raise ValueError(f"No contiguous whole-turn promo fits {settings['min_seconds']:g}–"
                         f"{settings['max_seconds']:g}s. Adjust promo bounds/bookends or select turn_ids.")
    if any(turn_phase(turn) != "dialogue" for turn in selected):
        raise ValueError("A promo cannot include the welcome/task-card phase.")
    start, stop = selected[0]["start_frame"], selected[-1]["end_frame"]
    total = intro_frames + stop - start + outro_frames
    if not settings["min_seconds"] <= total / original["fps"] <= settings["max_seconds"]:
        raise ValueError("Selected promo turns fall outside the configured duration bounds.")
    intro, outro = intro_frames / original["fps"], outro_frames / original["fps"]
    turns = copy.deepcopy(selected)
    for turn in turns:
        for field in ("start_frame", "end_frame"):
            turn[field] += intro_frames - start
        turn["start"], turn["end"] = turn["start_frame"] / original["fps"], turn["end_frame"] / original["fps"]
    timeline = {**original, "turns": turns, "intro_seconds": intro, "outro_seconds": outro,
                "total_frames": total, "duration": total / original["fps"]}
    episode.update(id=episode["id"] + "_promo", social_kind="promo", intro_seconds=intro, outro_seconds=outro,
                   hook=settings.get("hook", episode.get("hook", episode["title"])), takeaway=[], takeaway_seconds=0,
                   turns=[turn for turn in episode["turns"] if turn["id"] in {item["id"] for item in selected}])
    return episode, timeline, start, stop, intro_frames, outro_frames


def promo(build, source=None):
    from render import mux, scene_hash
    from social_captions import make_ass

    source = source if source is not None else ROOT / "build_v4"
    isolated(source, build)
    original = json.loads((source / "timeline.json").read_text())
    source_manifest = json.loads((source / "scene_manifest.json").read_text())
    if source_manifest["timeline"] != original:
        raise ValueError("Promo source scene and audio timeline differ.")
    receipt = json.loads((source / "frames_manifest.json").read_text())
    if receipt != {"scene": source_manifest, "blend_sha256": scene_hash(source)}:
        raise ValueError("Promo source frames are stale.")
    episode, timeline, start, stop, intro_frames, outro_frames = plan_promo(source_manifest["episode"], original)
    make_ass(episode, timeline)
    for name, value in (("episode.json", episode), ("timeline.json", timeline)):
        atomic_json(build / name, value)
    with wave.open(str(source / "dialogue.wav"), "rb") as input_audio:
        samples = input_audio.getframerate() // original["fps"]
        input_audio.setpos(start * samples)
        speech = input_audio.readframes((stop - start) * samples)
        with wave.open(str(build / "dialogue.wav"), "wb") as output:
            output.setparams(input_audio.getparams())
            output.writeframes(bytes(intro_frames * samples * 2) + speech + bytes(outro_frames * samples * 2))
    step = source_manifest["motion_step"]
    (build / "frames").mkdir(exist_ok=True)
    for frame in range(1, timeline["total_frames"] + 1, step):
        requested = min(stop, max(start + 1, start + frame - intro_frames))
        source_index = 1 + (requested - 1) // step * step
        link_frame(source / "frames" / f"frame_{source_index:04d}.png",
                   build / "frames" / f"frame_{frame:04d}.png")
    shutil.copy2(source / "studio.blend", build / "studio.blend")
    manifest = {**source_manifest, "episode": episode, "timeline": timeline, "derived_edit": {
        "source": str(source), "scene_sha256": scene_hash(source),
        "source_start_frame_zero_based": start, "source_stop_frame_exclusive": stop,
        "intro_hold_frames": intro_frames, "outro_hold_frames": outro_frames,
        "pose_sampling": f"Previous source pose at each edit sample; maximum offset {(step - 1) / original['fps']:.6f}s.",
        "scene_note": "studio.blend is the full source scene; the promo edit is defined by this manifest.",
        "audio": "Exact PCM crop, silent bookends; no interior cuts, resynthesis or time stretching.",
    }}
    atomic_json(build / "scene_manifest.json", manifest)
    atomic_json(build / "frames_manifest.json", {"scene": manifest, "blend_sha256": scene_hash(build)})
    (build / "subtitles.srt").write_text(subtitles(timeline), encoding="utf-8")
    make_ass(episode, timeline)
    mux(build, build / "episode.json")
    print(f"Promo: {timeline['duration']:.3f}s, turns {[turn['id'] for turn in timeline['turns']]}")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("v3", "scene", "promo", "repair-door", "revise-cameras"))
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--episode", type=Path)
    parser.add_argument("--profile", choices=tuple(PROFILES), default="preview")
    args = parser.parse_args(argv)
    if args.stage in ("promo", "revise-cameras"):
        if args.source is None:
            parser.error("--source is required for derived edits")
        if args.stage == "promo":
            promo(args.build.resolve(), args.source.resolve())
        else:
            revise_cameras(args.build.resolve(), args.source.resolve(), args.episode)
        return
    if args.stage == "scene":
        scene_build(args.build.resolve(), args.episode, args.profile)
        return
    {"v3": social_exchange, "scene": scene_build, "promo": promo,
     "repair-door": repair_door}[args.stage](args.build.resolve())


if __name__ == "__main__":
    main()
