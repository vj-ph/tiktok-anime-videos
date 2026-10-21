"""Speech-led acting and restrained art direction for the reusable exam room."""

import math

VERSION = 6
FUNCTION_WORDS = set(
    "aber als am an auch auf aus bei bis das dem den der des die doch du ein eine "
    "einem einen einer es für haben ich im in ist ja können könnten mit nach nicht "
    "oder sie so um und uns von vor wäre wir zu zum zur".split()
)


def ease(value):
    value = min(1.0, max(0.0, value))
    return value * value * (3 - 2 * value)


def envelope(t, peak, rise=0.35, hold=0.10, fall=0.65):
    if t < peak:
        return ease((t - peak + rise) / rise)
    return 1 - ease((t - peak - hold) / fall)


def conversation_turn(timeline, t):
    return next((turn for turn in reversed(timeline["turns"]) if turn["start"] <= t), None)


def performance_plan(timeline):
    gestures, nods, glances = [], [], []
    counts = {}
    for index, turn in enumerate(timeline["turns"]):
        speaker, action = turn["speaker"], turn["action"]
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
                          word["word"].strip(".,?!;:").lower() not in FUNCTION_WORDS]
            if not candidates:
                continue
            focus = max(candidates, key=lambda w: min(14, len(w["word"])) +
                        0.25 * (w["start"] - phrase[0]["start"]))
            peak = turn["start"] + (focus["start"] + focus["end"]) / 2
            if not peaks or peak - peaks[-1][0] >= 2.15:
                peaks.append((peak, focus["word"]))
            if len(peaks) == 3:
                break
        for beat, (peak, word) in enumerate(peaks):
            side = "L" if (ordinal + beat + (speaker == "candidate_b")) % 2 == 0 else "R"
            gestures.append({
                "actor": speaker, "turn_id": turn["id"], "action": action,
                "peak": peak, "word": word, "hand": side,
                "strength": (0.68 if action == "consider" else 1.0) * (1 if beat == 0 else 0.72),
            })
        if action == "agree":
            nods.append({"actor": speaker, "peak": turn["start"] + words[0]["end"] + 0.10,
                         "amount": 0.065})
        following = timeline["turns"][index + 1] if index + 1 < len(timeline["turns"]) else None
        if speaker.startswith("candidate") and following and following["speaker"] != speaker:
            nods.append({
                "actor": following["speaker"],
                "peak": turn["start"] + words[-1]["end"] + 0.16,
                "amount": 0.042 if following["action"] == "agree" else 0.024,
            })
        if action == "consider":
            pause = next(((left["end"] + right["start"]) / 2 for left, right in zip(words, words[1:])
                          if right["start"] - left["end"] >= 0.18 and left["end"] >= 1.1
                          and right["start"] < turn["duration"] - 0.75), None)
            if pause is not None:
                glances.append({"actor": speaker, "peak": turn["start"] + pause, "amount": 0.30})
        if speaker.startswith("candidate") and index % 3 == 1:
            glances.append({"actor": "observer", "peak": turn["start"] + min(1.6, turn["duration"] / 2),
                            "amount": 0.6})
    return {"version": VERSION, "gestures": gestures, "nods": nods, "glances": glances,
            "timing": "Aligned content-word emphasis; anticipation, hold and release; attention held across gaps."}


def performance_at(plan, actor, t):
    hands = {"L": 0.0, "R": 0.0}
    actions = {"L": "", "R": ""}
    for event in plan["gestures"]:
        if event["actor"] != actor:
            continue
        value = event["strength"] * envelope(t, event["peak"])
        if value > hands[event["hand"]]:
            hands[event["hand"]] = value
            actions[event["hand"]] = event["action"]
    nod = sum(event["amount"] * envelope(t, event["peak"], .19, 0, .32)
              for event in plan["nods"] if event["actor"] == actor)
    glance = max((event["amount"] * envelope(t, event["peak"], .20, .08, .42)
                  for event in plan["glances"] if event["actor"] == actor), default=0.0)
    return {"hands": hands, "actions": actions, "accent": max(hands.values()),
            "nod": min(.085, nod), "glance": glance}


def configure_cameras(scene):
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
    return cameras


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
