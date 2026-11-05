"""Native, still-only exam-room and four-person thumbnail poses."""

from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

from listening_scene import freeze_source_animation
from prepare_audio import atomic_json, sha256_file
from scene_direction import configure_cameras, room_design
from studio_characters import StudioCharacter


def hair_drop(actor):
    return (actor.rig.matrix_world @ actor.bones["FK-Hair_Ponytail1"].head).z - (
        actor.rig.matrix_world @ actor.bones["FK-Hair_Ponytail4"].tail).z


def correct_hair(actor):
    if actor.kind != "rain":
        return None
    before = hair_drop(actor)
    for index, angle in enumerate((-.70, -.48, -.12, .10), 1):
        bone = actor.bones[f"FK-Hair_Ponytail{index}"]
        bone.rotation_mode = "XYZ"
        bone.rotation_euler = (angle, 0, 0)
    bpy.context.view_layer.update()
    after = hair_drop(actor)
    if after < .15:
        raise ValueError(f"{actor.name}: ponytail does not hang down.")
    return {"actor": actor.name, "before_tip_drop_m": before, "after_tip_drop_m": after,
            "pose": "Existing generator Rain seated ponytail angles, not edited source geometry."}


def head_bounds(scene, camera, actors):
    result = []
    for actor in actors:
        meshes = [obj for obj in actor.root.children_recursive if obj.type == "MESH"
                  and obj.name.startswith("GEO-") and any(token in obj.name.lower() for token in ("head", "hair"))]
        if not meshes:
            raise ValueError(f"{actor.name}: missing head/hair geometry.")
        points = []
        for mesh in meshes:
            evaluated = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
            points += [evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box]
        if actor.kind == "rain":
            points += [actor.rig.matrix_world @ actor.bones["FK-Hair_Ponytail1"].head,
                       actor.rig.matrix_world @ actor.bones["FK-Hair_Ponytail4"].tail]
        projected = [world_to_camera_view(scene, camera, point) for point in points]
        result.append({"actor": actor.name, "bounds": [min(p.x for p in projected), min(p.y for p in projected),
                                                      max(p.x for p in projected), max(p.y for p in projected)],
                       "in_front": all(p.z > 0 for p in projected), "head_and_hair_meshes": [obj.name for obj in meshes]})
    return result


def render_still(scene, camera, actors, size, output):
    scene.camera = camera
    scene.render.resolution_x, scene.render.resolution_y = size
    bpy.context.view_layer.update()
    lens = camera.data.lens
    for _ in range(50):
        heads = head_bounds(scene, camera, actors)
        if all(h["in_front"] and min(h["bounds"]) > .05 and max(h["bounds"]) < .95 for h in heads):
            break
        camera.data.lens *= .95
    else:
        raise ValueError(f"Cannot frame the speakers in {output.name}.")
    scene.render.filepath = str(output)
    bpy.ops.render.render(write_still=True)
    camera.data.lens = lens
    return {"head_bounds": heads, "file": str(output), "sha256": sha256_file(output), "size": list(size)}


