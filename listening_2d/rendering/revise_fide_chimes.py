"""Add complete pre-answer reveal chimes and restore promotion cues in a fresh fide build."""

import argparse
import copy
import html
import math
import re
import shutil
import sys
import wave
from pathlib import Path

import listening_2d.rendering.revise_fide_inline as inline
from listening_2d.rendering.deliver_fide import run
from listening_2d.preparation.prepare_fide import ROOT, atomic_json, read, schedule, sha256_file, verify_files
from listening_2d.preparation.prepare_sample import mix_events, write_wav
from listening_2d.checks.validate_full import audio_info, block, encoded_events

SOURCE = ROOT / "builds" / "fide_a2_b1_listening_inline_r1"
CHIME_SOURCE = ROOT / "builds" / "oeif_b2_listening_display_r2" / "full" / "audio_manifest.json"
CUES = {"landscape": "Link in der Beschreibung", "portrait": "Link in der Bio / Beschreibung"}


def verify_source(source):
    delivery = read(source / "delivery_manifest.json")
    verify_files({str(source / name): digest for name, digest in delivery["files"].items()})
    verify_files(delivery["code_inputs"])
    verify_files(delivery["source_manifest"])
    inline.verify_source(Path(read(source / "revision.json")["source"]))
    return delivery


def revised_plan(source_plan):
    result = copy.deepcopy(source_plan)
    events = []
    for event in result["events"]:
        if re.fullmatch(r"solution_\d+", event["id"]):
            number = event["id"].split("_")[-1]
            events.append({"id": f"solution_chime_{number}", "kind": "chime",
                           "card": event["card"], "phase": "Lösung vergleichen",
                           "audio_id": "chime_remove", "sfx_id": "chime_remove", "visible": False})
        events.append(event)
    result["events"] = events
    return result


def compare_sequence(timeline, source_timeline, chime_samples):
    inline.compare_sequence(source_timeline)
    expected_ids = []
    for event in source_timeline["events"]:
        if re.fullmatch(r"solution_\d+", event["id"]):
            expected_ids.append(event["id"].replace("solution_", "solution_chime_"))
        expected_ids.append(event["id"])
    assert [e["id"] for e in timeline["events"]] == expected_ids
    original = {e["id"]: e for e in source_timeline["events"]}
    by_id = {e["id"]: e for e in timeline["events"]}
    time_keys = {"start_frame", "end_frame", "start", "end"}
    cursor = 0
    for event in timeline["events"]:
        assert event["start_frame"] == cursor
        assert event["start"] == cursor / 24 and event["end"] == event["end_frame"] / 24
        assert event["duration"] == (event["end_frame"] - cursor) / 24
        if event["id"] in original:
            assert {k: v for k, v in event.items() if k not in time_keys} == {
                k: v for k, v in original[event["id"]].items() if k not in time_keys}
        else:
            assert event["kind"] == "chime" and event["audio_id"] == "chime_remove"
            assert event["audio_samples"] == chime_samples
            assert event["end_frame"] - cursor == math.ceil(chime_samples / 2000)
        cursor = event["end_frame"]
    for number in range(7, 19):
        answer, chime, speech, hold = (by_id[f"{prefix}_{number}"] for prefix in (
            "answer", "solution_chime", "solution", "solution_padding"))
        assert answer["duration"] == (10 if number < 13 else 20)
        assert answer["end_frame"] == chime["start_frame"]
        assert chime["end_frame"] == speech["start_frame"]
        assert chime["start_frame"] * 2000 + chime_samples <= speech["start_frame"] * 2000
        assert speech["end_frame"] == hold["start_frame"] and hold["duration"] == 2
        assert chime["card"] == speech["card"] == f"solution_{number}"
    assert cursor == timeline["total_frames"] == source_timeline["total_frames"] + 12 * math.ceil(chime_samples / 2000)
    assert timeline["duration"] == cursor / 24
    return {"ok": True, "events": len(expected_ids), "reveal_chimes": 12,
            "sequence": "Full response silence, reveal and complete chime, unchanged spoken answer, two-second hold",
            "chime_samples": chime_samples, "chime_frames": math.ceil(chime_samples / 2000),
            "a2_response_seconds": 10, "b1_response_seconds": 20}


def document(source_html, timeline, content, layout):
    result, mappings = inline.document(source_html, timeline, content)
    cue = html.escape(CUES[layout])
    result = result.replace('👇 Amazon:<br><span class="amazon-url">',
                            f'👇 Amazon:<br><span class="amazon-cue">{cue}</span><br><span class="amazon-url">')
    result = result.replace('<p>Amazon:<br><span class="cta-book-url">',
                            f'<p>👇 Amazon: {cue}<br><span class="cta-book-url">')
    result = result.replace("<p>Sprechen · Schreiben<br>und Hören</p>",
                            '<p class="book-topics">Sprechen · Schreiben<br> und Hören</p>')
    result = result.replace("</style>", """
html[data-resolution="portrait"] aside h2 { margin:4px 0 8px; }
html[data-resolution="portrait"] aside p { margin-bottom:8px; }
html[data-resolution="portrait"] .book-topics br { display:none; }
</style>""")
    assert result.count('class="amazon-cue"') == 1
    assert result.count(cue) == 3
    assert result.count(f'class="amazon-url">{inline.BOOK_LINK}</span>') == 1
    assert result.count(f'class="cta-book-url">{inline.BOOK_LINK}</span>') == 2
    return result, mappings


