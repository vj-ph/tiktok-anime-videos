"""Prepare measured speech, chimes and a frame-exact Teil 1 sample timeline."""

import argparse
import copy
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import wave

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "pilot_3d"))
from prepare_audio import (MODEL, atomic_json, inspect_wav, prepare_turn_audio,
                           sha256_file, synthesize, tempo_turn_audio)

FPS = 24
RATE = 48000
FRAME_SAMPLES = RATE // FPS
CHIME_FILTER = (
    "atempo=0.8,volume=0.6,"
    "aecho=0.8:0.9:19|31|43|59|79|103|139|181:"
    "0.16|0.14|0.12|0.10|0.08|0.06|0.04|0.02"
)

def guided_timeline(timeline, reveal_seconds=3):
    frames = float(reveal_seconds) * FPS
    if not math.isfinite(frames) or frames <= 0 or not frames.is_integer():
        raise ValueError("Answer reveals need a positive, frame-exact duration.")
    result = copy.deepcopy(timeline)
    if any(event["kind"] == "reveal" for event in result["events"]):
        raise ValueError("Source timeline already contains answer reveals.")
    events, cursor = [], 0
    for event in result["events"]:
        duration = event["end_frame"] - event["start_frame"]
        event.update(start_frame=cursor, end_frame=cursor + duration,
                     start=cursor / FPS, end=(cursor + duration) / FPS)
        events.append(event)
        cursor += duration
        if event["id"] in ("example_answer", "task1_answer"):
            events.append({
                "id": event["id"].replace("_answer", "_reveal"), "kind": "reveal",
                "phase": "Lösung ansehen", "card": event["card"],
                "start_frame": cursor, "end_frame": cursor + int(frames),
                "start": cursor / FPS, "end": (cursor + frames) / FPS,
                "duration": reveal_seconds, "audio_samples": int(frames) * FRAME_SAMPLES,
            })
            cursor += int(frames)
    result.update(events=events, total_frames=cursor, duration=cursor / FPS,
                  practice_mode="guided", answer_reveal_seconds=reveal_seconds)
    speech = {event["id"]: event for event in events if event["kind"] == "speech"}
    for turn in result["turns"]:
        turn.update(start=speech[turn["id"]]["start"], end=speech[turn["id"]]["end"])
    return result


def mix_events(events):
    blocks = bytearray()
    for event in events:
        samples = (event["end_frame"] - event["start_frame"]) * FRAME_SAMPLES
        block = b""
        if event["kind"] != "silence" and (event["kind"] != "reveal" or event.get("audio")):
            with wave.open(event["audio"], "rb") as handle:
                block = handle.readframes(handle.getnframes())
        if len(block) > samples * 2:
            raise ValueError("Audio exceeds its measured event interval.")
        blocks.extend(block + b"\0" * (samples * 2 - len(block)))
    return blocks


def reveal_sound(timeline, cue):
    result = copy.deepcopy(timeline)
    for event in result["events"]:
        if event["kind"] == "reveal":
            capacity = (event["end_frame"] - event["start_frame"]) * FRAME_SAMPLES
            if cue["frames"] > capacity:
                raise ValueError("Reveal sound and its full tail exceed the reveal interval.")
            event.update(audio=cue["audio"], sha256=cue["sha256"],
                         audio_samples=cue["frames"], sfx_id="chime_remove")
    return result


def prepare_reveal_sound(episode, audio):
    filename = Path(episode["audio"]["sfx"]["reveal_file"]).name
    sources = json.loads((ROOT / "assets" / "sfx" / "sources.json").read_text())
    asset = next(item for item in sources["assets"] if item["file"] == filename)
    source = ROOT / "assets" / "sfx" / filename
    if sha256_file(source) != asset["sha256"]:
        raise ValueError("Original remove sound changed.")
    target = audio / "chime_remove.wav"
    info = normalize(source, target, CHIME_FILTER)
    return {**info, "audio": str(target), "sha256": sha256_file(target),
            "original_sha256": asset["sha256"], "filter": CHIME_FILTER}


