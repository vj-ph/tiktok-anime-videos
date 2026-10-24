#!/usr/bin/env python3
"""Production entry point; heavyweight audio/3D tools run in separate processes."""

import argparse
import hashlib
import json
import math
import os
import struct
import subprocess
import textwrap
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from build_paths import BUILDS, build_directory, resolve_build_reference
from runtime_config import RENDER_DEVICES, caption_fonts, qwen_python, render_expression, tool_path
ROOT = Path(__file__).resolve().parent
RIG_CREDITS = (
    "Snow Rig (CC) Blender Foundation | studio.blender.org",
    "Rain Rig (CC) Blender Foundation | studio.blender.org",
    "CC BY 4.0 · recolored, posed and animated for this film",
)


def run(command, **kwargs):
    print("+", " ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), check=True, **kwargs)


def ass_time(seconds):
    centiseconds = round(seconds * 100)
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{fraction:02d}"


def escape_ass(text):
    return text.replace("\\", "＼").replace("{", "｛").replace("}", "｝").replace("\n", r"\N")


def wrap(text, width=37):
    return r"\N".join(escape_ass(line) for line in textwrap.wrap(text, width=width))


def captions(episode, timeline):
    if episode.get("presentation") == "social":
        from social_captions import make_ass
        return make_ass(episode, timeline)
    if episode.get("presentation") == "exchange":
        return exchange_captions(episode, timeline)
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Brand,DejaVu Sans,18,&H00CDECD9,&H000000FF,&H00221810,&H00221810,-1,0,0,0,100,100,3,0,1,0,0,8,40,40,24,1
Style: Label,DejaVu Sans,22,&H00CDECD9,&H000000FF,&H00221810,&H00221810,-1,0,0,0,100,100,0,0,1,0,0,8,40,40,59,1
Style: Title,DejaVu Sans,29,&H00FFFFFF,&H000000FF,&H00221810,&H00221810,-1,0,0,0,100,100,0,0,1,0,0,8,30,30,94,1
Style: Role,DejaVu Sans,23,&H00CDECD9,&H000000FF,&H00221810,&H00221810,-1,0,0,0,100,100,0,0,1,0,0,8,45,45,965,1
Style: Speech,DejaVu Sans,29,&H00FFFFFF,&H000000FF,&H00221810,&H00221810,0,0,0,0,100,100,0,0,1,0,0,8,40,40,1005,1
Style: Note,DejaVu Sans,14,&H00FFFFFF,&H000000FF,&H00221810,&H00221810,0,0,0,0,100,100,0,0,1,0,0,2,30,30,12,1
Style: Credit,DejaVu Sans,15,&H00DDDDDD,&H000000FF,&H00221810,&H00221810,0,0,0,0,100,100,0,0,1,1,0,8,15,15,1191,1
Style: Card,DejaVu Sans,32,&H00FFFFFF,&H000000FF,&H00221810,&H00221810,-1,0,0,0,100,100,0,0,1,0,0,5,45,45,0,1
Style: Panel,DejaVu Sans,20,&H00221810,&H000000FF,&H00221810,&H00221810,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    duration = timeline["duration"]

    def event(start, end, style, text, layer=1):
        lines.append(f"Dialogue: {layer},{ass_time(start)},{ass_time(end)},{style},,0,0,0,,{text}\n")

    def panel(start, end, y1, y2, alpha="15"):
        event(start, end, "Panel", r"{\an7\pos(0,0)\p1\alpha&H" + alpha + "&}m 0 " + str(y1) + f" l 720 {y1} 720 {y2} 0 {y2}" + r"{\p0}", 0)

    panel(0, duration, 0, 170, "08")
    panel(0, duration, 945, 1175, "12")
    panel(0, duration, 1175, 1280, "05")
    event(0, duration, "Brand", escape_ass(episode["branding"]))
    event(0, duration, "Label", escape_ass(episode["label"]))
    event(0, duration, "Title", wrap(episode["title"], 27))
    event(0, duration, "Note", escape_ass(episode["disclaimer"]))
    event(0, duration, "Credit", r"\N".join(escape_ass(line) for line in RIG_CREDITS))
    event(0, episode["intro_seconds"], "Role", "PRÜFUNGSSITUATION KENNENLERNEN")
    event(0, episode["intro_seconds"], "Speech", "Zwei Teilnehmende. Zwei Prüfende." + r"\N" + "Ein gemeinsamer Plan.")
    for turn in timeline["turns"]:
        event(turn["start"], turn["end"], "Role", escape_ass(turn["name"]))
        event(turn["start"], turn["end"], "Speech", wrap(turn["text"]))
    outro = duration - episode["outro_seconds"]
    panel(outro, duration, 170, 1175, "08")
    event(outro, duration, "Card", r"{\pos(360,745)\fs25}" + "JETZT SELBST WEITERPLANEN" + r"\N\N" + r"{\fs22}" + r"\N".join(escape_ass(x) for x in episode["task_card"]))
    event(outro, duration, "Role", "DEIN NÄCHSTER SCHRITT")
    event(outro, duration, "Speech", r"\N".join(escape_ass(x) for x in episode["cta"]))
    return "".join(lines)


def exchange_captions(episode, timeline):
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Heading,DejaVu Sans,21,&H00FFFFFF,&H000000FF,&H00221810,&H00221810,-1,0,0,0,100,100,0,0,3,7,0,8,24,24,28,1
Style: Role,DejaVu Sans,22,&H00CDECD9,&H000000FF,&H00221810,&H00221810,-1,0,0,0,100,100,0,0,1,1,0,8,32,32,1013,1
Style: Speech,DejaVu Sans,29,&H00FFFFFF,&H000000FF,&H00221810,&H00221810,0,0,0,0,100,100,0,0,1,1,0,8,32,32,1053,1
Style: Credit,DejaVu Sans,15,&H00DDDDDD,&H000000FF,&H00221810,&H00221810,0,0,0,0,100,100,0,0,1,1,0,8,15,15,1191,1
Style: Panel,DejaVu Sans,20,&H00221810,&H000000FF,&H00221810,&H00221810,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    end = ass_time(timeline["duration"])
    lines = [header]
    lines.append(f"Dialogue: 0,0:00:00.00,{end},Panel,,0,0,0,,"
                 + r"{\an7\pos(0,0)\p1\alpha&H10&}m 0 995 l 720 995 720 1280 0 1280{\p0}" + "\n")
    lines.append(f"Dialogue: 1,0:00:00.00,{end},Heading,,0,0,0,,"
                 + escape_ass(episode["label"]) + " · Übungsausschnitt\n")
    lines.append(f"Dialogue: 1,0:00:00.00,{end},Credit,,0,0,0,,"
                 + r"\N".join(escape_ass(line) for line in RIG_CREDITS) + "\n")
    for turn in timeline["turns"]:
        for style, text in (("Role", "Es spricht: " + escape_ass(turn["name"])), ("Speech", wrap(turn["text"], 39))):
            lines.append(f"Dialogue: 1,{ass_time(turn['start'])},{ass_time(turn['end'])},{style},,0,0,0,,{text}\n")
    return "".join(lines)


def credit_captions(duration):
    """Keep attribution on the otherwise unbranded master as well."""
    return (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 720\nPlayResY: 1280\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Credit,DejaVu Sans,15,&H00FFFFFF,&H000000FF,&H00221810,&H00221810,0,0,0,0,100,100,0,0,3,2,0,2,15,15,16,1\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"Dialogue: 0,0:00:00.00,{ass_time(duration)},Credit,,0,0,0,,"
        + r"\N".join(escape_ass(line) for line in RIG_CREDITS) + "\n"
    )


def load_inputs(build, episode_path=None):
    from episode_config import read_episode
    from episode_profiles import language_code
    episode = read_episode(episode_path or ROOT / "episode.json")
    if episode.get("presentation", "promotion") not in ("promotion", "exchange", "social"):
        raise ValueError("Unsupported episode presentation.")
    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    if language_code(episode) != language_code(timeline):
        raise ValueError("Episode and audio languages differ; regenerate audio.")
    if timeline["fps"] != episode["fps"]:
        raise ValueError("Episode and audio frame rates differ; regenerate audio.")
    if not math.isfinite(timeline["duration"]) or timeline["duration"] <= 0:
        raise ValueError("Timeline duration must be positive and finite.")
    turns_match = len(episode["turns"]) == len(timeline["turns"]) and all(
        all(actual.get(key) == value for key, value in expected.items())
        for expected, actual in zip(episode["turns"], timeline["turns"])
    )
    if not turns_match:
        raise ValueError("Timeline does not match episode.json; regenerate audio.")
    return episode, timeline


def scene_hash(build):
    return hashlib.sha256((build / "studio.blend").read_bytes()).hexdigest()


def valid_frame(path, width, height):
    if not path.is_file() or path.stat().st_size < 32:
        return False
    with path.open("rb") as handle:
        header = handle.read(24)
        handle.seek(-12, 2)
        trailer = handle.read()
    return (
        header[:8] == b"\x89PNG\r\n\x1a\n"
        and struct.unpack(">II", header[16:24]) == (width, height)
        and trailer == b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def mux(build, episode_path=None):
    episode, timeline = load_inputs(build, episode_path)
    social = episode.get("presentation") == "social"
    ass = captions(episode, timeline)
    caption_fonts(build)
    (build / "captions.ass").write_text(ass, encoding="utf-8")
    if not social:
        (build / "credits.ass").write_text(credit_captions(timeline["duration"]), encoding="utf-8")
    expected = round(timeline["duration"] * timeline["fps"])
    manifest = json.loads((build / "scene_manifest.json").read_text(encoding="utf-8"))
    if manifest["episode"] != episode or manifest["timeline"] != timeline:
        raise ValueError("Saved scene is stale; rebuild it before muxing.")
    rendered = json.loads((build / "frames_manifest.json").read_text(encoding="utf-8"))
    if rendered["scene"] != manifest or rendered["blend_sha256"] != scene_hash(build):
        raise ValueError("Frames are stale for the saved scene; render the frames again.")
    step = manifest["motion_step"]
    frames = list(range(1, expected + 1, step))
    missing = [index for index in frames if not valid_frame(build / "frames" / f"frame_{index:04d}.png", manifest["width"], manifest["height"])]
    if missing:
        raise FileNotFoundError(f"Missing {len(missing)} rendered frames; first is {missing[0]}")
    output_size = (720, 1280) if social else (manifest["width"], manifest["height"])
    if social:
        from social_captions import audit_ass, write_caption_timing, write_publication
        audit_ass(build, ass)
        write_caption_timing(build, episode, timeline)
        write_publication(build, episode)
    # Relative paths keep FFmpeg filter escaping independent of the project location.
    sequence = ["ffconcat version 1.0\n"]
    for index in frames:
        sequence.append(f"file frames/frame_{index:04d}.png\n")
        sequence.append(f"option framerate {timeline['fps']}\n")
        sequence.append(f"duration {min(step, expected - index + 1) / timeline['fps']:.12f}\n")
    sequence.append(f"file frames/frame_{frames[-1]:04d}.png\n")
    sequence.append(f"option framerate {timeline['fps']}\n")
    (build / "frames.ffconcat").write_text("".join(sequence), encoding="utf-8")
    common = [
        "ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
        "-f", "concat", "-safe", "0", "-i", "frames.ffconcat", "-i", "dialogue.wav",
    ]
    encoding = [
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:v", "libx264",
        "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-r", str(timeline["fps"]), "-frames:v", str(expected),
        "-t", str(timeline["duration"]), "-movflags", "+faststart",
    ]
    if social:
        video = (f"scale={output_size[0]}:{output_size[1]}:flags=lanczos,"
                 f"fps={timeline['fps']},ass=captions.ass:fontsdir=caption_fonts")
        if episode.get("pictures"):
            from picture_presentation import picture_filters
            from prepare_audio import atomic_json
            from social_captions import cover_bounds
            from episode_config import takeaway_seconds

            inputs, filters, output, windows = picture_filters(episode, timeline)
            filters.insert(0, f"[0:v]{video}[captioned]")
            if episode["outro_seconds"] > 0:
                cover = Path(episode["book_cover"])
                x, y, right, bottom = cover_bounds(cover)
                cover_input = 2 + len(windows)
                inputs += ["-loop", "1", "-framerate", str(timeline["fps"]), "-i", str(cover)]
                cover_start = round((timeline["duration"] - episode["outro_seconds"]
                                     + takeaway_seconds(episode)) * timeline["fps"])
                filters += [f"[{cover_input}:v]scale={right-x}:{bottom-y}[cover]",
                            f"[{output}][cover]overlay=x={x}:y={y}:enable='gte(n,{cover_start})'[covered]"]
                output = "covered"
            filters.append(f"[{output}]fps={timeline['fps']}[video]")
            run(common + inputs + ["-filter_complex_threads", "1", "-filter_complex", ";".join(filters),
                                  "-map", "[video]", "-map", "1:a:0"] + encoding + ["pilot.mp4"], cwd=build)
            atomic_json(build / "picture_timing_report.json", {
                "fps": timeline["fps"], "windows": windows,
                "policy": ("Explicit notice crop or whole image, aspect-fit; output-frame enables, end exclusive."
                           if any(w.get("layout") == "notice_detail" for w in windows) else
                           "Whole image, aspect-fit without cropping; output-frame enables, end exclusive."),
                **({"notice_detail_policy": "Explicit task-only source crops, aspect-fit; "
                     "full original retained on the physical task sheet. User-approved graphic bounds, "
                     "not platform safe-zone certification."}
                   if any(w.get("layout") == "notice_detail" for w in windows) else {}),
            })
            report_path = build / "safe_zone_report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["pictures"] = windows
            if episode["outro_seconds"] > 0:
                report["book_cover"] = {"bounds": [x, y, right, bottom], "start": cover_start / timeline["fps"]}
            atomic_json(report_path, report)
        elif episode.get("social_kind") == "exchange" or episode["outro_seconds"] == 0:
            run(common + ["-vf", video + f",fps={timeline['fps']}"] + encoding + ["pilot.mp4"], cwd=build)
        else:
            from social_captions import cover_bounds
            cover = (ROOT / episode["book_cover"]).resolve()
            x, y, right, _bottom = cover_bounds(cover)
            cover_width = right - x
            outro = timeline["duration"] - episode["outro_seconds"]
            from episode_config import takeaway_seconds
            cover_start = outro + takeaway_seconds(episode)
            filters = (
                f"[2:v]scale={cover_width}:224[cover];[0:v]{video}[captioned];"
                f"[captioned][cover]overlay=x={x}:y={y}:enable='gte(t,{cover_start})',"
                f"fps={timeline['fps']}[video]"
            )
            run(common + ["-loop", "1", "-i", cover, "-filter_complex", filters,
                          "-map", "[video]", "-map", "1:a:0"] + encoding + ["pilot.mp4"], cwd=build)
            report_path = build / "safe_zone_report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["book_cover"] = {"bounds": [x, y, x + cover_width, y + 224], "start": cover_start}
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif episode.get("presentation") == "exchange":
        run(common + ["-vf", f"fps={timeline['fps']},ass=captions.ass:fontsdir=caption_fonts"] + encoding + ["pilot.mp4"], cwd=build)
    else:
        cover = (ROOT / episode["book_cover"]).resolve()
        if not cover.is_file():
            raise FileNotFoundError(f"Book cover not found: {cover}")
        height = manifest["height"]
        cover_height = round(height * 0.295) // 2 * 2
        cover_y = round(height * 0.21)
        outro = timeline["duration"] - episode["outro_seconds"]
        filters = (
            f"[2:v]scale=-2:{cover_height}[cover];"
            f"[0:v]fps={timeline['fps']},ass=captions.ass:fontsdir=caption_fonts[captioned];"
            f"[captioned][cover]overlay=x=(W-w)/2:y={cover_y}:enable='gte(t,{outro})',fps={timeline['fps']}[video]"
        )
        run(common + ["-loop", "1", "-i", cover, "-filter_complex", filters,
                      "-map", "[video]", "-map", "1:a:0"] + encoding + ["pilot.mp4"], cwd=build)
    clean_filter = (
        f"scale={output_size[0]}:{output_size[1]}:flags=lanczos,fps={timeline['fps']}"
        if social else f"fps={timeline['fps']},ass=credits.ass:fontsdir=caption_fonts"
    )
    run(common + ["-vf", clean_filter] + encoding + ["pilot_clean.mp4"], cwd=build)
    for filename, report_name in (("pilot.mp4", "media_report.json"), ("pilot_clean.mp4", "media_report_clean.json")):
        info = subprocess.run(
            ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(build / filename)],
            check=True, capture_output=True, text=True,
        )
        report = json.loads(info.stdout)
        video = next(s for s in report["streams"] if s["codec_type"] == "video")
        audio = next(s for s in report["streams"] if s["codec_type"] == "audio")
        if int(video["nb_frames"]) != expected:
            raise RuntimeError(f"{filename}: encoded {video['nb_frames']} frames, expected {expected}")
        if abs(float(report["format"]["duration"]) - timeline["duration"]) > 0.1:
            raise RuntimeError(f"{filename}: encoded duration differs from the audio timeline")
        if (video["width"], video["height"]) != output_size:
            raise RuntimeError(f"{filename}: dimensions differ from the intended export size")
        if audio["codec_name"] != "aac" or video["codec_name"] != "h264":
            raise RuntimeError(f"{filename}: unexpected output codecs")
        if audio["sample_rate"] != "48000" or audio["channels"] != 1:
            raise RuntimeError(f"{filename}: expected 48 kHz mono audio")
        (build / report_name).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Created {build / 'pilot.mp4'} ({timeline['duration']:.2f}s, {expected} frames)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("audio", "scene", "stills", "frames", "mux", "all"))
    parser.add_argument("--build", type=Path, default=BUILDS / "v2")
    parser.add_argument("--episode", type=Path, default=ROOT / "episode.json")
    parser.add_argument("--width", type=int, default=720)
    parser.add_argument("--height", type=int, default=1280)
    parser.add_argument("--engine", choices=("cycles", "workbench"), default="cycles")
    parser.add_argument("--samples", type=int, default=16)
    parser.add_argument("--motion-step", type=int, choices=(1, 2), default=2,
                        help="2 renders animation on twos (12 poses/sec at 24 fps); 1 renders every frame.")
    parser.add_argument("--jobs", type=int, choices=(1, 2, 4), default=2,
                        help="Independent Blender frame-range workers (four CPU threads each).")
    parser.add_argument("--qwen-python", default=str(qwen_python()))
    parser.add_argument("--render-device", choices=RENDER_DEVICES, default="CPU")
    parser.add_argument("--speech-device", default="cpu")
    args = parser.parse_args()
    os.environ.setdefault("LP_NUM_THREADS", "4")
    build = build_directory(args.build)
    args.episode = resolve_build_reference(args.episode)
    blender = tool_path("blender")
    if args.stage in ("audio", "all"):
        run([args.qwen_python, ROOT / "prepare_audio.py", "--episode", args.episode, "--output-dir", build, "--rhubarb", tool_path("rhubarb"), "--device", args.speech_device])
    if args.stage in ("scene", "all"):
        load_inputs(build, args.episode)
        run([blender, "-b", "--disable-autoexec", "-t", "4", "--python-exit-code", "1", "--python", ROOT / "build_scene.py", "--", "--episode", args.episode, "--build", build, "--width", args.width, "--height", args.height, "--engine", args.engine, "--samples", args.samples])
        episode, timeline = load_inputs(build, args.episode)
        (build / "scene_manifest.json").write_text(json.dumps({
            "episode": episode, "timeline": timeline, "width": args.width, "height": args.height,
            "motion_step": args.motion_step, "visual_version": 2,
            "engine": args.engine, "samples": args.samples,
            "source_sha256": {
                name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name in ("build_scene.py", "studio_characters.py")
            }
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.stage in ("frames", "stills", "all"):
        episode, timeline = load_inputs(build, args.episode)
        manifest = json.loads((build / "scene_manifest.json").read_text(encoding="utf-8"))
        if manifest["episode"] != episode or manifest["timeline"] != timeline:
            raise ValueError("Saved scene is stale; run the scene stage first.")
        if args.stage == "stills":
            frames = [36] + [1 + round((t["start"] + min(1.0, t["duration"] / 2)) * episode["fps"]) for t in timeline["turns"]]
            expression = (
                render_expression(args.render_device) + "from pathlib import Path; s=bpy.context.scene; "
                f"[(s.frame_set(f), setattr(s.render, 'filepath', str(Path({str(build)!r}) / ('still_%04d.png' % f))), bpy.ops.render.render(write_still=True)) for f in {frames!r}]"
            )
            run([blender, "-b", "--disable-autoexec", build / "studio.blend", "-t", "4", "--python-exit-code", "1", "--python-expr", expression])
        else:
            step = manifest["motion_step"]
            frame_manifest = build / "frames_manifest.json"
            if frame_manifest.exists():
                frame_manifest.unlink()
            all_frames = list(range(1, round(timeline["duration"] * timeline["fps"]) + 1, step))
            frames = all_frames
            before = scene_hash(build)
            checkpoint = {"scene": manifest, "blend_sha256": before, "render_device": args.render_device}
            checkpoint_file = build / "render_checkpoint.json"
            resumable = checkpoint_file.exists() and json.loads(checkpoint_file.read_text(encoding="utf-8")) == checkpoint
            if resumable:
                frames = [frame for frame in frames if not valid_frame(
                    build / "frames" / f"frame_{frame:04d}.png", manifest["width"], manifest["height"]
                )]
            else:
                for frame in frames:
                    (build / "frames" / f"frame_{frame:04d}.png").unlink(missing_ok=True)
            checkpoint_file.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"Rendering {len(frames)} remaining frames (matching saved-scene checkpoint: {resumable}).", flush=True)
            chunk_size = max(1, math.ceil(len(frames) / args.jobs))
            chunks = [frames[index:index + chunk_size] for index in range(0, len(frames), chunk_size)]

            def render_chunk(chunk):
                log = build / f"render_{chunk[0]:04d}_{chunk[-1]:04d}.log"
                command = [blender, "-b", "--disable-autoexec", build / "studio.blend", "-t", "4",
                           "--python-exit-code", "1", "--python-expr",
                           render_expression(args.render_device, build),
                           "-f", ",".join(map(str, chunk))]
                with log.open("w") as output:
                    print(f"Rendering frames {chunk[0]}–{chunk[-1]}; log: {log}", flush=True)
                    result = subprocess.run(list(map(str, command)), stdout=output, stderr=subprocess.STDOUT)
                if result.returncode:
                    raise RuntimeError(f"Blender exited {result.returncode}; {log}\n" + "\n".join(log.read_text(encoding="utf-8").splitlines()[-30:]))

            with ThreadPoolExecutor(max_workers=args.jobs) as workers:
                pending = {workers.submit(render_chunk, chunk) for chunk in chunks}
                while pending:
                    completed, pending = wait(pending, timeout=60, return_when=FIRST_COMPLETED)
                    for result in completed:
                        result.result()
                    count = sum(valid_frame(
                        build / "frames" / f"frame_{frame:04d}.png", manifest["width"], manifest["height"]
                    ) for frame in all_frames)
                    print(f"Rendered frames: {count}/{len(all_frames)}", flush=True)
            if scene_hash(build) != before:
                raise RuntimeError("Saved scene changed during frame rendering; render again.")
            frame_manifest.write_text(json.dumps({
                "scene": manifest, "blend_sha256": before
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.stage in ("mux", "all"):
        mux(build, args.episode)


if __name__ == "__main__":
    main()
