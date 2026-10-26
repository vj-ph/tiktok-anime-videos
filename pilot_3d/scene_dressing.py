"""Opt-in exam-room dressing. Configuration and asset checks need no Blender."""

import hashlib
import json
import math
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "assets" / "props"
COLLECTION = "Episode dressing"
ANCHORS = {
    "flag": {"back_wall_left", "table_corner"},
    "coffee_set": {"examiner_table_side"},
    "backpack": {"candidate_b_chair_side"},
}


def validate_dressing(episode, *, check_assets=False):
    from episode_profiles import active_actors

    dressing = episode.get("scene", {}).get("dressing", {})
    if not isinstance(dressing, dict) or set(dressing) - {"props", "accessories"}:
        raise ValueError("scene.dressing must contain only props and accessories arrays.")
    actors, occupied = active_actors(episode), set()
    for group in ("props", "accessories"):
        items = dressing.get(group, [])
        if not isinstance(items, list):
            raise ValueError(f"scene.dressing.{group} must be an array.")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Each dressing item must be an object.")
            kind = item.get("type")
            if group == "props":
                if not isinstance(kind, str) or kind not in ANCHORS:
                    raise ValueError("Unsupported dressing prop type.")
                anchor = item.get("anchor")
                if not isinstance(anchor, str) or anchor not in ANCHORS[kind]:
                    raise ValueError(f"Unsupported anchor for {kind}.")
                fields = {"type", "anchor"} | ({"pattern"} if kind == "flag" else set())
                if set(item) != fields or kind == "flag" and item["pattern"] != "austria":
                    raise ValueError(f"Unsupported options for {kind}.")
                if anchor == "candidate_b_chair_side" and "candidate_b" not in actors:
                    raise ValueError("Backpack anchor requires active candidate_b.")
                slot = ("anchor", anchor)
            else:
                if (set(item) != {"type", "style", "actor"} or kind != "hat"
                        or item["style"] != "alpine"):
                    raise ValueError("Only type=hat, style=alpine is supported as an accessory.")
                actor = item["actor"]
                if not isinstance(actor, str) or actor not in actors:
                    raise ValueError("Hat owner must be an active scene actor.")
                slot = ("head", actor)
            if slot in occupied:
                raise ValueError("Duplicate dressing anchor or head accessory.")
            occupied.add(slot)
    if check_assets:
        asset_files(episode, verify=True)
    return dressing


def asset_files(episode, *, verify=False):
    selected = {item["type"] for item in episode.get("scene", {}).get("dressing", {}).get("props", [])}
    selected &= {"coffee_set", "backpack"}
    if not selected:
        return []
    provenance = ASSETS / "provenance.json"
    catalog = json.loads(provenance.read_text(encoding="utf-8"))["assets"]
    result = [provenance]
    for kind in sorted(selected):
        record = catalog[kind]
        path = ASSETS / record["file"]
        if verify and hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError(f"Dressing asset checksum mismatch: {path.name}")
        result.append(path)
    return result


def cup_saucer_gaps(cup, saucer):
    from mathutils import Vector

    points = [cup.matrix_world @ vertex.co for vertex in cup.data.vertices]
    bottom = min(p.z for p in points)
    inverse = saucer.matrix_world.inverted()
    gaps = []
    for point in points:
        if point.z > bottom + .0001:
            continue
        hit, position, *_ = saucer.ray_cast(inverse @ (point + Vector((0, 0, .1))),
                                          inverse.to_3x3() @ Vector((0, 0, -1)))
        if not hit:
            raise ValueError("Cup foot overhangs its saucer.")
        gaps.append(point.z - (saucer.matrix_world @ position).z)
    if not gaps:
        raise ValueError("Cup has no measurable foot geometry.")
    return gaps


def head_meshes(actor):
    return [obj for obj in actor.root.children_recursive if obj.type == "MESH"
            and obj.name.startswith("GEO-") and "head" in obj.name.lower()
            and not obj.hide_render and obj.visible_get()]


def world_corners(objects):
    import bpy
    from mathutils import Vector

    graph = bpy.context.evaluated_depsgraph_get()
    evaluated = [obj.evaluated_get(graph) for obj in objects]
    return [obj.matrix_world @ Vector(p) for obj in evaluated for p in obj.bound_box]


