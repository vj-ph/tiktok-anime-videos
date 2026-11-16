"""Recompose the completed fide production with one book and a singular spoken CTA."""

import argparse
import copy
import json
import math
from pathlib import Path
import re
import shutil
import sys
import wave

from PIL import Image, ImageDraw, ImageOps

from align_words import validate_words
from b2_speaking import shared_head_fits
from derive_long_speaking import link
from episode_config import check_timeline
from fide_content import export_text, pronunciation
from fide_speaking import SOURCES, STATIC, compose_turn, native_plan, paste
from generation_runtime import generation_job
from long_speaking import ACCENT, BG, FORMATS, text_box
from long_speaking_preview import (
    caption_preflight, display_state, encode, native_sample, output_sizes, review_export,
)
from pipeline import run_command
from prepare_audio import atomic_json, sha256_file, subtitles

ROOT = Path(__file__).resolve().parent
REVISION_SOURCES = tuple(dict.fromkeys((*SOURCES, "derive_long_speaking.py", "revise_fide_book.py")))


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify_hashes(root, hashes):
    for name, digest in hashes.items():
        if sha256_file(root / name) != digest:
            raise ValueError(f"Revision source changed: {name}")


def load_config(path):
    path = path.resolve(strict=True)
    config = read(path)
    config["source"] = str((path.parent / config["source"]).resolve(strict=True))
    book = config["book"]
    book["cover"] = str((path.parent / book["cover"]).resolve(strict=True))
    if sha256_file(Path(book["cover"])) != book["cover_sha256"]:
        raise ValueError("The supplied complete-book cover changed.")
    if not re.fullmatch(r"https://amzn\.eu/d/[A-Za-z0-9]+", book["url"]):
        raise ValueError("Use the supplied Amazon product link.")
    if config["authorization"].get("requested_by") != "user":
        raise ValueError("A book revision must be requested by the user.")
    return config


def verify_source(config):
    source = Path(config["source"])
    if sha256_file(source / "export_manifest.json") != config["source_manifest_sha256"]:
        raise ValueError("The selected production manifest changed.")
    manifest = read(source / "export_manifest.json")
    verify_hashes(source, manifest["files_sha256"])
    verify_hashes(source / "source_export", manifest["generation_source_sha256"])
    verify_hashes(ROOT, manifest["generation_source_sha256"])
    episode, timeline = read(source / "episode.json"), read(source / "timeline.json")
    report = read(source / "delivery_checks.json")
    if (episode.get("template") != "fide_speaking_production"
            or report.get("status") != "production_verified"
            or set(report["exports"]) != {"youtube", "social"}
            or episode["render"] != {
                "motion_step": 2, "native_scale": 1.0, "samples": 8, "native_source": "youtube"}):
        raise ValueError("Use the completed full-resolution, dual-format fide production.")
    assets = report["source_sha256"]["asset_sha256"]
    # Manuscripts and scene-building assets are not reopened when reusing verified PCM/PNGs.
    reused = [episode["picture"], episode["promotion"]["pointing_emoji"],
              *(voice[key] for voice in episode["voices"].values() for key in ("audio", "transcript"))]
    verify_hashes(Path(), {name: assets[name] for name in reused})
    verify_hashes(Path(), read(source / "speech_chain_hashes.json"))
    check_timeline(episode, timeline)
    receipts, plan = read(source / "native_checks.json"), read(source / "native_plan.json")
    if [{k: r[k] for k in p} for r, p in zip(receipts, plan)] != plan:
        raise ValueError("The native receipts do not match the complete production plan.")
    if len(receipts) != len(plan) or native_plan(episode, timeline) != plan:
        raise ValueError("The complete shared native plan is required.")
    for record in receipts:
        if (sha256_file(source / record["file"]) != record["sha256"]
                or not record["head_bounds"]
                or not all(shared_head_fits(head) for head in record["head_bounds"])):
            raise ValueError(f"Native image or portrait-safe bounds changed: {record['file']}")
    print(f"Verified completed production: {len(receipts)} reusable native images.", flush=True)
    return episode, manifest, receipts


