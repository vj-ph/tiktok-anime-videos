"""Shorten only verified voiced openings to speech plus half a second."""

import argparse
import copy
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import wave

from compose_full import visual_events
from prepare_sample import ROOT, atomic_json, mix_events, sha256_file, write_wav
from reduce_full import SELECTIONS, read_json, review
from revise_reduced import validate_inputs as validate_previous_inputs
from validate_full import audio_info, encoded_events


def shortened_timeline(original, audio_directory):
    result = copy.deepcopy(original)
    first = result["events"][0]
    if first["id"] != "reduced_intro" or first["kind"] != "speech":
        raise ValueError("Expected the verified voiced opening.")
    frames = (first["audio_samples"] + 24000 + 1999) // 2000
    old_frames = first["end_frame"]
    if first["start_frame"] != 0 or not 0 < frames < old_frames:
        raise ValueError("Speech plus 0.5 seconds must shorten the current opening.")
    delta = old_frames - frames
    first.update(end_frame=frames, end=frames / 24, duration=frames / 24,
                 seconds=frames / 24)
    for event in result["events"][1:]:
        start, end = event["start_frame"] - delta, event["end_frame"] - delta
        event.update(start_frame=start, end_frame=end, start=start / 24, end=end / 24)
    for event in result["events"]:
        if event.get("audio"):
            event["audio"] = str(audio_directory / Path(event["audio"]).name)
    result.update(total_frames=original["total_frames"] - delta,
                  duration=(original["total_frames"] - delta) / 24)
    return result


def retimed_document(document, original, timeline):
    old_scenes, scenes = visual_events(original["events"]), visual_events(timeline["events"])
    pattern = (r'(<section id="scene-(\d+)"[^>]*data-start=")([^"]+)'
               r'(" data-duration=")([^"]+)(")')

    def replace(match):
        index = int(match[2])
        assert (float(match[3]), float(match[5])) == (
            old_scenes[index]["start"], old_scenes[index]["duration"])
        scene = scenes[index]
        return f'{match[1]}{scene["start"]}{match[4]}{scene["duration"]}{match[6]}'

    result, count = re.subn(pattern, replace, document)
    assert count == len(scenes)
    for element in ('<div id="root"', '<audio id="sample-audio"'):
        pattern = rf'({element}[^>]*data-duration=")[^"]+(")'
        result, count = re.subn(pattern, lambda m: f'{m[1]}{timeline["duration"]}{m[2]}', result)
        assert count == 1
    clock = f'tl.to(clock, {{ value: {timeline["duration"]}, duration: {timeline["duration"]}, ease: "none" }}, 0);'
    result, count = re.subn(r'tl\.to\(clock, .*?\);', lambda _: clock, result)
    assert count == 1
    pauses = [{"index": index, "start": scene["start"], "duration": scene["duration"]}
              for index, scene in enumerate(scenes) if scene["kind"] == "silence"]
    result, count = re.subn(r'const pauses = .*?;', lambda _: f'const pauses = {json.dumps(pauses)};', result)
    assert count == 1
    return result


def validate_inputs(build):
    pin = read_json(build / "input_pin.json")
    for name, digest in pin["files"].items():
        assert sha256_file(Path(name)) == digest, f"Pinned input changed: {name}"
    previous = Path(pin["previous_build"])
    validate_previous_inputs(previous)
    return previous


