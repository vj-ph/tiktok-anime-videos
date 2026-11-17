"""Six frame-exact portrait practice edits, preserving the frozen TEF exercise blocks."""

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

from prepare_tef import (
    FPS, FRAME_SAMPLES, RATE, ROOT, atomic_json, inspect_wav, mix_events, normalize,
    prepare_turn_audio, read, review, sha256_file, synthesize, verify_files, write_wav,
)
from align_words import align_build, validate_words
from compose_tef import compose
from deliver_tef import check, encoded, run

CONFIG = ROOT / "episodes" / "tef_canada_listening_01_social_six.json"


def settings(config_path):
    config = read(config_path)
    source = (config_path.parent / config["source"]).resolve(strict=True)
    if config["duration_limit_seconds"] != 180 or config["outro_frames"] < 1:
        raise ValueError("This approved derivative needs a strict 180-second cap and an end hold.")
    families = [f for p in config["parts"] for f in p["families"]]
    original = read(source / "content.json")
    if (len(config["parts"]) != 6 or [p["number"] for p in config["parts"]] != list(range(1, 7))
            or families != [g["family"] for g in original["groups"]]):
        raise ValueError("Select each complete family once, in source order, across six parts.")
    return config, source


def verify_source(source, digest):
    manifest_path = source / "delivery_manifest.json"
    if sha256_file(manifest_path) != digest:
        raise ValueError("The frozen source manifest changed.")
    manifest = read(manifest_path)
    verify_files({str(source / p): h for p, h in manifest["files"].items()})
    timeline = read(source / "timeline.json")
    if (timeline["answer_reveal"] != "after_exercise" or not timeline["chime_enabled"]
            or timeline["fps"] != 24 or timeline["sample_rate"] != 48000):
        raise ValueError("Use the verified 24-fps immediate-correction/chime source.")
    print(f"Verified {len(manifest['files'])} unchanged frozen source files.", flush=True)


def speech_event(ident, item, start):
    count = math.ceil(item["frames"] / FRAME_SAMPLES)
    end = start + count
    return {"id": ident, "kind": "speech", "start_frame": start, "end_frame": end,
            "start": start / FPS, "end": end / FPS, "duration": count / FPS, "visible": True,
            "audio_id": ident, "audio": item["audio"], "sha256": item["sha256"],
            "audio_samples": item["frames"], "text": item["text"]}


def edit_timeline(original, families, title, cta, outro_frames=24):
    events = original["events"]
    if not families or outro_frames < 1:
        raise ValueError("Select complete families and a positive end hold.")
    starts = [i for i, e in enumerate(events) if e["id"] == "instruction_" + families[0]]
    if len(starts) != 1 or len(families) != len(set(families)):
        raise ValueError("Cuts must begin at a unique complete family instruction.")
    first = starts[0]
    last = first + 1
    while last < len(events) and (events[last].get("family") in families
                                  or events[last]["kind"] == "sfx"
                                  or events[last]["id"].startswith("solution_")):
        last += 1
    body = copy.deepcopy(events[first:last])
    if ([e["family"] for e in body if e["id"].startswith("instruction_")] != families
            or body[-1]["kind"] != "speech" or not body[-1]["id"].startswith("solution_")):
        raise ValueError("Cuts must retain complete consecutive families and all final explanations.")
    for event in body:
        if event["kind"] == "recording":
            reveals = [e for e in body if e["id"].startswith("solution_")
                       and e.get("recording_id") == event["recording_id"]]
            if ([e["number"] for e in reveals] != event["numbers"]
                    or any(e["reveal_numbers"] != event["numbers"] for e in reveals)):
                raise ValueError("Every shared pair needs both complete explanations and answers.")
    source_start, source_end = body[0]["start_frame"], body[-1]["end_frame"]
    opening = speech_event("title", title, 0)
    shift = opening["end_frame"] - source_start
    for event in body:
        for key in ("start_frame", "end_frame"):
            event[key] += shift
        event.update(start=event["start_frame"] / FPS, end=event["end_frame"] / FPS)
    closing = speech_event("cta", cta, body[-1]["end_frame"])
    end = closing["end_frame"] + outro_frames
    if end >= 180 * FPS:
        raise ValueError("The complete Reel including narration and hold must be strictly below 180 seconds.")
    hold = {"id": "outro", "kind": "silence", "start_frame": closing["end_frame"],
            "end_frame": end, "start": closing["end"], "end": end / FPS,
            "duration": outro_frames / FPS}
    old_turns = {t["id"]: t for t in original["turns"]}
    selected = [opening] + body + [closing, hold]
    turns = []
    for event in selected:
        if event["kind"] not in ("speech", "recording"):
            continue
        item = title if event["id"] == "title" else cta if event["id"] == "cta" else old_turns[event["id"]]
        turn = {**copy.deepcopy(item), "id": event["id"], "start": event["start"],
                "end": event["end"], "visible": event.get("visible", False), "kind": event["kind"]}
        if turn["visible"]:
            validate_words(turn["words"], turn["text"], turn["wav_duration"])
        turns.append(turn)
    timeline = {**copy.deepcopy(original), "total_frames": end, "duration": end / FPS,
                "events": selected, "turns": turns, "duration_limit_seconds": 180,
                "practice_mode": "six_part_guided_practice"}
    mapping = {"source_start_frame": source_start, "source_end_frame": source_end,
               "output_start_frame": opening["end_frame"], "output_end_frame": closing["start_frame"],
               "families": families, "source_event_ids": [e["id"] for e in body]}
    return timeline, mapping


