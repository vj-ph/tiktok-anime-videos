"""Derive per-exercise fide answers without changing the frozen source delivery."""

import argparse
import copy
import html
import json
import re
import shutil
import sys
import wave
from pathlib import Path

from compose_fide import scene_body, word_mapping
from deliver_fide import run
from prepare_fide import ROOT, atomic_json, read, schedule, sha256_file, verify_files
from prepare_sample import mix_events, write_wav
from validate_full import audio_info, block, encoded_events

SOURCE = ROOT / "builds" / "fide_a2_b1_listening_full_production_r1"
CUT_WORDS = {"setup": 64, "end_test": 5}
BOOK_LINK = "amzn.eu/d/0dDgJ1ZT"
SCENES = re.compile(r'<section id="scene-\d+"[^>]*>.*?</section>', re.S)


def verify_source(source):
    delivery = read(source / "delivery_manifest.json")
    verify_files({str(source / name): digest for name, digest in delivery["files"].items()})
    verify_files(delivery["code_inputs"])
    inputs = delivery["inputs"]
    for key in ("files", "research", "official"):
        verify_files(inputs[key])
    for role in inputs["voices"].values():
        verify_files({ref["path"]: ref["sha256"] for ref in role.values()})
    return delivery


def revised_plan(source_plan, episode):
    result = copy.deepcopy(source_plan)
    by_id = {e["id"]: e for e in result["events"]}
    events = []
    for event in result["events"]:
        ident = event["id"]
        if ident == "solutions_instruction" or ident.startswith(("solution_", "solution_padding_")):
            continue
        events.append(event)
        if ident.startswith("answer_"):
            number = ident.split("_")[-1]
            events.extend([by_id[f"solution_{number}"], by_id[f"solution_padding_{number}"]])
    result["events"] = events
    result["turns"] = [t for t in result["turns"] if t["id"] != "solutions_instruction"]
    for turn in result["turns"]:
        if turn["id"] in CUT_WORDS:
            turn["text"] = episode[turn["id"]]
    return result


def compare_sequence(timeline):
    expected = ["title", "opening_padding", "setup", "a2_instruction"]
    for level, groups, first in (
            ("A2", ("a2_sbb", "a2_tram"), 7),
            ("B1", ("b1_verwaltung", "b1_nachbarn"), 13)):
        if level == "B1":
            expected.extend(["transition", "b1_instruction"])
        for offset, group in enumerate(groups):
            expected.append("context_" + group)
            for number in range(first + offset * 3, first + offset * 3 + 3):
                expected.append(f"question_{number}")
                if level == "A2":
                    expected.append(f"inspect_{number}")
                expected.extend(f"{prefix}_{number}" for prefix in (
                    "recording", "repeat_question", "answer", "solution", "solution_padding"))
    expected.extend(["end_test", "cta", "outro"])
    events = timeline["events"]
    assert [e["id"] for e in events] == expected, "Wrong independent per-item sequence."
    by_id = {e["id"]: e for e in events}
    cursor = 0
    for event in events:
        frames = event["end_frame"] - event["start_frame"]
        assert event["start_frame"] == cursor and frames > 0
        assert event["start"] == cursor / 24
        assert event["end"] == event["end_frame"] / 24 and event["duration"] == frames / 24
        if event["kind"] == "speech":
            assert 0 <= frames * 2000 - event["audio_samples"] < 2000
        cursor = event["end_frame"]
    for number in range(7, 19):
        question, repeated = by_id[f"question_{number}"], by_id[f"repeat_question_{number}"]
        assert all(question[k] == repeated[k] for k in ("audio", "sha256", "audio_samples", "text"))
        for prefix, seconds in (("answer", 10 if number < 13 else 20), ("solution_padding", 2)):
            event = by_id[f"{prefix}_{number}"]
            assert event["kind"] == "silence" and event["duration"] == seconds
        assert by_id[f"solution_{number}"]["start_frame"] == by_id[f"answer_{number}"]["end_frame"]
        assert by_id[f"solution_padding_{number}"]["start_frame"] == by_id[f"solution_{number}"]["end_frame"]
        if number < 13:
            assert by_id[f"inspect_{number}"]["duration"] == 5
    assert by_id["opening_padding"]["duration"] == .5 and by_id["outro"]["duration"] == 3
    assert cursor == timeline["total_frames"] and timeline["duration"] == cursor / 24
    return {"ok": True, "events": len(events), "answers": "Immediately after each complete response silence",
            "a2_answer_seconds": 10, "b1_answer_seconds": 20, "solution_hold_seconds": 2,
            "recording_plays": 1, "question_repetition": "Identical complete WAV",
            "pause_provenance": "Approved practice timings, not official fixed pauses."}