def prepare(build, source):
    if build.exists():
        raise ValueError("Use a fresh build; frozen deliveries must stay unchanged.")
    delivery = verify_source(source)
    chime = copy.deepcopy(read(CHIME_SOURCE)["chime_remove"])
    verify_files({chime["audio"]: chime["sha256"]})
    assert audio_info(Path(chime["audio"])) == chime["frames"]
    chime.update(text="", speaker="sfx")
    manifest = {**read(source / "audio_manifest.json"), "chime_remove": chime}
    plan = revised_plan(read(source / "speech_plan.json"))
    timeline = schedule(plan["events"], manifest)
    timeline["practice_mode"] = "guided_per_exercise_answers_with_chime"
    old_timeline = read(source / "timeline.json")
    timeline["word_alignment"] = old_timeline["word_alignment"]
    old_turns = {t["id"]: t for t in old_timeline["turns"]}
    for turn in timeline["turns"]:
        if turn["visible"]:
            previous = old_turns[turn["id"]]
            turn.update(words=copy.deepcopy(previous["words"]), alignment_key=previous["alignment_key"])
    compare_sequence(timeline, old_timeline, chime["frames"])
    build.mkdir(parents=True)
    atomic_json(build / "speech_plan.json", plan)
    atomic_json(build / "sample_content.json", read(source / "sample_content.json"))
    atomic_json(build / "audio_manifest.json", manifest)
    atomic_json(build / "timeline.json", timeline)
    atomic_json(build / "word_alignment.json", {
        "provenance": "Unchanged speech and measured local word intervals; only event starts retimed.",
        "turns": [{k: t[k] for k in ("id", "start", "words", "alignment_key")}
                  for t in timeline["turns"] if t["visible"]]})
    write_wav(build / "dialogue.wav", mix_events(timeline["events"]))
    from listening_2d.checks.review_fide_inline import __file__ as reviewer
    code = {str(Path(__file__)): sha256_file(Path(__file__)),
            str(Path(reviewer)): sha256_file(Path(reviewer))}
    atomic_json(build / "revision.json", {
        "source": str(source), "source_code_inputs": delivery["code_inputs"], "code_inputs": code,
        "source_pins": {str(source / name): sha256_file(source / name) for name in (
            "delivery_manifest.json", "audio_review_resolution.json")},
        "chime_source": {str(CHIME_SOURCE): sha256_file(CHIME_SOURCE),
                         chime["audio"]: chime["sha256"]},
        "authorization": "2026-11-17: chime before answer TTS; retain direct URL and restore bio/description cue.",
        "new_tts": False, "new_tempo_processing": False})
    receipts = {}
    for layout in ("landscape", "portrait"):
        folder = build / layout
        shutil.copytree(source / layout / "assets", folder / "assets")
        shutil.copyfile(build / "dialogue.wav", folder / "assets" / "dialogue.wav")
        markup, mappings = document((source / layout / "index.html").read_text(encoding="utf-8"),
                                    timeline, read(build / "sample_content.json"), layout)
        (folder / "index.html").write_text(markup, encoding="utf-8")
        shutil.copyfile(source / layout / "hyperframes.json", folder / "hyperframes.json")
        atomic_json(folder / "assets_manifest.json", {
            p.name: sha256_file(p) for p in (folder / "assets").iterdir() if p.is_file()})
        receipts[layout] = {"html_sha256": sha256_file(folder / "index.html")}
    atomic_json(build / "composition_receipt.json", {"layouts": receipts, "word_mappings": mappings,
                "timeline_sha256": sha256_file(build / "timeline.json"), "code_inputs": code})
    atomic_json(build / "audio_review_resolution.json", {
        "status": "pass_with_asr_notes", "audio_manifest_sha256": sha256_file(build / "audio_manifest.json"),
        "review_files_sha256": {str(source / "audio_review_resolution.json"):
                               sha256_file(source / "audio_review_resolution.json")},
        "notes": "All 47 speech WAVs unchanged, including exact sentence prefixes and inherited ASR/low-alignment notes. "
                 "Reuse complete approved 0.8x/reverb remove chime without another processing pass. No human listening."})
    print(f"Fide chime revision prepared: {timeline['total_frames']} frames / {timeline['duration']:.3f}s.", flush=True)


