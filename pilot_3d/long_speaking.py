"""Dual-format long speaking storyboard; native contact stills, never a movie."""

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from build_paths import build_directory
from generation_runtime import run_process
from prepare_audio import atomic_json, atomic_text, sha256_file
from runtime_config import font_path, tool_path

FORMATS = {
    "youtube": {
        "size": (1920, 1080), "safe": (48, 36, 1872, 1044),
        "scene": (64, 210, 1280, 790), "content": (64, 814, 1280, 1018),
        "promo": (1390, 302, 1840, 778), "cover": (1510, 365, 1720, 680),
        "cta": (1420, 705, 1810, 774),
    },
    "social": {
        "size": (1080, 1920), "safe": (60, 170, 920, 1660),
        "scene": (72, 370, 908, 875), "content": (72, 900, 908, 1220),
        "promo": (72, 1300, 908, 1550), "cover": (90, 1315, 235, 1535),
        "cta": (260, 1383, 875, 1486),
    },
}
BG, PANEL, INK, MUTED, ACCENT = "#101e27", "#20343f", "#f7f4e9", "#c4d2d7", "#e7bb67"
THUMBNAILS = {
    "youtube": {"scene": (0, 330, 1920, 1080), "logo": (1600, 35, 1850, 285),
                "title": (70, 100, 1510, 302), "subtitle": (70, 35, 1450, 95)},
    "social": {"scene": (40, 710, 1040, 1560), "logo": (710, 190, 900, 380),
               "title": (75, 430, 920, 680), "subtitle": (75, 225, 675, 365)},
}


def load_episode(path):
    from PIL import Image

    path = Path(path).resolve(strict=True)
    episode = json.loads(path.read_text(encoding="utf-8"))
    if (episode.get("schema_version") != 1 or episode.get("template") != "long_speaking"
            or episode.get("language") != "de"):
        raise ValueError("Expected the German long_speaking template.")
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", episode.get("id", "")):
        raise ValueError("Long-speaking id must be a safe identifier.")
    exam = episode.get("exam", {})
    if (exam.get("family") not in ("oeif", "dtz") or exam.get("skill") != "speaking"
            or exam.get("section") != "all"):
        raise ValueError("Long speaking requires an ÖIF or DTZ speaking episode with all three Teile.")
    level = exam.get("level", "B1")
    if level not in ("B1", "B2") or (level == "B2" and exam["family"] != "oeif"):
        raise ValueError("Supported long-speaking profiles are ÖIF/DTZ B1 and ÖIF B2.")
    for field in ("title", "branding", "disclaimer"):
        if not isinstance(episode.get(field), str) or not episode[field].strip():
            raise ValueError(f"Missing {field}.")
    if not episode["source"].get("duration_exception"):
        raise ValueError("Long-form duration must be explicitly requested.")
    for obj, field in ((episode["source"], "book"), (episode["source"], "manifest"),
                       (episode["scene"], "base_scene"), (episode["scene"], "wall_logo"),
                       (episode["promotion"], "cover"), (episode["promotion"], "pointing_emoji")):
        obj[field] = str((path.parent / obj[field]).resolve(strict=True))
    if "combined_edition" in episode["source"]:
        episode["source"]["combined_edition"] = str(
            (path.parent / episode["source"]["combined_edition"]).resolve(strict=True))
    if episode["opening"]["text"] != episode["title"]:
        raise ValueError("The opening must speak the complete displayed title.")
    if episode["opening"]["speaker"] not in episode["cast"]:
        raise ValueError("Opening speaker must belong to the cast.")
    if episode.get("subtitles", {}).get("highlight") != "word" or episode["subtitles"].get("timing") != "forced_alignment":
        raise ValueError("Long-speaking subtitles require measured word-level forced alignment.")
    if episode.get("thumbnail", {}).get("cast") != ["examiner", "candidate_a", "candidate_b", "observer"]:
        raise ValueError("The group thumbnail requires all four scene characters.")
    if episode["scene"].get("hair_pose") != "hanging_ponytail":
        raise ValueError("Long-speaking stills require the downward native ponytail pose.")
    promo = episode["promotion"]
    if not re.fullmatch(r"https://(?:www\.amazon\.[a-z.]+/dp/[A-Z0-9]{10}|amzn\.eu/d/[A-Za-z0-9]+)",
                        promo["amazon_url"]):
        raise ValueError("Provide the correct book's Amazon product link.")
    for mode in FORMATS:
        if "Amazon" not in promo[mode] or not promo[mode].strip():
            raise ValueError(f"Missing persistent Amazon CTA for {mode}.")
    if not promo.get("cta"):
        raise ValueError("The final CTA is required in addition to the persistent promotion.")
    if [part.get("number") for part in episode["parts"]] != [1, 2, 3]:
        raise ValueError("Expected Teil 1, Teil 2 and Teil 3, in order.")
    for part in episode["parts"]:
        if not part.get("task") or not part.get("instruction") or not part.get("tracks"):
            raise ValueError("Each Teil needs a task, instruction and source tracks.")
        if part.get("picture"):
            part["picture"] = str((path.parent / part["picture"]).resolve(strict=True))
    if not episode["parts"][2].get("result"):
        raise ValueError("Teil 3 needs the agreed result.")
    if level == "B1" and not episode["parts"][1].get("picture"):
        raise ValueError("Teil 2 needs its book picture.")
    if level == "B2" and episode["parts"][1].get("picture"):
        raise ValueError("B2 discussion uses a reading stimulus, not a B1 picture task.")
    pose = episode["scene"].get("contact_pose_frame")
    if type(pose) is not int or pose < 1:
        raise ValueError("A positive native contact-pose frame is required.")
    images = [promo["cover"], promo["pointing_emoji"], episode["scene"]["wall_logo"]]
    images += [part["picture"] for part in episode["parts"] if part.get("picture")]
    for image in images:
        with Image.open(image) as source:
            source.verify()
    compile_script(episode)
    return episode