def speech(config_path, destination):
    from huggingface_hub import snapshot_download
    from prepare_audio import MODEL
    config, source = settings(config_path)
    verify_source(source, config["source_manifest_sha256"])
    build = destination / "wrappers"
    build.mkdir(parents=True, exist_ok=True)
    voice = read(source / "voice_references.json")["narrator"]
    verify_files({voice["audio"]: voice["sha256"]})
    transcript = ROOT.parent / "pilot_3d/assets/voices/fr_ca_qc_narrator_f01_reference.txt"
    if transcript.read_text(encoding="utf-8").strip() != voice["reference_text"].strip():
        raise ValueError("The exact approved narrator reference text differs.")
    turns = [{"id": f"part_{p['number']:02d}", "text": f"TEF Canada. Partie {p['spoken_number']} sur six.",
              "speaker": "narrator", "name": "French Compass", "pause_after": 0} for p in config["parts"]]
    turns.append({"id": "cta", "text": config["cta"], "speaker": "narrator",
                  "name": "French Compass", "pause_after": 0})
    plan = {"turns": turns, "voice": voice, "config_sha256": sha256_file(config_path)}
    plan_path = build / "speech_plan.json"
    if plan_path.exists() and read(plan_path) != plan:
        raise ValueError("Speech inputs changed; use a fresh derivative build.")
    atomic_json(plan_path, plan)
    audio = build / "audio"
    audio.mkdir(exist_ok=True)
    raw = synthesize({"language": "fr", "voices": {
        "narrator": {"audio": voice["audio"], "reference_text": voice["reference_text"]}},
        "turns": turns}, ROOT, audio, snapshot_download(repo_id=MODEL, local_files_only=True), "cpu", 8)
    measured, cursor, aligned_turns = {}, 0, []
    for turn, recording in zip(turns, raw):
        clean = prepare_turn_audio(turn["id"], recording, audio)
        target = audio / (turn["id"] + ".wav")
        item = {**turn, **normalize(Path(clean["audio"]), target), "audio": str(target.resolve()),
                "sha256": sha256_file(target), "raw_audio": recording["audio"],
                "raw_sha256": sha256_file(Path(recording["audio"])), "processed_audio": clean["audio"],
                "processed_sha256": sha256_file(Path(clean["audio"])), "speech_tempo": 1.0}
        measured[turn["id"]] = item
        event = speech_event(turn["id"], item, cursor)
        aligned_turns.append({**item, "start": event["start"], "end": event["end"], "visible": True})
        cursor = event["end_frame"]
    atomic_json(build / "audio_manifest.json", measured)
    atomic_json(build / "timeline.json", {"language": "fr", "turns": aligned_turns})
    align_build(build)
    review(build)
    atomic_json(build / "voice_references.json", {"narrator": voice, "human_listening": False})
    print("Seven new Qwen clips synthesized, measured, force-aligned and independently transcribed.", flush=True)


