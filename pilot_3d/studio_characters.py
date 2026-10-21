"""Adapt Blender Studio's CC-BY Snow/Rain rigs without running their UI scripts."""

import math
from pathlib import Path

import bpy
from mathutils import Euler, Matrix, Vector

ROOT = Path(__file__).resolve().parent
ASSETS = {
    "snow": ROOT / "assets/studio/snow-v4/Snow/snow_v4.2.blend",
    "rain": ROOT / "assets/studio/rain-v3/Rain v3.3/rain_v3.2.blend",
}
CREDITS = (
    "Snow Rig (CC) Blender Foundation | studio.blender.org",
    "Rain Rig (CC) Blender Foundation | studio.blender.org",
)
MOUTHS = {
    "X": (0, 1.0), "A": (0.005, 1.0), "B": (0.045, 1.05),
    "C": (0.11, 1.05), "D": (0.18, 0.98), "E": (0.105, 0.8),
    "F": (0.07, 0.65), "G": (0.025, 0.98), "H": (0.08, 1.0),
}


def ease(value):
    value = max(0, min(1, value))
    return value * value * (3 - 2 * value)


def pulse(t, start, length):
    phase = (t - start) / length
    return math.sin(math.pi * phase) ** 2 if 0 < phase < 1 else 0


def key(bone, frame):
    for prop in ("location", "rotation_euler", "scale"):
        bone.keyframe_insert(data_path=prop, frame=frame)


def plain_material(name, color):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = 0.72
    return mat


