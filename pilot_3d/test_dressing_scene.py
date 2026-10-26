"""Blender prop/entrance fixture with silent synthetic timings, not an episode."""

import json
from pathlib import Path
import sys
import wave

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def prepare_fixture(build):
    from episode_config import read_episode, validate_template
    from prepare_audio import atomic_json, build_timeline
    from scene_dressing import ASSETS
    from social_captions import make_ass

    if not build.is_relative_to(ROOT / "builds") or build == ROOT / "builds":
        raise ValueError("Use a new dressing fixture directory under builds.")
    if build.exists() and any(build.iterdir()):
        raise ValueError("Use an empty fixture directory.")
    build.mkdir(parents=True, exist_ok=True)
    episode = read_episode(ROOT / "episodes/lerntreffen_dtz.json")
    episode.update(id="synthetic_austrian_props_fixture", title="Stumme Requisitenprobe",
                   hook="Requisitenprobe: ohne Ton", outro_seconds=0, task_card=[], cta=[])
    episode["header"] = {"brand": "DEUTSCHKOMPASS", "topic": "Stumme Requisitenprobe"}
    episode["scene"]["dressing"] = json.loads((ASSETS / "austria.json").read_text(encoding="utf-8"))
    episode["turns"] = [episode["turns"][i] for i in (0, 1, 3, 2)]
    texts = ("Guten Tag. Nehmen Sie bitte Platz.", "Heute sprechen wir über einen Feiertag.",
             "Heute bleibe ich lieber neutral.", "Wir brauchen trotzdem ein gutes Argument.")
    audio, cues = [], []
    for index, (turn, text) in enumerate(zip(episode["turns"], texts)):
        turn.update(text=text, pause_after=3.0 if index == 0 else 9.2 if index == 1 else 1.2)
        turn.pop("task_card_delay_seconds", None)
        path = build / f"synthetic_{index}.wav"
        duration = 2.5
        with wave.open(str(path), "wb") as output:
            output.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
            output.writeframes(bytes(round(duration * 48000) * 2))
        audio.append({"audio": str(path), "frames": round(duration * 48000), "sample_rate": 48000})
        cues.append([{"start": 0, "end": duration, "value": "X"}])
    validate_template(episode, check_assets=True)
    timeline = build_timeline(episode, audio, cues)
    for turn in timeline["turns"]:
        words = turn["text"].split()
        step = turn["wav_duration"] / len(words)
        turn["words"] = [{"word": word, "start": index * step,
                          "end": (index + 1) * step, "score": 1}
                         for index, word in enumerate(words)]
    timeline["word_alignment"] = {"synthetic_fixture": True, "language": "de",
                                  "notice": "Uniform artificial words over silence; no speech or alignment claim."}
    with wave.open(str(build / "dialogue.wav"), "wb") as output:
        output.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        output.writeframes(bytes(timeline["total_frames"] * 2000 * 2))
    atomic_json(build / "episode.json", episode)
    atomic_json(build / "timeline.json", timeline)
    (build / "preflight").mkdir()
    ass = make_ass(episode, timeline)
    (build / "preflight/captions.ass").write_text(ass, encoding="utf-8")
    (build / "captions.ass").write_text(ass, encoding="utf-8")