def document(source_html, timeline, content):
    mappings = {t["id"]: word_mapping(t) for t in timeline["turns"] if t["visible"]}
    scenes, pauses, highlights = [], [], []
    for index, event in enumerate(timeline["events"]):
        body, heading = scene_body(event, content["episode"], content["cards"], mappings)
        counter = ""
        if event["kind"] == "silence":
            counter = f'<span class="countdown" id="count-{index}">{event["duration"]:g} s</span>'
            pauses.append({"index": index, "start": event["start"], "duration": event["duration"]})
        phase = f'<div class="phase"><span class="phase-label">{html.escape(event["phase"])}</span>{counter}</div>'
        if counter:
            phase += f'<div class="progress"><div class="progress-fill" id="fill-{index}"></div></div>'
        oral = event["card"].startswith("item_") and content["cards"][event["card"]]["level"] == "B1"
        scenes.append(
            f'<section id="scene-{index}" class="clip scene" data-start="{event["start"]}" '
            f'data-duration="{event["duration"]}" data-track-index="0" data-event-id="{event["id"]}">'
            f'<div class="eyebrow">{html.escape(heading)}</div>'
            f'<div class="main{" oral" if oral else ""}">{body}</div>{phase}</section>')
        if event.get("visible"):
            highlights.extend(mappings[event["id"]])
    original = list(SCENES.finditer(source_html))
    assert original
    result = source_html[:original[0].start()] + "\n".join(scenes) + source_html[original[-1].end():]
    result, count = re.subn(r'(<(?:div id="root"|audio id="sample-audio")[^>]*data-duration=")[^"]+',
                            lambda m: m[1] + str(timeline["duration"]), result)
    assert count == 2
    result, count = re.subn(r'tl\.to\(clock, \{ value: [^,]+, duration: [^,]+,',
                            f'tl.to(clock, {{ value: {timeline["duration"]}, duration: {timeline["duration"]},',
                            result)
    assert count == 1
    result, count = re.subn(r'const pauses = .*?;', lambda _: f"const pauses = {json.dumps(pauses)};", result)
    assert count == 1
    result, count = re.subn(r'const words = .*?;\s*(?=for \(const word of words\))',
                            lambda _: "const words = " + json.dumps(highlights, ensure_ascii=False) + ";\n    ",
                            result, flags=re.S)
    assert count == 1
    result, count = re.subn(
        r'<p class="amazon">.*?</p>',
        f'<p class="amazon">👇 Amazon:<br><span class="amazon-url">{BOOK_LINK}</span></p>', result)
    assert count == 1
    result = result.replace(
        "<p>Amazon: Link in der<br>Beschreibung oder Bio</p>",
        f'<p>Amazon:<br><span class="cta-book-url">{BOOK_LINK}</span></p>')
    result = result.replace("</style>", """
.amazon-url { font-size:26px;white-space:nowrap; }
html[data-resolution="portrait"] .amazon-url { font-size:32px; }
.cta-book-url { white-space:nowrap; }
</style>""")
    return result, mappings


