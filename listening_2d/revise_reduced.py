"""Voice and simplify reduced openings, and enlarge portrait exercise text."""

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
from prepare_sample import (ROOT, MODEL, atomic_json, mix_events, normalize,
                            prepare_turn_audio, sha256_file, synthesize,
                            tempo_turn_audio, write_wav)
from reduce_full import INTRO_FRAMES, SELECTIONS, check_source, read_json, review
from validate_full import audio_info, encoded_events

NUMBERS = {1: "eins", 2: "zwei", 3: "drei", 4: "vier"}
MOBILE_STYLES = """
    html[data-resolution="portrait"] .scene h2 { font-size: 56px; }
    html[data-resolution="portrait"] .scene .option { font-size: 48px;
      padding: 18px 20px; margin-bottom: 18px; gap: 18px; }
    html[data-resolution="portrait"] .pair h2 { font-size: 42px; }
    html[data-resolution="portrait"] .pair .option { font-size: 40px;
      padding: 12px 16px; margin-bottom: 12px; gap: 16px; }
    html[data-resolution="portrait"] .pair .phase { font-size: 32px; }
    html[data-resolution="portrait"] .matching h2 { font-size: 48px; }
    html[data-resolution="portrait"] .matching .option { font-size: 40px;
      padding: 10px 16px; margin-bottom: 10px; gap: 16px; }
    html[data-resolution="portrait"] .matching .phase { font-size: 32px; }
"""


def title_text(part):
    return f"Ö I F B eins Hören. Teil {NUMBERS[part]}."


def revised_document(document):
    opening = re.search(r'(<section id="scene-0"(?=[ >]).*?</section>)', document, re.S)
    if not opening:
        raise ValueError("Missing reduced opening scene.")
    body = opening.group(1)
    body, counts = re.subn(r"<p>Aufgaben .*?</p>", "", body, count=1, flags=re.S)
    body, pauses = re.subn(r"<p>Die ursprünglichen Lese- und Antwortpausen bleiben erhalten\.</p>",
                          "", body, count=1)
    if (counts, pauses) != (1, 1):
        raise ValueError("Opening no longer matches the approved revision source.")
    result = document[:opening.start()] + body + document[opening.end():]
    return result.replace("  </style>", MOBILE_STYLES + "  </style>", 1)


def revised_timeline(original, audio_directory, title):
    if original["part"] != title["part"] or title["text"] != title_text(original["part"]):
        raise ValueError("Wrong title/section binding.")
    if not 0 < title["frames"] <= INTRO_FRAMES * 2000:
        raise ValueError("Title speech must fit the unchanged six-second opening.")
    result = copy.deepcopy(original)
    first = result["events"][0]
    if (first["kind"], first["end_frame"]) != ("silence", INTRO_FRAMES):
        raise ValueError("Expected the approved six-second silent opening.")
    first.update(kind="speech", audio_id="reduced_intro", text=title["text"],
                 speaker="narrator", audio=str(audio_directory / "reduced_intro.wav"),
                 audio_samples=title["frames"], sha256=title["sha256"])
    for event in result["events"][1:]:
        if event.get("audio"):
            event["audio"] = str(audio_directory / Path(event["audio"]).name)
    return result


def verify_previous(source):
    full = check_source(source)
    manifest = read_json(source / "delivery_manifest.json")
    for name, digest in manifest["files"].items():
        assert sha256_file(source / name) == digest, f"Changed approved short: {name}"
    return full