def revised_episode(original, config):
    episode = copy.deepcopy(original)
    for key in ("approved_preview", "approved_preview_manifest_sha256", "preview_approval"):
        episode.pop(key, None)
    episode["id"] += "_single_book"
    episode["revision_authorization"] = config["authorization"]
    episode["promotion"] = {
        "book": copy.deepcopy(config["book"]),
        "pointing_emoji": original["promotion"]["pointing_emoji"],
    }
    if episode["turns"][-1]["kind"] != "cta" or episode["turns"][-1]["panel_id"] not in STATIC:
        raise ValueError("Only a final static CTA can be changed without native rendering.")
    turn = episode["turns"][-1]
    turn["display_text"] = config["spoken_cta"]
    turn["text"], turn["display_word_groups"] = pronunciation(turn["display_text"])
    return episode


def overlay(episode, storyboard, timeline, mode, frame):
    turn, first, last, active = display_state(episode, timeline, frame)
    book = episode["promotion"]["book"]
    if turn["kind"] != "cta":
        compatible = {**episode, "promotion": {
            "a2": book, "b1": book, "pointing_emoji": episode["promotion"]["pointing_emoji"]}}
        return compose_turn(compatible, turn, mode, first, last, active, frame)
    portrait = mode == "social"
    image = Image.new("RGB", FORMATS[mode]["size"], BG)
    draw = ImageDraw.Draw(image)
    texts = []

    def text(value, box, **options):
        record = text_box(draw, value, box, **options)
        if "highlighted_word" in record:
            record["highlight_kind"] = "forced_alignment"
        texts.append(record)

    text("DEUTSCH KOMPASS · fide A2-B1",
         (72, 175, 908, 222) if portrait else (64, 40, 1856, 90),
         size=30 if portrait else 35, bold=True, color=ACCENT)
    text(turn["heading"], (72, 238, 908, 348) if portrait else (64, 105, 1856, 183),
         size=43 if portrait else 49, minimum=30, bold=True)
    cover = paste(image, book["cover"],
                  (330, 390, 750, 1020) if portrait else (200, 270, 580, 840))
    text(book["cta"], (90, 1070, 900, 1320) if portrait else (730, 330, 1780, 620),
         size=43 if portrait else 49, minimum=33, bold=True)
    cue = "Amazon: Link in der Bio" if portrait else "Amazon: Link in der Beschreibung"
    paste(image, episode["promotion"]["pointing_emoji"],
          (90, 1360, 130, 1400) if portrait else (730, 715, 774, 759))
    text(cue, (155, 1345, 900, 1450) if portrait else (800, 700, 1810, 850),
         size=39 if portrait else 45, minimum=30, color=ACCENT, bold=True)
    caption_box = (90, 1500, 900, 1730) if portrait else (64, 900, 1856, 1030)
    text(" ".join(turn["display_text"].split()[first:last]), caption_box,
         size=37 if portrait else 35, minimum=28, highlight_word=active)
    return image, {
        "id": turn["panel_id"], "format": mode, "frame": frame, "turn_id": turn["id"],
        "size": list(image.size), "page": [first, last], "active_word": active, "text": texts,
        "cover_count": 1, "cover_box": cover, "book_url": book["url"],
        "promo_group": False, "cta_box": list(caption_box),
    }


