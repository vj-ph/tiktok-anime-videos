#!/usr/bin/env python3
"""Make a non-destructive, ten-second acting study from the completed V2 scene."""

import argparse
import copy
import hashlib
import json
import math
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from build_paths import BUILDS, build_directory, resolve_build_reference

MOUTH_POSES = {
    # Jaw, width, forward lip rounding, closure.
    "X": (0.0, 1.0, 0.0, 0.0),
    "A": (0.0, 0.97, 0.0, 1.0),
    "B": (0.035, 1.025, 0.0, 0.0),
    "C": (0.075, 1.065, 0.0, 0.0),
    "D": (0.125, 1.015, 0.12, 0.0),
    "E": (0.065, 0.83, 0.55, 0.0),
    "F": (0.045, 0.70, 0.90, 0.0),
    "G": (0.006, 0.985, 0.0, 0.45),
    "H": (0.045, 1.025, 0.0, 0.0),
}


def smooth(value):
    value = min(1.0, max(0.0, value))
    return value * value * (3 - 2 * value)


def pulse(t, start, length):
    phase = (t - start) / length
    return math.sin(math.pi * phase) ** 2 if 0 < phase < 1 else 0.0


def mouth_pose(cues, t):
    """Short coarticulation ramps retain the center of brief closed-lip cues."""
    rest = MOUTH_POSES["X"]
    for index, cue in enumerate(cues):
        if cue["start"] <= t < cue["end"]:
            pose = MOUTH_POSES[cue["value"]]
            if cue["value"] == "A":
                return pose
            ramp = min(0.022, (cue["end"] - cue["start"]) / 3)
            if t - cue["start"] < ramp:
                previous = MOUTH_POSES[cues[index - 1]["value"]] if index else rest
                weight = smooth((t - cue["start"]) / ramp)
                return tuple(a + (b - a) * weight for a, b in zip(previous, pose))
            if cue["end"] - t < ramp:
                following = MOUTH_POSES[cues[index + 1]["value"]] if index + 1 < len(cues) else rest
                weight = smooth((t - cue["end"] + ramp) / ramp)
                return tuple(a + (b - a) * weight for a, b in zip(pose, following))
            return pose
    return rest


def exchange_inputs(episode, timeline):
    if episode["fps"] != timeline["fps"]:
        raise ValueError("Source episode and timeline frame rates differ.")
    selected = [turn for turn in timeline["turns"] if turn["id"] in ("05", "06")]
    if [turn["id"] for turn in selected] != ["05", "06"]:
        raise ValueError("The V3 acting study requires the source proposal/agreement turns 05 and 06.")
    fps = timeline["fps"]
    start = selected[0]["start_frame"] - round(0.25 * fps)
    stop = start + 10 * fps
    if start < 0 or selected[-1]["end_frame"] > stop:
        raise ValueError("Selected dialogue does not fit the ten-second study.")
    result = copy.deepcopy(episode)
    result.update(
        id="dtz_ausflug_v3_exchange", presentation="exchange", visual_version=3,
        intro_seconds=selected[0]["start"] - start / fps,
        outro_seconds=(stop - selected[-1]["end_frame"]) / fps,
    )
    original_turns = {turn["id"]: turn for turn in episode["turns"]}
    turns, screenplay = [], []
    for source in selected:
        turn = copy.deepcopy(source)
        for field in ("start_frame", "end_frame"):
            turn[field] -= start
        turn["start"], turn["end"] = turn["start_frame"] / fps, turn["end_frame"] / fps
        turn["camera"] = turn["speaker"]
        turns.append(turn)
        line = copy.deepcopy(original_turns[turn["id"]])
        line["camera"] = turn["camera"]
        screenplay.append(line)
    result["turns"] = screenplay
    clock = {
        "fps": fps, "intro_seconds": result["intro_seconds"],
        "outro_seconds": result["outro_seconds"], "duration": 10.0,
        "total_frames": stop - start, "turns": turns,
    }
    return result, clock, start, stop


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_fingerprints(source):
    return {name: file_hash(source / name) for name in
            ("studio.blend", "pilot.mp4", "pilot_clean.mp4", "dialogue.wav", "scene_manifest.json")}