def prepare(source, build):
    source, build = source.resolve(), build.resolve()
    if build.exists() or source == build or source in build.parents or build in source.parents:
        raise ValueError("Choose a fresh build separate from the approved shorts.")
    full = verify_previous(source)
    narrator = read_json(full / "voice_references.json")["narrator"]
    files = {source / name for name in read_json(source / "delivery_manifest.json")["files"]}
    files.update((source / "delivery_manifest.json", source / "input_pin.json",
                  ROOT / "revise_reduced.py", ROOT / "check_reduced_mobile.cjs"))
    files.update(Path(item["path"]) for item in narrator.values())
    build.mkdir(parents=True)
    atomic_json(build / "input_pin.json", {
        "previous_build": str(source), "full_build": str(full), "narrator": narrator,
        "files": {str(path): sha256_file(path) for path in sorted(files)}})
    turns = [{"id": f"title_{part}", "part": part, "speaker": "narrator",
              "name": "narrator", "text": title_text(part), "pause_after": 0}
             for part in SELECTIONS]
    atomic_json(build / "title_speech_plan.json", {"turns": turns, "atempo": 0.8})
    audio = build / "audio"
    audio.mkdir()
    binding = {key: item["path"] for key, item in narrator.items()}
    raw = synthesize({"language": "de", "voices": {"narrator": binding}, "turns": turns},
                     ROOT, audio, MODEL, "cpu", 8)
    measured = {}
    for turn, generated in zip(turns, raw):
        cleaned = prepare_turn_audio(turn["id"], generated, audio)
        slowed = tempo_turn_audio(turn["id"], cleaned, audio, 0.8)
        target = audio / f"{turn['id']}.wav"
        info = normalize(Path(slowed["audio"]), target)
        measured[str(turn["part"])] = {
            **turn, **info, "audio": str(target), "sha256": sha256_file(target),
            "atempo": 0.8, "tempo_processing": slowed["tempo_processing"],
            "audio_chain": {stage: {"path": item["audio"], "sha256": sha256_file(Path(item["audio"]))}
                            for stage, item in (("raw", generated), ("prepared", cleaned),
                                                ("slowed", slowed))}}
    atomic_json(build / "title_audio_manifest.json", measured)
    for part in SELECTIONS:
        previous, clip = source / f"teil_{part}", build / f"teil_{part}"
        clip.mkdir()
        shutil.copytree(previous / "audio", clip / "audio")
        shutil.copytree(previous / "portrait", clip / "portrait",
                        ignore=shutil.ignore_patterns(".hyperframes"))
        title = measured[str(part)]
        shutil.copyfile(title["audio"], clip / "audio" / "reduced_intro.wav")
        timeline = revised_timeline(read_json(previous / "timeline.json"), clip / "audio", title)
        atomic_json(clip / "timeline.json", timeline)
        shutil.copyfile(previous / "sample_content.json", clip / "sample_content.json")
        write_wav(clip / "dialogue.wav", mix_events(timeline["events"]))
        shutil.copyfile(clip / "dialogue.wav", clip / "portrait" / "assets" / "dialogue.wav")
        document = revised_document((previous / "portrait" / "index.html").read_text(encoding="utf-8"))
        (clip / "portrait" / "index.html").write_text(document, encoding="utf-8")
        assets = read_json(previous / "portrait" / "assets_manifest.json")
        assets["dialogue.wav"] = sha256_file(clip / "dialogue.wav")
        atomic_json(clip / "portrait" / "assets_manifest.json", assets)
        receipt = read_json(previous / "composition_receipt.json")
        receipt.update(timeline_sha256=sha256_file(clip / "timeline.json"),
                       generator_sha256=sha256_file(Path(__file__)),
                       scenes=visual_events(timeline["events"]),
                       previous_composition_sha256=sha256_file(previous / "composition_receipt.json"))
        atomic_json(clip / "composition_receipt.json", receipt)
        print(f"Teil {part}: {title['wav_duration']:.3f}s title in unchanged 6s opening; "
              f"video {timeline['duration']:.3f}s.", flush=True)


def validate_clip(clip, previous):
    timeline, original = read_json(clip / "timeline.json"), read_json(previous / "timeline.json")
    titles = read_json(clip.parent / "title_audio_manifest.json")
    title = titles[str(timeline["part"])]
    assert title["atempo"] == 0.8 and title["tempo_processing"]["filter"] == "atempo=0.8"
    assert sha256_file(Path(title["audio"])) == title["sha256"]
    for item in title["audio_chain"].values():
        assert sha256_file(Path(item["path"])) == item["sha256"]
    assert timeline == revised_timeline(original, clip / "audio", title)
    assert sha256_file(clip / "sample_content.json") == sha256_file(previous / "sample_content.json")
    assert audio_info(clip / "dialogue.wav") == timeline["total_frames"] * 2000
    with wave.open(str(clip / "dialogue.wav"), "rb") as current, \
            wave.open(str(previous / "dialogue.wav"), "rb") as old:
        mixed = current.readframes(current.getnframes())
        before = old.readframes(old.getnframes())
        assert mixed == mix_events(timeline["events"])
        assert mixed[INTRO_FRAMES * 4000:] == before[INTRO_FRAMES * 4000:]
    for event in timeline["events"]:
        if event.get("audio"):
            assert sha256_file(Path(event["audio"])) == event["sha256"]
            assert audio_info(Path(event["audio"])) == event["audio_samples"]
    document = (clip / "portrait" / "index.html").read_text(encoding="utf-8")
    assert document == revised_document((previous / "portrait" / "index.html").read_text(encoding="utf-8"))
    receipt = read_json(clip / "composition_receipt.json")
    assert receipt["timeline_sha256"] == sha256_file(clip / "timeline.json")
    assert receipt["scenes"] == visual_events(timeline["events"])
    for name, digest in read_json(clip / "portrait" / "assets_manifest.json").items():
        assert sha256_file(clip / "portrait" / "assets" / name) == digest
    return {"part": timeline["part"], "duration": timeline["duration"],
            "total_frames": timeline["total_frames"],
            "title": {"text": title["text"], "wav_duration": title["wav_duration"],
                      "sha256": title["sha256"], "atempo": 0.8},
            "post_intro_pcm": "byte-identical", "task_content_and_timing": "unchanged",
            "selected_numbers": receipt["selected_numbers"]}