def group_pose(scene, actors):
    order = ("examiner", "candidate_a", "candidate_b", "observer")
    table = scene.objects["Exam table"]
    scene.objects["Front wall"].hide_render = True
    table.scale.x *= 3.9 / table.dimensions.x
    for obj in scene.objects:
        if obj.name.startswith("Table leg"):
            obj.location.x *= 3.9 / 2.7
    camera_data = bpy.data.cameras.new("Long speaking group photo")
    camera = bpy.data.objects.new("Long speaking group photo", camera_data)
    scene.collection.objects.link(camera)
    camera.location = (0, -6.0, 2.05)
    camera.rotation_euler = (Vector((0, .35, 1.08)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera_data.lens = 65
    chairs = {"candidate_a": "Chair", "candidate_b": "Chair.002",
              "examiner": "Chair.001", "observer": "Chair.003"}
    pose = []
    for index, role in enumerate(order):
        actor = actors[role]
        actor.root.location = ((index - 1.5) * .84, .65, 0)
        actor.root.rotation_euler = (0, 0, 0)
        actor.head.rotation_mode = "XYZ"
        actor.head.rotation_euler = (0, 0, 0)
        actor.bones["FK-Chest"].rotation_euler = (0, 0, 0)
        jaw = actor.bones[actor.jaw_name]
        jaw.rotation_mode = "XYZ"
        jaw.rotation_euler = (0, 0, 0)
        actor.bones["MSTR-Mouth"].location = (0, 0, 0)
        actor.bones["MSTR-Mouth"].scale = (1, 1, 1)
        smile_lift = .012 if actor.kind == "snow" else .009
        for side, sign in (("L", 1), ("R", -1)):
            bone = actor.bones["ACT-Lips_Corner." + side]
            bone.location = actor.rest[bone.name].to_3x3().inverted() @ Vector((sign * .005, 0, smile_lift))
        chair = scene.objects[chairs[role]]
        chair.location = actor.root.location
        chair.rotation_euler = (0, 0, 0)
        bpy.context.view_layer.update()
        actor.position("TGT-Eyes", actor.rig.matrix_world.inverted() @ camera.location, 600)
        toward_camera = Vector((camera.location.x - actor.root.location.x,
                                camera.location.y - actor.root.location.y, 0)).normalized()
        facing = (actor.root.matrix_world.to_quaternion() @ Vector((0, -1, 0))).dot(toward_camera)
        if facing < .97:
            raise ValueError(f"{role}: group pose does not face the camera.")
        if actor.kind == "rain" and hair_drop(actor) < .15:
            raise ValueError(f"{role}: group-pose hair no longer hangs down.")
        pose.append({"actor": role, "location": list(actor.root.location), "facing_camera_dot": facing,
                     "smile_corner_lift_m": smile_lift, "seated_pose_from_base": True})
    for obj in scene.objects:
        if obj.name.startswith(("Direction logo", "Direction Deutsch Kompass wall logo")):
            obj.location += Vector((1.76, 0, .8))
        elif obj.name.startswith(("Examiner clipboard", "Examiner notes")):
            obj.hide_render = True
    bpy.context.view_layer.update()
    return camera, pose


def verify_group_visibility(scene, camera, actors):
    checks = []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for actor in actors.values():
        mesh = next(obj for obj in actor.root.children_recursive if obj.type == "MESH"
                    and obj.name.startswith("GEO-") and "head" in obj.name.lower())
        evaluated = mesh.evaluated_get(depsgraph)
        center = sum((Vector(corner) for corner in evaluated.bound_box), Vector()) / 8
        target = evaluated.matrix_world @ center
        direction = target - camera.location
        hit, _, _, _, obj, _ = scene.ray_cast(depsgraph, camera.location, direction.normalized(),
                                              distance=direction.length + .5)
        # Ray casting includes render-hidden architecture; temporarily omit it from the view layer too.
        if hit and obj.hide_render:
            hidden = [item for item in scene.objects if item.hide_render and not item.hide_get()]
            for item in hidden:
                item.hide_set(True)
            depsgraph.update()
            hit, _, _, _, obj, _ = scene.ray_cast(depsgraph, camera.location, direction.normalized(),
                                                  distance=direction.length + .5)
            for item in hidden:
                item.hide_set(False)
            depsgraph.update()
        if not hit or obj.original not in actor.root.children_recursive:
            raise ValueError(f"{actor.name}: thumbnail face is occluded by {obj.name if hit else 'empty space'}.")
        checks.append({"actor": actor.name, "visible_head_mesh": obj.name, "camera_ray_clear": True})
    return checks


def render_contacts(request, formats, thumbnail_formats):
    episode = request["episode"]
    build = Path(request["build"])
    scene = bpy.context.scene
    scene.frame_set(episode["scene"]["contact_pose_frame"])
    freeze_source_animation(scene)
    actors = {role: StudioCharacter.from_scene(role)
              for role in ("candidate_a", "candidate_b", "examiner", "observer")}
    hair = []
    for actor in actors.values():
        actor.restore_native_drivers()
        check = correct_hair(actor)
        if check:
            hair.append(check)
    room_design(scene, episode)
    cameras = configure_cameras(scene)
    scene.timeline_markers.clear()
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 8
    scene.cycles.use_denoising = True
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.use_sequencer = False
    scene.render.use_persistent_data = True
    receipt = []
    for mode, layout in formats.items():
        box = layout["scene"]
        size = box[2] - box[0], box[3] - box[1]
        for name in ("wide", "candidate_a", "candidate_b", "examiner", "candidates"):
            roles = (list(actors) if name == "wide" else
                     ["candidate_a", "candidate_b"] if name == "candidates" else [name])
            check = render_still(scene, cameras[name], [actors[role] for role in roles], size,
                                 build / "native" / f"{mode}_{name}.png")
            receipt.append({"format": mode, "camera": name, **check})
    freeze_source_animation(scene)
    camera, pose = group_pose(scene, actors)
    visibility = verify_group_visibility(scene, camera, actors)
    scene.cycles.samples = 16
    group = []
    for mode, layout in thumbnail_formats.items():
        box = layout["scene"]
        check = render_still(scene, camera, list(actors.values()),
                             (box[2] - box[0], box[3] - box[1]), build / "native" / f"{mode}_group.png")
        group.append({"format": mode, **check})
    atomic_json(build / "native_checks.json", receipt)
    atomic_json(build / "hair_checks.json", hair)
    atomic_json(build / "thumbnail_native_checks.json", {"pose": pose, "images": group,
                                                        "face_visibility": visibility,
                                                        "hidden_for_group": ["Front wall"],
                                                        "same_table_side": True, "source_scene_saved": False})