def overlays(project, label, scope):
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(str(project / "assets/arialbd.ttf"), 22)
    image = Image.new("RGB", (920, 36), "#8d172c")
    draw = ImageDraw.Draw(image)
    if draw.textbbox((0, 0), label, font=font)[2] > 880:
        raise ValueError("The complete part badge does not fit.")
    draw.text((460, 18), label, anchor="mm", font=font, fill="white")
    image.save(project / "assets/part_badge.png")
    footer = Image.new("RGB", (920, 70), "#f7f4f0")
    draw = ImageDraw.Draw(footer)
    font = ImageFont.truetype(str(project / "assets/arial.ttf"), 23)
    for y, text in ((0, "Préparation indépendante · Ce n’est pas une épreuve officielle"), (32, scope)):
        if draw.textbbox((0, 0), text, font=font)[2] > 920:
            raise ValueError("The new complete footer does not fit.")
        draw.text((0, y), text, font=font, fill="#536273")
    footer.save(project / "assets/short_footer.png")


def prepare(config_path, destination):
    config, source = settings(config_path)
    verify_source(source, config["source_manifest_sha256"])
    original, content = read(source / "timeline.json"), read(source / "content.json")
    speech_build = destination / "wrappers"
    wrappers = {t["id"]: t for t in read(speech_build / "timeline.json")["turns"]}
    spoken = read(speech_build / "audio_manifest.json")
    for item in spoken.values():
        verify_files({item["audio"]: item["sha256"], item["raw_audio"]: item["raw_sha256"]})
    if sha256_file(config_path) != read(speech_build / "speech_plan.json")["config_sha256"]:
        raise ValueError("The synthesized speech belongs to a different edit configuration.")
    pins = {str(p.resolve()): sha256_file(p) for p in (
        config_path, Path(__file__), ROOT / "compose_tef.py", ROOT / "deliver_tef.py",
        ROOT / "check_tef_layout.cjs", ROOT / "composition/index.html",
        source / "delivery_manifest.json", source / "preview_portrait.mp4", source / "dialogue.wav",
        source / "timeline.json", source / "content.json", source / "audio_manifest.json")}
    pin_path = destination / "input_pin.json"
    if pin_path.exists() and read(pin_path)["files"] != pins:
        raise ValueError("Generation inputs changed; preserve this revision and choose another directory.")
    atomic_json(pin_path, {"files": pins})
    source_manifest = read(source / "audio_manifest.json")
    for part in config["parts"]:
        build = destination / f"part_{part['number']:02d}"
        if (build / "timeline.json").exists():
            validate_short(build)
            continue
        build.mkdir(exist_ok=True)
        title = {**wrappers[f"part_{part['number']:02d}"], "id": "title"}
        timeline, mapping = edit_timeline(original, part["families"], title, wrappers["cta"], config["outro_frames"])
        groups = [g for g in content["groups"] if g["family"] in part["families"]]
        numbers = [n for g in groups for r in g["recordings"] for n in r["numbers"]]
        span = f"{numbers[0]}–{numbers[-1]}"
        label = f"Partie {part['number']}/6 · Questions {span}"
        selected = {**copy.deepcopy(content), "groups": groups,
                    "cards": {str(n): content["cards"][str(n)] for n in numbers}}
        selected["episode"].update(id=f"{config['id']}_part_{part['number']:02d}", title=title["text"],
                                   cta=config["cta"], series_label=label)
        manifest = {e["audio_id"]: source_manifest[e["audio_id"]]
                    for e in timeline["events"] if e["id"] in mapping["source_event_ids"] and e.get("audio_id")}
        manifest.update(title=title, cta=wrappers["cta"])
        mapping.update(source=str(source), source_manifest_sha256=config["source_manifest_sha256"],
                       part=part, numbers=numbers, label=label,
                       source_video_sha256=sha256_file(source / "preview_portrait.mp4"))
        for name, value in (("timeline.json", timeline), ("content.json", selected),
                            ("audio_manifest.json", manifest), ("edit_decisions.json", mapping),
                            ("input_pin.json", {"files": pins})):
            atomic_json(build / name, value)
        for name in ("visual_assets.json", "voice_references.json", "chime_provenance.json"):
            shutil.copyfile(source / name, build / name)
        write_wav(build / "dialogue.wav", mix_events(timeline["events"]))
        compose(build)
        project = build / "portrait"
        overlays(project, label, f"Questions {span} · Une seule écoute · Correction après chaque exercice")
        path = project / "index.html"
        document = path.read_text(encoding="utf-8")
        document = document.replace("16 questions · Correction après chaque exercice",
                                    f"{len(numbers)} questions · Correction après chaque exercice")
        document = document.replace("16 questions · 8 types · Une seule écoute",
                                    f"Questions {span} · Une seule écoute")
        document = document.replace("<header>", '<img id="part-badge" src="assets/part_badge.png" alt="' + label
                                    + '" style="position:absolute;left:80px;top:224px;width:920px;height:36px"><header>')
        first, last = document.index("<footer>"), document.index("</footer>") + len("</footer>")
        document = (document[:first] + '<img id="short-footer" src="assets/short_footer.png" '
                    'alt="Préparation indépendante · Questions ' + span
                    + '" style="position:absolute;left:80px;top:1730px;width:920px;height:70px">' + document[last:])
        path.write_text(document, encoding="utf-8")
        receipt = read(build / "composition_receipt.json")
        receipt["layouts"]["portrait"]["html_sha256"] = sha256_file(path)
        for name in ("part_badge.png", "short_footer.png"):
            receipt["layouts"]["portrait"]["sources"][name] = {
                "path": str(project / "assets" / name), "sha256": sha256_file(project / "assets" / name)}
        receipt["derivative"] = mapping
        atomic_json(build / "composition_receipt.json", receipt)
        atomic_json(project / "assets_manifest.json", {
            p.name: sha256_file(p) for p in (project / "assets").iterdir() if p.is_file()})
        cli = os.path.relpath(ROOT / "node_modules/hyperframes/bin/hyperframes.mjs", project).replace("\\", "/")
        atomic_json(project / "package.json", {"private": True, "scripts": {
            "check": f"node {cli} check . --json --no-browser-gpu --samples 12"}})
        validate_short(build)
        print(f"{label}: {timeline['duration']:.3f}s.", flush=True)


