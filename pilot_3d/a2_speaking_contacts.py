"""Still-only A2 transcript/layout review; no speech or animated video."""

import argparse
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def read_turns(path):
    text = path.read_text(encoding="utf-8")
    parsed = re.findall(r"\*\*(\d{2}) · ([^\n]+)\*\*\n\n([^\n]+)", text)
    if [int(number) for number, _, _ in parsed] != list(range(1, 56)):
        raise ValueError("Expected the complete approved 55-turn A2 review transcript.")
    turns = {int(number): {"label": label, "text": speech.strip()}
             for number, label, speech in parsed}
    if (turns[9]["text"] != "Ich komme aus Warschau in Polen."
            or turns[13]["text"] != "Zu Hause spreche ich meistens Polnisch."):
        raise ValueError("Lea's approved Polish background is missing.")
    return turns


def review_panels(turns):
    def panel(key, part, heading, body, camera="wide", *, card=None, picture=False,
              source_turn=None):
        return {"id": key, "part": part, "heading": heading, "body": body,
                "camera": camera, "picture": picture,
                **({"card_text": card} if card else {}),
                **({"source_turn": source_turn} if source_turn else {})}

    return [
        panel("01_opening", 0, "ÖIF A2 Sprechen mit Lea",
              ["S1 · Kontaktgespräch", "S2A · Bildsituation und Rollenspiel",
               "S2B · Eigene Erfahrungen"], source_turn=1),
        panel("introduction", 0, "Lea und die beiden Prüfenden",
              ["Herr Wagner führt das Gespräch.", "Frau Berger hört zu.",
               "Lea ist die einzige Kandidatin."], source_turn=2),
        panel("contact_card", 1, "S1 · Kontaktgespräch", "Erzählen und Fragen stellen.",
              card="Name · Heimat\nWohnort · Sprachen\n\nFragen an den Prüfer:\nWohnort · Sprachen",
              source_turn=6),
        panel("contact_model", 1, "Lea · Vorstellung", turns[7]["text"], "candidate_a",
              source_turn=7),
        panel("contact_origin", 1, "Lea · Herkunft",
              turns[9]["text"] + "\n" + turns[13]["text"], "candidate_a", source_turn=9),
        panel("contact_candidate_question", 1, "Lea · Frage an den Prüfer",
              turns[19]["text"], "candidate_a", source_turn=19),
        panel("contact_examiner_answer", 1, "Prüfer · Antwort",
              turns[20]["text"], "examiner", source_turn=20),
        panel("picture_choice", 2, "S2A · Wählen Sie ein Bild",
              "Welches Bild möchten Sie auswählen?", source_turn=24),
        panel("05_teil2_picture", 2, "Lea · Bild 3",
              "Auf dem Bild sehe ich ein Wartezimmer in einer Arztpraxis.",
              source_turn=27),
        panel("picture_description", 2, "Lea · Bildsituation",
              "Mehrere Personen sitzen auf Stühlen und warten. Vielleicht ist eine Person krank.",
              "candidate_a", picture=True, source_turn=27),
        panel("role_card", 2, "S2A · Einen Arzttermin vereinbaren",
              "Stellen Sie mindestens zwei Fragen.",
              card="Lea: Patientin am Telefon\nPrüfer: Mitarbeiter der Arztpraxis\n\nWann …?\nMuss ich …?",
              source_turn=28),
        panel("role_question_01", 2, "Lea · Frage nach dem Termin",
              turns[33]["text"], "candidate_a", picture=True, source_turn=33),
        panel("role_answer", 2, "Prüfer · Praxismitarbeiter",
              turns[34]["text"], "examiner", picture=True, source_turn=34),
        panel("role_question_02", 2, "Lea · Frage zur E-Card",
              turns[36]["text"], "candidate_a", picture=True, source_turn=36),
        panel("personal_card", 3, "S2B · Wie ist das bei Ihnen?",
              "Dasselbe Bildthema, persönliche Erfahrungen.",
              card="Termin vereinbaren\nWas nehme ich mit?\nIm Wartezimmer\nTermin absagen",
              source_turn=40),
        panel("personal_model", 3, "Lea · Eigene Erfahrungen",
              "Wenn ich krank bin, rufe ich meistens zuerst in der Praxis an und mache einen Termin.",
              "candidate_a", picture=True, source_turn=41),
        panel("personal_followup", 3, "Lea · Termine am Telefon",
              turns[43]["text"], "candidate_a", picture=True, source_turn=43),
        panel("closing", 3, "Vielen Dank, Lea.", turns[52]["text"], source_turn=52),
        panel("12_final_cta", 0, "Jetzt selbst sprechen!",
              ["Mehr Aufgaben und Modelldialoge", "im ÖIF-A2-Buch Sprechen + Schreiben."],
              source_turn=55),
    ]