def compile_script(episode):
    tracks = {}
    with Path(episode["source"]["manifest"]).open(encoding="utf-8") as source:
        for line in source:
            track = json.loads(line)
            if track["track_id"] in tracks:
                raise ValueError(f"Duplicate manifest track: {track['track_id']}")
            tracks[track["track_id"]] = track
    if episode.get("exam", {}).get("level") == "B2":
        from b2_speaking import compile_script as compile_b2
        return compile_b2(episode, tracks)
    turns = [{"id": "opening", **episode["opening"], "kind": "opening"}]
    for part in episode["parts"]:
        number = part["number"]
        turns.append({"id": f"teil{number}_instruction", "part": number, "speaker": "examiner",
                      "text": part["instruction"], "kind": "instruction"})
        for selection in part["tracks"]:
            track = tracks.get(selection["id"])
            if track is None or not track["section"].startswith(f"Teil {number}:"):
                raise ValueError(f"Missing or wrong-Teil source track: {selection['id']}")
            for segment in track["segments"]:
                role = selection["roles"].get(segment["speaker_label"])
                if role not in episode["cast"]:
                    raise ValueError(f"Unmapped speaker: {segment['speaker_label']}")
                turns.append({
                    "id": segment["segment_id"], "part": number, "speaker": role,
                    "text": segment["text_original"], "text_tts": segment["text_tts"],
                    "kind": "question" if role == "examiner" else "model",
                    "source_track": track["track_id"], "source_line": track["source_line"],
                    "source_voice_id": segment["voice_id"],
                    "adaptation": "Text unchanged; recast consistently as the scene's examiner, Lea and Samir.",
                })
        for index, followup in enumerate(part.get("follow_up", [])):
            if followup["speaker"] not in episode["cast"] or not followup["text"].strip():
                raise ValueError("Invalid authored follow-up.")
            turns.append({"id": f"teil{number}_followup_{index + 1}", "part": number,
                          **followup, "kind": "question" if followup["speaker"] == "examiner" else "model",
                          "adaptation": "Original linked follow-up for this video; not a book recording."})
    turns.append({"id": "final_cta", "speaker": "examiner", "kind": "cta",
                  "text": " ".join(episode["promotion"]["cta"])})
    return {"status": "storyboard_only", "timing": "Unmeasured; no audio or word timestamps generated.",
            "opening_alignment": episode["opening"]["alignment_policy"],
            "subtitle_alignment": episode["subtitles"],
            "turns": turns}


