"""Speech-led acting and restrained art direction for the reusable exam room."""

import math
from episode_profiles import ACTORS, active_actors, language_profile, scene_layout

VERSION = 7
GESTURE_LIMITS = {
    "welcome": 1, "explain": 2, "propose": 2, "consider": 1, "agree": 1,
    "introduce": 3, "describe": 3, "ask": 1, "answer": 2,
}
FUNCTION_WORDS = set(language_profile({})["function_words"].split())


def ease(value):
    value = min(1.0, max(0.0, value))
    return value * value * (3 - 2 * value)


def envelope(t, peak, rise=0.35, hold=0.10, fall=0.65):
    if t < peak:
        return ease((t - peak + rise) / rise)
    return 1 - ease((t - peak - hold) / fall)


def conversation_turn(timeline, t):
    return next((turn for turn in reversed(timeline["turns"]) if turn["start"] <= t), None)


def attention_yaw(actor, turn):
    target = turn.get("look_at") if turn["speaker"] == actor else turn["speaker"]
    if actor.startswith("candidate"):
        if target in ("candidate_a", "candidate_b") and target != actor:
            return .48 if actor == "candidate_a" else -.48
    elif target in ("candidate_a", "candidate_b"):
        return .10 if target == "candidate_a" else -.10
    return 0.0


def gaze_at(plan, actor, t):
    events = plan["attention"][actor]

    def track(delay, duration):
        value = 0.0
        for index, event in enumerate(events):
            if event["start"] > t:
                break
            stop = min(t, events[index + 1]["start"]) if index + 1 < len(events) else t
            value += (event["yaw"] - value) * ease((stop - event["start"] - delay) / duration)
        return value

    head = track(.06, .60)
    eyes = track(0, .42) * 1.18
    # Eyes lead the head, but never swivel far enough to hide the irises.
    eyes = head + min(.16, max(-.16, eyes - head))
    return {"head": head, "eyes": eyes}


def blink_at(plan, actor, t, fps, motion_step):
    pose_fps = fps / motion_step
    return max((math.cos(math.pi * (t - round(peak * pose_fps) / pose_fps) / .18) ** 2
                if abs(t - round(peak * pose_fps) / pose_fps) < .09 else 0.0
                for peak in plan["blinks"][actor]), default=0.0)


