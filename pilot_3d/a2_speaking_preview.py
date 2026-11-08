"""Authorized full A2 individual-exam preview, separate from B1/B2 content."""

import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import shutil
import sys

from PIL import Image, ImageDraw

from a2_speaking_contacts import compose_panel, read_turns
from align_words import validate_words
from build_paths import build_directory
from episode_config import check_timeline, read_episode
from generation_runtime import generation_job, stage_completed
from long_speaking import FORMATS, PANEL, text_box
from long_speaking_preview import (
    SOURCES as SHARED_SOURCES, caption_preflight, display_state, encode, output_name,
    output_sizes, review_export, is_production,
)
from prepare_audio import atomic_json, inspect_wav, sha256_file, validate_episode
from runtime_config import check_render_device, font_path, tool_path

ROOT = Path(__file__).resolve().parent
SOURCES = (*SHARED_SOURCES, "a2_speaking_contacts.py", "a2_speaking_preview.py",
           "a2_speaking_preview_scene.py", "a2_speaking_production.py")
STATIC_PANELS = {"contact_card", "picture_choice", "05_teil2_picture",
                 "role_card", "personal_card", "12_final_cta"}


def pronunciation(display):
    replacements = {"ÖIF": "Ö I F", "A2": "A zwei", "ÖIF-A2-Buch": "Ö I F A zwei Buch",
                    "15": "fünfzehn", "9": "neun", "E-Card": "E Card", "+": "und"}
    spoken, groups = [], []
    for token in display.split():
        word, punctuation = re.fullmatch(r"(.+?)([.,!?;:]?)", token).groups()
        phrase = replacements.get(word, word)
        if any(char.isdigit() for char in phrase):
            raise ValueError(f"Unmapped A2 spoken number: {token}")
        words = (phrase + punctuation).split()
        groups.append(list(range(len(spoken), len(spoken) + len(words))))
        spoken.extend(words)
    return " ".join(spoken), groups


def compile_turns(review):
    turns = []
    for number, source in review.items():
        role = "candidate_a" if source["label"].startswith("Lea") else "examiner"
        part = 0 if number < 6 or number == 55 else 1 if number < 24 else 2 if number < 40 else 3
        panel = ("01_opening" if number == 1 else "12_final_cta" if number == 55 else
                 "introduction" if number < 6 else "contact_card" if number == 6 else
                 "contact_model" if number < 24 else "picture_choice" if number == 24 else
                 "05_teil2_picture" if number in (25, 26) else
                 "picture_description" if number == 27 else "role_card" if number == 28 else
                 "role_question_01" if number < 40 else "personal_card" if number == 40 else
                 "closing" if number >= 52 else "personal_model")
        kind = ("opening" if number == 1 else "cta" if number == 55 else
                "instruction" if number in (6, 24, 26, 28, 40) else
                "question" if role == "examiner" else "model")
        spoken, groups = pronunciation(source["text"])
        heading = ("Lea" if role == "candidate_a" else "Prüfer") + " · " + (
            "Kontaktgespräch" if part == 1 else
            "Bildsituation" if number == 27 else "Arzttermin" if 29 <= number <= 39 else
            "Eigene Erfahrungen" if part == 3 and number < 52 else "Prüfungsgespräch")
        turns.append({
            "id": f"a2_{number:02d}", "speaker": role,
            "name": "Lea" if role == "candidate_a" else "Herr Wagner",
            "part": part, "kind": kind, "panel_id": panel, "text": spoken,
            "display_text": source["text"], "display_word_groups": groups,
            "reviewed_text": source["text"], "review_turn_id": number,
            "review_label": source["label"], "heading": heading,
            "pause_after": 0 if number == 55 else 1.2 if kind == "instruction" else .6,
            "camera": "wide" if number == 1 else role,
            "action": "explain" if kind in ("opening", "instruction", "cta") else
                      "ask" if kind == "question" else "describe" if number == 27 else "answer",
            "look_at": "examiner" if role == "candidate_a" else "candidate_a",
        })
    return turns


