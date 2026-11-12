"""Prepare the approved original A2 episode without changing frozen B1 inputs."""

import argparse
import copy
import json
import math
from pathlib import Path
import shutil

from prepare_full import voices
from prepare_sample import (
    ROOT, FPS, RATE, FRAME_SAMPLES, MODEL, CHIME_FILTER, atomic_json,
    inspect_wav, mix_events, normalize, prepare_turn_audio, sha256_file,
    synthesize, tempo_turn_audio, write_wav,
)

EPISODE = ROOT / "episodes" / "oeif_a2_listening_01.json"
REVIEW = ROOT / "builds" / "oeif_a2_listening_script_review_r1"
SOURCE = ROOT / "builds" / "oeif_b1_listening_full_production_r1"
NUMBERS = ["", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben",
           "acht", "neun", "zehn", "elf", "zwölf", "dreizehn", "vierzehn", "fünfzehn"]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def plan(episode):
    turns, events, cards = [], [], {}

    def speech(ident, text, speaker="narrator"):
        turns.append({"id": ident, "speaker": speaker, "name": speaker,
                      "text": text, "pause_after": 0})

    def event(ident, kind, card, phase, part, audio_id=None, seconds=None):
        row = dict(id=ident, kind=kind, card=card, phase=phase, part=part)
        if audio_id:
            row["audio_id"] = audio_id
        if seconds is not None:
            row["seconds"] = seconds
        events.append(row)

    speech("title", episode["opening"]["text"])
    event("title", "speech", "title", "Titel", 0, "title")
    for section in episode["sections"]:
        part = section["part"]
        speech(f"short_title_{part}", f"Ö I F A zwei Hören Teil {NUMBERS[part]}.")
        speech(f"instruction_{part}", section["instruction"])
        event(f"instruction_{part}", "speech", f"instruction_{part}",
              "Anleitung", part, f"instruction_{part}")
        overview = f"overview_{part}"
        cards[overview] = {
            "type": "compact" if part == 1 else "overview", "part": part,
            "questions": [copy.deepcopy(q) for g in section["groups"] for q in g["questions"]],
            "label": f"Teil {part} · Alle Fragen lesen",
        }
        event(f"part_{part}_start", "chime", overview, "Lesen vorbereiten", part, "chime_start")
        event(f"part_{part}_read", "silence", overview, "Lesen", part,
              seconds=episode["timing"]["initial_read_seconds_per_part"])
        for index, group in enumerate(section["groups"]):
            ident = group["id"]
            numbers = [q["number"] for q in group["questions"]]
            label = (f"Aufgaben {numbers[0]}–{numbers[-1]}" if len(numbers) > 1
                     else f"Aufgabe {numbers[0]}")
            cards[ident] = {
                "type": "compact" if len(numbers) > 1 else "binary" if part == 4 else "mc",
                "part": part, "questions": copy.deepcopy(group["questions"]), "label": label,
            }
            if index:
                event(ident + "_back", "chime", ident, "Nächste Aufgabe", part, "chime_back")
            cue = ("Nummer eins bis sieben." if len(numbers) > 1
                   else f"Nummer {NUMBERS[numbers[0]]}.")
            speech(ident + "_cue", cue)
            event(ident + "_cue", "speech", ident, "Aufgabe", part, ident + "_cue")
            for ti, turn in enumerate(group["recording"], 1):
                speech(f"{ident}_audio_{ti}", turn["text"], turn["speaker"])
            for play in range(1, section["plays"] + 1):
                if play > 1:
                    event(ident + "_replay_gap", "silence", ident, "Noch einmal hören", part,
                          seconds=episode["timing"]["between_replays_seconds"])
                for ti, turn in enumerate(group["recording"], 1):
                    event(f"{ident}_play{play}_turn{ti}", "speech", ident,
                          f"Jetzt hören · {play}/{section['plays']}", part, f"{ident}_audio_{ti}")
            event(ident + "_answer", "silence", ident, "Antwort notieren", part,
                  seconds=episode["timing"]["answer_seconds_after_final_play"])
            event(ident + "_reveal", "reveal", ident, "Lösung ansehen", part, "chime_remove",
                  episode["timing"]["reveal_seconds"])
        speech(f"end_part_{part}", f"Ende von Teil {NUMBERS[part]}.")
        event(f"end_part_{part}", "speech", "end", "Teil beendet", part, f"end_part_{part}")
    event("summary_read", "silence", "summary", "Lösungen vergleichen", 0, seconds=10)
    speech("cta", episode["promotion"]["cta"])
    event("cta", "speech", "cta", "Mehr üben", 0, "cta")
    return {"turns": turns, "events": events, "cards": cards}


