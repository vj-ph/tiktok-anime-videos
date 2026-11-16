"""Full-length fide preview using the established Blender individual-exam scene."""

from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageOps

from build_paths import build_directory
from episode_config import check_timeline
from fide_content import export_text, load_episode
from generation_runtime import (forget_process, generation_job, run_process, stage_completed,
                                start_process, stop_processes)
from long_speaking import ACCENT, BG, FORMATS, INK, MUTED, PANEL, text_box
from long_speaking_preview import (SOURCES as SHARED_SOURCES, caption_preflight, display_state,
                                   is_production, native_sample, output_name, output_sizes, review_export)
from prepare_audio import atomic_json, atomic_text, sha256_file
from runtime_config import check_render_device, font_path, tool_path

ROOT = Path(__file__).resolve().parent
SOURCES = (*SHARED_SOURCES, "a2_speaking_contacts.py", "a2_speaking_preview_scene.py",
           "fide_content.py", "fide_speaking.py", "swiss_flags.py",
           "a2_speaking_production.py", "fide_speaking_production.py")
STATIC = {"a2_picture", "b1_choice", "cta"}
CREDITS = """Snow Rig and Rain Rig: Blender Foundation, CC BY 4.0.
https://studio.blender.org/characters/snow/v4/
https://studio.blender.org/characters/rain/v3/
https://creativecommons.org/licenses/by/4.0/
Modified outfits, scale, poses, visibility, animation and seat placement.
Doctor picture and covers: user-supplied Deutsch Kompass fide A2/B1 books.
Speech: locally synthesized from the user-supplied Swiss voice references.
Pointing emoji: Twemoji, Twitter and contributors, CC BY 4.0; scaled.
Independent practice simulation; not issued or endorsed by fide.
Swiss flag artwork: Wikimedia Commons, public domain; Marc Mongenet and contributors.
https://commons.wikimedia.org/wiki/File:Flag_of_Switzerland.svg
Flag mesh: Quaternius, CC0; square cloth, Swiss texture, metal pole and desk stand adaptation.
https://poly.pizza/m/FuOkF3WBrx
"""


@lru_cache(maxsize=24)
def fitted(path, size):
    with Image.open(path) as source:
        return ImageOps.contain(source.convert("RGBA"), size, Image.Resampling.LANCZOS)


def paste(image, path, box):
    source = fitted(str(path), (box[2] - box[0], box[3] - box[1]))
    x, y = box[0] + (box[2] - box[0] - source.width) // 2, box[1] + (box[3] - box[1] - source.height) // 2
    image.paste(source, (x, y), source)
    return [x, y, x + source.width, y + source.height]


def overlay(episode, storyboard, timeline, mode, frame):
    turn, first, last, active = display_state(episode, timeline, frame)
    return compose_turn(episode, turn, mode, first, last, active, frame)


