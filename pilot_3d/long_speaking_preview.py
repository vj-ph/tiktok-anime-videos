"""Measured dual-format speaking previews and native production masters."""

import copy
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageOps

from align_words import validate_words
from build_paths import build_directory
from episode_config import PROFILES, check_timeline, read_episode
from generation_runtime import (forget_process, generation_job, run_process, stage_completed,
                                start_process, stop_processes)
from long_speaking import (ACCENT, FORMATS, PANEL, compile_script, compose, load_episode as load_storyboard,
                           panels, text_box)
from prepare_audio import atomic_json, sha256_file, validate_episode
from runtime_config import font_path, tool_path
from long_speaking_production import notice_at

ROOT = Path(__file__).resolve().parent
OUTPUTS = {"youtube": (960, 540), "social": (540, 960)}
SOURCES = ("pipeline.py", "long_speaking.py", "long_speaking_scene.py", "long_speaking_preview.py",
           "long_speaking_full_preview.py",
           "long_speaking_production.py",
           "long_speaking_preview_scene.py", "prepare_audio.py", "align_words.py", "check_speech.py",
           "episode_config.py", "episode_profiles.py", "scene_direction.py", "studio_characters.py",
           "produce_v4.py", "polish_exchange.py", "entrance.py", "picture_presentation.py",
           "listening_scene.py", "listener_motion.py", "runtime_config.py", "generation_runtime.py",
           "build_paths.py", "build_scene.py", "scene_dressing.py")


def is_production(episode):
    return episode.get("template") == "long_speaking_production"


def shared_native(episode):
    return is_production(episode) and episode["render"].get("native_source") == "youtube"


def native_panel(episode, mode, image):
    box = FORMATS[mode]["scene"]
    size = box[2] - box[0], box[3] - box[1]
    if shared_native(episode) and mode == "social":
        return ImageOps.fit(image, size, Image.Resampling.LANCZOS, centering=(.5, .5))
    return image.resize(size, Image.Resampling.LANCZOS)


def output_sizes(episode):
    return {mode: FORMATS[mode]["size"] for mode in OUTPUTS} if is_production(episode) else OUTPUTS


def output_name(episode, mode):
    return f"{'production' if is_production(episode) else 'preview'}_{mode}.mp4"


