"""Short landscape TEF speaking rehearsal, using the existing French interview."""

import argparse
from io import BytesIO
from functools import partial
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import wave

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from align_words import validate_words
from build_paths import build_directory
from episode_config import check_timeline, read_episode
from generation_runtime import (forget_process, generation_job, run_process, start_process,
                                stop_processes)
from prepare_audio import atomic_json, sha256_file, subtitles
from runtime_config import font_path, tool_path
from social_captions import caption_pages

SIZE = (960, 540)
SCENE = (32, 106, 672, 426)
GOLD = "#f4ce72"
WHITE = "#f4f4ef"
BG = "#14242e"


def is_production(episode):
    return episode.get("template") == "tef_speaking_full_production"


def is_full(episode):
    return episode.get("template") in ("tef_speaking_full_preview", "tef_speaking_full_production")


def output_scale(episode):
    return 2 if is_production(episode) else 1


def native_settings(episode):
    if is_production(episode):
        return {"width": 1280, "height": 640, "samples": 8, "motion_step": 2}
    return {"width": 640, "height": 320, "samples": 2, "motion_step": 3}


def load_preview(path):
    episode = read_episode(path)
    full = is_full(episode)
    if (episode.get("template") not in (
            "tef_speaking_youtube_preview", "tef_speaking_full_preview", "tef_speaking_full_production")
            or episode.get("language") != "fr"
            or episode.get("exam") != {"family": "tef_canada", "skill": "speaking", "section": "A_B"}
            or episode["scene"].get("entrance") is not False
            or episode["source"].get("duration_limit_seconds") != (1800 if full else 90)
            or (full and not episode["source"].get("duration_exception"))
            or episode["turns"][0]["text"] != episode["title"]
            or {t.get("section") for t in episode["turns"] if t.get("section")} != {"A", "B"}):
        raise ValueError("Expected a seated French A+B preview with spoken title and explicit duration limit.")
    for section, value in episode["preview_notices"].items():
        episode["preview_notices"][section] = str((Path(path).resolve().parent / value).resolve(strict=True))
    return episode


def native(build):
    import bpy
    from episode_profiles import active_actors
    from long_speaking_scene import head_bounds, hair_drop
    from produce_v4 import camera_at_frame, scene_build
    from episode_config import PROFILES
    from studio_characters import StudioCharacter

    episode = read_episode(build / "episode.json")
    profile = "production" if is_production(episode) else "preview"
    PROFILES[profile] = native_settings(episode)
    scene_build(build, build / "episode.json", profile)
    scene = bpy.context.scene
    manifest = json.loads((build / "scene_manifest.json").read_text(encoding="utf-8"))
    episode, timeline = manifest["episode"], manifest["timeline"]
    actors = {name: StudioCharacter.from_scene(name) for name in active_actors(episode)}
    checks = []
    # Lenses only widen, so checking earlier poses remains conservative.
    for frame in range(1, timeline["total_frames"] + 1, manifest["motion_step"]):
        scene.frame_set(frame)
        name = camera_at_frame(manifest["camera_markers"], frame)
        camera = scene.objects[name]
        selected = (list(actors.values()) if name.startswith("01") else
                    [actors["candidate_a" if name.startswith("04") else "examiner"]])
        for _ in range(60):
            bpy.context.view_layer.update()
            bounds = head_bounds(scene, camera, selected)
            if all(h["in_front"] and min(h["bounds"]) > .04 and max(h["bounds"]) < .96 for h in bounds):
                break
            camera.data.lens *= .96
        else:
            raise ValueError("Cannot fit the complete animated heads and hair.")
        if any(a.kind == "rain" and hair_drop(a) < .15 for a in actors.values()):
            raise ValueError("Animated ponytail does not hang down.")
        checks.append({"frame": frame, "camera": name, "heads": bounds})
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(build / "studio.blend"), compress=True)
    scale = output_scale(episode)
    manifest.update(output_width=SIZE[0] * scale, output_height=SIZE[1] * scale,
                    landscape_preview=not is_production(episode))
    atomic_json(build / "scene_manifest.json", manifest)
    atomic_json(build / "scene_checks.json", {
        "all_sampled_heads_and_hair_fit": True, "hair_hangs_down": True,
        "frames": checks, "blend_sha256": sha256_file(build / "studio.blend"),
    })


def current_turn(timeline, frame):
    return next((t for t in reversed(timeline["turns"]) if t["start_frame"] <= frame),
                timeline["turns"][0])


