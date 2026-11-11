"""Make four reduced-practice portrait cuts without changing speech or pauses."""

import argparse
import copy
import html
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import wave

from compose_full import STYLES, card_body, visual_events
from compose_sample import ROOT
from prepare_sample import atomic_json, mix_events, sha256_file, write_wav
from review_full_frames import sheets
from validate_full import audio_info, block, encoded_events

SELECTIONS = {
    1: ("p1_task_1", "p1_task_2"),
    2: ("p2_task_5", "p2_task_6"),
    3: ("p3_task_10_11", "p3_task_12_13"),
    4: ("p4_task_18", "p4_task_19"),
}
TOTALS = {1: 4, 2: 5, 3: 8, 4: 3}
NOTICE = "Verkürzte Übung · Ausgewählte Aufgaben"
INTRO_FRAMES = 144
OVERLAY_BOXES = ((80, 254, 1000, 300), (80, 1420, 1000, 1696),
                 (80, 1720, 1000, 1765))


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def selected_timeline(source, part):
    chosen = set(SELECTIONS[part])
    events = [{"id": "reduced_intro", "card": "reduced_intro", "kind": "silence",
               "phase": "Start", "part": part, "seconds": INTRO_FRAMES / 24,
               "start_frame": 0, "end_frame": INTRO_FRAMES, "start": 0,
               "end": INTRO_FRAMES / 24, "duration": INTRO_FRAMES / 24}]
    cursor = INTRO_FRAMES
    for original in source["events"]:
        if not (original["card"] in chosen or original["id"] == "cta" or
                (part == 4 and original["id"] == "p4_statements_read")):
            continue
        event = copy.deepcopy(original)
        frames = original["end_frame"] - original["start_frame"]
        event.update(source_start_frame=original["start_frame"],
                     source_end_frame=original["end_frame"], start_frame=cursor,
                     end_frame=cursor + frames, start=cursor / 24,
                     end=(cursor + frames) / 24, duration=frames / 24)
        events.append(event)
        cursor += frames
    if cursor >= 180 * 24:
        raise ValueError(f"Teil {part} is not strictly under three minutes.")
    return {"scope": "reduced", "part": part, "language": "de", "fps": 24,
            "sample_rate": 48000, "practice_mode": "guided",
            "answer_reveal_seconds": 3, "speech_atempo": 0.8,
            "notice": NOTICE, "cards": list(SELECTIONS[part]),
            "total_frames": cursor, "duration": cursor / 24, "events": events}


def source_ranges(timeline):
    ranges = []
    for event in timeline["events"]:
        if "source_start_frame" not in event:
            continue
        start, end = event["source_start_frame"], event["source_end_frame"]
        if ranges and ranges[-1][1] == start:
            ranges[-1][1] = end
        else:
            ranges.append([start, end])
    return ranges