def visible_head_bounds(scene, camera, actors):
    import bpy
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Vector

    heads = []
    for actor in actors:
        meshes = [obj for obj in actor.root.children_recursive
                  if obj.type == "MESH" and not obj.hide_render
                  and obj.visible_camera and "_helper" not in obj.name.lower()
                  and obj.name.startswith("GEO-")
                  and any(token in obj.name.lower() for token in ("head", "hair"))]
        if not meshes:
            raise ValueError(f"{actor.name}: missing visible head/hair geometry.")
        points = []
        for mesh in meshes:
            evaluated = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
            points.extend(evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box)
        projected = [world_to_camera_view(scene, camera, point) for point in points]
        heads.append({
            "actor": actor.name,
            "bounds": [min(p.x for p in projected), min(p.y for p in projected),
                       max(p.x for p in projected), max(p.y for p in projected)],
            "in_front": all(p.z > 0 for p in projected),
            "head_and_hair_meshes": [obj.name for obj in meshes],
        })
    return heads


def render_contact_still(scene, camera, actors, output):
    import bpy
    from b2_speaking import shared_head_fits
    from prepare_audio import sha256_file

    scene.camera = camera
    scene.render.resolution_x, scene.render.resolution_y = 1216, 580
    bpy.context.view_layer.update()
    for _ in range(50):
        heads = visible_head_bounds(scene, camera, actors)
        if all(shared_head_fits(head) for head in heads):
            break
        camera.data.lens *= .95
    else:
        raise ValueError(f"Cannot frame the speakers in {output.name}.")
    scene.render.filepath = str(output)
    bpy.ops.render.render(write_still=True)
    if scene.camera != camera:
        raise ValueError("The source scene overrode the requested contact camera.")
    return {"head_bounds": heads, "file": str(output), "sha256": sha256_file(output),
            "size": [1216, 580], "lens": camera.data.lens,
            "bounds_scope": "Visible rendered head/hair meshes; hidden rig helpers excluded."}


def setup_scene(visual):
    import math
    import bpy
    from mathutils import Vector
    from listening_scene import freeze_source_animation
    from long_speaking_scene import correct_hair
    from scene_direction import configure_cast, room_design
    from studio_characters import StudioCharacter

    scene = bpy.context.scene
    scene.frame_set(600)
    freeze_source_animation(scene)
    scene.timeline_markers.clear()
    actors = {role: StudioCharacter.from_scene(role)
              for role in ("candidate_a", "examiner", "observer")}
    hair = []
    for actor in actors.values():
        actor.restore_native_drivers()
        check = correct_hair(actor)
        if check:
            hair.append(check)
    room_design(scene, visual)
    cast = configure_cast(scene, visual)
    actor = actors["examiner"]
    old = actor.root.matrix_world.copy()
    actor.root.location = (-.82, -1.6, 0)
    actor.root.rotation_euler.z = math.pi
    bpy.context.view_layer.update()
    transform = actor.root.matrix_world @ old.inverted()
    scene.objects["Chair.001"].matrix_world = transform @ scene.objects["Chair.001"].matrix_world
    # Keep the seated body pose, but replace the original pair-exam gaze.
    for actor in actors.values():
        actor.bones[actor.jaw_name].rotation_euler.x = 0
    for role, angle in (("candidate_a", 0), ("examiner", 0), ("observer", .2)):
        actor = actors[role]
        actor.head.rotation_mode = "XYZ"
        actor.head.rotation_euler = (0, angle, 0)
        eyes = actor.bones["TGT-Eyes"]
        matrix = eyes.matrix.copy()
        matrix.translation = Vector((angle * 4, -2.5, actor.head.head.z + .05))
        eyes.matrix = matrix
    bpy.context.view_layer.update()
    directions = [actors[role].root.rotation_euler.z for role in ("candidate_a", "examiner")]
    if (abs(math.cos(directions[0] - directions[1]) + 1) > .01
            or abs(actors["candidate_a"].root.location.x
                   - actors["examiner"].root.location.x) > .01
            or actors["examiner"].root.location.y >= actors["candidate_a"].root.location.y):
        raise ValueError("The active examiner must face Lea from the opposite side of the table.")
    if any(not obj.hide_render for obj in scene.objects["candidate_b"].children_recursive
           if obj.type == "MESH"):
        raise ValueError("Samir must be absent.")
    cameras = {}
    settings = {
        "wide": ((3.3, -.45, 2.65), (-.1, -.45, 1.0), 28),
        "candidate_a": ((-.1, -1.35, 1.65), (-.82, .65, 1.17), 47),
    }
    head = actors["examiner"].rig.matrix_world @ actors["examiner"].head.head
    target = head - Vector((0, 0, .15))
    settings["examiner"] = (target + Vector((.5, 2.05, .35)), target, 45)
    for name, (location, target, lens) in settings.items():
        data = bpy.data.cameras.new(f"A2 still {name}")
        camera = bpy.data.objects.new(f"A2 still {name}", data)
        scene.collection.objects.link(camera)
        camera.location = location
        camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
        camera.data.lens = lens
        cameras[name] = camera
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 8
    scene.cycles.use_denoising = True
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.use_sequencer = False
    scene.render.use_persistent_data = True
    return actors, cameras, cast, hair


