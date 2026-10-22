#!/usr/bin/env python3
"""Decode exports and produce publication-safe-area review sheets."""

import argparse
import json
import subprocess
import wave
from pathlib import Path

from build_paths import resolve_build_reference
from align_words import validate_words
from prepare_audio import atomic_json, sha256_file
from episode_config import promo_settings, task_window
from social_captions import (MAX_PAGE_CPS, MIN_PAGE_SECONDS, SAFE, caption_pages,
                             displayed_seconds, make_ass)


def frame_at(build, filename, seconds, target):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", f"{seconds:.6f}",
                    "-i", str(build / filename), "-frames:v", "1", "-update", "1", str(target)], check=True)


def review_cameras(build, timeline, manifest):
    from produce_v4 import CAMERA_PREFIXES, camera_at_frame

    edit = manifest.get("derived_edit")
    context = resolve_build_reference(edit["source"]) if edit else build
    source_manifest = json.loads((context / "scene_manifest.json").read_text())
    receipt = json.loads((context / "frames_manifest.json").read_text())
    scene_hash = sha256_file(build / "studio.blend")
    if receipt != {"scene": source_manifest, "blend_sha256": scene_hash}:
        raise ValueError("Camera source frames are stale for their saved scene.")
    revision_path = context / "camera_revision_report.json"
    reused, changed = [], []
    if revision_path.exists():
        revision = json.loads(revision_path.read_text())
        if scene_hash != revision["revised_scene_sha256"]:
            raise ValueError("Camera report belongs to a different source scene.")
        markers = revision["new_markers"]
        reused, changed = revision["reused_frames"], revision["rerender_frames"]
        for item in reused:
            if sha256_file(context / "frames" / f"frame_{item['frame']:04d}.png") != item["sha256"]:
                raise ValueError(f"Verified reused pose changed: {item['frame']}")
    else:
        markers = source_manifest["camera_markers"]
    checked = 0
    step = manifest["motion_step"]
    for frame in range(timeline["total_frames"]):
        seconds = frame / timeline["fps"]
        pose = 1 + frame // step * step
        if edit:
            requested = min(edit["source_stop_frame_exclusive"], max(
                edit["source_start_frame_zero_based"] + 1,
                edit["source_start_frame_zero_based"] + pose - edit["intro_hold_frames"]))
            pose = 1 + (requested - 1) // step * step
        camera = camera_at_frame(markers, pose)
        for turn in timeline["turns"]:
            if turn["start"] + turn["words"][0]["start"] <= seconds < turn["start"] + turn["words"][-1]["end"]:
                if not camera.startswith(CAMERA_PREFIXES[turn["camera"]]):
                    raise ValueError(f"Encoded pose leaves speaker in turn {turn['id']}, frame {frame}: {camera}")
                checked += 1
    return {"encoded_speaking_frames_checked": checked, "early_listener_cutaways": 0,
            "unchanged_pose_hashes_checked": len(reused),
            "camera_changed_poses_rerendered": len(changed)}