def compose(build, timeline, content):
    part, scenes, pauses = timeline["part"], [], []
    numbers = [q["number"] for card in SELECTIONS[part]
               for q in content["cards"][card]["questions"]]
    scope = f"Teil {part} · Aufgaben {numbers[0]}–{numbers[-1]} · {len(numbers)} von {TOTALS[part]}"
    scene_events = visual_events(timeline["events"])
    for index, event in enumerate(scene_events):
        card, classes = event["card"], []
        if card == "reduced_intro":
            label = "Deine kurze Hörpraxis"
            body = (f"<h1>ÖIF B1 Hören<br>Teil {part}</h1>"
                    "<p>Verkürzte Übung</p>"
                    f"<p>Aufgaben {numbers[0]}–{numbers[-1]}<br>"
                    f"{len(numbers)} von {TOTALS[part]} Aufgaben</p>"
                    "<p>Die ursprünglichen Lese- und Antwortpausen bleiben erhalten.</p>")
        elif card == "cta":
            label = "Dein nächster Schritt"
            body = ("<h1>Weiter hören.<br>Sicherer antworten.</h1>"
                    "<p>Mehr Hörübungen, Transkripte und Erklärungen im Buch.</p>")
        else:
            question = content["cards"][card]
            label = question["label"]
            classes.append(question["type"])
            body = card_body(question, event["kind"] == "reveal")
        counter = ""
        if event["kind"] == "silence" and card != "reduced_intro":
            counter = f'<span class="countdown" id="count-{index}">{round(event["duration"])} s</span>'
            pauses.append({"index": index, "start": event["start"], "duration": event["duration"]})
        status = (f'<div class="phase"><span class="phase-label">'
                  f'{html.escape(event["phase"])}</span>{counter}</div>')
        if counter:
            status += f'<div class="progress"><div class="progress-fill" id="fill-{index}"></div></div>'
        eyebrow = html.escape(label) + (f" · Teil {event['part']}" if event["part"] else "")
        scenes.append(f'<section id="scene-{index}" class="clip scene {" ".join(classes)}" '
                      f'data-start="{event["start"]}" data-duration="{event["duration"]}" '
                      f'data-track-index="0"><div class="eyebrow">{eyebrow}</div>{body}{status}</section>')
    template = (ROOT / "composition" / "index.html").read_text(encoding="utf-8")
    template = template.replace("    {{SCENES}}", f'    <div id="reduced-notice">{NOTICE}</div>\n    {{{{SCENES}}}}')
    styles = STYLES + """
    #reduced-notice { position: absolute; top: 260px; left: 80px; width: 920px;
      font-size: 28px; line-height: 36px; font-weight: 700; color: #3f685b;
      text-align: center; }
"""
    target = build / "portrait"
    assets = target / "assets"
    assets.mkdir(parents=True)
    sources = {
        "gsap.min.js": ROOT / "node_modules" / "gsap" / "dist" / "gsap.min.js",
        "arial.ttf": Path(r"C:\Windows\Fonts\arial.ttf"),
        "arialbd.ttf": Path(r"C:\Windows\Fonts\arialbd.ttf"),
        "logo.png": ROOT.parent / "pilot_3d" / "assets" / "deutschkompass-logo.png",
        "book.jpg": ROOT / "episodes" / content["episode"]["promotion"]["cover_source"],
        "dialogue.wav": build / "dialogue.wav",
    }
    for name, source in sources.items():
        shutil.copyfile(source, assets / name)
    replacements = {
        "{{LAYOUT}}": "portrait", "{{WIDTH}}": "1080", "{{HEIGHT}}": "1920",
        "{{DURATION}}": str(timeline["duration"]), "{{SCENES}}": "\n".join(scenes),
        "{{PAUSES}}": json.dumps(pauses), "{{TITLE_WORDS}}": "[]",
        "{{INSTRUCTION_WORDS}}": "[]", "{{EXTRA_STYLES}}": styles,
        "{{SCOPE_LABEL}}": scope, "{{FOOTER_NOTE}}": "",
        "{{AMAZON}}": "Amazon: Bio / Beschreibung 👇",
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    if "{{" in template:
        raise ValueError("Unresolved reduced-composition placeholder.")
    (target / "index.html").write_text(template, encoding="utf-8")
    atomic_json(target / "hyperframes.json", {"media": {"autoProxy": False}})
    atomic_json(target / "assets_manifest.json",
                {name: sha256_file(assets / name) for name in sources})
    atomic_json(build / "composition_receipt.json",
                {"timeline_sha256": sha256_file(build / "timeline.json"),
                 "template_sha256": sha256_file(ROOT / "composition" / "index.html"),
                 "generator_sha256": sha256_file(Path(__file__)),
                 "selected_numbers": numbers, "scope_label": scope, "scenes": scene_events})


def prepare(source, build):
    source, build = source.resolve(), build.resolve()
    if build == source or source in build.parents or build in source.parents:
        raise ValueError("Reduced build must be separate from the frozen source.")
    if build.exists():
        raise ValueError("Choose a fresh reduced build; existing deliveries are preserved.")
    original, content = read_json(source / "timeline.json"), read_json(source / "sample_content.json")
    assert original["scope"] == "full"
    pinned = {source / name for name in (
        "timeline.json", "sample_content.json", "input_pin.json", "delivery_manifest.json",
        "production_portrait.mp4", "production_landscape.mp4")}
    pinned.update(Path(e["audio"]) for e in original["events"] if e.get("audio"))
    build.mkdir(parents=True)
    atomic_json(build / "input_pin.json",
                {"source": str(source), "files": {str(p): sha256_file(p) for p in sorted(pinned)},
                 "generator_sha256": sha256_file(Path(__file__))})
    for part in SELECTIONS:
        target = build / f"teil_{part}"
        (target / "audio").mkdir(parents=True)
        timeline = selected_timeline(original, part)
        cards = {card: copy.deepcopy(content["cards"][card]) for card in SELECTIONS[part]}
        if part == 4:
            cards["p4_statements"] = copy.deepcopy(content["cards"]["p4_statements"])
        reduced_content = {"episode": content["episode"], "cards": cards}
        for event in timeline["events"]:
            if event.get("audio"):
                destination = target / "audio" / Path(event["audio"]).name
                shutil.copyfile(event["audio"], destination)
                event["audio"] = str(destination)
        atomic_json(target / "timeline.json", timeline)
        atomic_json(target / "sample_content.json", reduced_content)
        write_wav(target / "dialogue.wav", mix_events(timeline["events"]))
        compose(target, timeline, reduced_content)
        print(f"Teil {part}: {timeline['total_frames']} frames / {timeline['duration']:.3f}s.", flush=True)


def check_source(build):
    pin = read_json(build / "input_pin.json")
    for filename, digest in pin["files"].items():
        assert sha256_file(Path(filename)) == digest, f"Frozen source changed: {filename}"
    assert pin["generator_sha256"] == sha256_file(Path(__file__))
    return Path(pin["source"])


def validate_clip(build, source):
    timeline, content = read_json(build / "timeline.json"), read_json(build / "sample_content.json")
    part = timeline["part"]
    expected = selected_timeline(read_json(source / "timeline.json"), part)
    actual_events = copy.deepcopy(timeline["events"])
    for event, original in zip(actual_events, expected["events"]):
        if event.get("audio"):
            assert sha256_file(Path(event["audio"])) == original["sha256"]
            assert audio_info(Path(event["audio"])) == original["audio_samples"]
            event["audio"] = original["audio"]
    assert {**timeline, "events": actual_events} == expected
    full_content = read_json(source / "sample_content.json")
    assert set(content["cards"]) == set(SELECTIONS[part]) | ({"p4_statements"} if part == 4 else set())
    assert all(card == full_content["cards"][name] for name, card in content["cards"].items())
    assert content["episode"] == full_content["episode"]
    assert audio_info(build / "dialogue.wav") == timeline["total_frames"] * 2000
    with wave.open(str(build / "dialogue.wav"), "rb") as mixed:
        assert mixed.readframes(mixed.getnframes()) == mix_events(timeline["events"])
    receipt = read_json(build / "composition_receipt.json")
    assert receipt["timeline_sha256"] == sha256_file(build / "timeline.json")
    assert [ident for scene in receipt["scenes"] for ident in scene["event_ids"]] == [
        event["id"] for event in timeline["events"]]
    document = (build / "portrait" / "index.html").read_text(encoding="utf-8")
    assert f'<div id="reduced-notice">{NOTICE}</div>' in document
    assert receipt["scope_label"] in document and "Amazon: Bio / Beschreibung 👇" in document
    assert "{{" not in document and "20 Aufgaben" not in document
    for removed in ("Geführte Hörübung", "Lösungen nach jeder Aufgabe", "von Deutsch Kompass"):
        assert removed not in document
    scenes = re.findall(r'<section id="scene-(\d+)"[^>]*data-start="([^"]+)"'
                        r'[^>]*data-duration="([^"]+)"[^>]*>(.*?)</section>', document, re.S)
    assert len(scenes) == len(receipt["scenes"])
    for (_, start, duration, body), event in zip(scenes, receipt["scenes"]):
        assert (float(start), float(duration)) == (event["start"], event["duration"])
        answers = re.findall(r'data-answer="([^"]+)"', body)
        expected_answers = ([q["answer"] for q in content["cards"][event["card"]]["questions"]]
                            if event["kind"] == "reveal" else [])
        assert answers == expected_answers
        assert ('class="solution"' in body) == (event["kind"] == "reveal")
    for name, digest in read_json(build / "portrait" / "assets_manifest.json").items():
        assert sha256_file(build / "portrait" / "assets" / name) == digest
    return {"part": part, "duration": timeline["duration"], "total_frames": timeline["total_frames"],
            "selected_numbers": receipt["selected_numbers"], "source_pcm_and_pauses": "unchanged",
            "answer_gating": "passed", "reduced_notice": "persistent",
            "source_ranges": source_ranges(timeline)}


def check(build):
    source, results = check_source(build), []
    for part in SELECTIONS:
        clip = build / f"teil_{part}"
        detail = validate_clip(clip, source)
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
        detail["browser"] = {name: report[name] for name in (
            "lint", "runtime", "layout", "contrast", "motion", "craft", "audio")}
        results.append(detail)
        print(f"Teil {part}: source and browser checks passed.", flush=True)
    atomic_json(build / "pre_render_checks.json", {"clips": results, "source_preserved": True})


def review_plan(timeline):
    selected = {24: ["reduced opening"]}
    for event in timeline["events"]:
        if event["card"] == "reduced_intro":
            continue
        if event["kind"] == "silence" and event["phase"] == "Lesen":
            selected[(event["start_frame"] + event["end_frame"]) // 2] = [event["card"] + " reading"]
        if event["phase"] == "Jetzt hören":
            selected.setdefault((event["start_frame"] + event["end_frame"]) // 2,
                                [event["card"] + " listening"])
        if event["kind"] == "reveal":
            selected[event["start_frame"] - 1] = [event["card"] + " final response frame"]
            selected[event["start_frame"]] = [event["card"] + " first reveal frame"]
        if event["id"] == "cta":
            selected[(event["start_frame"] + event["end_frame"]) // 2] = ["final CTA"]
    return [{"frame": frame, "seconds": frame / 24, "labels": labels,
             "snapshot_seconds": math.ceil(frame / 24 * 1000 - 1e-7) / 1000}
            for frame, labels in sorted(selected.items())]


def review(build, encoded=False):
    import numpy as np
    from PIL import Image

    for part in SELECTIONS:
        clip = build / f"teil_{part}"
        plan = review_plan(read_json(clip / "timeline.json"))
        destination = clip / "contact_portrait"
        destination.mkdir(exist_ok=True)
        stamps = [f'{item["snapshot_seconds"]:.3f}'.rstrip("0").rstrip(".") for item in plan]
        images = [destination / f"at-{stamp}s.png" for stamp in stamps]
        if not encoded:
            subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "hyperframes_local.py"),
                            "snapshot", str(clip / "portrait"), "--at", ",".join(stamps),
                            "--no-end", "--keep", "--output", str(destination),
                            "--no-browser-gpu", "--timeout", "120000", "--json"], check=True)
            assert all(p.is_file() for p in images)
            with Image.open(images[0]) as opening:
                opening.convert("RGB").save(clip / "opening.png")
                overlay = Image.new("RGBA", opening.size)
                for box in OVERLAY_BOXES:
                    overlay.paste(opening.crop(box).convert("RGBA"), box[:2])
                overlay.save(clip / "overlay.png")
            panel = None
            for path in images:
                with Image.open(path) as image:
                    current = b"".join(image.crop(box).tobytes() for box in OVERLAY_BOXES)
                    if panel is None:
                        panel = current
                    assert current == panel, "Notice, scope or book panel changed between frames."
            receipt = {"frames": plan, "browser_contact_sheets": sheets(images, plan, destination, "portrait"),
                       "browser_frames": {p.name: sha256_file(p) for p in images},
                       "persistent_overlay_regions": "pixel-identical across every review frame",
                       "opening_sha256": sha256_file(clip / "opening.png"),
                       "overlay_sha256": sha256_file(clip / "overlay.png")}
            atomic_json(clip / "browser_visual_review.json", receipt)
        else:
            output = clip / "encoded_portrait"
            output.mkdir(exist_ok=True)
            selector = "+".join(f'eq(n\\,{item["frame"]})' for item in plan)
            subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i",
                            str(clip / "production_portrait.mp4"), "-vf", "select=" + selector,
                            "-fps_mode", "vfr", "-frames:v", str(len(plan)),
                            str(output / "frame-%03d.png")], check=True)
            exported = [output / f"frame-{index + 1:03d}.png" for index in range(len(plan))]
            comparisons = []
            for item, expected, actual in zip(plan, images, exported):
                with Image.open(expected) as reference, Image.open(actual) as candidate:
                    assert reference.size == candidate.size == (1080, 1920)
                    error = float(np.mean(np.abs(np.asarray(reference.convert("RGB"), dtype=float) -
                                                 np.asarray(candidate.convert("RGB"), dtype=float))))
                    assert error < 4, f"Teil {part}, frame {item['frame']}: RGB error {error}"
                comparisons.append({**item, "mean_absolute_rgb_error": error,
                                    "sha256": sha256_file(actual)})
            atomic_json(clip / "export_visual_review.json", {
                "frames": comparisons, "encoded_contact_sheets": sheets(exported, plan, output, "portrait")})
        print(f"Teil {part}: {len(plan)} {'encoded' if encoded else 'browser'} review frames passed.", flush=True)


