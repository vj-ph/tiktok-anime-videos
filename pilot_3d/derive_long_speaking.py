"""Compose B2 portrait deliveries from verified production images and speech."""

import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import wave

from generation_runtime import generation_job
from b2_speaking import shared_head_fits
from long_speaking import compile_script, panels
from long_speaking_preview import (
    caption_preflight, encode, review_export,
)
from long_speaking_production import notice_at
from prepare_audio import atomic_json, sha256_file, subtitles


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def short_edit(timeline, ranges):
    fps = timeline["fps"]
    turns = {turn["id"]: turn for turn in timeline["turns"]}
    selected, edits, notices = [], [], []
    cursor, previous_part = 0, 0
    cards = {1: "prepare_teil1", 2: "reading_summary", 3: "prepare_teil3"}
    for item in ranges:
        turn = copy.deepcopy(turns[item["turn_id"]])
        first, last = item["start_frame"], item["end_frame"]
        if first != turn["start_frame"] or last < turn["end_frame"] or first >= last:
            raise ValueError("Short edits must preserve complete speech turns.")
        if turn["part"] and turn["part"] != previous_part:
            stop = cursor + 3 * fps
            notices.append({
                "id": f"short_teil{turn['part']}", "panel_id": cards[turn["part"]],
                "start_frame": cursor, "end_frame": stop,
                "text": "Kurzfassung: ausgewählte vollständige Gesprächsbeiträge.",
            })
            edits.append({"id": notices[-1]["id"], "frames": stop - cursor,
                          "output_start": cursor, "output_end": stop})
            cursor = stop
            previous_part = turn["part"]
        shift = cursor - first
        turn["source_start_frame"] = first
        for key in ("start_frame", "end_frame"):
            turn[key] += shift
        for key in ("start", "end"):
            turn[key] += shift / fps
        turn["pause_after_frames"] = last - timeline["turns"][
            next(i for i, t in enumerate(timeline["turns"]) if t["id"] == turn["id"])
        ]["end_frame"]
        turn["pause_after_seconds"] = turn["pause_after_frames"] / fps
        selected.append(turn)
        stop = cursor + last - first
        edits.append({"id": turn["id"], "source_start": first, "source_end": last,
                      "output_start": cursor, "output_end": stop})
        cursor = stop
    if (selected[0]["kind"] != "opening" or selected[-1]["kind"] != "cta"
            or {t["part"] for t in selected} != {0, 1, 2, 3} or cursor >= 180 * fps):
        raise ValueError("Short edit must include opening, all three Teile and CTA below 180s.")
    result = copy.deepcopy(timeline)
    result.update(turns=selected, silent_notices=notices, total_frames=cursor,
                  duration=cursor / fps)
    result["edit_provenance"] = "Exact source speech and local alignment; absolute starts rebased."
    return result, edits