def prepare(source, build):
    source, build = source.resolve(), build.resolve()
    if build.exists() or source == build or source in build.parents or build in source.parents:
        raise ValueError("Use a fresh build separate from previous deliveries.")
    validate_previous_inputs(source)
    manifest = read_json(source / "delivery_manifest.json")
    files = {source / name for name in manifest["files"]}
    files.update((source / "delivery_manifest.json", Path(__file__),
                  ROOT / "check_reduced_mobile.cjs"))
    for path in files:
        if path.is_relative_to(source) and str(path.relative_to(source)) in manifest["files"]:
            assert sha256_file(path) == manifest["files"][str(path.relative_to(source))]
    build.mkdir(parents=True)
    atomic_json(build / "input_pin.json", {
        "previous_build": str(source), "files": {str(p): sha256_file(p) for p in sorted(files)}})
    for part in SELECTIONS:
        previous, clip = source / f"teil_{part}", build / f"teil_{part}"
        clip.mkdir()
        shutil.copytree(previous / "audio", clip / "audio")
        shutil.copytree(previous / "portrait", clip / "portrait",
                        ignore=shutil.ignore_patterns(".hyperframes"))
        original = read_json(previous / "timeline.json")
        timeline = shortened_timeline(original, clip / "audio")
        atomic_json(clip / "timeline.json", timeline)
        shutil.copyfile(previous / "sample_content.json", clip / "sample_content.json")
        write_wav(clip / "dialogue.wav", mix_events(timeline["events"]))
        shutil.copyfile(clip / "dialogue.wav", clip / "portrait" / "assets" / "dialogue.wav")
        document = (previous / "portrait" / "index.html").read_text(encoding="utf-8")
        (clip / "portrait" / "index.html").write_text(
            retimed_document(document, original, timeline), encoding="utf-8")
        assets = read_json(previous / "portrait" / "assets_manifest.json")
        assets["dialogue.wav"] = sha256_file(clip / "dialogue.wav")
        atomic_json(clip / "portrait" / "assets_manifest.json", assets)
        receipt = read_json(previous / "composition_receipt.json")
        receipt.update(timeline_sha256=sha256_file(clip / "timeline.json"),
                       generator_sha256=sha256_file(Path(__file__)),
                       scenes=visual_events(timeline["events"]),
                       previous_composition_sha256=sha256_file(previous / "composition_receipt.json"))
        atomic_json(clip / "composition_receipt.json", receipt)
        print(f'Teil {part}: opening {timeline["events"][0]["duration"]:.6f}s; '
              f'video {timeline["duration"]:.6f}s.', flush=True)


def validate_clip(clip, previous):
    original, timeline = read_json(previous / "timeline.json"), read_json(clip / "timeline.json")
    assert timeline == shortened_timeline(original, clip / "audio")
    assert sha256_file(clip / "sample_content.json") == sha256_file(previous / "sample_content.json")
    first, old_first = timeline["events"][0], original["events"][0]
    padding = first["end_frame"] * 2000 - first["audio_samples"]
    assert 24000 <= padding < 26000
    assert audio_info(clip / "dialogue.wav") == timeline["total_frames"] * 2000
    with wave.open(str(clip / "dialogue.wav"), "rb") as current, \
            wave.open(str(previous / "dialogue.wav"), "rb") as old:
        mixed, before = current.readframes(current.getnframes()), old.readframes(old.getnframes())
        assert mixed == mix_events(timeline["events"])
        assert mixed[:first["audio_samples"] * 2] == before[:first["audio_samples"] * 2]
        assert mixed[first["end_frame"] * 4000:] == before[old_first["end_frame"] * 4000:]
    for event in timeline["events"]:
        if event.get("audio"):
            assert sha256_file(Path(event["audio"])) == event["sha256"]
            assert audio_info(Path(event["audio"])) == event["audio_samples"]
    old_document = (previous / "portrait" / "index.html").read_text(encoding="utf-8")
    assert (clip / "portrait" / "index.html").read_text(encoding="utf-8") == retimed_document(
        old_document, original, timeline)
    receipt = read_json(clip / "composition_receipt.json")
    assert receipt["timeline_sha256"] == sha256_file(clip / "timeline.json")
    assert receipt["scenes"] == visual_events(timeline["events"])
    for name, digest in read_json(clip / "portrait" / "assets_manifest.json").items():
        assert sha256_file(clip / "portrait" / "assets" / name) == digest
    return {"part": timeline["part"], "duration": timeline["duration"],
            "total_frames": timeline["total_frames"], "opening_duration": first["duration"],
            "title_audio_duration": first["audio_samples"] / 48000,
            "post_title_padding": padding / 48000,
            "post_intro_pcm": "byte-identical to previous post-intro PCM",
            "all_exercise_durations_and_content": "unchanged"}