def review(build):
    from PIL import Image, ImageDraw, ImageFont

    timeline = json.loads((build / "timeline.json").read_text())
    manifest = json.loads((build / "scene_manifest.json").read_text())
    episode = manifest["episode"]
    report = {"duration": timeline["duration"], "frames": timeline["total_frames"], "files": {}}
    for filename in ("pilot.mp4", "pilot_clean.mp4"):
        result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json",
                                 str(build / filename)], check=True, capture_output=True, text=True)
        info = json.loads(result.stdout)
        video = next(stream for stream in info["streams"] if stream["codec_type"] == "video")
        audio = next(stream for stream in info["streams"] if stream["codec_type"] == "audio")
        if (video["width"], video["height"], video["pix_fmt"], video["codec_name"]) != (720, 1280, "yuv420p", "h264"):
            raise ValueError(f"{filename}: wrong export format.")
        if int(video["nb_frames"]) != timeline["total_frames"] or abs(float(video["duration"]) - timeline["duration"]) > 0.001:
            raise ValueError(f"{filename}: frame/duration mismatch.")
        if (audio["sample_rate"], audio["channels"], audio["codec_name"]) != ("48000", 1, "aac"):
            raise ValueError(f"{filename}: wrong audio format.")
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", str(build / filename),
                        "-f", "null", "-"], check=True)
        report["files"][filename] = {"sha256": sha256_file(build / filename), "decoded": True,
                                     "frames": int(video["nb_frames"])}
    low = []
    for turn in timeline["turns"]:
        validate_words(turn["words"], turn["text"], turn["wav_duration"])
        for word in turn["words"]:
            if word["score"] < 0.4:
                low.append({"turn": turn["id"], "word": word["word"], "confidence": word["score"],
                            "start": turn["start"] + word["start"], "end": turn["start"] + word["end"]})
    report["alignment_review"] = {"low_confidence_words_below_0_4": low,
                                  "note": "Measured model confidence, not a guarantee of perceptual accuracy.",
                                  "maximum_display_quantization_seconds": 0.005 + 1 / timeline["fps"]}
    if (build / "audio_reuse.json").is_file():
        reuse = json.loads((build / "audio_reuse.json").read_text())
        for name, digest in reuse["files_sha256"].items():
            if sha256_file(build / name) != digest or sha256_file(resolve_build_reference(reuse["source"]) / name) != digest:
                raise ValueError(f"Visual revision changed approved source audio/alignment: {name}")
        report["original_audio_and_alignment_unchanged"] = True
    if episode.get("subtitle_mode") == "readable":
        pages = caption_pages(episode, timeline)
        if (build / "captions.ass").read_text() != make_ass(episode, timeline):
            raise ValueError("Encoded caption source differs from the verified readable pages.")
        durations = [displayed_seconds(page["start"], page["end"], timeline["fps"]) for page in pages]
        rates = [len(page["text"]) / duration for page, duration in zip(pages, durations)]
        if min(durations) < MIN_PAGE_SECONDS or max(rates) > MAX_PAGE_CPS:
            raise ValueError("Encoded subtitle pages fail the reading-time limits.")
        report["subtitle_readability"] = {
            "pages": len(pages), "minimum_encoded_page_seconds": min(durations),
            "maximum_encoded_characters_per_second": max(rates),
            "policy_minimum_seconds": MIN_PAGE_SECONDS, "policy_maximum_characters_per_second": MAX_PAGE_CPS,
            "note": "Project reading policy, not an official exam/platform requirement. Word highlighting uses measured speech only.",
        }
        report["camera_review"] = review_cameras(build, timeline, manifest)
        if not manifest.get("derived_edit") and "camera_revision_from" in manifest:
            source = resolve_build_reference(manifest["camera_revision_from"]["source"])
            for name in ("dialogue.wav", "word_alignment.json"):
                if sha256_file(build / name) != sha256_file(source / name):
                    raise ValueError(f"Camera-only revision changed {name}.")
            report["original_audio_and_alignment_unchanged"] = True
    if episode.get("social_kind") == "promo":
        limits = promo_settings(episode)
        if not limits["min_seconds"] <= timeline["duration"] <= limits["max_seconds"]:
            raise ValueError("Promo is outside the configured duration bounds.")
        edit = json.loads((build / "scene_manifest.json").read_text())["derived_edit"]
        with wave.open(str(resolve_build_reference(edit["source"]) / "dialogue.wav"), "rb") as original:
            samples = original.getframerate() // timeline["fps"]
            original.setpos(edit["source_start_frame_zero_based"] * samples)
            expected = original.readframes((edit["source_stop_frame_exclusive"] -
                                            edit["source_start_frame_zero_based"]) * samples)
        with wave.open(str(build / "dialogue.wav"), "rb") as excerpt:
            lead = excerpt.readframes(edit["intro_hold_frames"] * samples)
            actual = excerpt.readframes(len(expected) // 2)
            tail = excerpt.readframes(edit["outro_hold_frames"] * samples)
            if any(lead) or actual != expected or any(tail):
                raise ValueError("Promo changed original speech samples or contains non-silent bookends.")
        report["exact_original_pcm_excerpt"] = True
        atomic_json(build / "word_alignment.json", {
            "provenance": timeline["word_alignment"], "turns": [
                {"id": turn["id"], "start": turn["start"], "words": turn["words"],
                 "alignment_key": turn["alignment_key"]} for turn in timeline["turns"]],
        })
    safe = json.loads((build / "safe_zone_report.json").read_text())
    if not safe["all_inside"] or safe.get("overlapping_text_states"):
        raise ValueError("Missing successful text-safe-area audit.")
    report["safe_area_states_checked"] = safe["states_checked"]
    if not (build / "publishing_caption.txt").is_file():
        raise ValueError("Missing required publishing attribution.")
    moments = [0.7, timeline["duration"] - 2]
    moments += [turn["start"] + min(1.3, turn["wav_duration"] / 2) for turn in timeline["turns"]]
    if episode.get("social_kind") not in ("exchange", "promo"):
        window = task_window(timeline)
        if window is not None:
            moments.append((window[0] + window[1]) / 2)
        moments.append(timeline["duration"] - episode["outro_seconds"] + 0.5)
    moments = sorted(set(round(t, 3) for t in moments if 0 <= t < timeline["duration"]))
    folder = build / "review"
    folder.mkdir(exist_ok=True)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    columns, thumb_w, thumb_h, label_h = 4, 270, 480, 32
    sheet = Image.new("RGB", (columns * thumb_w, ((len(moments) + columns - 1) // columns) * (thumb_h + label_h)), "#17231d")
    for index, t in enumerate(moments):
        path = folder / f"captioned_{index:02d}.png"
        frame_at(build, "pilot.mp4", t, path)
        with Image.open(path) as source:
            image = source.convert("RGB")
        draw = ImageDraw.Draw(image)
        draw.rectangle(SAFE, outline="#55ff88", width=3)
        x, y = (index % columns) * thumb_w, (index // columns) * (thumb_h + label_h)
        sheet.paste(image.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS), (x, y))
        ImageDraw.Draw(sheet).text((x + 8, y + thumb_h + 5), f"{t:.2f}s · safe-area review", font=font, fill="white")
    sheet.save(build / "contact_sheet.jpg", quality=92)
    # Full-size overlay makes UI exclusions visible without altering either master.
    mid = timeline["turns"][0]["start"] + min(1.3, timeline["turns"][0]["wav_duration"] / 2)
    frame_at(build, "pilot.mp4", mid, folder / "safe_base.png")
    with Image.open(folder / "safe_base.png") as source:
        overlay = source.convert("RGBA")
    mask = Image.new("RGBA", overlay.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(mask)
    for rectangle in ((0, 0, 720, SAFE[1] - 1), (0, SAFE[3], 720, 1280),
                      (0, SAFE[1], SAFE[0] - 1, SAFE[3]), (SAFE[2], SAFE[1], 720, SAFE[3])):
        draw.rectangle(rectangle, fill=(255, 45, 45, 100))
    overlay = Image.alpha_composite(overlay, mask)
    ImageDraw.Draw(overlay).rectangle(SAFE, outline="#55ff88", width=4)
    overlay.convert("RGB").save(build / "safe_zone_review.png")
    atomic_json(build / "delivery_checks.json", report)
    print(f"{build.name}: {timeline['duration']:.3f}s; {safe['states_checked']} caption states checked; both masters decode.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    review(resolve_build_reference(parser.parse_args().build))