def load_preview(path, profile="preview"):
    path = Path(path).resolve(strict=True)
    episode = read_episode(path)
    production = episode.get("template") == "a2_speaking_production"
    if production != (profile == "production") or profile not in ("preview", "production"):
        raise ValueError("Use the A2 production template with --profile production.")
    expected_render = ({"motion_step": 2, "native_scale": 1.0, "samples": 8, "native_source": "youtube"}
                       if production else {"motion_step": 3, "native_scale": .25, "samples": 2})
    if (episode.get("template") not in ("a2_speaking_full_preview", "a2_speaking_production")
            or episode.get("exam") != {"family": "oeif", "level": "A2",
                                       "skill": "speaking", "section": "all"}
            or episode.get("fps") != 24 or episode.get("speech_tempo") != .8
            or episode.get("intro_seconds") != 0
            or episode.get("render") != expected_render
            or (not production and episode.get("output_formats") != ["youtube"])
            or episode.get("source", {}).get("duration_limit_seconds") != 900
            or not episode["source"].get("duration_exception")):
        raise ValueError("A2 uses its authorized YouTube-only, 0.8-tempo, bounded full-preview profile.")
    output_sizes(episode)
    contact = (path.parent / episode["contact_build"]).resolve(strict=True)
    manifest_path = contact / "export_manifest.json"
    if sha256_file(manifest_path) != episode["contact_manifest_sha256"]:
        raise ValueError("The reviewed A2 contact manifest changed.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, digest in manifest.items():
        if sha256_file(contact / name) != digest:
            raise ValueError(f"Reviewed A2 contact output changed: {name}")
    transcript = (path.parent / episode["review_script"]).resolve(strict=True)
    if sha256_file(transcript) != episode["review_script_sha256"]:
        raise ValueError("A2 reviewed speech changed; use a new authorized configuration.")
    request = json.loads((contact / "request.json").read_text(encoding="utf-8"))
    storyboard = copy.deepcopy(request["visual"])
    storyboard["panels"] = request["panels"]
    storyboard["scene"]["contact_pose_frame"] = 600
    book = ROOT.parent.parent / "german" / "books" / "a2" / "speaking_oeif_gpt_v1"
    storyboard["source"] = {"book": str(book / "book_no_toc.md"),
                            "manifest": str(book / "audio" / "manifest.jsonl")}
    storyboard["picture_paths"] = [str(book / "images" / f"{i:02d}.jpg") for i in (1, 2, 3)]
    episode["scene"] = copy.deepcopy(storyboard["scene"])
    episode["contact_build"] = str(contact)
    episode["review_script"] = str(transcript)
    episode["turns"] = compile_turns(read_turns(transcript))
    if episode["turns"][0]["display_text"].rstrip(".") != episode["title"]:
        raise ValueError("A2 displayed title and authorized spoken opening differ.")
    validate_episode(episode)
    if set(episode["voices"]) != {"candidate_a", "examiner"}:
        raise ValueError("Only Lea and the active examiner speak in the A2 individual exam.")
    for voice in episode["voices"].values():
        inspect_wav(Path(voice["audio"]))
        if not Path(voice["transcript"]).read_text(encoding="utf-8").strip():
            raise ValueError("A2 reference transcript is empty.")
    if production:
        from a2_speaking_production import resolve_production
        episode = resolve_production(episode, path, storyboard)
    return episode, storyboard


def overlay(episode, storyboard, timeline, mode, frame):
    turn, start, end, active = display_state(episode, timeline, frame)
    panel = copy.deepcopy(next(p for p in storyboard["panels"] if p["id"] == turn["panel_id"]))
    panel["part"] = turn["part"]
    if panel["id"] not in STATIC_PANELS | {"01_opening"}:
        panel["heading"] = turn["heading"]
    if panel["id"] == "01_opening":
        panel["heading"] = episode["title"]
    elif turn["kind"] != "cta":
        panel["body"] = " ".join(turn["display_text"].split()[start:end])
    visual = copy.deepcopy(storyboard)
    if not is_production(episode):
        visual["branding"] += " · VORSCHAU"
    box = FORMATS[mode]["scene"]
    blank = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), PANEL)
    image, check = compose_panel(visual, panel, mode, blank, storyboard["picture_paths"],
                                 active_word=active)
    if turn["kind"] == "cta":
        box = (700, 900, 1780, 1030) if mode == "youtube" else (90, 1518, 900, 1650)
        check["text"].append(text_box(
            ImageDraw.Draw(image), " ".join(turn["display_text"].split()[start:end]),
            box, size=35, minimum=27, highlight_word=active))
    for text in check["text"]:
        if "highlighted_word" in text:
            text["highlight_kind"] = "forced_alignment"
    check.update(frame=frame, turn_id=turn["id"], page=[start, end], active_word=active)
    return image, check


