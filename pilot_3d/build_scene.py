"""Run with Blender's Python: create the editable studio and render its frames."""

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector
sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio_characters import CREDITS, StudioCharacter


def material(name, color, roughness=0.65):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = roughness
    if name in ("wood", "floor"):
        nodes = mat.node_tree.nodes
        texture = nodes.new("ShaderNodeTexNoise")
        texture.inputs["Scale"].default_value = 4
        texture.inputs["Detail"].default_value = 2
        coordinates = nodes.new("ShaderNodeTexCoord")
        mapping = nodes.new("ShaderNodeVectorMath")
        mapping.operation = "MULTIPLY"
        mapping.inputs[1].default_value = (3, 85, 4)
        mat.node_tree.links.new(coordinates.outputs["Generated"], mapping.inputs[0])
        mat.node_tree.links.new(mapping.outputs["Vector"], texture.inputs["Vector"])
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (*(component * 0.7 for component in color), 1)
        ramp.color_ramp.elements[1].color = (*color, 1)
        mat.node_tree.links.new(texture.outputs["Fac"], ramp.inputs[0])
        mat.node_tree.links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    return mat


def finish(obj, name, mat, parent=None):
    obj.name = name
    obj.data.materials.append(mat)
    if parent:
        obj.parent = parent
    return obj


def box(name, pos, size, mat, bevel=0.04, parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=pos)
    obj = bpy.context.object
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = obj.modifiers.new("Soft edges", "BEVEL")
        mod.width, mod.segments = bevel, 3
        obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
    return finish(obj, name, mat, parent)


def ellipsoid(name, pos, scale, mat, parent=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16, radius=1, location=pos)
    obj = bpy.context.object
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for face in obj.data.polygons:
        face.use_smooth = True
    return finish(obj, name, mat, parent)


def empty(name, pos=(0, 0, 0), parent=None):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.location = pos
    obj.parent = parent
    return obj


def segment(name, start, end, radius, mat, parent=None):
    obj = ellipsoid(name, (0, 0, 0), (radius, radius, 1), mat, parent)
    pose_segment(obj, start, end)
    return obj


def pose_segment(obj, start, end):
    a, b = Vector(start), Vector(end)
    obj.location = (a + b) / 2
    obj.rotation_euler = (b - a).to_track_quat("Z", "Y").to_euler()
    obj.scale.z = (b - a).length / 2 + 0.025


def key_transform(obj, frame):
    for prop in ("location", "rotation_euler", "scale"):
        obj.keyframe_insert(data_path=prop, frame=frame)


def smoothstep(value):
    value = max(0, min(1, value))
    return value * value * (3 - 2 * value)


def chair(x, y, angle, mats):
    root = empty("Chair", (x, y, 0))
    root.rotation_euler.z = angle
    box("Upholstered seat", (0, 0, 0.52), (0.63, 0.59, 0.12), mats["chair"], parent=root)
    box("Chair back", (0, 0.25, 0.96), (0.62, 0.1, 0.74), mats["chair"], parent=root)
    for dx in (-0.24, 0.24):
        for dy in (-0.21, 0.21):
            box("Chair leg", (dx, dy, 0.25), (0.045, 0.045, 0.5), mats["metal"], 0.01, root)


