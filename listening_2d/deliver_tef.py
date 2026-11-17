"""Verify, render and freeze the full-resolution TEF review video."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import wave

from prepare_tef import FPS, FRAME_SAMPLES, RATE, ROOT, TIMINGS, atomic_json, chime_enabled, read, reveal_mode, sha256_file, verify_files


def run(command, log):
    log = Path(log)
    if log.exists():
        number = 2
        while log.with_name(f"{log.stem}_{number}{log.suffix}").exists():
            number += 1
        log = log.with_name(f"{log.stem}_{number}{log.suffix}")
    print("Running: " + subprocess.list2cmdline(list(map(str, command))), flush=True)
    with log.open("w", encoding="utf-8") as handle:
        subprocess.run(list(map(str, command)), stdout=handle, stderr=subprocess.STDOUT, check=True)
    return log


def validate(build):
    pin = read(build / "input_pin.json")
    verify_files(pin["files"])
    timeline, content = read(build / "timeline.json"), read(build / "content.json")
    manifest = read(build / "audio_manifest.json")
    if timeline["total_frames"] >= 21600 or len(content["cards"]) != 16:
        raise ValueError("Expected 16 questions and an entire video strictly below 15 minutes.")
    chime = chime_enabled(content.get("episode", {}))
    if timeline["chime_enabled"] != chime or chime_enabled(timeline) != chime or timeline["language"] != "fr":
        raise ValueError("Expected French audio with the approved reveal-chime setting.")
    events = timeline["events"]
    mode = reveal_mode(timeline)
    if mode != reveal_mode(content.get("episode", {})):
        raise ValueError("Timeline and approved episode disagree about answer reveal timing.")
    cursor, silent_frames, recordings, instructions, chimes = 0, 0, [], [], []
    with wave.open(str(build / "dialogue.wav")) as audio:
        if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth(), audio.getnframes()) != (
                RATE, 1, 2, timeline["total_frames"] * FRAME_SAMPLES):
            raise ValueError("The lossless mix and measured frame clock disagree.")
        for event in events:
            if event["start_frame"] != cursor or event["end_frame"] <= cursor:
                raise ValueError("Timeline has a gap, overlap or reversed event.")
            samples = (event["end_frame"] - cursor) * FRAME_SAMPLES
            actual = audio.readframes(samples)
            if event["kind"] == "silence":
                if any(actual):
                    raise ValueError(f"Protected silence is not digitally silent: {event['id']}")
                if event["id"] != "outro":
                    family = event["family"]
                    seconds = TIMINGS[family][0 if event["id"].startswith("read_") else 1]
                    if samples != seconds * RATE:
                        raise ValueError("A published sample pause was shortened or extended.")
                    silent_frames += event["end_frame"] - cursor
            else:
                item = manifest[event["audio_id"]]
                verify_files({item["audio"]: item["sha256"]})
                with wave.open(item["audio"]) as clip:
                    expected = clip.readframes(clip.getnframes())
                if actual != expected + b"\0" * (len(actual) - len(expected)):
                    raise ValueError(f"The mix changed/overlapped speech: {event['id']}")
                if event["kind"] == "recording":
                    recordings.append(event["audio_id"])
                if event["kind"] == "sfx":
                    chimes.append(event["id"])
                    if not chime or event["audio_id"] != "reveal_chime":
                        raise ValueError("Unexpected sound effect outside the approved reveal cue.")
                if event["kind"] in ("recording", "sfx"):
                    verify_files({item["source_audio"]: item["source_sha256"]})
                if event["id"].startswith("instruction_"):
                    instructions.append(event["family"])
            cursor = event["end_frame"]
    if len(recordings) != 14 or len(set(recordings)) != 14 or instructions != list(TIMINGS):
        raise ValueError("A recording was replayed/omitted or a complete instruction is missing.")
    if silent_frames != 320 * FPS:
        raise ValueError("Expected 125 reading plus 195 response seconds.")
    if cursor != timeline["total_frames"]:
        raise ValueError("Timeline event durations disagree with the complete frame clock.")
    expected_chimes = [f"chime_{r['id']}" for g in content["groups"] for r in g["recordings"]] if chime else []
    if chimes != expected_chimes:
        raise ValueError("Play exactly one approved chime per exercise, including shared pairs.")
    for group in content["groups"]:
        instruction = next(e for e in events if e["id"] == "instruction_" + group["family"])
        if instruction["text"] != group["instruction"]["tts_text"]:
            raise ValueError("The spoken instruction differs from the approved bank.")
        for recording in group["recordings"]:
            start = next(n for n, e in enumerate(events) if e["id"] == "read_" + recording["id"])
            seq = events[start:start + 3]
            if ([e["kind"] for e in seq] != ["silence", "recording", "silence"]
                    or any(e["numbers"] != recording["numbers"] for e in seq)
                    or instruction["end_frame"] > seq[0]["start_frame"]):
                raise ValueError("Instruction, reading, single playback and response order changed.")
            if mode == "after_exercise":
                reveal_start = start + 3
                speech_start = seq[-1]["end_frame"]
                if chime:
                    cue = events[reveal_start]
                    if (cue["id"] != f"chime_{recording['id']}" or cue["kind"] != "sfx"
                            or cue.get("reveal_numbers") != recording["numbers"]
                            or cue["start_frame"] != speech_start):
                        raise ValueError("The reveal chime must follow the full response silence.")
                    speech_start = cue["end_frame"]
                    reveal_start += 1
                reveals = events[reveal_start:reveal_start + len(recording["numbers"])]
                if ([e["id"] for e in reveals] != [f"solution_{n}" for n in recording["numbers"]]
                        or any(e.get("reveal_numbers") != recording["numbers"] for e in reveals)
                        or reveals[0]["start_frame"] != speech_start):
                    raise ValueError("Reveal every exercise/pair immediately after its full response pause.")
    solutions = [e for e in events if e["id"].startswith("solution_")]
    if [e["number"] for e in solutions] != list(range(1, 17)):
        raise ValueError("Every numbered correction must appear exactly once and in source order.")
    if mode == "after_attempt":
        last_answer = max(e["end_frame"] for e in events if e["id"].startswith("answer_"))
        intro = next(e for e in events if e["id"] == "solutions_intro")
        if (intro["start_frame"] != last_answer or solutions[0]["start_frame"] != intro["end_frame"]
                or any(e["start_frame"] < last_answer for e in solutions)):
            raise ValueError("Solutions must follow the full final response interval.")
    elif any(e["id"] == "solutions_intro" for e in events):
        raise ValueError("Immediate-correction practice must omit the final-corrections introduction.")
    report = {"question_count": 16, "unique_recordings": 14, "instruction_count": 8,
              "reading_silence_seconds": 125, "response_silence_seconds": 195,
              "lossless_silences_digital_zero": True, "all_mix_events_exact": True,
              "answer_reveal": mode,
              "reveal_chime_count": len(chimes),
              "frames": cursor, "fps": FPS, "duration": cursor / FPS,
              "timeline_sha256": sha256_file(build / "timeline.json"),
              "dialogue_sha256": sha256_file(build / "dialogue.wav")}
    atomic_json(build / "source_validation.json", report)
    print(f"TEF source/audio validation passed: {cursor / FPS:.3f}s including every pause and CTA.", flush=True)
    return report


def check(build, layout, validator=validate):
    validator(build)
    run(["node", ROOT / "check_tef_layout.cjs", build, layout], build / f"geometry_{layout}.log")
    env = dict(__import__("os").environ)
    env.update(HYPERFRAMES_NO_TELEMETRY="1", DO_NOT_TRACK="1", HYPERFRAMES_NO_UPDATE_CHECK="1",
               HYPERFRAMES_NO_AUTO_INSTALL="1", HYPERFRAMES_SKIP_SKILLS="1",
               HYPERFRAMES_NO_ORPHAN_CLEANUP="1")
    log = build / f"check_{layout}.log"
    with log.open("w", encoding="utf-8") as output:
        subprocess.run(["npm", "run", "check"], cwd=build / layout, env=env,
                       stdout=output, stderr=subprocess.STDOUT, check=True)
    reports = list((build / layout / ".hyperframes" / "artifacts" / "checks").glob("*.json"))
    report_path = max(reports, key=lambda p: p.stat().st_mtime_ns)
    report = read(report_path)
    if not report["ok"] or report.get("browserSkipped", False):
        raise ValueError(f"Native HyperFrames gate failed: {report_path}")
    geometry = read(build / f"geometry_{layout}.json")
    times = sorted({c["time"] for c in geometry["captures"]})
    snapshot_log = build / f"native_snapshots_{layout}.log"
    snapshot_log = run([sys.executable, ROOT / "hyperframes_local.py", "snapshot", build / layout,
         "--at", ",".join(str(t) for t in times), "--no-end", "--no-browser-gpu",
         "--output", build / f"native_{layout}", "--json"], snapshot_log)
    text = snapshot_log.read_text(encoding="utf-8")
    native = json.loads(text[text.index('\n{\n  "ok":') + 1:])
    if not native["ok"] or len(native["frames"]) != len(times):
        raise ValueError("The native renderer did not capture every requested review frame.")
    for capture in geometry["captures"]:
        match = min(native["frames"], key=lambda f: abs(f["time"] - capture["time"]))
        if abs(match["time"] - capture["time"]) > .00051:
            raise ValueError("A native frame is missing at a protected review boundary.")
        capture["native_file"] = match["path"]
        capture["native_sha256"] = sha256_file(Path(match["path"]))
    atomic_json(build / f"native_captures_{layout}.json", geometry["captures"])
    atomic_json(build / f"checks_{layout}.json", {
        "report_path": str(report_path), "report_sha256": sha256_file(report_path),
        "html_sha256": sha256_file(build / layout / "index.html"),
        "geometry_sha256": sha256_file(build / f"geometry_{layout}.json"),
        "native_captures_sha256": sha256_file(build / f"native_captures_{layout}.json"),
        "composition_sha256": sha256_file(build / "composition_receipt.json"),
        "source_validation_sha256": sha256_file(build / "source_validation.json")})
    print(f"TEF {layout} native checks passed.", flush=True)


def render(build, layout):
    validate(build)
    if read(build / "composition_receipt.json").get("layout_only"):
        raise ValueError("A silent layout fixture must never be rendered as the measured video.")
    receipt = read(build / f"checks_{layout}.json")
    verify_files({receipt["report_path"]: receipt["report_sha256"],
                  str(build / layout / "index.html"): receipt["html_sha256"],
                  str(build / "composition_receipt.json"): receipt["composition_sha256"],
                  str(build / f"native_captures_{layout}.json"): receipt["native_captures_sha256"],
                  str(build / f"geometry_{layout}.json"): receipt["geometry_sha256"]})
    for name, info in read(build / "composition_receipt.json")["layouts"][layout]["sources"].items():
        verify_files({str(build / layout / "assets" / name): info["sha256"]})
    visual = read(build / "visual_review.json")
    if not visual.get(layout, {}).get("contact_sheets_inspected"):
        raise ValueError("Inspect native contact sheets before the complete review render.")
    final = build / f"preview_{layout}.mp4"
    master = build / f"render_{layout}.mp4"
    if final.exists() or master.exists():
        raise ValueError("Preserve existing exports; choose a fresh revision.")
    run([sys.executable, "-X", "utf8", ROOT / "hyperframes_local.py", "render", build / layout,
         "--fps", "24", "--quality", "delivery", "--workers", "4", "--no-browser-gpu",
         "--output", master], build / f"render_{layout}.log")
    duration = read(build / "timeline.json")["duration"]
    run(["ffmpeg", "-nostdin", "-v", "error", "-i", master, "-i", build / "dialogue.wav",
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-ar", "48000", "-ac", "1", "-t", str(duration), "-movflags", "+faststart", final],
        build / f"mux_{layout}.log")
    print(f"TEF full-resolution review export ready: {final}", flush=True)


def encoded(build, layout, validator=validate):
    import numpy as np
    from PIL import Image, ImageChops, ImageStat
    expected = validator(build)
    video = build / f"preview_{layout}.mp4"
    probe = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)], text=True))
    stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    audio_stream = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    dimensions = (1920, 1080) if layout == "landscape" else (1080, 1920)
    if (stream["width"], stream["height"]) != dimensions or stream["r_frame_rate"] != "24/1":
        raise ValueError("Encoded native dimensions or frame rate changed.")
    if int(stream["nb_frames"]) != expected["frames"]:
        raise ValueError("Encoded frame count differs from the measured timeline.")
    durations = [float(probe["format"]["duration"]), float(stream["duration"]), float(audio_stream["duration"])]
    limit = expected.get("duration_limit_seconds", 900)
    if max(durations) >= limit or abs(durations[1] - expected["duration"]) > .001:
        raise ValueError(f"Video, audio and container must all remain below {limit} seconds.")
    folder = build / f"encoded_{layout}"
    folder.mkdir(exist_ok=True)
    decoded = folder / "decoded.wav"
    if not decoded.exists():
        run(["ffmpeg", "-nostdin", "-v", "error", "-i", video,
             "-map", "0:v:0", "-f", "null", "-", "-map", "0:a:0", "-ar", "48000", "-ac", "1",
             "-c:a", "pcm_s16le", decoded], build / f"decode_{layout}.log")
    with wave.open(str(build / "dialogue.wav")) as w:
        reference = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    with wave.open(str(decoded)) as w:
        actual = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    if abs(len(actual) - len(reference)) > 1024:
        raise ValueError("Decoded AAC sample count is inconsistent with its source.")
    size = min(len(reference), len(actual))
    correlation = float(np.corrcoef(reference[:size].astype(float), actual[:size].astype(float))[0, 1])
    if correlation < .998:
        raise ValueError(f"Encoded speech/mix correlation is too low: {correlation}")
    silent = []
    for event in read(build / "timeline.json")["events"]:
        if event["kind"] == "silence":
            start = event["start_frame"] * FRAME_SAMPLES + 4096
            end = event["end_frame"] * FRAME_SAMPLES - 4096
            peak = int(np.max(np.abs(actual[start:end].astype(np.int32))))
            if peak > 8:
                raise ValueError(f"Unexpected audio during encoded silence {event['id']}: peak {peak}")
            silent.append({"id": event["id"], "peak_pcm16": peak, "codec_guard_samples": 4096})
    comparisons, title_boundaries, reveal_boundaries = [], [], []
    for n, capture in enumerate(read(build / f"native_captures_{layout}.json")):
        target = folder / f"frame-{n:03d}.png"
        if not target.exists():
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", str(capture["time"]),
                            "-i", str(video), "-frames:v", "1", str(target)], check=True)
        verify_files({capture["native_file"]: capture["native_sha256"]})
        with Image.open(capture["native_file"]) as native, Image.open(target) as encoded_frame:
            difference = ImageChops.difference(native.convert("RGB"), encoded_frame.convert("RGB"))
            error = sum(ImageStat.Stat(difference).mean) / 3
            if error >= 5:
                raise ValueError(f"Encoded frame differs from the inspected browser: {capture['event']}, {error}")
            if capture.get("reveal_boundary"):
                region_errors = []
                for box in capture["reveal_regions"]:
                    region = ImageChops.difference(native.convert("RGB").crop(box),
                                                   encoded_frame.convert("RGB").crop(box))
                    region_error = sum(ImageStat.Stat(region).mean) / 3
                    if region_error >= 5:
                        raise ValueError(f"Encoded reveal is early/late or incorrect at frame {capture['frame']}.")
                    region_errors.append(region_error)
                reveal_boundaries.append({"frame": capture["frame"],
                                          "revealed_questions": capture["revealed_questions"],
                                          "answer_region_mae": region_errors})
            if capture.get("selector"):
                green = np.array([210, 233, 223])
                pixels = np.asarray(native.convert("RGB")).astype(np.int16)
                mask = np.max(np.abs(pixels - green), axis=2) < 12
                if int(mask.sum()) < 50:
                    raise ValueError("A native opening word has no measurable highlight.")

                def fraction(image):
                    colors = np.asarray(image.convert("RGB")).astype(np.int16)
                    return float(np.mean((np.max(np.abs(colors - green), axis=2) < 25)[mask]))

                visible = fraction(encoded_frame)
                if visible < .85:
                    raise ValueError("An encoded opening word lost its measured highlight.")
                word = next(w for w in read(build / "composition_receipt.json")["word_mappings"]["title"]
                            if w["selector"] == capture["selector"])
                checks = {"selector": capture["selector"], "first_frame": capture["frame"],
                          "first_frame_green_fraction": visible}
                import math
                for label, frame in (("before", capture["frame"] - 1), ("after", math.ceil(word["end"] * FPS))):
                    image_path = folder / f"title-{word['index']}-{label}.png"
                    if not image_path.exists():
                        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", str(frame / FPS),
                                        "-i", str(video), "-frames:v", "1", str(image_path)], check=True)
                    with Image.open(image_path) as image:
                        score = fraction(image)
                    if score > .15:
                        raise ValueError(f"Encoded opening highlight extends beyond its alignment: {label}")
                    checks[label] = {"frame": frame, "green_fraction": score,
                                     "image_sha256": sha256_file(image_path)}
                title_boundaries.append(checks)
        comparisons.append({**capture, "encoded_file": str(target), "mean_absolute_rgb_error": error,
                            "encoded_sha256": sha256_file(target)})
    chime_audio = []
    events = read(build / "timeline.json")["events"]
    for index, event in enumerate(events):
        if event["kind"] != "sfx":
            continue
        speech = events[index + 1]
        scores = {}
        for label, item in (("chime", event), ("following_tts", speech)):
            start = item["start_frame"] * FRAME_SAMPLES
            end = start + item["audio_samples"]
            score = float(np.corrcoef(reference[start:end].astype(float),
                                      actual[start:end].astype(float))[0, 1])
            if not np.isfinite(score) or score < .995:
                raise ValueError(f"Encoded {label} is missing, overlapped or shifted: {event['id']}")
            scores[label + "_correlation"] = score
        chime_audio.append({"id": event["id"], "start_frame": event["start_frame"],
                            "tts_start_frame": speech["start_frame"], **scores})
    report = {"layout": layout, "video": str(video), "video_sha256": sha256_file(video),
              "frames": expected["frames"], "dimensions": list(dimensions), "durations": durations,
              "full_video_decode": True, "audio_correlation": correlation,
              "opening_word_boundary_checks": title_boundaries,
              "reveal_boundary_checks": reveal_boundaries,
              "chime_audio_checks": chime_audio,
              "silent_intervals": silent, "comparisons": comparisons,
              "human_listening": False, "status": "review_export_not_publication"}
    atomic_json(build / f"encoded_checks_{layout}.json", report)
    print(f"TEF encoded {layout}: complete decode, {len(comparisons)} frame comparisons, "
          f"{len(silent)} silence intervals, correlation {correlation:.6f}.", flush=True)


def freeze(build):
    validate(build)
    visual = read(build / "visual_review.json")
    for layout in ("landscape", "portrait"):
        report = read(build / f"encoded_checks_{layout}.json")
        verify_files({report["video"]: report["video_sha256"]})
        if not visual.get(layout, {}).get("encoded_contact_sheets_inspected"):
            raise ValueError("Inspect both encoded contact sheets before freezing.")
    source = build / "delivery_sources"
    source.mkdir(exist_ok=True)
    programs = [ROOT / n for n in ("prepare_tef.py", "compose_tef.py", "deliver_tef.py",
                                  "check_tef_layout.cjs", "test_tef.py", "hyperframes_local.py")]
    for program in programs:
        shutil.copyfile(program, source / program.name)
    for name in ("package.json", "package-lock.json"):
        shutil.copyfile(ROOT / name, source / name)
    shutil.copyfile(ROOT / "composition" / "index.html", source / "base_composition.html")
    narrator = read(build / "voice_references.json")["narrator"]
    shutil.copyfile(narrator["audio"], source / "narrator_reference.wav")
    posts = build / "post_drafts"
    posts.mkdir(exist_ok=True)
    episode_id = read(build / "content.json")["episode"].get("id", "tef_canada_listening_01")
    for name in ("tiktok.txt", "instagram.txt", "youtube.txt", "thumbnail_youtube.jpg",
                 "thumbnail_tiktok.jpg", "thumbnail_instagram.jpg", "thumbnail_provenance.json"):
        shutil.copyfile(ROOT.parent / "posts" / episode_id / name, posts / name)
    files = {str(p.relative_to(build)): sha256_file(p) for p in build.rglob("*")
             if p.is_file() and ".hyperframes" not in p.parts
             and p.name != "delivery_manifest.json" and p.suffix != ".log"}
    atomic_json(build / "delivery_manifest.json", {
        "scope": "Full-resolution reduced TEF listening review: 16 questions, eight task families",
        "files": files, "inputs": read(build / "input_pin.json"),
        "human_listening": False, "publication": "Not uploaded",
        "duration": read(build / "timeline.json")["duration"]})
    verify_files({str(build / name): digest for name, digest in files.items()})
    print(f"TEF review delivery frozen: {len(files)} verified files.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("validate", "check", "render", "encoded", "freeze"))
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--layout", choices=("landscape", "portrait"))
    args = parser.parse_args()
    build = args.build.resolve()
    if args.stage in ("validate", "freeze"):
        {"validate": validate, "freeze": freeze}[args.stage](build)
    else:
        if not args.layout:
            parser.error("--layout is required for this stage")
        {"check": check, "render": render, "encoded": encoded}[args.stage](build, args.layout)
