"""Book-based B2 pair dialogue, reading cards and measured review checks."""

import copy
from functools import lru_cache
import math
import re
from pathlib import Path

from prepare_audio import atomic_json, sha256_file

TRACKS = {1: "oeif_b2_v2_001_praesentation", 2: "oeif_b2_v2_026_diskussion",
          3: "oeif_b2_v2_047_planung"}


def is_b2(episode):
    return episode.get("exam", {}).get("level") == "B2"


def shared_head_fits(head):
    from long_speaking import FORMATS

    youtube, social = FORMATS["youtube"]["scene"], FORMATS["social"]["scene"]
    ratio = ((social[2] - social[0]) / (social[3] - social[1])) / (
        (youtube[2] - youtube[0]) / (youtube[3] - youtube[1]))
    margin = (1 - ratio) / 2
    x0, y0, x1, y1 = head["bounds"]
    return (head["in_front"] and margin + .05 * ratio < x0 <= x1 < 1 - margin - .05 * ratio
            and .05 < y0 <= y1 < .95)


def reading_pages(episode):
    from runtime_config import font_path

    text = Path(episode["source"]["book"]).read_text(encoding="utf-8")
    exercise = text.split("## Soll die Sommerzeit abgeschafft werden?\n", 1)[1]
    reading = exercise.split("### Impulstext\n", 1)[1].split(
        "### Gestufter Diskussionsauftrag", 1)[0].strip()
    font = font_path()
    return list(_paginate_reading(reading, str(font), font.stat().st_mtime_ns))