def room(mats):
    box("Floor", (0, 0, -0.1), (9, 9, 0.2), mats["floor"])
    box("Back wall", (0, 3.35, 1.75), (9, 0.18, 3.5), mats["wall"])
    box("Left wall", (-4, 0.5, 1.75), (0.18, 5.7, 3.5), mats["wall"])
    box("Front wall", (0, -3.5, 1.75), (8, 0.14, 3.5), mats["wall"])
    box("Wall skirting", (0, 3.23, 0.09), (8, 0.07, 0.17), mats["wood"])
    box("Door frame", (-2.9, 3.18, 1.2), (1.17, 0.12, 2.4), mats["wood"])
    box("Door", (-2.9, 3.09, 1.15), (1.02, 0.07, 2.25), mats["door"])
    box("Door handle", (-2.53, 3.0, 1.12), (0.17, 0.08, 0.045), mats["metal"], 0.02)
    box("Wall art frame", (1.35, 3.2, 2), (1.6, 0.08, 0.95), mats["wood"])
    box("Wall art", (1.35, 3.14, 2), (1.48, 0.035, 0.83), mats["paper"])
    for i, color in enumerate(("teal", "gold", "chair")):
        ellipsoid("Abstract print", (0.92 + i * 0.4, 3.1, 2), (0.22, 0.018, 0.28), mats[color])
    box("Window frame", (-3.86, 0.7, 2), (0.08, 2.1, 1.65), mats["wood"])
    box("Soft daylight window", (-3.8, 0.7, 2), (0.04, 1.96, 1.5), mats["sky"])
    box("Window divider", (-3.75, 0.7, 2), (0.08, 0.045, 1.53), mats["paper"])
    box("Exam table", (0, -0.45, 0.82), (2.7, 1.25, 0.12), mats["wood"], 0.07)
    for x in (-1.12, 1.12):
        for y in (-0.92, 0.02):
            box("Table leg", (x, y, 0.39), (0.07, 0.07, 0.78), mats["metal"], 0.015)
    for x in (-0.78, 0.75):
        obj = box("Task sheet", (x, -0.13, 0.888), (0.37, 0.28, 0.012), mats["paper"], 0.005)
        obj.rotation_euler.z = 0.08 if x < 0 else -0.12
        for j in range(4):
            box("Printed task line", (x, -0.2 + j * 0.045, 0.897), (0.24, 0.006, 0.002), mats["ink"], 0)
        box("Pen", (x + 0.26, -0.18, 0.903), (0.025, 0.21, 0.025), mats["teal"], 0.01)
    box("Examiner clipboard", (0.65, -0.78, 0.902), (0.43, 0.3, 0.035), mats["teal"], 0.01)
    box("Examiner notes", (0.65, -0.78, 0.924), (0.36, 0.25, 0.006), mats["paper"], 0.002)
    for x in (-0.82, 0.82):
        chair(x, 0.65, 0, mats)
        chair(x, -1.6, math.pi, mats)
    ellipsoid("Plant pot", (2.8, 2.4, 0.28), (0.3, 0.3, 0.35), mats["pot"])
    for i in range(9):
        angle = i * 2.4
        tip = (2.8 + 0.4 * math.cos(angle), 2.4 + 0.4 * math.sin(angle), 1.0 + 0.12 * (i % 3))
        segment("Plant stem", (2.8, 2.4, 0.45), tip, 0.018, mats["leaf"])
        obj = ellipsoid("Leaf", tip, (0.11, 0.045, 0.26), mats["leaf"])
        obj.rotation_euler = (0.5, 0.4, angle)
    for i in range(15):
        box("Acoustic oak slat", (2.1 + i * 0.095, 3.20, 1.8), (0.045, 0.08, 2.5), mats["wood"], 0.008)
    for i in range(4):
        box("Floor board seam", (-3 + i * 1.7, 0, 0.005), (0.009, 8, 0.004), mats["floor"], 0)
    for x in (-0.78, 0.78):
        box("Water cup", (x, -0.48, 0.96), (0.075, 0.075, 0.15), mats["paper"], 0.028)
    for pos, target, power, size, color in (
        ((-2.8, -0.7, 3.4), (0, 0, 1), 260, 3.0, (0.83, 0.92, 1.0)),
        ((2.5, -2.2, 3.2), (0, 0, 1.2), 120, 3.0, (1.0, 0.84, 0.68)),
        ((0, 2.5, 3.4), (0, 0.4, 1.2), 180, 2.0, (1.0, 0.91, 0.79)),
    ):
        bpy.ops.object.light_add(type="AREA", location=pos)
        lamp = bpy.context.object
        lamp.data.energy, lamp.data.shape, lamp.data.size = power, "DISK", size
        lamp.data.color = color
        lamp.rotation_euler = (Vector(target) - lamp.location).to_track_quat("-Z", "Y").to_euler()


VISEMES = {
    "A": (0.055, 0.006), "B": (0.064, 0.019), "C": (0.065, 0.047),
    "D": (0.061, 0.068), "E": (0.045, 0.045), "F": (0.029, 0.027),
    "G": (0.062, 0.013), "H": (0.065, 0.03), "X": (0.055, 0.006),
}