def native_plan(episode, timeline):
    result = []
    box = FORMATS["youtube"]["scene"]
    size = [round((box[i + 2] - box[i]) * episode["render"]["native_scale"]) for i in (0, 1)]
    for index, turn in enumerate(timeline["turns"]):
        if turn["panel_id"] in STATIC_PANELS:
            continue
        stop = (timeline["turns"][index + 1]["start_frame"]
                if index + 1 < len(timeline["turns"]) else timeline["total_frames"])
        result.extend({"format": "youtube", "frame": frame, "camera": turn["camera"],
                       "size": size, "file": f"native/youtube_{frame:05d}.png"}
                      for frame in range(turn["start_frame"], stop, episode["render"]["motion_step"]))
    return result


@generation_job
def build_preview(path, output, jobs=2, until="export", speech_cache_from=None, *,
                  profile="preview", reuse_audio=None, render_device="CPU"):
    from pipeline import run_command
    from check_speech import check_speech

    episode, storyboard = load_preview(path, profile)
    production = is_production(episode)
    reuse = None
    if production:
        from a2_speaking_production import production_inputs, production_reuse_spec, prepare_production_audio
        if speech_cache_from:
            raise ValueError("A2 production reuses exact audio, not raw speech caches.")
        reuse = production_reuse_spec(episode, reuse_audio)
        if render_device != "CPU":
            check_render_device(render_device)
    elif reuse_audio or render_device != "CPU":
        raise ValueError("A2 previews remain CPU-only without exact audio reuse.")
    build = build_directory(output)
    if reuse:
        source = Path(reuse["source"])
        if build == source or build.is_relative_to(source) or source.is_relative_to(build):
            raise ValueError("Production must be separate from its approved preview.")
        episode["render_device"] = render_device
    assets = [Path(path).resolve(), Path(episode["review_script"]),
              Path(episode["contact_build"]) / "export_manifest.json",
              Path(episode["contact_build"]) / "request.json",
              Path(episode["contact_build"]) / "CREDITS.txt",
              Path(storyboard["scene"]["base_scene"]), Path(storyboard["scene"]["wall_logo"]),
              Path(storyboard["source"]["book"]), Path(storyboard["source"]["manifest"]),
              Path(storyboard["promotion"]["cover"]), Path(storyboard["promotion"]["pointing_emoji"]),
              font_path(), font_path(True), *map(Path, storyboard["picture_paths"])]
    assets += [Path(v[k]) for v in episode["voices"].values() for k in ("audio", "transcript")]
    if reuse:
        assets += production_inputs(reuse)
    spec = {"episode": episode, "code_sha256": {n: sha256_file(ROOT / n) for n in SOURCES},
            "asset_sha256": {str(p): sha256_file(p) for p in assets}}
    if reuse:
        spec["audio_reuse"] = reuse
    state_path = build / ("production_state.json" if production else "preview_state.json")
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state["spec"] != spec:
            raise ValueError("A2 preview inputs changed; use a fresh build.")
    else:
        if build.exists() and any(build.iterdir()):
            raise ValueError("Use a fresh A2 preview build.")
        build.mkdir(parents=True, exist_ok=True)
        state = {"spec": spec, "stages": {}}
        atomic_json(state_path, state)
        atomic_json(build / "episode.json", episode)
        atomic_json(build / "storyboard_episode.json", storyboard)
    snapshot = build / "source_export"
    snapshot.mkdir(exist_ok=True)
    for name, digest in spec["code_sha256"].items():
        target = snapshot / name
        if target.exists() and sha256_file(target) != digest:
            raise ValueError("A2 generation snapshot changed.")
        if not target.exists():
            shutil.copy2(ROOT / name, target)

    def stage(name, action, outputs):
        previous = state["stages"].get(name, {})
        if previous and all((build / n).is_file() and sha256_file(build / n) == h
                            for n, h in previous.items()):
            print(f"{name}: verified checkpoint", flush=True)
            return
        order = ("audio_reuse", "audio", "alignment", "speech_check", "scene", "frames",
                 *["encode_" + mode for mode in output_sizes(episode)])
        for dependent in order[order.index(name):]:
            state["stages"].pop(dependent, None)
        atomic_json(state_path, state)
        print(f"{name}: running", flush=True)
        action()
        state["stages"][name] = {str(n): sha256_file(build / n) for n in outputs}
        atomic_json(state_path, state)
        stage_completed(name, force=True)

    python, blender = sys.executable, tool_path("blender")
    if production:
        stage("audio_reuse", lambda: prepare_production_audio(build, reuse),
              ["dialogue.wav", "timeline.json", "audio_timeline.json", "word_alignment.json",
               "subtitles.srt", "speech_asr_check.json", "audio_reuse.json", "auditory_review_flags.json"])
    else:
        command = [python, ROOT / "prepare_audio.py", "--episode", build / "episode.json",
                   "--output-dir", build, "--threads", "8", "--device", "cpu"]
        if speech_cache_from:
            command += ["--speech-cache-from", build_directory(speech_cache_from)]
        stage("audio", lambda: run_command(command, build / "audio.log"),
              ["episode.json", "dialogue.wav", "audio_timeline.json", "subtitles.srt"])
        stage("alignment", lambda: run_command(
            [python, ROOT / "align_words.py", "--build", build], build / "alignment.log"),
            ["timeline.json", "word_alignment.json"])
    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    check_timeline(episode, timeline)
    for turn in timeline["turns"]:
        validate_words(turn["words"], turn["text"], turn["wav_duration"])
    caption_preflight(build, episode, storyboard, timeline, overlay_fn=overlay)
    if not production:
        stage("speech_check", lambda: check_speech(build), ["speech_asr_check.json"])
    plan = native_plan(episode, timeline)
    atomic_json(build / "native_plan.json", plan)
    if until == "audio":
        return build
    native_command = [blender, "-b", episode["scene"]["base_scene"], "--disable-autoexec", "-t", "4",
                      "--python-exit-code", "1", "--python", ROOT / "a2_speaking_preview_scene.py",
                      "--", "--build", build]
    stage("scene", lambda: run_command(native_command + ["--bake"], build / "scene.log"),
          ["preview.blend", "scene_checks.json"])
    if until == "scene":
        return build

    def frames():
        def worker(index):
            command = [blender, "-b", build / "preview.blend", "--disable-autoexec", "-t", "4",
                       "--python-exit-code", "1", "--python", ROOT / "a2_speaking_preview_scene.py",
                       "--", "--build", build, "--worker", str(index), "--jobs", str(jobs)]
            run_command(command, build / f"frames_{index}.log")
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            list(pool.map(worker, range(jobs)))
        receipts = [record for index in range(jobs) for record in json.loads(
            (build / f"native_checks_{index}.json").read_text(encoding="utf-8"))]
        if (len(receipts) != len(plan)
                or {r["file"] for r in receipts} != {r["file"] for r in plan}
                or any(sha256_file(build / r["file"]) != r["sha256"] for r in receipts)):
            raise ValueError("A2 native frame receipts are incomplete.")
        atomic_json(build / "native_checks.json", receipts)

    stage("frames", frames, ["native_checks.json", *[item["file"] for item in plan]])
    def verify_inputs():
        for name, digest in spec["code_sha256"].items():
            if sha256_file(ROOT / name) != digest:
                raise ValueError("A2 implementation changed during generation.")
        for name, digest in spec["asset_sha256"].items():
            if sha256_file(Path(name)) != digest:
                raise ValueError("An A2 source changed during generation.")
    verify_inputs()
    reports = {}
    for mode in output_sizes(episode):
        stage("encode_" + mode, lambda: encode(build, episode, storyboard, timeline, mode,
                                               overlay_fn=overlay, static_panels=STATIC_PANELS),
              [output_name(episode, mode)])
        reports[mode] = review_export(build, episode, storyboard, timeline, mode, overlay_fn=overlay)
    verify_inputs()
    speech = json.loads((build / "speech_asr_check.json").read_text(encoding="utf-8"))
    atomic_json(build / "delivery_checks.json", {
        "status": "production_verified" if production else "preview_only",
        "exports": reports, "render": episode["render"],
        "speech_asr_all_match": speech["all_match"], "source_sha256": spec,
        "voice_cast": episode["voices"], "human_listening_performed": False,
        "preview_approval": episode.get("preview_approval"),
        "limitations": ("Full-resolution exact-audio production; inherited ASR flags remain. No publication approval."
                        if production else "Reduced-quality complete individual-exam practice. "
                        "ASR/alignment do not certify accent or human listening. No production/publication approval."),
    })
    for name in ("CREDITS.txt",):
        shutil.copy2(Path(episode["contact_build"]) / name, build / name)
    outputs = [p for p in build.iterdir() if p.is_file() and p.suffix in
               (".json", ".wav", ".srt", ".mp4", ".jpg", ".blend", ".txt")]
    outputs += [p for folder in ("source_export", *["review_" + mode for mode in output_sizes(episode)])
                for p in (build / folder).rglob("*") if p.is_file()]
    atomic_json(build / "export_manifest.json", {
        "files_sha256": {str(p.relative_to(build)): sha256_file(p) for p in outputs
                         if p.name != "export_manifest.json"},
        "generation_source_sha256": spec["code_sha256"],
    })
    print(f"A2 {'production' if production else 'preview'} ready: {build}", flush=True)
    return build
