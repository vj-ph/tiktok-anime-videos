"""Derive six complete two-exercise portrait clips from frozen fide chimes r1."""

import argparse
import copy
import html
import json
import math
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import revise_fide_chimes as chimes
from compose_fide import word_mapping
from deliver_fide import run
from prepare_fide import ROOT, atomic_json, read, schedule, sha256_file, verify_files
from prepare_sample import mix_events, write_wav
from review_full_frames import sheets
from validate_full import audio_info, block, encoded_events

SOURCE = ROOT / "builds" / "fide_a2_b1_listening_chimes_r1"
PAIRS = ((7, 8), (9, 10), (11, 12), (13, 14), (15, 16), (17, 18))
PREFIX_WORDS = {"title": 6, "context_a2_sbb": 10, "context_a2_tram": 9,
                "context_b1_verwaltung": 7, "context_b1_nachbarn": 11}
GROUPS = ("a2_sbb", "a2_tram", "b1_verwaltung", "b1_nachbarn")
HEADINGS = ("A2 · Bahnhof", "A2 · Tram", "B1 · Hausverwaltung", "B1 · Nachbarschaft")
OVERLAY_BOXES = ((80, 254, 1000, 300), (80, 1710, 1000, 1766))
PROMOTION_BOX = (80, 1420, 1000, 1696)
TIME_KEYS = {"start_frame", "end_frame", "start", "end"}


def verify_source(source):
    delivery = read(source / "delivery_manifest.json")
    verify_files({str(source / p): digest for p, digest in delivery["files"].items()})
    verify_files(delivery["code_inputs"])
    verify_files(delivery["source_manifest"])
    chimes.verify_source(Path(read(source / "revision.json")["source"]))
    return delivery