def native(request):
    import bpy
    from prepare_audio import atomic_json

    actors, cameras, cast, hair = setup_scene(request["visual"])
    scene = bpy.context.scene
    receipts = []
    build = Path(request["build"])
    for name, camera in cameras.items():
        visible = list(actors.values()) if name == "wide" else [actors[name]]
        receipt = render_contact_still(scene, camera, visible,
                                       build / "native" / f"youtube_{name}.png")
        receipts.append({"camera": name, **receipt})
    atomic_json(build / "native_checks.json", {
        "images": receipts, "cast": cast, "hair": hair,
        "candidate_examiner_angle_degrees": 180,
        "examiner_seating": "Opposite Lea across the table, as requested.",
        "source_scene_saved": False, "speech_generated": False,
    })


def compose_panel(visual, panel, mode, source, picture_paths, *, active_word=None):
    from PIL import Image, ImageDraw, ImageOps
    from long_speaking import ACCENT, BG, FORMATS, PANEL, compose, paste_contained, text_box

    image, check = compose(visual, panel, mode, source, sample_highlights=False,
                           active_word=active_word)
    if panel["id"] == "12_final_cta":
        return image, check
    navigation = (1410, 810, 1820, 855) if mode == "youtube" else (72, 1240, 908, 1275)
    draw = ImageDraw.Draw(image)
    draw.rectangle(navigation, fill=BG)
    labels = ["S1", "S2A", "S2B"]
    if panel["part"]:
        labels[panel["part"] - 1] += " AKTIV"
    check["text"] = [text for text in check["text"] if tuple(text["box"]) != navigation]
    check["text"].append(text_box(draw, " · ".join(labels), navigation,
                                 size=25, color=ACCENT, bold=True))
    if panel["id"] == "picture_choice":
        box = (72, 330, 908, 1180) if mode == "social" else FORMATS[mode]["scene"]
        if mode == "social":
            draw.rectangle((72, 330, 908, 1232), fill=BG)
            check["text"] = [text for text in check["text"]
                             if text["box"][1] < 330 or text["box"][1] >= 1232]
        draw.rectangle(box, fill=PANEL)
        gap = 12
        width = (box[2] - box[0] - gap * 4) // 3
        height = (box[3] - box[1] - gap * 4) // 3
        picture_checks = []
        for index, picture in enumerate(picture_paths):
            if mode == "social":
                top = box[1] + gap + index * (height + gap)
                destination = (box[0] + gap, top, box[2] - gap, top + height)
            else:
                left = box[0] + gap + index * (width + gap)
                destination = (left, box[1] + 58, left + width, box[3] - 20)
            paste_contained(image, picture, destination)
            with Image.open(picture) as original:
                fitted = ImageOps.contain(original, (destination[2] - destination[0],
                                                    destination[3] - destination[1]))
                x = destination[0] + (destination[2] - destination[0] - fitted.width) // 2
                y = destination[1] + (destination[3] - destination[1] - fitted.height) // 2
                picture_checks.append({"file": str(picture), "box": [x, y, x + fitted.width,
                                                                    y + fitted.height]})
            if mode != "social":
                check["text"].append(text_box(draw, str(index + 1),
                                             (left, box[1] + 12, left + width, box[1] + 50),
                                             size=30, color=ACCENT, bold=True))
        if mode == "social":
            check["text"].append(text_box(draw, panel["body"], (90, 1184, 900, 1232),
                                         size=28, highlight_word=active_word))
        check["picture_choice_labels"] = [] if mode == "social" else ["1", "2", "3"]
        check["picture_choice_board"] = list(box)
        check["picture_choice_images"] = picture_checks
        check["picture_choice_layout"] = "vertical" if mode == "social" else "horizontal"
        check["picture_choice_topics_revealed"] = False
    check["a2_navigation"] = labels
    check["source_turn"] = panel["source_turn"]
    return image, check


