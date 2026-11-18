"""Prepare the reviewed fide A2-B1 script with independent playback/pause events."""

import argparse
import copy
import json
import math
from pathlib import Path
import shutil

from listening_2d.preparation.prepare_sample import (
    FPS, FRAME_SAMPLES, MODEL, RATE, ROOT, atomic_json, inspect_wav, mix_events,
    normalize, prepare_turn_audio, sha256_file, synthesize, tempo_turn_audio, write_wav,
)
from generation_runtime import generation_job

EPISODE = ROOT / "episodes" / "fide_a2_b1_listening_01.json"
REVIEW = ROOT / "builds" / "fide_a2_b1_listening_script_review_r1"
NUMBERS = dict(zip(range(7, 19), (
    "sieben", "acht", "neun", "zehn", "elf", "zwölf",
    "dreizehn", "vierzehn", "fünfzehn", "sechzehn", "siebzehn", "achtzehn")))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_files(files):
    for path, digest in files.items():
        if sha256_file(Path(path)) != digest:
            raise ValueError(f"Fide input changed: {path}")


def validate_episode(episode):
    if (episode["schema"] != "fide_a2_b1_listening_v1"
            or episode["voice_locale"] != "de-CH"
            or episode["timing"]["speech_tempo"] != .8
            or episode["timing"]["recording_plays"] != 1
            or episode["timing"]["fps"] != FPS
            or episode["timing"]["sample_rate"] != RATE):
        raise ValueError("Expected the approved Swiss 0.8x single-play fide profile.")
    situations = episode["situations"]
    if ([s["level"] for s in situations] != ["A2", "A2", "B1", "B1"]
            or any(len(s["items"]) != 3 for s in situations)
            or [i["number"] for s in situations for i in s["items"]] != list(range(7, 19))
            or situations[0]["field"] != situations[1]["field"]
            or situations[2]["field"] != situations[3]["field"]):
        raise ValueError("Fide requires two coherent three-item situations per level, numbered 7-18.")
    for situation in situations:
        for item in situation["items"]:
            minimum, maximum = (30, 45) if situation["level"] == "A2" else (35, 55)
            if not minimum <= len(item["recording"].split()) <= maximum:
                raise ValueError(f"Recording word count is outside its level range: {item['number']}")
            if situation["level"] == "A2":
                if len(item["options"]) != 3 or item["answer"] not in "ABC":
                    raise ValueError("Each A2 item needs one of three picture choices.")
                (EPISODE.parent / item["image"]).resolve(strict=True)
            elif any(key in item for key in ("image", "options", "answer")) or not item["accepted"]:
                raise ValueError("B1 requires open oral-response information, not picture/MC alternatives.")
    for key in ("opening", "transition"):
        block = episode[key]
        groups = block["display_word_groups"]
        if (len(groups) != len(block["display_text"].split())
                or [i for group in groups for i in group] != list(range(len(block["text"].split())))):
            raise ValueError(f"Every displayed {key} token needs a complete, ordered spoken-word mapping.")


def approved_episode():
    episode = read(EPISODE)
    validate_episode(episode)
    digest = sha256_file(EPISODE)
    review, approval = read(REVIEW / "review_resolution.json"), read(REVIEW / "user_approval.json")
    if (review["reviewed_episode_sha256"] != digest or approval["episode_sha256"] != digest
            or review["status"] != "pass" or review["mandatory_fixes_remaining"] != 0
            or review["reviewer_model"] != "claude-sonnet-5.5"
            or not approval["script_approved"]):
        raise ValueError("Independent review and user script approval must bind this exact fide script.")
    verify_files(review["review_files_sha256"])
    return episode