def load_preview(path, profile="preview"):
    path = Path(path).resolve(strict=True)
    episode = read_episode(path)
    production = is_production(episode)
    if production != (profile == "production") or profile not in ("preview", "production"):
        raise ValueError("Use the production template with --profile production; previews remain preview-only.")
    full = production or episode.get("template") == "long_speaking_full_preview"
    if production:
        from long_speaking_production import resolve_production
        episode = resolve_production(episode, path)
    elif full:
        from long_speaking_full_preview import resolve_full_episode
        episode = resolve_full_episode(episode, path)
    elif episode.get("template") != "long_speaking_preview":
        raise ValueError("Expected a long_speaking preview template.")
    validate_episode(episode)
    if episode["source"].get("duration_limit_seconds") != (900 if full else 90) or episode["fps"] != 24:
        raise ValueError("The short preview requires 24 fps and a strict 90-second limit.")
    if episode["intro_seconds"] != 0 or episode["scene"].get("entrance") is not False:
        raise ValueError("The preview opens with speech and uses the seated scene.")
    render = episode["render"]
    expected = ({"motion_step": PROFILES["production"]["motion_step"], "native_scale": 1.0,
                 "samples": PROFILES["production"]["samples"]} if production else
                {"motion_step": 3, "native_scale": .25, "samples": 2})
    if shared_native(episode):
        expected = {"motion_step": 2, "native_scale": 1.0, "samples": 8, "native_source": "youtube"}
    if render != expected:
        raise ValueError("Use approved production quality: native 16-sample per-frame renders, "
                         "or shared 8-sample YouTube renders on twos."
                         if production else
                         "Use the bounded CPU preview quality; this is not a production path.")
    episode["storyboard"] = str((path.parent / episode["storyboard"]).resolve(strict=True))
    storyboard = load_storyboard(episode["storyboard"])
    if full:
        storyboard["parts"][0].update({key: episode["review_part1"][key] for key in ("title", "topic", "task")})
    if episode["title"] != storyboard["title"]:
        raise ValueError("Preview and approved storyboard titles differ.")
    if episode["scene"]["base_scene"] != storyboard["scene"]["base_scene"]:
        raise ValueError("Preview must use the approved room.")
    source_script = compile_script(storyboard)
    source_turns = {turn["id"]: turn for turn in source_script["turns"]}
    allowed = {panel["id"] for panel in panels(storyboard, source_script)}
    if {t["part"] for t in episode["turns"] if t["kind"] == "model"} != {1, 2, 3}:
        raise ValueError("Preview must include models for all three Teile.")
    if episode["turns"][0]["kind"] != "opening" or episode["turns"][-1]["kind"] != "cta":
        raise ValueError("Spoken title and final book CTA are required.")
    opening = episode["turns"][0]
    groups = opening.get("display_word_groups", [])
    if (len(groups) != len(episode["title"].split())
            or [i for group in groups for i in group] != list(range(len(opening["text"].split())))):
        raise ValueError("Every displayed title word must map to actual spoken tokens.")
    for turn in episode["turns"]:
        if turn["panel_id"] not in allowed:
            raise ValueError("Unknown approved storyboard panel.")
        if "source_segment" in turn:
            source = source_turns.get(turn["source_segment"])
            if source is None or (turn["text"] not in source["text"] and not turn.get("adaptation")):
                raise ValueError("Preview excerpts require source provenance or an explicit adaptation.")
    for voice in episode["voices"].values():
        from prepare_audio import inspect_wav
        inspect_wav(Path(voice["audio"]))
        if not Path(voice["transcript"]).read_text(encoding="utf-8").strip():
            raise ValueError("Reference transcript is empty.")
    return episode, storyboard


def caption_pages(turn):
    tokens = turn.get("display_text", turn["text"]).split()
    result, start = [], 0
    while start < len(tokens):
        end = min(start + 12, len(tokens))
        punctuation = [i + 1 for i in range(start + 5, end) if tokens[i].endswith((".", "?", "!"))]
        if punctuation:
            end = punctuation[-1]
        result.append((start, end))
        start = end
    return result


def caption_words(turn):
    words = validate_words(turn["words"], turn["text"], turn["wav_duration"])
    if "display_text" not in turn:
        return words
    tokens = turn["display_text"].split()
    groups = turn["display_word_groups"]
    if len(groups) != len(tokens) or [i for group in groups for i in group] != list(range(len(words))):
        raise ValueError("Display words must map exactly to measured spoken tokens.")
    return [{"word": token, "start": words[group[0]]["start"], "end": words[group[-1]]["end"],
             "score": min(words[i]["score"] for i in group)}
            for token, group in zip(tokens, groups)]


def turn_at(timeline, frame):
    return next((turn for turn in reversed(timeline["turns"]) if turn["start_frame"] <= frame),
                timeline["turns"][0])


def display_state(episode, timeline, frame):
    turn = turn_at(timeline, frame)
    elapsed = frame / timeline["fps"] - turn["start"]
    words = validate_words(turn["words"], turn["text"], turn["wav_duration"])
    if turn["kind"] == "opening":
        intervals = [(words[group[0]]["start"], words[group[-1]]["end"])
                     for group in episode["turns"][0]["display_word_groups"]]
        active = next((i for i, (start, end) in enumerate(intervals) if start <= elapsed < end), None)
        return turn, 0, len(words), active
    words = caption_words(turn)
    pages = caption_pages(turn)
    start, end = next(((a, b) for a, b in reversed(pages) if elapsed >= words[a]["start"]), pages[0])
    active = next((i - start for i in range(start, end)
                   if words[i]["start"] <= elapsed < words[i]["end"]), None)
    return turn, start, end, active


def native_sample(turn, frame, step):
    return turn["start_frame"] + (frame - turn["start_frame"]) // step * step


