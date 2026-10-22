"""Episode content, asset resolution and the supported exam-room template contract."""

import copy
import json
from pathlib import Path

from build_paths import resolve_build_reference
from prepare_audio import SAFE_ID, ceil_frames, inspect_wav, nonempty, number, validate_episode
from scene_direction import GESTURE_LIMITS
from picture_presentation import PICTURE_CAMERAS, validate_pictures

CAMERA_PREFIXES = {"wide": "01", "examiner": "02", "candidates": "03",
                   "candidate_a": "04", "candidate_b": "05", "picture_a": "06", "picture_b": "07"}
ACTORS = ("candidate_a", "candidate_b", "examiner", "observer")
PROFILES = {
    "preview": {"width": 360, "height": 640, "samples": 2, "motion_step": 2},
    "production": {"width": 720, "height": 1280, "samples": 16, "motion_step": 1},
}


def read_episode(path):
    path = resolve_build_reference(path).resolve(strict=True)
    episode = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(episode, dict):
        raise ValueError("Episode must be a JSON object.")
    if "schema_version" in episode:
        if type(episode["schema_version"]) is not int or episode["schema_version"] != 1:
            raise ValueError("Unsupported schema_version; expected 1.")
        episode = copy.deepcopy(episode)
        voices = episode.get("voices", {})
        if not isinstance(voices, dict):
            raise ValueError("voices must be an object.")
        for voice in voices.values():
            for field in ("audio", "transcript"):
                if isinstance(voice, dict) and isinstance(voice.get(field), str):
                    voice[field] = str((path.parent / voice[field]).resolve())
        if isinstance(episode.get("book_cover"), str):
            episode["book_cover"] = str((path.parent / episode["book_cover"]).resolve())
        if isinstance(episode.get("pictures"), dict):
            for picture in episode["pictures"].values():
                if isinstance(picture, dict) and isinstance(picture.get("path"), str):
                    picture["path"] = str((path.parent / picture["path"]).resolve())
        scene = episode.get("scene", {})
        if isinstance(scene, dict) and isinstance(scene.get("base_scene"), str):
            scene["base_scene"] = str((path.parent / scene["base_scene"]).resolve())
        if isinstance(scene, dict) and isinstance(scene.get("wall_logo"), str):
            scene["wall_logo"] = str((path.parent / scene["wall_logo"]).resolve())
    return episode


def turn_phase(turn):
    return turn.get("phase", {"welcome": "welcome", "explain": "instruction"}.get(turn.get("action"), "dialogue"))


def instruction_turn(turns):
    return next((turn for turn in turns if turn_phase(turn) == "instruction"), None)


def section_windows(episode, timeline):
    """Exam task labels are independent of entrance/instruction/dialogue blocking."""
    default = episode.get("header", {}).get("topic", episode.get("title", ""))
    labels = episode.get("sections", {})
    changes = [{"start": 0.0, "section": None, "label": default}]
    events = [(turn["start"], turn.get("section")) for turn in timeline["turns"]]
    events.append((timeline["duration"] - episode.get("outro_seconds", 0), None))
    for start, section in events:
        if start >= timeline["duration"] or section == changes[-1]["section"]:
            continue
        event = {"start": start, "section": section,
                 "label": labels[section] if section is not None else default}
        if start == changes[-1]["start"]:
            changes[-1] = event
        else:
            changes.append(event)
    return [{**event, "end": changes[index + 1]["start"] if index + 1 < len(changes)
             else timeline["duration"]} for index, event in enumerate(changes)]


def task_window(timeline):
    instruction = instruction_turn(timeline["turns"])
    if instruction is None:
        return None
    following = next((turn for turn in timeline["turns"]
                      if turn["start"] >= instruction["end"] and turn_phase(turn) == "dialogue"), None)
    if following is None or following["start"] <= instruction["end"]:
        return None
    delay = ceil_frames(instruction.get("task_card_delay_seconds", 0), timeline["fps"])
    start = instruction["end"] + delay / timeline["fps"]
    if start >= following["start"]:
        raise ValueError("task_card_delay_seconds leaves no task-card reading time.")
    return start, following["start"]


def entrance_enabled(episode):
    return episode.get("scene", {}).get("entrance", any(turn_phase(t) == "welcome" for t in episode["turns"]))


def seating_deadline(episode, timeline):
    if not entrance_enabled(episode):
        return 0.0
    following = next((turn for turn in timeline["turns"] if turn_phase(turn) != "welcome"), None)
    if following is None:
        raise ValueError("Entrance requires a turn after the welcome.")
    return following["start"]