def prepare(build, source):
    if build.exists() or build == source:
        raise ValueError("Use a fresh build; never overwrite the frozen source.")
    delivery = verify_source(source)
    source_timeline = read(source / "timeline.json")
    episode = copy.deepcopy(read(source / "sample_content.json")["episode"])
    manifest = copy.deepcopy(read(source / "audio_manifest.json"))
    original_turns = {t["id"]: t for t in source_timeline["turns"]}
    for ident, count in CUT_WORDS.items():
        episode[ident] = " ".join(original_turns[ident]["text"].split()[:count])
    episode.pop("solutions_instruction")
    episode["promotion"]["amazon_url"] = "https://" + BOOK_LINK
    planned = revised_plan(read(source / "speech_plan.json"), episode)
    build.mkdir(parents=True)
    audio = build / "audio"
    audio.mkdir()
    cuts = {}
    for ident, count in CUT_WORDS.items():
        turn = original_turns[ident]
        words = turn["words"]
        assert words[count - 1]["word"].endswith(".")
        endpoint = round((words[count - 1]["end"] + words[count]["start"]) / 2 * 48000)
        target = audio / f"{ident}.wav"
        with wave.open(manifest[ident]["audio"], "rb") as wav:
            pcm = wav.readframes(endpoint)
        assert len(pcm) == endpoint * 2
        write_wav(target, pcm)
        cuts[ident] = {"source_audio": manifest[ident]["audio"], "source_sha256": manifest[ident]["sha256"],
                       "start_sample": 0, "end_sample": endpoint, "retained_words": count,
                       "removed_text": " ".join(turn["text"].split()[count:])}
        manifest[ident].update(text=episode[ident], audio=str(target), sha256=sha256_file(target),
                               frames=endpoint, wav_duration=endpoint / 48000,
                               processed_audio=str(target), processed_sha256=sha256_file(target),
                               derivation=cuts[ident])
    manifest.pop("solutions_instruction")
    timeline = schedule(planned["events"], manifest)
    timeline["practice_mode"] = "guided_per_exercise_answers"
    timeline["word_alignment"] = {
        "method": "Inherited measured local words; exact audio-prefix sentence cuts, no estimated word timing.",
        "source_alignment_sha256": sha256_file(source / "word_alignment.json")}
    for turn in timeline["turns"]:
        if turn["visible"]:
            previous = original_turns[turn["id"]]
            turn.update(words=copy.deepcopy(previous["words"][:CUT_WORDS.get(turn["id"], len(previous["words"]))]),
                        alignment_key=previous["alignment_key"])
    compare_sequence(timeline)
    atomic_json(build / "speech_plan.json", planned)
    atomic_json(build / "sample_content.json", {"episode": episode, "cards": planned["cards"]})
    atomic_json(build / "audio_manifest.json", manifest)
    atomic_json(build / "timeline.json", timeline)
    atomic_json(build / "word_alignment.json", {
        "provenance": timeline["word_alignment"],
        "turns": [{k: t[k] for k in ("id", "start", "words", "alignment_key")}
                  for t in timeline["turns"] if t["visible"]]})
    write_wav(build / "dialogue.wav", mix_events(timeline["events"]))
    source_pins = {str(source / "delivery_manifest.json"): sha256_file(source / "delivery_manifest.json"),
                   str(source / "audio_review_resolution.json"): sha256_file(source / "audio_review_resolution.json")}
    atomic_json(build / "revision.json", {
        "source": str(source), "source_files": len(delivery["files"]), "source_pins": source_pins,
        "authorization": "2026-11-17: reveal after every exercise; A2 10s, B1 20s; reuse spoken answer plus 2s hold.",
        "book_link_authorization": "2026-11-17: show amzn.eu/d/0dDgJ1ZT directly near Amazon.",
        "exercise_review": "Inherited unchanged Claude Sonnet 5.5 reviewed questions, recordings, keys and rubrics.",
        "cuts": cuts, "new_tts": False, "source_code_inputs": delivery["code_inputs"],
        "code_inputs": {str(Path(__file__)): sha256_file(Path(__file__))}})
    receipts = {}
    for layout in ("landscape", "portrait"):
        folder = build / layout
        shutil.copytree(source / layout / "assets", folder / "assets")
        shutil.copyfile(build / "dialogue.wav", folder / "assets" / "dialogue.wav")
        source_html = (source / layout / "index.html").read_text(encoding="utf-8")
        composed, mappings = document(source_html, timeline, read(build / "sample_content.json"))
        (folder / "index.html").write_text(composed, encoding="utf-8")
        shutil.copyfile(source / layout / "hyperframes.json", folder / "hyperframes.json")
        atomic_json(folder / "assets_manifest.json", {
            p.name: sha256_file(p) for p in (folder / "assets").iterdir() if p.is_file()})
        receipts[layout] = {"html_sha256": sha256_file(folder / "index.html")}
    atomic_json(build / "composition_receipt.json", {"layouts": receipts, "word_mappings": mappings,
                "timeline_sha256": sha256_file(build / "timeline.json"),
                "generator_sha256": sha256_file(Path(__file__))})
    print(f"Inline fide prepared: {timeline['total_frames']} frames / {timeline['duration']:.3f}s.", flush=True)