def native_plan(episode, storyboard, timeline):
    lookup = {panel["id"]: panel for panel in panels(storyboard, compile_script(storyboard))}
    result = []
    modes = ("youtube",) if shared_native(episode) else FORMATS
    for mode in modes:
        layout = FORMATS[mode]
        box = layout["scene"]
        width, height = (max(2, round((box[i + 2] - box[i]) * episode["render"]["native_scale"]))
                         for i in (0, 1))
        for index, turn in enumerate(timeline["turns"]):
            if turn["panel_id"] in ("05_teil2_picture", "12_final_cta"):
                continue
            end = timeline["turns"][index + 1]["start_frame"] if index + 1 < len(timeline["turns"]) else timeline["total_frames"]
            for frame in range(turn["start_frame"], end, episode["render"]["motion_step"]):
                if notice_at(timeline, frame):
                    continue
                result.append({"format": mode, "frame": frame, "camera": turn.get("camera", lookup[turn["panel_id"]]["camera"]),
                               "size": [width, height], "file": f"native/{mode}_{frame:05d}.png"})
    return result


def overlay(episode, storyboard, timeline, mode, frame):
    notice = notice_at(timeline, frame)
    if notice:
        from long_speaking_production import notice_overlay
        image, check = notice_overlay(storyboard, mode, notice)
        check.update(frame=frame, turn_id=notice["id"], page=None, active_word=None)
        return image, check
    turn, start, end, active = display_state(episode, timeline, frame)
    panel = copy.deepcopy(next(p for p in panels(storyboard, compile_script(storyboard))
                               if p["id"] == turn["panel_id"]))
    panel["part"] = turn["part"]
    if "heading" in turn:
        panel["heading"] = turn["heading"]
    if turn["kind"] not in ("opening", "cta"):
        panel["body"] = " ".join(turn.get("display_text", turn["text"]).split()[start:end])
    if turn["kind"] == "task":
        panel["heading"] = f"Teil {turn['part']} · {storyboard['parts'][turn['part'] - 1]['title']}"
    visual = copy.deepcopy(storyboard)
    if not is_production(episode):
        visual["branding"] += " · VORSCHAU"
    box = FORMATS[mode]["scene"]
    blank = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), PANEL)
    image, check = compose(visual, panel, mode, blank, sample_highlights=False, active_word=active)
    if turn["kind"] == "cta":
        box = (700, 900, 1780, 1030) if mode == "youtube" else (90, 1518, 900, 1650)
        caption = text_box(ImageDraw.Draw(image), " ".join(turn.get("display_text", turn["text"]).split()[start:end]), box,
                           size=35, minimum=27, highlight_word=active)
        if "highlighted_word" in caption:
            caption["highlight_kind"] = "forced_alignment"
        check["text"].append(caption)
    check.update(frame=frame, turn_id=turn["id"], page=[start, end], active_word=active)
    return image, check


def run_logged(command, log):
    with Path(log).open("w", encoding="utf-8") as output:
        run_process(command, stdout=output, stderr=subprocess.STDOUT, check=True)


def caption_preflight(build, episode, storyboard, timeline):
    checks, pages = [], []
    for index, turn in enumerate(timeline["turns"]):
        words = caption_words(turn)
        end = (timeline["turns"][index + 1]["start_frame"] / timeline["fps"]
               if index + 1 < len(timeline["turns"]) else timeline["duration"])
        end = min([end] + [n["start_frame"] / timeline["fps"]
                          for n in timeline.get("silent_notices", [])
                          if turn["start"] < n["start_frame"] / timeline["fps"] < end])
        for start, stop in caption_pages(turn):
            page_start = turn["start"] if start == 0 else turn["start"] + words[start]["start"]
            page_end = end if stop == len(words) else turn["start"] + words[stop]["start"]
            text = " ".join(turn.get("display_text", turn["text"]).split()[start:stop])
            pages.append({"turn_id": turn["id"], "text": text, "start": page_start,
                          "end": page_end, "characters_per_second": len(text) / (page_end - page_start)})
        for word in turn["words"]:
            frame = turn["start_frame"] + math.ceil((word["start"] + word["end"]) * timeline["fps"] / 2)
            for mode in OUTPUTS:
                _, check = overlay(episode, storyboard, timeline, mode, frame)
                checks.append(check)
    atomic_json(build / "caption_preflight.json", {
        "all_aligned_word_layouts_fit": True, "pages": pages, "checks": checks,
        "reading_warnings": [p for p in pages if p["characters_per_second"] > 20],
        "low_confidence_words": [{"turn_id": t["id"], **w} for t in timeline["turns"]
                                 for w in t["words"] if w["score"] < .1],
    })


