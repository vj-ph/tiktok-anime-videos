"""Prepare the approved four-part listening practice with measured local audio."""

import argparse
import copy
import json
import math
from pathlib import Path
import shutil
import wave

from prepare_sample import (
    ROOT, FPS, RATE, FRAME_SAMPLES, CHIME_FILTER, MODEL, atomic_json, inspect_wav,
    mix_events, normalize, prepare_turn_audio, sha256_file, synthesize, tempo_turn_audio,
    write_wav,
)


def plan(episode, instructions):
    turns, events, cards = [], [], {}

    def speech(ident, text, speaker, card, phase, part):
        turns.append({"id": ident, "speaker": speaker, "name": speaker,
                      "text": text, "pause_after": 0})
        events.append({"id": ident, "audio_id": ident, "kind": "speech",
                       "card": card, "phase": phase, "part": part})

    def timed(ident, kind, card, phase, part, seconds=None, audio_id=None):
        event = {"id": ident, "kind": kind, "card": card, "phase": phase, "part": part}
        if seconds is not None:
            event["seconds"] = seconds
        if audio_id:
            event["audio_id"] = audio_id
        events.append(event)

    def group(card, recording, part, cue_id, cue, pre, post, initial=False):
        timed(f"back_before_{card}" if not initial else "start_before_example",
              "chime", card, "Beispiel" if "example" in card else "Nächste Aufgabe",
              part, audio_id="chime_start" if initial else "chime_back")
        speech(cue_id, cue, "narrator", card, "Beispiel" if "example" in card else "Aufgabe", part)
        timed(f"{card}_read", "silence", card, "Lesen", part, pre)
        for index, turn in enumerate(recording):
            speech(f"{card}_audio_{index + 1}", turn["text"], turn["speaker"],
                   card, "Jetzt hören", part)
        timed(f"{card}_answer", "silence", card, "Antwort notieren", part, post)
        timed(f"{card}_reveal", "reveal", card, "Lösung ansehen", part,
              episode["answer_reveal_seconds"], "chime_remove")

    speech("title", "Ö I F B eins Hören. Unabhängige Prüfungssimulation.",
           "narrator", "title", "Titel", 0)
    speech("setup_full", "Halten Sie Papier und einen Stift bereit. "
           "Notieren Sie zu jeder Aufgabennummer Ihre Antwort. "
           "Nach jeder Aufgabe sehen Sie kurz die richtige Lösung.",
           "narrator", "setup", "Vorbereitung", 0)
    for section, instruction in zip(episode["sections"], instructions["sections"]):
        part = section["part"]
        speech(f"instruction_{part}", instruction["instruction"], "narrator",
               f"instruction_{part}", "Anleitung", part)
        if part == 4:
            cards["p4_statements"] = {"type": "matching", "part": 4,
                                    "questions": [{"question": section["topic"],
                                                   "options": section["options"]}],
                                    "label": "Sätze a–f lesen"}
            timed("p4_statements_read", "silence", "p4_statements", "Lesen", 4, 60)
        example = section.get("example")
        if example:
            card = f"p{part}_example"
            questions = example.get("questions", [example])
            if part == 4:
                questions = [{"question": section["topic"], "options": section["options"],
                              "answer": example["answer"]}]
            cards[card] = {"type": "pair" if part == 3 else "matching" if part == 4 else "mc",
                           "part": part, "questions": questions, "label": "Beispiel"}
            group(card, example["recording"], part, f"example_cue_{part}",
                  instruction["example_cue"], 1 if part == 4 else 10, 12 if part == 4 else 10,
                  initial=part == 1)
        units = section["conversations"] if part == 3 else section["tasks"]
        for index, unit in enumerate(units):
            numbers = unit["numbers"] if part == 3 else [unit["number"]]
            card = "p%d_task_%s" % (part, "_".join(map(str, numbers)))
            questions = unit["questions"] if part == 3 else [unit]
            if part == 4:
                questions = [{"number": unit["number"], "question": section["topic"],
                              "options": section["options"], "answer": unit["answer"]}]
            cards[card] = {"type": "pair" if part == 3 else "matching" if part == 4 else "mc",
                           "part": part, "questions": questions,
                           "label": ("Aufgaben " if part == 3 else "Aufgabe ") +
                           " und ".join(map(str, numbers))}
            pre = 12 if part == 1 else 10 if part == 2 else (10 if index == 0 else 12) if part == 3 else 1
            group(card, unit["recording"], part, "cue_" + "_".join(map(str, numbers)),
                  instruction["number_cues"][index], pre, 12)
        if part == 4:
            timed("back_at_end", "chime", "end", "Hörteil beendet", 4, audio_id="chime_back")
        speech(f"end_part_{part}", instruction["end_cue"], "narrator", "end", "Teil beendet", part)
    speech("review_transition", instructions["review_transition"], "narrator",
           "summary", "Lösungen vergleichen", 0)
    timed("summary_read", "silence", "summary", "Lösungen vergleichen", 0, 10)
    speech("cta", episode["promotion"]["cta"], "narrator", "cta", "Mehr üben", 0)
    return {"turns": turns, "events": events, "cards": cards}


