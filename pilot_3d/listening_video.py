"""DTZ listening challenge: original audio, response time and voiced reveal."""

import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from build_paths import build_directory, resolve_build_reference
from episode_config import PROFILES
from generation_runtime import generation_job, run_process, stage_completed
from prepare_audio import (MODEL, atomic_json, ceil_frames, content_hash, inspect_wav,
                           make_cache_payload, sha256_file, synthesize, wav_frames_to_video_frames)
from runtime_config import font_path, tool_path

ROOT = Path(__file__).resolve().parent
WIDTH, HEIGHT = 720, 1280


def render_settings(profile):
    if profile not in PROFILES:
        raise ValueError(f"Unknown listening profile: {profile}")
    settings = PROFILES[profile]
    if profile == "production":
        if (settings["width"], settings["height"]) != (WIDTH, HEIGHT):
            raise ValueError("Listening production crop requires a 720x1280 production profile.")
        # Render the whole zoomed camera frame at native pixels before the existing crop.
        return {"width": settings["width"] + 72, "height": settings["height"] + 128,
                "samples": settings["samples"]}
    return {key: settings[key] for key in ("width", "height", "samples")}


def load_episode(path):
    path = Path(path).resolve(strict=True)
    episode = json.loads(path.read_text(encoding="utf-8"))
    exam = episode.get("exam")
    if (episode.get("schema_version") != 1 or episode.get("language") != "de"
            or not isinstance(exam, dict) or set(exam) != {"family", "skill", "section"}
            or exam["family"] != "dtz" or exam["skill"] != "listening"
            or exam["section"] not in ("1", "2", "3", "4")):
        raise ValueError("This listening template supports DTZ German Teile 1–4 only.")
    if episode.get("fps") != 24:
        raise ValueError("Listening video requires 24 fps.")
    for field in ("id", "title", "question", "answer_text", "key_detail"):
        if not isinstance(episode.get(field), str) or not episode[field].strip():
            raise ValueError(f"{field} must be nonempty text.")
    def validate_choices(item, count):
        choices = item.get("choices")
        if not isinstance(choices, list) or len(choices) != count or any(
                not isinstance(choice, str) or not choice.strip() for choice in choices):
            raise ValueError(f"choices must contain {count} nonempty answers.")
        if item.get("correct_choice") not in tuple(chr(65 + i) for i in range(count)):
            raise ValueError("correct_choice must identify an available answer.")

    if exam["section"] == "3":
        questions = episode.get("questions")
        if not isinstance(questions, list) or len(questions) != 2:
            raise ValueError("Teil 3 requires two questions.")
        for item, count in zip(questions, (2, 3)):
            if (not isinstance(item, dict) or not isinstance(item.get("prompt"), str)
                    or not item["prompt"].strip() or type(item.get("number")) is not int
                    or item["number"] < 1):
                raise ValueError("Each Teil 3 question requires a number and prompt.")
            validate_choices(item, count)
        if questions[0]["number"] == questions[1]["number"]:
            raise ValueError("Teil 3 question numbers must differ.")
    else:
        validate_choices(episode, 6 if exam["section"] == "4" else 3)
    timing = episode.get("timing")
    if not isinstance(timing, dict):
        raise ValueError("timing must be an object.")
    for name in ("hook_seconds", "reading_seconds", "response_seconds", "reveal_seconds", "cta_seconds"):
        if type(timing.get(name)) is not int or timing[name] < 1:
            raise ValueError(f"{name} must be a positive whole number of seconds.")
    if timing["response_seconds"] < 6 or timing["reading_seconds"] < 7:
        raise ValueError("Allow at least seven seconds to read and six seconds to respond.")
    if timing["reveal_seconds"] < 1.8 or len(episode["answer_text"]) / timing["reveal_seconds"] > 20:
        raise ValueError("The answer caption needs more reading time.")
    source = episode.get("source")
    if not isinstance(source, dict) or source.get("duration_limit_seconds") != 90:
        raise ValueError("source.duration_limit_seconds must be 90.")
    scene = episode.get("scene")
    if not isinstance(scene, dict) or not isinstance(scene.get("camera_prefix"), str):
        raise ValueError("scene requires a source and camera prefix.")
    for name in ("pose_frame", "cycle_frames"):
        if type(scene.get(name)) is not int or scene[name] < 1:
            raise ValueError(f"scene.{name} must be a positive integer.")
    if scene["cycle_frames"] < 5:
        raise ValueError("Listener animation requires at least five samples.")
    device = scene.get("playback_device")
    if (not isinstance(device, dict) or set(device) != {"model", "provenance", "table_position"}
            or not isinstance(device["table_position"], list) or len(device["table_position"]) != 2
            or any(type(value) not in (int, float) for value in device["table_position"])):
        raise ValueError("scene.playback_device requires model, provenance and table_position.")
    if not isinstance(episode.get("voice"), dict):
        raise ValueError("voice must be an object.")

    def asset(value, label):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} must be a file path.")
        result = (path.parent / value).resolve(strict=True)
        if not result.is_file():
            raise ValueError(f"{label} must be a file: {result}")
        return result

    files = {
        "book_audio.wav": asset(episode.get("audio"), "audio"),
        "book_cover.jpg": asset(episode.get("book_cover"), "book_cover"),
        "book.md": asset(source.get("book"), "source.book"),
        "scene.blend": asset(scene.get("source"), "scene.source"),
        "device.glb": asset(device["model"], "scene.playback_device.model"),
        "device.provenance.json": asset(device["provenance"], "scene.playback_device.provenance"),
        "voice.wav": asset(episode["voice"].get("audio"), "voice.audio"),
        "voice.txt": asset(episode["voice"].get("transcript"), "voice.transcript"),
    }
    provenance = json.loads(files["device.provenance.json"].read_text(encoding="utf-8"))
    if sha256_file(files["device.glb"]) != provenance["sha256"]:
        raise ValueError("Playback device model checksum mismatch.")
    info = inspect_wav(files["book_audio.wav"])
    excerpt = episode.get("audio_excerpt")
    if excerpt is not None:
        if (not isinstance(excerpt, dict) or set(excerpt) != {"start_sample", "end_sample"}
                or any(type(excerpt[k]) is not int for k in excerpt)
                or not 0 <= excerpt["start_sample"] < excerpt["end_sample"] <= info["frames"]):
            raise ValueError("audio_excerpt requires valid start_sample and end_sample within the source WAV.")
    inspect_wav(files["voice.wav"])
    with Image.open(files["book_cover.jpg"]) as image:
        image.verify()
    return episode, files