def validate(build, encoded=False):
    revision = read(build / "revision.json")
    verify_files(revision["source_pins"])
    verify_files(revision["source_code_inputs"])
    verify_files(revision["code_inputs"])
    source = Path(revision["source"])
    content, timeline = read(build / "sample_content.json"), read(build / "timeline.json")
    original_content = read(source / "sample_content.json")
    assert content["cards"] == original_content["cards"]
    expected_episode = copy.deepcopy(original_content["episode"])
    for ident, count in CUT_WORDS.items():
        expected_episode[ident] = " ".join(expected_episode[ident].split()[:count])
    expected_episode.pop("solutions_instruction")
    expected_episode["promotion"]["amazon_url"] = "https://" + BOOK_LINK
    assert content["episode"] == expected_episode
    planned = revised_plan(read(source / "speech_plan.json"), expected_episode)
    assert read(build / "speech_plan.json") == planned
    manifest = read(build / "audio_manifest.json")
    original_manifest = read(source / "audio_manifest.json")
    assert set(manifest) == {t["id"] for t in planned["turns"]}
    for turn in planned["turns"]:
        ident, actual = turn["id"], manifest[turn["id"]]
        assert all(actual[k] == v for k, v in turn.items())
        verify_files({actual["audio"]: actual["sha256"]})
        assert audio_info(Path(actual["audio"])) == actual["frames"]
        if ident not in CUT_WORDS:
            assert actual == original_manifest[ident], f"Unchanged speech modified: {ident}"
        else:
            cut = revision["cuts"][ident]
            verify_files({cut["source_audio"]: cut["source_sha256"]})
            previous = next(t for t in read(source / "timeline.json")["turns"] if t["id"] == ident)
            count = CUT_WORDS[ident]
            assert cut["end_sample"] == round((previous["words"][count - 1]["end"] +
                                              previous["words"][count]["start"]) / 2 * 48000)
            with wave.open(cut["source_audio"], "rb") as original, wave.open(actual["audio"], "rb") as current:
                assert current.readframes(current.getnframes()) == original.readframes(cut["end_sample"])
    sequence = compare_sequence(timeline)
    expected = schedule(planned["events"], manifest)
    assert expected["events"] == timeline["events"]
    assert timeline["total_frames"] == expected["total_frames"]
    original_turns = {t["id"]: t for t in read(source / "timeline.json")["turns"]}
    assert len(timeline["turns"]) == len(expected["turns"])
    for turn, scheduled in zip(timeline["turns"], expected["turns"]):
        assert {k: v for k, v in turn.items() if k not in ("words", "alignment_key")} == scheduled
        if turn["visible"]:
            previous = original_turns[turn["id"]]
            assert turn["words"] == previous["words"][:CUT_WORDS.get(turn["id"], len(previous["words"]))]
            assert turn["alignment_key"] == previous["alignment_key"]
    assert audio_info(build / "dialogue.wav") == timeline["total_frames"] * 2000
    with wave.open(str(build / "dialogue.wav"), "rb") as track:
        for event in timeline["events"]:
            pcm = block(track, event["start_frame"] * 2000, event["end_frame"] * 2000)
            if event["kind"] == "silence":
                assert not any(pcm), event["id"]
            else:
                with wave.open(event["audio"], "rb") as clip:
                    original = clip.readframes(clip.getnframes())
                assert pcm[:len(original)] == original and not any(pcm[len(original):]), event["id"]
    for layout in ("landscape", "portrait"):
        folder = build / layout
        composed, _ = document((source / layout / "index.html").read_text(encoding="utf-8"), timeline, content)
        actual = (folder / "index.html").read_text(encoding="utf-8")
        assert actual == composed
        assert "Die Lösungen folgen erst nach allen Aufgaben." not in actual
        assert "Jetzt folgen die Lösungen" not in actual
        assert actual.count(f'class="amazon-url">{BOOK_LINK}</span>') == 1
        assert actual.count(f'class="cta-book-url">{BOOK_LINK}</span>') == 2
        for body, event in zip(SCENES.findall(actual), timeline["events"]):
            keys = re.findall(r'data-answer="([^"]+)"', body)
            if event["card"].startswith("solution_"):
                number = int(event["card"].split("_")[-1])
                assert keys == [f'{number}:{content["cards"][f"item_{number}"].get("answer", "model")}']
            else:
                assert not keys, event["id"]
            if event["card"].startswith("item_"):
                item = content["cards"][event["card"]]
                assert html.escape(item["question"]) not in body
                assert html.escape(item["recording"]) not in body
        verify_files({str(folder / "assets" / name): digest
                      for name, digest in read(folder / "assets_manifest.json").items()})
    report = {"sequence": sequence, "source_pcm": "Exact source WAVs or explicitly bound sentence prefixes",
              "unchanged_speech_clips": len(manifest) - len(CUT_WORDS),
              "cut_speech_clips": len(CUT_WORDS), "frames": timeline["total_frames"],
              "duration": timeline["duration"], "human_listening": False}
    if encoded:
        report["encoded"] = {layout: encoded_events(build, timeline, layout) for layout in ("landscape", "portrait")}
    atomic_json(build / ("validation.json" if encoded else "source_validation.json"), report)
    print(f"Inline fide {'encoded' if encoded else 'source'} validation passed.", flush=True)