def voices():
    folder = ROOT.parent.parent / "shared-voices" / "gemini_3.8_flash_tts" / "austrain"
    files = {
        "narrator": "male_middle_adult_austrian.wav",
        "service_female": "female_middle_adult_austrian.wav",
        "announcement_male": "male_middle_adult_austrian.wav",
        "radio_female": "female_middle_adult_austrian.wav",
        "dialogue_female": "female_young_adult_austrian.wav",
        "dialogue_male": "male_young_adlut_austrian.wav",
        "opinion_female": "female_young_adult_austrian.wav",
        "opinion_male": "male_young_adlut_austrian.wav",
        "opinion_mature": "female_elderly_adult_austrian.wav",
    }
    result, receipt = {}, {}
    for role, name in files.items():
        audio, transcript = folder / name, folder / "phrase.txt"
        inspect_wav(audio)
        if not transcript.read_text(encoding="utf-8").strip():
            raise ValueError("Empty voice reference transcript.")
        result[role] = {"audio": str(audio), "transcript": str(transcript)}
        receipt[role] = {key: {"path": value, "sha256": sha256_file(Path(value))}
                         for key, value in result[role].items()}
    assert receipt["dialogue_female"]["audio"]["sha256"] != receipt["dialogue_male"]["audio"]["sha256"]
    assert len({receipt[role]["audio"]["sha256"] for role in
                ("opinion_female", "opinion_male", "opinion_mature")}) == 3
    return result, receipt


