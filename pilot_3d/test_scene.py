"""Blender-side integration checks against the saved production scene."""

import json
import math
import sys
from pathlib import Path

import bpy


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    build = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
    timeline = json.loads((build / "timeline.json").read_text())
    scene = bpy.context.scene
    check(scene.frame_end == round(timeline["duration"] * timeline["fps"]), "Scene duration mismatch")
    check(len([obj for obj in scene.objects if obj.type == "CAMERA"]) == 5, "Expected five cameras")
    actors = {}
    for name in ("candidate_a", "candidate_b", "examiner", "observer"):
        root = scene.objects.get(name)
        check(root is not None, f"Missing actor {name}")
        rigs = [obj for obj in root.children_recursive if obj.type == "ARMATURE" and obj.get("actor") == name]
        check(len(rigs) == 1, f"Missing unique native rig for {name}")
        rig = rigs[0]
        check(len(rig.pose.bones) > 500, f"Incomplete native character rig: {name}")
        jaw_name = "Jaw" if root["asset"] == "snow" else "MSTR-Jaw"
        actors[name] = (rig, jaw_name)
        check("CC" in root["credit"], f"Missing attribution: {name}")
    scene.frame_set(1)
    distance = (scene.objects["candidate_a"].location - scene.objects["candidate_b"].location).length
    check(distance > 0.5, "Candidates overlap at the entrance")
    for turn in timeline["turns"]:
        check(turn["mouth_cues"], f"Missing mouth cues for {turn['id']}")
        frame = 1 + round((turn["start"] + min(0.5, turn["duration"] / 2)) * timeline["fps"])
        scene.frame_set(frame)
        expected = {"wide": "01", "examiner": "02", "candidates": "03", "candidate_a": "04", "candidate_b": "05"}[turn["camera"]]
        check(scene.camera.name.startswith(expected), f"Wrong camera for turn {turn['id']}")
        for actor, (rig, jaw_name) in actors.items():
            values = list(rig.pose.bones[jaw_name].rotation_euler)
            check(all(math.isfinite(v) and abs(v) <= 0.25 for v in values), f"Invalid jaw pose on {actor}")
            if actor != turn["speaker"]:
                check(max(abs(value) for value in values) < 0.01, f"Listener {actor} is lip-syncing someone else's audio")
        check(scene.camera.location.y > -3.4, f"Camera behind the studio wall: {turn['id']}")
    scene.frame_set(300)
    for actor, (rig, jaw_name) in actors.items():
        foot_heights = [
            (rig.matrix_world @ rig.pose.bones[f"IK-Foot.{side}"].head).z
            for side in ("L", "R")
        ]
        check(all(0.03 < value < 0.16 for value in foot_heights), f"Feet not planted: {actor}")
        hand_name = "IK-Wrist" if scene.objects[actor]["asset"] == "snow" else "IK-Hand"
        for side in ("L", "R"):
            hand_height = (rig.matrix_world @ rig.pose.bones[f"{hand_name}.{side}"].head).z
            check(0.87 < hand_height < 1.16, f"Hands below tabletop: {actor} {side} {hand_height}")
    scene.frame_set(453)
    head = actors["candidate_b"][0].pose.bones["FK-Head"]
    check(head.rotation_euler.y < -0.4, "Partner gaze must turn around the native head's vertical Y axis")
    check(abs(head.rotation_euler.z) < 0.08, "Partner gaze must not roll the head sideways")
    scene.frame_set(scene.frame_end)
    for name, (rig, jaw_name) in actors.items():
        check(max(abs(value) for value in rig.pose.bones[jaw_name].rotation_euler) < 0.01, f"Mouth not at rest after dialogue: {name}")
    check(all(image.packed_file for image in bpy.data.images if image.source == "FILE" and image.size[0]), "Unpacked character textures")
    print("Scene checks passed: four native rigs, five cameras, isolated lip sync, feet/hands, textures and duration.")


if __name__ == "__main__":
    main()