def check(build):
    validate(build)
    checks = {}
    for layout in ("landscape", "portrait"):
        folder = build / layout
        run(["node", str(ROOT / "check_fide_layout.cjs"), str(folder / "index.html"),
             str(build / f"geometry_{layout}.json"), layout], build / f"geometry_{layout}.log")
        run([sys.executable, "-B", "-X", "utf8", str(ROOT / "hyperframes_local.py"), "check",
             str(folder), "--json", "--at-transitions", "--snapshots", "--no-browser-gpu",
             "--timeout", "4m"], build / f"check_{layout}.log")
        report_path = max((folder / ".hyperframes" / "artifacts" / "checks").glob("*.json"),
                          key=lambda p: p.stat().st_mtime_ns)
        report = read(report_path)
        assert report["ok"] and not report.get("browserSkipped", False)
        checks[layout] = {"report": str(report_path), "sha256": sha256_file(report_path),
                          "html": sha256_file(folder / "index.html"),
                          "geometry": sha256_file(build / f"geometry_{layout}.json")}
    atomic_json(build / "pre_render_checks.json", checks)


def render(build):
    validate(build)
    checks = read(build / "pre_render_checks.json")
    audio = read(build / "audio_review_resolution.json")
    assert audio["audio_manifest_sha256"] == sha256_file(build / "audio_manifest.json")
    assert audio["status"] == "pass_with_asr_notes"
    verify_files(audio["review_files_sha256"])
    approval = read(build / "visual_approval.json")
    assert approval["contact_sheets_inspected"]
    assert approval["browser_visual_review_sha256"] == sha256_file(build / "browser_visual_review.json")
    for layout, receipt in checks.items():
        verify_files({receipt["report"]: receipt["sha256"], str(build / layout / "index.html"): receipt["html"],
                      str(build / f"geometry_{layout}.json"): receipt["geometry"]})
        master, final = build / f"render_{layout}.mp4", build / f"production_{layout}.mp4"
        if master.exists() or final.exists():
            raise ValueError("Export exists; use a fresh revision.")
        run([sys.executable, "-B", "-X", "utf8", str(ROOT / "hyperframes_local.py"), "render",
             str(build / layout), "--fps", "24", "--quality", "delivery", "--workers", "2",
             "--no-browser-gpu", "--output", str(master)], build / f"render_{layout}.log")
        run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(master), "-i", str(build / "dialogue.wav"),
             "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-ar", "48000", "-ac", "1", "-t", str(read(build / "timeline.json")["duration"]),
             "-movflags", "+faststart", str(final)], build / f"mux_{layout}.log")
        print(f"Inline fide export ready: {final}", flush=True)


