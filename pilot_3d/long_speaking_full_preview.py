"""Resolve the approved complete speaking script without weakening short previews."""

import copy
import json
from pathlib import Path
import re

from prepare_audio import sha256_file


def pronunciation(display):
    display = display.replace(" - ", ", ")
    spoken, groups = [], []
    replacements = {"28": "achtundzwanzig", "25": "fünfundzwanzig", "18": "achtzehn",
                    "18:15": "achtzehn Uhr fünfzehn", "8": "acht", "+": "plus",
                    "ÖIF-B1-Buch": "Ö I F B eins Buch"}
    for token in display.split():
        match = re.fullmatch(r'(.+?)([.,!?;:]?)', token)
        word, punctuation = match.groups()
        phrase = replacements.get(word, word)
        if any(c.isdigit() for c in phrase):
            raise ValueError(f"Unmapped spoken number/abbreviation: {token}")
        tokens = (phrase + punctuation).split()
        groups.append(list(range(len(spoken), len(spoken) + len(tokens))))
        spoken.extend(tokens)
    return display, " ".join(spoken), groups


def resolve_full_episode(episode, path):
    episode = copy.deepcopy(episode)
    if (episode["source"].get("duration_limit_seconds") != 900
            or not episode["source"].get("duration_exception")):
        raise ValueError("Full preview requires the explicit long-form authorization and bounded 900-second ceiling.")
    for field in ("review_script", "review_manifest", "storyboard"):
        episode[field] = str((path.parent / episode[field]).resolve(strict=True))
    script_path = Path(episode["review_script"])
    if sha256_file(script_path) != episode["review_script_sha256"]:
        raise ValueError("Approved full-review text changed; use a new reviewed configuration.")
    manifest_path = Path(episode["review_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["files_sha256"].get(script_path.name) != episode["review_script_sha256"]:
        raise ValueError("The approved review manifest and script differ.")
    for name in ("script.json", "teil1_revision.json"):
        if sha256_file(manifest_path.parent / name) != manifest["files_sha256"][name]:
            raise ValueError(f"Approved full-review input changed: {name}")
    script = json.loads(script_path.read_text(encoding="utf-8"))
    if episode["title"] != script["turns"][0]["text"]:
        raise ValueError("Full preview title differs from its approved script.")
    episode["voices"] = script["voices"]
    episode["review_part1"] = json.loads(
        (manifest_path.parent / "teil1_revision.json").read_text(encoding="utf-8"))
    turns = []
    for source in script["turns"]:
        turn = {key: copy.deepcopy(source[key]) for key in ("id", "speaker", "name", "kind", "text")}
        part, role = source.get("part", 0), source["speaker"]
        turn.update(part=part, reviewed_text=source["text"],
                    adaptation=source.get("adaptation", "Approved authored full-review speech."),
                    review_turn_id=source["id"], pause_after=.6)
        if turn["kind"] == "opening":
            turn.update(text=source["text_tts"], display_text=source["text"],
                        display_word_groups=source["display_word_groups"],
                        panel_id="01_opening", camera="wide", action="explain", look_at="candidate_b")
        else:
            display, spoken, groups = pronunciation(source["text"])
            turn.update(text=spoken, display_text=display, display_word_groups=groups)
            if turn["kind"] == "cta":
                turn.update(panel_id="12_final_cta", camera="wide", action="explain",
                            look_at="candidate_a", pause_after=0)
            elif turn["kind"] == "instruction":
                turn.update(kind="task", panel_id={1: "02_teil1_task", 2: "05_teil2_picture",
                                                   3: "08_teil3_task"}[part],
                            camera="wide" if part != 3 else "candidates", action="ask",
                            look_at="candidate_b" if part == 1 else "candidate_a", pause_after=1.2)
            elif role == "examiner":
                next_turn = script["turns"][source["sequence"]]
                target = next_turn["speaker"]
                turn.update(panel_id="04_teil1_followup" if part == 1 else "07_teil2_followup",
                            camera="examiner", action="ask", look_at=target,
                            heading=f"Prüfer · Frage an {next_turn['name']}")
            else:
                turn.update(panel_id=("03_teil1_model" if part == 1 else "06_teil2_model" if part == 2
                                      else "09_teil3_lea" if role == "candidate_a" else "10_teil3_samir"),
                            camera=role, action="introduce" if part == 1 else "describe" if part == 2 else "propose",
                            look_at="examiner" if part != 3 else "candidate_b" if role == "candidate_a" else "candidate_a",
                            heading=f"{source['name']} · " + ("Vorstellung" if source["id"].endswith("_introduction")
                                                           else "Antwort" if part in (1, 2) else "Gemeinsam planen"))
        if "source_track" in source:
            turn["source_segment"] = source["id"]
        turns.append(turn)
    episode["turns"] = turns
    return episode