def prepare(build, sample, plan_only=False):
    build, sample = build.resolve(), sample.resolve()
    if build == sample or build == (ROOT / "builds").resolve():
        raise ValueError("Choose a separate individual production build.")
    episode_path = ROOT / "episodes" / "oeif_b1_listening_01.json"
    instruction_path = ROOT / "instruction_templates.json"
    episode = json.loads(episode_path.read_text(encoding="utf-8"))
    instructions = json.loads(instruction_path.read_text(encoding="utf-8"))
    speech_plan = plan(episode, instructions)
    bindings, reference_pin = voices()
    pin = {"episode_sha256": sha256_file(episode_path),
           "instructions_sha256": sha256_file(instruction_path),
           "generator_sha256": sha256_file(Path(__file__)),
           "audio_helper_sha256": sha256_file(ROOT.parent / "pilot_3d" / "prepare_audio.py"),
           "sample_helper_sha256": sha256_file(ROOT / "prepare_sample.py"),
           "sample_build": str(sample), "chime_filter": CHIME_FILTER,
           "voice_references": reference_pin,
           "source_hashes": {name: sha256_file(sample / name) for name in (
               "timeline.json", "dialogue.wav", "sample_content.json", "audio_manifest.json",
               "voice_references.json", "preview_landscape.mp4", "preview_portrait.mp4")},
           "authorization": "User requested full production on 2026-11-09 after r4 review."}
    build.mkdir(parents=True, exist_ok=True)
    if (build / "input_pin.json").exists():
        if json.loads((build / "input_pin.json").read_text(encoding="utf-8")) != pin:
            raise ValueError("Production inputs changed; choose a new build directory.")
    atomic_json(build / "input_pin.json", pin)
    atomic_json(build / "voice_references.json", reference_pin)
    atomic_json(build / "speech_plan.json", speech_plan)
    atomic_json(build / "sample_content.json", {
        "episode": episode, "instructions": instructions, "cards": speech_plan["cards"],
        "scope": "Full four-part, 20-task guided listening practice.",
    })
    print(f"Full plan: {len(speech_plan['turns'])} speech turns, "
          f"{len(speech_plan['cards'])} listening/reading cards.", flush=True)
    if plan_only:
        return
    audio = build / "audio"
    audio.mkdir(exist_ok=True)
    sample_manifest = json.loads((sample / "audio_manifest.json").read_text(encoding="utf-8"))
    sample_refs = json.loads((sample / "voice_references.json").read_text(encoding="utf-8"))
    measured, pending = {}, []
    for turn in speech_plan["turns"]:
        reused = None
        for item in sample_manifest.values():
            if item.get("text") == turn["text"] and item.get("speaker") in sample_refs:
                if sample_refs[item["speaker"]] == reference_pin[turn["speaker"]]:
                    reused = item
                    break
        if reused:
            source = Path(reused["audio"])
            if sha256_file(source) != reused["sha256"]:
                raise ValueError("Approved sample clip changed.")
            target = audio / f"{turn['id']}.wav"
            shutil.copyfile(source, target)
            measured[turn["id"]] = {**turn, **inspect_wav(target), "audio": str(target),
                                   "sha256": sha256_file(target), "atempo": 0.8,
                                   "reused_from": str(source)}
            print(f"Reused approved speech: {turn['id']}", flush=True)
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
    sfx = json.loads((ROOT / "assets" / "sfx" / "sources.json").read_text())
    for ident, role in (("chime_start", "start"), ("chime_back", "end"), ("chime_remove", "reveal")):
        asset = next(item for item in sfx["assets"] if item["file"] == sfx["selected_cues"][role])
        source = ROOT / "assets" / "sfx" / asset["file"]
        assert sha256_file(source) == asset["sha256"]
        target = audio / f"{ident}.wav"
        info = normalize(source, target, CHIME_FILTER)
        measured[ident] = {**info, "audio": str(target), "sha256": sha256_file(target),
                           "original_sha256": asset["sha256"], "filter": CHIME_FILTER}
    events, cursor = [], 0
    for planned in speech_plan["events"]:
        event = copy.deepcopy(planned)
        item = measured.get(event.get("audio_id"))
        frames = round(event["seconds"] * FPS) if "seconds" in event else math.ceil(item["frames"] / FRAME_SAMPLES)
        event.update(start_frame=cursor, end_frame=cursor + frames, start=cursor / FPS,
                     end=(cursor + frames) / FPS, duration=frames / FPS)
        if item:
            if item["frames"] > frames * FRAME_SAMPLES:
                raise ValueError(f"Full audio tail exceeds {event['id']}.")
            event.update(audio=item["audio"], sha256=item["sha256"],
                         audio_samples=item["frames"], text=item.get("text"),
                         speaker=item.get("speaker"))
        events.append(event)
        cursor += frames
    timeline = {"language": "de", "scope": "full", "fps": FPS, "sample_rate": RATE,
                "practice_mode": "guided", "answer_reveal_seconds": episode["answer_reveal_seconds"],
                "duration": cursor / FPS, "total_frames": cursor, "events": events,
                "turns": [{**measured[event["audio_id"]], "start": event["start"], "end": event["end"]}
                          for event in events if event["kind"] == "speech"]}
    write_wav(build / "dialogue.wav", mix_events(events))
    atomic_json(build / "audio_manifest.json", measured)
    atomic_json(build / "timeline.json", timeline)
    atomic_json(build / "audio_ready.json", {"frames": cursor, "duration": cursor / FPS,
                                           "dialogue_sha256": sha256_file(build / "dialogue.wav")})
    print(f"Full audio prepared: {cursor / FPS:.3f}s, {cursor} frames.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--reuse-sample", type=Path,
                        default=ROOT / "builds" / "oeif_b1_listening_sample_r4")
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    prepare(args.build, args.reuse_sample, args.plan_only)