def render(build):
    source = check_source(build)
    assert (build / "pre_render_checks.json").is_file()
    for part in SELECTIONS:
        clip = build / f"teil_{part}"
        timeline = read_json(clip / "timeline.json")
        validate_clip(clip, source)
        visuals = read_json(clip / "browser_visual_review.json")
        assert sha256_file(clip / "opening.png") == visuals["opening_sha256"]
        assert sha256_file(clip / "overlay.png") == visuals["overlay_sha256"]
        target = clip / "production_portrait.mp4"
        if target.exists():
            raise ValueError(f"Preserving existing render: {target}")
        ranges = source_ranges(timeline)
        labels = "".join(f"[source{i}]" for i in range(len(ranges)))
        filters = [f"[0:v]split={len(ranges)}{labels}",
                   f"[1:v]trim=end_frame={INTRO_FRAMES},setpts=PTS-STARTPTS,format=yuv420p[intro]"]
        for index, (start, end) in enumerate(ranges):
            filters.append(f"[source{index}]trim=start_frame={start}:end_frame={end},"
                           f"setpts=PTS-STARTPTS[cut{index}]")
        inputs = "[intro]" + "".join(f"[cut{i}]" for i in range(len(ranges)))
        filters.extend([f"{inputs}concat=n={len(ranges) + 1}:v=1:a=0[base]",
                        "[base][2:v]overlay=shortest=1,format=yuv420p[video]"])
        command = [
            "ffmpeg", "-nostdin", "-v", "warning", "-stats", "-i", str(source / "production_portrait.mp4"),
            "-loop", "1", "-framerate", "24", "-i", str(clip / "opening.png"),
            "-loop", "1", "-framerate", "24", "-i", str(clip / "overlay.png"),
            "-i", str(clip / "dialogue.wav"), "-filter_complex_threads", "2",
            "-filter_complex", ";".join(filters), "-map", "[video]", "-map", "3:a:0",
            "-c:v", "libx264", "-threads", "2", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-r", "24", "-frames:v", str(timeline["total_frames"]),
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-t", str(timeline["duration"]),
            "-movflags", "+faststart", str(target)]
        atomic_json(clip / "render_command.json", {"command": command, "source_ranges": ranges,
                    "overlay_boxes": OVERLAY_BOXES, "source_video_sha256":
                    sha256_file(source / "production_portrait.mp4")})
        print(f"Rendering Teil {part}, {timeline['duration']:.3f}s.", flush=True)
        with (clip / "render.log").open("w", encoding="utf-8") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        print(f"Teil {part}: render complete.", flush=True)