def performance_plan(timeline, episode=None):
    gestures, nods, glances = [], [], []
    context = episode if episode is not None else timeline
    actors = active_actors(context)
    function_words = set(language_profile(context)["function_words"].split())
    attention = {actor: [] for actor in actors}
    counts = {}
    for index, turn in enumerate(timeline["turns"]):
        speaker, action = turn["speaker"], turn["action"]
        for actor in actors:
            events = attention[actor]
            yaw = attention_yaw(actor, turn)
            if yaw != (events[-1]["yaw"] if events else 0.0):
                events.append({"start": turn["start"], "yaw": yaw})
        ordinal = counts.get(speaker, 0)
        counts[speaker] = ordinal + 1
        words = turn["words"]
        phrases, phrase = [], []
        for word in words:
            phrase.append(word)
            if word["word"].endswith((",", ".", "?", "!", ";", ":")):
                phrases.append(phrase)
                phrase = []
        if phrase:
            phrases.append(phrase)
        peaks = []
        for phrase in phrases:
            candidates = [word for word in phrase if word["start"] >= 0.30 and
                          word["end"] <= turn["duration"] - 0.12 and
                          word["word"].strip(".,?!;:").lower() not in function_words]
            if not candidates:
                continue
            focus = max(candidates, key=lambda w: min(14, len(w["word"])) +
                        0.25 * (w["start"] - phrase[0]["start"]))
            peak = turn["start"] + (focus["start"] + focus["end"]) / 2
            if not peaks or peak - peaks[-1][0] >= 2.15:
                peaks.append((peak, focus["word"]))
            if action not in ("introduce", "describe") and len(peaks) == GESTURE_LIMITS[action]:
                break
        if action in ("introduce", "describe") and len(peaks) > GESTURE_LIMITS[action]:
            peaks = [peaks[round(i * (len(peaks) - 1) / (GESTURE_LIMITS[action] - 1))]
                     for i in range(GESTURE_LIMITS[action])]
        for beat, (peak, word) in enumerate(peaks):
            side = "L" if (ordinal + beat + (speaker == "candidate_b")) % 2 == 0 else "R"
            gestures.append({
                "actor": speaker, "turn_id": turn["id"], "action": action,
                "peak": peak, "word": word, "hand": side,
                "strength": {"consider": .68, "introduce": .72, "describe": .72, "ask": .55, "answer": .75}.get(
                    action, 1.0) * (1 if beat == 0 else 0.72),
                "rise": (.32, .42, .36)[ordinal % 3],
                "hold": (.08, .14, .06)[ordinal % 3],
                "fall": (.62, .74, .56)[ordinal % 3],
                "reach": (.80, 1.0, .90)[ordinal % 3],
            })
        if action == "agree":
            nods.append({"actor": speaker, "peak": turn["start"] + words[0]["end"] + 0.10,
                         "amount": 0.065})
        following = timeline["turns"][index + 1] if index + 1 < len(timeline["turns"]) else None
        listener = turn.get("look_at")
        partner_response = (
            listener in ("candidate_a", "candidate_b") and listener != speaker and following
            and (following["action"] == "agree" or (ordinal % 2 == 0 and turn["duration"] >= 3)))
        interview_response = listener == "examiner" and action in ("introduce", "describe", "answer") and turn["duration"] >= 3
        if (speaker.startswith("candidate") and following and following["speaker"] == listener
                and (partner_response or interview_response)):
            peak = min(turn["start"] + words[-1]["end"] + .12, following["start"] - .34)
            if peak - .19 >= turn["start"]:
                nods.append({
                    "actor": listener, "turn_id": turn["id"], "kind": "listener",
                    "peak": peak,
                    "amount": .034 if following["action"] == "agree" else .022,
                })
        if action == "consider":
            pause = next(((left["end"] + right["start"]) / 2 for left, right in zip(words, words[1:])
                          if right["start"] - left["end"] >= 0.18 and left["end"] >= 1.1
                          and right["start"] < turn["duration"] - 0.75), None)
            if pause is not None:
                glances.append({"actor": speaker, "peak": turn["start"] + pause, "amount": 0.30})
        if "observer" in actors and speaker.startswith("candidate") and index % 3 == 1:
            glances.append({"actor": "observer", "peak": turn["start"] + min(1.6, turn["duration"] / 2),
                            "amount": 0.6})
    blinks = {}
    for actor in actors:
        index = ACTORS.index(actor)
        peaks, peak, ordinal = [], .65 + index * .61, 0
        while peak < timeline["duration"]:
            peaks.append(peak)
            peak += (4.3, 5.1, 3.9, 4.8)[(ordinal + index) % 4]
            ordinal += 1
        for event in attention[actor]:
            if abs(event["yaw"]) < .2:
                continue
            peak = event["start"] + .12
            if peak < timeline["duration"]:
                peaks = [value for value in peaks if abs(value - peak) >= .75]
                peaks.append(peak)
        blinks[actor] = sorted(peaks)
    return {"version": VERSION, "gestures": gestures, "nods": nods, "glances": glances,
            "attention": attention, "blinks": blinks,
            "timing": "Aligned, varied emphasis; selective listener responses; bounded eye lead and smooth head turns."}


def performance_at(plan, actor, t):
    hands = {"L": 0.0, "R": 0.0}
    actions = {"L": "", "R": ""}
    reach = {"L": 1.0, "R": 1.0}
    for event in plan["gestures"]:
        if event["actor"] != actor:
            continue
        value = event["strength"] * envelope(t, event["peak"], event["rise"], event["hold"], event["fall"])
        if value > hands[event["hand"]]:
            hands[event["hand"]] = value
            actions[event["hand"]] = event["action"]
            reach[event["hand"]] = event["reach"]
    nod = sum(event["amount"] * envelope(t, event["peak"], .19, 0, .32)
              for event in plan["nods"] if event["actor"] == actor)
    glance = max((event["amount"] * envelope(t, event["peak"], .20, .08, .42)
                  for event in plan["glances"] if event["actor"] == actor), default=0.0)
    return {"hands": hands, "actions": actions, "reach": reach, "accent": max(hands.values()),
            "nod": min(.085, nod), "glance": glance}