def encode(build, episode, storyboard, timeline, mode):
    width, height = output_sizes(episode)[mode]
    path = build / output_name(episode, mode)
    command = [shutil.which("ffmpeg"), "-nostdin", "-v", "error", "-y", "-f", "rawvideo",
               "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(timeline["fps"]),
               "-i", "pipe:0", "-i", str(build / "dialogue.wav"), "-map", "0:v", "-map", "1:a",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-t",
               str(timeline["total_frames"] / timeline["fps"]), "-movflags", "+faststart", str(path)]
    last_key = last_native = None
    cached = native_image = None
    with (build / f"encode_{mode}.log").open("w") as log:
        process = start_process(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
        try:
            for frame in range(timeline["total_frames"]):
                notice = notice_at(timeline, frame)
                if notice:
                    key = ("silent_notice", notice["id"])
                    if key != last_key:
                        cached, _ = overlay(episode, storyboard, timeline, mode, frame)
                        last_key = key
                    process.stdin.write(cached.resize(
                        (width, height), Image.Resampling.LANCZOS).tobytes())
                    continue
                turn, start, end, active = display_state(episode, timeline, frame)
                key = (turn["id"], start, end, active)
                if key != last_key:
                    cached, _ = overlay(episode, storyboard, timeline, mode, frame)
                    last_key = key
                image = cached.copy()
                if turn["panel_id"] not in ("05_teil2_picture", "12_final_cta"):
                    sample = native_sample(turn, frame, episode["render"]["motion_step"])
                    if sample != last_native:
                        native_mode = "youtube" if shared_native(episode) else mode
                        with Image.open(build / "native" / f"{native_mode}_{sample:05d}.png") as source:
                            native_image = native_panel(episode, mode, source.convert("RGB"))
                        last_native = sample
                    box = FORMATS[mode]["scene"]
                    image.paste(native_image, box[:2])
                process.stdin.write(image.resize((width, height), Image.Resampling.LANCZOS).tobytes())
            process.stdin.close()
            if process.wait():
                raise RuntimeError(f"Encoding failed; see {log.name}.")
        except BaseException:
            stop_processes([process])
            raise
        finally:
            forget_process(process)
    return path


def encoded_highlight_fraction(expected, encoded):
    import numpy as np

    want, got = np.asarray(expected).astype(int), np.asarray(encoded).astype(int)
    mask = (want[:, :, 0] > 170) & (want[:, :, 0] - want[:, :, 1] > 20) & (want[:, :, 1] - want[:, :, 2] > 45)
    # Narrow YUV420 strokes can have G >= R while retaining yellow chroma distinct from white.
    gold = (got[:, :, 0] - got[:, :, 2] > 20) & (got[:, :, 1] - got[:, :, 2] > 10)
    return float(gold[mask].mean()) if mask.any() else 0


def review_export(build, episode, storyboard, timeline, mode):
    import numpy as np
    import wave

    video = build / output_name(episode, mode)
    size = output_sizes(episode)[mode]
    result = run_process([shutil.which("ffprobe"), "-v", "error", "-count_frames", "-show_streams",
                          "-show_format", "-of", "json", video], capture_output=True, check=True)
    media = json.loads(result.stdout)
    stream = next(s for s in media["streams"] if s["codec_type"] == "video")
    if (int(stream["nb_read_frames"]) != timeline["total_frames"]
            or (stream["width"], stream["height"]) != size
            or stream["r_frame_rate"] != f"{timeline['fps']}/1"
            or int(stream["nb_read_frames"]) / timeline["fps"] >= episode["source"]["duration_limit_seconds"]):
        raise ValueError("Encoded preview frame clock or dimensions differ.")
    run_logged([shutil.which("ffmpeg"), "-nostdin", "-v", "error", "-i", video, "-f", "null", "-"],
               build / f"decode_{mode}.log")
    pcm = run_process([shutil.which("ffmpeg"), "-nostdin", "-v", "error", "-i", video, "-vn",
                       "-ac", "1", "-ar", "48000", "-f", "s16le", "pipe:1"],
                      capture_output=True, check=True).stdout
    with wave.open(str(build / "dialogue.wav"), "rb") as wav:
        reference = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(float)
    actual = np.frombuffer(pcm, dtype="<i2").astype(float)
    if abs(len(actual) - len(reference)) > 2048:
        raise ValueError("Encoded audio clock differs.")
    length = min(len(actual), len(reference))
    correlation = float(np.corrcoef(reference[:length], actual[:length])[0, 1])
    if not math.isfinite(correlation) or correlation < .98:
        raise ValueError("Encoded speech is shifted or differs from the measured dialogue.")
    silence = []
    for notice in timeline.get("silent_notices", []):
        first, last = (notice[key] * 48000 // timeline["fps"] for key in ("start_frame", "end_frame"))
        peak = float(np.abs(actual[first:last]).max())
        if peak > 1:
            raise ValueError("Encoded silent notice contains audio.")
        silence.append({"id": notice["id"], "peak_pcm16": peak})
    folder = build / f"review_{mode}"
    folder.mkdir(exist_ok=True)
    samples = {min(timeline["total_frames"] - 1,
                   t["start_frame"] + math.ceil((t["words"][0]["start"] + t["words"][0]["end"]) / 2 * timeline["fps"]))
               for t in timeline["turns"]}
    opening = timeline["turns"][0]
    samples.update(math.ceil((opening["words"][group[0]]["start"] +
                              opening["words"][group[-1]]["end"]) * timeline["fps"] / 2)
                   for group in episode["turns"][0]["display_word_groups"])
    first_group = episode["turns"][0]["display_word_groups"][0]
    onset = math.ceil(opening["words"][first_group[0]]["start"] * timeline["fps"])
    offset = math.ceil(opening["words"][first_group[-1]]["end"] * timeline["fps"])
    samples.update(f for f in (max(0, onset - 1), onset, offset - 1, offset) if f < timeline["total_frames"])
    samples.add(timeline["total_frames"] - 1)
    if is_production(episode):
        for turn in timeline["turns"]:
            for word in caption_words(turn):
                if turn["kind"] == "opening" or any(c.isdigit() for c in word["word"]) or word["word"] == "+":
                    first = turn["start_frame"] + math.ceil(word["start"] * timeline["fps"])
                    last = turn["start_frame"] + math.ceil(word["end"] * timeline["fps"]) - 1
                    if first > last:
                        raise ValueError("An aligned display word has no encoded highlight frame.")
                    samples.update(f for f in (max(0, first - 1), first, (first + last) // 2, last, last + 1)
                                   if f < timeline["total_frames"])
        for notice in timeline.get("silent_notices", []):
            samples.update((notice["start_frame"] - 1, notice["start_frame"],
                            (notice["start_frame"] + notice["end_frame"]) // 2,
                            notice["end_frame"] - 1, notice["end_frame"]))
    samples = sorted(samples)
    select = "+".join(f"eq(n\\,{frame})" for frame in samples)
    run_logged([shutil.which("ffmpeg"), "-nostdin", "-v", "error", "-y", "-i", video,
                "-vf", f"select={select}", "-fps_mode", "vfr", folder / "frame_%03d.png"],
               build / f"review_{mode}.log")
    checks = []
    for index, frame in enumerate(samples, 1):
        expected, check = overlay(episode, storyboard, timeline, mode, frame)
        with Image.open(folder / f"frame_{index:03d}.png") as encoded:
            check["encoded_file"] = str((folder / f"frame_{index:03d}.png").resolve())
            expected = expected.resize(size, Image.Resampling.LANCZOS)
            for text in check["text"]:
                if "highlighted_word" not in text:
                    continue
                scale = size[0] / FORMATS[mode]["size"][0]
                box = tuple(round(v * scale) for v in text["box"])
                fraction = encoded_highlight_fraction(expected.crop(box), encoded.crop(box))
                if fraction < .6:
                    raise ValueError(f"Missing encoded word highlight: {text['highlighted_word']}.")
                text["encoded_highlight_fraction"] = fraction
            if check.get("silent"):
                error = float(np.abs(np.asarray(expected).astype(float) -
                                     np.asarray(encoded).astype(float)).mean())
                if error > 3:
                    raise ValueError("Encoded notice differs from the approved screen.")
                check["encoded_mean_pixel_error"] = error
            checks.append(check)
    columns, thumb = 4, (320, 180) if mode == "youtube" else (180, 320)
    sheet = Image.new("RGB", (columns * thumb[0], math.ceil(len(samples) / columns) * thumb[1]), PANEL)
    for index, check in enumerate(checks):
        with Image.open(check["encoded_file"]) as frame:
            sheet.paste(frame.resize(thumb), ((index % columns) * thumb[0], (index // columns) * thumb[1]))
    sheet.save(build / f"{'production' if is_production(episode) else 'preview'}_contact_{mode}.jpg", quality=94)
    return {"media": media, "audio_correlation": correlation, "samples": checks,
            "encoded_frame_clock_seconds": timeline["total_frames"] / timeline["fps"],
            "silent_notices": silence, "sha256": sha256_file(video)}


@generation_job
def build_preview(path, output, jobs=4, until="export", speech_cache_from=None, *,
                  profile="preview", reuse_audio=None, reuse_scene=None, render_device="CPU"):
    from pipeline import run_command

    episode, storyboard = load_preview(path, profile)
    production = is_production(episode)
    if not production and (reuse_audio or reuse_scene or render_device != "CPU"):
        raise ValueError("Previews support CPU rendering without exact audio reuse.")
    if production and speech_cache_from:
        raise ValueError("Production requires exact --reuse-audio, not --speech-cache-from.")
    episode["render_device"] = render_device
    build = build_directory(output)
    assets = [Path(path).resolve(), Path(episode["storyboard"]), Path(episode["scene"]["base_scene"]),
              Path(storyboard["source"]["book"]), Path(storyboard["source"]["manifest"]),
              Path(storyboard["parts"][1]["picture"]), Path(storyboard["promotion"]["cover"]),
              Path(storyboard["promotion"]["pointing_emoji"]), Path(storyboard["scene"]["wall_logo"]),
              font_path(), font_path(True)]
    assets += [Path(v[k]) for v in episode["voices"].values() for k in ("audio", "transcript")]
    if production or episode.get("template") == "long_speaking_full_preview":
        assets += [Path(episode["review_script"]), Path(episode["review_manifest"]),
                   Path(episode["review_manifest"]).parent / "teil1_revision.json"]
    reuse = scene_reuse = None
    if production:
        from long_speaking_production import production_inputs, production_reuse_spec
        reuse = production_reuse_spec(episode, reuse_audio)
        for source in (Path(reuse["source"]), Path(reuse["approved_preview"])):
            if build == source or build.is_relative_to(source) or source.is_relative_to(build):
                raise ValueError("Production output must be separate from both verified source builds.")
        assets += production_inputs(episode, reuse)
        if reuse_scene:
            from long_speaking_production import production_scene_reuse_spec
            source = build_directory(reuse_scene)
            if build == source or build.is_relative_to(source) or source.is_relative_to(build):
                raise ValueError("Production output must be separate from the baked scene source.")
            scene_reuse = production_scene_reuse_spec(episode, storyboard, reuse, source)
            assets += [Path(scene_reuse["source"]) / name for name in scene_reuse["files_sha256"]]
            assets += [Path(name) for name in scene_reuse["assets_sha256"]]
    spec = {"episode": episode, "code_sha256": {name: sha256_file(ROOT / name) for name in SOURCES},
            "asset_sha256": {str(p): sha256_file(p) for p in assets}}
    if production:
        spec["audio_reuse"] = reuse
    if scene_reuse:
        spec["scene_reuse"] = scene_reuse
    state_path = build / ("production_state.json" if production else "preview_state.json")
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state["spec"] != spec:
            raise ValueError("Preview settings/inputs changed; use a fresh build directory.")
    else:
        if build.exists() and any(build.iterdir()):
            raise ValueError("Preview needs a fresh dedicated build directory.")
        build.mkdir(parents=True, exist_ok=True)
        state = {"spec": spec, "stages": {}}
        atomic_json(state_path, state)
        atomic_json(build / "episode.json", episode)
        atomic_json(build / "storyboard_episode.json", storyboard)
    snapshot = build / "source_export"
    snapshot.mkdir(exist_ok=True)
    for name, digest in spec["code_sha256"].items():
        target = snapshot / name
        if target.exists():
            if sha256_file(target) != digest:
                raise ValueError("Generation snapshot differs; use a fresh build.")
        else:
            shutil.copy2(ROOT / name, target)
    python, blender = sys.executable, tool_path("blender")

    def stage(name, action, outputs):
        previous = state["stages"].get(name, {})
        if previous and all((build / p).is_file() and sha256_file(build / p) == digest
                            for p, digest in previous.items()):
            print(f"{name}: verified checkpoint", flush=True)
            return
        print(f"{name}: running", flush=True)
        action()
        state["stages"][name] = {str(p): sha256_file(build / p) for p in outputs}
        atomic_json(state_path, state)
        stage_completed(name, force=True)

    if production:
        from long_speaking_production import prepare_production_audio
        stage("audio_reuse", lambda: prepare_production_audio(build, episode, reuse),
              ["dialogue.wav", "timeline.json", "word_alignment.json", "audio_reuse.json",
               "speech_asr_check.json", "auditory_review_flags.json", "subtitles.srt"])
    else:
        command = [python, ROOT / "prepare_audio.py", "--episode", build / "episode.json",
                   "--output-dir", build, "--threads", "8", "--device", "cpu"]
        if speech_cache_from:
            command += ["--speech-cache-from", build_directory(speech_cache_from)]
        stage("audio", lambda: run_command(command, build / "audio.log"),
              ["episode.json", "dialogue.wav", "audio_timeline.json", "subtitles.srt"])
        stage("alignment", lambda: run_command([python, ROOT / "align_words.py", "--build", build],
                                               build / "alignment.log"), ["timeline.json", "word_alignment.json"])
    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    check_timeline(episode, timeline)
    for turn in timeline["turns"]:
        validate_words(turn["words"], turn["text"], turn["wav_duration"])
    caption_preflight(build, episode, storyboard, timeline)
    if not production:
        from check_speech import check_speech
        stage("speech_check", lambda: check_speech(build), ["speech_asr_check.json"])
    atomic_json(build / "native_plan.json", native_plan(episode, storyboard, timeline))
    if until == "audio":
        return build
    native_command = [blender, "-b", episode["scene"]["base_scene"], "--disable-autoexec", "-t", "4",
                      "--python-exit-code", "1", "--python", ROOT / "long_speaking_preview_scene.py",
                      "--", "--build", build]
    if scene_reuse:
        from long_speaking_production import prepare_reused_scene
        stage("scene", lambda: prepare_reused_scene(build, scene_reuse),
              ["preview.blend", "scene_checks.json", "scene_reuse.json"])
    else:
        stage("scene", lambda: run_command(native_command + ["--bake"], build / "scene.log"),
              ["preview.blend", "scene_checks.json"])
    if until == "scene":
        return build

    def frames():
        def worker(index):
            command = [blender, "-b", build / "preview.blend", "--disable-autoexec", "-t", "4",
                       "--python-exit-code", "1",
                       "--python-expr", f"import bpy; bpy.context.scene.cycles.samples = {episode['render']['samples']}; "
                                        "bpy.context.scene.cycles.use_denoising = True",
                       "--python", ROOT / "long_speaking_preview_scene.py",
                       "--", "--build", build, "--worker", str(index), "--jobs", str(jobs)]
            run_command(command, build / f"frames_{index}.log")
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            list(pool.map(worker, range(jobs)))
        plan = json.loads((build / "native_plan.json").read_text(encoding="utf-8"))
        receipts = [record for index in range(jobs)
                    for record in json.loads((build / f"native_checks_{index}.json").read_text(encoding="utf-8"))]
        if len(receipts) != len(plan) or any(sha256_file(build / r["file"]) != r["sha256"] for r in receipts):
            raise ValueError("Native frame receipts are incomplete.")
        atomic_json(build / "native_checks.json", receipts)

    planned = json.loads((build / "native_plan.json").read_text(encoding="utf-8"))
    stage("frames", frames, ["native_checks.json", *[item["file"] for item in planned]])
    for name, digest in spec["code_sha256"].items():
        if sha256_file(ROOT / name) != digest:
            raise ValueError("Preview implementation changed during generation; use a fresh build.")
    for name, digest in spec["asset_sha256"].items():
        if sha256_file(Path(name)) != digest:
            raise ValueError("A preview source changed during generation.")
    for mode in OUTPUTS:
        stage("encode_" + mode, lambda mode=mode: encode(build, episode, storyboard, timeline, mode),
              [output_name(episode, mode)])
    report = {mode: review_export(build, episode, storyboard, timeline, mode) for mode in OUTPUTS}
    speech = json.loads((build / "speech_asr_check.json").read_text(encoding="utf-8"))
    if (any(sha256_file(ROOT / name) != digest for name, digest in spec["code_sha256"].items())
            or any(sha256_file(Path(name)) != digest for name, digest in spec["asset_sha256"].items())):
        raise ValueError("Preview inputs changed before delivery.")
    atomic_json(build / "delivery_checks.json", {
        "status": "production" if production else "preview_only",
        "exports": report, "speech_asr_all_match": speech["all_match"],
        "render": episode["render"],
        "native_formats": ["youtube"] if shared_native(episode) else list(OUTPUTS),
        "social_scene_transform": "fixed_center_crop" if shared_native(episode) else "native_render",
        "voice_cast": episode["voices"], "source_sha256": spec,
        "audio_reuse": reuse, "scene_reuse": scene_reuse, "human_listening_performed": False,
        "limitations": ("Full-resolution output from approved 8-sample YouTube scene images on twos; "
                        "social uses a fixed center crop, without a second speaker-centering guard. "
                        "Inherited speech and reading flags remain for human review; no publication approval."
                        if shared_native(episode) else
                        "Full-resolution, per-frame production render using the established production sample count. "
                        "Inherited speech and reading flags remain for human review; no publication approval."
                        if production else
                        "Reduced-resolution CPU rehearsal at eight native poses/second. Independent ASR and forced alignment are not human listening or an accent guarantee. Not a complete exam or publication approval."),
    })
    snapshot = build / "source_export"
    snapshot.mkdir(exist_ok=True)
    for name in SOURCES:
        shutil.copy2(ROOT / name, snapshot / name)
    selected = [p for p in build.iterdir() if p.is_file() and p.suffix in (".json", ".wav", ".srt", ".mp4", ".jpg", ".blend")]
    selected += [p for folder in ("source_export", "review_youtube", "review_social")
                 for p in (build / folder).rglob("*") if p.is_file()]
    atomic_json(build / "export_manifest.json", {
        "files_sha256": {str(p.relative_to(build)): sha256_file(p)
                         for p in selected if p.name != "export_manifest.json"},
        "generation_source_sha256": spec["code_sha256"],
    })
    print(f"{'Production' if production else 'Preview'} ready: {build}", flush=True)
    return build