def book_audio_file(episode, build, *, create):
    source = build / "inputs" / "book_audio.wav"
    excerpt = episode.get("audio_excerpt")
    if excerpt is None:
        return source
    target = build / "audio" / "book_excerpt.wav"
    with wave.open(str(source), "rb") as original:
        params = original.getparams()
        start, end = excerpt["start_sample"], excerpt["end_sample"]
        if not 0 <= start < end <= params.nframes:
            raise ValueError("Listening excerpt exceeds the source audio.")
        original.setpos(start)
        samples = original.readframes(end - start)
    if not target.exists() and create:
        target.parent.mkdir(exist_ok=True)
        partial = target.with_name(target.name + ".part")
        with wave.open(str(partial), "wb") as output:
            output.setparams(params)
            output.writeframes(samples)
        partial.replace(target)
    if not target.is_file():
        raise ValueError(f"Missing verified book excerpt: {target}")
    with wave.open(str(target), "rb") as output:
        actual = output.getparams()
        if (actual.nchannels != params.nchannels or actual.sampwidth != params.sampwidth
                or actual.framerate != params.framerate or actual.nframes != end - start
                or output.readframes(actual.nframes) != samples):
            raise ValueError("Book audio excerpt differs from the original sample range.")
    return target


def timeline_for(episode, book_info, answer_info, hook_info):
    fps = episode["fps"]
    timing = episode["timing"]
    cursor = 0
    phases = []

    def add(name, frames):
        nonlocal cursor
        phases.append({"name": name, "start_frame": cursor, "end_frame": cursor + frames})
        cursor += frames

    hook_frames = wav_frames_to_video_frames(hook_info["frames"], hook_info["sample_rate"], fps)
    add("hook", max(ceil_frames(timing["hook_seconds"], fps), hook_frames))
    for remaining in range(timing["reading_seconds"], 0, -1):
        add(f"reading_{remaining}", fps)
    add("listening", wav_frames_to_video_frames(book_info["frames"], book_info["sample_rate"], fps))
    for remaining in range(timing["response_seconds"], 0, -1):
        add(f"response_{remaining}", fps)
    answer_frames = wav_frames_to_video_frames(answer_info["frames"], answer_info["sample_rate"], fps)
    reveal_frames = ceil_frames(timing["reveal_seconds"], fps)
    if answer_frames > reveal_frames:
        raise ValueError("Answer narration exceeds reveal duration; extend the reveal.")
    add("reveal", reveal_frames)
    add("cta", ceil_frames(timing["cta_seconds"], fps))
    if cursor >= episode["source"]["duration_limit_seconds"] * fps:
        raise ValueError("Listening video must be strictly shorter than 90 seconds.")
    return {"fps": fps, "total_frames": cursor, "duration": cursor / fps, "phases": phases}