def configure_cameras(scene, episode=None, timeline=None):
    from mathutils import Vector

    cameras = {name: next(obj for obj in scene.objects if obj.type == "CAMERA" and obj.name.startswith(prefix))
               for name, prefix in (("wide", "01"), ("examiner", "02"), ("candidates", "03"),
                                    ("candidate_a", "04"), ("candidate_b", "05"))}
    for name, location, target in (
        ("candidate_a", (-.45, -1.60, 1.62), (-.82, .65, 1.17)),
        ("candidate_b", (.45, -1.60, 1.65), (.82, .65, 1.23)),
    ):
        camera = cameras[name]
        camera.location = location
        camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
        camera.data.lens = 47
    if episode and episode.get("pictures"):
        from bpy_extras.object_utils import world_to_camera_view
        from picture_presentation import FACE_BOX, PICTURE_CAMERAS
        from studio_characters import StudioCharacter
        for role, name in PICTURE_CAMERAS.items():
            turn = next((t for t in timeline["turns"] if t["speaker"] == role and t["action"] == "describe"), None)
            if turn is None:
                continue
            scene.frame_set(1 + round((turn["start"] + .5) * timeline["fps"]))
            camera = cameras[role].copy()
            camera.data = camera.data.copy()
            camera.name = ("06" if role == "candidate_a" else "07") + " Picture " + role
            scene.collection.objects.link(camera)
            actor = StudioCharacter.from_scene(role)
            mesh = next(obj for obj in actor.root.children_recursive
                        if obj.type == "MESH" and obj.name.startswith("GEO-") and "head" in obj.name.lower())
            evaluated = mesh.evaluated_get(scene.view_layers[0].depsgraph)
            points = [evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box]

            def bounds():
                projected = [world_to_camera_view(scene, camera, point) for point in points]
                return (min(p.x for p in projected) * 720, min(1-p.y for p in projected) * 1280,
                        max(p.x for p in projected) * 720, max(1-p.y for p in projected) * 1280)

            box = bounds()
            camera.data.lens *= min(1, 158 / (box[2]-box[0]), 235 / (box[3]-box[1]))
            for axis, target, coordinate in (("shift_x", 420, 0), ("shift_y", 446, 1)):
                box = bounds()
                current = (box[coordinate] + box[coordinate+2]) / 2
                old = getattr(camera.data, axis)
                setattr(camera.data, axis, old + .01)
                changed = bounds()
                delta = (changed[coordinate] + changed[coordinate+2]) / 2 - current
                setattr(camera.data, axis, old + .01 * (target-current) / delta)
            box = bounds()
            if not (FACE_BOX[0] <= box[0] < box[2] <= FACE_BOX[2]
                    and FACE_BOX[1] <= box[1] < box[3] <= FACE_BOX[3]):
                raise ValueError(f"{role}: picture camera cannot keep the face clear: {box}")
            cameras[name] = camera
    return cameras


def configure_cast(scene, episode):
    active = active_actors(episode)
    hidden = []

    def hide(obj):
        animation = getattr(obj, "animation_data", None)
        if animation is not None:
            for curve in animation.drivers:
                if curve.data_path == "hide_render":
                    # Native visibility drivers otherwise undo the inactive cast's hide flags.
                    curve.mute = True
        obj.hide_render = True
        obj.hide_set(True)
        hidden.append(obj.name)

    for name in ACTORS:
        if name in active:
            continue
        root = scene.objects[name]
        for obj in (root, *root.children_recursive):
            hide(obj)
    if scene_layout(episode) == "interview":
        for obj in scene.objects:
            unused_chair = (obj.name.startswith("Chair") and obj.parent is None and obj.location.x > 0
                            and (obj.location.y > 0 or "observer" not in active))
            unused_task = obj.name.startswith(("Task sheet", "Printed task line")) and obj.location.x > 0
            personal_item = obj.name.startswith(("Pen", "Water cup", "Examiner clipboard", "Examiner notes"))
            if unused_chair or unused_task or personal_item:
                for item in (obj, *obj.children_recursive):
                    hide(item)
    return {"layout": scene_layout(episode), "active_actors": list(active),
            "hidden_objects": sorted(set(hidden))}