def event_ids(numbers):
    result, previous = ["title", "opening_padding"], None
    for number in numbers:
        group = GROUPS[(number - 7) // 3]
        if group != previous:
            result.append("context_" + group)
            previous = group
        result.append(f"question_{number}")
        if number < 13:
            result.append(f"inspect_{number}")
        result.extend(f"{prefix}_{number}" for prefix in (
            "recording", "repeat_question", "answer", "solution_chime", "solution", "solution_padding"))
    return result + ["cta", "outro"]


def prefix_info(previous, turn, count, audio):
    words = turn["words"]
    assert words[count - 1]["word"].endswith(".")
    endpoint = round((words[count - 1]["end"] + words[count]["start"]) * 24000)
    assert words[count - 1]["end"] * 48000 <= endpoint < words[count]["start"] * 48000
    info = copy.deepcopy(previous)
    info.update(text=" ".join(turn["text"].split()[:count]), frames=endpoint,
                wav_duration=endpoint / 48000, audio=str(audio),
                processed_audio=str(audio), words=copy.deepcopy(words[:count]),
                alignment_key=turn["alignment_key"])
    if "display_text" in turn:
        groups = [g for g in turn["display_word_groups"] if max(g) < count]
        info.update(display_text=" ".join(turn["display_text"].split()[:len(groups)]),
                    display_word_groups=groups)
    info["derivation"] = {"source_audio": previous["audio"], "source_sha256": previous["sha256"],
                          "start_sample": 0, "end_sample": endpoint, "retained_words": count,
                          "removed_text": " ".join(turn["text"].split()[count:]),
                          "method": "Sentence prefix; midpoint of inherited measured inter-word gap."}
    return info


def selected_timeline(source, plan, manifest, part):
    numbers = PAIRS[part - 1]
    wanted = event_ids(numbers)
    planned = {e["id"]: e for e in plan["events"]}
    timeline = schedule([planned[ident] for ident in wanted], manifest)
    timeline.update(scope="selected", practice_mode="guided_per_exercise_answers_with_chime",
                    part=part, parts=6, selected_numbers=list(numbers), full_question_count=12,
                    word_alignment={"method": "Inherited measured speech words; no estimated timings."})
    originals = {t["id"]: t for t in source["turns"]}
    source_events = {e["id"]: e for e in source["events"]}
    for event in timeline["events"]:
        if event["id"] not in PREFIX_WORDS and event["id"] != "opening_padding":
            old = source_events[event["id"]]
            event.update(source_start_frame=old["start_frame"], source_end_frame=old["end_frame"])
    for turn in timeline["turns"]:
        if turn["visible"]:
            previous = originals[turn["id"]]
            count = PREFIX_WORDS[turn["id"]]
            turn.update(words=copy.deepcopy(previous["words"][:count]),
                        alignment_key=previous["alignment_key"])
    assert timeline["total_frames"] < 4320
    return timeline


def document(source_html, timeline, content):
    result, mappings = chimes.document(source_html, timeline, content, "portrait")
    part = timeline["part"]
    first, last = timeline["selected_numbers"]
    level = "A2" if last < 13 else "B1"
    notice = f"Video {part}/6 · {level} · Aufgaben {first}–{last}"
    footer = "Verkürzte Übung · Ausgewählte Aufgaben · 2 von 12"
    result = result.replace('    <section id="scene-0"',
                            f'    <div id="short-notice">{notice}</div>\n    <section id="scene-0"', 1)
    result, count = re.subn(r"<footer>.*?</footer>", f"<footer><span>{footer}</span></footer>",
                            result, flags=re.S)
    assert count == 1
    result = result.replace("</style>", """
#short-notice { position:absolute;left:80px;top:254px;width:920px;height:46px;
  font-size:32px;line-height:46px;font-weight:700;color:#3f685b;text-align:center; }
html[data-resolution="portrait"] footer { top:1720px;bottom:auto;height:40px;
  font-size:26px;line-height:35px; }
</style>""")
    assert result.count('id="short-notice"') == 1
    assert result.count(chimes.CUES["portrait"]) == 3
    return result, mappings


def prepare(build, source):
    if build.exists() or source == build or source in build.parents or build in source.parents:
        raise ValueError("Choose a fresh build separate from the frozen source.")
    delivery = verify_source(source)
    old_timeline = read(source / "timeline.json")
    old_manifest = read(source / "audio_manifest.json")
    turns = {t["id"]: t for t in old_timeline["turns"]}
    build.mkdir(parents=True)
    (build / "audio").mkdir()
    derived = {}
    for ident, count in PREFIX_WORDS.items():
        target = build / "audio" / f"{ident}.wav"
        info = prefix_info(old_manifest[ident], turns[ident], count, target)
        with wave.open(old_manifest[ident]["audio"], "rb") as wav:
            pcm = wav.readframes(info["frames"])
        assert len(pcm) == info["frames"] * 2
        write_wav(target, pcm)
        info.update(sha256=sha256_file(target), processed_sha256=sha256_file(target))
        derived[ident] = info
    atomic_json(build / "audio_manifest.json", derived)
    code = [Path(__file__), ROOT / "test_fide_social.py", ROOT / "check_fide_social.cjs",
            ROOT / "review_full_frames.py", ROOT / "validate_full.py", ROOT / "process_fide.py"]
    atomic_json(build / "input_pin.json", {
        "source": str(source), "source_manifest_sha256": sha256_file(source / "delivery_manifest.json"),
        "source_files": len(delivery["files"]), "source_code_inputs": delivery["code_inputs"],
        "code_inputs": {str(p): sha256_file(p) for p in code},
        "authorization": "2026-11-17: six two-exercise social clips, all tasks 7-18, complete pauses and CTA.",
        "new_tts": False, "new_tempo_processing": False})
    manifest = {**old_manifest, **derived}
    for part in range(1, 7):
        clip = build / f"clip_{part}"
        clip.mkdir()
        timeline = selected_timeline(old_timeline, read(source / "speech_plan.json"), manifest, part)
        content = copy.deepcopy(read(source / "sample_content.json"))
        content["episode"]["title"] = derived["title"]["display_text"]
        for situation, heading in zip(content["episode"]["situations"], HEADINGS):
            situation["heading"] = heading
            situation["context"] = derived["context_" + situation["id"]]["text"]
        atomic_json(clip / "timeline.json", timeline)
        atomic_json(clip / "sample_content.json", content)
        write_wav(clip / "dialogue.wav", mix_events(timeline["events"]))
        folder = clip / "portrait"
        shutil.copytree(source / "portrait" / "assets", folder / "assets")
        shutil.copyfile(clip / "dialogue.wav", folder / "assets" / "dialogue.wav")
        markup, mappings = document((source / "portrait" / "index.html").read_text(encoding="utf-8"),
                                    timeline, content)
        (folder / "index.html").write_text(markup, encoding="utf-8")
        shutil.copyfile(source / "portrait" / "hyperframes.json", folder / "hyperframes.json")
        atomic_json(folder / "assets_manifest.json",
                    {p.name: sha256_file(p) for p in (folder / "assets").iterdir() if p.is_file()})
        atomic_json(clip / "composition_receipt.json", {
            "html_sha256": sha256_file(folder / "index.html"),
            "timeline_sha256": sha256_file(clip / "timeline.json"), "word_mappings": mappings,
            "exercise_geometry": "Unchanged; source footage outside notice/footer overlays.",
            "native_replacement": "Shortened title and complete first sentence of each situation."})
        print(f"Clip {part}: tasks {timeline['selected_numbers']}, "
              f"{timeline['total_frames']} frames / {timeline['duration']:.3f}s.", flush=True)


def check_pins(build):
    pin = read(build / "input_pin.json")
    source = Path(pin["source"])
    assert sha256_file(source / "delivery_manifest.json") == pin["source_manifest_sha256"]
    verify_files(pin["code_inputs"])
    verify_files(pin["source_code_inputs"])
    return source


def compare_sequence(timeline, original):
    numbers = PAIRS[timeline["part"] - 1]
    assert timeline["selected_numbers"] == list(numbers)
    events = timeline["events"]
    assert [e["id"] for e in events] == event_ids(numbers)
    previous = {e["id"]: e for e in original["events"]}
    by_id, cursor = {}, 0
    for event in events:
        ident = event["id"]
        by_id[ident] = event
        assert event["start_frame"] == cursor
        frames = event["end_frame"] - cursor
        assert frames > 0 and event["start"] == cursor / 24
        assert event["end"] == event["end_frame"] / 24 and event["duration"] == frames / 24
        if ident not in PREFIX_WORDS:
            retained = {k: v for k, v in event.items()
                        if k not in TIME_KEYS | {"source_start_frame", "source_end_frame"}}
            assert retained == {k: v for k, v in previous[ident].items() if k not in TIME_KEYS}
            assert frames == previous[ident]["end_frame"] - previous[ident]["start_frame"]
        cursor = event["end_frame"]
    for number in numbers:
        sequence = [by_id[f"{p}_{number}"] for p in (
            "repeat_question", "answer", "solution_chime", "solution", "solution_padding")]
        assert all(a["end_frame"] == b["start_frame"] for a, b in zip(sequence, sequence[1:]))
        assert by_id[f"answer_{number}"]["duration"] == (10 if number < 13 else 20)
        assert by_id[f"solution_padding_{number}"]["duration"] == 2
        if number < 13:
            assert by_id[f"inspect_{number}"]["duration"] == 5
        question, repeated = by_id[f"question_{number}"], by_id[f"repeat_question_{number}"]
        assert all(question[k] == repeated[k] for k in ("audio", "sha256", "audio_samples", "text"))
    assert cursor == timeline["total_frames"] < 4320
    assert timeline["duration"] == cursor / 24
    return {"ok": True, "numbers": list(numbers), "frames": cursor, "seconds": cursor / 24}


def validate_clip(clip, source):
    timeline = read(clip / "timeline.json")
    original = read(source / "timeline.json")
    report = compare_sequence(timeline, original)
    derived = read(clip.parent / "audio_manifest.json")
    manifest = {**read(source / "audio_manifest.json"), **derived}
    expected = selected_timeline(original, read(source / "speech_plan.json"),
                                 manifest, timeline["part"])
    assert timeline == expected
    old_turns = {t["id"]: t for t in original["turns"]}
    for ident, info in derived.items():
        derivation = info["derivation"]
        assert info["text"] == " ".join(old_turns[ident]["text"].split()[:PREFIX_WORDS[ident]])
        assert "drei" not in info["text"].split() and "Prüfungssimulation." not in info["text"]
        verify_files({info["audio"]: info["sha256"], derivation["source_audio"]: derivation["source_sha256"]})
        assert audio_info(Path(info["audio"])) == derivation["end_sample"] == info["frames"]
        with wave.open(info["audio"], "rb") as cut, wave.open(derivation["source_audio"], "rb") as full:
            assert cut.readframes(cut.getnframes()) == full.readframes(info["frames"])
    content = read(clip / "sample_content.json")
    old_content = read(source / "sample_content.json")
    assert content["cards"] == old_content["cards"]
    for current, previous in zip(content["episode"]["situations"], old_content["episode"]["situations"]):
        assert current["items"] == previous["items"]
    assert audio_info(clip / "dialogue.wav") == timeline["total_frames"] * 2000
    with wave.open(str(clip / "dialogue.wav"), "rb") as track:
        for event in timeline["events"]:
            pcm = block(track, event["start_frame"] * 2000, event["end_frame"] * 2000)
            if event["kind"] == "silence":
                assert not any(pcm), event["id"]
            else:
                verify_files({event["audio"]: event["sha256"]})
                with wave.open(event["audio"], "rb") as audio:
                    original_pcm = audio.readframes(audio.getnframes())
                assert pcm[:len(original_pcm)] == original_pcm and not any(pcm[len(original_pcm):])
    folder = clip / "portrait"
    markup, _ = document((source / "portrait" / "index.html").read_text(encoding="utf-8"),
                         timeline, content)
    assert markup == (folder / "index.html").read_text(encoding="utf-8")
    for scene, event in zip(chimes.inline.SCENES.findall(markup), timeline["events"]):
        assert bool(re.findall(r'data-answer="([^"]+)"', scene)) == event["card"].startswith("solution_")
        if event["card"].startswith("item_"):
            item = content["cards"][event["card"]]
            assert html.escape(item["recording"]) not in scene
            assert html.escape(item["question"]) not in scene
    verify_files({str(folder / "assets" / p): digest
                  for p, digest in read(folder / "assets_manifest.json").items()})
    atomic_json(clip / "source_validation.json", report)
    return report


def check(build):
    source = check_pins(build)
    results = {}
    for part in range(1, 7):
        clip = build / f"clip_{part}"
        validate_clip(clip, source)
        folder = clip / "portrait"
        run(["node", str(ROOT / "check_fide_layout.cjs"), str(folder / "index.html"),
             str(clip / "geometry_portrait.json"), "portrait"], clip / "geometry.log")
        run(["node", str(ROOT / "check_fide_social.cjs"), str(folder / "index.html"),
             str(clip / "social_layout.json"), str(part)], clip / "social_layout.log")
        run([sys.executable, "-B", "-X", "utf8", str(ROOT / "hyperframes_local.py"), "check",
             str(folder), "--json", "--at-transitions", "--snapshots", "--no-browser-gpu",
             "--timeout", "4m"], clip / "browser_check.log")
        report_path = max((folder / ".hyperframes" / "artifacts" / "checks").glob("*.json"),
                          key=lambda p: p.stat().st_mtime_ns)
        report = read(report_path)
        assert report["ok"] and not report.get("browserSkipped", False)
        results[str(part)] = {str(p): sha256_file(p) for p in (
            report_path, folder / "index.html", clip / "geometry_portrait.json", clip / "social_layout.json")}
        print(f"Clip {part}: native browser/geometry gates passed.", flush=True)
    atomic_json(build / "pre_render_checks.json", results)


def frame_plan(timeline):
    selected = {}

    def add(frame, label):
        if 0 <= frame < timeline["total_frames"]:
            selected.setdefault(frame, []).append(label)

    for event in timeline["events"]:
        ident, start, end = event["id"], event["start_frame"], event["end_frame"]
        if (ident in PREFIX_WORDS or ident in ("opening_padding", "cta", "outro")
                or ident.startswith(("solution_chime_", "solution_", "question_"))):
            for frame, suffix in ((start - 1, "preceding"), (start, "first"),
                                  (end - 1, "last"), (end, "following")):
                add(frame, ident + " " + suffix)
        if ident.startswith(("inspect_", "answer_", "recording_")) or ident in PREFIX_WORDS or ident == "cta":
            add((start + end) // 2, ident + " middle")
    return [{"frame": frame, "seconds": frame / 24,
             "snapshot_seconds": math.ceil(frame / 24 * 1000 - 1e-7) / 1000, "labels": labels}
            for frame, labels in sorted(selected.items())]


def review(build, encoded=False):
    import numpy as np
    from PIL import Image

    check_pins(build)
    for part in range(1, 7):
        clip = build / f"clip_{part}"
        timeline = read(clip / "timeline.json")
        plan = frame_plan(timeline)
        destination = clip / "contact_portrait"
        destination.mkdir(exist_ok=True)
        stamps = [f'{p["snapshot_seconds"]:.3f}'.rstrip("0").rstrip(".") for p in plan]
        images = [destination / f"at-{stamp}s.png" for stamp in stamps]
        if not encoded:
            run([sys.executable, "-B", "-X", "utf8", str(ROOT / "hyperframes_local.py"),
                 "snapshot", str(clip / "portrait"), "--at", ",".join(stamps), "--no-end",
                 "--keep", "--output", str(destination), "--no-browser-gpu", "--timeout",
                 "180000", "--json"], clip / "browser_review.log")
            with Image.open(images[0]) as first:
                first = first.convert("RGB")
                baseline = first.crop(PROMOTION_BOX).tobytes()
                overlay_baseline = [first.crop(box).tobytes() for box in OVERLAY_BOXES]
                overlay = Image.new("RGBA", first.size)
                for box in OVERLAY_BOXES:
                    overlay.paste(first.crop(box).convert("RGBA"), box[:2])
                overlay.save(clip / "overlay.png")
            for image in images:
                with Image.open(image) as actual:
                    actual = actual.convert("RGB")
                    assert actual.crop(PROMOTION_BOX).tobytes() == baseline
                    assert [actual.crop(box).tobytes() for box in OVERLAY_BOXES] == overlay_baseline
            atomic_json(clip / "browser_visual_review.json", {
                "frames": plan, "browser_contact_sheets": sheets(images, plan, destination, "portrait"),
                "browser_frames": {str(p): sha256_file(p) for p in images},
                "overlay_sha256": sha256_file(clip / "overlay.png"),
                "persistent_promotion_and_scope": "pixel-identical at all selected frames"})
        else:
            native = read(clip / "browser_visual_review.json")
            verify_files(native["browser_frames"])
            assert native["frames"] == plan
            folder = clip / "encoded_portrait"
            folder.mkdir(exist_ok=True)
            selector = "+".join(f'eq(n\\,{p["frame"]})' for p in plan)
            run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(clip / "production_portrait.mp4"),
                 "-vf", "select=" + selector, "-fps_mode", "vfr", "-frames:v", str(len(plan)),
                 str(folder / "frame-%03d.png")], clip / "encoded_frames.log")
            exported = [folder / f"frame-{i:03d}.png" for i in range(1, len(plan) + 1)]
            comparisons = []
            for item, expected, actual in zip(plan, images, exported):
                with Image.open(expected) as a, Image.open(actual) as b:
                    a, b = a.convert("RGB"), b.convert("RGB")
                    assert a.size == b.size == (1080, 1920)
                    boxes = ((0, 0, 1080, 1920), PROMOTION_BOX, *OVERLAY_BOXES)
                    errors = [float(np.mean(np.abs(np.asarray(a.crop(box), dtype=float) -
                                                   np.asarray(b.crop(box), dtype=float)))) for box in boxes]
                assert all(error < 4 for error in errors), (part, item, errors)
                comparisons.append({**item, "rgb_errors_full_promotion_notice_footer": errors,
                                    "file": str(actual), "sha256": sha256_file(actual)})
            atomic_json(clip / "export_visual_review.json", {
                "frames": comparisons, "encoded_contact_sheets": sheets(exported, plan, folder, "portrait")})
        print(f"Clip {part}: {len(plan)} {'encoded' if encoded else 'native'} review frames passed.", flush=True)