def prepare(source, build):
    from prepare_audio import subtitles

    if source == build or source in build.parents or build in source.parents:
        raise ValueError("V3 must use a separate sibling output directory.")
    manifest = json.loads((source / "scene_manifest.json").read_text())
    episode, timeline, start, stop = exchange_inputs(manifest["episode"], manifest["timeline"])
    before = source_fingerprints(source)
    build.mkdir(parents=True, exist_ok=True)
    with wave.open(str(source / "dialogue.wav"), "rb") as original:
        if original.getframerate() % timeline["fps"]:
            raise ValueError("Audio samples must align exactly to the source video clock.")
        samples_per_frame = original.getframerate() // timeline["fps"]
        if stop * samples_per_frame > original.getnframes():
            raise ValueError("The requested excerpt exceeds the source audio.")
        original.setpos(start * samples_per_frame)
        samples = original.readframes((stop - start) * samples_per_frame)
        with wave.open(str(build / "dialogue.wav"), "wb") as output:
            output.setparams(original.getparams())
            output.writeframes(samples)
    for filename, value in (("episode.json", episode), ("timeline.json", timeline)):
        (build / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    (build / "subtitles.srt").write_text(subtitles(timeline), encoding="utf-8")
    provenance = {
        "source": str(source), "source_files_sha256": before,
        "start_frame_zero_based": start, "stop_frame_exclusive": stop,
        "audio_edit": "Exact PCM sample crop only; no resynthesis, interior cuts or time stretching.",
    }
    (build / "source_excerpt.json").write_text(json.dumps(provenance, indent=2) + "\n")
    if source_fingerprints(source) != before:
        raise RuntimeError("Source files changed while preparing the excerpt.")
    print(f"Prepared {timeline['duration']:.2f}s from source frames {start}:{stop} in {build}")


def animate_actor(actor, timeline):
    import bpy
    from mathutils import Matrix, Vector
    from studio_characters import key

    first, second = timeline["turns"]
    sign = 1 if actor.name == "candidate_a" else -1
    is_rain = actor.kind == "rain"
    top_lip = "MSTR-UpperLip" if is_rain else "MSTR-Lip_Top"
    bottom_lip = "MSTR-LowerLip" if is_rain else "MSTR-Lip_Bottom"
    upper_lid = "ACT-Eyelid_Upper" if is_rain else "MSTR-Eyelid_Upper"
    lower_lid = "ACT-Eyelid_Lower" if is_rain else "MSTR-Eyelid_Lower"
    required = [top_lip, bottom_lip]
    required += [name + "." + side for name in (upper_lid, lower_lid, "ACT-Lips_Corner", "MSTR-Eyebrow") for side in ("L", "R")]
    if is_rain:
        required += [f"FK-Hair_Ponytail{index}" for index in range(1, 5)]
    missing = [name for name in required if name not in actor.bones]
    if missing:
        raise ValueError(f"{actor.name} lacks performance controls: {missing}")

    def offset(name, delta, frame):
        bone = actor.bones[name]
        bone.location = actor.rest[name].to_3x3().inverted() @ Vector(delta)
        key(bone, frame)

    for frame in range(1, timeline["total_frames"] + 1):
        t = (frame - 1) / timeline["fps"]
        turn = next((turn for turn in timeline["turns"] if turn["start"] <= t < turn["end"]), None)
        speaking = turn is not None and turn["speaker"] == actor.name
        own_turn = first if is_rain else second
        phase = t - own_turn["start"]
        gesture = pulse(phase, 0.5, 1.6) if is_rain else 0.55 * pulse(phase, 2.25, 1.45)
        question = pulse(t, first["start"] + 2.55, 1.45)
        agreement = pulse(t, second["start"] + 0.36, 0.72)
        response = pulse(t, second["start"] + 0.65, 0.8) + 0.8 * pulse(t, second["end"] - 0.2, 0.65)
        nod = 0.075 * (response if is_rain else agreement)
        if not is_rain:
            nod += 0.045 * pulse(t, first["end"] - 0.55, 0.62)
        glance = pulse(t, second["start"] + 1.55, 0.72) if is_rain else 0.0
        yaw = sign * (0.38 - 0.11 * glance)
        actor.rotate("FK-Chest", (0.018 * gesture, sign * 0.075, 0), frame)
        actor.rotate("FK-Head", (nod + 0.20 * glance, yaw, sign * 0.018 * question), frame)
        bpy.context.view_layer.update()
        eye_height = 1.24 if is_rain else 1.37
        partner = Vector((sign * 1.75, -1.65, eye_height - 0.015))
        paper = Vector((sign * 0.15, -0.95, eye_height - 0.30))
        actor.position("TGT-Eyes", partner.lerp(paper, glance), frame)

        jaw, width, rounding, seal = mouth_pose(turn["mouth_cues"], t - turn["start"]) if speaking else MOUTH_POSES["X"]
        actor.rotate(actor.jaw_name, (jaw, 0, 0), frame)
        mouth = actor.bones["MSTR-Mouth"]
        mouth.scale = (width, 1, 1)
        key(mouth, frame)
        offset("MSTR-Mouth", (0, -0.004 * rounding, 0), frame)
        offset(top_lip, (0, -0.0015 * rounding, -0.0011 * seal), frame)
        offset(bottom_lip, (0, -0.0018 * rounding, 0.0017 * seal), frame)
        smile = (0.25 + 0.35 * response) if is_rain else (0.18 + 0.40 * agreement)
        smile *= 0.25 if speaking else 1
        blink_starts = (2.55, 6.55, 9.60) if is_rain else (1.30, 4.55, 7.00)
        blink = max(pulse(t, start, 0.16) for start in blink_starts)
        for side, side_sign in (("L", 1), ("R", -1)):
            offset("ACT-Lips_Corner." + side, (side_sign * 0.0015 * smile, 0, 0.003 * smile), frame)
            brow = 0.0017 * question * (1.0 if side == "L" else 0.65) if is_rain else 0.0014 * agreement
            offset("MSTR-Eyebrow." + side, (0, 0, brow), frame)
            lid_height = -((0.004 + 0.007 * glance) * (1 - blink) + 0.040 * blink) if is_rain else -0.003 - 0.027 * blink
            offset(upper_lid + "." + side, (0, 0, lid_height), frame)
            offset(lower_lid + "." + side, (0, 0, 0.0008 - 0.001 * glance + 0.003 * blink), frame)
            if is_rain:
                for region in ("Upper", "Lower"):
                    offset(f"MSTR-Eyering_{region}.{side}", (0, 0, 0), frame)
            lift = (0.045 if side == "L" else 0.009) * gesture
            wrist_height = 0.902 if is_rain else 0.91
            hand = (side_sign * (0.24 + 0.022 * gesture), -0.38 - 0.025 * gesture, wrist_height / actor.scale + lift)
            rotation = Matrix.Rotation(side_sign * gesture * (0.65 if side == "L" else 0.12), 4, "Y") @ Matrix.Rotation(-side_sign * math.pi / 2, 4, "Z")
            actor.position(actor.hand_name + "." + side, hand, frame, rotation)
        if is_rain:
            for index, angle in enumerate((-0.70, -0.48, -0.12, 0.10), 1):
                actor.rotate(f"FK-Hair_Ponytail{index}", (angle + (0.012 * nod if index > 1 else 0), 0, 0), frame)
    for curve in actor.rig.animation_data.action.fcurves:
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR"


def scene_build(source, build):
    import bpy
    from mathutils import Vector
    from studio_characters import StudioCharacter

    episode = json.loads((build / "episode.json").read_text())
    timeline = json.loads((build / "timeline.json").read_text())
    provenance = json.loads((build / "source_excerpt.json").read_text())
    if source_fingerprints(source) != provenance["source_files_sha256"]:
        raise ValueError("V2 source changed; prepare the excerpt again.")
    scene = bpy.context.scene
    start = provenance["start_frame_zero_based"]
    scene.frame_set(start + 1)
    for obj in scene.objects:
        if obj.animation_data and obj.animation_data.action:
            obj.animation_data.action = obj.animation_data.action.copy()
            for curve in obj.animation_data.action.fcurves:
                for point in curve.keyframe_points:
                    point.co.x -= start
                    point.handle_left.x -= start
                    point.handle_right.x -= start
    for name in ("candidate_a", "candidate_b", "observer"):
        actor = StudioCharacter.from_scene(name)
        if name != "observer":
            actor.restore_native_drivers()
            animate_actor(actor, timeline)
        else:
            for index, angle in enumerate((-0.70, -0.48, -0.12, 0.10), 1):
                actor.rotate(f"FK-Hair_Ponytail{index}", (angle, 0, 0), 1)
    for name in ("examiner", "observer"):
        for obj in scene.objects[name].children_recursive:
            if obj.type == "MESH":
                obj.hide_render = True
    cameras = {key: next(obj for obj in scene.objects if obj.type == "CAMERA" and obj.name.startswith(prefix))
               for key, prefix in (("candidate_a", "04"), ("candidate_b", "05"))}
    for name, location, target in (
        ("candidate_a", (-1.35, -1.60, 1.62), (-0.82, 0.65, 1.17)),
        ("candidate_b", (1.35, -1.60, 1.65), (0.82, 0.65, 1.20)),
    ):
        camera = cameras[name]
        camera.location = location
        camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
        camera.data.lens = 52
    scene.timeline_markers.clear()
    # Brief listener cutaways precede and follow the reply without changing audio.
    shots = [(0, "candidate_a"), (3.5, "candidate_b"), (6.65, "candidate_a"),
             (7.65, "candidate_b"), (9.35, "candidate_a")]
    for t, actor in shots:
        marker = scene.timeline_markers.new(actor, frame=1 + round(t * timeline["fps"]))
        marker.camera = cameras[actor]
    scene.camera = cameras["candidate_a"]
    editor = scene.sequence_editor_create()
    for strip in list(editor.sequences):
        editor.sequences.remove(strip)
    sound = editor.sequences.new_sound("Original Qwen exchange · exact sample crop", str(build / "dialogue.wav"), channel=1, frame_start=1)
    scene.frame_start, scene.frame_end = 1, timeline["total_frames"]
    scene.render.fps = timeline["fps"]
    scene.render.resolution_x, scene.render.resolution_y = 720, 1280
    scene.render.resolution_percentage = 100
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 12
    scene.render.use_persistent_data = True
    scene["render_note"] = "Version 3 · ten-second authored acting study · 24 distinct poses/sec"
    scene["lip_sync"] = "Rhubarb cues with short coarticulation ramps, native lip closures/rounding and listener silence"
    (build / "frames").mkdir(exist_ok=True)
    scene.render.filepath = str(build / "frames" / "frame_")
    scene.frame_set(1)
    bpy.ops.file.pack_all()
    sound.sound.filepath = "//dialogue.wav"
    bpy.ops.wm.save_as_mainfile(filepath=str(build / "studio.blend"), compress=True)
    manifest = {
        "episode": episode, "timeline": timeline, "width": 720, "height": 1280,
        "motion_step": 1, "visual_version": 3, "engine": "cycles", "samples": 12,
        "source_excerpt": provenance,
        "source_sha256": {name: file_hash(ROOT / name) for name in
                          ("polish_exchange.py", "studio_characters.py", "render.py")},
    }
    (build / "scene_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved V3 performance: {build / 'studio.blend'}")


def check_scene(source, build):
    import bpy

    from studio_characters import StudioCharacter

    scene = bpy.context.scene
    clock = json.loads((build / "timeline.json").read_text())
    provenance = json.loads((build / "source_excerpt.json").read_text())
    actors = {name: StudioCharacter.from_scene(name) for name in ("candidate_a", "candidate_b")}
    if (scene.frame_start, scene.frame_end, scene.render.fps) != (1, 240, 24):
        raise RuntimeError("V3 must contain exactly 240 frames at 24 fps.")
    if source_fingerprints(source) != provenance["source_files_sha256"]:
        raise RuntimeError("V2 source files were modified.")
    scene.frame_set(1)
    for actor in actors.values():
        drivers = actor.rig.animation_data.drivers
        if len(drivers) != actor.rig.get("native_driver_count", -1):
            raise RuntimeError(f"Missing native deformation drivers: {actor.name}")
        invalid = [curve.data_path for curve in drivers if not curve.driver.is_valid]
        if invalid:
            raise RuntimeError(f"Invalid native drivers for {actor.name}: {invalid[:5]}")
    rain = actors["candidate_a"]
    drop = (rain.rig.matrix_world @ rain.bones["FK-Hair_Ponytail1"].head).z - (
        rain.rig.matrix_world @ rain.bones["FK-Hair_Ponytail4"].tail).z
    if drop < 0.15:
        raise RuntimeError(f"Ponytail must hang down; measured vertical drop is {drop:.3f}m.")
    report = {"hair_tip_drop_m": drop, "frames": 240, "fps": 24, "source_files_unchanged": True}
    fingertips = {}
    for name, actor in actors.items():
        prefix = "FK-" if actor.kind == "rain" else "FK-Finger_"
        heights = [(actor.rig.matrix_world @ actor.bones[f"{prefix}{finger}3.{side}"].tail).z
                   for finger in ("Index", "Middle") for side in ("L", "R")]
        if not all(0.884 < height < 0.903 for height in heights):
            raise RuntimeError(f"Resting fingertips must sit just above the tabletop: {name}, {heights}")
        fingertips[name] = heights
    report["resting_fingertip_heights_m"] = fingertips
    samples = []
    for frame in (1, 25, 49, 85, 109, 137, 169, 201, 233, 240):
        scene.frame_set(frame)
        t = (frame - 1) / 24
        turn = next((turn for turn in clock["turns"] if turn["start"] <= t < turn["end"]), None)
        for name, actor in actors.items():
            jaw = actor.bones[actor.jaw_name].rotation_euler.x
            if not math.isfinite(jaw) or not 0 <= jaw <= 0.15:
                raise RuntimeError(f"Invalid V3 jaw: {name}, frame {frame}, {jaw}")
            if (not turn or turn["speaker"] != name) and abs(jaw) > 0.0001:
                raise RuntimeError(f"Listener mouth moves with the speaker: {name}, frame {frame}")
            if abs(actor.head.rotation_euler.z) > 0.04:
                raise RuntimeError(f"Excessive head roll: {name}, frame {frame}")
            for side in ("L", "R"):
                height = (actor.rig.matrix_world @ actor.bones[actor.hand_name + "." + side].head).z
                if not 0.88 < height < 1.03:
                    raise RuntimeError(f"V3 hand outside tabletop performance range: {name}, frame {frame}, {height}")
            samples.append({"frame": frame, "actor": name, "jaw": jaw})
    report["sampled_performances"] = samples
    closures = []
    for turn in clock["turns"]:
        actor = actors[turn["speaker"]]
        curve = actor.rig.animation_data.action.fcurves.find(
            f'pose.bones["{actor.jaw_name}"].rotation_euler', index=0)
        if not curve or len([point for point in curve.keyframe_points if 1 <= point.co.x <= 240]) != 240:
            raise RuntimeError(f"Missing full-rate facial animation: {actor.name}")
        for cue in turn["mouth_cues"]:
            if cue["value"] != "A":
                continue
            frame = 1 + round((turn["start"] + (cue["start"] + cue["end"]) / 2) * 24)
            scene.frame_set(frame)
            if abs(actor.bones[actor.jaw_name].rotation_euler.x) > 0.0001:
                raise RuntimeError(f"Closed-lip cue was lost at the rendered frame rate: {actor.name}, frame {frame}")
            if abs(actor.bones["MSTR-Mouth"].scale.x - MOUTH_POSES["A"][1]) > 0.0001:
                raise RuntimeError(f"Closed-lip width is not wired to the native mouth: {actor.name}, frame {frame}")
            closures.append({"actor": actor.name, "frame": frame})
    scene.frame_set(163)
    if not scene.camera.name.startswith("04") or actors["candidate_a"].head.rotation_euler.x < 0.12:
        raise RuntimeError("The listener's task-sheet glance must be visible in its scheduled cutaway.")
    head_mesh = next(obj for obj in rain.root.children_recursive
                     if obj.type == "MESH" and obj.name.startswith("GEO-rain-head"))
    lid_closure = head_mesh.data.shape_keys.key_blocks["EyelidsClose.L"].value
    if lid_closure < 0.20:
        raise RuntimeError("The downward gaze must drive Rain's actual eyelid shape, not only the eye-ring helper.")
    report["glance_eyelid_shape_weight"] = lid_closure
    scene.frame_set(230)
    if not scene.camera.name.startswith("04") or actors["candidate_a"].head.rotation_euler.x < 0.015:
        raise RuntimeError("The final acknowledgment must be visible on camera.")
    report["verified_closed_lip_frames"] = closures
    scene.frame_set(64)
    if head_mesh.data.shape_keys.key_blocks["EyelidsClose.L"].value < 0.95:
        raise RuntimeError("Rain's blink must close the actual eyelid shape.")
    scene.frame_set(112)
    snow = actors["candidate_b"]
    close_action = next(constraint for constraint in snow.bones["Eyelid_Upper3.L"].constraints
                        if constraint.type == "ACTION" and "CloseOpen" in constraint.name)
    if close_action.eval_time < 0.98:
        raise RuntimeError("Snow's blink must drive its actual deformation action.")
    report["native_driver_counts"] = {name: len(actor.rig.animation_data.drivers) for name, actor in actors.items()}
    report["native_driver_compatibility"] = {
        name: actor.rig["driver_compatibility"] for name, actor in actors.items() if actor.rig.get("driver_compatibility")
    }
    (build / "scene_checks.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"V3 scene checks passed: hair drop {drop:.3f}m, isolated mouths, hands, head axes, 240 frames, unchanged V2.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "scene", "check"))
    parser.add_argument("--source", type=Path, default=BUILDS / "v2")
    parser.add_argument("--build", type=Path, default=BUILDS / "v3_exchange")
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    args = parser.parse_args(arguments)
    source, build = resolve_build_reference(args.source), build_directory(args.build)
    if args.stage == "prepare":
        prepare(source, build)
    elif args.stage == "scene":
        scene_build(source, build)
    else:
        check_scene(source, build)


if __name__ == "__main__":
    main()