def retime_alignment(alignment, timeline):
    result = copy.deepcopy(alignment)
    starts = {turn["id"]: turn["start"] for turn in timeline["turns"]}
    for turn in result["turns"]:
        turn["start"] = starts[turn["id"]]
    return result


def revise(source, build):
    source, build = source.resolve(), build.resolve()
    if source == build or build.exists():
        raise ValueError("Choose a new build directory; preserve the source preview.")
    timeline = json.loads((source / "timeline.json").read_text(encoding="utf-8"))
    content = json.loads((source / "sample_content.json").read_text(encoding="utf-8"))
    episode = json.loads((ROOT / "episodes" / "oeif_b1_listening_01.json").read_text(encoding="utf-8"))
    expected = copy.deepcopy(content["episode"])
    expected.update(mode=episode["mode"], answer_reveal_seconds=episode["answer_reveal_seconds"])
    expected["audio"]["sfx"]["reveal_file"] = episode["audio"]["sfx"]["reveal_file"]
    expected["audio"]["sfx"]["placement"] = episode["audio"]["sfx"]["placement"]
    if expected != episode:
        raise ValueError("Episode speech/content changed; do not reuse the previous audio.")
    content["episode"] = episode
    if timeline.get("practice_mode") == "guided":
        if timeline["answer_reveal_seconds"] != episode["answer_reveal_seconds"]:
            raise ValueError("Source reveal duration changed; use an uninterrupted source build.")
    else:
        timeline = guided_timeline(timeline, float(episode["answer_reveal_seconds"]))
    build.mkdir(parents=True)
    audio = build / "audio"
    audio.mkdir()
    manifest = json.loads((source / "audio_manifest.json").read_text(encoding="utf-8"))
    for item in manifest.values():
        original = Path(item["audio"])
        if sha256_file(original) != item["sha256"]:
            raise ValueError("Source speech or chime changed.")
        target = audio / original.name
        shutil.copyfile(original, target)
        item["audio"] = str(target)
    for item in timeline["events"] + timeline["turns"]:
        if "audio" in item:
            item["audio"] = manifest[item.get("sfx_id", item["id"])]["audio"]
    manifest["chime_remove"] = prepare_reveal_sound(episode, audio)
    timeline = reveal_sound(timeline, manifest["chime_remove"])
    write_wav(build / "dialogue.wav", mix_events(timeline["events"]))
    for name in ("voice_references.json",
                 "speech_review.json", "short_cue_review.json"):
        shutil.copyfile(source / name, build / name)
    alignment = json.loads((source / "word_alignment.json").read_text(encoding="utf-8"))
    atomic_json(build / "word_alignment.json", retime_alignment(alignment, timeline))
    atomic_json(build / "audio_manifest.json", manifest)
    atomic_json(build / "timeline.json", timeline)
    atomic_json(build / "sample_content.json", content)
    atomic_json(build / "input_pin.json", {
        "source_build": str(source), "generator_sha256": sha256_file(Path(__file__)),
        "episode_sha256": sha256_file(ROOT / "episodes" / "oeif_b1_listening_01.json"),
        "practice_mode": "guided", "answer_reveal_seconds": episode["answer_reveal_seconds"],
        "source_hashes": {name: sha256_file(source / name) for name in (
            "input_pin.json", "timeline.json", "dialogue.wav", "sample_content.json",
            "word_alignment.json", "preview_landscape.mp4", "preview_portrait.mp4")},
    })
    print(f"Reused measured speech: {timeline['duration']:.3f} seconds with answer reveals.", flush=True)


def write_wav(path, pcm):
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(RATE)
        output.writeframes(pcm)


def normalize(source, target, effect=None):
    command = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source)]
    if effect:
        command += ["-af", effect]
    subprocess.run(command + ["-ar", str(RATE), "-ac", "1", "-c:a", "pcm_s16le",
                              str(target)], check=True)
    return inspect_wav(target)