def takeaway_seconds(episode):
    if episode.get("social_kind") in ("exchange", "promo") or not episode.get("takeaway"):
        return 0.0
    return episode.get("takeaway_seconds", 4.0)


def promo_settings(episode):
    return {"intro_seconds": 2.5, "outro_seconds": 6.0, "min_seconds": 30.0,
            "max_seconds": 45.0, **episode.get("promo", {})}


def validate_template(episode, *, check_assets=False):
    validate_episode(episode)
    if episode.get("language", "de") != "de":
        raise ValueError("This voice/alignment pipeline currently supports German (language=de).")
    for field in ("id", "title", "label", "branding", "disclaimer"):
        nonempty(episode.get(field), field)
    if not SAFE_ID.fullmatch(episode["id"]):
        raise ValueError("id must be a safe filename identifier.")
    if episode.get("presentation") != "social" or episode.get("social_kind") in ("exchange", "promo"):
        raise ValueError("The episode builder requires a full social episode; promo is a derived output.")
    if episode.get("credit_policy") != "publishing_caption":
        raise ValueError("credit_policy must be publishing_caption; posting attribution remains required.")
    if episode.get("subtitle_mode") != "readable":
        raise ValueError("subtitle_mode must be readable.")
    if "exam_part" in episode and (type(episode["exam_part"]) is not int
                                  or episode["exam_part"] not in (1, 2, 3)):
        raise ValueError("exam_part must be 1, 2 or 3.")
    sections = episode.get("sections", {})
    if not isinstance(sections, dict):
        raise ValueError("sections must be an object of section IDs and header labels.")
    for section, label in sections.items():
        if not isinstance(section, str) or not SAFE_ID.fullmatch(section):
            raise ValueError("Section IDs must be safe filename identifiers.")
        nonempty(label, f"sections.{section}")
    scene = episode.get("scene", {})
    if not isinstance(scene, dict) or scene.get("template", "exam_room") != "exam_room":
        raise ValueError("Only the exam_room scene template is currently supported.")
    if "entrance" in scene and type(scene["entrance"]) is not bool:
        raise ValueError("scene.entrance must be a boolean.")
    nonempty(scene.get("base_scene"), "scene.base_scene")
    if "wall_logo" in scene:
        nonempty(scene["wall_logo"], "scene.wall_logo")
    if set(episode["voices"]) - {"candidate_a", "candidate_b", "examiner"}:
        raise ValueError("exam_room supports candidate_a, candidate_b and examiner voice slots.")
    for turn in episode["turns"]:
        role, camera = turn["speaker"], turn.get("camera")
        allowed = {"wide", role} | ({"candidates"} if role.startswith("candidate") else set())
        if role in PICTURE_CAMERAS:
            allowed.add(PICTURE_CAMERAS[role])
        if camera not in allowed:
            raise ValueError(f"Turn {turn['id']}: camera must include its speaker; allowed: {sorted(allowed)}.")
        if turn.get("action") not in GESTURE_LIMITS:
            raise ValueError(f"Turn {turn['id']}: unsupported acting action.")
        if "section" in turn and (not isinstance(turn["section"], str) or turn["section"] not in sections):
            raise ValueError(f"Turn {turn['id']}: section must name a declared section ID.")
        if turn_phase(turn) not in ("welcome", "instruction", "dialogue"):
            raise ValueError(f"Turn {turn['id']}: unknown phase.")
        if turn.get("look_at") not in ACTORS:
            raise ValueError(f"Turn {turn['id']}: look_at must name an exam_room actor slot.")
        if "task_card_delay_seconds" in turn:
            delay = number(turn["task_card_delay_seconds"], f"turn {turn['id']}.task_card_delay_seconds")
            if turn_phase(turn) != "instruction" or not episode.get("task_card"):
                raise ValueError("task_card_delay_seconds requires an instruction turn with a task_card.")
            if ceil_frames(delay, episode["fps"]) >= ceil_frames(turn["pause_after"], episode["fps"]):
                raise ValueError("task_card_delay_seconds must leave positive task-card reading time "
                                 "within the instruction pause_after.")
    phases = [turn_phase(turn) for turn in episode["turns"]]
    if "dialogue" not in phases or phases.count("instruction") > 1:
        raise ValueError("An episode needs dialogue and at most one instruction phase.")
    if phases != sorted(phases, key={"welcome": 0, "instruction": 1, "dialogue": 2}.get):
        raise ValueError("Phases must run in order: welcome, instruction, dialogue.")
    if entrance_enabled(episode) and "welcome" not in phases:
        raise ValueError("scene.entrance=true requires a welcome phase.")
    validate_pictures(episode, check_assets=check_assets)
    header = episode.get("header", {})
    if not isinstance(header, dict):
        raise ValueError("header must be an object.")
    for field in ("brand", "topic"):
        nonempty(header.get(field), f"header.{field}")
    nonempty(episode.get("hook"), "hook")
    for field, limit in (("task_card", 6), ("takeaway", 3), ("cta", 3)):
        values = episode.get(field, [])
        if not isinstance(values, list) or len(values) > limit:
            raise ValueError(f"{field} must be an array of at most {limit} strings for this layout.")
        for value in values:
            nonempty(value, field)
    if episode.get("task_card"):
        instruction = instruction_turn(episode["turns"])
        if instruction is None or instruction["pause_after"] <= 0:
            raise ValueError("task_card requires an instruction phase with a positive pause_after.")
        for field in ("task_title", "task_summary", "task_hint"):
            nonempty(episode.get(field), field)
    if episode.get("takeaway"):
        nonempty(episode.get("takeaway_title"), "takeaway_title")
        if not 0 < number(episode.get("takeaway_seconds"), "takeaway_seconds") < episode["outro_seconds"]:
            raise ValueError("takeaway_seconds must leave a positive CTA duration within outro_seconds.")
    if episode["outro_seconds"] > 0:
        nonempty(episode.get("book_cover"), "book_cover")
        if not episode.get("cta"):
            raise ValueError("A positive outro_seconds requires CTA text.")
    publication = episode.get("publication", {})
    if not isinstance(publication, dict):
        raise ValueError("publication must be an object.")
    for field in ("intro", "disclosure"):
        nonempty(publication.get(field), f"publication.{field}")
    tags = publication.get("hashtags", [])
    if not isinstance(tags, list) or any(not isinstance(t, str) or not t.startswith("#") or " " in t for t in tags):
        raise ValueError("publication.hashtags must contain hashtag strings without spaces.")
    if "promo" in episode and not isinstance(episode["promo"], dict):
        raise ValueError("promo must be an object.")
    promo = promo_settings(episode)
    for field in ("intro_seconds", "outro_seconds", "min_seconds", "max_seconds"):
        number(promo[field], f"promo.{field}", positive=field in ("min_seconds", "max_seconds"))
    if promo["min_seconds"] > promo["max_seconds"]:
        raise ValueError("promo.min_seconds cannot exceed promo.max_seconds.")
    if promo["intro_seconds"] + promo["outro_seconds"] >= promo["max_seconds"]:
        raise ValueError("Promo bookends leave no time for speech.")
    if "hook" in promo:
        nonempty(promo["hook"], "promo.hook")
    if "turn_ids" in promo:
        ids = promo["turn_ids"]
        if not isinstance(ids, list) or not ids or any(
                not isinstance(value, str) or value not in {t["id"] for t in episode["turns"]} for value in ids) or len(set(ids)) != len(ids):
            raise ValueError("promo.turn_ids must be a nonempty list of unique existing turn IDs.")
        indexes = [next(i for i, turn in enumerate(episode["turns"]) if turn["id"] == value) for value in ids]
        if indexes != list(range(indexes[0], indexes[-1] + 1)):
            raise ValueError("promo.turn_ids must be consecutive and in screenplay order.")
        if any(turn_phase(episode["turns"][i]) != "dialogue" for i in indexes):
            raise ValueError("Promo selection must contain dialogue, not the welcome/task card.")
    if check_assets:
        if not resolve_build_reference(scene["base_scene"]).is_file():
            raise FileNotFoundError(f"Base scene not found: {scene['base_scene']}")
        if "wall_logo" in scene and not Path(scene["wall_logo"]).is_file():
            raise FileNotFoundError(f"Wall logo not found: {scene['wall_logo']}")
        for role, voice in episode["voices"].items():
            inspect_wav(Path(voice["audio"]))
            nonempty(Path(voice["transcript"]).read_text(encoding="utf-8"), f"{role} reference transcript")
        if episode["outro_seconds"] > 0 and not Path(episode["book_cover"]).is_file():
            raise FileNotFoundError(f"Book cover not found: {episode['book_cover']}")


def check_timeline(episode, timeline):
    if timeline["fps"] != episode["fps"] or len(timeline["turns"]) != len(episode["turns"]):
        raise ValueError("Episode and prepared timeline differ; regenerate audio.")
    for expected, actual in zip(episode["turns"], timeline["turns"]):
        if any(actual.get(key) != value for key, value in expected.items()):
            raise ValueError(f"Turn {expected['id']}: episode and prepared timeline differ; regenerate audio.")
    from entrance import entrance_plan
    entrance_plan(episode, timeline)
    if episode.get("task_card") and task_window(timeline) is None:
        raise ValueError("Task card has no pause between instruction and dialogue.")