def draw_wrapped(draw, text, x, y, font, width, fill, leading=5, max_lines=3):
    lines = []
    for word in text.split():
        candidate = (lines[-1] + " " + word) if lines else word
        if draw.textlength(word, font=font) > width:
            raise ValueError(f"Word too wide for listening layout: {word}")
        if not lines or draw.textlength(candidate, font=font) > width:
            lines.append(word)
        else:
            lines[-1] = candidate
    if len(lines) > max_lines:
        raise ValueError(f"Text exceeds listening layout: {text}")
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill, stroke_width=0)
        y += font.size + leading
    return y


def make_overlay(episode, phase, cover_path):
    image = Image.new("RGBA", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    regular = ImageFont.truetype(str(font_path()), 24)
    small = ImageFont.truetype(str(font_path()), 20)
    compact = ImageFont.truetype(str(font_path()), 17)
    bold = ImageFont.truetype(str(font_path(True)), 27)
    heading = ImageFont.truetype(str(font_path(True)), 22)
    countdown = ImageFont.truetype(str(font_path(True)), 84)
    white, green = (255, 255, 255, 255), (174, 242, 198, 255)
    dark = (10, 26, 35, 231)
    draw.rounded_rectangle((78, 105, 590, 185), radius=14, fill=dark)
    draw.text((96, 112), "DTZ B1 HÖREN", font=bold, fill=green)
    section = episode.get("exam", {}).get("section", "1")
    draw.text((96, 151), f"DEUTSCHKOMPASS · Teil {section}", font=small, fill=white)

    if phase == "cta":
        draw.rounded_rectangle((78, 520, 590, 790), radius=18, fill=dark)
        with Image.open(cover_path) as cover:
            cover = cover.convert("RGB")
            cover.thumbnail((135, 205))
            image.paste(cover, (96, 538))
        draw_wrapped(draw, "Mehr Hörübungen im DTZ B1 Übungsbuch", 250, 538,
                     bold, 320, white, max_lines=5)
        draw_wrapped(draw, "Amazon-Buchlink im Profil", 250, 688, small, 320, green)
        draw_wrapped(draw, "Unabhängiges Übungsmaterial", 250, 748, compact, 320, white)
        return image

    def draw_status():
        if phase == "listening":
            draw.rounded_rectangle((450, 842, 590, 922), radius=16, fill=dark)
            draw_wrapped(draw, "Jetzt genau zuhören.", 464, 851, compact, 112, green, leading=1)
        else:
            status = "Lies zuerst die Antworten." if phase.startswith("reading_") else "Deine Antwort?"
            remaining = phase.split("_")[1]
            draw.rounded_rectangle((450, 810, 590, 1008), radius=16, fill=dark)
            draw_wrapped(draw, status, 464, 820, compact, 112, green, leading=1)
            draw.text((520, 928), remaining, font=countdown, fill=white, anchor="mm")
            draw.text((520, 985), "SEK.", font=compact, fill=green, anchor="mm")

    if section == "3" and phase != "hook":
        draw.rounded_rectangle((78, 520, 590, 790), radius=18, fill=dark)
        if phase == "reveal":
            y = 532
            for item in episode["questions"]:
                answer = item["choices"][ord(item["correct_choice"]) - ord("A")]
                y = draw_wrapped(draw, f"{item['number']}  {item['correct_choice']}  {answer}",
                                 96, y, heading, 468, green, leading=2, max_lines=2) + 8
            y = draw_wrapped(draw, episode["key_detail"], 96, y + 8, small, 468, white,
                             leading=2, max_lines=2)
            if y > 790:
                raise ValueError("Teil 3 answer exceeds the reveal panel.")
        else:
            y = 532
            for index, item in enumerate(episode["questions"]):
                y = draw_wrapped(draw, f"{item['number']}. {item['prompt']}", 96, y, heading, 468, white,
                                 leading=2, max_lines=2) + 4
                if index == 0:
                    y = draw_wrapped(draw, "A  " + item["choices"][0] + "      B  " + item["choices"][1],
                                     96, y, small, 468, white, max_lines=1) + 9
                else:
                    for choice_index, choice in enumerate(item["choices"]):
                        y = draw_wrapped(draw, f"{chr(65 + choice_index)}  {choice}", 96, y,
                                         small, 468, white, leading=1, max_lines=2) + 4
            if y > 790:
                raise ValueError("Teil 3 questions exceed the listening panel.")
            draw_status()
        return image

    draw.rounded_rectangle((78, 520, 590, 603), radius=18, fill=dark)
    draw_wrapped(draw, episode["question"], 96, 531, bold, 475, white, leading=3, max_lines=2)
    if phase == "hook":
        return image
    elif phase == "reveal":
        draw.rounded_rectangle((78, 615, 590, 790), radius=18, fill=dark)
        correct = ord(episode["correct_choice"]) - ord("A")
        choice_end = draw_wrapped(draw, f"{episode['correct_choice']}  {episode['choices'][correct]}",
                                  96, 625, heading, 468, green, leading=2, max_lines=2)
        answer_end = draw_wrapped(draw, episode["answer_text"], 96, max(671, choice_end + 3),
                                  regular, 468, white, leading=0, max_lines=3)
        detail_y = max(754, answer_end + 3)
        if detail_y + small.size > 790:
            raise ValueError("Answer text exceeds the listening reveal panel.")
        draw_wrapped(draw, episode["key_detail"], 96, detail_y, small, 468, green, max_lines=1)
    else:
        draw.rounded_rectangle((78, 615, 590, 790), radius=16, fill=dark)
        if section == "4":
            for index, choice in enumerate(episode["choices"]):
                draw_wrapped(draw, f"{chr(65 + index)}  {choice}",
                             96 + (index % 2) * 241, 627 + (index // 2) * 50,
                             small, 220, white, leading=1, max_lines=2)
        else:
            for index, choice in enumerate(episode["choices"]):
                draw_wrapped(draw, f"{chr(65 + index)}  {choice}", 96, 627 + index * 52,
                             regular, 472, white, leading=0, max_lines=2)
        draw_status()
    return image


def run_logged(command, log):
    with Path(log).open("w", encoding="utf-8") as output:
        result = run_process(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        tail = Path(log).read_text(encoding="utf-8", errors="replace").splitlines()[-25:]
        raise RuntimeError(f"Command failed ({result.returncode}); see {log}\n" + "\n".join(tail))


def verified_copy(source, target, expected):
    if not target.exists():
        shutil.copy2(source, target)
    if sha256_file(target) != expected or sha256_file(source) != expected:
        raise ValueError(f"Source or snapshot changed: {source}")


def loop_indices(count):
    if count < 2:
        raise ValueError("Listener loop requires at least two source frames.")
    return list(range(count)) + list(range(count - 2, 0, -1))


def video_filters(timeline, profile="preview"):
    fps = timeline["fps"]
    phases = timeline["phases"]
    render_settings(profile)
    scale = "scale=792:1408:flags=lanczos," if profile == "preview" else ""
    filters = [f"[0:v]fps=24,{scale}crop=720:1280:36:120,"
               "setsar=1,setpts=PTS-STARTPTS[base]"]
    previous = "base"
    for index, phase in enumerate(phases, 1):
        label = f"v{index}"
        filters.append(
            f"[{previous}][{index}:v]overlay=0:0:enable='gte(n,{phase['start_frame']})"
            f"*lt(n,{phase['end_frame']})'[{label}]")
        previous = label
    listening = next(p for p in phases if p["name"] == "listening")["start_frame"]
    reveal = next(p for p in phases if p["name"] == "reveal")["start_frame"]
    book_input, answer_input, hook_input = len(phases) + 1, len(phases) + 2, len(phases) + 3
    samples_per_frame = 48000 // fps
    filters.extend([
        f"[{book_input}:a]aresample=48000,aformat=channel_layouts=mono,"
        f"adelay={listening * samples_per_frame}S:all=1[book]",
        f"[{answer_input}:a]aresample=48000,aformat=channel_layouts=mono,"
        f"adelay={reveal * samples_per_frame}S:all=1[answer]",
        f"[{hook_input}:a]aresample=48000,aformat=channel_layouts=mono[hook]",
        f"[hook][book][answer]amix=inputs=3:normalize=0:duration=longest,"
        f"apad=whole_len={timeline['total_frames'] * samples_per_frame},"
        f"atrim=end_sample={timeline['total_frames'] * samples_per_frame}[audio]",
    ])
    return ";".join(filters), previous


def encoding_command(build, episode, timeline, answer_audio, hook_audio, profile="preview", book_audio=None):
    frames = build / "listener_frames"
    overlays = build / "overlays"
    inputs = build / "inputs"
    fps = episode["fps"]
    command = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-filter_complex_threads", "1", "-y",
               "-framerate", str(fps), "-stream_loop", "-1",
               "-i", str(frames / "listener_%03d.png")]
    for phase in timeline["phases"]:
        command += ["-loop", "1", "-framerate", str(fps), "-i", str(overlays / f"{phase['name']}.png")]
    command += ["-i", str(book_audio or inputs / "book_audio.wav"), "-i", str(answer_audio),
                "-i", str(hook_audio)]
    filters, video_label = video_filters(timeline, profile)
    command += ["-filter_complex", filters, "-map", f"[{video_label}]", "-map", "[audio]",
                "-frames:v", str(timeline["total_frames"]), "-t", f"{timeline['duration']:.9f}",
                "-shortest", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                "-movflags", "+faststart", str(build / "pilot.mp4")]
    return command


def audio_delivery_check(video, book, answer, hook, timeline):
    import numpy as np

    def pcm(path):
        result = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "48000",
             "-f", "s16le", "-"], check=True, capture_output=True)
        return np.frombuffer(result.stdout, dtype="<i2").astype(np.float64)

    output, original, narration, opening = pcm(video), pcm(book), pcm(answer), pcm(hook)
    phases = {phase["name"]: phase for phase in timeline["phases"]}
    sample_per_frame = 48000 // timeline["fps"]
    correlations = {}
    for label, samples, phase in (("hook", opening, "hook"), ("book", original, "listening"),
                                  ("answer", narration, "reveal")):
        start = phases[phase]["start_frame"] * sample_per_frame
        decoded = output[start:start + len(samples)]
        if len(decoded) != len(samples) or np.std(decoded) == 0 or np.std(samples) == 0:
            raise ValueError(f"Missing or silent encoded {label} audio.")
        correlation = float(np.corrcoef(samples, decoded)[0, 1])
        if not np.isfinite(correlation) or correlation < 0.95:
            raise ValueError(f"Encoded {label} audio does not match its source: {correlation:.4f}")
        correlations[label] = correlation
    response_start = phases["response_6"]["start_frame"] * sample_per_frame + 12000
    response_end = phases["reveal"]["start_frame"] * sample_per_frame - 12000
    response = output[response_start:response_end]
    if not len(response):
        raise ValueError("Encoded response pause is missing.")
    response_rms = float(np.sqrt(np.mean(response * response)) / 32768)
    if response_rms > 0.005:
        raise ValueError(f"Unexpected audio during the response pause: RMS {response_rms:.5f}")
    return {"source_correlations": correlations, "response_rms_fraction": response_rms,
            "note": "AAC output compared with resampled source waveforms; not an auditory review."}