def world_vertices(objects):
    import bpy

    graph = bpy.context.evaluated_depsgraph_get()
    evaluated = [obj.evaluated_get(graph) for obj in objects]
    return [obj.matrix_world @ vertex.co for obj in evaluated for vertex in obj.data.vertices]


def hair_crown_clearance(crown, hairs):
    from mathutils import Vector

    inverse = crown.matrix_world.inverted()
    minimum, covered = float("inf"), 0
    for point in world_vertices(hairs):
        point = inverse @ point
        if point.z < .014:
            continue
        if point.z > .17:
            raise ValueError("Covered hair rises outside the hat crown.")
        radial = Vector((point.x, point.y, 0))
        direction = radial.normalized() if radial.length > 1e-8 else Vector((1, 0, 0))
        hit, surface, *_ = crown.ray_cast(Vector((0, 0, point.z)), direction)
        if not hit:
            raise ValueError("Covered hair rises outside the hat crown.")
        minimum = min(minimum, Vector((surface.x, surface.y, 0)).length - radial.length)
        covered += 1
    return minimum, covered


def projected_bounds(scene, camera, points):
    from bpy_extras.object_utils import world_to_camera_view

    projected = [world_to_camera_view(scene, camera, p) for p in points]
    return (min(p.x for p in projected) * 720, min(1 - p.y for p in projected) * 1280,
            max(p.x for p in projected) * 720, max(1 - p.y for p in projected) * 1280)


def fit_hat_camera(scene, actor, hat, timeline, fit_frame):
    from episode_config import CAMERA_PREFIXES

    prefix = CAMERA_PREFIXES.get(actor.name)
    if prefix is None:
        return None
    camera = next(obj for obj in scene.objects if obj.type == "CAMERA" and obj.name.startswith(prefix))
    frames = {fit_frame}
    for turn in timeline["turns"]:
        if turn["speaker"] == actor.name and turn["camera"] == actor.name:
            frames.update(1 + round(t * timeline["fps"]) for t in
                          (turn["start"] + .1, (turn["start"] + turn["end"]) / 2, turn["end"] - .1))
    objects = head_meshes(actor) + [obj for obj in hat.children if obj.type == "MESH"]
    points = []
    for frame in sorted(frames):
        scene.frame_set(frame)
        points.extend(world_corners(objects))
    original = {"lens": camera.data.lens, "shift_x": camera.data.shift_x, "shift_y": camera.data.shift_y}
    bounds = projected_bounds(scene, camera, points)
    target = (120, 286, 480, 556)
    if not (target[0] <= bounds[0] < bounds[2] <= target[2]
            and target[1] <= bounds[1] < bounds[3] <= target[3]):
        camera.data.lens *= min(1, (target[2] - target[0]) / (bounds[2] - bounds[0]),
                               (target[3] - target[1]) / (bounds[3] - bounds[1]))
        for axis, coordinate in (("shift_x", 0), ("shift_y", 1)):
            bounds = projected_bounds(scene, camera, points)
            current = (bounds[coordinate] + bounds[coordinate + 2]) / 2
            wanted = (target[coordinate] + target[coordinate + 2]) / 2
            old = getattr(camera.data, axis)
            setattr(camera.data, axis, old + .01)
            changed = projected_bounds(scene, camera, points)
            delta = (changed[coordinate] + changed[coordinate + 2]) / 2 - current
            setattr(camera.data, axis, old + .01 * (wanted - current) / delta)
    return {"object": camera.name, "before": original, "lens": camera.data.lens,
            "shift_x": camera.data.shift_x, "shift_y": camera.data.shift_y,
            "sample_frames": sorted(frames), "head_and_hat_bounds_px": projected_bounds(scene, camera, points)}