def compose_turn(episode, turn, mode, first=0, last=12, active=None, frame=None):
    portrait = mode == "social"
    layout = FORMATS[mode]
    image = Image.new("RGB", layout["size"], BG)
    draw = ImageDraw.Draw(image)
    texts = []

    def text(value, box, **options):
        result = text_box(draw, value, box, **options)
        if "highlighted_word" in result:
            result["highlight_kind"] = "forced_alignment"
        texts.append(result)

    text("DEUTSCH KOMPASS · fide A2-B1" + (" · VORSCHAU" if not portrait and not is_production(episode) else ""),
         (72, 175, 908, 222) if portrait else (64, 40, 1856, 90),
         size=30 if portrait else 35, bold=True, color=ACCENT)
    text(turn["heading"], (72, 238, 908, 348) if portrait else (64, 105, 1856, 183),
         size=43 if portrait else 49, minimum=30, bold=True,
         highlight_word=active if turn["kind"] == "opening" else None)
    cue = "Amazon: Link in der Bio" if portrait else "Amazon: Link in der Beschreibung"
    check = {"id": turn["panel_id"], "format": mode, "frame": frame, "turn_id": turn["id"],
             "size": list(image.size), "page": [first, last], "active_word": active, "text": texts}
    if turn["kind"] == "cta":
        covers = ((130, 390, 430, 840), (550, 390, 850, 840)) if portrait else (
            (150, 300, 450, 750), (480, 300, 780, 750))
        for key, box in zip(("a2", "b1"), covers):
            paste(image, episode["promotion"][key]["cover"], box)
        text("Mehr Aufgaben und Modelldialoge in unseren fide-Büchern für A2 und B1: Sprechen + Schreiben.",
             (90, 900, 900, 1160) if portrait else (850, 330, 1780, 620),
             size=45 if portrait else 49, minimum=35, bold=True)
        text(cue, (90, 1210, 900, 1330) if portrait else (850, 700, 1780, 850),
             size=42 if portrait else 47, color=ACCENT, bold=True)
        caption_box = (90, 1450, 900, 1650) if portrait else (64, 900, 1856, 1030)
        text(" ".join(turn["display_text"].split()[first:last]), caption_box,
             size=37 if portrait else 35, minimum=28, highlight_word=active)
        check.update(cover_count=2, promo_group=False, cta_box=list(caption_box))
        return image, check
    scene_box = layout["scene"]
    draw.rounded_rectangle(scene_box, radius=18, fill=PANEL)
    draw.rounded_rectangle(layout["promo"], radius=22, fill=PANEL)
    book = episode["promotion"]["b1" if turn["section"].startswith("b1") or turn["section"] == "closing" else "a2"]
    paste(image, book["cover"], layout["cover"])
    if portrait:
        text(book["title"], (260, 1320, 875, 1372), size=33, bold=True)
        text(cue, layout["cta"], size=36, minimum=27, color=ACCENT, bold=True)
    else:
        text("Mehr üben mit dem Buch", (1420, 315, 1810, 358), size=27, color=MUTED)
        paste(image, episode["promotion"]["pointing_emoji"], (1420, 715, 1456, 751))
        text(cue, (1468, 705, 1810, 774), size=28, minimum=26, color=ACCENT, bold=True)
    navigation = (72, 1240, 908, 1275) if portrait else (1410, 820, 1840, 930)
    text("A2 · Bild / Telefon / Gespräch   →   B1" if portrait else
         "A2: Bild · Telefon · Gespräch\nB1: Themenwahl und Gespräch",
         navigation, size=23 if portrait else 25, minimum=20, color=ACCENT)
    if turn["section"] == "a2_picture":
        check["picture_box"] = paste(image, episode["picture"], scene_box)
    elif turn["section"] == "b1_choice":
        x0, y0, x1, y1 = scene_box
        boxes = ((x0 + 28, y0 + 45, x1 - 28, y0 + 210),
                 (x0 + 28, y0 + 255, x1 - 28, y1 - 30)) if portrait else (
                     (x0 + 35, y0 + 90, x0 + 580, y1 - 90),
                     (x0 + 640, y0 + 90, x1 - 35, y1 - 90))
        for title, box in zip(("Wohnen und\nNachbarschaft", "Arbeit und\nArbeitssuche"), boxes):
            draw.rounded_rectangle(box, radius=18, outline=ACCENT, width=3)
            text(title, (box[0] + 25, box[1] + 30, box[2] - 25, box[3] - 20),
                 size=40, minimum=28, bold=True)
    if turn["kind"] != "opening":
        text(("Lea · " if turn["speaker"] == "candidate_a" else "Prüfer · ") +
             ("Modellantwort" if turn["speaker"] == "candidate_a" else "Gespräch"),
             (90, 900, 890, 946) if portrait else (64, 810, 1280, 853),
             size=25, color=MUTED)
        text(" ".join(turn["display_text"].split()[first:last]),
             (90, 958, 890, 1218) if portrait else (64, 865, 1280, 1030),
             size=38 if portrait else 35, minimum=28, highlight_word=active)
    else:
        text("Mit Lea · A2 Gesundheit · B1 Wohnen",
             layout["content"], size=36, minimum=28, color=MUTED)
    check.update(persistent_cover=list(layout["cover"]), persistent_cta=cue,
                 cover_count=1, book_url=book["url"], scene_box=list(scene_box), promo_group=True)
    return image, check


def native_plan(episode, timeline):
    result = []
    box = FORMATS["youtube"]["scene"]
    size = [round((box[i + 2] - box[i]) * episode["render"]["native_scale"]) for i in (0, 1)]
    for index, turn in enumerate(timeline["turns"]):
        if turn["panel_id"] in STATIC:
            continue
        stop = timeline["turns"][index + 1]["start_frame"] if index + 1 < len(timeline["turns"]) else timeline["total_frames"]
        result.extend({"format": "youtube", "frame": frame, "camera": turn["camera"], "size": size,
                       "file": f"native/youtube_{frame:05d}.png"}
                      for frame in range(turn["start_frame"], stop, episode["render"]["motion_step"]))
    return result