def replace_cta(original, replacement):
    if len(replacement["turns"]) != 1 or replacement["turns"][0]["kind"] != "cta":
        raise ValueError("The replacement must contain exactly one CTA.")
    old, new = original["turns"][-1], replacement["turns"][0]
    if (old["kind"] != "cta" or new["id"] != old["id"]
            or replacement["fps"] != original["fps"] or new["start_frame"] != 0):
        raise ValueError("Only the final CTA may be replaced at its original start frame.")
    offset = old["start_frame"]
    result = copy.deepcopy(original)
    turn = copy.deepcopy(new)
    for key in ("start_frame", "end_frame"):
        turn[key] += offset
    for key in ("start", "end"):
        turn[key] += offset / original["fps"]
    result["turns"][-1] = turn
    result["total_frames"] = offset + replacement["total_frames"]
    result["duration"] = result["total_frames"] / original["fps"]
    result["word_alignment"] = {
        **original["word_alignment"], "final_cta_revision": replacement["word_alignment"],
        "note": "All exam speech and local alignment unchanged; only the final static CTA was resynthesized.",
    }
    return result


def join_audio(source, cta, output, first, fps):
    if 48000 % fps:
        raise ValueError("The frame rate must divide the PCM sample rate.")
    boundary = first * (48000 // fps)
    with wave.open(str(source), "rb") as old, wave.open(str(cta), "rb") as new:
        for handle in (old, new):
            if (handle.getnchannels(), handle.getsampwidth(), handle.getframerate()) != (1, 2, 48000):
                raise ValueError("Expected 48kHz mono PCM16 speech.")
        prefix, suffix = old.readframes(boundary), new.readframes(new.getnframes())
    if len(prefix) != boundary * 2:
        raise ValueError("The original speech ends before the CTA boundary.")
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(48000)
        wav.writeframes(prefix + suffix)
    with wave.open(str(output), "rb") as wav:
        if wav.readframes(wav.getnframes()) != prefix + suffix:
            raise ValueError("Recomposed audio differs from the exact selected PCM spans.")
    return {"unchanged_prefix_samples": boundary, "replacement_cta_samples": len(suffix) // 2,
            "prefix_pcm_byte_identical": True, "sha256": sha256_file(output)}


def prepare(build, episode, source, receipts):
    original, replacement = read(source / "timeline.json"), read(build / "cta" / "timeline.json")
    timeline = replace_cta(original, replacement)
    check_timeline(episode, timeline)
    for turn in timeline["turns"]:
        validate_words(turn["words"], turn["text"], turn["wav_duration"])
    if timeline["turns"][:-1] != original["turns"][:-1]:
        raise ValueError("Exam speech or timing changed.")
    audio = join_audio(source / "dialogue.wav", build / "cta" / "dialogue.wav",
                       build / "dialogue.wav", original["turns"][-1]["start_frame"], timeline["fps"])
    if (audio["unchanged_prefix_samples"] + audio["replacement_cta_samples"]
            != timeline["total_frames"] * (48000 // timeline["fps"])):
        raise ValueError("The audio does not match the revised video clock.")
    atomic_json(build / "audio_revision.json", audio)
    atomic_json(build / "timeline.json", timeline)
    atomic_json(build / "word_alignment.json", {
        "provenance": timeline["word_alignment"],
        "turns": [{k: turn[k] for k in ("id", "start", "words", "alignment_key")}
                  for turn in timeline["turns"]],
    })
    (build / "subtitles.srt").write_text(subtitles(timeline), encoding="utf-8")
    speech, cta_speech = read(source / "speech_asr_check.json"), read(build / "cta" / "speech_asr_check.json")
    if speech["turns"][-1]["id"] != cta_speech["turns"][0]["id"]:
        raise ValueError("The independently checked replacement CTA has a different ID.")
    speech["turns"][-1] = cta_speech["turns"][0]
    speech.update(all_match=all(t["matches"] for t in speech["turns"]),
                  episode_sha256=sha256_file(build / "episode.json"),
                  timeline_sha256=sha256_file(build / "timeline.json"),
                  revision_provenance={"original": str(source / "speech_asr_check.json"),
                                       "replacement": str(build / "cta" / "speech_asr_check.json")})
    atomic_json(build / "speech_asr_check.json", speech)
    plan = native_plan(episode, timeline)
    if plan != read(source / "native_plan.json"):
        raise ValueError("A book-only revision must not change the native scene plan.")
    for record in receipts:
        link(source / record["file"], build / record["file"])
    atomic_json(build / "native_reuse.json", receipts)
    atomic_json(build / "native_plan.json", plan)
    shutil.copy2(source / "CREDITS.txt", build / "CREDITS.txt")
    export_text(episode, build)
    return timeline


def contacts(build, episode, timeline):
    checks = []
    for mode in output_sizes(episode):
        selected = [next(t for t in timeline["turns"] if t["section"] == section)
                    for section in dict.fromkeys(t["section"] for t in timeline["turns"])]
        thumb = (480, 270) if mode == "youtube" else (270, 480)
        sheet = Image.new("RGB", (thumb[0] * 3, thumb[1] * math.ceil(len(selected) / 3)), BG)
        for index, turn in enumerate(selected):
            frame = turn["start_frame"]
            image, check = overlay(episode, episode, timeline, mode, frame)
            if turn["panel_id"] not in STATIC:
                box = FORMATS[mode]["scene"]
                sample = native_sample(turn, frame, episode["render"]["motion_step"])
                with Image.open(build / "native" / f"youtube_{sample:05d}.png") as native:
                    image.paste(ImageOps.fit(native.convert("RGB"), (box[2] - box[0], box[3] - box[1]),
                                             Image.Resampling.LANCZOS), box[:2])
            target = build / f"contact_{mode}_{turn['section']}.png"
            image.save(target)
            checks.append({**check, "file": target.name, "sha256": sha256_file(target)})
            sheet.paste(image.resize(thumb), ((index % 3) * thumb[0], (index // 3) * thumb[1]))
        sheet.save(build / f"contact_{mode}.jpg", quality=94)
    atomic_json(build / "contact_checks.json", checks)


@generation_job
def build_revision(config_path, destination, until="export"):
    config = load_config(config_path)
    source = Path(config["source"])
    build = destination.resolve()
    if source == build or source in build.parents or build in source.parents:
        raise ValueError("Use a separate fresh derivative directory.")
    original, manifest, receipts = verify_source(config)
    episode = revised_episode(original, config)
    spec = {"config": config, "config_sha256": sha256_file(config_path),
            "code_sha256": {name: sha256_file(ROOT / name) for name in REVISION_SOURCES},
            "reused_asset_sha256": {
                name: sha256_file(Path(name)) for name in
                [original["picture"], original["promotion"]["pointing_emoji"],
                 *(voice[key] for voice in original["voices"].values()
                   for key in ("audio", "transcript"))]}}
    state_path = build / "revision_state.json"
    if state_path.exists():
        state = read(state_path)
        if state["spec"] != spec:
            raise ValueError("Revision inputs changed; use a fresh derivative.")
    else:
        if build.exists() and any(build.iterdir()):
            raise ValueError("Use a fresh derivative directory.")
        build.mkdir(parents=True, exist_ok=True)
        state = {"spec": spec, "stages": {}}
        atomic_json(state_path, state)
        atomic_json(build / "episode.json", episode)
        atomic_json(build / "storyboard_episode.json", episode)
        snapshot = build / "derivative_sources"
        snapshot.mkdir()
        for name in spec["code_sha256"]:
            shutil.copy2(ROOT / name, snapshot / name)

    def stage(name, action, outputs):
        previous = state["stages"].get(name)
        if previous:
            verify_hashes(build, previous)
            print(f"{name}: verified checkpoint", flush=True)
            return
        print(f"{name}: running", flush=True)
        action()
        state["stages"][name] = {p: sha256_file(build / p) for p in outputs}
        atomic_json(state_path, state)

    cta = build / "cta"
    cta.mkdir(exist_ok=True)
    cta_episode = {**episode, "intro_seconds": 0, "turns": [episode["turns"][-1]]}
    atomic_json(cta / "episode.json", cta_episode)

    def cta_audio():
        run_command([sys.executable, "-B", "-X", "utf8", ROOT / "prepare_audio.py",
                     "--episode", cta / "episode.json", "--output-dir", cta,
                     "--threads", "8", "--device", "cpu"], cta / "audio.log")
        run_command([sys.executable, "-B", "-X", "utf8", ROOT / "align_words.py",
                     "--build", cta], cta / "alignment.log")
        from check_speech import check_speech
        check_speech(cta)

    stage("cta", cta_audio, ["cta/timeline.json", "cta/dialogue.wav", "cta/word_alignment.json",
                              "cta/speech_asr_check.json"])
    stage("prepare", lambda: prepare(build, episode, source, receipts),
          ["timeline.json", "dialogue.wav", "word_alignment.json", "speech_asr_check.json",
           "subtitles.srt", "native_reuse.json", "native_plan.json", "audio_revision.json"])
    timeline = read(build / "timeline.json")
    caption_preflight(build, episode, episode, timeline, overlay_fn=overlay)
    stage("contacts", lambda: contacts(build, episode, timeline),
          ["contact_checks.json", "contact_youtube.jpg", "contact_social.jpg"])
    if until == "contacts":
        return build
    reports = {}
    for mode in output_sizes(episode):
        stage("encode_" + mode, lambda: encode(build, episode, episode, timeline, mode,
                                               overlay_fn=overlay, static_panels=STATIC),
              [f"production_{mode}.mp4"])
        reports[mode] = review_export(build, episode, episode, timeline, mode, overlay_fn=overlay)
    verify_hashes(ROOT, spec["code_sha256"])
    verify_hashes(Path(), spec["reused_asset_sha256"])
    verify_hashes(source, manifest["files_sha256"])
    if sha256_file(source / "export_manifest.json") != config["source_manifest_sha256"]:
        raise ValueError("The original production manifest changed.")
    if sha256_file(Path(config["book"]["cover"])) != config["book"]["cover_sha256"]:
        raise ValueError("The supplied cover changed during composition.")
    for record in receipts:
        if sha256_file(build / record["file"]) != record["sha256"]:
            raise ValueError("A reused native image changed during composition.")
    preflight, speech = read(build / "caption_preflight.json"), read(build / "speech_asr_check.json")
    atomic_json(build / "auditory_review_flags.json", {
        "asr_disagreements": [t for t in speech["turns"] if not t["matches"]],
        "low_confidence_words": preflight["low_confidence_words"],
        "reading_warnings": preflight["reading_warnings"], "human_listening_performed": False,
    })
    atomic_json(build / "delivery_checks.json", {
        "status": "production_book_revision", "exports": reports, "book": config["book"],
        "source": str(source), "source_manifest_sha256": config["source_manifest_sha256"],
        "original_production_unchanged": True, "new_native_rendering": False,
        "native_images_reused": len(receipts), "exam_speech_and_timings_unchanged": True,
        "source_verification_scope": "All frozen delivery files, snapshots, PCM/speech-chain and native "
                                     "PNGs verified. Only reused picture/emoji/voice assets reopened; "
                                     "historical manuscripts and scene-construction assets not reloaded.",
        "new_speech": "Final static CTA only; Swiss examiner voice, pitch-preserving 0.8x.",
        "audio_revision": read(build / "audio_revision.json"),
        "human_listening_performed": False, "publication_approved": False,
    })
    atomic_json(build / "export_manifest.json", {
        "files_sha256": {str(p.relative_to(build)): sha256_file(p) for p in build.rglob("*")
                         if p.is_file() and "native" not in p.relative_to(build).parts
                         and p != build / "export_manifest.json"},
        "source_manifest_sha256": config["source_manifest_sha256"],
        "generation_source_sha256": spec["code_sha256"],
    })
    print(f"Single-book fide video ready: {build}", flush=True)
    return build


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--until", choices=("contacts", "export"), default="export")
    args = parser.parse_args()
    build_revision(args.config, args.build, args.until)