@lru_cache(maxsize=8)
def _paginate_reading(reading, font_file, _font_mtime):
    from PIL import Image, ImageDraw, ImageFont
    from long_speaking import wrapped

    draw = ImageDraw.Draw(Image.new("RGB", (836, 505)))
    font = ImageFont.truetype(font_file, 32)

    def fits(words):
        return len(words) <= 60 and len(wrapped(draw, " ".join(words), font, 776)) * 32 * 1.28 <= 455

    pages, current = [], []
    for word in reading.split():
        if current and not fits([*current, word]):
            pages.append(current)
            current = []
        current.append(word)
    if current:
        pages.append(current)
    if not pages:
        raise ValueError("The complete B2 reading stimulus is empty.")
    if len(pages) > 1 and len(pages[-1]) < 20:
        combined = pages[-2] + pages[-1]
        left, right = combined[:len(combined) // 2], combined[len(combined) // 2:]
        if fits(left) and fits(right):
            pages[-2:] = [left, right]
    return tuple(" ".join(page) for page in pages)


def reading_cards(episode):
    summary = episode["parts"][1].get("reading_summary")
    if summary is not None:
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("The reading summary must be nonempty text.")
        return [("reading_summary", "Teil 2: Kurzfassung des Lesetexts",
                 "Den vollständigen Lesetext findest du im Buch.", summary)]
    pages = reading_pages(episode)
    return [(f"reading_{index:02d}", f"Teil 2: Lesetext · Seite {index}/{len(pages)}",
             "Vollständiger Buchtext · Bei Bedarf anhalten.", text)
            for index, text in enumerate(pages, 1)]


def preparation_cards(episode):
    def task(part):
        return {"id": f"prepare_teil{part['number']}", "part": part["number"],
                "heading": f"Teil {part['number']}: {part['topic']}",
                "body": "Bei Bedarf das Video anhalten.",
                "card_text": "\n".join(part["task"]).replace(" · ", ", ")}

    return [task(episode["parts"][0]),
            *[{"id": key, "part": 2, "heading": heading, "body": hint, "card_text": text}
              for key, heading, hint, text in reading_cards(episode)],
            task(episode["parts"][2])]


def compile_script(episode, tracks):
    turns = [{"id": "opening", **episode["opening"], "part": 0, "kind": "opening"}]
    turns.append({"id": "preparation", "speaker": "examiner", "part": 0,
                  "kind": "preparation", "text": episode["preparation"]})
    if episode.get("narrate_preparation_cards"):
        for card in preparation_cards(episode):
            turns.append({"id": card["id"], "panel_id": card["id"], "part": card["part"],
                          "kind": "preparation_card", "speaker": "examiner",
                          "text": " ".join((card["heading"] + " " + card["card_text"] + " "
                                            + card["body"]).split()),
                          "adaptation": "Voiced learning card, not part of the exam conversation."})
    for index, turn in enumerate(episode["contact"], 1):
        turns.append({"id": f"contact_{index:02d}", "part": 0, "kind": "contact", **turn,
                      "adaptation": "Fictional contact exchange authored for this video."})
    book = Path(episode["source"]["book"]).read_text(encoding="utf-8")
    for part in episode["parts"]:
        number = part["number"]
        turns.append({"id": f"teil{number}_instruction", "part": number, "speaker": "examiner",
                      "text": part["instruction"], "kind": "instruction"})
        if [selection["id"] for selection in part["tracks"]] != [TRACKS[number]]:
            raise ValueError("B2 uses the first actual exercise in each chapter, not an introductory model.")
        for selection in part["tracks"]:
            track = tracks.get(selection["id"])
            if track is None or not track["section"].startswith(f"Kapitel {number}:"):
                raise ValueError("Missing or wrong-chapter B2 source track.")
            for segment in track["segments"]:
                role = selection["roles"].get(segment["speaker_label"])
                if role not in episode["cast"]:
                    raise ValueError(f"Unmapped B2 speaker: {segment['speaker_label']}")
                turns.append({
                    "id": segment["segment_id"], "part": number, "speaker": role, "kind": "model",
                    "text": segment["text_original"], "text_tts": segment["text_tts"],
                    "source_track": track["track_id"], "source_line": track["source_line"],
                    "source_voice_id": segment["voice_id"],
                    "adaptation": "Original book model unchanged; recast as Lea and Samir.",
                })
        for index, turn in enumerate(part.get("follow_up", []), 1):
            if turn["text"] not in book or turn["speaker"] not in ("candidate_a", "candidate_b"):
                raise ValueError("B2 presentation follow-ups must be the supplied book partner questions/answers.")
            turns.append({"id": f"teil{number}_followup_{index:02d}", "part": number,
                          "kind": "question" if turn["speaker"] == "candidate_b" else "model",
                          **turn, "adaptation": "Partner question/example answer from the first book exercise."})
        for index, turn in enumerate(part.get("extension", []), 1):
            if turn["speaker"] not in ("candidate_a", "candidate_b") or not turn["text"].strip():
                raise ValueError("B2 dialogue extensions require two candidate roles.")
            turns.append({"id": f"teil{number}_extension_{index:02d}", "part": number,
                          "kind": "model", **turn,
                          "adaptation": "Original continuation authored for this video, not a book quotation."})
    turns.append({"id": "exam_close", "speaker": "examiner", "part": 3,
                  "kind": "close", "text": "Vielen Dank Ihnen beiden. Damit ist das Gespräch beendet."})
    turns.append({"id": "final_cta", "speaker": "examiner", "part": 0, "kind": "cta",
                  "text": " ".join(episode["promotion"]["cta"])})
    return {"status": "unmeasured_b2_script", "turns": turns,
            "timing": "No generated audio or estimated word timestamps.",
            "opening_alignment": episode["opening"]["alignment_policy"],
            "subtitle_alignment": episode["subtitles"]}


def panels(episode, script):
    from long_speaking import caption_excerpt

    def panel(key, part, heading, body, camera="wide", **extra):
        return {"id": key, "part": part, "heading": heading, "body": body,
                "camera": camera, "picture": False, **extra}

    model = next(t for t in script["turns"] if t.get("source_track") == TRACKS[1])
    discussion = next(t for t in script["turns"] if t.get("source_track") == TRACKS[2])
    planning = [t for t in script["turns"] if t.get("source_track") == TRACKS[3]]
    first, second, third = episode["parts"]
    result = [
        panel("01_opening", 0, episode["title"], [f"{p['number']} · {p['title']}" for p in episode["parts"]]),
        panel("00_preparation", 0, "Vorbereitung · Lernpause", ["20 Minuten Einzelvorbereitung in der Prüfung.",
              "Hier: Video zum Lesen bei Bedarf anhalten."]),
        panel("00_contact", 0, "Kontaktphase · Lea und Samir", caption_excerpt(episode["contact"][0]["text"]),
              "candidates"),
        panel("02_teil1_task", 1, first["topic"], first["task"]),
        panel("03_teil1_model", 1, "Lea · Präsentation", caption_excerpt(model["text"]), "candidate_a"),
        panel("04_teil1_followup", 1, "Samir · Rückfrage", first["follow_up"][0]["text"], "candidate_b"),
        panel("teil1_skip", 1, "Teil 1 · Hinweis", "Weiter mit Teil 2: Diskussion.",
              card_text="Samirs Präsentation und die Rückfragen dazu werden übersprungen."),
        panel("05_teil2_task", 2, second["topic"], second["task"]),
        panel("06_teil2_model", 2, "Lea · Diskussion", caption_excerpt(discussion["text"]), "candidate_a"),
        panel("07_teil2_followup", 2, "Samir · Diskussion", "Welche Folgen hätte das im Winter?", "candidate_b"),
        panel("08_teil3_task", 3, third["topic"], third["task"], "candidates"),
        panel("09_teil3_lea", 3, "Lea · Gemeinsam planen", caption_excerpt(planning[0]["text"]), "candidate_a"),
        panel("10_teil3_samir", 3, "Samir · Gemeinsam planen", caption_excerpt(planning[1]["text"]), "candidate_b"),
        panel("11_teil3_result", 3, "Unser gemeinsamer Plan", third["result"], "candidates"),
        panel("12_final_cta", 0, episode["promotion"]["cta"][0], episode["promotion"]["cta"][1:]),
    ]
    for card in preparation_cards(episode):
        result.append(panel(card["id"], card["part"], card["heading"], card["body"],
                            card_text=card["card_text"]))
    return result


def pronunciation(display):
    replacements = {
        "ÖIF": "Ö I F", "B2": "B zwei", "ÖIF-B2-Buch": "Ö I F B zwei Buch",
        "1": "eins", "2": "zwei", "3": "drei",
        "32": "zweiunddreißig", "55": "fünfundfünfzig", "800": "achthundert",
        "640": "sechshundertvierzig", "256": "zweihundertsechsundfünfzig",
        "1.696": "eintausendsechshundertsechsundneunzig", "53": "dreiundfünfzig",
        "1.760": "eintausendsiebenhundertsechzig", "WCs": "Toiletten",
    }
    spoken, groups = [], []
    for token in display.split():
        word, punctuation = re.fullmatch(r"(.+?)([.,!?;:]?)", token).groups()
        phrase = replacements.get(word, word)
        if any(c.isdigit() for c in phrase):
            raise ValueError(f"Unmapped B2 spoken number: {token}")
        tokens = (phrase + punctuation).split()
        groups.append(list(range(len(spoken), len(spoken) + len(tokens))))
        spoken.extend(tokens)
    return " ".join(spoken), groups


def resolve_episode(episode, path):
    from long_speaking import compile_script as compile_storyboard, load_episode

    episode = copy.deepcopy(episode)
    if (episode["source"].get("duration_limit_seconds") != 900
            or not episode["source"].get("duration_exception")):
        raise ValueError("B2 requires an explicitly authorized bounded long-form episode.")
    episode["storyboard"] = str((path.parent / episode["storyboard"]).resolve(strict=True))
    storyboard = load_episode(episode["storyboard"])
    if not is_b2(storyboard) or episode["title"] != storyboard["title"]:
        raise ValueError("B2 execution and storyboard identity differ.")
    turns = []
    for source in compile_storyboard(storyboard)["turns"]:
        turn = copy.deepcopy(source)
        part, role, kind = turn["part"], turn["speaker"], turn["kind"]
        spoken, groups = pronunciation(turn["text"])
        turn.update(name=storyboard["cast"][role], text=spoken, display_text=source["text"],
                    display_word_groups=groups, pause_after=.6, camera=role,
                    action="answer", look_at="candidate_b" if role == "candidate_a" else "candidate_a")
        if "source_track" in source:
            turn["source_segment"] = source["id"]
        if kind == "opening":
            turn.update(panel_id="01_opening", camera="wide", action="explain")
        elif kind == "preparation":
            turn.update(panel_id="00_preparation", camera="wide", action="explain")
        elif kind == "preparation_card":
            turn.update(camera="wide", action="explain", pause_after=1.5)
        elif kind == "contact":
            turn.update(panel_id="00_contact", heading=f"Kontaktphase · {turn['name']}")
        elif kind == "instruction":
            turn.update(kind="task", panel_id={1: "02_teil1_task", 2: "05_teil2_task", 3: "08_teil3_task"}[part],
                        camera="examiner", action="explain")
        elif kind == "cta":
            turn.update(panel_id="12_final_cta", camera="wide", action="explain", pause_after=0)
        elif kind == "close":
            turn.update(panel_id="11_teil3_result", camera="wide", action="explain")
        else:
            key = ("04_teil1_followup" if role == "candidate_b" else "03_teil1_model") if part == 1 else (
                "06_teil2_model" if role == "candidate_a" else "07_teil2_followup") if part == 2 else (
                "09_teil3_lea" if role == "candidate_a" else "10_teil3_samir")
            turn.update(panel_id=key, heading=f"{turn['name']} · " + (
                "Präsentation" if part == 1 and "source_track" in source else
                "Rückfragen" if part == 1 else "Diskussion" if part == 2 else "Gemeinsam planen"))
        turns.append(turn)
    cards = ["prepare_teil1", *[card[0] for card in reading_cards(storyboard)],
             "prepare_teil3"]
    episode["review_cards"] = [
        {"after_turn": "teil1_followup_06", "panels": ["teil1_skip"], "seconds_each": 5},
    ]
    if not storyboard.get("narrate_preparation_cards"):
        episode["review_cards"].insert(
            0, {"after_turn": "preparation", "panels": cards, "seconds_each": 4})
    by_id = {t["id"]: t for t in turns}
    for hold in episode["review_cards"]:
        by_id[hold["after_turn"]]["pause_after"] = len(hold["panels"]) * hold["seconds_each"] + .5
    episode["turns"] = turns
    return episode


def attach_cards(build, episode):
    import json

    path = build / "timeline.json"
    timeline = json.loads(path.read_text(encoding="utf-8"))
    turns = {t["id"]: t for t in timeline["turns"]}
    notices = []
    for hold in episode["review_cards"]:
        turn = turns[hold["after_turn"]]
        # Match both the on-threes review and on-twos master sampling grids.
        cursor = turn["start_frame"] + math.ceil(
            (turn["end_frame"] - turn["start_frame"]) / 6) * 6
        length = hold["seconds_each"] * timeline["fps"]
        for panel in hold["panels"]:
            notices.append({"id": panel, "panel_id": panel, "start_frame": cursor,
                            "end_frame": cursor + length})
            cursor += length
        if cursor > turn["end_frame"] + turn["pause_after_frames"]:
            raise ValueError("Reading cards overlap the next speech turn.")
    timeline["silent_notices"] = notices
    atomic_json(path, timeline)


def timing_checks(episode, storyboard, timeline):
    turns = {t["id"]: t for t in timeline["turns"]}
    presentation = turns[TRACKS[1] + "_seg_001"]["wav_duration"]
    reactions = [turns[TRACKS[2] + f"_seg_{i:03d}"]["wav_duration"] for i in (1, 2)]
    if presentation > 90 or any(duration > 60 for duration in reactions):
        raise ValueError("Measured B2 presentation or initial text reaction exceeds its speaking limit.")
    ranges = []
    for key in storyboard["social_selection"]["turns"]:
        turn = turns[key]
        tail = (round(episode["outro_seconds"] * timeline["fps"]) if key == "final_cta"
                else min(turn["pause_after_frames"], timeline["fps"] // 2))
        ranges.append({"turn_id": key, "start_frame": turn["start_frame"],
                       "end_frame": turn["end_frame"] + tail})
    card_budget = 9 * timeline["fps"]
    short_frames = sum(r["end_frame"] - r["start_frame"] for r in ranges) + card_budget
    if short_frames / timeline["fps"] >= 180:
        raise ValueError("The complete-turn short selection needs revision before native rendering; do not accelerate speech.")
    windows = {}
    for part in (1, 2, 3):
        selected = [t for t in timeline["turns"] if t["part"] == part and t["speaker"] != "examiner"]
        windows[str(part)] = selected[-1]["end"] - selected[0]["start"]
    return {"presentation_seconds": presentation, "initial_text_reactions_seconds": reactions,
            "candidate_section_windows_seconds": windows,
            "master_seconds": timeline["total_frames"] / timeline["fps"],
            "short_candidate_ranges": ranges, "short_card_budget_frames": card_budget,
            "short_candidate_total_frames": short_frames, "short_candidate_seconds": short_frames / timeline["fps"],
            "short_limit_seconds": 180, "short_complete_turn_selection_fits": True,
            "note": "Measured source ranges plus a nine-second card budget, not an encoded social delivery.",
            "human_listening_performed": False}


def resolve_production(episode, path):
    import json

    episode = resolve_episode(episode, path)
    if (episode.get("preview_approval", {}).get("approved_by") != "user"
            or not episode["preview_approval"].get("approved_on")):
        raise ValueError("B2 production requires explicit user preview approval.")
    episode["approved_preview"] = str((path.parent / episode["approved_preview"]).resolve(strict=True))
    source = Path(episode["approved_preview"])
    if sha256_file(source / "export_manifest.json") != episode["approved_preview_manifest_sha256"]:
        raise ValueError("Approved B2 preview manifest changed.")
    manifest = json.loads((source / "export_manifest.json").read_text(encoding="utf-8"))
    for name in ("preview_youtube.mp4", "episode.json", "dialogue.wav", "timeline.json",
                 "word_alignment.json", "subtitles.srt", "delivery_checks.json",
                 "speech_asr_check.json", "b2_timing_checks.json"):
        if manifest["files_sha256"].get(name) != sha256_file(source / name):
            raise ValueError(f"Unverified B2 preview file: {name}")
    report = json.loads((source / "delivery_checks.json").read_text(encoding="utf-8"))
    if report["status"] != "preview_only" or "youtube" not in report["exports"]:
        raise ValueError("B2 production requires the full YouTube preview, not contact sheets alone.")
    original = json.loads((source / "episode.json").read_text(encoding="utf-8"))
    allowed = {"id", "template", "render", "render_device", "output_formats",
               "approved_preview", "approved_preview_manifest_sha256", "preview_approval"}
    if ({k: v for k, v in original.items() if k not in allowed}
            != {k: v for k, v in episode.items() if k not in allowed}):
        raise ValueError("B2 production content differs from its approved preview.")
    for name, digest in report["source_sha256"]["asset_sha256"].items():
        if sha256_file(Path(name)) != digest:
            raise ValueError(f"Approved B2 input changed: {name}")
    from long_speaking_preview import ROOT, SOURCES
    if manifest["generation_source_sha256"] != {name: sha256_file(ROOT / name) for name in SOURCES}:
        raise ValueError("B2 generation code changed after preview; prepare a new reviewed build.")
    return episode


def production_reuse_spec(episode, source):
    from build_paths import resolve_build_reference
    from pipeline import audio_reuse_spec

    if source is None or resolve_build_reference(source).resolve(strict=True) != Path(episode["approved_preview"]):
        raise ValueError("B2 production must exactly reuse its approved preview audio.")
    receipt = audio_reuse_spec(episode, source)
    receipt.update(approved_preview=episode["approved_preview"],
                   approved_manifest_sha256=episode["approved_preview_manifest_sha256"])
    receipt["files_sha256"].update({
        name: sha256_file(Path(episode["approved_preview"]) / name)
        for name in ("export_manifest.json", "delivery_checks.json", "speech_asr_check.json",
                     "b2_timing_checks.json", "subtitles.srt")
    })
    return receipt