def validate_short(build):
    verify_files(read(build / "input_pin.json")["files"])
    timeline, mapping = read(build / "timeline.json"), read(build / "edit_decisions.json")
    source = Path(mapping["source"])
    original = read(source / "timeline.json")
    if sha256_file(source / "delivery_manifest.json") != mapping["source_manifest_sha256"]:
        raise ValueError("The frozen source reference changed.")
    turns = {t["id"]: t for t in timeline["turns"]}
    expected, expected_mapping = edit_timeline(original, mapping["families"], turns["title"], turns["cta"],
                                                timeline["events"][-1]["end_frame"] - timeline["events"][-1]["start_frame"])
    if timeline != expected or any(mapping[k] != v for k, v in expected_mapping.items()):
        raise ValueError("A derivative changed source events, alignment, family boundaries or its exact clock.")
    manifest = read(build / "audio_manifest.json")
    cursor = 0
    with wave.open(str(build / "dialogue.wav")) as audio:
        if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth(), audio.getnframes()) != (
                RATE, 1, 2, timeline["total_frames"] * FRAME_SAMPLES):
            raise ValueError("Lossless audio differs from the derivative frame clock.")
        for event in timeline["events"]:
            if event["start_frame"] != cursor:
                raise ValueError("The derivative has a gap or overlap.")
            actual = audio.readframes((event["end_frame"] - cursor) * FRAME_SAMPLES)
            if event["kind"] == "silence":
                if any(actual):
                    raise ValueError("A protected silent window is not digital zero.")
            else:
                item = manifest[event["audio_id"]]
                verify_files({item["audio"]: item["sha256"]})
                with wave.open(item["audio"]) as clip:
                    pcm = clip.readframes(clip.getnframes())
                if len(pcm) > len(actual) or actual != pcm + bytes(len(actual) - len(pcm)):
                    raise ValueError("Speech/chime samples were changed, clipped or overlapped.")
            cursor = event["end_frame"]
        audio.setpos(mapping["output_start_frame"] * FRAME_SAMPLES)
        body_pcm = audio.readframes((mapping["output_end_frame"] - mapping["output_start_frame"]) * FRAME_SAMPLES)
    with wave.open(str(source / "dialogue.wav")) as audio:
        audio.setpos(mapping["source_start_frame"] * FRAME_SAMPLES)
        if body_pcm != audio.readframes(len(body_pcm) // 2):
            raise ValueError("The whole exercise block is not byte-identical to frozen source PCM.")
    report = {"frames": cursor, "fps": FPS, "duration": cursor / FPS, "duration_limit_seconds": 180,
              "question_count": len(mapping["numbers"]), "source_pcm_byte_identical": True,
              "all_mix_events_exact": True, "lossless_silences_digital_zero": True,
              "timeline_sha256": sha256_file(build / "timeline.json"),
              "dialogue_sha256": sha256_file(build / "dialogue.wav")}
    atomic_json(build / "source_validation.json", report)
    return report


def export(build):
    validate_short(build)
    receipt = read(build / "checks_portrait.json")
    verify_files({str(build / "portrait/index.html"): receipt["html_sha256"],
                  str(build / "composition_receipt.json"): receipt["composition_sha256"]})
    for name, info in read(build / "composition_receipt.json")["layouts"]["portrait"]["sources"].items():
        verify_files({str(build / "portrait/assets" / name): info["sha256"]})
    if not read(build / "visual_review.json").get("portrait", {}).get("contact_sheets_inspected"):
        raise ValueError("Inspect native frames before exporting the Reel.")
    timeline, mapping = read(build / "timeline.json"), read(build / "edit_decisions.json")
    title_end = mapping["output_start_frame"]
    cta_start = mapping["output_end_frame"]
    for name, first, last in (("opening", 0, title_end), ("closing", cta_start, timeline["total_frames"])):
        target = build / (name + ".mp4")
        if not target.exists():
            run([sys.executable, "-X", "utf8", ROOT / "hyperframes_local.py", "render", build / "portrait",
                 "--fps", "24", "--quality", "delivery", "--workers", "2", "--no-browser-gpu",
                 "--start", str(first / FPS), "--end", str(last / FPS), "--output", target],
                build / (name + "_render.log"))
        probe = json.loads(subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams", "-of", "json", str(target)],
            text=True))["streams"][0]
        if (int(probe["nb_frames"]) != last - first
                or (probe["width"], probe["height"], probe["r_frame_rate"]) != (1080, 1920, "24/1")):
            raise ValueError(f"The native {name} render lost frames or changed its resolution.")
    body = build / "exercise_video.mp4"
    if not body.exists():
        seek = mapping["source_start_frame"] // FPS
        first, last = mapping["source_start_frame"] - seek * FPS, mapping["source_end_frame"] - seek * FPS
        run(["ffmpeg", "-nostdin", "-v", "error", "-threads", "2", "-ss", str(seek),
             "-i", Path(mapping["source"]) / "preview_portrait.mp4",
             "-i", build / "portrait/assets/part_badge.png",
             "-i", build / "portrait/assets/short_footer.png",
             "-filter_complex", "[1:v]scale=out_color_matrix=bt709,format=yuva420p[badge];"
             "[2:v]scale=out_color_matrix=bt709,format=yuva420p[footer];"
             f"[0:v]trim=start_frame={first}:end_frame={last},setpts=PTS-STARTPTS[v];"
             "[v][badge]overlay=80:224:format=yuv420[b];"
             "[b][footer]overlay=80:1730:format=yuv420[out]",
             "-map", "[out]", "-an", "-c:v", "libx264", "-threads", "2",
             "-preset", "fast", "-crf", "16", "-r", "24", "-colorspace", "bt709",
             "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
             "-movflags", "+faststart", body],
            build / "exercise_video.log")
    final = build / "preview_portrait.mp4"
    if final.exists():
        raise ValueError("Preserve the existing final export; do not overwrite it.")
    run(["ffmpeg", "-nostdin", "-v", "error", "-i", build / "opening.mp4", "-i", body,
         "-i", build / "closing.mp4", "-i", build / "dialogue.wav",
         "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0,format=yuv420p[v]",
         "-map", "[v]", "-map", "3:a:0", "-c:v", "libx264", "-threads", "2", "-preset", "fast",
         "-crf", "16", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
         "-color_range", "tv", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "1",
         "-t", str(timeline["duration"]), "-movflags", "+faststart", final], build / "mux_portrait.log")