def validate_inputs(build):
    pin = read_json(build / "input_pin.json")
    for name, digest in pin["files"].items():
        assert sha256_file(Path(name)) == digest, f"Pinned input changed: {name}"
    source = Path(pin["previous_build"])
    verify_previous(source)
    return source


def speech_review(build):
    from faster_whisper import WhisperModel

    model = WhisperModel("small", device="cpu", compute_type="int8",
                         cpu_threads=4, local_files_only=True)
    results = []
    for part, title in read_json(build / "title_audio_manifest.json").items():
        assert sha256_file(Path(title["audio"])) == title["sha256"]
        segments, _ = model.transcribe(title["audio"], language="de", beam_size=5, vad_filter=False)
        recognized = " ".join(segment.text.strip() for segment in segments)
        results.append({"part": int(part), "expected": title["text"],
                        "recognized": recognized, "audio_sha256": title["sha256"]})
        print(f"Title {part}: {recognized}", flush=True)
    atomic_json(build / "title_speech_review.json", {
        "model": "faster-whisper-small", "scope": "Independent unprompted ASR, not human listening.",
        "titles": results})


def check(build):
    source, results = validate_inputs(build), []
    for part in SELECTIONS:
        clip = build / f"teil_{part}"
        detail = validate_clip(clip, source / f"teil_{part}")
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
        detail["browser_checks"] = "passed"
        detail["mobile_layout"] = read_json(clip / "mobile_layout.json")
        results.append(detail)
        print(f"Teil {part}: source, browser and mobile typography checks passed.", flush=True)
    atomic_json(build / "pre_render_checks.json", {"clips": results})
    review(build)


def render(build):
    source = validate_inputs(build)
    assert (build / "pre_render_checks.json").is_file()
    for part in SELECTIONS:
        clip = build / f"teil_{part}"
        validate_clip(clip, source / f"teil_{part}")
        target = clip / "production_portrait.mp4"
        if target.exists():
            raise ValueError(f"Preserving existing render: {target}")
        command = [
            sys.executable, "-X", "utf8", str(ROOT / "hyperframes_local.py"),
            "render", str(clip / "portrait"), "--fps", "24", "--quality", "delivery",
            "--workers", "2", "--no-browser-gpu", "--output", str(target)]
        atomic_json(clip / "render_command.json", {"command": command, "native_render": True})
        print(f"Rendering revised Teil {part}.", flush=True)
        with (clip / "render.log").open("w", encoding="utf-8") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        print(f"Revised Teil {part}: render complete.", flush=True)


def verify(build):
    source, results = validate_inputs(build), []
    assert (build / "title_speech_review.json").is_file()
    for part in SELECTIONS:
        clip = build / f"teil_{part}"
        detail = validate_clip(clip, source / f"teil_{part}")
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
        print(f"Revised Teil {part}: full decode and every encoded event passed.", flush=True)
    review(build, encoded=True)
    validate_inputs(build)
    files = {name: sha256_file(build / name) for name in (
        "input_pin.json", "title_speech_plan.json", "title_audio_manifest.json", "title_speech_review.json",
        "pre_render_checks.json")}
    for part in SELECTIONS:
        clip = build / f"teil_{part}"
        for name in ("production_portrait.mp4", "timeline.json", "sample_content.json", "dialogue.wav",
                     "composition_receipt.json", "browser_check.json", "mobile_layout.json",
                     "browser_visual_review.json", "export_visual_review.json", "validation.json",
                     "render_command.json", "opening.png"):
            files[str((clip / name).relative_to(build))] = sha256_file(clip / name)
    atomic_json(build / "delivery_manifest.json", {
        "revision": "Four voiced, simplified openings and larger mobile exercise typography.",
        "previous_build": str(source), "previous_sources_preserved": True,
        "exercise_audio_and_timing": "unchanged", "clips": results, "files": files,
        "inherited_audio_review": str(Path(read_json(build / "input_pin.json")["full_build"]) /
                                      "speech_review_notes.json"), "publication": "not uploaded"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "speech-review", "check", "render", "verify"))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--build", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        if not args.source:
            parser.error("prepare requires --source")
        prepare(args.source, args.build)
    else:
        {"speech-review": speech_review, "check": check, "render": render, "verify": verify}[
            args.action](args.build.resolve())