def freeze(build):
    if (build / "delivery_manifest.json").exists():
        raise ValueError("Already frozen.")
    validate(build, encoded=True)
    approval = read(build / "visual_approval.json")
    assert approval["contact_sheets_inspected"] and approval["encoded_contact_sheets_inspected"]
    assert approval["export_visual_review_sha256"] == sha256_file(build / "export_visual_review.json")
    visual = read(build / "export_visual_review.json")
    for layout, details in visual["layouts"].items():
        verify_files({str(build / f"contact_{layout}" / name): digest for name, digest in details["browser_frames"].items()})
        for index, frame in enumerate(details["export_comparisons"], 1):
            assert frame["mean_absolute_rgb_error"] < 4 and frame["promotion_mean_absolute_rgb_error"] < 4
            verify_files({str(build / f"encoded_{layout}" / f"frame-{index:03d}.png"): frame["export_sha256"]})
    revision = read(build / "revision.json")
    original = verify_source(Path(revision["source"]))
    code = {**original["code_inputs"], **revision["code_inputs"]}
    code[str(ROOT / "review_fide_inline.py")] = sha256_file(ROOT / "review_fide_inline.py")
    files = {str(p.relative_to(build)): sha256_file(p) for p in build.rglob("*")
             if p.is_file() and p.name not in ("delivery_manifest.json", "delivery_audit.json")
             and ".hyperframes" not in p.parts}
    report = read(build / "validation.json")
    atomic_json(build / "delivery_manifest.json", {
        "scope": "Full fide A2-B1 guided per-exercise answers, both native aspect ratios",
        "files": files, "code_inputs": code, "source_manifest": revision["source_pins"],
        "frames": report["frames"], "duration": report["duration"],
        "outputs": {layout: {"sha256": d["sha256"]} for layout, d in report["encoded"].items()},
        "human_listening": False, "uploaded": False})
    verify_files({str(build / name): digest for name, digest in files.items()})
    verify_files(code)
    atomic_json(build / "delivery_audit.json", {
        "manifest_sha256": sha256_file(build / "delivery_manifest.json"), "files_rehashed": len(files),
        "code_pins_rehashed": len(code), "source_files_rehashed": len(original["files"]),
        "source_code_pins_rehashed": len(original["code_inputs"]), "uploaded": False})
    print(f"Inline fide frozen: {build}", flush=True)


def publish(build, output):
    from publish_fide_assets import caption, publish as original_publish
    from publication_assets import timestamp
    if output.exists():
        raise ValueError("Use a fresh posts directory.")
    # Reuse the unchanged cover layout, but never retain the old caption sequence.
    original_publish(build, output)
    timeline = read(build / "timeline.json")
    episode = read(build / "sample_content.json")["episode"]
    events = {e["id"]: e for e in timeline["events"]}
    old_claim = ("Alle Lösungen folgen erst nach dem gesamten Test: A2 mit Bild und Erklärung, "
                 "B1 mit möglichen Antworten.")
    for platform in ("youtube", "tiktok", "instagram"):
        value = caption(platform, episode, timeline).replace(
            old_claim, "Nach jeder Aufgabe folgt direkt die Lösung: A2 mit Bild und Erklärung, B1 mit einer möglichen Antwort.")
        value = value.replace("Prüfungssimulation mit Lösungen", "Geführte Hörübung mit Lösungen")
        if platform == "youtube":
            value = re.sub(r'\nKapitel:\n.*?\n\nHörtexte', "\nKapitel:\n" + "\n".join(
                f'{timestamp(0 if ident is None else events[ident]["start"])} {label}' for ident, label in (
                    (None, "Start und Anleitung"), ("context_a2_sbb", "A2 · Bahnhof · Aufgaben 7–9"),
                    ("context_a2_tram", "A2 · Tram · Aufgaben 10–12"), ("transition", "Wechsel zu B1"),
                    ("context_b1_verwaltung", "B1 · Hausverwaltung · Aufgaben 13–15"),
                    ("context_b1_nachbarn", "B1 · Nachbarschaft · Aufgaben 16–18"),
                    ("end_test", "Abschluss"), ("cta", "Mehr üben mit dem Buch"))) + "\n\nHörtexte", value, flags=re.S)
        value = value.replace("Jeder Hörtext einmal.", "Danach die vollständige gesprochene Lösung und zwei Sekunden Haltezeit. Jeder Hörtext einmal.")
        assert old_claim not in value and len(value) <= (5000 if platform == "youtube" else 2200)
        (output / f"{platform}.txt").write_text(value, encoding="utf-8")
    manifest = read(output / "publication_manifest.json")
    manifest["inputs"][str(Path(__file__))] = sha256_file(Path(__file__))
    manifest["assets"] = {p.name: sha256_file(p) for p in output.iterdir()
                          if p.is_file() and p.name != "publication_manifest.json"}
    manifest["presentation"] = "Per-exercise spoken answers after complete 10/20s response pauses; 2s holds."
    atomic_json(output / "publication_manifest.json", manifest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "check", "validate", "render", "freeze", "publish"))
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--encoded", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    build = args.build.resolve()
    if args.stage == "prepare":
        prepare(build, args.source.resolve())
    elif args.stage == "validate":
        validate(build, args.encoded)
    elif args.stage == "publish":
        if args.output is None:
            parser.error("--output is required for publish")
        publish(build, args.output.resolve())
    else:
        {"check": check, "render": render, "freeze": freeze}[args.stage](build)