def validate(build, encoded=False):
    revision = read(build / "revision.json")
    for key in ("source_pins", "source_code_inputs", "code_inputs", "chime_source"):
        verify_files(revision[key])
    source = Path(revision["source"])
    timeline, manifest = read(build / "timeline.json"), read(build / "audio_manifest.json")
    old_manifest, old_timeline = read(source / "audio_manifest.json"), read(source / "timeline.json")
    assert {k: v for k, v in manifest.items() if k != "chime_remove"} == old_manifest
    expected_chime = {**read(CHIME_SOURCE)["chime_remove"], "text": "", "speaker": "sfx"}
    assert manifest["chime_remove"] == expected_chime
    plan = revised_plan(read(source / "speech_plan.json"))
    assert plan == read(build / "speech_plan.json")
    assert read(build / "sample_content.json") == read(source / "sample_content.json")
    scheduled = schedule(plan["events"], manifest)
    assert timeline["events"] == scheduled["events"]
    source_turns = {t["id"]: t for t in old_timeline["turns"]}
    assert len(timeline["turns"]) == len(old_timeline["turns"]) == 59
    for turn, expected in zip(timeline["turns"], scheduled["turns"]):
        assert {k: v for k, v in turn.items() if k not in ("words", "alignment_key")} == expected
        previous = source_turns[turn["id"]]
        assert {k: v for k, v in turn.items() if k not in ("start", "end")} == {
            k: v for k, v in previous.items() if k not in ("start", "end")}
    for info in manifest.values():
        verify_files({info["audio"]: info["sha256"]})
        assert audio_info(Path(info["audio"])) == info["frames"]
    sequence = compare_sequence(timeline, old_timeline, manifest["chime_remove"]["frames"])
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
    content = read(build / "sample_content.json")
    for layout in ("landscape", "portrait"):
        folder = build / layout
        expected, _ = document((source / layout / "index.html").read_text(encoding="utf-8"),
                               timeline, content, layout)
        markup = (folder / "index.html").read_text(encoding="utf-8")
        assert markup == expected
        for scene, event in zip(inline.SCENES.findall(markup), timeline["events"]):
            keys = re.findall(r'data-answer="([^"]+)"', scene)
            assert bool(keys) == event["card"].startswith("solution_"), event["id"]
            if event["card"].startswith("item_"):
                item = content["cards"][event["card"]]
                assert html.escape(item["question"]) not in scene
                assert html.escape(item["recording"]) not in scene
        verify_files({str(folder / "assets" / name): digest
                      for name, digest in read(folder / "assets_manifest.json").items()})
    report = {"sequence": sequence, "unchanged_speech_clips": len(old_manifest),
              "new_tts": False, "frames": timeline["total_frames"], "duration": timeline["duration"],
              "human_listening": False}
    if encoded:
        report["encoded"] = {layout: encoded_events(build, timeline, layout) for layout in CUES}
    atomic_json(build / ("validation.json" if encoded else "source_validation.json"), report)
    print(f"Fide chime {'encoded' if encoded else 'source'} validation passed.", flush=True)


def check(build):
    validate(build)
    checks = {}
    for layout in CUES:
        folder = build / layout
        run(["node", str(ROOT / "checks/check_fide_layout.cjs"), str(folder / "index.html"),
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
    checks, audio = read(build / "pre_render_checks.json"), read(build / "audio_review_resolution.json")
    assert audio["status"] == "pass_with_asr_notes"
    assert audio["audio_manifest_sha256"] == sha256_file(build / "audio_manifest.json")
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


def freeze(build):
    if (build / "delivery_manifest.json").exists():
        raise ValueError("Already frozen.")
    validate(build, True)
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
    files = {str(p.relative_to(build)): sha256_file(p) for p in build.rglob("*")
             if p.is_file() and ".hyperframes" not in p.parts}
    report = read(build / "validation.json")
    atomic_json(build / "delivery_manifest.json", {
        "scope": "Full fide A2-B1 per-exercise chime then spoken answer; direct URL plus promotion cue",
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


def publish(build, output):
    inline.publish(build, output)
    for platform in ("youtube", "tiktok", "instagram"):
        path = output / f"{platform}.txt"
        text = path.read_text(encoding="utf-8")
        text = text.replace("Danach die vollständige gesprochene Lösung",
                            "Danach der vollständige Lösungsklang, dann die vollständige gesprochene Lösung")
        text = text.replace("keine Musik oder Soundeffekte.",
                            "keine Musik. SFX: Mixkit Software interface remove; 0,8x und leichter Nachhall. "
                            "Mixkit Sound Effects Free License: https://mixkit.co/license/#sfxFree")
        cue = "Link in der Beschreibung" if platform == "youtube" else "Link in der Bio / Beschreibung"
        text = text.replace("Amazon: https://", f"👇 Amazon: {cue}\nhttps://")
        assert len(text) <= (5000 if platform == "youtube" else 2200)
        path.write_text(text, encoding="utf-8")
    manifest = read(output / "publication_manifest.json")
    manifest["inputs"][str(Path(__file__))] = sha256_file(Path(__file__))
    manifest["assets"] = {p.name: sha256_file(p) for p in output.iterdir()
                          if p.is_file() and p.name != "publication_manifest.json"}
    manifest["presentation"] = "Full response silence, reveal chime, existing answer TTS, two-second hold."
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