def build_contacts(output):
    from PIL import Image, ImageOps
    from generation_runtime import run_process
    from long_speaking import FORMATS, PANEL
    from prepare_audio import atomic_json, sha256_file
    from runtime_config import font_path, tool_path

    output = output.resolve()
    if output.exists():
        raise ValueError("Use a fresh A2 contact-sheet build.")
    transcript = ROOT.parent / "plan" / "oeif_a2_speaking_transcript_review.md"
    book = ROOT.parent.parent / "german" / "books" / "a2" / "speaking_oeif_gpt_v1"
    turns = read_turns(transcript)
    pictures = [book / "images" / f"{index:02d}.jpg" for index in (1, 2, 3)]
    visual = {
        "exam": {"family": "oeif", "level": "A2"}, "branding": "DEUTSCHKOMPASS",
        "scene": {"base_scene": str(ROOT / "builds" / "v2" / "studio.blend"),
                  "wall_logo": str(ROOT / "assets" / "deutschkompass-logo.png"),
                  "layout": "interview", "observer": True, "entrance": False},
        "parts": [{}, {"picture": str(pictures[2])}, {}],
        "promotion": {
            "cover": str(book.parent / "combined_oeif_gpt_v1" / "oeif_a2_combined.jpg"),
            "book_title": "ÖIF A2 Sprechen + Schreiben",
            "amazon_url": "https://amzn.eu/d/0eC3q7T3",
            "youtube": "Amazon: Link in der Beschreibung", "social": "Amazon: Link in der Bio",
            "pointing_emoji": str(ROOT / "assets" / "emoji" / "point-down.png"),
            "cta": ["Jetzt selbst sprechen!", "Mehr Aufgaben und Modelldialoge",
                    "im ÖIF-A2-Buch Sprechen + Schreiben."],
        },
    }
    dependencies = [Path(__file__), transcript, book / "book_no_toc.md",
                    book / "audio" / "manifest.jsonl", *pictures,
                    Path(visual["promotion"]["cover"]), Path(visual["scene"]["base_scene"]),
                    Path(visual["scene"]["wall_logo"]), Path(visual["promotion"]["pointing_emoji"]),
                    font_path(), font_path(True)]
    dependencies += [ROOT / name for name in (
        "long_speaking.py", "long_speaking_scene.py", "b2_speaking.py",
        "scene_direction.py", "studio_characters.py", "listening_scene.py")]
    protected = {str(path): sha256_file(path) for path in dependencies}
    output.mkdir()
    (output / "native").mkdir()
    (output / "panels").mkdir()
    request = {"build": str(output), "visual": visual, "speech_tempo": .8,
               "transcript": str(transcript), "turns": turns, "panels": review_panels(turns)}
    atomic_json(output / "request.json", request)
    shutil.copy2(transcript, output / "transcript_review.md")
    # This is a new still-only path, not a changed frozen B1/B2 pipeline.
    command = [str(tool_path("blender")), "-b", visual["scene"]["base_scene"],
               "--disable-autoexec", "-t", "4", "--python-exit-code", "1",
               "--python", str(Path(__file__)), "--", "--native", str(output / "request.json")]
    with (output / "native.log").open("w", encoding="utf-8") as log:
        run_process(command, stdout=log, stderr=log, check=True)
    native_report = json.loads((output / "native_checks.json").read_text(encoding="utf-8"))
    checks = []
    crop_receipts = []
    for mode in ("youtube", "social"):
        columns = 4 if mode == "youtube" else 3
        thumb = (480, 270) if mode == "youtube" else (270, 480)
        sheet = Image.new("RGB", (columns * thumb[0],
                                 ((len(request["panels"]) + columns - 1) // columns) * thumb[1]), PANEL)
        for index, panel in enumerate(request["panels"]):
            box = FORMATS[mode]["scene"]
            with Image.open(output / "native" / f"youtube_{panel['camera']}.png") as raw:
                raw = raw.convert("RGB")
                size = (box[2] - box[0], box[3] - box[1])
                source = (raw if mode == "youtube" else
                          ImageOps.fit(raw, size, Image.Resampling.LANCZOS, centering=(.5, .5)))
                if mode == "social":
                    crop_receipts.append({"panel": panel["id"], "camera": panel["camera"],
                                          "source_size": list(raw.size), "target_size": list(size),
                                          "transform": "fixed center crop of shared YouTube still"})
                image, check = compose_panel(visual, panel, mode, source, pictures)
            path = output / "panels" / f"{mode}_{panel['id']}.png"
            image.save(path)
            check.update(file=str(path), sha256=sha256_file(path),
                         highlight_timing="Not generated; no simulated alignment.")
            checks.append(check)
            sheet.paste(image.resize(thumb), (index % columns * thumb[0], index // columns * thumb[1]))
        sheet.save(output / f"contact_sheet_{mode}.jpg", quality=95)
    for path, digest in protected.items():
        if sha256_file(Path(path)) != digest:
            raise ValueError(f"A contact source changed: {path}")
    for receipt in native_report["images"]:
        if sha256_file(Path(receipt["file"])) != receipt["sha256"]:
            raise ValueError("Native still differs from its render receipt.")
    atomic_json(output / "review_checks.json", {
        "status": "contact_sheets_only", "panels": checks, "shared_crop": crop_receipts,
        "source_sha256": protected, "native_checks": native_report,
        "cast": ["Lea", "Herr Wagner", "Frau Berger"], "speech_tempo": .8,
        "tts_generated": False, "video_generated": False,
        "selected_book_cover": "User-selected combined A2 Sprechen + Schreiben cover.",
        "amazon_product_title_verified": False,
    })
    (output / "CREDITS.txt").write_text(
        "Snow Rig and Rain Rig: Blender Foundation, CC BY 4.0.\n"
        "https://studio.blender.org/characters/snow/v4/\n"
        "https://studio.blender.org/characters/rain/v3/\n"
        "https://creativecommons.org/licenses/by/4.0/\n"
        "Modified outfits, scale, poses, visibility and seat placement.\n"
        "Images and cover: requested ÖIF A2 speaking GPT-v1 book.\n"
        "Pointing emoji: Twemoji, Twitter and contributors, CC BY 4.0; scaled.\n",
        encoding="utf-8")
    shutil.copy2(Path(__file__), output / "contact_source.py")
    atomic_json(output / "export_manifest.json", {
        str(path.relative_to(output)): sha256_file(path)
        for path in output.rglob("*") if path.is_file() and path.suffix != ".log"
    })
    print(f"A2 contact sheets ready: {output}", flush=True)
    print(f"{len(checks)} panels, three shared native stills; no audio or video.", flush=True)


if __name__ == "__main__":
    if "--" in sys.argv:
        sys.argv = [sys.argv[0], *sys.argv[sys.argv.index("--") + 1:]]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path)
    parser.add_argument("--native", type=Path)
    args = parser.parse_args()
    if args.native:
        native(json.loads(args.native.read_text(encoding="utf-8")))
    elif args.build:
        from generation_runtime import generation_job
        generation_job(build_contacts)(args.build)
    else:
        parser.error("Choose --build for contact sheets.")