def segments(timeline):
    result = []
    for event in timeline["events"]:
        kind = "source" if "source_start_frame" in event else "native"
        entry = {"kind": kind, "start_frame": event["start_frame"], "end_frame": event["end_frame"]}
        if kind == "source":
            entry.update(source_start_frame=event["source_start_frame"],
                         source_end_frame=event["source_end_frame"])
        if (result and result[-1]["kind"] == kind and result[-1]["end_frame"] == entry["start_frame"]
                and (kind == "native" or result[-1]["source_end_frame"] == entry["source_start_frame"])):
            result[-1]["end_frame"] = entry["end_frame"]
            if kind == "source":
                result[-1]["source_end_frame"] = entry["source_end_frame"]
        else:
            result.append(entry)
    return result


def render(build):
    source = check_pins(build)
    for pins in read(build / "pre_render_checks.json").values():
        verify_files(pins)
    audio = read(build / "audio_review_resolution.json")
    assert audio["status"] == "pass_with_asr_notes"
    verify_files(audio["review_files_sha256"])
    assert audio["audio_manifest_sha256"] == sha256_file(build / "audio_manifest.json")
    approval = read(build / "visual_approval.json")
    assert approval["contact_sheets_inspected"]
    verify_files(approval["native_reviews"])
    for part in range(1, 7):
        clip = build / f"clip_{part}"
        target = clip / "production_portrait.mp4"
        if target.exists():
            raise ValueError(f"Preserving existing render: {target}")
        validate_clip(clip, source)
        timeline = read(clip / "timeline.json")
        parts = segments(timeline)
        arguments, native_index = ["-i", str(source / "production_portrait.mp4")], 1
        for index, segment in enumerate(parts):
            if segment["kind"] == "native":
                patch = clip / f"native_patch_{index}.mp4"
                if patch.exists():
                    raise ValueError(f"Preserving native patch: {patch}")
                run([sys.executable, "-B", "-X", "utf8", str(ROOT / "hyperframes_local.py"),
                     "render", str(clip / "portrait"), "--start", str(segment["start_frame"] / 24),
                     "--end", str(segment["end_frame"] / 24), "--fps", "24", "--quality", "delivery",
                     "--workers", "2", "--no-browser-gpu", "--output", str(patch)],
                    clip / f"native_patch_{index}.log")
                metadata = json.loads(subprocess.run([
                    "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                    "stream=nb_frames", "-of", "json", str(patch)], check=True,
                    capture_output=True, text=True).stdout)["streams"][0]
                assert int(metadata["nb_frames"]) == segment["end_frame"] - segment["start_frame"]
                segment["input_index"] = native_index
                native_index += 1
                arguments += ["-i", str(patch)]
        overlay_index, audio_index = native_index, native_index + 1
        arguments += ["-loop", "1", "-framerate", "24", "-i", str(clip / "overlay.png"),
                      "-i", str(clip / "dialogue.wav")]
        cuts = [p for p in parts if p["kind"] == "source"]
        filters = [f'[0:v]split={len(cuts)}' + "".join(f"[source{i}]" for i in range(len(cuts)))]
        cut_index = 0
        for index, segment in enumerate(parts):
            if segment["kind"] == "source":
                filters.append(f"[source{cut_index}]trim=start_frame={segment['source_start_frame']}:"
                               f"end_frame={segment['source_end_frame']},setpts=PTS-STARTPTS[v{index}]")
                cut_index += 1
            else:
                filters.append(f"[{segment['input_index']}:v]trim=end_frame="
                               f"{segment['end_frame'] - segment['start_frame']},setpts=PTS-STARTPTS[v{index}]")
        filters += ["".join(f"[v{i}]" for i in range(len(parts))) +
                    f"concat=n={len(parts)}:v=1:a=0[base]",
                    f"[base][{overlay_index}:v]overlay=shortest=1,format=yuv420p[video]"]
        command = ["ffmpeg", "-nostdin", "-v", "warning", "-stats", *arguments,
                   "-filter_complex_threads", "2", "-filter_complex", ";".join(filters),
                   "-map", "[video]", "-map", f"{audio_index}:a:0", "-c:v", "libx264",
                   "-threads", "2", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                   "-r", "24", "-frames:v", str(timeline["total_frames"]), "-c:a", "aac",
                   "-b:a", "192k", "-ar", "48000", "-ac", "1", "-t", str(timeline["duration"]),
                   "-movflags", "+faststart", str(target)]
        atomic_json(clip / "render_command.json", {
            "command": command, "segments": parts, "overlay_boxes": OVERLAY_BOXES,
            "source_video_sha256": sha256_file(source / "production_portrait.mp4"),
            "overlay_sha256": sha256_file(clip / "overlay.png"),
            "native_composition_sha256": sha256_file(clip / "portrait" / "index.html")})
        assert read(clip / "browser_visual_review.json")["overlay_sha256"] == sha256_file(clip / "overlay.png")
        run(command, clip / "render.log")
        print(f"Clip {part}: portrait export complete.", flush=True)


def verify(build):
    source = check_pins(build)
    results = []
    for part in range(1, 7):
        clip = build / f"clip_{part}"
        report = validate_clip(clip, source)
        timeline = read(clip / "timeline.json")
        report["encoded"] = encoded_events(clip, timeline, "portrait")
        metadata = json.loads(subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,duration",
            "-of", "json", str(clip / "production_portrait.mp4")],
            check=True, capture_output=True, text=True).stdout)
        durations = [float(metadata["format"]["duration"])] + [
            float(s["duration"]) for s in metadata["streams"]]
        assert len(durations) == 3 and all(0 < d < 180 for d in durations), durations
        report["container_and_stream_durations"] = metadata
        atomic_json(clip / "validation.json", report)
        results.append(report)
        print(f"Clip {part}: full decode, every audio/silence event and strict duration cap passed.", flush=True)
    review(build, True)
    atomic_json(build / "validation.json", {"clips": results, "uploaded": False})