def schedule(planned, measured, scope="full", part=None, selected=None):
    result, cursor = [], 0
    for original in planned:
        event = copy.deepcopy(original)
        item = measured.get(event.get("audio_id"))
        frames = (round(event["seconds"] * FPS) if "seconds" in event
                  else math.ceil(item["frames"] / FRAME_SAMPLES))
        if event.get("title_padding"):
            frames = (item["frames"] + RATE // 2 + FRAME_SAMPLES - 1) // FRAME_SAMPLES
        event.update(start_frame=cursor, end_frame=cursor + frames,
                     start=cursor / FPS, end=(cursor + frames) / FPS, duration=frames / FPS)
        if item:
            if item["frames"] > frames * FRAME_SAMPLES:
                raise ValueError(f"Audio tail exceeds {event['id']}.")
            event.update(audio=item["audio"], sha256=item["sha256"],
                         audio_samples=item["frames"], text=item.get("text"),
                         speaker=item.get("speaker"))
        result.append(event)
        cursor += frames
    turns = [{**measured[e["audio_id"]], "id": e["id"], "audio_id": e["audio_id"],
              "start": e["start"], "end": e["end"]}
             for e in result if e["kind"] == "speech"]
    return dict(language="de", scope=scope, part=part, selected=selected, fps=FPS,
                sample_rate=RATE, practice_mode="guided", answer_reveal_seconds=3,
                duration=cursor / FPS, total_frames=cursor, events=result, turns=turns)


def prepare(build, plan_only=False):
    build = build.resolve()
    episode = read(EPISODE)
    approval, review = read(REVIEW / "user_approval.json"), read(REVIEW / "recheck.json")
    digest = sha256_file(EPISODE)
    if not (digest == approval["episode_sha256"] == review["reviewed_episode_sha256"].lower()
            and review["verdict"] == "pass" and not review["blockers"]):
        raise ValueError("Script review/approval does not match the episode.")
    all_bindings, all_refs = voices()
    roles = {"narrator": "narrator", "service_female": "service_female",
             "announcement_male": "announcement_male", "announcement_female": "opinion_mature",
             "dialogue_female": "dialogue_female", "dialogue_male": "dialogue_male"}
    bindings = {role: all_bindings[source] for role, source in roles.items()}
    refs = {role: all_refs[source] for role, source in roles.items()}
    if refs["announcement_female"]["audio"]["sha256"] == refs["service_female"]["audio"]["sha256"]:
        raise ValueError("Task 8 needs a voice distinct from Part 1.")
    files = [EPISODE, Path(__file__), ROOT / "prepare_full.py", ROOT / "prepare_sample.py",
             ROOT.parent / "pilot_3d" / "prepare_audio.py",
             ROOT / "assets" / "oeif_a2_format_reference.json",
             REVIEW / "review.json", REVIEW / "recheck.json", REVIEW / "user_approval.json",
             SOURCE / "audio_manifest.json", SOURCE / "voice_references.json"]
    pins = {"files": {str(p.resolve()): sha256_file(p) for p in files}, "voices": refs,
            "book": {str((EPISODE.parent / episode["promotion"]["cover_source"]).resolve()):
                     sha256_file(EPISODE.parent / episode["promotion"]["cover_source"])}}
    build.mkdir(parents=True, exist_ok=True)
    if (build / "input_pin.json").is_file() and read(build / "input_pin.json") != pins:
        raise ValueError("A2 inputs changed; use a fresh build.")
    atomic_json(build / "input_pin.json", pins)
    atomic_json(build / "voice_references.json", refs)
    speech_plan = plan(episode)
    atomic_json(build / "speech_plan.json", speech_plan)
    atomic_json(build / "sample_content.json", {"episode": episode, "cards": speech_plan["cards"]})
    print(f"A2 plan: {len(speech_plan['turns'])} unique speech turns; "
          f"{len(speech_plan['events'])} full events.", flush=True)
    if plan_only:
        return
    audio = build / "audio"
    audio.mkdir(exist_ok=True)
    previous, previous_refs = read(SOURCE / "audio_manifest.json"), read(SOURCE / "voice_references.json")
    measured, pending = {}, []
    for turn in speech_plan["turns"]:
        reusable = next((item for item in previous.values() if item.get("text") == turn["text"]
                         and item.get("speaker") in previous_refs
                         and previous_refs[item["speaker"]] == refs[turn["speaker"]]), None)
        if reusable:
            source = Path(reusable["audio"])
            if sha256_file(source) != reusable["sha256"]:
                raise ValueError("Changed approved source audio.")
            target = audio / f"{turn['id']}.wav"
            shutil.copyfile(source, target)
            measured[turn["id"]] = {**turn, **inspect_wav(target), "audio": str(target),
                                   "sha256": sha256_file(target), "atempo": 0.8,
                                   "reused_from": str(source)}
        else:
            pending.append(turn)
    raw = synthesize({"language": "de", "voices": bindings, "turns": pending},
                     ROOT, audio, MODEL, "cpu", 8)
    for turn, result in zip(pending, raw):
        cleaned = prepare_turn_audio(turn["id"], result, audio)
        slowed = tempo_turn_audio(turn["id"], cleaned, audio, 0.8)
        target = audio / f"{turn['id']}.wav"
        info = normalize(Path(slowed["audio"]), target)
        measured[turn["id"]] = {**turn, **info, "audio": str(target),
                               "sha256": sha256_file(target), "raw_audio": result["audio"],
                               "processed_audio": slowed["audio"], "atempo": 0.8}
    sfx = read(ROOT / "assets" / "sfx" / "sources.json")
    for ident, role in (("chime_start", "start"), ("chime_back", "end"), ("chime_remove", "reveal")):
        asset = next(a for a in sfx["assets"] if a["file"] == sfx["selected_cues"][role])
        source = ROOT / "assets" / "sfx" / asset["file"]
        if sha256_file(source) != asset["sha256"]:
            raise ValueError("Original sound effect changed.")
        target = audio / f"{ident}.wav"
        measured[ident] = {**normalize(source, target, CHIME_FILTER), "audio": str(target),
                           "sha256": sha256_file(target), "original_sha256": asset["sha256"],
                           "filter": CHIME_FILTER}
    timeline = schedule(speech_plan["events"], measured)
    write_wav(build / "dialogue.wav", mix_events(timeline["events"]))
    atomic_json(build / "audio_manifest.json", measured)
    atomic_json(build / "timeline.json", timeline)
    print(f"A2 full audio ready: {timeline['duration']:.3f}s.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    prepare(args.build, args.plan_only)