def check(build):
    previous, results = validate_inputs(build), []
    for part in SELECTIONS:
        clip = build / f"teil_{part}"
        detail = validate_clip(clip, previous / f"teil_{part}")
        process = subprocess.run([
            sys.executable, "-X", "utf8", str(ROOT / "hyperframes_local.py"),
            "check", str(clip / "portrait"), "--json", "--at-transitions", "--snapshots",
            "--no-browser-gpu", "--timeout", "4m"],
            capture_output=True, text=True, encoding="utf-8")
        (clip / "browser_check.log").write_text(process.stdout + process.stderr, encoding="utf-8")
        process.check_returncode()
        start = process.stdout.find("\n{")
        report = json.loads(process.stdout[start + 1:] if start >= 0 else process.stdout)
        assert report["ok"] and not report["browserSkipped"]
        for name in ("runtime", "layout", "contrast", "audio"):
            assert report[name]["ok"] and report[name]["errorCount"] == 0
        atomic_json(clip / "browser_check.json", report)
        subprocess.run(["node", str(ROOT / "check_reduced_mobile.cjs"),
                        str(clip / "portrait" / "index.html"), str(clip / "mobile_layout.json")], check=True)
        results.append(detail)
        print(f"Teil {part}: source, timing, browser and mobile gates passed.", flush=True)
    atomic_json(build / "pre_render_checks.json", {"clips": results})
    review(build)


def render(build):
    previous = validate_inputs(build)
    assert (build / "pre_render_checks.json").is_file()
    for part in SELECTIONS:
        clip, source = build / f"teil_{part}", previous / f"teil_{part}"
        detail = validate_clip(clip, source)
        target = clip / "production_portrait.mp4"
        if target.exists():
            raise ValueError(f"Preserving existing render: {target}")
        timeline, old = read_json(clip / "timeline.json"), read_json(source / "timeline.json")
        new_intro, old_intro = timeline["events"][0]["end_frame"], old["events"][0]["end_frame"]
        command = [
            "ffmpeg", "-nostdin", "-v", "warning", "-stats", "-i", str(source / target.name),
            "-i", str(clip / "dialogue.wav"), "-map", "0:v:0", "-map", "1:a:0",
            "-vf", f"select='lt(n,{new_intro})+gte(n,{old_intro})',setpts=N/(24*TB)",
            "-c:v", "libx264", "-threads", "2", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-r", "24", "-frames:v", str(timeline["total_frames"]),
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", str(timeline["duration"]),
            "-movflags", "+faststart", str(target)]
        atomic_json(clip / "render_command.json", {
            "command": command, "source_video_sha256": sha256_file(source / target.name),
            "source_frame_ranges": [[0, new_intro], [old_intro, old["total_frames"]]]})
        with (clip / "render.log").open("w", encoding="utf-8") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        print(f'Teil {part}: rendered {detail["duration"]:.6f}s.', flush=True)


def verify(build):
    previous, results = validate_inputs(build), []
    for part in SELECTIONS:
        clip = build / f"teil_{part}"
        detail = validate_clip(clip, previous / f"teil_{part}")
        detail["encoded"] = encoded_events(clip, read_json(clip / "timeline.json"), "portrait")
        metadata = json.loads(subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,duration",
            "-of", "json", str(clip / "production_portrait.mp4")],
            check=True, capture_output=True, text=True).stdout)
        assert all(0 < float(item["duration"]) < 180
                   for item in [metadata["format"], *metadata["streams"]])
        detail["durations"] = metadata
        atomic_json(clip / "validation.json", detail)
        results.append(detail)
        print(f"Teil {part}: full decode and every encoded event passed.", flush=True)
    review(build, encoded=True)
    validate_inputs(build)
    files = {name: sha256_file(build / name) for name in ("input_pin.json", "pre_render_checks.json")}
    for part in SELECTIONS:
        clip = build / f"teil_{part}"
        for name in ("production_portrait.mp4", "timeline.json", "sample_content.json", "dialogue.wav",
                     "composition_receipt.json", "browser_check.json", "mobile_layout.json",
                     "browser_visual_review.json", "export_visual_review.json", "validation.json",
                     "render_command.json", "opening.png"):
            files[str((clip / name).relative_to(build))] = sha256_file(clip / name)
    atomic_json(build / "delivery_manifest.json", {
        "revision": "Opening equals complete title audio plus 0.5s, rounded up to 24 fps.",
        "previous_build": str(previous), "previous_sources_preserved": True,
        "post_intro_audio_and_exercise_durations": "unchanged", "clips": results, "files": files,
        "inherited_title_review": str(previous / "title_speech_review.json"),
        "inherited_audio_review": read_json(previous / "delivery_manifest.json")["inherited_audio_review"],
        "publication": "not uploaded"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "check", "render", "verify"))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--build", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        if not args.source:
            parser.error("prepare requires --source")
        prepare(args.source, args.build)
    else:
        globals()[args.action](args.build.resolve())
