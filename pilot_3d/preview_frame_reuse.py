"""Verified turn-local native-frame reuse for B2 preview title/card revisions."""

import ast
import copy
import json
from pathlib import Path
import shutil

from prepare_audio import atomic_json, content_hash, sha256_file

REVISED_TURNS = {"opening", "prepare_teil1", "reading_summary", "prepare_teil3"}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def definitions(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    return {node.name: ast.dump(node, include_attributes=False)
            for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def source_spec(source, build, episode, storyboard):
    from long_speaking_preview import ROOT

    source, build = Path(source).resolve(strict=True), Path(build).resolve()
    if source == build or source.is_relative_to(build) or build.is_relative_to(source):
        raise ValueError("Frame reuse needs separate source and destination builds.")
    state = read(source / "preview_state.json")
    old = state["spec"]["episode"]
    if (episode.get("template") != "long_speaking_full_preview"
            or old.get("template") != "long_speaking_full_preview"
            or episode.get("exam", {}).get("level") != "B2"
            or old.get("exam") != episode.get("exam")
            or episode.get("output_formats") != ["youtube"]):
        raise ValueError("Partial frame reuse supports B2 YouTube previews only.")
    for key in ("scene", "render", "fps", "voices", "speech_tempo", "intro_seconds", "outro_seconds"):
        if old.get(key) != episode.get(key):
            raise ValueError(f"Frame reuse settings differ: {key}")
    prior = {t["id"]: t for t in old["turns"]}
    if list(prior) != [t["id"] for t in episode["turns"]]:
        raise ValueError("Frame reuse requires the same ordered turns.")
    for turn in episode["turns"]:
        before, after = copy.deepcopy(prior[turn["id"]]), copy.deepcopy(turn)
        if turn["id"] in REVISED_TURNS:
            for key in ("text", "display_text", "display_word_groups"):
                before.pop(key, None)
                after.pop(key, None)
        if before != after:
            raise ValueError(f"Only title/card wording may change: {turn['id']}")
    old_storyboard = read(source / "storyboard_episode.json")
    before, after = copy.deepcopy(old_storyboard), copy.deepcopy(storyboard)
    for value in (before, after):
        value.pop("title", None)
        value["opening"].pop("text", None)
    if before != after:
        raise ValueError("Frame reuse requires unchanged tasks, dialogue, room and promotion.")
    files = {"preview_state.json", "episode.json", "storyboard_episode.json",
             "native_plan.json", "native_checks.json", "timeline.json", "scene_checks.json"}
    for stage in ("audio", "alignment", "scene", "frames"):
        outputs = state["stages"].get(stage)
        if not outputs:
            raise ValueError(f"Source preview has no completed {stage} checkpoint.")
        for name, digest in outputs.items():
            path = source / name
            if not path.is_file() or sha256_file(path) != digest:
                raise ValueError(f"Source preview checkpoint changed: {name}")
            if not name.startswith("native/"):
                files.add(name)
    editorial = {"pipeline.py", "long_speaking_preview.py", "b2_speaking.py"}
    for name, digest in state["spec"]["code_sha256"].items():
        snapshot = source / "source_export" / name
        if sha256_file(snapshot) != digest:
            raise ValueError(f"Source code snapshot changed: {name}")
        if name == "long_speaking_preview_scene.py":
            before, after = definitions(snapshot), definitions(ROOT / name)
            compatible = all(before[key] == after.get(key)
                             for key in ("actors_from_scene", "roles", "render"))
        elif name == "b2_speaking.py":
            compatible = definitions(snapshot)["shared_head_fits"] == definitions(ROOT / name)["shared_head_fits"]
        else:
            compatible = name in editorial or sha256_file(ROOT / name) == digest
        if not compatible:
            raise ValueError(f"Native scene implementation changed: {name}")
        files.add(str(Path("source_export") / name))
    for name, digest in state["spec"]["asset_sha256"].items():
        if name in (old["storyboard"], str(Path(old["storyboard"]).with_name("oeif_b2_speaking_full_preview.json"))):
            continue
        if sha256_file(Path(name)) != digest:
            raise ValueError(f"Native source asset changed: {name}")
    return {"source": str(source),
            "files_sha256": {name: sha256_file(source / name) for name in sorted(files)},
            "policy": "Exact turn-local native PNG reuse; only opening/card wording may change."}


def audio_spec(source, build, episode):
    from long_speaking_preview import ROOT

    source, build = Path(source).resolve(strict=True), Path(build).resolve()
    if source == build or source.is_relative_to(build) or build.is_relative_to(source):
        raise ValueError("Audio checkpoint reuse needs separate builds.")
    state = read(source / "preview_state.json")
    if state["spec"]["episode"] != episode:
        raise ValueError("Preview audio checkpoint must match the exact resolved episode.")
    for name in ("prepare_audio.py", "align_words.py", "check_speech.py",
                 "episode_config.py", "episode_profiles.py"):
        if sha256_file(ROOT / name) != state["spec"]["code_sha256"][name]:
            raise ValueError(f"Audio checkpoint implementation changed: {name}")
    files = {"preview_state.json"}
    for stage in ("audio", "alignment", "speech_check"):
        outputs = state["stages"].get(stage)
        if not outputs:
            raise ValueError(f"Source audio checkpoint has no completed {stage} stage.")
        for name, digest in outputs.items():
            if sha256_file(source / name) != digest:
                raise ValueError(f"Audio checkpoint output changed: {name}")
            files.add(name)
    if read(source / "episode.json") != episode:
        raise ValueError("Prepared audio episode differs from resolved settings.")
    speech = read(source / "speech_asr_check.json")
    if (speech["episode_sha256"] != sha256_file(source / "episode.json")
            or speech["timeline_sha256"] != sha256_file(source / "timeline.json")):
        raise ValueError("Speech checkpoint does not describe the exact saved episode/timeline.")
    checks = {t["id"]: t for t in speech["turns"]}
    for turn in read(source / "timeline.json")["turns"]:
        check = checks.get(turn["id"], {})
        if (check.get("expected") != turn["text"]
                or check.get("audio_sha256") != sha256_file(Path(turn["audio"]))):
            raise ValueError(f"Checked speech PCM changed: {turn['id']}")
        files.add(str(Path(turn["audio"]).resolve()))
    return {"source": str(source),
            "files_sha256": {name: sha256_file(source / name) for name in sorted(files)},
            "policy": "Exact completed preview audio/alignment/ASR checkpoint, not production approval."}


def reuse_audio(build, spec):
    source = Path(spec["source"])
    for name in ("episode.json", "dialogue.wav", "audio_timeline.json", "subtitles.srt",
                 "timeline.json", "word_alignment.json", "speech_asr_check.json"):
        shutil.copy2(source / name, Path(build) / name)
    atomic_json(Path(build) / "preview_audio_reuse.json", spec)


def opening_bake_timeline(timeline, plan, reused):
    reused_files = {r["file"] for r in reused}
    missing = [p for p in plan if p["file"] not in reused_files]
    stop = timeline["turns"][1]["start_frame"]
    if (timeline["turns"][0]["id"] != "opening" or not missing
            or any(p["frame"] >= stop for p in missing)):
        raise ValueError("Partial scene bake requires only opening frames to be missing.")
    shortened = copy.deepcopy(timeline)
    shortened.update(turns=shortened["turns"][:1], total_frames=stop,
                     duration=stop / timeline["fps"], silent_notices=[],
                     partial_opening_bake=True)
    return shortened, missing


def frame_mapping(episode, timeline, plan, old_timeline, old_plan):
    old_turns = {t["id"]: t for t in old_timeline["turns"]}
    old_frames = {(p["format"], p["frame"]): p for p in old_plan}
    turns = timeline["turns"]
    reusable, mappings = {}, []
    for index, turn in enumerate(turns):
        if turn["id"] in REVISED_TURNS:
            continue
        old = old_turns[turn["id"]]
        for key in ("text", "speaker", "camera", "action", "look_at", "panel_id",
                    "wav_duration", "sample_count", "pause_after_frames", "mouth_cues"):
            if turn.get(key) != old.get(key):
                raise ValueError(f"Unchanged turn differs in {key}: {turn['id']}")
        if sha256_file(Path(turn["audio"])) != sha256_file(Path(old["audio"])):
            raise ValueError(f"Unchanged speech PCM differs: {turn['id']}")
        end = turns[index + 1]["start_frame"] if index + 1 < len(turns) else timeline["total_frames"]
        old_index = next(i for i, t in enumerate(old_timeline["turns"]) if t["id"] == turn["id"])
        old_end = (old_timeline["turns"][old_index + 1]["start_frame"]
                   if old_index + 1 < len(old_timeline["turns"]) else old_timeline["total_frames"])
        if end - turn["start_frame"] != old_end - old["start_frame"]:
            raise ValueError(f"Unchanged turn frame clock differs: {turn['id']}")
        reusable[turn["id"]] = (turn, old, end)
    index = 0
    for item in plan:
        while index + 1 < len(turns) and turns[index + 1]["start_frame"] <= item["frame"]:
            index += 1
        turn = turns[index]
        if turn["id"] not in reusable:
            continue
        old = reusable[turn["id"]][1]
        source_frame = old["start_frame"] + item["frame"] - turn["start_frame"]
        prior = old_frames.get((item["format"], source_frame))
        if prior is None or any(prior[k] != item[k] for k in ("camera", "size")):
            raise ValueError(f"No matching turn-local source frame: {turn['id']}")
        mappings.append({"target": item, "source_file": prior["file"], "turn_id": turn["id"],
                         "source_frame": source_frame})
    return mappings


def reuse_alignment(build, spec):
    from align_words import validate_words

    build, source = Path(build), Path(spec["source"])
    old_turns = {t["id"]: t for t in read(source / "timeline.json")["turns"]}
    cache = build / "alignment"
    cache.mkdir(exist_ok=True)
    count = 0
    timeline = read(build / "timeline.json")
    for turn in timeline["turns"]:
        old = old_turns[turn["id"]]
        if turn["id"] in REVISED_TURNS or turn["text"] != old["text"]:
            continue
        if sha256_file(Path(turn["audio"])) != sha256_file(Path(old["audio"])):
            raise ValueError(f"Unchanged alignment PCM differs: {turn['id']}")
        turn["mouth_cues"] = copy.deepcopy(old["mouth_cues"])
        name = f"{turn['id']}-{old['alignment_key'][:20]}.words.json"
        saved = read(source / "alignment" / name)
        if (saved["cache_key"] != old["alignment_key"]
                or content_hash(saved["payload"]) != old["alignment_key"]
                or saved["payload"]["text"] != turn["text"]
                or saved["payload"]["wav_sha256"] != sha256_file(Path(turn["audio"]))
                or saved["words"] != old["words"]):
            raise ValueError(f"Source alignment cache differs: {turn['id']}")
        validate_words(saved["words"], turn["text"], turn["wav_duration"])
        atomic_json(cache / name, saved)
        count += 1
    timeline["mouth_cue_reuse"] = {
        "source": str(source), "timeline_sha256": sha256_file(source / "timeline.json"),
        "turn_ids": [t["id"] for t in timeline["turns"] if t["id"] not in REVISED_TURNS],
        "policy": "Preserve original measured lip cues only after exact speech-text and PCM verification."}
    atomic_json(build / "timeline.json", timeline)
    print(f"Imported {count} verified unchanged alignment caches.", flush=True)


def reuse_frames(build, episode, timeline, plan, spec):
    from b2_speaking import shared_head_fits

    build, source = Path(build), Path(spec["source"])
    mappings = frame_mapping(episode, timeline, plan, read(source / "timeline.json"),
                             read(source / "native_plan.json"))
    receipts = {r["file"]: r for r in read(source / "native_checks.json")}
    reused = []
    for mapping in mappings:
        original = receipts[mapping["source_file"]]
        src, dst = source / mapping["source_file"], build / mapping["target"]["file"]
        if sha256_file(src) != original["sha256"]:
            raise ValueError(f"Reused native PNG changed: {src}")
        if not all(shared_head_fits(h) for h in original["head_bounds"]):
            raise ValueError("Reused frame fails shared portrait clearance.")
        dst.parent.mkdir(exist_ok=True)
        if not dst.exists() or sha256_file(dst) != original["sha256"]:
            shutil.copy2(src, dst)
        reused.append({**mapping["target"], "sha256": original["sha256"],
                       "head_bounds": original["head_bounds"], "reused_from": {
                           "build": str(source), "file": mapping["source_file"],
                           "frame": mapping["source_frame"], "turn_id": mapping["turn_id"]}})
    atomic_json(build / "reused_native_checks.json", reused)
    atomic_json(build / "preview_frame_reuse.json", {
        **spec, "reused_frames": len(reused), "new_frames": len(plan) - len(reused),
        "changed_turns": sorted(REVISED_TURNS),
        "note": "The scene is rebaked for revised speech; only missing native frames are rendered. "
                "Unchanged images retain their source pose, lip sync, framing and hash."})
    return reused