def active_on_frame(words, turn_start, frame, fps):
    start, end = frame / fps - turn_start, (frame + 1) / fps - turn_start
    overlaps = [max(0, min(end, word["end"]) - max(start, word["start"])) for word in words]
    return max(range(len(words)), key=overlaps.__getitem__) if overlaps and max(overlaps) > 0 else None


def notice_countdown(turn, frame, fps):
    duration = turn.get("pause_after_frames", 0)
    start = turn["end_frame"]
    end = start + duration
    if turn.get("kind") != "notice" or not start <= frame < end:
        return None
    return math.ceil((end - frame) / fps), (end - frame) / duration


def draw_words(draw, words, box, *, active=None, size=22, color=WHITE, scale=1):
    from PIL import ImageFont

    box = tuple(value * scale for value in box)
    size *= scale
    gap = 5 * scale
    font = ImageFont.truetype(str(font_path()), size)
    x, y = box[:2]
    for index, word in enumerate(words):
        width = draw.textlength(word, font=font)
        if x + width > box[2]:
            x, y = box[0], y + size + gap
        if x + width > box[2] or y + size + gap > box[3]:
            raise ValueError("Landscape subtitle or title overflows its reserved box.")
        draw.text((x, y), word, font=font, fill=GOLD if active == index else color)
        x += draw.textlength(word + " ", font=font)