class Character:
    def __init__(self, name, pos, angle, skin, shirt, hair, mats, female=False):
        self.name = name
        self.root = empty(name, pos)
        self.root.rotation_euler.z = angle
        self.body = empty(name + " torso control", parent=self.root)
        self.head = empty(name + " head control", (0, 0, 1.62), self.body)
        ellipsoid("Trouser hips", (0, 0, 0.73), (0.23, 0.15, 0.15), mats["trousers"], self.body)
        ellipsoid("Tailored jacket", (0, 0.01, 1.1), (0.25, 0.16, 0.34), shirt, self.body)
        box("Shirt front", (0, -0.155, 1.18), (0.12, 0.02, 0.28), mats["paper"], 0.02, self.body)
        for side in (-1, 1):
            obj = box("Jacket lapel", (side * 0.09, -0.16, 1.26), (0.075, 0.025, 0.22), shirt, 0.015, self.body)
            obj.rotation_euler.y = side * -0.25
        ellipsoid("Neck", (0, 0, 1.4), (0.085, 0.08, 0.13), skin, self.body)
        ellipsoid("Head", (0, 0, 0), (0.215, 0.185, 0.27), skin, self.head)
        for side in (-1, 1):
            ellipsoid("Ear", (side * 0.214, 0, -0.005), (0.042, 0.035, 0.067), skin, self.head)
            ellipsoid("Eye white", (side * 0.086, -0.168, 0.04), (0.052, 0.025, 0.036), mats["paper"], self.head)
            ellipsoid("Iris", (side * 0.086, -0.191, 0.04), (0.025, 0.009, 0.026), mats["iris"], self.head)
            ellipsoid("Pupil", (side * 0.086, -0.199, 0.04), (0.012, 0.006, 0.018), mats["ink"], self.head)
            ellipsoid("Eye sparkle", (side * 0.086 - 0.006, -0.205, 0.05), (0.005, 0.003, 0.006), mats["paper"], self.head)
            brow = ellipsoid("Eyebrow", (side * 0.09, -0.175, 0.105), (0.059, 0.014, 0.012), hair, self.head)
            brow.rotation_euler.y = side * -0.08
        self.lids = [
            ellipsoid("Blink lid", (side * 0.086, -0.194, 0.04), (0.055, 0.014, 0.037), skin, self.head)
            for side in (-1, 1)
        ]
        ellipsoid("Nose", (0, -0.189, -0.023), (0.029, 0.032, 0.04), skin, self.head)
        ellipsoid("Lower lip", (0, -0.17, -0.132), (0.058, 0.018, 0.014), skin, self.head)
        mouth = ellipsoid("Mouth viseme mesh", (0, -0.178, -0.108), (0.055, 0.016, 0.006), mats["mouth"], self.head)
        mouth.shape_key_add(name="Basis")
        for cue, (width, height) in VISEMES.items():
            key = mouth.shape_key_add(name=cue)
            for point in key.data:
                point.co.x *= width / 0.055
                point.co.z *= height / 0.006
        self.mouth = mouth
        self.teeth = ellipsoid("Upper teeth", (0, -0.194, -0.091), (0.042, 0.006, 0.009), mats["paper"], self.head)
        if female:
            ellipsoid("Bob back", (0, 0.10, 0), (0.243, 0.15, 0.29), hair, self.head)
            for side in (-1, 1):
                ellipsoid("Bob side", (side * 0.20, 0.01, -0.015), (0.058, 0.13, 0.25), hair, self.head)
        ellipsoid("Hair crown", (0, 0.018, 0.205), (0.22, 0.184, 0.115), hair, self.head)
        fringe = ellipsoid("Swept fringe", (-0.055, -0.115, 0.19), (0.17, 0.085, 0.06), hair, self.head)
        fringe.rotation_euler.y = -0.2
        self.arms = []
        self.legs = []
        for side in (-1, 1):
            upper = segment("Jacket sleeve", (side * 0.22, 0, 1.28), (side * 0.33, -0.12, 1), 0.085, shirt, self.body)
            lower = segment("Forearm sleeve", (side * 0.33, -0.12, 1), (side * 0.23, -0.4, 0.93), 0.064, shirt, self.body)
            hand = ellipsoid("Hand", (side * 0.23, -0.41, 0.93), (0.065, 0.10, 0.038), skin, self.body)
            self.arms.append((side, upper, lower, hand))
            thigh = segment("Trouser thigh", (side * 0.13, 0, 0.65), (side * 0.16, -0.40, 0.53), 0.115, mats["trousers"], self.root)
            shin = segment("Trouser shin", (side * 0.16, -0.40, 0.53), (side * 0.16, -0.42, 0.15), 0.085, mats["trousers"], self.root)
            shoe = ellipsoid("Shoe", (side * 0.16, -0.5, 0.1), (0.10, 0.19, 0.085), mats["shoe"], self.root)
            self.legs.append((side, thigh, shin, shoe))
        self.pos = Vector(pos)
        self.angle = angle

    def animate(self, timeline, fps, candidate=False, index=0):
        sit_start = timeline["turns"][0]["start"] + 0.5
        sit_end = timeline["turns"][0]["end"] + 0.4
        count = round(timeline["duration"] * fps)
        for frame in range(1, count + 1, 3):
            t = (frame - 1) / fps
            active = next((turn for turn in timeline["turns"] if turn["start"] <= t < turn["end"]), None)
            speaking = active and active["speaker"] == self.name
            seated = smoothstep((t - sit_start) / max(0.1, sit_end - sit_start)) if candidate else 1
            walk = smoothstep((t - index * 0.3) / 3.2)
            if candidate:
                offset = Vector((-2.9 - self.pos.x, 1.8 + index * 0.75 - self.pos.y, 0))
                self.root.location = self.pos + offset * (1 - walk)
                arrival_angle = math.atan2(-offset.x, offset.y)
                self.root.rotation_euler.z = arrival_angle * (1 - smoothstep((t - 2.8) / 0.65))
                self.body.location.z = (1 - seated) * 0.43
                self.body.location.y = -0.10 * math.sin(seated * math.pi)
            breath = math.sin(t * 1.7 + index) * 0.008
            self.body.rotation_euler.x = breath
            self.head.rotation_euler.x = math.sin(t * (3.8 if speaking else 1.3) + index) * (0.025 if speaking else 0.012)
            target = active["look_at"] if speaking else active["speaker"] if active else "examiner"
            head_turn = 0
            if candidate and target in ("candidate_a", "candidate_b") and target != self.name:
                head_turn = 0.33 if self.name == "candidate_a" else -0.33
            elif not candidate and target in ("candidate_a", "candidate_b"):
                head_turn = 0.13 if target == "candidate_a" else -0.13
            self.head.rotation_euler.z = head_turn
            blink = (t + index * 0.67) % 4.1
            for lid in self.lids:
                lid.scale.z = 1 if blink < 0.13 else 0.001
                key_transform(lid, frame)
            for side, upper, lower, hand in self.arms:
                gesture = 0
                if speaking:
                    gesture = math.sin((t - active["start"]) * 2.8) * 0.5 + 0.5
                lift = gesture * (0.13 if side == 1 else 0.065)
                elbow = (side * (0.33 + gesture * 0.025), -0.13, 1.0 + lift / 3)
                rest = Vector((side * 0.23, -0.41, 0.93))
                standing = Vector((side * 0.30, -0.04, 0.68))
                hand_pos = standing.lerp(rest, seated)
                hand_pos.z += lift
                hand_pos.y -= gesture * 0.05
                pose_segment(upper, (side * 0.22, 0, 1.28), elbow)
                pose_segment(lower, elbow, hand_pos)
                hand.location = hand_pos
                hand.rotation_euler.x = -gesture * 0.4
                for obj in (upper, lower, hand):
                    key_transform(obj, frame)
            for side, thigh, shin, shoe in self.legs:
                stride = math.sin(t * 7 + (0 if side == 1 else math.pi)) * 0.19 * (1 - walk)
                hip = (side * 0.13, 0, 0.65 + 0.43 * (1 - seated))
                knee = (side * 0.16, -0.40 * seated + stride, 0.53)
                foot = (side * 0.16, -0.42 * seated - stride, 0.15 + abs(stride) * 0.2)
                pose_segment(thigh, hip, knee)
                pose_segment(shin, knee, foot)
                shoe.location = (foot[0], foot[1] - 0.08, foot[2] - 0.05)
                for obj in (thigh, shin, shoe):
                    key_transform(obj, frame)
            for obj in (self.root, self.body, self.head):
                key_transform(obj, frame)
        self.animate_mouth(timeline, fps)

    def animate_mouth(self, timeline, fps):
        keys = self.mouth.data.shape_keys.key_blocks
        for key in list(keys)[1:]:
            key.value = 0
            key.keyframe_insert(data_path="value", frame=1)
        self.teeth.scale = (1, 1, 0.001)
        key_transform(self.teeth, 1)
        for turn in timeline["turns"]:
            if turn["speaker"] != self.name:
                continue
            for cue in turn["mouth_cues"]:
                frame = 1 + round((turn["start"] + cue["start"]) * fps)
                end = max(frame + 1, 1 + round((turn["start"] + cue["end"]) * fps))
                for key in list(keys)[1:]:
                    key.value = 0
                    key.keyframe_insert(data_path="value", frame=max(1, frame - 1))
                    key.value = 1 if key.name == cue["value"] else 0
                    key.keyframe_insert(data_path="value", frame=frame)
                    key.keyframe_insert(data_path="value", frame=max(frame, end - 1))
                    key.value = 0
                    key.keyframe_insert(data_path="value", frame=end)
                show_teeth = cue["value"] in "BCDH"
                self.teeth.scale.z = 1 if show_teeth else 0.001
                key_transform(self.teeth, frame)
                key_transform(self.teeth, max(frame, end - 1))
            end = 1 + round(turn["end"] * fps)
            for key in list(keys)[1:]:
                key.value = 0
                key.keyframe_insert(data_path="value", frame=end)
            self.teeth.scale.z = 0.001
            key_transform(self.teeth, end)
        if self.mouth.data.shape_keys.animation_data:
            for curve in self.mouth.data.shape_keys.animation_data.action.fcurves:
                for point in curve.keyframe_points:
                    point.interpolation = "LINEAR"


