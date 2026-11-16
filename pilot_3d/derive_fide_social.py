"""Three strictly-under-180-second portrait edits from the verified single-book fide video."""

import argparse
import copy
import math
from pathlib import Path
import shutil
import wave

from PIL import ImageDraw

from align_words import validate_words
from b2_speaking import shared_head_fits
from derive_long_speaking import link, splice_audio
from episode_config import check_timeline
from fide_speaking import native_plan
from generation_runtime import generation_job
from long_speaking import ACCENT, text_box
from long_speaking_preview import caption_preflight, encode, review_export
from prepare_audio import atomic_json, content_hash, inspect_wav, sha256_file, subtitles
from revise_fide_book import REVISION_SOURCES, overlay as book_overlay, read, verify_hashes
from runtime_config import font_path

ROOT = Path(__file__).resolve().parent
SOURCES = tuple(dict.fromkeys((*REVISION_SOURCES, "derive_fide_social.py")))


def verify_source(source, digest):
    if sha256_file(source / "export_manifest.json") != digest:
        raise ValueError("The approved single-book source manifest changed.")
    manifest = read(source / "export_manifest.json")
    verify_hashes(source, manifest["files_sha256"])
    verify_hashes(source / "derivative_sources", manifest["generation_source_sha256"])
    verify_hashes(ROOT, manifest["generation_source_sha256"])
    episode = read(source / "episode.json")
    report = read(source / "delivery_checks.json")
    if (report.get("status") != "production_book_revision"
            or set(report["exports"]) != {"youtube", "social"}
            or episode.get("speech_tempo") != .8
            or episode["render"] != {
                "motion_step": 2, "native_scale": 1.0, "samples": 8, "native_source": "youtube"}):
        raise ValueError("Use the complete 0.8x single-book shared-frame fide production.")
    if sha256_file(Path(report["book"]["cover"])) != report["book"]["cover_sha256"]:
        raise ValueError("The complete-book cover changed.")
    spec = read(source / "revision_state.json")["spec"]
    verify_hashes(Path(), spec["reused_asset_sha256"])
    receipts, plan = read(source / "native_reuse.json"), read(source / "native_plan.json")
    timeline = read(source / "timeline.json")
    check_timeline(episode, timeline)
    if (len(receipts) != len(plan) or native_plan(episode, timeline) != plan
            or [{k: r[k] for k in p} for r, p in zip(receipts, plan)] != plan):
        raise ValueError("The source native plan and receipts differ.")
    for record in receipts:
        if (sha256_file(source / record["file"]) != record["sha256"]
                or not record["head_bounds"]
                or not all(shared_head_fits(head) for head in record["head_bounds"])):
            raise ValueError(f"Native hash or portrait-safe clearance failed: {record['file']}")
    return episode, timeline, manifest, receipts


def short_cta(original, sentence, fps):
    if original["kind"] != "cta" or not original["display_text"].endswith(sentence):
        raise ValueError("The short CTA must be a complete final source sentence.")
    display = original["display_text"].split()
    tokens = sentence.split()
    first = len(display) - len(tokens)
    if first < 1 or display[first:] != tokens or not display[first - 1].endswith((".", "!", "?")):
        raise ValueError("The CTA cut must start at a complete sentence boundary.")
    groups = original["display_word_groups"][first:]
    first_word = groups[0][0]
    words = original["words"]
    cut = math.floor(words[first_word]["start"] * fps)
    offset = cut / fps
    if offset < words[first_word - 1]["end"]:
        raise ValueError("No frame-aligned gap before the measured CTA sentence; do not clip a word.")
    turn = copy.deepcopy(original)
    turn["display_text"] = sentence
    turn["text"] = " ".join(w["word"] for w in words[first_word:])
    turn["display_word_groups"] = [[i - first_word for i in group] for group in groups]
    turn["words"] = [{**word, "start": word["start"] - offset, "end": word["end"] - offset}
                     for word in words[first_word:]]
    turn["mouth_cues"] = [
        {**cue, "start": max(0, cue["start"] - offset), "end": cue["end"] - offset}
        for cue in original["mouth_cues"] if cue["end"] > offset]
    turn["wav_duration"] -= offset
    turn["duration"] -= offset
    turn["start_frame"] += cut
    turn["start"] += offset
    turn["alignment_key"] = content_hash({
        "source_alignment_key": original["alignment_key"], "source_cut_frame": cut,
        "words": turn["words"], "display_word_groups": turn["display_word_groups"],
    })
    for field in ("raw_audio", "raw_sample_count", "raw_wav_duration", "preprocessing"):
        turn.pop(field, None)
    turn["source_tempo_processing"] = turn["tempo_processing"]
    turn["tempo_processing"] = {"tempo": .8, "operation": "unchanged_measured_pcm_excerpt"}
    turn["source_audio"] = original["audio"]
    turn["source_clip_start_frame"] = cut
    return turn