def prepare(build):
    build = build.resolve()
    build.mkdir(parents=True, exist_ok=True)
    episode_path = ROOT / "episodes" / "oeif_b1_listening_01.json"
    instruction_path = ROOT / "instruction_templates.json"
    episode = json.loads(episode_path.read_text(encoding="utf-8"))
    instruction = json.loads(instruction_path.read_text(encoding="utf-8"))
    pin = {
        "episode_sha256": sha256_file(episode_path),
        "instructions_sha256": sha256_file(instruction_path),
        "generator_sha256": sha256_file(Path(__file__)),
        "helper_sha256": sha256_file(ROOT.parent / "pilot_3d" / "prepare_audio.py"),
        "scope": "Teil 1 instruction, example and task 1 only",
        "chime_filter": CHIME_FILTER,
    }
    receipt = build / "input_pin.json"
    if receipt.exists() and json.loads(receipt.read_text()) != pin:
        raise ValueError("Inputs changed: choose a fresh build directory.")
    atomic_json(receipt, pin)
    voices_root = ROOT.parent.parent / "shared-voices" / "gemini_3.8_flash_tts" / "austrain"
    voices = {
        "narrator": {"audio": str(voices_root / "male_middle_adult_austrian.wav"),
                     "transcript": str(voices_root / "phrase.txt")},
        "service": {"audio": str(voices_root / "female_middle_adult_austrian.wav"),
                    "transcript": str(voices_root / "phrase.txt")},
    }
    reference_pin = {}
    for role, voice in voices.items():
        inspect_wav(Path(voice["audio"]))
        reference_pin[role] = {
            key: {"path": value, "sha256": sha256_file(Path(value))}
            for key, value in voice.items()
        }
    voice_receipt = build / "voice_references.json"
    if voice_receipt.exists() and json.loads(voice_receipt.read_text()) != reference_pin:
        raise ValueError("Voice references changed: choose a fresh build directory.")
    atomic_json(voice_receipt, reference_pin)
    sample = episode["sections"][0]
    texts = [
        ("title", "narrator", "Ö I F B eins Hören. Unabhängige Prüfungssimulation."),
        ("setup", "narrator", "Diese Vorschau zeigt ein Beispiel und die erste Aufgabe. "
         "Halten Sie Papier und einen Stift bereit. Notieren Sie Ihre Antwort."),
        ("instruction", "narrator", instruction["sections"][0]["instruction"]),
        ("example_cue", "narrator", "Beispiel."),
        ("example", "service", sample["example"]["recording"][0]["text"]),
        ("number1", "narrator", "Nummer eins."),
        ("task1", "service", sample["tasks"][0]["recording"][0]["text"]),
        ("sample_end", "narrator", "Hier endet die kurze Vorschau. "
         "In der vollständigen Simulation folgt jetzt Aufgabe zwei."),
        ("cta", "narrator", "Mehr Hörübungen, Transkripte und Erklärungen finden Sie im Buch. "
         "Den Amazon-Link finden Sie in der Beschreibung oder in der Bio."),
    ]
    turns = [{"id": ident, "speaker": role, "name": role, "text": text,
              "pause_after": 0} for ident, role, text in texts]
    speech_episode = {"language": "de", "voices": voices, "turns": turns}
    audio = build / "audio"
    audio.mkdir(exist_ok=True)
    raw = synthesize(speech_episode, ROOT, audio, MODEL, "cpu", 8)
    measured = {}
    for turn, result in zip(turns, raw):
        cleaned = prepare_turn_audio(turn["id"], result, audio)
        slowed = tempo_turn_audio(turn["id"], cleaned, audio, 0.8)
        target = audio / f"{turn['id']}.wav"
        info = normalize(Path(slowed["audio"]), target)
        measured[turn["id"]] = {
            **turn, **info, "audio": str(target), "sha256": sha256_file(target),
            "raw_audio": result["audio"], "processed_audio": slowed["audio"],
            "atempo": 0.8,
        }
    sources = json.loads((ROOT / "assets" / "sfx" / "sources.json").read_text())
    for ident, role in (("chime_start", "start"), ("chime_back", "end")):
        filename = sources["selected_cues"][role]
        source = ROOT / "assets" / "sfx" / filename
        asset = next(item for item in sources["assets"] if item["file"] == filename)
        if sha256_file(source) != asset["sha256"]:
            raise ValueError(f"Original chime hash changed: {source}")
        target = audio / f"{ident}.wav"
        info = normalize(source, target, CHIME_FILTER)
        measured[ident] = {
            **info, "audio": str(target), "sha256": sha256_file(target),
            "original_sha256": asset["sha256"], "filter": CHIME_FILTER,
        }
    atomic_json(build / "audio_manifest.json", measured)
    events, pcm, cursor = [], bytearray(), 0

    def add(ident, phase, card, silence=None):
        nonlocal cursor
        item = measured.get(ident)
        if silence is None:
            with wave.open(item["audio"], "rb") as handle:
                block = handle.readframes(handle.getnframes())
            samples = len(block) // 2
            frames = math.ceil(samples / FRAME_SAMPLES)
            block += b"\0" * (frames * FRAME_SAMPLES * 2 - len(block))
        else:
            frames = round(silence * FPS)
            samples = frames * FRAME_SAMPLES
            block = b"\0" * (samples * 2)
        event = {
            "id": ident, "kind": "silence" if silence is not None else
            ("chime" if ident.startswith("chime") else "speech"),
            "phase": phase, "card": card,
            "start_frame": cursor, "end_frame": cursor + frames,
            "start": cursor / FPS, "end": (cursor + frames) / FPS,
            "duration": frames / FPS, "audio_samples": samples,
        }
        if item:
            event.update(audio=item["audio"], sha256=item["sha256"],
                         text=item.get("text"), speaker=item.get("speaker"))
        events.append(event)
        pcm.extend(block)
        cursor += frames

    add("title", "Titel", "title")
    add("setup", "Vorschau", "setup")
    add("instruction", "Anleitung", "instruction")
    add("chime_start", "Beispiel", "example")
    add("example_cue", "Beispiel", "example")
    add("example_read", "Lesen", "example", 10)
    add("example", "Jetzt hören", "example")
    add("example_answer", "Antwort notieren", "example", 10)
    add("chime_back", "Nächste Aufgabe", "task1")
    add("number1", "Aufgabe 1", "task1")
    add("task1_read", "Lesen", "task1", 12)
    add("task1", "Jetzt hören", "task1")
    add("task1_answer", "Antwort notieren", "task1", 12)
    add("chime_back", "Vorschau beendet", "end")
    add("sample_end", "Vorschau beendet", "end")
    add("cta", "Mehr üben", "cta")
    write_wav(build / "dialogue.wav", pcm)
    timeline = {
        "language": "de", "fps": FPS, "sample_rate": RATE,
        "total_frames": cursor, "duration": cursor / FPS, "events": events,
        "turns": [{**measured[event["id"]], "start": event["start"],
                   "end": event["end"]}
                  for event in events if event["kind"] == "speech"],
    }
    if episode.get("answer_reveal_seconds", 0):
        timeline = guided_timeline(timeline, episode["answer_reveal_seconds"])
        if episode["audio"]["sfx"].get("reveal_file"):
            measured["chime_remove"] = prepare_reveal_sound(episode, audio)
            timeline = reveal_sound(timeline, measured["chime_remove"])
            atomic_json(build / "audio_manifest.json", measured)
        write_wav(build / "dialogue.wav", mix_events(timeline["events"]))
    atomic_json(build / "timeline.json", timeline)
    atomic_json(build / "sample_content.json", {
        "episode": episode, "instructions": instruction,
        "scope": "Preview only: example and task 1, not a complete test.",
    })
    print(f"Prepared {timeline['total_frames']} frames at {FPS} fps: "
          f"{timeline['duration']:.3f} seconds.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--source-build", type=Path,
                        help="Reuse a preserved sample's speech/alignment for guided practice.")
    args = parser.parse_args()
    if args.build.resolve() == (ROOT / "builds").resolve():
        parser.error("Select an individual build directory, not builds itself.")
    if args.source_build:
        revise(args.source_build, args.build)
    else:
        prepare(args.build)