def verify(build):
    source, results = check_source(build), []
    for part in SELECTIONS:
        clip = build / f"teil_{part}"
        detail = validate_clip(clip, source)
        timeline = read_json(clip / "timeline.json")
        detail["encoded"] = encoded_events(clip, timeline, "portrait")
        metadata = json.loads(subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,duration",
            "-of", "json", str(clip / "production_portrait.mp4")],
            check=True, capture_output=True, text=True).stdout)
        durations = [float(metadata["format"]["duration"])] + [
            float(stream["duration"]) for stream in metadata["streams"]]
        assert all(0 < duration < 180 for duration in durations), durations
        detail["container_and_stream_durations"] = metadata
        atomic_json(clip / "validation.json", detail)
        results.append(detail)
        print(f"Teil {part}: full decode and every encoded event passed.", flush=True)
    review(build, encoded=True)
    check_source(build)
    files = {}
    for part in SELECTIONS:
        clip = build / f"teil_{part}"
        for name in ("production_portrait.mp4", "timeline.json", "sample_content.json",
                     "dialogue.wav", "composition_receipt.json", "browser_check.json",
                     "browser_visual_review.json", "export_visual_review.json", "validation.json",
                     "render_command.json", "opening.png", "overlay.png"):
            files[str((clip / name).relative_to(build))] = sha256_file(clip / name)
    atomic_json(build / "delivery_manifest.json", {
        "scope": "four reduced-practice selections, not complete exam sections",
        "notice": NOTICE, "speech_and_pauses": "unchanged from frozen full production",
        "source_preserved": True, "clips": results, "files": files,
        "inherited_audio_review": str(source / "speech_review_notes.json"),
        "publication": "not uploaded"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "check", "review", "render", "verify"))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--build", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        if not args.source:
            parser.error("prepare requires --source")
        prepare(args.source, args.build)
    else:
        globals()[args.action](args.build.resolve())
