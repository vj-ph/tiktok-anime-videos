"""Five portrait speaking excerpts with exact source dialogue and measured new openings."""

import argparse
import copy
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from align_words import validate_words
from build_paths import build_directory
from generation_runtime import generation_job, run_process
from pipeline import run_command
from prepare_audio import atomic_json, sha256_file, subtitles
from render import valid_frame
from runtime_config import font_path
from social_captions import readable_pages
from tef_speaking_preview import BG, GOLD, WHITE, active_on_frame, current_turn, draw_words, notice_countdown

ROOT = Path(__file__).resolve().parent
SIZE = (1080, 1920)
ROOM = (90, 480, 930, 900)
CAPTIONS = (100, 960, 930, 1260)
SOURCES = ("derive_tef_speaking_social.py", "tef_speaking_preview.py", "social_captions.py",
           "align_words.py", "prepare_audio.py", "check_speech.py", "pipeline.py",
           "runtime_config.py", "generation_runtime.py", "episode_config.py",
           "episode_profiles.py", "build_paths.py", "render.py")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_hashes(folder, hashes):
    for name, digest in hashes.items():
        if sha256_file(Path(folder) / name) != digest:
            raise ValueError(f"Frozen input changed: {name}")


def verify_source(source, digest):
    if sha256_file(source / "export_manifest.json") != digest:
        raise ValueError("The selected TEF production manifest changed.")
    manifest = read(source / "export_manifest.json")
    verify_hashes(source, manifest["files_sha256"])
    verify_hashes(source / "source_export", manifest["source_sha256"])
    episode, timeline = read(source / "episode.json"), read(source / "timeline.json")
    report, scene = read(source / "delivery_checks.json"), read(source / "scene_manifest.json")
    if (episode["template"] != "tef_speaking_full_production" or manifest["preview_only"]
            or report["preview_only"] or not report["encoded_checks"]
            or episode.get("speech_tempo", 1) != 1
            or (scene["width"], scene["height"], scene["motion_step"], scene["samples"])
            != (1280, 640, 2, 8) or scene["timeline"] != timeline):
        raise ValueError("Use the completed full-resolution 1.0x TEF speaking production.")
    checks = read(source / "scene_checks.json")
    if (sha256_file(source / "studio.blend") != checks["blend_sha256"]
            or read(source / "frames_manifest.json")["scene"] != scene
            or not checks["all_sampled_heads_and_hair_fit"] or not checks["hair_hangs_down"]):
        raise ValueError("Source native scene checks differ.")
    for frame in range(1, timeline["total_frames"] + 1, 2):
        if not valid_frame(source / "frames" / f"frame_{frame:04d}.png", 1280, 640):
            raise ValueError(f"Missing or incomplete native source frame {frame}.")
    return episode, timeline


def speech_episode(original, config):
    episode = copy.deepcopy(original)
    episode.update(id=config["id"] + "_openings", intro_seconds=0, outro_seconds=0)
    episode["source"].update(duration_limit_seconds=180, duration_exception=config["duration_exception"])
    episode["turns"] = []
    for index, clip in enumerate(config["clips"], 1):
        for kind, text in (("opening", clip["title"]), ("setup", clip["context"])):
            episode["turns"].append({
                "id": f"{kind}_{index}", "name": f"Partie {index} - {kind}",
                "kind": kind, "speaker": "candidate_a", "text": text,
                "phase": "dialogue", "section": clip["section"], "camera": "candidate_a",
                "pause_after": .5, "caption_hold_seconds": .5,
            })
    return episode