def short_edit(original, numbers, sentence):
    fps = original["fps"]
    ids = [f"fide_{n:02d}" for n in numbers]
    lookup = {turn["id"]: turn for turn in original["turns"]}
    if (numbers != sorted(set(numbers)) or not numbers or numbers[0] != 1
            or not set(ids) <= lookup.keys() or original["turns"][-1]["id"] in ids):
        raise ValueError("Select ordered complete source turns, beginning with the spoken opening.")
    cta = short_cta(original["turns"][-1], sentence, fps)
    selected = [copy.deepcopy(lookup[key]) for key in ids] + [cta]
    stops = {turn["id"]: original["turns"][i + 1]["start_frame"]
             if i + 1 < len(original["turns"]) else original["total_frames"]
             for i, turn in enumerate(original["turns"])}
    edits, cursor = [], 0
    for turn in selected:
        start, stop = turn["start_frame"], stops[turn["id"]]
        if stop < turn["end_frame"] or start >= stop:
            raise ValueError("Short cuts must retain complete speech and following pauses.")
        shift = cursor - start
        turn["source_start_frame"] = start
        for key in ("start_frame", "end_frame"):
            turn[key] += shift
        for key in ("start", "end"):
            turn[key] += shift / fps
        edits.append({"id": turn["id"], "source_start": start, "source_end": stop,
                      "output_start": cursor, "output_end": cursor + stop - start})
        cursor += stop - start
        validate_words(turn["words"], turn["text"], turn["wav_duration"])
    if cursor >= 180 * fps:
        raise ValueError(f"The complete short is {cursor / fps:.3f}s; it must be strictly below 180s.")
    result = copy.deepcopy(original)
    result.update(turns=selected, total_frames=cursor, duration=cursor / fps)
    result["word_alignment"] = {
        **original["word_alignment"],
        "short_edit": "Exact complete source turns plus measured final CTA sentence; only start offsets rebased.",
    }
    return result, edits


def overlay(episode, storyboard, timeline, mode, frame):
    image, check = book_overlay(episode, storyboard, timeline, mode, frame)
    check["text"].append(text_box(ImageDraw.Draw(image), episode["series_label"],
                                  (72, 90, 908, 145), size=28, minimum=23,
                                  bold=True, color=ACCENT))
    return image, check