@generation_job
def build_contacts(path, output):
    episode, pins = load_episode(path)
    build = build_directory(output)
    if build.exists():
        raise ValueError("Use a fresh fide contact-sheet directory.")
    (build / "native").mkdir(parents=True)
    (build / "panels").mkdir()
    request = {"build": str(build), "visual": episode}
    atomic_json(build / "request.json", request)
    from pipeline import run_command
    run_command([tool_path("blender"), "-b", episode["scene"]["base_scene"], "--disable-autoexec",
                 "-t", "4", "--python-exit-code", "1", "--python", ROOT / "a2_speaking_contacts.py",
                 "--", "--native", build / "request.json"], build / "native.log")
    selected = []
    for section in dict.fromkeys(t["section"] for t in episode["turns"]):
        matching = [t for t in episode["turns"] if t["section"] == section]
        selected.append(next((t for t in matching if t["speaker"] == "candidate_a"), matching[0])
                        if section not in ("opening", "a2_phone", "b1_choice", "routing", "cta") else matching[0])
    checks = []
    for mode in output_sizes(episode):
        thumb = (480, 270) if mode == "youtube" else (270, 480)
        columns = 3
        sheet = Image.new("RGB", (thumb[0] * columns, thumb[1] * math.ceil(len(selected) / columns)), BG)
        for index, turn in enumerate(selected):
            image, check = compose_turn(episode, turn, mode, last=len(turn["display_text"].split())
                                       if turn["kind"] == "opening" else 12)
            if turn["panel_id"] not in STATIC:
                box = FORMATS[mode]["scene"]
                with Image.open(build / "native" / f"youtube_{turn['camera']}.png") as source:
                    image.paste(ImageOps.fit(source.convert("RGB"), (box[2] - box[0], box[3] - box[1]),
                                             Image.Resampling.LANCZOS, centering=(.5, .5)), box[:2])
            target = build / "panels" / f"{mode}_{turn['section']}.png"
            image.save(target)
            checks.append({**check, "file": str(target), "sha256": sha256_file(target),
                           "highlight_timing": "None: still-only layout review."})
            sheet.paste(image.resize(thumb), ((index % columns) * thumb[0], (index // columns) * thumb[1]))
        sheet.save(build / f"contact_{mode}.jpg", quality=94)
    if any(sha256_file(Path(p)) != h for p, h in pins.items()):
        raise ValueError("Fide contact input changed during rendering.")
    atomic_json(build / "contact_checks.json", {"panels": checks, "source_sha256": pins,
                                               "speech_generated": False})
    atomic_text(build / "CREDITS.txt", CREDITS)
    return build


def encode(build, episode, timeline, mode):
    size = output_sizes(episode)[mode]
    command = [shutil.which("ffmpeg"), "-nostdin", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{size[0]}x{size[1]}", "-r", "24", "-i", "pipe:0", "-i", str(build / "dialogue.wav"),
               "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-threads", "4", "-preset", "veryfast",
               "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
               "-t", str(timeline["total_frames"] / 24), "-movflags", "+faststart",
               str(build / output_name(episode, mode))]
    key = previous = None
    with (build / f"encode_{mode}.log").open("w") as log:
        process = start_process(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
        try:
            for frame in range(timeline["total_frames"]):
                turn, first, last, active = display_state(episode, timeline, frame)
                state = turn["id"], first, last, active
                if state != key:
                    cached, _ = overlay(episode, episode, timeline, mode, frame)
                    key = state
                image = cached.copy()
                if turn["panel_id"] not in STATIC:
                    sample = native_sample(turn, frame, episode["render"]["motion_step"])
                    if sample != previous:
                        with Image.open(build / "native" / f"youtube_{sample:05d}.png") as source:
                            box = FORMATS[mode]["scene"]
                            native = ImageOps.fit(source.convert("RGB"), (box[2] - box[0], box[3] - box[1]),
                                                  Image.Resampling.LANCZOS, centering=(.5, .5))
                        previous = sample
                    image.paste(native, FORMATS[mode]["scene"][:2])
                process.stdin.write(image.resize(size, Image.Resampling.LANCZOS).tobytes())
            process.stdin.close()
            if process.wait():
                raise RuntimeError(f"Encoding failed; see {log.name}.")
        except BaseException:
            stop_processes([process])
            raise
        finally:
            forget_process(process)


@generation_job
def build_preview(path, output, jobs=2, until="export", speech_cache_from=None, *,
                  profile="preview", reuse_audio=None, render_device="CPU"):
    from check_speech import check_speech
    from pipeline import run_command

    episode, assets = load_episode(path, profile)
    production = is_production(episode)
    reuse = None
    if production:
        from fide_speaking_production import (
            prepare_production_audio, production_inputs, production_reuse_spec)
        if speech_cache_from:
            raise ValueError("Fide production reuses exact audio, not raw speech caches.")
        reuse = production_reuse_spec(episode, reuse_audio)
        if render_device != "CPU":
            check_render_device(render_device)
        episode["render_device"] = render_device
        assets.update({str(p): sha256_file(p) for p in production_inputs(reuse)})
    elif reuse_audio or render_device != "CPU":
        raise ValueError("Fide previews remain CPU-only without exact audio reuse.")
    build = build_directory(output)
    if reuse:
        source = Path(reuse["source"])
        if build == source or build.is_relative_to(source) or source.is_relative_to(build):
            raise ValueError("Fide production must be separate from its approved preview.")
    assets.update({str(font_path()): sha256_file(font_path()), str(font_path(True)): sha256_file(font_path(True))})
    spec = {"episode": episode, "code_sha256": {name: sha256_file(ROOT / name) for name in SOURCES},
            "asset_sha256": assets}
    if reuse:
        spec["audio_reuse"] = reuse
    state_path = build / ("production_state.json" if production else "preview_state.json")
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state["spec"] != spec:
            raise ValueError("Fide preview inputs changed; use a fresh build.")
    else:
        if build.exists() and any(build.iterdir()):
            raise ValueError("Use a fresh dedicated fide build.")
        build.mkdir(parents=True, exist_ok=True)
        state = {"spec": spec, "stages": {}}
        atomic_json(state_path, state)
        atomic_json(build / "episode.json", episode)
        atomic_json(build / "storyboard_episode.json", episode)
        export_text(episode, build)
        atomic_text(build / "CREDITS.txt", CREDITS)
    snapshot = build / "source_export"
    snapshot.mkdir(exist_ok=True)
    for name, digest in spec["code_sha256"].items():
        target = snapshot / name
        if target.exists() and sha256_file(target) != digest:
            raise ValueError("Fide generation snapshot changed.")
        if not target.exists():
            shutil.copy2(ROOT / name, target)

    order = ("audio_reuse", "audio", "alignment", "speech_check", "scene", "frames",
             "encode_youtube", "encode_social")

    def stage(name, action, outputs):
        previous = state["stages"].get(name, {})
        if previous and all((build / n).is_file() and sha256_file(build / n) == h for n, h in previous.items()):
            print(f"{name}: verified checkpoint", flush=True)
            return
        for dependent in order[order.index(name):]:
            state["stages"].pop(dependent, None)
        atomic_json(state_path, state)
        print(f"{name}: running", flush=True)
        action()
        state["stages"][name] = {str(n): sha256_file(build / n) for n in outputs}
        atomic_json(state_path, state)
        stage_completed(name, force=True)

    if production:
        stage("audio_reuse", lambda: prepare_production_audio(build, reuse),
              ["dialogue.wav", "timeline.json", "audio_timeline.json", "word_alignment.json",
               "subtitles.srt", "speech_asr_check.json", "audio_reuse.json", "auditory_review_flags.json"])
    else:
        audio_command = [sys.executable, ROOT / "prepare_audio.py", "--episode", build / "episode.json",
                         "--output-dir", build, "--threads", "8", "--device", "cpu"]
        if speech_cache_from:
            audio_command += ["--speech-cache-from", build_directory(speech_cache_from)]
        stage("audio", lambda: run_command(audio_command, build / "audio.log"),
              ["episode.json", "dialogue.wav", "audio_timeline.json", "subtitles.srt"])
        stage("alignment", lambda: run_command(
            [sys.executable, ROOT / "align_words.py", "--build", build], build / "alignment.log"),
            ["timeline.json", "word_alignment.json"])
    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    check_timeline(episode, timeline)
    caption_preflight(build, episode, episode, timeline, overlay_fn=overlay)
    if not production:
        stage("speech_check", lambda: check_speech(build), ["speech_asr_check.json"])
    speech = json.loads((build / "speech_asr_check.json").read_text(encoding="utf-8"))
    recognized = {turn["id"]: turn for turn in speech["turns"]}
    audio_pins = {}
    for turn in timeline["turns"]:
        raw, prepared = Path(turn["raw_audio"]), Path(turn["audio"])
        if (sha256_file(raw) != turn["preprocessing"]["raw_sha256"]
                or sha256_file(prepared) != recognized[turn["id"]]["audio_sha256"]):
            raise ValueError(f"Speech chain changed after preparation/ASR: {turn['id']}")
        audio_pins.update({str(p): sha256_file(p) for p in
                           (raw, raw.with_suffix(".cache.json"), prepared, prepared.with_suffix(".cache.json"))})
        if tempo := turn.get("tempo_processing"):
            original = Path(tempo["input_audio"])
            if sha256_file(original) != tempo["input_sha256"]:
                raise ValueError(f"Pre-tempo speech changed: {turn['id']}")
            audio_pins.update({str(p): sha256_file(p) for p in
                               (original, original.with_suffix(".cache.json"))})
    chain_path = build / "speech_chain_hashes.json"
    if chain_path.exists() and json.loads(chain_path.read_text(encoding="utf-8")) != audio_pins:
        raise ValueError("Frozen fide speech chain changed; use a fresh build.")
    atomic_json(chain_path, audio_pins)
    plan = native_plan(episode, timeline)
    atomic_json(build / "native_plan.json", plan)
    if until == "audio":
        return build
    blender = tool_path("blender")
    scene_script = ROOT / "a2_speaking_preview_scene.py"
    stage("scene", lambda: run_command(
        [blender, "-b", episode["scene"]["base_scene"], "--disable-autoexec", "-t", "4",
         "--python-exit-code", "1", "--python", scene_script, "--", "--build", build, "--bake"],
        build / "scene.log"), ["preview.blend", "scene_checks.json"])
    if until == "scene":
        return build

    def frames():
        def worker(index):
            run_command([blender, "-b", build / "preview.blend", "--disable-autoexec", "-t", "4",
                         "--python-exit-code", "1", "--python", scene_script, "--", "--build", build,
                         "--worker", str(index), "--jobs", str(jobs)], build / f"frames_{index}.log")
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            list(pool.map(worker, range(jobs)))
        records = [r for i in range(jobs) for r in json.loads(
            (build / f"native_checks_{i}.json").read_text(encoding="utf-8"))]
        if (len(records) != len(plan) or {r["file"] for r in records} != {p["file"] for p in plan}
                or any(sha256_file(build / r["file"]) != r["sha256"] for r in records)):
            raise ValueError("Fide native frame receipts are incomplete.")
        atomic_json(build / "native_checks.json", records)

    stage("frames", frames, ["native_checks.json", *[p["file"] for p in plan]])

    def verify_inputs():
        for name, digest in spec["code_sha256"].items():
            if sha256_file(ROOT / name) != digest:
                raise ValueError(f"Generation source changed: {name}")
        for name, digest in spec["asset_sha256"].items():
            if sha256_file(Path(name)) != digest:
                raise ValueError(f"Source asset changed: {name}")
        for name, digest in audio_pins.items():
            if sha256_file(Path(name)) != digest:
                raise ValueError(f"Prepared speech changed during generation: {name}")

    verify_inputs()
    reports = {}
    for mode in output_sizes(episode):
        stage("encode_" + mode, lambda: encode(build, episode, timeline, mode), [output_name(episode, mode)])
        reports[mode] = review_export(build, episode, episode, timeline, mode, overlay_fn=overlay)
    verify_inputs()
    speech = json.loads((build / "speech_asr_check.json").read_text(encoding="utf-8"))
    atomic_json(build / "delivery_checks.json", {
        "status": "production_verified" if production else "full_length_preview_only",
        "exports": reports, "render": episode["render"],
        "voice_cast": episode["voices"], "source_sha256": spec,
        "source_model_segments_preserved": sum("source_segment" in t for t in episode["turns"]),
        "speech_asr_all_match": speech["all_match"],
        "human_listening_performed": False,
        "preview_approval": episode.get("preview_approval"),
        "limitations": ("Full-resolution exact-audio production; inherited ASR flags remain. No publication approval."
                        if production else "Reduced-quality Blender preview. ASR is not human listening or accent certification. "
                        "No production/publication approval; social excerpts deferred."),
    })
    files = [p for p in build.rglob("*") if p.is_file() and
             (p.parent == build or p.is_relative_to(snapshot) or p.parent.name.startswith("review_"))]
    atomic_json(build / "export_manifest.json", {
        "files_sha256": {str(p.relative_to(build)): sha256_file(p) for p in files
                         if p.name != "export_manifest.json"},
        "generation_source_sha256": spec["code_sha256"],
    })
    print(f"Full fide Blender {'production' if production else 'preview'} ready: {build}", flush=True)
    return build