def audio_reuse_spec(source, build, episode, files, sources):
    source = resolve_build_reference(source).resolve(strict=True)
    if not source.is_dir() or source == build or source in build.parents or build in source.parents:
        raise ValueError("Audio reuse requires a separate, non-nested delivery directory.")

    def read_json(path):
        if not path.is_file():
            raise ValueError(f"Missing listening delivery file: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    state_path = source / "listening_state.json"
    report_path = source / "delivery_checks.json"
    timeline_path = source / "timeline.json"
    state, report, timeline = (read_json(p) for p in (state_path, report_path, timeline_path))
    try:
        if (state["profile"] != "preview" or state["episode"] != episode
                or read_json(source / "episode.json") != episode):
            raise ValueError("Audio reuse requires a matching completed listening preview.")
        if report["timeline"] != timeline:
            raise ValueError("Listening delivery timeline does not match its report.")
        if set(state["sources"]) != set(sources) or report["source_sha256"] != state["sources"]:
            raise ValueError("Listening delivery source records do not match.")
        for name, entry in sources.items():
            digest = entry["sha256"]
            if (state["sources"][name]["sha256"] != digest
                    or sha256_file(source / "inputs" / name) != digest):
                raise ValueError(f"Listening source changed: {name}")
        video = source / "pilot.mp4"
        if sha256_file(video) != report["output_sha256"]:
            raise ValueError("Listening delivery video checksum mismatch.")
        if "hook_audio_sha256" not in report:
            raise ValueError("Listening preview has no verified spoken hook; generate a new preview.")
        recordings = {}
        for name, text in (("answer", episode["answer_text"]), ("hook", episode["question"])):
            digest = report[f"{name}_audio_sha256"]
            candidates = [p for p in (source / "audio").glob(f"{name}-*.wav")
                          if sha256_file(p) == digest]
            if len(candidates) != 1:
                raise ValueError(f"Expected exactly one verified listening {name} recording.")
            audio = candidates[0]
            metadata_path = audio.with_suffix(".cache.json")
            metadata = read_json(metadata_path)
            payload = make_cache_payload(
                {"speaker": "narrator", "text": text},
                files["voice.wav"], files["voice.txt"], metadata["payload"]["settings"])
            if (metadata["payload"] != payload or metadata["cache_key"] != content_hash(payload)
                    or metadata["wav_sha256"] != digest or metadata["audio_info"] != inspect_wav(audio)):
                raise ValueError(f"Listening {name} recording cache does not match its inputs.")
            recordings[name] = (audio, metadata_path, digest)
        answer, answer_metadata, answer_digest = recordings["answer"]
        hook, hook_metadata, hook_digest = recordings["hook"]
        book_audio = book_audio_file(episode, source, create=False)
        if episode.get("audio_excerpt") is not None and sha256_file(book_audio) != report["book_audio_sha256"]:
            raise ValueError("Listening excerpt checksum differs from its delivery report.")
        measured = timeline_for(episode, inspect_wav(book_audio), inspect_wav(answer), inspect_wav(hook))
        if measured != timeline:
            raise ValueError("Listening delivery timing differs from the measured audio.")
        audio_delivery_check(video, book_audio, answer, hook, timeline)
        return {
            "source": str(source), "answer": str(answer),
            "answer_sha256": answer_digest, "answer_metadata_sha256": sha256_file(answer_metadata),
            "hook": str(hook), "hook_sha256": hook_digest,
            "hook_metadata_sha256": sha256_file(hook_metadata),
            "output_sha256": report["output_sha256"],
            "report_sha256": sha256_file(report_path),
            "state_sha256": sha256_file(state_path),
            "timeline_sha256": sha256_file(timeline_path),
        }, timeline
    except (KeyError, TypeError) as error:
        raise ValueError(f"Invalid listening delivery metadata: {source}") from error


@generation_job
def build_listening(path, build, jobs=4, until="export", speech_cache_from=None,
                    profile="preview", reuse_audio=None):
    episode, files = load_episode(path)
    build = build_directory(build).resolve()
    render = render_settings(profile)
    if reuse_audio and speech_cache_from:
        raise ValueError("Choose exact audio reuse or a speech cache, not both.")
    if profile == "production" and not reuse_audio:
        raise ValueError("Listening production requires --reuse-audio from a completed preview.")
    if build == ROOT or build in ROOT.parents or any(build == p or build in p.parents for p in files.values()):
        raise ValueError("Use a separate dedicated output directory.")
    sources = {name: {"path": str(file), "sha256": sha256_file(file)} for name, file in files.items()}
    reuse, reuse_timeline = (audio_reuse_spec(reuse_audio, build, episode, files, sources)
                             if reuse_audio else (None, None))
    code_names = ("pipeline.py", "listening_video.py", "listening_scene.py", "listener_motion.py", "prepare_audio.py",
                  "episode_config.py", "episode_profiles.py", "scene_direction.py", "picture_presentation.py",
                  "generation_runtime.py", "runtime_config.py", "build_paths.py")
    spec = {"episode": episode, "sources": sources,
            "code_sha256": {name: sha256_file(ROOT / name) for name in code_names},
            "profile": profile, "render": render, "render_device": "CPU", "threads": jobs,
            "audio_reuse": reuse}
    state_path = build / "listening_state.json"
    if state_path.exists():
        if json.loads(state_path.read_text(encoding="utf-8")) != spec:
            raise ValueError("Build inputs changed; choose a new build directory.")
    else:
        if build.exists() and any(build.iterdir()):
            raise ValueError("Build directory is not empty; choose a fresh directory.")
        build.mkdir(parents=True, exist_ok=True)
        atomic_json(state_path, spec)
    inputs = build / "inputs"
    inputs.mkdir(exist_ok=True)
    for name, file in files.items():
        verified_copy(file, inputs / name, sources[name]["sha256"])
    source_export = build / "source_export"
    source_export.mkdir(exist_ok=True)
    for name in code_names:
        verified_copy(ROOT / name, source_export / name, spec["code_sha256"][name])
    atomic_json(build / "episode.json", episode)
    audio_dir = build / "audio"
    audio_dir.mkdir(exist_ok=True)
    book_audio = book_audio_file(episode, build, create=True)
    book_audio_sha256 = sha256_file(book_audio)
    narration = {
        "language": "de",
        "voices": {"narrator": {"audio": str(inputs / "voice.wav"), "transcript": str(inputs / "voice.txt")}},
        "turns": [{"id": "hook", "speaker": "narrator", "text": episode["question"]},
                  {"id": "answer", "speaker": "narrator", "text": episode["answer_text"]}],
    }
    if reuse:
        recordings = {}
        for name in ("hook", "answer"):
            original = Path(reuse[name])
            recordings[name] = audio_dir / original.name
            verified_copy(original, recordings[name], reuse[f"{name}_sha256"])
            verified_copy(original.with_suffix(".cache.json"), recordings[name].with_suffix(".cache.json"),
                          reuse[f"{name}_metadata_sha256"])
        hook_audio, answer_audio = recordings["hook"], recordings["answer"]
    else:
        cache = Path(speech_cache_from).resolve() if speech_cache_from else None
        if cache and (cache / "audio").is_dir():
            cache = cache / "audio"
        if cache and not cache.is_dir():
            raise ValueError("speech cache directory does not exist.")
        results = synthesize(narration, ROOT, audio_dir, MODEL, "cpu", 8, cache_from=cache)
        hook_audio, answer_audio = (Path(result["audio"]) for result in results)
    hook_sha256, answer_sha256 = sha256_file(hook_audio), sha256_file(answer_audio)
    timeline = timeline_for(episode, inspect_wav(book_audio), inspect_wav(answer_audio), inspect_wav(hook_audio))
    if reuse and timeline != reuse_timeline:
        raise ValueError("Reused listening audio does not match the preview timeline.")
    for phase in timeline["phases"]:
        make_overlay(episode, phase["name"], inputs / "book_cover.jpg")
    atomic_json(build / "timeline.json", timeline)
    stage_completed("audio")
    if until == "audio":
        return build

    frames = build / "listener_frames"
    frames.mkdir(exist_ok=True)
    scene = episode["scene"]
    count = scene["cycle_frames"]
    indices = loop_indices(count)
    expected = [frames / f"listener_{index:03d}.png" for index in range(len(indices))]
    receipt_path = build / "listener_frames.json"
    if not receipt_path.exists():
        run_logged([str(tool_path("blender")), "-b", "--disable-autoexec", str(inputs / "scene.blend"),
                    "-t", str(jobs), "--python-exit-code", "1", "--python",
                    str(source_export / "listening_scene.py"),
                    "--", "--output", str(frames), "--camera-prefix", scene["camera_prefix"],
                    "--pose-frame", str(scene["pose_frame"]), "--cycle-frames", str(count),
                    "--width", str(render["width"]), "--height", str(render["height"]),
                    "--samples", str(render["samples"]),
                    "--device", str(inputs / "device.glb"),
                    "--device-x", str(scene["playback_device"]["table_position"][0]),
                    "--device-y", str(scene["playback_device"]["table_position"][1]),
                    "--device-report", str(build / "device_checks.json")], build / "render.log")
        for index in range(count, len(indices)):
            shutil.copyfile(expected[indices[index]], expected[index])
        atomic_json(receipt_path, {p.name: sha256_file(p) for p in expected})
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt != {p.name: sha256_file(p) for p in expected}:
        raise ValueError("Listener frame receipt mismatch; use a fresh build.")
    for frame in expected:
        with Image.open(frame) as image:
            if image.size != (render["width"], render["height"]):
                raise ValueError(f"Unexpected listener frame dimensions: {frame}")
            image.verify()
    stage_completed("scene")
    if until == "scene":
        return build

    def verify_frozen_inputs():
        if any(sha256_file(inputs / name) != entry["sha256"] for name, entry in sources.items()):
            raise ValueError("Listening input snapshot changed; use a fresh build.")
        if any(sha256_file(ROOT / name) != digest or sha256_file(source_export / name) != digest
               for name, digest in spec["code_sha256"].items()):
            raise ValueError("Listening pipeline code changed; use a fresh build.")
        if sha256_file(answer_audio) != answer_sha256 or sha256_file(hook_audio) != hook_sha256:
            raise ValueError("Listening narration changed; use a fresh build.")
        if sha256_file(book_audio) != book_audio_sha256:
            raise ValueError("Book audio excerpt changed; use a fresh build.")
        book_audio_file(episode, build, create=False)

    verify_frozen_inputs()
    overlays = build / "overlays"
    overlays.mkdir(exist_ok=True)
    for phase in timeline["phases"]:
        make_overlay(episode, phase["name"], inputs / "book_cover.jpg").save(overlays / f"{phase['name']}.png")
    run_logged(encoding_command(build, episode, timeline, answer_audio, hook_audio, profile, book_audio),
               build / "encode.log")
    run_logged(["ffmpeg", "-v", "error", "-i", str(build / "pilot.mp4"), "-f", "null", "-"],
               build / "decode.log")
    probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_streams",
                            "-show_format", "-of", "json", str(build / "pilot.mp4")],
                           check=True, capture_output=True, text=True)
    media = json.loads(probe.stdout)
    video = next(stream for stream in media["streams"] if stream["codec_type"] == "video")
    audio = next(stream for stream in media["streams"] if stream["codec_type"] == "audio")
    if (int(video["nb_read_frames"]) != timeline["total_frames"]
            or video["width"] != WIDTH or video["height"] != HEIGHT
            or video["r_frame_rate"] != "24/1" or video["sample_aspect_ratio"] != "1:1"
            or video["display_aspect_ratio"] != "9:16" or audio["sample_rate"] != "48000"
            or float(media["format"]["duration"]) >= 90):
        raise ValueError("Encoded listening video does not match the checked timeline.")
    audio_check = audio_delivery_check(build / "pilot.mp4", book_audio,
                                       answer_audio, hook_audio, timeline)
    verify_frozen_inputs()
    review = build / "review"
    review.mkdir(exist_ok=True)
    for phase in timeline["phases"]:
        if phase["name"] not in ("hook", "reading_7", "reading_1", "listening", "response_6", "response_1", "reveal", "cta"):
            continue
        sample_frame = phase["start_frame"] + min(12, phase["end_frame"] - phase["start_frame"] - 1)
        run_logged(["ffmpeg", "-v", "error", "-y", "-i", str(build / "pilot.mp4"),
                    "-vf", f"select=eq(n\\,{sample_frame})", "-frames:v", "1",
                    str(review / f"{phase['name']}.png")], review / f"{phase['name']}.log")
    credits = (
        "Werbung für unser DTZ-B1-Übungsbuch. Unabhängiges Übungsmaterial; keine offizielle Prüfung. "
        "KI-generierte Stimmen und animierte Figur. Amazon-Buchlink im Profil.\n\n"
        "Snow Rig (CC) Blender Foundation | studio.blender.org\n"
        "https://studio.blender.org/characters/snow/v4/\n"
        "Rain Rig (CC) Blender Foundation | studio.blender.org\n"
        "https://studio.blender.org/characters/rain/v3/\n"
        "CC BY 4.0: https://creativecommons.org/licenses/by/4.0/\n"
        "Kleidung/Haare umgefärbt, Figuren skaliert, posiert und animiert. "
        "Keine Unterstützung oder Empfehlung durch Blender Foundation/Blender Studio.\n"
        "Boombox model by Innerscene, CC0: "
        "https://www.innerscene.com/tools/library/3d-parts/boombox-e5bca8cf\n"
    )
    (build / "publishing_caption.txt").write_text(credits, encoding="utf-8")
    report = {"timeline": timeline, "media": media, "profile": profile, "render": render,
              "audio_reuse": reuse, "source_sha256": sources, "audio_check": audio_check,
              "output_sha256": sha256_file(build / "pilot.mp4"),
              "answer_audio_sha256": answer_sha256, "hook_audio_sha256": hook_sha256,
              "book_audio_sha256": book_audio_sha256,
              "listener_frames_sha256": {p.name: sha256_file(p) for p in expected},
              "loop_source_indices": indices,
              "device_checks": json.loads((build / "device_checks.json").read_text(encoding="utf-8")),
              "disclosure": ("Preview only; " if profile == "preview" else "Production render; ")
                            + "listening and pronunciation review and platform placement remain pending."}
    atomic_json(build / "delivery_checks.json", report)
    stage_completed("export", force=True)
    print(f"Listening {profile}: {build / 'pilot.mp4'} ({timeline['duration']:.3f}s)", flush=True)
    return build