def room_design(scene, episode):
    import bpy
    from mathutils import Vector
    from build_scene import box, material
    from prepare_audio import sha256_file
    from pathlib import Path

    palette = {
        "ivory": (.73, .75, .69), "sage": (.35, .45, .39),
        "oak": (.43, .29, .17), "navy": (.035, .065, .10),
        "felt": (.09, .14, .13), "ceramic": (.62, .57, .47),
    }
    mats = {name: material("wood" if name == "oak" else "Direction " + name, color)
            for name, color in palette.items()}
    mats["oak"].name = "Direction oak"
    for name, mat in (("Back wall", mats["sage"]), ("Front wall", mats["ivory"]),
                      ("Left wall", mats["ivory"]), ("Exam table", mats["oak"]),
                      ("Door", mats["navy"]), ("Door frame", mats["oak"]),
                      ("Wall skirting", mats["oak"])):
        obj = scene.objects[name]
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    for obj in list(scene.objects):
        if obj.name.startswith(("Wall art", "Abstract print")):
            obj.hide_render = True
        elif obj.name.startswith("Acoustic oak slat"):
            obj.data.materials.clear()
            obj.data.materials.append(mats["oak"])
    box("Direction acoustic felt", (2.76, 3.255, 1.8), (1.57, .045, 2.65), mats["felt"], .015)
    box("Direction storage cabinet", (1.55, 2.95, .39), (1.55, .42, .75), mats["oak"], .025)
    for x in (1.17, 1.93):
        box("Direction cabinet door", (x, 2.724, .39), (.735, .026, .66), mats["ivory"], .012)
        box("Direction recessed pull", (x, 2.704, .64), (.16, .012, .012), mats["navy"], .004)
    for index, (width, mat) in enumerate(((.31, mats["navy"]), (.28, mats["ivory"]), (.33, mats["sage"]))):
        box("Direction reference book", (1.85, 2.92, .781 + index * .032), (width, .23, .032), mat, .003)
    box("Direction window sill", (-3.76, .7, 1.22), (.28, 2.22, .07), mats["ivory"], .012)
    lights = sorted((obj for obj in scene.objects if obj.type == "LIGHT"), key=lambda obj: obj.location.x)
    if len(lights) != 3:
        raise ValueError(f"The exam_room lighting contract expects three area lights; got {len(lights)}.")
    for lamp, energy, color, size in zip(
            lights, (310, 175, 130), ((.91, .96, 1.0), (1.0, .90, .76), (.94, .96, 1.0)), (3.5, 2.4, 3.0)):
        lamp.data.energy, lamp.data.color, lamp.data.size = energy, color, size
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (.80, .85, .88, 1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = .19
    scene.view_settings.look = "AgX - Medium High Contrast"
    result = {"version": VERSION, "palette": palette, "logo": None,
              "intent": "Sage acoustic wall, light oak, neutral daylight, tidy examination furniture."}
    logo = episode.get("scene", {}).get("wall_logo")
    if logo:
        image = bpy.data.images.load(logo, check_existing=True)
        image.colorspace_settings.name = "sRGB"
        image.pack()
        ratio = image.size[0] / image.size[1]
        width, height = .42 * min(1, ratio), .42 * min(1, 1 / ratio)
        center = Vector((-1.76, 3.1235, 1.47))
        box("Direction logo frame", (center.x, 3.18, center.z),
            (width + .065, .065, height + .065), mats["oak"], .012)
        box("Direction logo mount", (center.x, 3.137, center.z),
            (width + .035, .025, height + .035), mats["ivory"], .006)
        bpy.ops.mesh.primitive_plane_add(size=1, location=center, rotation=(math.pi / 2, 0, 0))
        plane = bpy.context.object
        plane.name = "Direction Deutsch Kompass wall logo"
        plane.scale = (width, height, 1)
        logo_mat = material("Direction original logo print", palette["ivory"], .78)
        nodes, links = logo_mat.node_tree.nodes, logo_mat.node_tree.links
        texture = nodes.new("ShaderNodeTexImage")
        texture.image, texture.extension = image, "CLIP"
        mix = nodes.new("ShaderNodeMixRGB")
        mix.inputs[1].default_value = (*palette["ivory"], 1)
        links.new(texture.outputs["Alpha"], mix.inputs[0])
        links.new(texture.outputs["Color"], mix.inputs[2])
        shader = nodes.get("Principled BSDF")
        links.new(mix.outputs["Color"], shader.inputs["Base Color"])
        plane.data.materials.append(logo_mat)
        plane["original_logo_sha256"] = sha256_file(Path(logo))
        result["logo"] = {"path": logo, "sha256": plane["original_logo_sha256"],
                          "object": plane.name, "packed_image": image.name,
                          "width_m": width, "height_m": height, "center_m": list(center)}
    return result