def splice_audio(source, target, edits, fps):
    with wave.open(str(source), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 48000):
            raise ValueError("Expected verified 48kHz mono PCM16 production speech.")
        pcm = wav.readframes(wav.getnframes())
    stride = 48000 // fps * 2
    chunks = [pcm[e["source_start"] * stride:e["source_end"] * stride]
              if "source_start" in e else bytes(e["frames"] * stride) for e in edits]
    joined = b"".join(chunks)
    if len(joined) != edits[-1]["output_end"] * stride:
        raise ValueError("Edited audio does not match its exact frame clock.")
    with wave.open(str(target), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(48000)
        wav.writeframes(joined)
    with wave.open(str(target), "rb") as wav:
        actual = wav.readframes(wav.getnframes())
    if actual != joined:
        raise ValueError("Edited PCM failed exact source-span verification.")
    return {"exact_source_pcm_spans": True, "inserted_cards_digital_silence": True,
            "no_time_stretch_or_synthesis": True, "sha256": sha256_file(target)}


def link(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)


def verify_source(source):
    manifest = read(source / "export_manifest.json")
    for name, digest in manifest["files_sha256"].items():
        if sha256_file(source / name) != digest:
            raise ValueError(f"Source export changed: {name}")
    for name, digest in manifest["generation_source_sha256"].items():
        if sha256_file(Path(__file__).parent / name) != digest:
            raise ValueError(f"Source compositor changed: {name}")
    report = read(source / "delivery_checks.json")
    if report["status"] != "production" or "youtube" not in report["exports"]:
        raise ValueError("A verified YouTube production delivery is required.")
    episode = read(source / "episode.json")
    if episode["exam"]["level"] != "B2" or episode["render"] != {
        "motion_step": 2, "native_scale": 1.0, "samples": 8, "native_source": "youtube"
    }:
        raise ValueError("Expected B2 shared-frame production.")
    for name, digest in report["source_sha256"]["asset_sha256"].items():
        if sha256_file(Path(name)) != digest:
            raise ValueError(f"Production asset changed: {name}")
    receipts = read(source / "native_checks.json")
    planned = read(source / "native_plan.json")
    if [r["file"] for r in receipts] != [r["file"] for r in planned]:
        raise ValueError("Native receipts do not match the production plan.")
    for index, receipt in enumerate(receipts, 1):
        if (sha256_file(source / receipt["file"]) != receipt["sha256"]
                or not all(shared_head_fits(head) for head in receipt["head_bounds"])):
            raise ValueError(f"Native image hash or portrait crop failed: {receipt['file']}")
        if index % 1000 == 0:
            print(f"Verified source native images: {index}/{len(receipts)}", flush=True)
    print(f"Verified {len(manifest['files_sha256'])} exports and {len(receipts)} native images.",
          flush=True)
    return manifest, receipts


def prepare(source, output, short, receipts):
    episode = read(source / "episode.json")
    episode["output_formats"] = ["social"]
    storyboard = read(source / "storyboard_episode.json")
    timeline = read(source / "timeline.json")
    edits = None
    if short:
        ranges = read(source / "b2_timing_checks.json")["short_candidate_ranges"]
        timeline, edits = short_edit(timeline, ranges)
        episode["source"]["duration_limit_seconds"] = 180
        episode["turns"] = [copy.deepcopy(t) for t in timeline["turns"]]
        storyboard["branding"] += " · Kurzfassung"
    output.mkdir(parents=True)
    for name, value in (("episode.json", episode), ("storyboard_episode.json", storyboard),
                        ("timeline.json", timeline)):
        atomic_json(output / name, value)
    atomic_json(output / "word_alignment.json", {
        "provenance": timeline["word_alignment"],
        "turns": [{key: turn[key] for key in ("id", "start", "words", "alignment_key")}
                  for turn in timeline["turns"]],
    })
    shutil.copy2(source / "speech_asr_check.json", output / "source_speech_asr_check.json")
    shutil.copy2(source / "auditory_review_flags.json", output / "source_auditory_review_flags.json")
    if short:
        audio = splice_audio(source / "dialogue.wav", output / "dialogue.wav", edits, timeline["fps"])
        atomic_json(output / "edit_decisions.json", edits)
    else:
        shutil.copy2(source / "dialogue.wav", output / "dialogue.wav")
        audio = {"exact_complete_source_wav": sha256_file(output / "dialogue.wav")
                 == sha256_file(source / "dialogue.wav")}
    (output / "subtitles.srt").write_text(subtitles(timeline), encoding="utf-8")
    lookup = {r["file"]: r for r in receipts}
    static = {"05_teil2_picture", "12_final_cta"} | {
        p["id"] for p in panels(storyboard, compile_script(storyboard)) if p.get("card_text")
    }
    mappings = []
    for index, turn in enumerate(timeline["turns"]):
        if turn["panel_id"] in static:
            continue
        stop = (edits[next(i for i, e in enumerate(edits) if e["id"] == turn["id"])]["output_end"]
                if short else timeline["turns"][index + 1]["start_frame"]
                if index + 1 < len(timeline["turns"]) else timeline["total_frames"])
        for frame in range(turn["start_frame"], stop, episode["render"]["motion_step"]):
            if notice_at(timeline, frame):
                continue
            original = turn.get("source_start_frame", turn["start_frame"]) + frame - turn["start_frame"]
            name = f"native/youtube_{original:05d}.png"
            receipt = lookup[name]
            destination = f"native/youtube_{frame:05d}.png"
            link(source / name, output / destination)
            mappings.append({"file": destination, "source_file": name,
                             "sha256": receipt["sha256"], "head_bounds": receipt["head_bounds"]})
    atomic_json(output / "native_reuse.json", mappings)
    return episode, storyboard, timeline, audio, edits


@generation_job
def build(source, build, short_only=False):
    source, build = source.resolve(strict=True), build.resolve()
    if source == build or source in build.parents or build.exists():
        raise ValueError("Use a fresh derivative directory separate from its source.")
    manifest, receipts = verify_source(source)
    original_manifest = sha256_file(source / "export_manifest.json")
    build.mkdir()
    atomic_json(build / "source_verification.json", {
        "source": str(source), "manifest_sha256": original_manifest,
        "export_files_verified": len(manifest["files_sha256"]),
        "native_images_verified": len(receipts), "all_portrait_head_bounds_fit": True,
        "generation_source_sha256": manifest["generation_source_sha256"],
    })
    deliveries = ((True, "social_under3"),) if short_only else (
        (False, "full_social"), (True, "social_under3"))
    for short, folder in deliveries:
        output = build / folder
        episode, storyboard, timeline, audio, edits = prepare(source, output, short, receipts)
        print(f"{folder}: {timeline['total_frames']} frames / {timeline['duration']:.3f}s; "
              "caption checks", flush=True)
        caption_preflight(output, episode, storyboard, timeline)
        print(f"{folder}: encoding existing scene images; no Blender or TTS", flush=True)
        encode(output, episode, storyboard, timeline, "social")
        print(f"{folder}: encoded delivery review", flush=True)
        report = review_export(output, episode, storyboard, timeline, "social")
        atomic_json(output / "delivery_checks.json", {
            "status": "production_derivative", "exports": {"social": report},
            "source": str(source), "source_manifest_sha256": original_manifest,
            "audio_verification": audio, "shortened_example": short,
            "native_scene_transform": "fixed center crop of lossless YouTube images",
            "new_native_rendering": False, "new_speech_or_alignment": False,
            "human_listening_performed": False, "publication_approved": False,
            "inherited_asr_flags": "source_speech_asr_check.json; original source times",
            "inherited_auditory_flags": "source_auditory_review_flags.json; original source times",
            "source_times_for_short_turns": "timeline.json: source_start_frame",
        })
        for mapping in read(output / "native_reuse.json"):
            if sha256_file(output / mapping["file"]) != mapping["sha256"]:
                raise ValueError("A reused native image changed during composition.")
        selected = [p for p in output.rglob("*") if p.is_file() and "native" not in p.parts
                    and p.suffix in (".json", ".wav", ".srt", ".mp4", ".jpg", ".png")]
        shutil.copy2(Path(__file__), output / "derivative_source.py")
        atomic_json(output / "export_manifest.json", {
            "files_sha256": {str(p.relative_to(output)): sha256_file(p) for p in selected},
            "derivative_source_sha256": sha256_file(output / "derivative_source.py"),
            "generation_source_sha256": manifest["generation_source_sha256"],
        })
        print(f"Verified delivery ready: {output}", flush=True)
    for name, digest in manifest["files_sha256"].items():
        if sha256_file(source / name) != digest:
            raise ValueError(f"Original source export changed: {name}")
    if sha256_file(source / "export_manifest.json") != original_manifest:
        raise ValueError("Original source manifest changed.")
    atomic_json(build / "source_preservation.json", {
        "original_exports_and_manifest_unchanged": True,
        "native_receipts_verified_again_in_derivative": True,
        "source_manifest_sha256": original_manifest,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--short-only", action="store_true",
                        help="Produce only the short derivative, preserving an existing full portrait.")
    args = parser.parse_args()
    build(args.source, args.build, args.short_only)