def apply_dressing(scene, episode, actors, fit_frame, timeline):
    import bpy
    from mathutils import Matrix, Vector
    from build_scene import box, empty, material

    config = validate_dressing(episode, check_assets=True)
    if not any(config.get(group) for group in ("props", "accessories")):
        return None
    if bpy.data.collections.get(COLLECTION):
        raise ValueError("Dressing already exists; build from the undressed base scene.")
    collection = bpy.data.collections.new(COLLECTION)
    scene.collection.children.link(collection)
    catalog = json.loads((ASSETS / "provenance.json").read_text(encoding="utf-8"))
    saved_frame = scene.frame_current
    scene.frame_set(fit_frame)
    mats = {name: material("Dressing " + name, color, roughness) for name, color, roughness in (
        ("red", (.65, .018, .026), .7), ("white", (.88, .88, .82), .6),
        ("felt", (.025, .105, .055), .92), ("gold", (.35, .23, .075), .3),
        ("porcelain", (.83, .80, .72), .24), ("coffee", (.025, .009, .003), .2),
        ("glass", (.8, .9, .95), .08),
    )}
    glass = mats["glass"].node_tree.nodes.get("Principled BSDF")
    # Transparent/Fresnel glass keeps the existing four-bounce scene budget.
    nodes, links = mats["glass"].node_tree.nodes, mats["glass"].node_tree.links
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    transparent.inputs["Color"].default_value = (.92, .97, .99, 1)
    fresnel = nodes.new("ShaderNodeFresnel")
    fresnel.inputs["IOR"].default_value = 1.45
    mix = nodes.new("ShaderNodeMixShader")
    links.new(fresnel.outputs[0], mix.inputs[0])
    links.new(transparent.outputs[0], mix.inputs[1])
    links.new(glass.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], nodes.get("Material Output").inputs["Surface"])

    def adopt(obj, name, parent=None):
        obj.name = "Dressing " + name
        for owner in list(obj.users_collection):
            owner.objects.unlink(obj)
        collection.objects.link(obj)
        if parent is not None:
            obj.parent = parent
        return obj

    def cube(name, pos, size, mat, parent):
        return adopt(box("Dressing " + name, pos, size, mat, .001), name, parent)

    def lathe(name, profile, mat, parent, ellipse=1):
        count = 48
        vertices = [(radius * math.cos(2 * math.pi * i / count),
                     radius * ellipse * math.sin(2 * math.pi * i / count), z)
                    for radius, z in profile for i in range(count)]
        faces = [(j * count + i, j * count + (i + 1) % count,
                  (j + 1) * count + (i + 1) % count, (j + 1) * count + i)
                 for j in range(len(profile) - 1) for i in range(count)]
        mesh = bpy.data.meshes.new("Dressing " + name)
        mesh.from_pydata(vertices, [], faces)
        mesh.materials.append(mat)
        obj = bpy.data.objects.new("Dressing " + name, mesh)
        collection.objects.link(obj)
        obj.parent = parent
        for face in mesh.polygons:
            face.use_smooth = True
        return obj

    def normalize(objects, height=None):
        points = [obj.matrix_world @ vertex.co for obj in objects for vertex in obj.data.vertices]
        low = Vector(tuple(min(p[i] for p in points) for i in range(3)))
        high = Vector(tuple(max(p[i] for p in points) for i in range(3)))
        factor = height / (high.z - low.z) if height else 1
        transform = Matrix.Scale(factor, 4) @ Matrix.Translation((-(low.x + high.x) / 2,
                                                                -(low.y + high.y) / 2, -low.z))
        for obj in objects:
            original = obj.data
            obj.data = original.copy()
            if not original.users:
                bpy.data.meshes.remove(original)
            obj.data.transform(transform @ obj.matrix_world)
            obj.parent = None
            obj.matrix_world = Matrix.Identity(4)
        return high - low

    table = scene.objects["Exam table"]
    bpy.context.view_layer.update()
    tabletop = max((table.matrix_world @ Vector(p)).z for p in table.bound_box)
    roots = []
    for index, item in enumerate(config.get("props", [])):
        kind, anchor = item["type"], item["anchor"]
        locations = {
            "back_wall_left": (-1.35, 3.19, 2.25),
            "table_corner": (.95, -.80, tabletop),
            "examiner_table_side": (-.90, -.80, tabletop),
            "candidate_b_chair_side": (1.70, -.27, 0),
        }
        root = adopt(empty("Dressing prop"), f"{index} {kind}", None)
        root.location = locations[anchor]
        entry = {"type": kind, "anchor": anchor, "root": root.name, "location_m": list(root.location)}
        if kind == "flag":
            wall = anchor == "back_wall_left"
            width, height = (.90, .60) if wall else (.24, .16)
            if not wall:
                lathe("flag base", [(0, 0), (.046, 0), (.046, .015), (0, .015)], mats["gold"], root)
                lathe("flag pole", [(0, .015), (.006, .015), (.006, .39), (0, .39)], mats["gold"], root)
            for band, color in enumerate(("red", "white", "red")):
                cube(f"{index} flag stripe {band}", (0 if wall else width / 2 + .007,
                     0, (1 - band) * height / 3 + (0 if wall else .29)),
                     (width, .006, height / 3), mats[color], root)
        elif kind == "coffee_set":
            replaced = [obj for obj in scene.objects
                        if obj.name.startswith("Water cup") and obj.location.x < 0]
            for obj in replaced:
                obj.hide_render = True
                obj.hide_set(True)
            entry["replaced_objects"] = [obj.name for obj in replaced]
            before_materials, before_images = set(bpy.data.materials), set(bpy.data.images)
            with bpy.data.libraries.load(str(ASSETS / catalog["assets"][kind]["file"]), link=False) as (_, target):
                target.objects = ["tea_set_01_cup_small_01", "tea_set_01_saucer_circular_03"]
            for obj, name in zip(target.objects, ("coffee cup", "coffee saucer")):
                if obj is None:
                    raise ValueError("Cup/saucer missing from the pinned tea-set asset.")
                collection.objects.link(obj)
                normalize([obj])
                obj.data.transform(Matrix.Scale(1.25, 4))
                obj.data.materials.clear()
                obj.data.materials.append(mats["porcelain"])
                adopt(obj, name, root)
            cup, saucer = target.objects
            bottom = min(vertex.co.z for vertex in cup.data.vertices)
            foot = [vertex.co for vertex in cup.data.vertices if vertex.co.z <= bottom + .0001]
            center = sum(foot, Vector()) / len(foot)
            cup.data.transform(Matrix.Translation((-center.x, -center.y, 0)))
            bpy.context.view_layer.update()
            cup.location.z -= min(cup_saucer_gaps(cup, saucer)) - .0002
            bpy.context.view_layer.update()
            entry.update(cup_object=cup.name, saucer_object=saucer.name)
            for mat in set(bpy.data.materials) - before_materials:
                mat.use_fake_user = False
                if not mat.users:
                    bpy.data.materials.remove(mat)
            for image in set(bpy.data.images) - before_images:
                image.use_fake_user = False
                if not image.users:
                    bpy.data.images.remove(image)
            coffee_z = cup.location.z + .075
            lathe("coffee surface", [(0, coffee_z), (.061, coffee_z)], mats["coffee"], root)
            water = lathe("water glass", [(0, 0), (.036, 0), (.036, .133), (.033, .133),
                                         (.033, .007), (0, .007)], mats["glass"], root)
            water.location.x = .235
            surface = lathe("glass water", [(0, .008), (.032, .008), (.032, .080), (0, .080)],
                            mats["glass"], root)
            surface.location.x = .235
            entry["source"] = catalog["assets"][kind]
        else:
            before = set(bpy.data.objects)
            bpy.ops.import_scene.gltf(filepath=str(ASSETS / catalog["assets"][kind]["file"]))
            imported = set(bpy.data.objects) - before
            objects = [obj for obj in imported if obj.type == "MESH"]
            if not objects:
                raise ValueError("Pinned backpack has no mesh geometry.")
            bpy.context.view_layer.update()
            normalize(objects, .52)
            for obj in objects:
                adopt(obj, "backpack " + obj.name, root)
            for obj in imported - set(objects):
                bpy.data.objects.remove(obj, do_unlink=True)
            root.rotation_euler.z = -.25
            entry["source"] = catalog["assets"][kind]
        entry["objects"] = [obj.name for obj in root.children_recursive]
        roots.append(entry)

    for item in config.get("accessories", []):
        actor = actors[item["actor"]]
        scene.frame_set(fit_frame)
        bpy.context.view_layer.update()
        head_world = actor.rig.matrix_world @ actor.head.matrix
        # Fit in the unposed head frame, not the world axes of a tilted dialogue pose.
        rest_head_world = actor.rig.matrix_world @ actor.head.bone.matrix_local
        head_pose = head_world @ rest_head_world.inverted()
        fit_inverse = head_pose.inverted()
        heads = head_meshes(actor)
        if not heads:
            raise ValueError(f"{actor.name}: missing head geometry for hat fitting.")
        points = [fit_inverse @ point for point in world_vertices(heads)]
        top, bottom = max(p.z for p in points), min(p.z for p in points)
        seat = top - .15 * (top - bottom)
        hairs = [obj for obj in actor.root.children_recursive if obj.type == "MESH"
                 and "hair" in obj.name.lower() and not obj.hide_render and obj.visible_get()]
        upper = [p for p in points + [fit_inverse @ point for point in world_vertices(hairs)] if p.z >= seat]
        center = Vector(((min(p.x for p in upper) + max(p.x for p in upper)) / 2,
                         (min(p.y for p in upper) + max(p.y for p in upper)) / 2, seat))
        root = adopt(empty("Dressing hat"), actor.name + " alpine hat")
        root.matrix_world = head_pose @ Matrix.Translation(center) @ Matrix.Rotation(actor.root.rotation_euler.z, 4, "Z")
        follow = root.constraints.new("CHILD_OF")
        follow.name, follow.target, follow.subtarget = "Native head attachment", actor.rig, actor.head.name
        follow.inverse_matrix = head_world.inverted()
        lathe("hat brim", [(.145, .006), (.220, -.007), (.223, -.001), (.145, .014)],
              mats["felt"], root, 1.05)
        crown = lathe("hat crown", [(.151, .004), (.154, .04), (.138, .14), (.10, .178), (0, .172)],
                      mats["felt"], root, 1.10)
        for band, color in enumerate(("red", "white", "red")):
            lathe(f"hat band {band}", [(.156 - band * .00192, .04 + band * .012),
                                     (.15408 - band * .00192, .052 + band * .012)],
                  mats[color], root, 1.10)
        hair_fit = None
        if hairs:
            # Preserve the hairline; compress only the hairstyle above the brim.
            cage = bpy.data.lattices.new("Dressing hat hair fit")
            cage.points_u, cage.points_v, cage.points_w = 2, 2, 3
            cage.interpolation_type_u = cage.interpolation_type_v = cage.interpolation_type_w = "KEY_LINEAR"
            for point in cage.points:
                if point.co_deform.z > 0:
                    point.co_deform.x *= .15
                    point.co_deform.y *= .15
                    point.co_deform.z *= .65
            helper = bpy.data.objects.new("Dressing hat hair fit", cage)
            collection.objects.link(helper)
            adopt(helper, actor.name + " hat hair fit", root)
            helper.scale = (.4, .4, .4)
            helper.hide_render = True
            for obj in hairs:
                modifier = obj.modifiers.new("Dressing hat hair fit", "LATTICE")
                modifier.object = helper
            hair_fit = {"object": helper.name, "meshes": [obj.name for obj in hairs]}
        bpy.context.view_layer.update()
        relative = head_world.inverted() @ root.matrix_world
        camera = fit_hat_camera(scene, actor, root, timeline, fit_frame)
        roots.append({"type": "hat", "actor": actor.name, "root": root.name, "camera": camera,
                      "attachment_bone": actor.head.name, "fit_frame": fit_frame,
                      "hair_fit": hair_fit, "crown_object": crown.name,
                      "head_relative_matrix": [list(row) for row in relative],
                      "objects": [obj.name for obj in root.children_recursive if obj.type == "MESH"]})
    scene.frame_set(saved_frame)
    return {"config": config, "collection": collection.name, "items": roots,
            "asset_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in asset_files(episode)}, "tabletop_z_m": tabletop}


def check_dressing(scene, episode, receipt, timeline, entrance, motion_step, actors):
    import bpy
    from mathutils import Matrix, Vector

    config = validate_dressing(episode, check_assets=True)
    if not any(config.get(group) for group in ("props", "accessories")):
        if bpy.data.collections.get(COLLECTION):
            raise ValueError("Unrequested dressing objects exist.")
        return None
    if not receipt or receipt["config"] != config:
        raise ValueError("Dressing configuration/receipt differs from the saved scene.")
    expected_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in asset_files(episode)}
    if receipt["asset_sha256"] != expected_hashes:
        raise ValueError("Dressing source assets differ from the scene receipt.")
    expected_count = sum(len(config.get(group, [])) for group in ("props", "accessories"))
    if len(receipt["items"]) != expected_count:
        raise ValueError("Incomplete dressing receipt.")
    items, checks = receipt["items"], []
    candidate_names = tuple(name for name in actors if name.startswith("candidate"))
    saved_frame = scene.frame_current
    for entry in items:
        root = scene.objects[entry["root"]]
        objects = [scene.objects[name] for name in entry["objects"]]
        if any(not scene.objects[name].hide_render for name in entry.get("replaced_objects", [])):
            raise ValueError("The coffee set's replaced generic water cup remains visible.")
        if not objects or any(obj.hide_render or obj.name not in bpy.data.collections[COLLECTION].objects
                              or obj.parent != root for obj in objects):
            raise ValueError("Dressing geometry is hidden, unparented or outside its collection.")
        if entry["type"] == "hat":
            actor = actors[entry["actor"]]
            scene.frame_set(entry["fit_frame"])
            head_points = [root.matrix_world.inverted() @ point for point in world_vertices(head_meshes(actor))]
            top, bottom = max(p.z for p in head_points), min(p.z for p in head_points)
            seat_depth = top
            if not .12 <= seat_depth / (top - bottom) <= .18:
                raise ValueError(f"Hat is perched above or too low on {actor.name}'s head.")
            hair_fit = entry.get("hair_fit")
            if hair_fit:
                helper = scene.objects[hair_fit["object"]]
                if helper.parent != root or helper.type != "LATTICE":
                    raise ValueError("Hat hair fitting must follow its owner's head.")
                for name in hair_fit["meshes"]:
                    modifiers = scene.objects[name].modifiers
                    if not any(mod.type == "LATTICE" and mod.object == helper
                               and mod.show_render and mod.show_viewport for mod in modifiers):
                        raise ValueError("The hatted actor's local hair fitting is missing.")
            expected = Matrix(entry["head_relative_matrix"])
            samples, portal_samples, camera_samples = 0, 0, 0
            hair_samples, hair_clearance = 0, float("inf")
            camera = scene.objects[entry["camera"]["object"]] if entry.get("camera") else None
            head_objects = head_meshes(actor)
            for frame in range(1, timeline["total_frames"] + 1, motion_step):
                scene.frame_set(frame)
                head = actor.rig.matrix_world @ actor.head.matrix
                actual = head.inverted() @ root.matrix_world
                if actual.translation.length > .35:
                    raise ValueError(f"Hat is not fitted to {actor.name}'s head.")
                error = max(abs(actual[r][c] - expected[r][c]) for r in range(4) for c in range(4))
                if error > 1e-4:
                    raise ValueError(f"Hat does not follow {actor.name}'s head at frame {frame}: {error}")
                if hair_fit:
                    clearance, covered = hair_crown_clearance(
                        scene.objects[entry["crown_object"]],
                        [scene.objects[name] for name in hair_fit["meshes"]])
                    if covered and clearance < .001:
                        raise ValueError(f"Hair protrudes through or touches the hat at frame {frame}: {clearance}")
                    hair_clearance = min(hair_clearance, clearance)
                    hair_samples += 1
                if entrance["enabled"]:
                    points = [obj.matrix_world @ Vector(p) for obj in objects for p in obj.bound_box]
                    if min(p.y for p in points) < 3.44 and max(p.y for p in points) > 3.26:
                        left, right, top = entrance["portal"]
                        if min(p.x for p in points) < left or max(p.x for p in points) > right or max(p.z for p in points) > top:
                            raise ValueError(f"Hat intersects the doorway at frame {frame}.")
                        portal_samples += 1
                t = (frame - 1) / timeline["fps"]
                if camera is not None and any(turn["speaker"] == actor.name and turn["camera"] == actor.name
                                              and turn["start"] <= t < turn["end"] for turn in timeline["turns"]):
                    bounds = projected_bounds(scene, camera, world_corners(head_objects + objects))
                    if not (112 <= bounds[0] < bounds[2] <= 488 and 276 <= bounds[1] < bounds[3] <= 566):
                        raise ValueError(f"Hat/face overlaps captions or leaves its portrait area: {bounds}")
                    camera_samples += 1
                samples += 1
            if entrance["enabled"] and portal_samples < 1:
                raise ValueError("Hat clearance check missed the doorway crossing.")
            checks.append({"type": "hat", "actor": actor.name, "head_follow_samples": samples,
                           "brim_below_head_top_m": seat_depth,
                           "hair_fit_meshes": hair_fit["meshes"] if hair_fit else [],
                           "hair_crown_samples": hair_samples,
                           "minimum_hair_crown_clearance_m": hair_clearance if hair_fit else None,
                           "portal_clearance_samples": portal_samples,
                           "caption_clear_head_and_hat_samples": camera_samples})
        else:
            scene.frame_set(1)
            contact_gap = None
            if entry["type"] == "coffee_set":
                gaps = cup_saucer_gaps(scene.objects[entry["cup_object"]], scene.objects[entry["saucer_object"]])
                contact_gap = min(gaps)
                if not -.0003 <= contact_gap <= .0008:
                    raise ValueError(f"Cup floats over or intersects its saucer: {contact_gap:.4f}m.")
            points = [obj.matrix_world @ Vector(p) for obj in objects for p in obj.bound_box]
            bottom = min(p.z for p in points)
            target = 0 if entry["type"] == "backpack" else receipt["tabletop_z_m"]
            if entry["anchor"] != "back_wall_left" and abs(bottom - target) > .003:
                raise ValueError(f"{entry['type']} floats or intersects its support: {bottom}, {target}")
            if entry["anchor"] != "back_wall_left":
                low = Vector(tuple(min(p[i] for p in points) for i in range(3)))
                high = Vector(tuple(max(p[i] for p in points) for i in range(3)))
            if entry["type"] == "backpack":
                minimum = float("inf")
                for frame in range(1, timeline["total_frames"] + 1, motion_step):
                    scene.frame_set(frame)
                    for name in ("candidate_a", "candidate_b"):
                        actor = scene.objects.get(name)
                        if actor is None or name not in candidate_names:
                            continue
                        pos = actor.matrix_world.translation
                        distance = math.hypot(max(low.x - pos.x, 0, pos.x - high.x),
                                              max(low.y - pos.y, 0, pos.y - high.y))
                        minimum = min(minimum, distance)
                if minimum < .34:
                    raise ValueError(f"Backpack blocks a candidate's route: {minimum:.3f}m.")
                checks.append({"type": "backpack", "support_error_m": abs(bottom - target),
                               "minimum_route_clearance_m": minimum - .34})
            else:
                hand_clearance = None
                if entry["anchor"] != "back_wall_left":
                    table = scene.objects["Exam table"]
                    bounds = [table.matrix_world @ Vector(p) for p in table.bound_box]
                    if (low.x < min(p.x for p in bounds) or high.x > max(p.x for p in bounds)
                            or low.y < min(p.y for p in bounds) or high.y > max(p.y for p in bounds)):
                        raise ValueError(f"{entry['type']} overhangs the tabletop.")
                    hand_clearance = float("inf")
                    for frame in range(1, timeline["total_frames"] + 1, motion_step):
                        scene.frame_set(frame)
                        for actor in actors.values():
                            prefix = "FK-" if actor.kind == "rain" else "FK-Finger_"
                            for side in ("L", "R"):
                                for finger in ("Index", "Middle"):
                                    p = actor.rig.matrix_world @ actor.bones[f"{prefix}{finger}3.{side}"].tail
                                    distance = math.sqrt(sum(max(low[i] - p[i], 0, p[i] - high[i]) ** 2
                                                             for i in range(3)))
                                    hand_clearance = min(hand_clearance, distance)
                    if hand_clearance < .012:
                        raise ValueError(f"{entry['type']} intersects a hand: {hand_clearance:.4f}m.")
                checks.append({"type": entry["type"], "anchor": entry["anchor"],
                               "support_error_m": None if entry["anchor"] == "back_wall_left" else abs(bottom - target),
                               "minimum_fingertip_clearance_m": hand_clearance,
                               "cup_saucer_contact_gap_m": contact_gap})
    for image in bpy.data.images:
        if image.users and image.source == "FILE" and not image.packed_file:
            raise ValueError(f"Unpacked image in dressed scene: {image.name}")
    scene.frame_set(saved_frame)
    return {"items": checks, "asset_sha256": expected_hashes, "external_images_packed": True}