def main():
    import bpy
    from mathutils import Vector
    import subprocess
    from check_v4_scene import check
    from prepare_audio import atomic_json
    from produce_v4 import camera_at_frame, scene_build
    from runtime_config import qwen_python
    from scene_dressing import projected_bounds, world_corners
    import scene_dressing

    build = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
    subprocess.run([str(qwen_python()), str(Path(__file__).resolve()), "--prepare", str(build)],
                   cwd=ROOT, check=True)
    episode = json.loads((build / "episode.json").read_text(encoding="utf-8"))
    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    if "--tilted-fit" in sys.argv:
        original_dressing = scene_dressing.apply_dressing

        def tilted_dressing(scene, episode, actors, fit_frame, timeline):
            scene.frame_set(fit_frame)
            head = actors["candidate_b"].head
            head.rotation_euler.x += .22
            head.rotation_euler.y += .10
            head.keyframe_insert(data_path="rotation_euler", frame=fit_frame)
            bpy.context.view_layer.update()
            return original_dressing(scene, episode, actors, fit_frame, timeline)

        scene_dressing.apply_dressing = tilted_dressing
    scene_build(build, profile="preview")
    bpy.ops.wm.open_mainfile(filepath=str(build / "studio.blend"))
    check(build)
    atomic_json(build / "fixture.json", {
        "silent_synthetic_fixture": True, "tilted_fit_regression": "--tilted-fit" in sys.argv,
    })
    if "--render" not in sys.argv:
        return
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = 720, 1280
    scene.cycles.samples = 16
    scene.render.image_settings.file_format = "PNG"
    scene.render.threads_mode, scene.render.threads = "FIXED", 4
    cameras = {key: next(obj for obj in scene.objects if obj.type == "CAMERA" and obj.name.startswith(prefix))
               for key, prefix in (("wide", "01"), ("candidate_b", "05"), ("examiner", "02"))}
    views = [
        ("entrance", 3.2, cameras["wide"]),
        ("room", 10.8, cameras["wide"]),
        ("hat", timeline["turns"][2]["start"] + 1.0, cameras["candidate_b"]),
        ("examiner", timeline["turns"][1]["start"] + 1.0, cameras["examiner"]),
    ]
    for name, position, target, lens in (
        ("coffee", (-.80, -.15, 1.55), (-.79, -.80, .93), 48),
        ("backpack", (2.75, -1.9, 1.05), (1.70, -.27, .27), 52),
    ):
        data = bpy.data.cameras.new("Review " + name)
        camera = bpy.data.objects.new("Review " + name, data)
        scene.collection.objects.link(camera)
        camera.location = position
        camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
        camera.data.lens = lens
        views.append((name, 10.8, camera))
    markers = [{"frame": marker.frame, "camera": marker.camera.name}
               for marker in scene.timeline_markers if marker.camera]
    scene.timeline_markers.clear()
    records = []
    folder = build / "review"
    folder.mkdir()
    for name, seconds, camera in views:
        frame = 1 + round(seconds * timeline["fps"])
        scene.frame_set(frame)
        scene.camera = camera
        scene.render.filepath = str(folder / f"{name}.png")
        bpy.ops.render.render(write_still=True)
        active_camera = camera_at_frame(markers, frame)
        record = {"name": name, "frame": frame, "seconds": (frame - 1) / timeline["fps"],
                        "camera": camera.name, "file": f"review/{name}.png",
                        "detail_only": name in ("coffee", "backpack"),
                        "active_episode_camera": active_camera,
                        "actual_episode_shot": camera.name == active_camera}
        if name == "entrance":
            bag = next(obj for obj in scene.objects if obj.name.startswith("Dressing ")
                       and obj.name.endswith(" backpack"))
            bounds = projected_bounds(scene, camera, world_corners(list(bag.children)))
            if not (record["actual_episode_shot"] and 0 <= bounds[0] < bounds[2] <= 720
                    and 840 <= bounds[1] < bounds[3] <= 1280):
                raise ValueError(f"Backpack is not clear in the actual opening wide shot: {bounds}")
            record["backpack_bounds_px"] = bounds
        records.append(record)
    atomic_json(build / "dressing_review.json", {
        "synthetic_silent_fixture": True, "width": 720, "height": 1280, "samples": 16,
        "notice": "Prop review only. Detail cameras are not episode shots. No TTS, movie or production delivery.",
        "views": records,
    })
    subprocess.run([str(qwen_python()), str(Path(__file__).resolve()), "--review", str(build)],
                   cwd=ROOT, check=True)
    print("PASS: saved-scene dressing checks and six actual Blender review stills; no voiced video.")


def review_stills(build):
    import hashlib
    import subprocess
    from PIL import Image, ImageChops, ImageDraw, ImageStat
    from prepare_audio import atomic_json
    from runtime_config import caption_fonts

    report = json.loads((build / "dressing_review.json").read_text(encoding="utf-8"))
    caption_fonts(build)
    sheet = Image.new("RGB", (1080, 1344), "#17212a")
    draw = ImageDraw.Draw(sheet)
    checks = []
    for index, view in enumerate(report["views"]):
        source = build / view["file"]
        with Image.open(source) as image:
            image.load()
            if image.size != (720, 1280) or max(ImageStat.Stat(image.convert("RGB")).stddev) < 8:
                raise ValueError(f"Invalid or blank review still: {source}")
        captioned = source.with_name(source.stem + "_captioned.png")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(source.relative_to(build)),
                        "-vf", f"setpts=PTS+{view['seconds']}/TB,ass=captions.ass:fontsdir=caption_fonts",
                        "-frames:v", "1", "-fps_mode", "passthrough", "-update", "1",
                        str(captioned.relative_to(build))], cwd=build, check=True)
        with Image.open(source) as raw, Image.open(captioned) as image:
            changed = sum(value > 0 for value in ImageChops.difference(
                raw.convert("RGB"), image.convert("RGB")).convert("L").getdata())
            if changed < 1000:
                raise ValueError("Review frame is missing the actual caption overlay.")
            sheet.paste(image.convert("RGB").resize((360, 640)), (index % 3 * 360, index // 3 * 672 + 32))
            if "backpack_bounds_px" in view:
                annotated = image.convert("RGB")
                drawing = ImageDraw.Draw(annotated)
                left, top, right, bottom = view["backpack_bounds_px"]
                drawing.rectangle((left - 8, top - 8, right + 8, bottom + 8), outline="#ffcd35", width=4)
                drawing.text((left - 8, top - 26), "Backpack: opening wide shot", fill="#ffcd35")
                annotated.save(build / "review/backpack_in_entrance.png")
        label = view["name"] + (" (detail only)" if view["detail_only"] else
                               " (actual episode shot)" if view["actual_episode_shot"] else " (wide-camera review)")
        draw.text((index % 3 * 360 + 10, index // 3 * 672 + 9), label, fill="white")
        checks.append({"file": view["file"], "captioned": str(captioned.relative_to(build)),
                       "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                       "captioned_sha256": hashlib.sha256(captioned.read_bytes()).hexdigest(),
                       "caption_changed_pixels": changed, "dimensions": [720, 1280]})
    sheet.save(build / "review/contact_sheet.jpg", quality=95)
    report["image_checks"] = checks
    atomic_json(build / "dressing_review.json", report)


if __name__ == "__main__":
    if "--prepare" in sys.argv:
        prepare_fixture(Path(sys.argv[sys.argv.index("--prepare") + 1]).resolve())
    elif "--review" in sys.argv:
        review_stills(Path(sys.argv[sys.argv.index("--review") + 1]).resolve())
    else:
        main()