def panels(episode, script):
    if episode.get("exam", {}).get("level") == "B2":
        from b2_speaking import panels as b2_panels
        return b2_panels(episode, script)
    first, second, third = episode["parts"]
    turns = script["turns"]

    def model(part, index=0):
        return [t for t in turns if t.get("part") == part and t["kind"] == "model"][index]

    def sample(key, part, heading, body, camera="wide", picture=False):
        return {"id": key, "part": part, "heading": heading, "body": body,
                "camera": camera, "picture": picture}

    return [
        sample("01_opening", 0, episode["title"],
               [f"{part['number']} · {part['title']}" for part in episode["parts"]]),
        sample("02_teil1_task", 1, first["topic"], first["task"]),
        sample("03_teil1_model", 1, "Samir · Modellantwort",
               caption_excerpt(model(1)["text"]), "candidate_b"),
        sample("04_teil1_followup", 1, f"{episode['cast']['examiner']} · Nachfrage",
               first["follow_up"][0]["text"] if first.get("follow_up") else first["instruction"], "examiner"),
        sample("05_teil2_picture", 2, second["topic"], second["task"], "candidate_a", True),
        sample("06_teil2_model", 2, "Lea · Bildbeschreibung",
               caption_excerpt(model(2)["text"]), "candidate_a", True),
        sample("07_teil2_followup", 2, "Prüfer · Nachfrage",
               next(t["text"] for t in turns if t.get("part") == 2 and t["kind"] == "question"), "examiner"),
        sample("08_teil3_task", 3, third["topic"], third["task"], "candidates"),
        sample("09_teil3_lea", 3, "Lea · Vorschlag",
               caption_excerpt(model(3, 2)["text"]), "candidate_a"),
        sample("10_teil3_samir", 3, "Samir · Gegenvorschlag",
               caption_excerpt(model(3, 3)["text"]), "candidate_b"),
        sample("11_teil3_result", 3, "Unser gemeinsamer Plan", third["result"], "candidates"),
        sample("12_final_cta", 0, episode["promotion"]["cta"][0], episode["promotion"]["cta"][1:]),
    ]


def caption_excerpt(text, limit=145):
    sentences = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if sentences and len(" ".join([*sentences, sentence])) > limit:
            break
        sentences.append(sentence)
    return " ".join(sentences)


def wrapped(draw, text, font, width):
    result = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}".strip()
            if draw.textlength(candidate, font=font) > width:
                if not line:
                    raise ValueError(f"Unbreakable text does not fit: {word}")
                result.append(line)
                line = word
                if draw.textlength(line, font=font) > width:
                    raise ValueError(f"Unbreakable text does not fit: {word}")
            else:
                line = candidate
        result.append(line)
    return result


def text_box(draw, text, box, size=36, minimum=26, color=INK, bold=False, highlight_word=None):
    from PIL import ImageFont

    x0, y0, x1, y1 = box
    for points in range(size, min(size, minimum) - 1, -1):
        font = ImageFont.truetype(str(font_path(bold)), points)
        try:
            lines = wrapped(draw, text, font, x1 - x0)
        except ValueError:
            continue
        step = points * 1.28
        if len(lines) * step <= y1 - y0:
            cursor = 0
            for index, line in enumerate(lines):
                if highlight_word is None:
                    draw.text((x0, y0 + index * step), line, font=font, fill=color)
                else:
                    left = x0
                    for word in line.split():
                        draw.text((left, y0 + index * step), word, font=font,
                                  fill=ACCENT if cursor == highlight_word else color)
                        left += draw.textlength(word + " ", font=font)
                        cursor += 1
            result = {"box": list(box), "font_size": points, "lines": lines}
            if highlight_word is not None:
                result.update(highlighted_word=text.split()[highlight_word],
                              highlight_kind="illustrative_unmeasured")
            return result
    raise ValueError(f"Text overflows its reserved box: {text}")