def plan(episode):
    validate_episode(episode)
    turns, events, cards = [], [], {}

    def speech(ident, text, card, phase, *, speaker="narrator", visible=False, block=None):
        turn = {"id": ident, "speaker": speaker, "name": speaker, "text": text,
                "pause_after": 0, "visible": visible}
        if block:
            turn.update(display_text=block["display_text"],
                        display_word_groups=copy.deepcopy(block["display_word_groups"]))
        turns.append(turn)
        event(ident, "speech", card, phase, audio_id=ident, visible=visible)

    def event(ident, kind, card, phase, **fields):
        events.append({"id": ident, "kind": kind, "card": card, "phase": phase, **fields})

    speech("title", episode["opening"]["text"], "title", "Titel",
           visible=True, block=episode["opening"])
    event("opening_padding", "silence", "title", "Titel",
          seconds=episode["timing"]["opening_padding_seconds"])
    for ident, text in (("setup", episode["setup"]), ("a2_instruction", episode["a2_instruction"])):
        speech(ident, text, ident, "Anleitung", visible=True)
    for situation in episode["situations"]:
        if situation["id"] == "b1_verwaltung":
            speech("transition", episode["transition"]["text"], "transition", "Nächste Stufe",
                   visible=True, block=episode["transition"])
            speech("b1_instruction", episode["b1_instruction"], "b1_instruction", "Anleitung", visible=True)
        speech("context_" + situation["id"], situation["introduction"],
               "context_" + situation["id"], "Situation", visible=True)
        for item in situation["items"]:
            number, level = item["number"], situation["level"]
            card = f"item_{number}"
            cards[card] = {"type": "picture_choice" if level == "A2" else "oral_response",
                           "level": level, "situation": situation["id"], **copy.deepcopy(item)}
            question = f"question_{number}"
            speech(question, f"Frage {NUMBERS[number]}. {item['question']}", card, "Frage hören")
            if level == "A2":
                event(f"inspect_{number}", "silence", card, "Bilder ansehen",
                      seconds=episode["timing"]["a2_picture_seconds"])
            speech(f"recording_{number}", item["recording"], card, "Jetzt hören",
                   speaker=item["speaker"])
            event(f"repeat_question_{number}", "speech", card, "Frage hören",
                  audio_id=question, visible=False)
            event(f"answer_{number}", "silence", card,
                  "Bild auswählen" if level == "A2" else "Mündlich antworten",
                  seconds=episode["timing"]["a2_answer_seconds" if level == "A2" else "b1_answer_seconds"])
    speech("end_test", episode["end_test"], "end_test", "Hörteil beendet", visible=True)
    speech("solutions_instruction", episode["solutions_instruction"],
           "solutions_instruction", "Lösungen", visible=True)
    for situation in episode["situations"]:
        for item in situation["items"]:
            number = item["number"]
            solution = item["solution"]
            if situation["level"] == "B1":
                solution = f"Frage {NUMBERS[number]}. {solution}"
            speech(f"solution_{number}", solution, f"solution_{number}", "Lösung vergleichen")
            event(f"solution_padding_{number}", "silence", f"solution_{number}", "Lösung vergleichen",
                  seconds=episode["timing"]["solution_padding_seconds"])
    speech("cta", episode["promotion"]["cta"], "cta", "Mehr üben")
    event("outro", "silence", "cta", "Mehr üben", seconds=episode["timing"]["outro_seconds"])
    if len({t["id"] for t in turns}) != len(turns) or len({e["id"] for e in events}) != len(events):
        raise ValueError("Speech and event identifiers must be unique.")
    return {"turns": turns, "events": events, "cards": cards}


def schedule(events, measured):
    result, cursor = [], 0
    for source in events:
        event = copy.deepcopy(source)
        info = measured.get(event.get("audio_id"))
        frames = round(event["seconds"] * FPS) if event["kind"] == "silence" else math.ceil(info["frames"] / FRAME_SAMPLES)
        if frames <= 0:
            raise ValueError("Events need a positive frame-exact duration.")
        event.update(start_frame=cursor, end_frame=cursor + frames, start=cursor / FPS,
                     end=(cursor + frames) / FPS, duration=frames / FPS)
        if info:
            event.update(audio=info["audio"], sha256=info["sha256"], audio_samples=info["frames"],
                         text=info["text"], speaker=info["speaker"])
        result.append(event)
        cursor += frames
    turns = [{**measured[e["audio_id"]], "id": e["id"], "audio_id": e["audio_id"],
              "visible": e.get("visible", False), "start": e["start"], "end": e["end"]}
             for e in result if e["kind"] == "speech"]
    return {"language": "de", "scope": "full", "fps": FPS, "sample_rate": RATE,
            "practice_mode": "fide_exam_sequence_slowed", "events": result, "turns": turns,
            "total_frames": cursor, "duration": cursor / FPS}


def voices():
    folder = ROOT.parent.parent / "shared-voices" / "gemini_3.8_flash_tts" / "swiss"
    bindings, pins = {}, {}
    for role, name in (("narrator", "male_middle_aged"), ("service", "female_middle_aged"),
                       ("resident", "female_young_adult"), ("neighbour", "female_middle_aged")):
        bindings[role] = {"audio": str(folder / f"{name}.wav"),
                          "transcript": str(folder / f"text_{name}.txt")}
        inspect_wav(Path(bindings[role]["audio"]))
        pins[role] = {key: {"path": path, "sha256": sha256_file(Path(path))}
                      for key, path in bindings[role].items()}
    return bindings, pins