def sheets(destination, mode):
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    for build in sorted(destination.glob("part_??")):
        font = ImageFont.truetype(str(build / "portrait/assets/arial.ttf"), 17)
        records = (read(build / "native_captures_portrait.json") if mode == "native"
                   else read(build / "encoded_checks_portrait.json")["comparisons"])
        key = "native_file" if mode == "native" else "encoded_file"
        for first in range(0, len(records), 18):
            page = records[first:first + 18]
            canvas = Image.new("RGB", (1200, 3 * 745), "white")
            draw = ImageDraw.Draw(canvas)
            for n, record in enumerate(page):
                x, y = (n % 6) * 200, (n // 6) * 745
                with Image.open(record[key]) as image:
                    thumb = ImageOps.contain(image.convert("RGB"), (200, 700))
                    canvas.paste(thumb, (x, y + 38))
                draw.text((x + 3, y + 3), str(record["event"])[:22], font=font, fill="black")
                draw.text((x + 3, y + 21), f'{record["time"]:.3f}s', font=font, fill="black")
            path = build / f"review_{mode}_{first // 18 + 1:02d}.jpg"
            canvas.save(path, quality=90)
            print(path, flush=True)


def posts(config_path, destination):
    import textwrap
    from PIL import Image, ImageDraw, ImageFont
    config, _ = settings(config_path)
    for build in sorted(destination.glob("part_??")):
        mapping, timeline = read(build / "edit_decisions.json"), read(build / "timeline.json")
        content = read(build / "content.json")
        target = ROOT.parent / "posts" / config["id"] / build.name
        if target.exists():
            raise ValueError("Preserve existing post drafts/covers; choose a fresh revision.")
        target.mkdir(parents=True)
        part = mapping["part"]
        span = f'{mapping["numbers"][0]} à {mapping["numbers"][-1]}'
        topics = "\n".join(f'Question {n} : {content["cards"][str(n)]["question"]}' for n in mapping["numbers"])
        text = (
            f'TEF Canada · Partie {part["number"]}/6 — {part["label"]}\n'
            f'Questions vidéo {span} · {timeline["duration"]:.3f} secondes.\n\n{topics}\n\n'
            "Lisez pendant la pause, écoutez une seule fois, puis répondez pendant tout le silence prévu. "
            "La correction apparaît après chaque exercice : carillon, puis explication parlée. "
            "Les deux réponses des audios partagés apparaissent ensemble après leur pause commune. "
            "Consignes complètes et silences des exemples publiés conservés ; aucune musique ajoutée.\n\n"
            "Les numéros vidéo restent ceux de la série 1–16. Les audios annoncent les numéros du livre, "
            "également affichés à l’écran. Retrouvez les six parties dans l’ordre ; chaque partie est autonome. "
            "Pratique guidée réduite, pas l’examen officiel complet.\n\n"
            "Notre livre « TEF Canada : Compréhension orale », French Compass : 380 exercices, audio, "
            "transcriptions et explications.\nAmazon : https://a.co/d/013rkncS\n\n"
            "Publicité pour notre livre. Voix générées par synthèse vocale (IA). Préparation indépendante, "
            "non affiliée à l’organisateur du TEF.\n"
            "Crédits : contenu, couverture et illustrations du livre fourni"
            + (" (planches finales P19/P21)" if part["number"] == 1 else "")
            + " ; logo French Compass fourni et autorisé ; drapeau canadien du domaine public ; DejaVu Sans. "
            "Carillon Mixkit « Software interface remove », Sound Effects Free License, "
            "https://mixkit.co/license/ ; volume réduit, vitesse originale, sans réverbération ajoutée.\n\n"
            "#TEFCanada #ComprehensionOrale #FrancaisAuCanada #FrenchCompass\n")
        for name in ("instagram.txt", "tiktok.txt"):
            (target / name).write_text(text, encoding="utf-8")
        frame = next(c for c in read(build / "native_captures_portrait.json") if c["event"] == "title")
        with Image.open(frame["native_file"]) as source_image:
            image = source_image.convert("RGB")
        draw = ImageDraw.Draw(image)
        draw.rectangle((105, 300, 975, 1350), fill="white")
        font_path = str(build / "portrait/assets/arialbd.ttf")

        def line(text, y, size, fill="#253342"):
            font = ImageFont.truetype(font_path, size)
            if draw.textbbox((0, 0), text, font=font)[2] > 850:
                raise ValueError("Cover text exceeds its safe width.")
            draw.text((540, y), text, font=font, fill=fill, anchor="mt")

        line("TEF Canada", 470, 76)
        line("Compréhension", 585, 60)
        line("orale", 665, 60)
        draw.rounded_rectangle((190, 790, 890, 925), radius=22, fill="#8d172c")
        line(f'Partie {part["number"]}/6', 805, 80, "white")
        for n, label in enumerate(textwrap.wrap(part["label"], width=26)):
            line(label, 980 + n * 68, 46)
        line(f"Questions {span}", 1150, 42)
        image.save(target / "thumbnail_instagram.jpg", quality=94)
        shutil.copyfile(target / "thumbnail_instagram.jpg", target / "thumbnail_tiktok.jpg")
        atomic_json(target / "thumbnail_provenance.json", {
            "source_native_file": frame["native_file"], "source_native_sha256": frame["native_sha256"],
            "book": read(build / "visual_assets.json")["book_image"],
            "title": f'TEF Canada · Compréhension orale · Partie {part["number"]}/6',
            "content_label": part["label"], "essential_title_bounds": [105, 460, 975, 1240],
            "thumbnail_sha256": sha256_file(target / "thumbnail_instagram.jpg")})


def freeze(config_path, destination):
    config, source = settings(config_path)
    verify_source(source, config["source_manifest_sha256"])
    exports = []
    for build in sorted(destination.glob("part_??")):
        report = validate_short(build)
        checks = read(build / "encoded_checks_portrait.json")
        verify_files({checks["video"]: checks["video_sha256"]})
        if not read(build / "visual_review.json").get("portrait", {}).get("encoded_contact_sheets_inspected"):
            raise ValueError("Inspect encoded exercise edits, openings, badges and CTAs before freezing.")
        posts = ROOT.parent / "posts" / config["id"] / build.name
        for name in ("instagram.txt", "tiktok.txt", "thumbnail_instagram.jpg", "thumbnail_tiktok.jpg",
                     "thumbnail_provenance.json"):
            target = build / "post_drafts" / name
            target.parent.mkdir(exist_ok=True)
            shutil.copyfile(posts / name, target)
        exports.append({"part": build.name, "video": str((build / "preview_portrait.mp4").relative_to(destination)),
                        "duration": report["duration"], "sha256": checks["video_sha256"]})
    if len(exports) != 6:
        raise ValueError("All six independent Reels are required.")
    archive = destination / "generation_sources"
    archive.mkdir(exist_ok=True)
    for path in (Path(__file__), ROOT / "test_tef_social.py", ROOT / "compose_tef.py", ROOT / "deliver_tef.py",
                 ROOT / "prepare_tef.py", ROOT / "check_tef_layout.cjs", ROOT / "hyperframes_local.py",
                 ROOT / "composition/index.html", config_path, ROOT / "package.json", ROOT / "package-lock.json"):
        shutil.copyfile(path, archive / path.name)
    shutil.copyfile(source / "delivery_manifest.json", destination / "source_delivery_manifest.json")
    shutil.copyfile(source / "speech_review_small.json", destination / "source_speech_review_small.json")
    files = {str(p.relative_to(destination)): sha256_file(p) for p in destination.rglob("*")
             if p.is_file() and p.name != "delivery_manifest.json" and p.suffix != ".log"
             and ".hyperframes" not in p.parts}
    path = destination / "delivery_manifest.json"
    if path.exists():
        raise ValueError("A frozen delivery already exists.")
    atomic_json(path, {"scope": "Six portrait TEF guided-practice Reels, each strictly below 180 seconds",
                       "source": str(source), "source_manifest_sha256": config["source_manifest_sha256"],
                       "exports": exports, "files": files, "human_listening": False, "publication": False})
    verify_files({str(destination / p): h for p, h in files.items()})
    print(f"Frozen and verified {len(files)} files across six portrait Reels.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("speech", "prepare", "check", "export", "encoded", "sheets", "posts", "freeze"))
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--part", type=int, choices=range(1, 7))
    parser.add_argument("--mode", choices=("native", "encoded"), default="native")
    args = parser.parse_args()
    destination = args.build.resolve()
    if args.command in ("speech", "prepare", "posts", "freeze"):
        if (source := settings(args.config)[1]) == destination or source in destination.parents:
            raise ValueError("Keep the full frozen source separate from derivative output.")
        globals()[args.command](args.config.resolve(), destination)
    elif args.command == "sheets":
        sheets(destination, args.mode)
    else:
        builds = [destination / f"part_{args.part:02d}"] if args.part else sorted(destination.glob("part_??"))
        if not builds:
            raise ValueError("Prepare all six parts first.")
        for build in builds:
            if args.command == "check":
                check(build, "portrait", validator=validate_short)
            elif args.command == "encoded":
                encoded(build, "portrait", validator=validate_short)
            else:
                export(build)