class StudioCharacter:
    def __init__(self, name, pos, angle, kind, outfit_color, older=False):
        self.name, self.kind = name, kind
        self.root = bpy.data.objects.new(name, None)
        bpy.context.scene.collection.objects.link(self.root)
        self.root.location = pos
        self.root.rotation_euler.z = angle
        self.pos, self.angle = Vector(pos), angle
        self.scale = 1.07 if kind == "snow" else 1.14
        path = ASSETS[kind]
        if not path.is_file():
            raise FileNotFoundError(f"Missing licensed studio character: {path}; run setup_characters.sh")
        with bpy.data.libraries.load(str(path), link=False) as (source, target):
            collection = "CH-" + kind
            if collection not in source.collections:
                raise ValueError(f"Unsupported {kind} asset: expected {collection}")
            target.collections = [collection]
        self.collection = target.collections[0]
        self.collection.name = name + " · " + kind
        bpy.context.scene.collection.children.link(self.collection)
        objects = list(self.collection.all_objects)
        self.rig = next(obj for obj in objects if obj.type == "ARMATURE" and obj.name.startswith("RIG"))
        self.rig.name = name + " · native rig"
        if self.rig.animation_data:
            self.rig.animation_data.action = None
            for track in list(self.rig.animation_data.nla_tracks):
                self.rig.animation_data.nla_tracks.remove(track)
        self.bones = self.rig.pose.bones
        self.root["asset"] = kind
        self.root["credit"] = CREDITS[0 if kind == "snow" else 1]
        self.rig["actor"] = name
        for obj in objects:
            if obj.type == "ARMATURE" and obj != self.rig:
                obj.hide_render = True
            if obj.parent is None:
                obj.parent = self.root
                obj.matrix_parent_inverse = Matrix.Identity(4)
                obj.location *= self.scale
                obj.scale *= self.scale
            if obj.type == "MESH":
                for mod in obj.modifiers:
                    if mod.type == "SUBSURF":
                        for prop in ("levels", "render_levels"):
                            mod.driver_remove(prop)
                        level = 1 if any(token in obj.name.lower() for token in ("head", "body", "eyes")) else 0
                        mod.levels = level
                        mod.render_levels = level
                if obj.name.startswith("WGT"):
                    obj.hide_render = True
        outfit = plain_material(name + " woven fabric", outfit_color)
        for obj in objects:
            if obj.type != "MESH":
                continue
            base = obj.name.lower()
            if (kind == "snow" and "shirt" in base) or (kind == "rain" and "top" in base):
                obj.data = obj.data.copy()
                obj.data.materials.clear()
                obj.data.materials.append(outfit)
            if older and any(token in base for token in ("hair", "eyebrows")):
                obj.data = obj.data.copy()
                gray = plain_material(name + " salt and pepper", (0.21, 0.23, 0.25))
                obj.data.materials.clear()
                obj.data.materials.append(gray)
        self.configure_controls()

    @classmethod
    def from_scene(cls, name):
        actor = cls.__new__(cls)
        actor.name = name
        actor.root = bpy.context.scene.objects[name]
        actor.kind = actor.root["asset"]
        actor.scale = 1.07 if actor.kind == "snow" else 1.14
        actor.pos = actor.root.location.copy()
        actor.angle = actor.root.rotation_euler.z
        rigs = [
            obj for obj in actor.root.children_recursive
            if obj.type == "ARMATURE" and obj.get("actor") == name
        ]
        if len(rigs) != 1:
            raise ValueError(f"Expected one native rig for {name}, found {len(rigs)}")
        actor.rig = rigs[0]
        actor.bones = actor.rig.pose.bones
        actor.configure_controls()
        return actor

    def configure_controls(self):
        if self.kind == "snow":
            properties = self.bones["Properties"]
            properties["ik_spine"] = 0
            for side in ("left", "right"):
                properties[f"ik_{side}_upperarm"] = 1
                properties[f"ik_{side}_thigh"] = 1
                properties[f"ik_stretch_{side}_upperarm"] = 0
                properties[f"ik_stretch_{side}_thigh"] = 0
            self.bones["Properties_Character_Snow"]["Quality"] = 1
            self.torso_name, self.jaw_name = "TORSO-Spine", "Jaw"
            self.hand_name, self.knee_name = "IK-Wrist", None
        else:
            properties = self.bones["Properties_IKFK"]
            properties["ik_spine"] = 0
            properties["ik_stretch_arms"] = 0
            self.bones["Properties_Character_Rain"]["Quality"] = 1
            self.bones["Properties_Character_Rain"]["Scarf"] = False
            self.torso_name, self.jaw_name = "MSTR-Pelvis", "MSTR-Jaw"
            self.hand_name, self.knee_name = "IK-Hand", "IK-Pole-Shin"
        required = [self.torso_name, self.jaw_name, "FK-Head", self.hand_name + ".L", "IK-Foot.L"]
        for control in required:
            if control not in self.bones:
                raise ValueError(f"{self.kind} is missing required control: {control}")
        self.head = self.bones["FK-Head"]
        self.rest = {bone.name: bone.bone.matrix_local.copy() for bone in self.bones}
        self.repair_legacy_spine_driver()
        bpy.context.view_layer.update()

    def repair_legacy_spine_driver(self):
        if self.kind != "rain" or "STR-Spine4" in self.bones or not self.rig.animation_data:
            return
        path = 'pose.bones["DEF-Spine3"].bbone_easeout'
        curve = self.rig.animation_data.drivers.find(path)
        if curve is None:
            return
        targets = [target.bone_target for variable in curve.driver.variables for target in variable.targets]
        if targets != ["STR-Spine4"] or curve.driver.expression != "scale-1":
            raise ValueError("Unexpected Rain spine-easing driver; cannot apply the pinned-asset repair.")
        self.rig.driver_remove(path)
        self.rig["legacy_spine_driver_omitted"] = True
        self.rig["driver_compatibility"] = (
            "Rain v3.2 references nonexistent STR-Spine4. Omitted only its dangling "
            "DEF-Spine3 easeout driver, retaining the authored fixed easing value."
        )
        print(f"Native-asset compatibility repair for {self.name}: {self.rig['driver_compatibility']}")

    def restore_native_drivers(self):
        """Repair scenes made by the old loader, retaining their baked performance."""
        with bpy.data.libraries.load(str(ASSETS[self.kind]), link=False) as (source, target):
            target.objects = [name for name in source.objects if name.lower() == "rig-" + self.kind]
        if len(target.objects) != 1:
            raise ValueError(f"Expected one source rig for {self.kind}")
        original = target.objects[0]
        existing = {(curve.data_path, curve.array_index) for curve in self.rig.animation_data.drivers}
        restored = 0
        for source_curve in original.animation_data.drivers:
            if (source_curve.data_path, source_curve.array_index) in existing:
                continue
            resolved = self.rig.path_resolve(source_curve.data_path)
            curve = (self.rig.driver_add(source_curve.data_path) if isinstance(resolved, (int, float, str))
                     else self.rig.driver_add(source_curve.data_path, source_curve.array_index))
            curve.driver.type = source_curve.driver.type
            curve.driver.use_self = source_curve.driver.use_self
            for variable in list(curve.driver.variables):
                curve.driver.variables.remove(variable)
            for source_variable in source_curve.driver.variables:
                variable = curve.driver.variables.new()
                variable.type, variable.name = source_variable.type, source_variable.name
                for source_target, destination in zip(source_variable.targets, variable.targets):
                    if source_target.id != original:
                        raise ValueError(f"Unexpected external native-driver dependency: {source_curve.data_path}")
                    destination.id = self.rig
                    for attribute in ("bone_target", "data_path", "transform_type", "transform_space", "rotation_mode"):
                        setattr(destination, attribute, getattr(source_target, attribute))
            curve.driver.expression = source_curve.driver.expression
            curve.extrapolation = source_curve.extrapolation
            for modifier in list(curve.modifiers):
                curve.modifiers.remove(modifier)
            for source_modifier in source_curve.modifiers:
                if source_modifier.type != "GENERATOR":
                    raise ValueError(f"Unsupported native driver modifier: {source_modifier.type}")
                modifier = curve.modifiers.new("GENERATOR")
                for attribute in ("mode", "poly_order", "use_additive", "coefficients", "mute",
                                  "use_influence", "influence", "use_restricted_range",
                                  "frame_start", "frame_end", "blend_in", "blend_out"):
                    setattr(modifier, attribute, getattr(source_modifier, attribute))
            curve.keyframe_points.add(len(source_curve.keyframe_points))
            for source_point, destination in zip(source_curve.keyframe_points, curve.keyframe_points):
                destination.co = source_point.co
                destination.interpolation = source_point.interpolation
                destination.handle_left_type = source_point.handle_left_type
                destination.handle_right_type = source_point.handle_right_type
                destination.handle_left = source_point.handle_left
                destination.handle_right = source_point.handle_right
            curve.update()
            restored += 1
        expected = len(original.animation_data.drivers)
        bpy.data.objects.remove(original, do_unlink=True)
        self.rig["restored_native_drivers"] = restored
        self.configure_controls()
        self.rig["native_driver_count"] = expected - int(self.rig.get("legacy_spine_driver_omitted", False))
        print(f"Restored {restored}/{expected} native drivers for {self.name}")

    def rotate(self, name, angles, frame):
        bone = self.bones[name]
        bone.rotation_mode = "XYZ"
        bone.rotation_euler = angles
        key(bone, frame)

    def position(self, name, target, frame, rotation=None):
        bone = self.bones[name]
        bone.rotation_mode = "XYZ"
        matrix = self.rest[name].copy()
        if rotation:
            if isinstance(rotation, Matrix):
                matrix = rotation @ matrix
            else:
                matrix = Euler(rotation, "XYZ").to_matrix().to_4x4() @ matrix
        matrix.translation = Vector(target)
        bone.matrix = matrix
        key(bone, frame)

    def animate(self, timeline, fps, candidate=False, index=0):
        count = round(timeline["duration"] * fps)
        torso_rest = self.rest[self.torso_name].translation
        # Native rigs are meter-scaled; pelvis settles over the upholstered seat.
        pelvis_drop = 0.25 if self.kind == "snow" else 0.23
        gaze = 0.0
        for frame in range(1, count + 1, 2):
            t = (frame - 1) / fps
            turn = next((item for item in timeline["turns"] if item["start"] <= t < item["end"]), None)
            speaker = turn["speaker"] if turn else None
            speaking = speaker == self.name
            target = turn["look_at"] if speaking else speaker
            seated = ease((t - 4.4 - index * 0.15) / 2.1) if candidate else 1
            walk = ease((t - index * 0.45) / 3.2) if candidate else 1
            walk_weight = math.sin(math.pi * walk) if candidate else 0
            stride_phase = t * 7 + index
            if candidate:
                origin = Vector((-2.9, 2.25 + index * 0.65, 0))
                self.root.location = origin.lerp(self.pos, walk)
                delta = self.pos - origin
                heading = math.atan2(delta.x, -delta.y)
                self.root.rotation_euler.z = heading * (1 - ease((t - 2.7) / 0.8))
                self.root.location.z = abs(math.sin(stride_phase)) * 0.025 * walk_weight
            self.root.keyframe_insert(data_path="location", frame=frame)
            self.root.keyframe_insert(data_path="rotation_euler", frame=frame)
            phase = t - turn["start"] if speaking else 0
            accent = 0
            if speaking:
                accent = pulse(phase, 0.3, 1.5) + 0.6 * pulse(phase, 2.65, 1.3)
            action = turn["action"] if speaking else ""
            consider = accent if action == "consider" else 0
            self.position(self.torso_name, torso_rest + Vector((
                0.008 * math.sin(t * 0.8 + index),
                -0.055 * math.sin(seated * math.pi) - 0.012 * accent,
                -pelvis_drop * seated + 0.003 * math.sin(t * 1.6 + index),
            )), frame)
            want = 0
            if candidate and target in ("candidate_a", "candidate_b") and target != self.name:
                want = 0.55 if self.name == "candidate_a" else -0.55
            elif not candidate and target in ("candidate_a", "candidate_b"):
                want = 0.10 if target == "candidate_a" else -0.1
            gaze += (want - gaze) * 0.22
            self.rotate("FK-Chest", (0.045 * accent, gaze * 0.2, 0.025 * consider), frame)
            # Head turns carry a small eye lead; listeners give one nod near a turn's end.
            nod = 0
            if turn and not speaking and self.name in ("candidate_a", "candidate_b"):
                nod = 0.07 * pulse(t, turn["end"] - 0.9, 0.65)
            if action == "agree":
                nod += 0.1 * pulse(phase, 0.25, 0.65)
            self.rotate("FK-Head", (nod + 0.025 * accent, gaze, 0.035 * consider), frame)
            bpy.context.view_layer.update()
            eye_height = (1.62 if self.kind == "snow" else 1.47) - pelvis_drop * seated
            self.position("TGT-Eyes", (gaze * 4.0, -1.8 if abs(want) > 0.2 else -2.5, eye_height - 0.02), frame)
            self.face(turn, t, frame, index, speaking)
            for side, sign in (("L", 1), ("R", -1)):
                foot_rest = self.rest["IK-Foot." + side].translation
                swing = math.sin(stride_phase + (0 if sign == 1 else math.pi))
                foot = Vector((sign * 0.115, -0.34 * seated + 0.19 * swing * walk_weight, foot_rest.z))
                foot.z += max(0, swing) * 0.07 * walk_weight
                self.position("IK-Foot." + side, foot, frame)
                if self.knee_name:
                    pole = self.rest[self.knee_name + "." + side].translation.copy()
                    pole.y = -0.8
                    self.position(self.knee_name + "." + side, pole, frame)
                lift = accent * (0.11 if sign == 1 else 0.012)
                if action == "consider":
                    lift *= 0.65
                hand = Vector((sign * (0.24 + accent * 0.045), -0.37 - 0.035 * accent, 0.91 / self.scale + lift))
                hanging = Vector((sign * 0.24, -0.02 - 0.10 * swing * walk_weight, 0.82))
                hand = hanging.lerp(hand, seated)
                # Rotate the outstretched rest hand into a forward-facing wrist.
                rotation = (
                    Matrix.Rotation(sign * accent * (2.5 if sign == 1 else 0.3), 4, "Y")
                    @ Matrix.Rotation(-sign * math.pi / 2, 4, "Z")
                )
                standing_rotation = Matrix.Rotation(sign * math.pi / 2, 4, "Y")
                rotation = standing_rotation.to_quaternion().slerp(rotation.to_quaternion(), seated).to_matrix().to_4x4()
                self.position(self.hand_name + "." + side, hand, frame, rotation)
            bpy.context.view_layer.update()
        # Linear interpolation prevents IK overshoot at contacts and facial cue boundaries.
        if self.rig.animation_data and self.rig.animation_data.action:
            for curve in self.rig.animation_data.action.fcurves:
                for point in curve.keyframe_points:
                    point.interpolation = "LINEAR"

    def face(self, turn, t, frame, index, speaking):
        openness, width = 0, 1
        if speaking:
            relative = t - turn["start"]
            cue = next((cue for cue in turn["mouth_cues"] if cue["start"] <= relative < cue["end"]), None)
            if cue:
                openness, width = MOUTHS[cue["value"]]
        self.rotate(self.jaw_name, (openness, 0, 0), frame)
        mouth = self.bones["MSTR-Mouth"]
        mouth.scale = (width, 1, 1)
        key(mouth, frame)
        brow_amount = 0.0025 * pulse(t, turn["start"] + 0.2, 1.3) if speaking else 0
        for side in ("L", "R"):
            brow = self.bones.get("MSTR-Eyebrow." + side)
            if brow:
                brow.location = (0, brow_amount, 0)
                key(brow, frame)
            if self.kind == "snow":
                blink = pulse((t + index * 0.81) % 4.7, 0.4, 0.18)
                upper = self.bones["MSTR-Eyelid_Upper." + side]
                upper.location.y = -0.030 * blink
                key(upper, frame)
            else:
                blink_bone = self.bones.get("ACT-Eyelid_Upper." + side)
                if blink_bone:
                    blink = pulse((t + index * 0.81) % 4.7, 0.4, 0.18)
                    blink_bone.location.y = -0.040 * blink
                    key(blink_bone, frame)