def script_text(episode, planned):
    texts = {turn["id"]: turn["text"] for turn in planned["turns"]}
    lines = [episode["title"], "", "COMPLETE SPOKEN SCRIPT - includes post-test answers", ""]
    for event in planned["events"]:
        lines.append(f"[{event['id']} | {event['phase']}]")
        lines.append(texts[event["audio_id"]] if event["kind"] == "speech"
                     else f"Silence: {event['seconds']} seconds")
        lines.append("")
    lines.extend(["SOURCE ADAPTATIONS AND ACCEPTED ANSWERS", ""])
    for situation in episode["situations"]:
        lines.extend([situation["source"], ""])
        for item in situation["items"]:
            lines.append(f"{item['number']}: {item['source_item']}")
            lines.extend(item["adaptations"] or ["Source wording retained."])
            if "accepted" in item:
                lines.extend(["Accept: " + answer for answer in item["accepted"]])
                lines.append("Rubric: " + item["essential"])
            lines.append("")
    return "\n".join(lines)


@generation_job
def prepare(build, plan_only=False):
    build = build.resolve()
    episode = read(EPISODE) if plan_only else approved_episode()
    planned = plan(episode)
    bindings, references = voices()
    research_path = (EPISODE.parent / episode["source"]["research_pin"]).resolve(strict=True)
    research = read(research_path)
    verify_files(research["inputs_sha256"])
    official = {str(research_path.parent / item["local"]): item["sha256"] for item in research["official"]}
    verify_files(official)
    files = [EPISODE, Path(__file__), ROOT / "preparation/prepare_sample.py",
             ROOT.parent / "pilot_3d" / "prepare_audio.py", research_path]
    if not plan_only:
        files.extend((REVIEW / "review_resolution.json", REVIEW / "user_approval.json"))
    inputs = {"files": {str(p): sha256_file(p) for p in files}, "voices": references,
              "research": research["inputs_sha256"], "official": official}
    build.mkdir(parents=True, exist_ok=True)
    pin_path = build / "input_pin.json"
    if pin_path.exists() and read(pin_path) != inputs:
        raise ValueError("Fide preparation inputs changed; use a fresh build.")
    atomic_json(pin_path, inputs)
    atomic_json(build / "speech_plan.json", planned)
    atomic_json(build / "sample_content.json", {"episode": episode, "cards": planned["cards"]})
    atomic_json(build / "voice_references.json", references)
    (build / "script_review.txt").write_text(script_text(episode, planned), encoding="utf-8")
    print(f"Fide plan: {len(planned['turns'])} unique speech clips, {len(planned['events'])} events.", flush=True)
    if plan_only:
        return
    snapshot = build / "preparation_sources"
    snapshot.mkdir(exist_ok=True)
    for path in files:
        target = snapshot / path.name
        if target.exists() and sha256_file(target) != sha256_file(path):
            raise ValueError("A preparation source snapshot changed.")
        shutil.copy2(path, target)
    audio = build / "audio"
    audio.mkdir(exist_ok=True)
    raw = synthesize({"language": "de", "voices": bindings, "turns": planned["turns"]},
                     ROOT, audio, MODEL, "cpu", 8)
    measured = {}
    for turn, recording in zip(planned["turns"], raw):
        cleaned = prepare_turn_audio(turn["id"], recording, audio)
        slowed = tempo_turn_audio(turn["id"], cleaned, audio, .8)
        target = audio / f"{turn['id']}.wav"
        measured[turn["id"]] = {
            **turn, **normalize(Path(slowed["audio"]), target), "audio": str(target),
            "sha256": sha256_file(target), "raw_audio": recording["audio"],
            "raw_sha256": sha256_file(Path(recording["audio"])), "processed_audio": slowed["audio"],
            "processed_sha256": sha256_file(Path(slowed["audio"])), "atempo": .8,
        }
    timeline = schedule(planned["events"], measured)
    write_wav(build / "dialogue.wav", mix_events(timeline["events"]))
    atomic_json(build / "audio_manifest.json", measured)
    atomic_json(build / "timeline.json", timeline)
    verify_files(inputs["files"])
    verify_files(inputs["research"])
    verify_files(inputs["official"])
    print(f"Fide audio ready: {timeline['total_frames']} frames / {timeline['duration']:.3f}s.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    prepare(args.build, args.plan_only)
