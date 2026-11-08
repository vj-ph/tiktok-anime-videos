"""Create full and under-three-minute A2 portrait videos from production resources."""

import argparse
import copy
import json
from pathlib import Path
import shutil

from a2_speaking_preview import STATIC_PANELS, native_plan, overlay
from b2_speaking import shared_head_fits
from derive_long_speaking import link, splice_audio
from episode_config import check_timeline
from generation_runtime import generation_job
from long_speaking_preview import caption_preflight, encode, review_export
from prepare_audio import atomic_json, sha256_file, subtitles

ROOT = Path(__file__).resolve().parent
SHORT_TURNS = (1, 6, 7, 8, 9, 18, 19, 20, 21, 22, *range(24, 42), 52, 53, 54, 55)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def short_edit(timeline):
    selected, edits, cursor = [], [], 0
    ids = [f"a2_{number:02d}" for number in SHORT_TURNS]
    if not set(ids) <= {turn["id"] for turn in timeline["turns"]}:
        raise ValueError("The short A2 edit requires the complete reviewed speaking sequence.")
    for index, original in enumerate(timeline["turns"]):
        if original["id"] not in ids:
            continue
        first = original["start_frame"]
        last = (timeline["turns"][index + 1]["start_frame"]
                if index + 1 < len(timeline["turns"]) else timeline["total_frames"])
        if last < original["end_frame"] or first >= last:
            raise ValueError("A2 cuts must preserve complete speech and its following pause.")
        turn = copy.deepcopy(original)
        shift = cursor - first
        turn["source_start_frame"] = first
        for key in ("start_frame", "end_frame"):
            turn[key] += shift
        for key in ("start", "end"):
            turn[key] += shift / timeline["fps"]
        stop = cursor + last - first
        edits.append({"id": turn["id"], "source_start": first, "source_end": last,
                      "output_start": cursor, "output_end": stop})
        selected.append(turn)
        cursor = stop
    if ([turn["id"] for turn in selected] != ids or cursor >= 180 * timeline["fps"]
            or selected[0]["kind"] != "opening" or selected[-1]["kind"] != "cta"
            or {turn["part"] for turn in selected} != {0, 1, 2, 3}):
        raise ValueError("A2 short must retain opening, all speaking stages and CTA strictly below 180 seconds.")
    result = copy.deepcopy(timeline)
    result.update(turns=selected, total_frames=cursor, duration=cursor / timeline["fps"])
    result["edit_provenance"] = "Complete source turns and pauses; exact local words/lip cues, rebased starts."
    return result, edits


def verify_source(source):
    manifest = read(source / "export_manifest.json")
    for name, digest in manifest["files_sha256"].items():
        if sha256_file(source / name) != digest:
            raise ValueError(f"Production export changed: {name}")
    for name, digest in manifest["generation_source_sha256"].items():
        if (sha256_file(source / "source_export" / name) != digest
                or sha256_file(ROOT / name) != digest):
            raise ValueError(f"Production compositor/snapshot changed: {name}")
    episode = read(source / "episode.json")
    report = read(source / "delivery_checks.json")
    if (episode.get("template") != "a2_speaking_production"
            or report.get("status") != "production_verified" or "youtube" not in report["exports"]
            or episode["render"] != {
                "motion_step": 2, "native_scale": 1.0, "samples": 8, "native_source": "youtube"}):
        raise ValueError("Use the verified full A2 shared-frame YouTube production.")
    for name, digest in report["source_sha256"]["asset_sha256"].items():
        if sha256_file(Path(name)) != digest:
            raise ValueError(f"Production source asset changed: {name}")
    receipts, planned = read(source / "native_checks.json"), read(source / "native_plan.json")
    if [r["file"] for r in receipts] != [r["file"] for r in planned]:
        raise ValueError("Production native plan and receipts differ.")
    for receipt in receipts:
        if (sha256_file(source / receipt["file"]) != receipt["sha256"]
                or not receipt["head_bounds"]
                or not all(shared_head_fits(head) for head in receipt["head_bounds"])):
            raise ValueError(f"Native PNG/hash/portrait clearance failed: {receipt['file']}")
    check_timeline(episode, read(source / "timeline.json"))
    print(f"Verified {len(manifest['files_sha256'])} exports and {len(receipts)} native PNGs.", flush=True)
    return manifest, receipts


