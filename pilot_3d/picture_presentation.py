"""Timed picture stimuli shared by the screenplay, compositor and delivery checks."""

from pathlib import Path

from prepare_audio import SAFE_ID, ceil_frames, nonempty, number, sha256_file

PICTURE_CAMERAS = {"candidate_a": "picture_a", "candidate_b": "picture_b"}
REVEAL_BOX = (104, 344, 496, 558)
COMPACT_BOX = (104, 310, 324, 430)
FACE_BOX = (336, 284, 504, 570)


def validate_pictures(episode, *, check_assets=False):
    pictures = episode.get("pictures", {})
    if not isinstance(pictures, dict):
        raise ValueError("pictures must be an object.")
    owners = set()
    for key, picture in pictures.items():
        if not isinstance(key, str) or not SAFE_ID.fullmatch(key) or not isinstance(picture, dict):
            raise ValueError("Pictures require safe IDs and object values.")
        for field in ("path", "label", "credit", "permission"):
            nonempty(picture.get(field), f"pictures.{key}.{field}")
        owner = picture.get("candidate")
        if not isinstance(owner, str) or owner not in PICTURE_CAMERAS or owner in owners:
            raise ValueError("The exam_room template supports one picture per candidate.")
        owners.add(owner)
        if check_assets:
            from PIL import Image
            with Image.open(picture["path"]) as image:
                if min(image.size) < 392:
                    raise ValueError(f"Picture {key}: source is too small for the reading card.")
                image.verify()
    used = set()
    turns = episode["turns"]
    for index, turn in enumerate(turns):
        key = turn.get("picture")
        if "picture" in turn:
            if not isinstance(key, str) or key not in pictures:
                raise ValueError(f"Turn {turn['id']}: picture must name a declared image.")
            used.add(key)
            owner = pictures[key]["candidate"]
            if "picture_card_delay_seconds" in turn:
                delay = number(turn["picture_card_delay_seconds"], "picture_card_delay_seconds")
                if (turn["speaker"] != "examiner" or turn.get("look_at") != owner
                        or ceil_frames(delay, episode["fps"]) >= ceil_frames(turn["pause_after"], episode["fps"])):
                    raise ValueError("Picture reveal requires an examiner prompt and positive reading time.")
                following = turns[index + 1] if index + 1 < len(turns) else {}
                if following.get("picture") != key or following.get("action") != "describe":
                    raise ValueError("Picture reveal must immediately precede its candidate description.")
                if episode.get("task_card") and turn.get("action") == "explain" and turn.get("phase") != "dialogue":
                    raise ValueError("Use the picture reading card, not a simultaneous text task_card.")
            elif (turn["speaker"] != owner or turn.get("action") != "describe"
                  or turn.get("camera") != PICTURE_CAMERAS[owner]):
                raise ValueError("A picture description requires its owner and picture camera.")
        elif "picture_card_delay_seconds" in turn or turn.get("camera") in PICTURE_CAMERAS.values():
            raise ValueError("Picture timing and picture cameras require a declared picture.")
        elif turn.get("action") == "describe":
            raise ValueError("describe requires a picture stimulus.")
    if used != set(pictures):
        raise ValueError("Every declared picture must be used by the screenplay.")
    for key in pictures:
        descriptions = [t for t in turns if t.get("picture") == key and t.get("action") == "describe"]
        reveals = [t for t in turns if t.get("picture") == key and "picture_card_delay_seconds" in t]
        if not descriptions or len(reveals) != len(descriptions):
            raise ValueError("Each picture description needs its own reading-card prompt.")


def picture_windows(episode, timeline):
    windows = []
    for index, turn in enumerate(timeline["turns"]):
        if "picture" not in turn:
            continue
        stop = (timeline["turns"][index + 1]["start"] if index + 1 < len(timeline["turns"])
                else timeline["duration"] - episode.get("outro_seconds", 0))
        reveal = "picture_card_delay_seconds" in turn
        start = (turn["end"] + ceil_frames(turn["picture_card_delay_seconds"], timeline["fps"]) / timeline["fps"]
                 if reveal else turn["start"])
        if stop <= start:
            raise ValueError(f"Turn {turn['id']}: no picture display time.")
        windows.append({"picture": turn["picture"], "turn": turn["id"],
                        "mode": "reveal" if reveal else "compact",
                        "start": start, "end": stop,
                        "start_frame": round(start * timeline["fps"]),
                        "end_frame": round(stop * timeline["fps"])})
    return windows


def picture_bounds(path, mode):
    from PIL import Image
    box = REVEAL_BOX if mode == "reveal" else COMPACT_BOX
    with Image.open(path) as image:
        scale = min((box[2] - box[0]) / image.width, (box[3] - box[1]) / image.height)
        width, height = (max(2, round(value * scale / 2) * 2) for value in image.size)
    # Match overlay's 4:2:0 chroma grid, including portrait letterboxing.
    x = (box[0] + (box[2] - box[0] - width) // 2) // 2 * 2
    y = (box[1] + (box[3] - box[1] - height) // 2) // 2 * 2
    return x, y, x + width, y + height


def picture_filters(episode, timeline, input_start=2):
    """Overlay after full-rate ASS; frame-index enables cannot drift on odd frames."""
    inputs, filters, windows = [], [], []
    previous = "captioned"
    for index, window in enumerate(picture_windows(episode, timeline)):
        picture = episode["pictures"][window["picture"]]
        path = picture["path"]
        x, y, right, bottom = picture_bounds(path, window["mode"])
        inputs += ["-loop", "1", "-framerate", str(timeline["fps"]), "-i", path]
        filters.append(f"[{input_start + index}:v]scale={right-x}:{bottom-y}:flags=lanczos,setsar=1[stimulus{index}]")
        output = f"pictured{index}"
        filters.append(f"[{previous}][stimulus{index}]overlay=x={x}:y={y}:"
                       f"enable='gte(n,{window['start_frame']})*lt(n,{window['end_frame']})'[{output}]")
        previous = output
        windows.append({**window, "bounds": [x, y, right, bottom],
                        "path": path, "sha256": sha256_file(Path(path))})
    return inputs, filters, previous, windows


def add_table_pictures(scene, episode):
    """Use the same packed stimuli on the candidates' physical task sheets."""
    import bpy
    from build_scene import material
    if not episode.get("pictures"):
        return []
    for obj in scene.objects:
        if obj.name.startswith("Printed task line"):
            obj.hide_render = True
    result = []
    for key, picture in episode["pictures"].items():
        owner = picture["candidate"]
        sheet = scene.objects["Task sheet" + (".001" if owner == "candidate_b" else "")]
        image = bpy.data.images.load(picture["path"], check_existing=True)
        image.pack()
        ratio = image.size[0] / image.size[1]
        width = min(.33, .22 * ratio)
        height = width / ratio
        bpy.ops.mesh.primitive_plane_add(size=1, location=(sheet.location.x, sheet.location.y, .899))
        plane = bpy.context.object
        plane.name = "Picture sheet " + key
        plane.rotation_euler.z = sheet.rotation_euler.z + 3.141592653589793
        plane.scale = (width, height, 1)
        mat = material("Picture print " + key, (.9, .9, .9))
        texture = mat.node_tree.nodes.new("ShaderNodeTexImage")
        texture.image = image
        mat.node_tree.links.new(texture.outputs["Color"],
                                mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
        plane.data.materials.append(mat)
        digest = sha256_file(Path(picture["path"]))
        plane["picture_sha256"] = digest
        result.append({"picture": key, "candidate": owner, "object": plane.name,
                       "packed_image": image.name, "sha256": digest})
    return result