def compose(episode, timeline, pages, frame, native_image):
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    scale = output_scale(episode)
    production = is_production(episode)
    xy = lambda values: tuple(value * scale for value in values)
    image = Image.new("RGB", xy(SIZE), BG)
    draw = ImageDraw.Draw(image)
    words = partial(draw_words, draw, scale=scale)
    turn = current_turn(timeline, frame)
    seconds = frame / timeline["fps"]
    closing = turn["id"] == episode["turns"][-1]["id"]
    full = is_full(episode)
    font = lambda size: ImageFont.truetype(str(font_path(True)), size * scale)
    draw.text(xy((32, 15)), "FRENCH COMPASS  |  EXPRESSION ORALE", font=font(16), fill=GOLD)
    badge = "TEST BLANC INTÉGRAL" if production else "APERÇU INTÉGRAL" if full else "APERÇU · 16:9"
    draw.text(xy((730 if production else 756 if full else 790, 18)), badge,
              font=font(14), fill=WHITE)
    opening = timeline["turns"][0]
    active = active_on_frame(opening["words"], opening["start"], frame, timeline["fps"])
    words(episode["title"].split(), (32, 42, 928, 82), active=active, size=24 if full else 29)
    label = episode["sections"].get(turn.get("section"), "Test blanc 1 · Dialogues complets" if full
                                   else "Test blanc 1 · Extraits adaptés")
    draw.text(xy((32, 82)), label, font=font(16), fill=GOLD)
    draw.rounded_rectangle(xy((704, 106, 928, 512)), radius=15 * scale, fill="#223842")
    with Image.open(episode["book_cover"]) as cover:
        height = 242 if full else 258
        fitted = ImageOps.contain(cover.convert("RGB"), xy((176, height)), Image.Resampling.LANCZOS)
        image.paste(fitted, (816 * scale - fitted.width // 2,
                            131 * scale + (height * scale - fitted.height) // 2))
    if full:
        words(episode["promotion"]["promotion"].split(), (724, 393, 912, 464), size=18, color=GOLD)
        if episode["promotion"].get("description_hint"):
            draw.text(xy((720, 449)), episode["promotion"]["description_hint"], font=font(14), fill=WHITE)
        draw.text(xy((720, 479)), episode["promotion"]["visible_url"], font=font(17), fill=WHITE)
    else:
        words("Plus de pratique avec notre livre TEF Canada".split(),
              (724, 405, 912, 499), size=18, color=GOLD)
    if (full and turn.get("kind") == "notice") or (not full and turn["id"] in ("01", "04")):
        draw.rounded_rectangle(xy(SCENE), radius=14 * scale, fill="#223842")
        with Image.open(episode["preview_notices"][turn["section"]]) as notice:
            fitted = ImageOps.contain(notice.convert("RGB"), xy((640, 320)), Image.Resampling.LANCZOS)
            image.paste(fitted, (32 * scale + (640 * scale - fitted.width) // 2,
                                106 * scale + (320 * scale - fitted.height) // 2))
    elif full and turn.get("kind") == "setup":
        draw.rounded_rectangle(xy(SCENE), radius=14 * scale, fill="#223842")
        words("Deux sections".split(), (64, 144, 642, 195), size=32, color=GOLD)
        words("A · Se renseigner".split(), (64, 220, 642, 267), size=28)
        words("B · Convaincre un ami".split(), (64, 297, 642, 344), size=28)
    elif closing:
        draw.rounded_rectangle(xy(SCENE), radius=14 * scale, fill="#223842")
        words("À vous de parler !".split(), (64, 162, 642, 218), size=35, color=GOLD)
        words(("Plus de tâches et de dialogues modèles dans notre livre TEF Canada."
                         if full else "Retrouvez les dialogues modèles complets dans notre livre TEF Canada.").split(),
                   (64, 240, 642, 360), size=28)
    else:
        if native_image.size != xy((640, 320)):
            raise ValueError("Use the native landscape scene without stretching or cropping.")
        image.paste(native_image, xy(SCENE[:2]))
    page = next((p for p in pages if p["start"] <= seconds < p["end"]), None)
    reading = notice_countdown(turn, frame, timeline["fps"]) if full else None
    if reading:
        remaining, fraction = reading
        draw.text(xy((48, 448)), f"Temps de lecture : {remaining} s", font=font(22), fill=WHITE)
        draw.rounded_rectangle(xy((48, 490, 656, 504)), radius=7 * scale, fill="#38505a")
        draw.rectangle(xy((48, 490, 48 + max(1, round(608 * fraction)) - 1, 504)), fill=GOLD)
    elif page:
        active = active_on_frame(page["words"], page["turn_start"], frame, timeline["fps"])
        words([w["word"] for w in page["words"]], (32, 441, 672, 522), active=active, size=22)
    footer = ("Simulation guidée indépendante · Durée des modèles adaptée" if production else
              "Simulation guidée indépendante · Durée des modèles adaptée · PRÉVISUALISATION" if full else
              "Aperçu adapté · Pas une simulation complète · PRÉVISUALISATION")
    draw.text(xy((32, 525)), footer, font=ImageFont.truetype(str(font_path()), 10 * scale), fill="#aabac1")
    return image


def review(build, episode, timeline, pages):
    import numpy as np
    from PIL import Image, ImageDraw

    production = is_production(episode)
    scale = output_scale(episode)
    size = tuple(value * scale for value in SIZE)
    step = native_settings(episode)["motion_step"]
    video = build / ("production_youtube.mp4" if production else "preview_youtube.mp4")
    report = json.loads(run_process(
        ["ffprobe", "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", video],
        capture_output=True, check=True).stdout)
    stream = next(s for s in report["streams"] if s["codec_type"] == "video")
    if ((stream["width"], stream["height"]) != size or stream["r_frame_rate"] != "24/1"
            or int(stream["nb_read_frames"]) != timeline["total_frames"]
            or float(report["format"]["duration"]) >= episode["source"]["duration_limit_seconds"]):
        raise ValueError("Encoded size, duration or frame clock differs.")
    run_process(["ffmpeg", "-nostdin", "-v", "error", "-i", video, "-f", "null", "-"], check=True)
    pcm = run_process(["ffmpeg", "-nostdin", "-v", "error", "-i", video, "-vn", "-ac", "1",
                       "-ar", "48000", "-f", "s16le", "pipe:1"], capture_output=True, check=True).stdout
    with wave.open(str(build / "dialogue.wav"), "rb") as wav:
        reference = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(float)
    actual = np.frombuffer(pcm, dtype="<i2").astype(float)
    count = min(len(reference), len(actual))
    correlation = float(np.corrcoef(reference[:count], actual[:count])[0, 1])
    if abs(len(reference) - len(actual)) > 2048 or not math.isfinite(correlation) or correlation < .98:
        raise ValueError("Encoded audio differs or is shifted.")
    frames = {0, timeline["total_frames"] - 1}
    silences = []
    for turn in timeline["turns"]:
        frames.update((max(0, turn["start_frame"] - 1), turn["start_frame"],
                       min(timeline["total_frames"] - 1, turn["start_frame"] + 24)))
        if is_full(episode) and turn.get("kind") == "notice":
            start = turn["end_frame"]
            end = start + turn["pause_after_frames"]
            for boundary in range(start, end + 1, timeline["fps"]):
                frames.update((boundary - 1, boundary))
            samples_per_frame = 48000 // timeline["fps"]
            left, right = start * samples_per_frame + 2048, end * samples_per_frame - 2048
            if np.any(reference[left:right]):
                raise ValueError(f"Non-silent reading pause: {turn['id']}")
            peak = float(np.max(np.abs(actual[left:right])))
            if peak > 1:
                raise ValueError(f"Encoded reading pause is not silent: {turn['id']}")
            silences.append({"turn": turn["id"], "start_frame": start, "end_frame": end,
                             "seconds": (end - start) / timeline["fps"],
                             "encoded_guarded_peak_pcm16": peak, "edge_guard_samples": 2048})
    for word in timeline["turns"][0]["words"]:
        frames.add(math.ceil((word["start"] + word["end"]) * 12))
    folder = build / "review_youtube"
    folder.mkdir(exist_ok=True)
    checks, thumbs = [], []
    frames = sorted(frames)
    select = "+".join(f"eq(n\\,{frame})" for frame in frames)
    run_process(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", video,
                 "-vf", f"select={select}", "-fps_mode", "vfr", folder / "sample_%04d.png"], check=True)
    for index, frame in enumerate(frames, 1):
        with Image.open(folder / f"sample_{index:04d}.png") as source:
            decoded = source.convert("RGB")
        sample = 1 + (frame // step) * step
        with Image.open(build / "frames" / f"frame_{sample:04d}.png") as source:
            expected = compose(episode, timeline, pages, frame, source.convert("RGB"))
        errors = {}
        for name, box in (("full", (0, 0, *SIZE)), ("promotion", (704, 106, 928, 512)),
                          ("subtitles", (32, 441, 672, 522)), ("title", (32, 42, 928, 82))):
            box = tuple(value * scale for value in box)
            error = float(np.abs(np.asarray(decoded.crop(box)).astype(float)
                                - np.asarray(expected.crop(box)).astype(float)).mean())
            if error > 8:
                raise ValueError(f"Encoded {name} differs at frame {frame}: {error}")
            errors[name] = error
        decoded.save(folder / f"frame_{frame:05d}.png")
        thumb = decoded.resize((384, 216))
        canvas = Image.new("RGB", (384, 238), BG)
        canvas.paste(thumb)
        ImageDraw.Draw(canvas).text((8, 219), f"{frame / 24:.3f}s · frame {frame}", fill=WHITE)
        thumbs.append(canvas)
        checks.append({"frame": frame, "mean_absolute_errors": errors})
    for first in range(0, len(thumbs), 12):
        group = thumbs[first:first + 12]
        sheet = Image.new("RGB", (1152, math.ceil(len(group) / 3) * 238), BG)
        for index, thumb in enumerate(group):
            sheet.paste(thumb, ((index % 3) * 384, (index // 3) * 238))
        sheet.save(build / f"contact_youtube_{first // 12 + 1}.jpg", quality=94)
    atomic_json(build / "delivery_checks.json", {
        "media": report, "audio_correlation": correlation, "encoded_checks": checks,
        "notice_silences": silences,
        "human_listening": False, "preview_only": not production,
    })


def reuse_native(source, build):
    from render import valid_frame

    source = Path(source).resolve(strict=True)
    manifest = json.loads((source / "export_manifest.json").read_text(encoding="utf-8"))
    audit_path = source.with_name(source.name + "_final_audit.json")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit["export_manifest_sha256"] != sha256_file(source / "export_manifest.json"):
        raise ValueError("Native audit is not bound to the frozen source delivery.")
    for name, digest in manifest["files_sha256"].items():
        if sha256_file(source / name) != digest:
            raise ValueError(f"Native source delivery changed: {name}")
    for name, digest in manifest["source_sha256"].items():
        if sha256_file(source / "source_export" / name) != digest:
            raise ValueError(f"Native source snapshot changed: {name}")
    if read_episode(source / "episode.json") != read_episode(build / "episode.json"):
        raise ValueError("Native reuse requires an identical resolved episode.")
    if (source / "timeline.json").read_bytes() != (build / "timeline.json").read_bytes():
        raise ValueError("Native reuse requires the exact measured timeline.")
    checks = json.loads((source / "scene_checks.json").read_text(encoding="utf-8"))
    if sha256_file(source / "studio.blend") != checks["blend_sha256"]:
        raise ValueError("Native source scene changed.")
    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    files = ("studio.blend", "scene_checks.json", "scene_manifest.json", "frames_manifest.json",
             "speech_asr_check.json")
    if (source / "speech_medium_review.json").is_file():
        files += ("speech_medium_review.json",)
    hashes = {}
    for name in files:
        hashes[name] = sha256_file(source / name)
        shutil.copy2(source / name, build / name)
    (build / "frames").mkdir(exist_ok=True)
    for frame in range(1, timeline["total_frames"] + 1, 3):
        name = f"frames/frame_{frame:04d}.png"
        if not valid_frame(source / name, 640, 320):
            raise ValueError(f"Invalid source native frame: {name}")
        hashes[name] = sha256_file(source / name)
        if audit["native_sha256"].get(Path(name).name) != hashes[name]:
            raise ValueError(f"Native source differs from its independent audit: {name}")
        shutil.copy2(source / name, build / name)
    for name, digest in hashes.items():
        if sha256_file(build / name) != digest:
            raise ValueError(f"Native copy differs: {name}")
    atomic_json(build / "native_reuse.json", {
        "source": str(source), "source_manifest_sha256": sha256_file(source / "export_manifest.json"),
        "native_audit_sha256": sha256_file(audit_path),
        "files_sha256": hashes, "policy": "Exact native PNGs, scene and audio; composition-only revision.",
    })


@generation_job
def build_preview(path, build, jobs=2, until="export", speech_cache_from=None, reuse_audio=None,
                  profile="preview", render_device="CPU"):
    from PIL import Image
    from pipeline import build_episode, run_command

    episode = load_preview(path)
    production = is_production(episode)
    if production:
        from tef_speaking_production import production_reuse_spec
        if profile != "production" or speech_cache_from is not None:
            raise ValueError("TEF production requires exact approved audio, not new speech.")
        receipt = production_reuse_spec(episode, reuse_audio)
    elif profile != "preview" or render_device != "CPU":
        raise ValueError("TEF previews require their CPU preview profile.")
    build = build_directory(build)
    build_episode(path, build, jobs=jobs, until="audio", speech_cache_from=speech_cache_from,
                  reuse_audio=reuse_audio, profile=profile, render_device=render_device)
    if production:
        source = Path(receipt["source"])
        atomic_json(build / "production_approval.json", receipt)
        for name in ("speech_asr_check.json", "speech_medium_review.json", "subtitles.srt"):
            if name in receipt["files_sha256"]:
                if sha256_file(source / name) != receipt["files_sha256"][name]:
                    raise ValueError(f"Approved TEF speech evidence changed: {name}")
                shutil.copy2(source / name, build / name)
    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    check_timeline(episode, timeline)
    for turn in timeline["turns"]:
        validate_words(turn["words"], turn["text"], turn["wav_duration"])
    pages = caption_pages(episode, timeline)
    for section, source in episode["preview_notices"].items():
        target = build / f"notice_{section}.jpg"
        shutil.copy2(source, target)
    inputs = {str(Path(path).resolve()): sha256_file(Path(path)),
              **{name: value for name, value in json.loads(
                  (build / "pipeline_state.json").read_text(encoding="utf-8"))["spec"]["asset_sha256"].items()}}
    source_book = (Path(path).resolve().parent / episode["source"]["book"]).resolve(strict=True)
    inputs[str(source_book)] = sha256_file(source_book)
    if episode["source"].get("authoring_config"):
        config = Path(episode["source"]["authoring_config"])
        inputs[str(config)] = sha256_file(config)
    if production:
        config = Path(episode["production_config"])
        source = Path(episode["approved_preview"])
        inputs[str(config)] = sha256_file(config)
        inputs[str(source / "export_manifest.json")] = episode["approved_preview_manifest_sha256"]
        for name, digest in receipt["files_sha256"].items():
            inputs[str(source / name)] = digest
    shutil.copy2(episode["book_cover"], build / "book_cover.jpg")
    for value in episode["preview_notices"].values():
        inputs[value] = sha256_file(Path(value))
    atomic_json(build / "preview_inputs.json", inputs)
    atomic_json(build / "caption_review.json", {"pages": pages, "low_confidence_words": [
        {"turn": t["id"], **w} for t in timeline["turns"] for w in t["words"] if w["score"] < .4]})
    if until == "audio":
        return build
    if reuse_audio is not None and not production:
        reuse_native(reuse_audio, build)
    elif not (build / "scene_checks.json").is_file():
        run_command([tool_path("blender"), "-b", "--disable-autoexec", episode["scene"]["base_scene"],
                     "-t", "4", "--python-exit-code", "1", "--python", Path(__file__),
                     "--", "--native", "--build", build], build / "native_scene.log")
    scene = json.loads((build / "scene_manifest.json").read_text(encoding="utf-8"))
    checks = json.loads((build / "scene_checks.json").read_text(encoding="utf-8"))
    quality = native_settings(episode)
    if (sha256_file(build / "studio.blend") != checks["blend_sha256"]
            or scene["episode"] != episode or scene["timeline"] != timeline
            or any(scene[key] != value for key, value in quality.items())
            or not checks["all_sampled_heads_and_hair_fit"] or not checks["hair_hangs_down"]):
        raise ValueError("Saved TEF native scene/checks differ from the requested production or preview.")
    if until == "scene":
        return build
    if reuse_audio is None or production:
        run_command([sys.executable, ROOT / "render.py", "frames", "--episode", build / "episode.json",
                     "--build", build, "--jobs", str(jobs), "--render-device", render_device],
                    build / "native_frames.log")
    if not (build / "speech_asr_check.json").is_file():
        result = run_process([sys.executable, ROOT / "check_speech.py", "--build", build],
                             capture_output=True)
        (build / "speech_check.log").write_bytes(result.stdout + result.stderr)
        if not (build / "speech_asr_check.json").is_file():
            raise RuntimeError("Independent ASR did not produce its report.")
    for name, digest in inputs.items():
        if sha256_file(Path(name)) != digest:
            raise ValueError(f"Input changed during generation: {name}")
    scale = output_scale(episode)
    filename = "production_youtube.mp4" if production else "preview_youtube.mp4"
    command = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{960 * scale}x{540 * scale}", "-r", "24", "-i", "pipe:0",
               "-i", str(build / "dialogue.wav"),
               "-map", "0:v", "-map", "1:a", "-c:v", "libx264",
               "-preset", "medium" if production else "veryfast", "-crf", "18" if production else "20",
               "-pix_fmt", "yuv420p", "-color_range", "tv", "-c:a", "aac", "-b:a", "160k",
               "-t", str(timeline["duration"]), "-movflags", "+faststart",
               str(build / filename)]
    with (build / "encode_youtube.log").open("w") as log:
        process = start_process(command, stdin=subprocess.PIPE, stderr=log)
        try:
            for frame in range(timeline["total_frames"]):
                sample = 1 + (frame // quality["motion_step"]) * quality["motion_step"]
                with Image.open(build / "frames" / f"frame_{sample:04d}.png") as source:
                    image = compose(episode, timeline, pages, frame, source.convert("RGB"))
                process.stdin.write(image.tobytes())
            process.stdin.close()
            if process.wait():
                raise RuntimeError("TEF YouTube encoding failed.")
        except BaseException:
            stop_processes([process])
            raise
        finally:
            forget_process(process)
    (build / "subtitles.srt").write_text(subtitles(timeline), encoding="utf-8")
    review(build, episode, timeline, pages)
    code = json.loads((build / "pipeline_state.json").read_text(encoding="utf-8"))["spec"]["code_sha256"]
    for name, digest in code.items():
        if sha256_file(ROOT / name) != digest:
            raise ValueError(f"Code changed during generation: {name}")
    folder = build / "source_export"
    folder.mkdir(exist_ok=True)
    for name in code:
        shutil.copy2(ROOT / name, folder / name)
    outputs = [filename, "episode.json", "timeline.json", "dialogue.wav",
               "word_alignment.json", "speech_asr_check.json", "caption_review.json", "scene_checks.json",
               "scene_manifest.json", "frames_manifest.json", "preview_inputs.json", "delivery_checks.json",
               "subtitles.srt", "notice_A.jpg", "notice_B.jpg", "book_cover.jpg"]
    outputs += [p.name for p in build.glob("contact_youtube_*.jpg")]
    outputs += [name for name in ("native_reuse.json", "audio_reuse.json", "speech_medium_review.json",
                                 "production_approval.json")
                if (build / name).is_file()]
    atomic_json(build / "export_manifest.json", {
        "files_sha256": {name: sha256_file(build / name) for name in outputs},
        "source_sha256": code, "preview_only": not production,
    })
    print(f"Ready: {build / filename} ({timeline['duration']:.3f}s)", flush=True)
    return build


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", action="store_true", required=True)
    parser.add_argument("--build", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else None)
    native(args.build.resolve())