def edit_clip(original, wrappers, clip, index):
    fps = original["fps"]
    if fps != 24:
        raise ValueError("Expected the source 24-fps frame clock.")
    ids = [t["id"] for t in original["turns"]]
    first, last = ids.index(clip["first"]), ids.index(clip["last"])
    if first > last or original["turns"][first]["section"] != clip["section"]:
        raise ValueError("Select consecutive complete dialogue turns in one section.")
    plans = [
        (wrappers, [t for t in wrappers["turns"] if t["id"] in (f"opening_{index}", f"setup_{index}")], "speech"),
        (original, original["turns"][first:last + 1], "production"),
        (original, [original["turns"][-1]], "production"),
    ]
    turns, edits, cursor = [], [], 0
    for timeline, selected, source in plans:
        stops = {t["id"]: timeline["turns"][i + 1]["start_frame"]
                 if i + 1 < len(timeline["turns"]) else timeline["total_frames"]
                 for i, t in enumerate(timeline["turns"])}
        for item in selected:
            turn = copy.deepcopy(item)
            start, end = item["start_frame"], stops[item["id"]]
            if end < item["end_frame"] or start >= end:
                raise ValueError("An edit would truncate source speech.")
            shift = cursor - start
            turn.update(source_frame=start, source_kind=source)
            for key in ("start_frame", "end_frame"):
                turn[key] += shift
            for key in ("start", "end"):
                turn[key] += shift / fps
            turn["pause_after_frames"] = end - item["end_frame"]
            turn["pause_after_seconds"] = turn["pause_after_frames"] / fps
            validate_words(turn["words"], turn["text"], turn["wav_duration"])
            turns.append(turn)
            edits.append({"id": turn["id"], "source_kind": source, "source_start": start,
                          "source_end": end, "output_start": cursor, "output_end": cursor + end - start})
            cursor += end - start
    if cursor >= 180 * fps:
        raise ValueError(f"{clip['id']} is {cursor / fps:.3f}s; it must be strictly below 180s.")
    result = {"fps": fps, "total_frames": cursor, "duration": cursor / fps, "turns": turns,
              "language": "fr", "word_alignment": {"source_exact_local_words": True,
                  "new_openings_provenance": wrappers["word_alignment"],
                  "production_provenance": original["word_alignment"]}}
    return result, edits


def pages_for(timeline):
    pages = []
    for index, turn in enumerate(timeline["turns"]):
        end = (timeline["turns"][index + 1]["start"] if index + 1 < len(timeline["turns"])
               else timeline["duration"])
        if turn["kind"] == "notice":
            end = turn["end"]
        groups = readable_pages(turn["words"], turn["start"], end, 24, width=830, size=36)
        pages.extend({**p, "turn_start": turn["start"], "turn_id": turn["id"]} for p in groups)
    return pages


def audio_chunks(source, speech, edits):
    pcm = {}
    for name, folder in (("production", source), ("speech", speech)):
        with wave.open(str(folder / "dialogue.wav"), "rb") as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 48000):
                raise ValueError("Expected 48kHz mono PCM16.")
            pcm[name] = wav.readframes(wav.getnframes())
    return b"".join(pcm[e["source_kind"]][e["source_start"] * 4000:e["source_end"] * 4000] for e in edits)


def native_frame(turn, frame):
    if turn["source_kind"] == "speech":
        return 1
    requested = turn["source_frame"] + frame - turn["start_frame"]
    return 1 + requested // 2 * 2