def prepare_clip(source, output, original, timeline, clip, sentence, receipts):
    output.mkdir(parents=True, exist_ok=True)
    edited, edits = short_edit(timeline, clip["turn_numbers"], sentence)
    episode = copy.deepcopy(original)
    episode.update(id=clip["id"], output_formats=["social"], series_label=clip["label"])
    episode["source"]["duration_limit_seconds"] = 180
    episode["source"]["duration_exception"] = "User-approved three social excerpts, each strictly below 180 seconds."
    last = edited["turns"][-1]
    source_audio = Path(last["source_audio"])
    cut = last["source_clip_start_frame"]
    target = output / "cta_sentence.wav"
    with wave.open(str(source_audio), "rb") as wav:
        params = wav.getparams()
        if params.framerate % edited["fps"]:
            raise ValueError("CTA sample rate must divide exactly at the measured frame cut.")
        wav.setpos(cut * (params.framerate // edited["fps"]))
        pcm = wav.readframes(wav.getnframes() - wav.tell())
    with wave.open(str(target), "wb") as wav:
        wav.setparams(params)
        wav.writeframes(pcm)
    info = inspect_wav(target)
    last.update(audio=str(target.resolve()), sample_count=info["frames"],
                sample_rate=info["sample_rate"], wav_duration=info["wav_duration"])
    validate_words(last["words"], last["text"], last["wav_duration"])
    episode["turns"] = copy.deepcopy(edited["turns"])
    check_timeline(episode, edited)
    audio = splice_audio(source / "dialogue.wav", output / "dialogue.wav", edits, edited["fps"])
    for name, value in (("episode.json", episode), ("storyboard_episode.json", episode),
                        ("timeline.json", edited), ("edit_decisions.json", edits),
                        ("audio_edit.json", audio)):
        atomic_json(output / name, value)
    atomic_json(output / "word_alignment.json", {
        "provenance": edited["word_alignment"],
        "turns": [{key: turn[key] for key in ("id", "start", "words", "alignment_key")}
                  for turn in edited["turns"]],
    })
    (output / "subtitles.srt").write_text(subtitles(edited), encoding="utf-8")
    for name in ("speech_asr_check.json", "auditory_review_flags.json"):
        shutil.copy2(source / name, output / ("source_" + name))
    shutil.copy2(source / "CREDITS.txt", output / "CREDITS.txt")
    lookup = {r["file"].replace("\\", "/"): r for r in receipts}
    mappings = []
    for item in native_plan(episode, edited):
        turn = next(t for t in reversed(edited["turns"]) if t["start_frame"] <= item["frame"])
        frame = turn["source_start_frame"] + item["frame"] - turn["start_frame"]
        record = lookup[f"native/youtube_{frame:05d}.png"]
        link(source / record["file"], output / item["file"])
        mappings.append({**item, "source_file": record["file"], "sha256": record["sha256"]})
    atomic_json(output / "native_reuse.json", mappings)
    caption_preflight(output, episode, episode, edited, overlay_fn=overlay)
    atomic_json(output / "auditory_review_flags.json", {
        "inherited_source_flags": "source_auditory_review_flags.json retains the full source times.",
        "cta": "A complete sentence cut at a measured gap; original ASR is for the full source CTA.",
        "human_listening_performed": False,
    })
    return episode, edited


@generation_job
def build(config_path, destination, until="export"):
    config_path = config_path.resolve(strict=True)
    config = read(config_path)
    source = (config_path.parent / config["source"]).resolve(strict=True)
    destination = destination.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("Use a separate short-video build directory.")
    original, timeline, manifest, receipts = verify_source(source, config["source_manifest_sha256"])
    spec = {"config": config, "code_sha256": {name: sha256_file(ROOT / name) for name in SOURCES},
            "fonts": {str(font_path(bold)): sha256_file(font_path(bold)) for bold in (False, True)}}
    state_path = destination / "shorts_state.json"
    if state_path.exists():
        state = read(state_path)
        if state["spec"] != spec:
            raise ValueError("Short-video inputs changed; use a fresh build directory.")
    else:
        if destination.exists() and any(destination.iterdir()):
            raise ValueError("Use a fresh short-video build directory.")
        destination.mkdir(parents=True, exist_ok=True)
        state = {"spec": spec, "exports": {}}
        atomic_json(state_path, state)
        snapshot = destination / "source_export"
        snapshot.mkdir()
        for name in spec["code_sha256"]:
            shutil.copy2(ROOT / name, snapshot / name)
    summaries = []
    for clip in config["clips"]:
        output = destination / clip["id"]
        episode, edited = prepare_clip(source, output, original, timeline, clip,
                                       config["cta_sentence"], receipts)
        summaries.append({"id": clip["id"], "label": clip["label"], "frames": edited["total_frames"],
                          "fps": edited["fps"], "duration_seconds": edited["duration"],
                          "output": str(output / "production_social.mp4")})
        print(f"{clip['id']}: {edited['duration']:.3f}s, strictly below 180s.", flush=True)
        if until == "prepare":
            continue
        video = output / "production_social.mp4"
        if clip["id"] in state["exports"]:
            if not video.is_file() or sha256_file(video) != state["exports"][clip["id"]]:
                raise ValueError("A completed short export changed.")
        else:
            encode(output, episode, episode, edited, "social", overlay_fn=overlay,
                   static_panels={"a2_picture", "b1_choice", "cta"})
            state["exports"][clip["id"]] = sha256_file(video)
            atomic_json(state_path, state)
        report = review_export(output, episode, episode, edited, "social", overlay_fn=overlay)
        for mapping in read(output / "native_reuse.json"):
            if sha256_file(output / mapping["file"]) != mapping["sha256"]:
                raise ValueError("A reused native image changed during composition.")
        atomic_json(output / "delivery_checks.json", {
            "status": "social_excerpt_under_180_seconds", "exports": {"social": report},
            "source": str(source), "source_manifest_sha256": config["source_manifest_sha256"],
            "series_label": clip["label"], "audio_edit": read(output / "audio_edit.json"),
            "new_native_rendering": False, "new_speech_or_alignment": False,
            "human_listening_performed": False, "publication_approved": False,
        })
        atomic_json(output / "export_manifest.json", {
            "files_sha256": {str(p.relative_to(output)): sha256_file(p) for p in output.rglob("*")
                             if p.is_file() and "native" not in p.relative_to(output).parts
                             and p != output / "export_manifest.json"},
            "source_manifest_sha256": config["source_manifest_sha256"],
        })
    verify_hashes(ROOT, spec["code_sha256"])
    verify_hashes(Path(), spec["fonts"])
    verify_hashes(source, manifest["files_sha256"])
    if sha256_file(source / "export_manifest.json") != config["source_manifest_sha256"]:
        raise ValueError("The full-video source manifest changed.")
    atomic_json(destination / "shorts_plan.json", {
        "clips": summaries, "all_strictly_below_180_seconds": True,
        "original_full_video_unchanged": True, "full_exports_generated": until == "export",
    })
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--until", choices=("prepare", "export"), default="export")
    args = parser.parse_args()
    build(args.config, args.build, args.until)