def camera(name, pos, target, lens=43):
    bpy.ops.object.camera_add(location=pos)
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    obj.data.lens = lens
    obj.data.clip_end = 100
    return obj


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode", type=Path, default=Path(__file__).with_name("episode.json"))
    from build_paths import BUILDS, build_directory

    parser.add_argument("--build", type=Path, default=BUILDS / "v2")
    parser.add_argument("--width", type=int, default=720)
    parser.add_argument("--height", type=int, default=1280)
    parser.add_argument("--engine", choices=("workbench", "cycles"), default="cycles")
    parser.add_argument("--samples", type=int, default=16)
    parser.add_argument("--still", type=int, help="Render just this frame")
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--start", type=int)
    parser.add_argument("--end", type=int)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    args.build = build_directory(args.build)
    episode = json.loads(args.episode.read_text(encoding="utf-8"))
    timeline = json.loads((args.build / "timeline.json").read_text(encoding="utf-8"))
    if min(args.width, args.height) <= 0:
        raise ValueError("Dimensions must be positive")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    colors = {
        "floor": (0.34, 0.26, 0.19), "wall": (0.64, 0.69, 0.66),
        "wood": (0.48, 0.30, 0.16), "door": (0.12, 0.25, 0.24),
        "chair": (0.10, 0.24, 0.27), "metal": (0.16, 0.19, 0.21),
        "paper": (0.96, 0.95, 0.88), "ink": (0.025, 0.035, 0.045),
        "teal": (0.04, 0.42, 0.42), "gold": (0.89, 0.58, 0.22),
        "sky": (0.64, 0.83, 0.88), "pot": (0.78, 0.38, 0.24),
        "leaf": (0.12, 0.34, 0.18), "iris": (0.16, 0.26, 0.22),
        "mouth": (0.15, 0.035, 0.033), "shoe": (0.065, 0.07, 0.075),
        "trousers": (0.12, 0.17, 0.22),
        "skin_a": (0.76, 0.47, 0.30), "skin_b": (0.48, 0.28, 0.16),
        "skin_e": (0.81, 0.58, 0.43), "skin_o": (0.64, 0.40, 0.27),
        "shirt_a": (0.04, 0.38, 0.37), "shirt_b": (0.25, 0.33, 0.53),
        "shirt_e": (0.16, 0.21, 0.29), "shirt_o": (0.48, 0.23, 0.18),
        "hair_a": (0.14, 0.06, 0.035), "hair_b": (0.038, 0.025, 0.02),
        "hair_e": (0.28, 0.27, 0.25),
    }
    mats = {name: material(name, color) for name, color in colors.items()}
    room(mats)
    people = [
        StudioCharacter("candidate_a", (-0.82, 0.65, 0), 0, "rain", (0.025, 0.21, 0.19)),
        StudioCharacter("candidate_b", (0.82, 0.65, 0), 0, "snow", (0.09, 0.17, 0.32)),
        StudioCharacter("examiner", (-0.82, -1.6, 0), math.pi, "snow", (0.16, 0.18, 0.22), older=True),
        StudioCharacter("observer", (0.82, -1.6, 0), math.pi, "rain", (0.32, 0.13, 0.10), older=True),
    ]
    for index, person in enumerate(people):
        person.animate(timeline, episode["fps"], person.name.startswith("candidate"), index)
    cameras = {
        "wide": camera("01 Room overview", (3.4, -3.1, 3.15), (-0.4, 0.1, 1.0), 28),
        "examiner": camera("02 Examiner", (-1.65, 1.6, 1.95), (-0.82, -1.55, 1.22), 48),
        "candidates": camera("03 Both candidates", (0, -3.25, 1.95), (0, 0.58, 1.22), 26),
        "candidate_a": camera("04 Lea", (-1.65, -2.45, 1.85), (-0.80, 0.60, 1.25), 48),
        "candidate_b": camera("05 Samir", (1.65, -2.45, 1.9), (0.80, 0.60, 1.30), 48),
    }
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH" if args.engine == "workbench" else "CYCLES"
    if args.engine == "cycles":
        scene.cycles.samples = args.samples
        scene.cycles.use_denoising = True
        scene.cycles.device = "CPU"
        scene.cycles.max_bounces = 4
        scene.cycles.diffuse_bounces = 2
        scene.cycles.glossy_bounces = 2
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.adaptive_threshold = 0.08
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.72, 0.81, 0.93, 1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.23
    shading = scene.display.shading
    shading.light = "STUDIO"
    shading.studiolight_rotate_z = 0.35
    shading.color_type = "MATERIAL"
    shading.show_shadows = True
    shading.show_cavity = True
    shading.cavity_type = "BOTH"
    shading.curvature_ridge_factor = 1.2
    shading.curvature_valley_factor = 0.7
    shading.show_specular_highlight = False
    shading.shadow_intensity = 0.35
    shading.background_type = "WORLD"
    scene.display.render_aa = "8"
    scene.view_settings.view_transform = "AgX" if args.engine == "cycles" else "Standard"
    scene.view_settings.look = "AgX - Medium High Contrast" if args.engine == "cycles" else "None"
    scene.render.resolution_x, scene.render.resolution_y = args.width, args.height
    scene.render.resolution_percentage = 100
    scene.render.fps = episode["fps"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.threads_mode, scene.render.threads = "FIXED", 4
    scene.frame_start, scene.frame_end = 1, round(timeline["duration"] * episode["fps"])
    scene.camera = cameras["wide"]
    marker = scene.timeline_markers.new("Entrance", frame=1)
    marker.camera = cameras["wide"]
    for turn in timeline["turns"]:
        marker = scene.timeline_markers.new(turn["id"] + " " + turn["speaker"], frame=1 + round(turn["start"] * episode["fps"]))
        marker.camera = cameras[turn["camera"]]
    marker = scene.timeline_markers.new("Book end card", frame=1 + round((timeline["duration"] - episode["outro_seconds"]) * episode["fps"]))
    marker.camera = cameras["wide"]
    editor = scene.sequence_editor_create()
    audio_strip = editor.sequences.new_sound("Qwen dialogue", str(args.build / "dialogue.wav"), channel=1, frame_start=1)
    scene.render.use_sequencer = False
    scene["episode"] = episode["title"]
    scene["notice"] = episode["disclaimer"]
    scene["lip_sync"] = "Rhubarb phonetic cues mapped to native jaw and mouth controls"
    scene["render_note"] = "Version 2 · native studio rigs · Cycles soft lighting"
    scene["credits"] = "\n".join(CREDITS)
    scene.frame_set(1)
    args.build.mkdir(parents=True, exist_ok=True)
    (args.build / "frames").mkdir(exist_ok=True)
    scene.render.filepath = str(args.build / "frames" / "frame_")
    bpy.ops.file.pack_all()
    audio_strip.sound.filepath = "//dialogue.wav"
    bpy.ops.wm.save_as_mainfile(filepath=str(args.build / "studio.blend"), compress=True)
    if args.still:
        scene.frame_set(args.still)
        scene.render.filepath = str(args.build / f"still_{args.still:04d}.png")
        bpy.ops.render.render(write_still=True)
    elif args.render:
        if args.start:
            scene.frame_start = args.start
        if args.end:
            scene.frame_end = args.end
        bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()