def compose(episode, timeline, pages, frame, native):
    image = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(image)
    font = lambda size: ImageFont.truetype(str(font_path(True)), size)
    draw.text((100, 110), "FRENCH COMPASS", font=font(27), fill=GOLD)
    draw.text((100, 160), f"Partie {episode['part']} / 5 · Section {episode['section']}",
              font=font(30), fill=WHITE)
    turn = current_turn(timeline, frame)
    opening = timeline["turns"][0]
    active = active_on_frame(opening["words"], opening["start"], frame, 24)
    draw_words(draw, episode["title"].split(), (100, 235, 930, 420), size=48, active=active)
    draw.rounded_rectangle(ROOM, radius=18, fill="#223842")
    if turn["kind"] == "notice":
        with Image.open(episode["notices"][turn["section"]]) as notice:
            fitted = ImageOps.contain(notice.convert("RGB"), (840, 420), Image.Resampling.LANCZOS)
        image.paste(fitted, (90 + (840 - fitted.width) // 2, 480 + (420 - fitted.height) // 2))
    elif turn["kind"] == "cta":
        draw_words(draw, "À vous de parler !".split(), (125, 545, 895, 645), size=48, color=GOLD)
        draw_words(draw, "Plus de tâches et de dialogues modèles dans notre livre TEF Canada.".split(),
                   (125, 665, 895, 870), size=38)
    else:
        if native.size != (1280, 640):
            raise ValueError("Only complete native production images can be used.")
        image.paste(native.resize((840, 420), Image.Resampling.LANCZOS), ROOM[:2])
    reading = notice_countdown(turn, frame, 24)
    if reading:
        seconds, fraction = reading
        draw.text((115, 985), f"Temps de lecture : {seconds} s", font=font(38), fill=WHITE)
        draw.rounded_rectangle((115, 1060, 910, 1080), radius=10, fill="#38505a")
        draw.rectangle((115, 1060, 115 + max(1, round(795 * fraction)) - 1, 1080), fill=GOLD)
    else:
        page = next((p for p in pages if p["start"] <= frame / 24 < p["end"]), None)
        if page:
            active = active_on_frame(page["words"], page["turn_start"], frame, 24)
            draw_words(draw, [w["word"] for w in page["words"]], CAPTIONS, size=36, active=active)
    draw.rounded_rectangle((100, 1300, 930, 1560), radius=20, fill="#223842")
    with Image.open(episode["cover"]) as cover:
        fitted = ImageOps.contain(cover.convert("RGB"), (150, 220), Image.Resampling.LANCZOS)
    image.paste(fitted, (115 + (150 - fitted.width) // 2, 1320 + (220 - fitted.height) // 2))
    draw_words(draw, "Livre disponible sur Amazon".split(), (295, 1330, 905, 1440),
               size=34, color=GOLD)
    draw.text((295, 1447), "Lien en bio / description", font=font(27), fill=WHITE)
    draw.text((295, 1496), episode["visible_url"], font=font(32), fill=WHITE)
    draw.text((100, 1590), "Entraînement guidé indépendant · Voix IA", font=font(20), fill="#aabac1")
    return image


def expected_image(source, episode, timeline, pages, frame):
    turn = current_turn(timeline, frame)
    path = source / "frames" / f"frame_{native_frame(turn, frame):04d}.png"
    with Image.open(path) as native:
        return compose(episode, timeline, pages, frame, native.convert("RGB"))


def sample_frames(timeline, pages):
    frames = {0, timeline["total_frames"] - 1}
    for turn in timeline["turns"]:
        for boundary in (turn["start_frame"], turn["end_frame"]):
            frames.update((max(0, boundary - 1), min(timeline["total_frames"] - 1, boundary)))
        if turn["kind"] in ("opening", "setup", "cta"):
            for word in turn["words"]:
                frames.add(min(timeline["total_frames"] - 1,
                               int((turn["start"] + (word["start"] + word["end"]) / 2) * 24)))
        if turn["kind"] == "notice":
            for boundary in range(turn["end_frame"], turn["end_frame"] + turn["pause_after_frames"] + 1, 24):
                frames.update((boundary - 1, boundary))
    frames.update(round((page["start"] + page["end"]) * 12) for page in pages)
    return sorted(f for f in frames if 0 <= f < timeline["total_frames"])


def sheets(folder, frames, images, prefix):
    for first in range(0, len(frames), 12):
        group = frames[first:first + 12]
        sheet = Image.new("RGB", (1080, math.ceil(len(group) / 4) * 505), BG)
        draw = ImageDraw.Draw(sheet)
        for index, frame in enumerate(group):
            x, y = index % 4 * 270, index // 4 * 505
            sheet.paste(images(frame).resize((270, 480)), (x, y))
            draw.text((x + 6, y + 483), f"{frame/24:.3f}s / {frame}", fill=WHITE)
        sheet.save(folder / f"{prefix}_{first // 12 + 1:02d}.jpg", quality=94)


def encode(source, folder, episode, timeline, pages):
    target = folder / "production_social.mp4"
    command = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", "1080x1920", "-r", "24", "-i", "pipe:0", "-i", str(folder / "dialogue.wav"),
               "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-t", str(timeline["duration"]),
               "-movflags", "+faststart", str(target)]
    with (folder / "encode.log").open("w") as log:
        with subprocess.Popen(command, stdin=subprocess.PIPE, stderr=log) as encoder:
            try:
                for frame in range(timeline["total_frames"]):
                    encoder.stdin.write(expected_image(source, episode, timeline, pages, frame).tobytes())
                    if frame % 720 == 0:
                        print(f"{episode['id']}: encoded {frame}/{timeline['total_frames']} frames", flush=True)
                encoder.stdin.close()
                if encoder.wait():
                    raise RuntimeError(f"Encoding failed: {folder / 'encode.log'}")
            except BaseException:
                encoder.kill()
                encoder.wait()
                raise


def review(source, folder, episode, timeline, pages):
    video = folder / "production_social.mp4"
    media = json.loads(run_process(["ffprobe", "-v", "error", "-count_frames", "-show_streams",
        "-show_format", "-of", "json", video], capture_output=True, check=True).stdout)
    stream = next(s for s in media["streams"] if s["codec_type"] == "video")
    if ((stream["width"], stream["height"]) != SIZE or stream["r_frame_rate"] != "24/1"
            or int(stream["nb_read_frames"]) != timeline["total_frames"]
            or float(media["format"]["duration"]) >= 180):
        raise ValueError("Encoded portrait size, frame clock or strict duration failed.")
    run_process(["ffmpeg", "-nostdin", "-v", "error", "-i", video, "-f", "null", "-"], check=True)
    actual = np.frombuffer(run_process(["ffmpeg", "-nostdin", "-v", "error", "-i", video, "-vn",
        "-ac", "1", "-ar", "48000", "-f", "s16le", "pipe:1"], capture_output=True, check=True).stdout,
        dtype="<i2").astype(float)
    with wave.open(str(folder / "dialogue.wav"), "rb") as wav:
        reference = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(float)
    count = min(len(actual), len(reference))
    correlation = float(np.corrcoef(actual[:count], reference[:count])[0, 1])
    if abs(len(actual) - len(reference)) > 2048 or not math.isfinite(correlation) or correlation < .98:
        raise ValueError("Encoded audio differs or is shifted.")
    silences = []
    for turn in timeline["turns"]:
        if turn["kind"] == "notice":
            left = turn["end_frame"] * 2000 + 2048
            right = (turn["end_frame"] + turn["pause_after_frames"]) * 2000 - 2048
            peak = float(np.max(np.abs(actual[left:right])))
            if np.any(reference[left:right]) or peak > 1 or turn["pause_after_frames"] != 192:
                raise ValueError("The complete eight-second reading silence was not preserved.")
            silences.append({"id": turn["id"], "seconds": 8, "encoded_guarded_peak_pcm16": peak})
    frames = sample_frames(timeline, pages)
    captures = folder / "review"
    captures.mkdir(exist_ok=True)
    select = "+".join(f"eq(n\\,{f})" for f in frames)
    run_process(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", video, "-vf", f"select={select}",
                 "-fps_mode", "vfr", captures / "sample_%04d.png"], check=True)
    checks = []
    for index, frame in enumerate(frames, 1):
        expected = expected_image(source, episode, timeline, pages, frame)
        with Image.open(captures / f"sample_{index:04d}.png") as image:
            decoded = image.convert("RGB")
        errors = {}
        for name, box in (("full", (0, 0, *SIZE)), ("captions", CAPTIONS),
                          ("promotion", (100, 1300, 930, 1560)), ("title", (100, 235, 930, 420))):
            error = float(np.abs(np.asarray(decoded.crop(box)).astype(float)
                                 - np.asarray(expected.crop(box)).astype(float)).mean())
            if error > 8:
                raise ValueError(f"Encoded {name} mismatch at frame {frame}: {error}")
            errors[name] = error
        decoded.save(captures / f"frame_{frame:05d}.png")
        checks.append({"frame": frame, "errors": errors})
    sheets(folder, frames, lambda f: Image.open(captures / f"frame_{f:05d}.png"), "contact_encoded")
    atomic_json(folder / "delivery_checks.json", {"media": media, "audio_correlation": correlation,
        "encoded_checks": checks, "reading_silences": silences, "human_listening": False,
        "publication_approved": False})


def prepare(source, speech, folder, original, source_timeline, wrappers, clip, index):
    folder.mkdir(exist_ok=True)
    timeline, edits = edit_clip(source_timeline, wrappers, clip, index)
    episode = {**clip, "part": index, "cover": str(source / "book_cover.jpg"),
               "notices": {s: str(source / f"notice_{s}.jpg") for s in ("A", "B")},
               "visible_url": original["promotion"]["visible_url"]}
    pages = pages_for(timeline)
    pcm = audio_chunks(source, speech, edits)
    if len(pcm) != timeline["total_frames"] * 4000:
        raise ValueError("Edited samples do not match the complete output frame clock.")
    with wave.open(str(folder / "dialogue.wav"), "wb") as wav:
        wav.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        wav.writeframes(pcm)
    atomic_json(folder / "episode.json", episode)
    atomic_json(folder / "timeline.json", timeline)
    atomic_json(folder / "edit_decisions.json", edits)
    atomic_json(folder / "caption_pages.json", pages)
    atomic_json(folder / "word_alignment.json", {"provenance": timeline["word_alignment"],
        "turns": [{"id": t["id"], "start": t["start"], "words": t["words"]} for t in timeline["turns"]]})
    (folder / "subtitles.srt").write_text(subtitles(timeline), encoding="utf-8")
    hashes = {}
    for turn in timeline["turns"]:
        stop = next((t["start_frame"] for t in timeline["turns"] if t["start_frame"] > turn["start_frame"]),
                    timeline["total_frames"])
        for frame in range(turn["start_frame"], stop):
            name = f"frames/frame_{native_frame(turn, frame):04d}.png"
            if name not in hashes:
                hashes[name] = sha256_file(source / name)
    atomic_json(folder / "native_reuse.json", {"source": str(source), "files_sha256": hashes,
        "full_native_image_contained_not_cropped": True, "source_frame_clock_preserved": True})
    for frame in sample_frames(timeline, pages):
        expected_image(source, episode, timeline, pages, frame)
    previews = [0, timeline["turns"][2]["start_frame"], timeline["turns"][-1]["start_frame"]]
    for turn in timeline["turns"]:
        if turn["kind"] == "notice":
            previews.extend([turn["end_frame"], turn["end_frame"] + 96, turn["end_frame"] + 191])
    sheets(folder, previews, lambda f: expected_image(source, episode, timeline, pages, f), "contact_native")
    expected_image(source, episode, timeline, pages, 0).save(folder / "opening.png")
    return episode, timeline, pages


@generation_job
def build(config_path, destination, until="export"):
    config_path = Path(config_path).resolve(strict=True)
    config = read(config_path)
    if (config["template"] != "tef_speaking_social_five" or config["duration_limit_seconds"] != 180
            or len(config["clips"]) != 5 or not config["duration_exception"]):
        raise ValueError("Expected the approved five-part under-180-second edit.")
    source = (config_path.parent / config["source"].replace("\\", os.sep)).resolve(strict=True)
    destination = build_directory(destination)
    if destination == source or source in destination.parents or destination in source.parents:
        raise ValueError("Preserve the full delivery in a separate build.")
    original, source_timeline = verify_source(source, config["source_manifest_sha256"])
    source_ids = [t["id"] for t in source_timeline["turns"]]
    selected = [t["id"] for clip in config["clips"] for t in source_timeline["turns"][
        source_ids.index(clip["first"]):source_ids.index(clip["last"]) + 1] if t["kind"] == "model"]
    if selected != [t["id"] for t in source_timeline["turns"] if t["kind"] == "model"]:
        raise ValueError("The five parts must preserve every model turn exactly once in order.")
    spec = {"config": config, "code_sha256": {n: sha256_file(ROOT / n) for n in SOURCES},
            "fonts": {str(font_path(b)): sha256_file(font_path(b)) for b in (False, True)}}
    state_path = destination / "shorts_state.json"
    if state_path.exists():
        state = read(state_path)
        if state["spec"] != spec:
            raise ValueError("Derivative code/inputs changed; use a fresh build.")
    else:
        if destination.exists() and any(destination.iterdir()):
            raise ValueError("Use a fresh derivative build.")
        destination.mkdir(parents=True, exist_ok=True)
        state = {"spec": spec, "exports": {}}
        atomic_json(state_path, state)
        snapshot = destination / "source_export"
        snapshot.mkdir()
        for name in SOURCES:
            shutil.copy2(ROOT / name, snapshot / name)
    speech = destination / "speech"
    speech.mkdir(exist_ok=True)
    episode_path = speech / "authoring_episode.json"
    if "speech_sha256" not in state:
        atomic_json(episode_path, speech_episode(original, config))
        run_command([sys.executable, ROOT / "prepare_audio.py", "--episode", episode_path,
                     "--output-dir", speech, "--threads", "8"], speech / "prepare.log")
        run_command([sys.executable, ROOT / "align_words.py", "--build", speech], speech / "align.log")
        result = run_process([sys.executable, ROOT / "check_speech.py", "--build", speech], capture_output=True)
        (speech / "asr.log").write_bytes(result.stdout + result.stderr)
        if not (speech / "speech_asr_check.json").exists():
            raise ValueError("New opening ASR report is missing.")
        state["speech_sha256"] = {n: sha256_file(speech / n) for n in
            ("dialogue.wav", "timeline.json", "word_alignment.json", "speech_asr_check.json")}
        atomic_json(state_path, state)
    verify_hashes(speech, state["speech_sha256"])
    if until == "audio":
        return destination
    wrappers = read(speech / "timeline.json")
    source_models = [t["id"] for t in source_timeline["turns"] if t["kind"] == "model"]
    selected_models, summaries = [], []
    for index, clip in enumerate(config["clips"], 1):
        folder = destination / clip["id"]
        episode, timeline, pages = prepare(source, speech, folder, original, source_timeline, wrappers, clip, index)
        selected_models += [t["id"] for t in timeline["turns"] if t["kind"] == "model"]
        summaries.append({"id": clip["id"], "seconds": timeline["duration"], "frames": timeline["total_frames"],
                          "output": str(folder / "production_social.mp4")})
        print(f"{clip['id']}: {timeline['duration']:.3f}s", flush=True)
        if until == "export":
            if clip["id"] in state["exports"]:
                verify_hashes(folder, state["exports"][clip["id"]])
            else:
                encode(source, folder, episode, timeline, pages)
                review(source, folder, episode, timeline, pages)
                verify_hashes(source, read(folder / "native_reuse.json")["files_sha256"])
                state["exports"][clip["id"]] = {p.name: sha256_file(p) for p in folder.iterdir() if p.is_file()}
                atomic_json(state_path, state)
    if selected_models != source_models:
        raise ValueError("The five parts must preserve every model turn exactly once in order.")
    atomic_json(destination / "shorts_summary.json", summaries)
    verify_source(source, config["source_manifest_sha256"])
    verify_hashes(ROOT, spec["code_sha256"])
    if until == "export":
        atomic_json(destination / "export_manifest.json", {
            "source_manifest_sha256": config["source_manifest_sha256"],
            "files_sha256": {str(p.relative_to(destination)): sha256_file(p)
                for p in destination.rglob("*") if p.is_file() and
                p.name != "export_manifest.json" and
                (p.parent == destination or p.parent.name in [c["id"] for c in config["clips"]])},
            "source_sha256": spec["code_sha256"], "all_five_under_180_seconds": True,
            "human_listening": False, "publication_approved": False})
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", required=True, type=Path)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--until", choices=("audio", "scene", "export"), default="export")
    args = parser.parse_args()
    build(args.episode, args.build, args.until)
