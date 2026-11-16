"""Book-bound content for the individual fide A2-B1 speaking simulation."""

import json
from pathlib import Path
import re

from episode_config import read_episode
from prepare_audio import atomic_json, atomic_text, inspect_wav, sha256_file, validate_episode

ROOT = Path(__file__).resolve().parent
SECTIONS = {
    "opening": "fide-test A2-B1 Sprechen Prüfungssimulation",
    "welcome": "Willkommen · Lea und die Prüfenden",
    "a2_picture": "A2 · Aufgabe 1 · Situationsbeschreibung",
    "a2_phone": "A2 · Aufgabe 2 · Telefonat",
    "a2_conversation": "A2 · Aufgabe 3 · Persönliches Gespräch",
    "routing": "Nach A2 · Welches Niveau möchten Sie versuchen?",
    "b1_choice": "B1 · Wählen Sie ein Thema",
    "b1_experience": "B1 · Wohnen · Eine Erfahrung schildern",
    "b1_process": "B1 · Wohnen · Einen Ablauf erklären",
    "b1_aspects": "B1 · Wohnen · Vor- und Nachteile",
    "b1_hypothesis": "B1 · Wohnen · Was wäre, wenn …?",
    "closing": "Vielen Dank, Lea!",
    "cta": "Weiter üben mit Deutsch Kompass",
}
TRACKS = (
    "fide_a2_037_picture", "fide_a2_038_roleplay", "fide_a2_039_conversation",
    "fide_b1_002_answer", "fide_b1_003_answer", "fide_b1_004_answer",
    "fide_b1_005_answer", "fide_b1_006_followups",
)


def pronunciation(display, *, opening=False):
    replacements = {"fide-test": "fide Test", "A1": "A eins", "A2": "A zwei", "B1": "B eins",
                    "A1-A2": "A eins A zwei", "A2-B1": "A zwei B eins", "SBB": "S B B"}
    spoken, groups = [], []
    for token in display.split():
        word, punctuation = re.fullmatch(r"(.+?)([.,!?;:]?)", token).groups()
        phrase = replacements.get(word, word)
        if any(c.isdigit() for c in phrase):
            raise ValueError(f"Unmapped fide spoken number: {token}")
        words = (phrase + punctuation).split()
        groups.append(list(range(len(spoken), len(spoken) + len(words))))
        spoken.extend(words)
    if opening and not spoken[-1].endswith((".", "!", "?")):
        spoken[-1] += "."
    return " ".join(spoken), groups


def compile_turns(blocks, tracks, selection=None):
    if selection is None:
        expected = {segment["segment_id"] for track in tracks.values() for segment in track["segments"]}
    else:
        if set(selection) != set(tracks):
            raise ValueError("Explicit source selection must account for every selected track.")
        expected = set()
        for key, indexes in selection.items():
            if (not isinstance(indexes, list) or len(set(indexes)) != len(indexes)
                    or any(type(i) is not int or not 0 <= i < len(tracks[key]["segments"]) for i in indexes)):
                raise ValueError(f"Invalid source selection for {key}")
            expected.update(tracks[key]["segments"][i]["segment_id"] for i in indexes)
    turns = []
    for block in blocks:
        section = block["section"]
        if section not in SECTIONS:
            raise ValueError(f"Unknown fide section: {section}")
        if "track" in block:
            track = tracks[block["track"]]
            selections = block.get("segments", range(len(track["segments"])))
            material = [
                {"speaker": "candidate_a" if track["model_kind"] == "picture" or
                 segment["speaker_label"] == "Kandidat/in" else "examiner",
                 "text": segment["text_original"], "source_track": track["track_id"],
                 "source_segment": segment["segment_id"], "source_text": segment["text_original"]}
                for segment in [track["segments"][i] for i in selections]
            ]
        else:
            material = [block]
        for item in material:
            speaker = item["speaker"]
            kind = block.get("kind", "question" if speaker == "examiner" else "model")
            spoken, groups = pronunciation(item["text"], opening=kind == "opening")
            turns.append({
                "id": f"fide_{len(turns) + 1:02d}", "speaker": speaker,
                "name": "Lea" if speaker == "candidate_a" else "Herr Wagner",
                "text": spoken, "display_text": item["text"], "display_word_groups": groups,
                "kind": kind, "section": section, "heading": SECTIONS[section],
                "part": 0 if section in ("opening", "welcome", "cta", "closing") else
                        1 if section.startswith("a2") else 2 if section == "routing" else 3,
                "panel_id": section, "camera": "wide" if section in ("opening", "welcome", "closing") else speaker,
                "action": "explain" if kind in ("instruction", "opening", "cta") else
                          "ask" if speaker == "examiner" else "answer",
                "look_at": "examiner" if speaker == "candidate_a" else "candidate_a",
                "pause_after": 0 if kind == "cta" else 1.0 if kind == "instruction" else 0.6,
                **{k: item[k] for k in ("source_track", "source_segment", "source_text") if k in item},
                **({"adaptation": "Original simulation framing or follow-up."} if "source_track" not in item else {}),
            })
    actual = [turn["source_segment"] for turn in turns if "source_segment" in turn]
    if len(actual) != len(expected) or len(set(actual)) != len(actual) or set(actual) != expected:
        raise ValueError("Every explicitly selected book segment must occur exactly once.")
    return turns