def freeze(build):
    if (build / "delivery_manifest.json").exists():
        raise ValueError("Already frozen.")
    source = check_pins(build)
    original = verify_source(source)
    pin = read(build / "input_pin.json")
    approval = read(build / "visual_approval.json")
    assert approval["contact_sheets_inspected"] and approval["encoded_contact_sheets_inspected"]
    verify_files(approval["native_reviews"])
    verify_files(approval["encoded_reviews"])
    covered = []
    for part in range(1, 7):
        clip = build / f"clip_{part}"
        validation = read(clip / "validation.json")
        assert validation["encoded"]["sha256"] == sha256_file(clip / "production_portrait.mp4")
        assert validation["frames"] == int(validation["encoded"]["nb_frames"]) < 4320
        covered.extend(validation["numbers"])
        native = read(clip / "browser_visual_review.json")
        verify_files(native["browser_frames"])
        assert native["overlay_sha256"] == sha256_file(clip / "overlay.png")
        for frame in read(clip / "export_visual_review.json")["frames"]:
            verify_files({frame["file"]: frame["sha256"]})
            assert all(error < 4 for error in frame["rgb_errors_full_promotion_notice_footer"])
    assert covered == list(range(7, 19))
    files = {str(p.relative_to(build)): sha256_file(p) for p in build.rglob("*")
             if p.is_file() and ".hyperframes" not in p.parts}
    atomic_json(build / "delivery_manifest.json", {
        "scope": "Six portrait clips, two complete exercises each; all tasks 7-18 covered once.",
        "files": files, "code_inputs": {**original["code_inputs"], **pin["code_inputs"]},
        "source": str(source), "source_manifest_sha256": sha256_file(source / "delivery_manifest.json"),
        "clips": read(build / "validation.json")["clips"],
        "speech_and_pauses": "Complete original exercises/chimes/answers/CTA; exact measured sentence prefixes only for title/context.",
        "inherited_audio_review": str(source / "audio_review_resolution.json"),
        "human_listening": False, "continuous_motion_certification": False, "uploaded": False})
    verify_files({str(build / p): digest for p, digest in files.items()})
    atomic_json(build / "delivery_audit.json", {
        "manifest_sha256": sha256_file(build / "delivery_manifest.json"),
        "files_rehashed": len(files), "source_files_rehashed": len(original["files"]),
        "all_twelve_tasks_once": True, "uploaded": False})
    print(f"Frozen six-clip delivery: {len(files)} files; source preserved.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "check", "review", "render", "verify", "freeze"))
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--source", default=SOURCE, type=Path)
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare(args.build.resolve(), args.source.resolve())
    else:
        globals()[args.stage](args.build.resolve())
