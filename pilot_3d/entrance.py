"""Physical doorway, outside-to-chair blocking and door timing for exam_room."""

import math

PORTAL = (-3.42, -2.38, 2.30)
HINGE = (-3.41, 3.055, 0)
BODY_RADIUS = .34
MAX_WALK_SPEED = 1.85


def ease(value):
    value = min(1.0, max(0.0, value))
    return value * value * (3 - 2 * value)


def path_at(points, progress):
    lengths = [math.dist(a[:2], b[:2]) for a, b in zip(points, points[1:])]
    if not lengths or any(length <= 0 for length in lengths):
        raise ValueError("Entrance path requires nonzero segments.")
    if progress >= 1:
        a, b = points[-2:]
        return tuple(b), math.atan2(b[0] - a[0], a[1] - b[1])
    distance = min(1, max(0, progress)) * sum(lengths)
    for index, (a, b, length) in enumerate(zip(points, points[1:], lengths)):
        if distance <= length or index == len(lengths) - 1:
            blend = min(1.0, distance / length)
            return tuple(x + (y - x) * blend for x, y in zip(a, b)), math.atan2(b[0] - a[0], a[1] - b[1])
        distance -= length


def walk_pose(blocking, t):
    start, end, points = blocking["walk_start"], blocking["walk_end"], blocking["path"]
    position, angle = path_at(points, (t - start) / (end - start))
    before = path_at(points, (t - .18 - start) / (end - start))[0]
    after = path_at(points, (t + .18 - start) / (end - start))[0]
    if math.dist(before, after) > 1e-8:
        angle = math.atan2(after[0] - before[0], before[1] - after[1])
    return position, angle * (1 - ease((t - end) / .35))


def entrance_plan(episode, timeline):
    from episode_config import entrance_enabled, seating_deadline

    result = {"enabled": entrance_enabled(episode), "portal": PORTAL, "hinge": HINGE,
              "body_radius_m": BODY_RADIUS, "actors": {}}
    if not result["enabled"]:
        return result
    last_seat = min(seating_deadline(episode, timeline), 8.0) - .12
    for name, x, start, outside_y in (
            ("candidate_a", -.82, .65, 3.95), ("candidate_b", .82, 1.20, 4.8)):
        seat_end = last_seat - (.8 if name == "candidate_a" else 0)
        points = ([(-2.9, outside_y, 0), (-2.9, 2.85, 0), (-2.9, 1.35, 0),
                   (-1.38, 1.35, 0), (-1.38, .30, 0), (x, .30, 0)]
                  if name == "candidate_a" else
                   [(-2.9, outside_y, 0), (-2.9, 2.35, 0), (1.4, 1.35, 0), (1.4, .30, 0), (x, .30, 0)])
        length = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
        walk_end = seat_end - 1.5
        speed = length / (walk_end - start) if walk_end > start else float("inf")
        if speed > MAX_WALK_SPEED:
            raise ValueError(f"Welcome/intro leave insufficient time for an outside entrance: {name} "
                             f"would walk at {speed:.2f}m/s (maximum {MAX_WALK_SPEED:.2f}). "
                             "Increase the welcome pause_after or disable scene.entrance.")
        result["actors"][name] = {"walk_start": start, "walk_end": walk_end,
                                  "seat_start": seat_end - 1.15, "seat_end": seat_end,
                                  "path": points, "walk_speed_m_s": speed}
    second = result["actors"]["candidate_b"]
    points = second["path"]
    clear_x = HINGE[0] + 1.02 + BODY_RADIUS + .06
    distance = math.dist(points[0], points[1])
    distance += math.dist(points[1], points[2]) * (clear_x - points[1][0]) / (points[2][0] - points[1][0])
    close_start = second["walk_start"] + distance / second["walk_speed_m_s"] + .20
    result["door"] = {"open_start": .15, "open_end": .85,
                      "close_start": close_start, "close_end": close_start + .90}
    return result


def door_angle(plan, t):
    if not plan["enabled"]:
        return 0.0
    door = plan["door"]
    return -math.pi / 2 * ease((t - door["open_start"]) / (door["open_end"] - door["open_start"])) * (
        1 - ease((t - door["close_start"]) / (door["close_end"] - door["close_start"])))


def doorway_geometry(scene):
    import bpy
    from mathutils import Vector
    from build_scene import box

    def open_mesh(obj, left, right, top, front, back):
        inner_left, inner_right, inner_top = PORTAL
        boundary = [(left, 0), (inner_left, 0), (inner_left, inner_top), (inner_right, inner_top),
                    (inner_right, 0), (right, 0), (right, top), (left, top)]
        inverse = obj.matrix_world.inverted()
        vertices = [inverse @ Vector((x, y, z)) for y in (front, back) for x, z in boundary]
        faces = [tuple(range(8)), tuple(reversed(range(8, 16)))]
        faces += [(i, i + 8, (i + 1) % 8 + 8, (i + 1) % 8) for i in range(8)]
        mesh = bpy.data.meshes.new(obj.name + " open portal")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        for mat in obj.data.materials:
            mesh.materials.append(mat)
        obj.data = mesh

    bpy.context.view_layer.update()
    open_mesh(scene.objects["Back wall"], -4.5, 4.5, 3.5, 3.26, 3.44)
    frame = scene.objects["Door frame"]
    open_mesh(frame, -3.48, -2.32, 2.38, 3.05, 3.35)
    for modifier in frame.modifiers:
        if modifier.type == "BEVEL":
            modifier.width = .010
    skirting = scene.objects["Wall skirting"]
    mat = skirting.data.materials[0]
    bpy.data.objects.remove(skirting, do_unlink=True)
    for name, left, right in (("left", -4.0, -3.48), ("right", -2.32, 4.0)):
        box("Entrance skirting " + name, ((left + right) / 2, 3.23, .09),
            (right - left, .07, .17), mat, .015)
    wall_mat = scene.objects["Front wall"].data.materials[0]
    floor_mat = scene.objects["Floor"].data.materials[0]
    box("Entrance corridor floor", (-2.9, 5.7, -.1), (2.44, 2.4, .2), floor_mat, 0)
    for name, position, size in (
            ("left wall", (-4.06, 5.1, 1.75), (.12, 3.5, 3.5)),
            ("right wall", (-1.74, 5.1, 1.75), (.12, 3.5, 3.5)),
            ("back wall", (-2.9, 6.85, 1.75), (2.44, .12, 3.5))):
        box("Entrance corridor " + name, position, size, wall_mat, .015)
    lamp = bpy.data.lights.new("Entrance corridor ceiling", "AREA")
    lamp.energy, lamp.size, lamp.color = 85, 1.2, (1.0, .94, .84)
    obj = bpy.data.objects.new("Entrance corridor ceiling", lamp)
    scene.collection.objects.link(obj)
    obj.location = (-2.9, 5.0, 3.15)
    return {"portal_m": PORTAL, "corridor_back_y_m": 6.85,
            "method": "Open wall and U-shaped frame; interrupted skirting; continuous floor into a lit corridor."}