def prepare(source, output, short, receipts):
    episode, visual, timeline = (read(source / name) for name in
                                 ("episode.json", "storyboard_episode.json", "timeline.json"))
    episode["output_formats"] = ["social"]
    edits = None
    if short:
        timeline, edits = short_edit(timeline)
        episode["source"]["duration_limit_seconds"] = 180
        episode["turns"] = copy.deepcopy(timeline["turns"])
        visual["branding"] += " · Kurzfassung"
    check_timeline(episode, timeline)
    output.mkdir(parents=True)
    for name, value in (("episode.json", episode), ("storyboard_episode.json", visual),
                        ("timeline.json", timeline)):
        atomic_json(output / name, value)
    atomic_json(output / "word_alignment.json", {
        "provenance": timeline["word_alignment"],
        "turns": [{k: turn[k] for k in ("id", "start", "words", "alignment_key")}
                  for turn in timeline["turns"]],
    })
    if short:
        audio = splice_audio(source / "dialogue.wav", output / "dialogue.wav", edits, timeline["fps"])
        atomic_json(output / "edit_decisions.json", edits)
    else:
        shutil.copy2(source / "dialogue.wav", output / "dialogue.wav")
        audio = {"exact_complete_source_wav": sha256_file(output / "dialogue.wav")
                 == sha256_file(source / "dialogue.wav")}
    (output / "subtitles.srt").write_text(subtitles(timeline), encoding="utf-8")
    for name in ("speech_asr_check.json", "auditory_review_flags.json"):
        shutil.copy2(source / name, output / ("source_" + name))
    shutil.copy2(source / "CREDITS.txt", output / "CREDITS.txt")
    lookup = {r["file"]: r for r in receipts}
    turns = {t["id"]: t for t in timeline["turns"]}
    mappings = []
    for item in native_plan(episode, timeline):
        turn = next(t for t in reversed(list(turns.values())) if t["start_frame"] <= item["frame"])
        original = turn.get("source_start_frame", turn["start_frame"]) + item["frame"] - turn["start_frame"]
        name = str(Path("native") / f"youtube_{original:05d}.png")
        # Production manifests use portable relative path strings.
        receipt = lookup[name.replace("\\", "/")]
        link(source / name, output / item["file"])
        mappings.append({**item, "source_file": name, "sha256": receipt["sha256"],
                         "head_bounds": receipt["head_bounds"]})
    atomic_json(output / "native_reuse.json", mappings)
    return episode, visual, timeline, audio


@generation_job
def build(source, destination):
    source, destination = source.resolve(strict=True), destination.resolve()
    if destination.exists() or source == destination or source in destination.parents:
        raise ValueError("Use a fresh derivative directory separate from the production.")
    manifest, receipts = verify_source(source)
    original_manifest = sha256_file(source / "export_manifest.json")
    destination.mkdir(parents=True)
    atomic_json(destination / "source_verification.json", {
        "source": str(source), "manifest_sha256": original_manifest,
        "verified_exports": len(manifest["files_sha256"]), "verified_native_PNGs": len(receipts),
    })
    for short, folder in ((False, "full_social"), (True, "social_under3")):
        output = destination / folder
        episode, visual, timeline, audio = prepare(source, output, short, receipts)
        print(f"{folder}: {timeline['total_frames']} frames / {timeline['duration']:.3f}s", flush=True)
        caption_preflight(output, episode, visual, timeline, overlay_fn=overlay)
        encode(output, episode, visual, timeline, "social", overlay_fn=overlay, static_panels=STATIC_PANELS)
        report = review_export(output, episode, visual, timeline, "social", overlay_fn=overlay)
        atomic_json(output / "delivery_checks.json", {
            "status": "production_derivative", "exports": {"social": report},
            "source": str(source), "source_manifest_sha256": original_manifest,
            "audio_verification": audio, "shortened_example": short,
            "new_native_rendering": False, "new_speech_or_alignment": False,
            "human_listening_performed": False, "publication_approved": False,
            "inherited_flags": "source_speech_asr_check.json and source_auditory_review_flags.json retain original source times.",
        })
        for mapping in read(output / "native_reuse.json"):
            if sha256_file(output / mapping["file"]) != mapping["sha256"]:
                raise ValueError("Reused native PNG changed during composition.")
        snapshot = output / "derivative_sources"
        snapshot.mkdir()
        for script in ("derive_a2_speaking.py", "derive_long_speaking.py"):
            shutil.copy2(ROOT / script, snapshot / script)
        atomic_json(output / "export_manifest.json", {
            "files_sha256": {str(p.relative_to(output)): sha256_file(p) for p in output.rglob("*")
                             if p.is_file() and "native" not in p.relative_to(output).parts
                             and p.name != "export_manifest.json"},
            "source_manifest_sha256": original_manifest,
        })
        print(f"Ready: {output / 'production_social.mp4'}", flush=True)
    for name, digest in manifest["files_sha256"].items():
        if sha256_file(source / name) != digest:
            raise ValueError(f"Original production export changed: {name}")
    if sha256_file(source / "export_manifest.json") != original_manifest:
        raise ValueError("Original production manifest changed.")
    atomic_json(destination / "source_preservation.json", {"original_exports_and_manifest_unchanged": True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--build", required=True, type=Path)
    args = parser.parse_args()
    build(args.source, args.build)