def paste_contained(image, path, box):
    from PIL import Image, ImageOps

    x0, y0, x1, y1 = box
    with Image.open(path) as source:
        fitted = ImageOps.contain(source.convert("RGBA"), (x1 - x0, y1 - y0), Image.Resampling.LANCZOS)
    image.paste(fitted, (x0 + (x1 - x0 - fitted.width) // 2, y0 + (y1 - y0 - fitted.height) // 2), fitted)


def amazon_cta(image, draw, episode, mode, box, size):
    x0, y0, x1, y1 = box
    if mode != "youtube":
        return text_box(draw, episode["promotion"][mode], box,
                        size=size, minimum=26, color=ACCENT, bold=True)
    icon_size = size + 8
    result = text_box(draw, episode["promotion"][mode], (x0 + icon_size + 10, y0, x1, y1),
                      size=size, minimum=26, color=ACCENT, bold=True)
    icon_top = max(y0, int(y0 + (len(result["lines"]) * result["font_size"] * 1.28 - icon_size) / 2))
    icon = (x0, icon_top, x0 + icon_size, icon_top + icon_size)
    paste_contained(image, episode["promotion"]["pointing_emoji"], icon)
    result["emoji"] = {"glyph": "👇", "box": list(icon)}
    return result


def compose_thumbnail(episode, mode, native):
    from PIL import Image, ImageDraw

    layout = THUMBNAILS[mode]
    image = Image.new("RGB", FORMATS[mode]["size"], BG)
    draw = ImageDraw.Draw(image)
    box = layout["scene"]
    with Image.open(native) as source:
        if source.size != (box[2] - box[0], box[3] - box[1]):
            raise ValueError("Group thumbnail must use its uncropped native camera frame.")
        image.paste(source.convert("RGB"), box[:2])
    paste_contained(image, episode["scene"]["wall_logo"], layout["logo"])
    text = [
        text_box(draw, episode["thumbnail"]["subtitle"], layout["subtitle"], size=50, minimum=34, color=ACCENT, bold=True),
        text_box(draw, episode["thumbnail"]["title"], layout["title"],
                 size=105 if mode == "youtube" else 86, minimum=65, bold=True),
    ]
    flag = None
    if episode["exam"].get("level") == "B2":
        flag = (1460, 45, 1550, 105) if mode == "youtube" else (760, 385, 820, 425)
        x0, y0, x1, y1 = flag
        draw.rectangle(flag, fill="#ed2939")
        draw.rectangle((x0, y0 + round((y1 - y0) / 3), x1,
                        y0 + round(2 * (y1 - y0) / 3)), fill="#ffffff")
    return image, {"format": mode, "size": list(image.size), "scene_box": box,
                   "logo_box": layout["logo"], "cast": episode["thumbnail"]["cast"], "text": text,
                   **({"austrian_flag_box": flag} if flag else {})}


def compose(episode, panel, mode, native, *, sample_highlights=True, active_word=None):
    from PIL import Image, ImageDraw

    layout, promo = FORMATS[mode], episode["promotion"]
    image = Image.new("RGB", layout["size"], BG)
    draw = ImageDraw.Draw(image)
    portrait = mode == "social"
    exam_label = "ÖIF" if episode["exam"]["family"] == "oeif" else "DTZ"
    level = episode["exam"].get("level", "B1")
    texts = []

    def text(value, box, **options):
        result = text_box(draw, value, box, **options)
        if not sample_highlights and "highlighted_word" in result:
            result["highlight_kind"] = "forced_alignment"
        texts.append(result)

    if portrait:
        text(f"{episode['branding']} · {exam_label} {level}",
             (72, 175, 908, 222), size=31, bold=True, color=ACCENT)
        text(panel["heading"], (72, 238, 908, 348), size=43, minimum=32, bold=True,
             highlight_word=(2 if sample_highlights else active_word) if panel["id"] == "01_opening"
             else panel.get("heading_active_word"))
        navigation = (72, 1240, 908, 1275)
    else:
        text(f"{episode['branding']} · {exam_label} {level} SPRECHEN",
             (64, 40, 1856, 90), size=35, bold=True, color=ACCENT)
        text(panel["heading"], (64, 105, 1856, 183), size=49, minimum=36, bold=True,
             highlight_word=(2 if sample_highlights else active_word) if panel["id"] == "01_opening"
             else panel.get("heading_active_word"))
        navigation = (1410, 810, 1820, 855)
    if panel["id"] == "12_final_cta":
        cover = (310, 380, 690, 950) if portrait else (160, 280, 600, 940)
        message = (90, 1020, 900, 1280) if portrait else (700, 330, 1780, 610)
        amazon = (90, 1330, 900, 1510) if portrait else (700, 675, 1780, 850)
        paste_contained(image, promo["cover"], cover)
        text(" ".join(promo["cta"][1:]), message, size=45 if portrait else 59, minimum=36, bold=True)
        texts.append(amazon_cta(image, draw, episode, mode, amazon, 43 if portrait else 53))
        return image, {"id": panel["id"], "format": mode, "size": list(image.size),
                       "persistent_cover": cover, "persistent_cta": promo[mode], "cta_box": amazon,
                       "promo_group": False, "cover_count": 1, "text": texts}
    draw.rounded_rectangle(layout["promo"], radius=22, fill=PANEL)
    paste_contained(image, promo["cover"], layout["cover"])
    if portrait:
        text(promo["book_title"], (260, 1320, 875, 1372), size=33, bold=True)
        texts.append(amazon_cta(image, draw, episode, mode, layout["cta"], 36))
    else:
        text("Mehr üben mit dem Buch", (1420, 315, 1810, 358), size=27, color=MUTED)
        texts.append(amazon_cta(image, draw, episode, mode, layout["cta"], 28))
    text("   ·   ".join(f"{n}{' AKTIV' if panel['part'] == n else ''}" for n in (1, 2, 3)),
         navigation, size=25, color=ACCENT)

    scene_box = layout["scene"]
    draw.rounded_rectangle(scene_box, radius=18, fill=PANEL)
    source = Image.open(native) if isinstance(native, (str, Path)) else native.copy()
    with source:
        if source.size != (scene_box[2] - scene_box[0], scene_box[3] - scene_box[1]):
            raise ValueError("Native scene must match its panel: never stretch or crop the speakers.")
        image.paste(source.convert("RGB"), scene_box[:2])
    content = layout["content"]
    if panel["id"] == "05_teil2_picture":
        draw.rectangle(scene_box, fill=PANEL)
        paste_contained(image, episode["parts"][1]["picture"], scene_box)
    elif panel["picture"]:
        if portrait:
            picture_box, content = (72, 900, 450, 1195), (480, 905, 908, 1190)
        else:
            picture_box, content = (64, 812, 360, 1018), (390, 818, 1260, 1012)
        paste_contained(image, episode["parts"][1]["picture"], picture_box)
    if panel.get("card_text"):
        draw.rectangle(scene_box, fill=PANEL)
        x0, y0, x1, y1 = scene_box
        text(panel["card_text"], (x0 + 30, y0 + 25, x1 - 30, y1 - 25),
             size=34 if portrait else 40, minimum=30, highlight_word=panel.get("card_active_word"))
    body = panel["body"]
    if portrait and (not panel["picture"] or panel["id"] == "05_teil2_picture"):
        content = (90, 920, 890, 1220)
    if not portrait and isinstance(body, list) and len(body) > 4:
        middle = (len(body) + 1) // 2
        x0, y0, x1, y1 = content
        center = (x0 + x1) // 2
        text("\n".join(body[:middle]), (x0, y0, center - 16, y1), size=34, minimum=27)
        text("\n".join(body[middle:]), (center + 16, y0, x1, y1), size=34, minimum=27)
    else:
        speech = panel["id"] in ("03_teil1_model", "04_teil1_followup", "06_teil2_model",
                                 "07_teil2_followup", "09_teil3_lea", "10_teil3_samir")
        text("\n".join(body) if isinstance(body, list) else body, content,
             size=38 if portrait else 35, minimum=27, color=INK,
             highlight_word=(1 if speech else None) if sample_highlights else
             active_word if panel["id"] != "01_opening" else None)
    return image, {"id": panel["id"], "format": mode, "size": list(image.size),
                   "persistent_cover": layout["cover"], "persistent_cta": promo[mode], "cta_box": layout["cta"],
                   "promo_group": True, "cover_count": 1, "scene_box": scene_box, "text": texts}


def native_stills(request_path):
    from long_speaking_scene import render_contacts

    render_contacts(json.loads(Path(request_path).read_text(encoding="utf-8")), FORMATS, THUMBNAILS)


def build_contacts(episode_path, output):
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    episode = load_episode(episode_path)
    build = build_directory(output)
    if build.exists() and any(build.iterdir()):
        raise ValueError("Contact review needs a fresh dedicated build directory.")
    if build == Path(episode_path).resolve().parent or Path(episode_path).resolve().is_relative_to(build):
        raise ValueError("Output must be separate from the authored episode.")
    script = compile_script(episode)
    for mode, layout in FORMATS.items():
        box = layout["scene"]
        with Image.new("RGB", (box[2] - box[0], box[3] - box[1])) as probe:
            for panel in panels(episode, script):
                compose(episode, panel, mode, probe)
    build.mkdir(parents=True, exist_ok=True)
    (build / "native").mkdir()
    inputs = [Path(episode_path).resolve(), Path(__file__).resolve(),
              ROOT / "scene_direction.py", ROOT / "studio_characters.py", ROOT / "runtime_config.py",
              ROOT / "build_scene.py", ROOT / "long_speaking_scene.py", ROOT / "listening_scene.py",
              ROOT / "listener_motion.py", font_path(), font_path(True), Path(episode["source"]["book"]),
              Path(episode["source"]["manifest"]), Path(episode["scene"]["base_scene"]),
              Path(episode["scene"]["wall_logo"]), Path(episode["promotion"]["cover"]),
              Path(episode["promotion"]["pointing_emoji"])]
    inputs += [Path(part["picture"]) for part in episode["parts"] if part.get("picture")]
    if episode["source"].get("combined_edition"):
        inputs.append(Path(episode["source"]["combined_edition"]))
    if episode["exam"].get("level") == "B2":
        inputs.append(ROOT / "b2_speaking.py")
    hashes = {str(path): sha256_file(path) for path in inputs}
    atomic_json(build / "episode.json", episode)
    atomic_json(build / "script.json", script)
    if episode["exam"].get("level") == "B2":
        atomic_text(build / "full_script.txt", "\n\n".join(
            f"{turn['id']} | {episode['cast'][turn['speaker']]}\n{turn['text']}"
            for turn in script["turns"]) + "\n")
        atomic_text(build / "CREDITS.txt", "\n\n".join(episode["credits"]) + "\n")
    atomic_json(build / "native_request.json", {"episode": episode, "build": str(build)})
    with (build / "native.log").open("w", encoding="utf-8") as log:
        run_process([str(tool_path("blender")), "-b", episode["scene"]["base_scene"], "--disable-autoexec",
                     "-t", "4", "--python-exit-code", "1", "--python", str(Path(__file__).resolve()),
                     "--", "--native", str(build / "native_request.json")],
                    stdout=log, stderr=log, check=True)
    if episode["exam"].get("level") == "B2":
        receipts = json.loads((build / "native_checks.json").read_text(encoding="utf-8"))
        box = FORMATS["social"]["scene"]
        size = box[2] - box[0], box[3] - box[1]
        for receipt in list(receipts):
            source = Path(receipt["file"])
            target = source.with_name("social_" + source.name.removeprefix("youtube_"))
            with Image.open(source) as image:
                ratio = (size[0] / size[1]) / (image.width / image.height)
                cropped = ImageOps.fit(image.convert("RGB"), size, Image.Resampling.LANCZOS, centering=(.5, .5))
            cropped.save(target)
            margin = (1 - ratio) / 2
            heads = [{**head, "bounds": [(head["bounds"][0] - margin) / ratio, head["bounds"][1],
                                         (head["bounds"][2] - margin) / ratio, head["bounds"][3]]}
                     for head in receipt["head_bounds"]]
            receipts.append({**receipt, "format": "social", "file": str(target), "size": list(size),
                             "head_bounds": heads, "sha256": sha256_file(target),
                             "source_file": str(source), "source_sha256": sha256_file(source),
                             "transform": "fixed_center_crop"})
        atomic_json(build / "native_checks.json", receipts)
    checks, thumbnail_checks = [], []
    for mode in FORMATS:
        folder = build / mode
        folder.mkdir()
        thumbnails = []
        for panel in panels(episode, script):
            image, check = compose(episode, panel, mode, build / "native" / f"{mode}_{panel['camera']}.png")
            output_path = folder / f"{panel['id']}.png"
            image.save(output_path)
            check["sha256"] = sha256_file(output_path)
            checks.append(check)
            thumb = image.copy()
            thumb.thumbnail((640, 360) if mode == "youtube" else (270, 480), Image.Resampling.LANCZOS)
            thumbnails.append((panel["id"], thumb))
        width, height = (640, 360) if mode == "youtube" else (270, 480)
        columns = 3 if mode == "youtube" else 4
        rows = (len(thumbnails) + columns - 1) // columns
        sheet = Image.new("RGB", (columns * width, rows * (height + 30)), "#080e13")
        draw = ImageDraw.Draw(sheet)
        for index, (label, thumb) in enumerate(thumbnails):
            x, y = index % columns * width, index // columns * (height + 30)
            sheet.paste(thumb, (x, y))
            draw.text((x + 8, y + height + 4), label, font=ImageFont.truetype(str(font_path()), 18), fill=INK)
        sheet.save(build / f"contact_sheet_{mode}.jpg", quality=94)
        thumbnail, check = compose_thumbnail(episode, mode, build / "native" / f"{mode}_group.png")
        thumbnail_path = build / f"thumbnail_{mode}.png"
        thumbnail.save(thumbnail_path)
        thumbnail_checks.append({**check, "sha256": sha256_file(thumbnail_path)})
    if any(sha256_file(Path(path)) != digest for path, digest in hashes.items()):
        raise ValueError("A source or implementation changed during contact generation.")
    atomic_json(build / "review_checks.json", {
        "status": "contact_sheets_only", "audio_generated": False, "video_generated": False,
        "timing_verified": False, "native_pose": "Existing seated pose; not animation of the new dialogue.",
        "source_sha256": hashes, "panels": checks, "thumbnails": thumbnail_checks,
        "subtitle_highlights": "Illustrative word-level style samples only; real timestamps still require forced alignment.",
        "next_gate": "Visual approval, then real TTS, forced alignment and motion/encoded checks before delivery.",
    })
    print(f"Contact sheets: {build}", flush=True)
    return build


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    args = parser.parse_args(argv)
    native_stills(args.native)