def load_episode(path, profile="preview"):
    path = Path(path).resolve(strict=True)
    episode = read_episode(path)
    production = episode.get("template") == "fide_speaking_production"
    if production != (profile == "production") or profile not in ("preview", "production"):
        raise ValueError("Use the fide production template with --profile production.")
    expected_render = ({"motion_step": 2, "native_scale": 1.0, "samples": 8, "native_source": "youtube"}
                       if production else {"motion_step": 3, "native_scale": .25, "samples": 2})
    if (episode.get("template") not in ("fide_speaking_full_preview", "fide_speaking_production")
            or episode.get("exam") != {"family": "fide", "level": "A2-B1", "skill": "speaking", "section": "all"}
            or episode.get("fps") != 24 or episode.get("intro_seconds") != 0
            or episode.get("render") != expected_render
            or episode.get("source", {}).get("duration_limit_seconds") != 900
            or not episode["source"].get("duration_exception")
            or episode.get("scene", {}).get("layout") != "interview"
            or episode["scene"].get("observer") is not True
            or episode["scene"].get("entrance") is not False):
        raise ValueError("Use the explicit, bounded fide individual-exam preview configuration.")
    files = [path]
    for key in ("a2_manifest", "b1_manifest"):
        manifest = (path.parent / episode["source"][key]).resolve(strict=True)
        episode["source"][key] = str(manifest)
        files += [manifest, manifest.parent.parent / "book_no_toc.md"]
    tracks = {}
    for key in ("a2_manifest", "b1_manifest"):
        for line in Path(episode["source"][key]).read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            if item["track_id"] in TRACKS:
                tracks[item["track_id"]] = item
    if set(tracks) != set(TRACKS):
        raise ValueError("Selected fide practice tracks are missing.")
    script = (path.parent / episode["script"]).resolve(strict=True)
    episode["script"] = str(script)
    document = json.loads(script.read_text(encoding="utf-8"))
    episode["turns"] = compile_turns(document["blocks"], tracks, document.get("source_selection"))
    if episode["turns"][0]["display_text"] != episode["title"]:
        raise ValueError("The opening must speak the complete selected title.")
    files.append(script)
    episode["picture"] = str((path.parent / episode["picture"]).resolve(strict=True))
    for level in ("a2", "b1"):
        promo = episode["promotion"][level]
        promo["cover"] = str((path.parent / promo["cover"]).resolve(strict=True))
        if not re.fullmatch(r"https://amzn\.eu/d/[A-Za-z0-9]+", promo["url"]):
            raise ValueError("Use the supplied fide Amazon product links.")
        files.append(Path(promo["cover"]))
    episode["promotion"]["pointing_emoji"] = str(
        (path.parent / episode["promotion"]["pointing_emoji"]).resolve(strict=True))
    files += [Path(episode["picture"]), Path(episode["promotion"]["pointing_emoji"]),
              Path(episode["scene"]["base_scene"]), Path(episode["scene"]["wall_logo"])]
    if flags := episode["scene"].get("swiss_flags"):
        for key in ("model", "texture", "provenance"):
            flags[key] = str((path.parent / flags[key]).resolve(strict=True))
            files.append(Path(flags[key]))
        provenance = json.loads(Path(flags["provenance"]).read_text(encoding="utf-8"))
        for key in ("model", "texture"):
            asset = Path(flags[key])
            if sha256_file(asset) != provenance[asset.name]["sha256"]:
                raise ValueError(f"Flag asset differs from its downloaded provenance: {asset.name}")
    if set(episode["voices"]) != {"candidate_a", "examiner"}:
        raise ValueError("Only Lea and the active examiner speak.")
    for voice in episode["voices"].values():
        inspect_wav(Path(voice["audio"]))
        if not Path(voice["transcript"]).read_text(encoding="utf-8").strip():
            raise ValueError("Reference transcript is empty.")
        files.extend(Path(voice[key]) for key in ("audio", "transcript"))
    if episode.get("output_formats") != ["youtube", "social"]:
        raise ValueError("The full preview retains both approved aspect ratios.")
    validate_episode(episode)
    if production:
        from fide_speaking_production import resolve_production
        episode = resolve_production(episode, path)
    return episode, {str(p): sha256_file(p) for p in files}


def export_text(episode, build):
    lines = [episode["title"], "", "Complete book-based model conversation; not an official examination.", ""]
    for turn in episode["turns"]:
        lines += [f'{turn["id"]} | {turn["heading"]} | {turn["name"]}',
                  turn["display_text"],
                  "Source: " + turn.get("source_segment", "original simulation text"), ""]
    atomic_text(build / "full_script.txt", "\n".join(lines))
    atomic_json(build / "source_segments.json", [
        {k: turn[k] for k in ("id", "source_track", "source_segment", "source_text")}
        for turn in episode["turns"] if "source_segment" in turn])
