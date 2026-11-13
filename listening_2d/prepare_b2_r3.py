"""Reuse verified B2 speech for in-place, two-page answer reveals."""

import argparse
import copy
from pathlib import Path
import shutil

from prepare_b2 import approved_episode, plan as original_plan, read, schedule
from prepare_sample import ROOT, atomic_json, mix_events, sha256_file, write_wav
from validate_b2 import verify_files

SOURCE = ROOT / "builds" / "oeif_b2_listening_full_production_r2"


def plan(episode):
    result = original_plan(episode)
    index = next(i for i, e in enumerate(result["events"])
                 if e["id"] == "b2_p2_learning_reveal")
    first = result["events"][index]
    first["reveal_group"] = 1
    second = copy.deepcopy(first)
    second.update(id=first["id"] + "_page2", reveal_group=2)
    result["events"].insert(index + 1, second)
    return result


def verify_source():
    manifest = read(SOURCE / "delivery_manifest.json")
    audit = read(SOURCE / "delivery_audit.json")
    assert audit["manifest_sha256"] == sha256_file(SOURCE / "delivery_manifest.json")
    verify_files({str(SOURCE / name): digest for name, digest in manifest["files"].items()})
    verify_files(manifest["code_inputs"])
    verify_files(manifest["inputs"]["files"])
    verify_files(manifest["inputs"]["book"])
    verify_files(read(SOURCE / "research_input_pin.json")["files"])
    return manifest


def prepare(build):
    if build.exists():
        raise ValueError("Use a fresh B2 revision build.")
    source_manifest = verify_source()
    episode = approved_episode()
    assert episode == read(SOURCE / "sample_content.json")["episode"]
    speech_plan = plan(episode)
    measured = read(SOURCE / "audio_manifest.json")
    timeline = schedule(speech_plan["events"], measured)
    previous = read(SOURCE / "timeline.json")
    old_turns = {t["id"]: t for t in previous["turns"]}
    aligned = []
    for turn in timeline["turns"]:
        old = old_turns[turn["id"]]
        assert all(turn[k] == old[k] for k in ("text", "speaker", "sha256", "audio"))
        if "words" in old:
            turn.update(words=copy.deepcopy(old["words"]), alignment_key=old["alignment_key"])
            aligned.append({k: turn[k] for k in ("id", "start", "words", "alignment_key")})
    timeline["word_alignment"] = previous["word_alignment"]
    timeline["reveal_revision"] = "Inline markings; Teil 2 two consecutive three-second groups."
    assert timeline["total_frames"] == previous["total_frames"] + 72
    build.mkdir(parents=True)
    for name in ("sample_content.json", "voice_references.json", "research_input_pin.json",
                 "audio_review_resolution.json", "speech_review_small.json",
                 "speech_review_medium.json"):
        shutil.copyfile(SOURCE / name, build / name)
    pins = copy.deepcopy(source_manifest["inputs"])
    pins["files"].update({str(SOURCE / name): sha256_file(SOURCE / name) for name in (
        "delivery_manifest.json", "delivery_audit.json", "timeline.json", "audio_manifest.json",
        "word_alignment.json", "audio_review_resolution.json", "audio_review_binding.json",
        "speech_review_small.json", "speech_review_medium.json")})
    pins["files"][str(Path(__file__).resolve())] = sha256_file(Path(__file__))
    atomic_json(build / "input_pin.json", pins)
    atomic_json(build / "revision_authorization.json", {
        "date": "2026-11-13", "request": "now let's regenerated the improved video",
        "source": str(SOURCE), "source_manifest_sha256": sha256_file(SOURCE / "delivery_manifest.json"),
        "scope": "Both full ratios; inline true/false markings, no separate solution-only slide.",
        "teil_2": "Three seconds for 46-50, then three seconds for 51-55 in both ratios; portrait changes page, landscape retains all statements and earlier markings.",
        "other_reveals": "Three seconds each; no exercise pause, speech, chime tail or final overview shortened.",
        "audio": "All 47 speech WAVs and measured local word intervals reused without synthesis or tempo processing. One existing remove cue added at second reveal page.",
        "review": "Original script review and ASR notes inherited unchanged; no new human listening.",
        "publication": "Nothing uploaded."
    })
    atomic_json(build / "speech_plan.json", speech_plan)
    atomic_json(build / "audio_manifest.json", measured)
    atomic_json(build / "timeline.json", timeline)
    atomic_json(build / "word_alignment.json", {
        "provenance": timeline["word_alignment"],
        "scope": "Verified source word intervals, rescheduled after the extra reveal phase.",
        "turns": aligned
    })
    atomic_json(build / "source_preservation.json", {
        "source": str(SOURCE), "manifest_sha256": sha256_file(SOURCE / "delivery_manifest.json"),
        "files": {str(SOURCE / name): digest for name, digest in source_manifest["files"].items()},
        "code_inputs": source_manifest["code_inputs"]
    })
    write_wav(build / "dialogue.wav", mix_events(timeline["events"]))
    print(f"B2 r3 reused 47 speech clips: {timeline['total_frames']} frames / "
          f"{timeline['duration']:.3f}s.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    prepare(parser.parse_args().build.resolve())
