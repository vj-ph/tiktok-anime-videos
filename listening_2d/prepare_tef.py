"""Prepare source-pinned French speech and a single-play TEF practice timeline."""

import argparse
import copy
import json
import math
from pathlib import Path
import shutil
import sys
import wave

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "pilot_3d"))
from prepare_audio import MODEL, atomic_json, inspect_wav, prepare_turn_audio, sha256_file, synthesize
from prepare_sample import FRAME_SAMPLES, FPS, RATE, mix_events, normalize, write_wav

EPISODE = ROOT / "episodes" / "tef_canada_listening_01.json"
REVEAL_CHIME = ROOT / "assets" / "sfx" / "mixkit-software-interface-remove-2576.wav"
CHIME_SOURCES = REVEAL_CHIME.parent / "sources.json"
TIMINGS = {
    "picture_dialogue": (5, 10, 1), "public_announcement": (10, 10, 1),
    "voicemail": (10, 10, 1), "street_interview": (5, 15, 1),
    "radio_chronicle": (10, 15, 1), "interview": (20, 30, 2),
    "reportage": (10, 15, 2), "varied_document": (10, 15, 1),
}
NUMBERS = ["un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit",
           "neuf", "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize"]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_files(files):
    for path, digest in files.items():
        if sha256_file(Path(path)) != digest:
            raise ValueError(f"TEF input changed: {path}")


def reveal_mode(profile):
    mode = profile.get("answer_reveal", "after_attempt")
    if mode not in ("after_attempt", "after_exercise"):
        raise ValueError("answer_reveal must be after_attempt or after_exercise.")
    return mode


def chime_enabled(profile):
    enabled = profile.get("reveal_chime", False)
    if not isinstance(enabled, bool) or (enabled and reveal_mode(profile) != "after_exercise"):
        raise ValueError("reveal_chime must be boolean and requires after_exercise practice.")
    return enabled


def prepare_reveal_chime(audio):
    asset = next(a for a in read(CHIME_SOURCES)["assets"] if a["file"] == REVEAL_CHIME.name)
    verify_files({str(REVEAL_CHIME): asset["sha256"]})
    target = audio / "reveal_chime.wav"
    return {**normalize(REVEAL_CHIME, target, "volume=0.5"), "audio": str(target),
            "sha256": sha256_file(target), "source_audio": str(REVEAL_CHIME),
            "source_sha256": asset["sha256"], "kind": "sfx", "text": "",
            "filter": "volume=0.5", "speed": 1.0, "license": read(CHIME_SOURCES)["license"]}


def sources(config_path=EPISODE):
    episode = read(config_path)
    reveal_mode(episode)
    if (episode["schema"] != "tef_canada_reduced_listening_v1"
            or episode["language"] != "fr" or episode["fps"] != FPS
            or episode["duration_limit_seconds"] != 900):
        raise ValueError("Expected the French 24-fps, under-15-minute TEF profile.")
    base = config_path.parent
    book = (base / episode["book_root"]).resolve(strict=True)
    bank_path = (base / episode["instruction_bank"]).resolve(strict=True)
    bank = read(bank_path)
    instructions = {i["id"]: i for i in bank["instructions"]}
    if bank["chime_enabled"] or bank["added_sfx_enabled"] or set(instructions) != set(TIMINGS):
        raise ValueError("All eight families and the approved no-effects contract are required.")
    if [g["family"] for g in episode["groups"]] != list(TIMINGS):
        raise ValueError("Retain all eight task families in their approved order.")
    for family, timing in TIMINGS.items():
        row = instructions[family]
        if tuple(row[k] for k in ("reading_seconds", "response_seconds", "questions_per_recording")) != timing:
            raise ValueError(f"Changed official-sample timing: {family}")
    ledger_path = book / "content_ledger" / "full_mocks_01_02.jsonl"
    ledger = {r["question_number"]: r for r in map(json.loads, ledger_path.read_text().splitlines())
              if r.get("mock_id") == "M01"}
    manifest_path = book / "audio" / "manifest.jsonl"
    manifest = {r["track_id"]: r for r in map(json.loads, manifest_path.read_text().splitlines())}
    files = [config_path.resolve(), Path(__file__), ROOT / "prepare_sample.py",
             ROOT.parent / "pilot_3d" / "prepare_audio.py", bank_path, ledger_path, manifest_path,
             (base / episode["manuscript"]).resolve(strict=True)]
    if chime_enabled(episode):
        files += [REVEAL_CHIME, CHIME_SOURCES]
    cards, groups, used_tracks, used_questions = {}, [], set(), set()
    for group in episode["groups"]:
        family = group["family"]
        grouped = {}
        for number in group["source_questions"]:
            if number in used_questions:
                raise ValueError("A source question occurs twice.")
            used_questions.add(number)
            row = ledger[number]
            if set(row["options_fr"]) != set("ABCD") or row["correct_option"] not in "ABCD":
                raise ValueError("Every question needs four choices and one valid key.")
            card = {"number": len(cards) + 1, "source_number": number, "source_id": row["question_id"],
                    "question": row["candidate_question_fr"], "options": row["options_fr"],
                    "answer": row["correct_option"], "explanation": episode["explanations"][str(number)],
                    "visual_set_id": row.get("visual_set_id"), "family": family,
                    "source_rationale": row["rationale_en"]}
            cards[str(card["number"])] = card
            grouped.setdefault(row["track_id"], []).append(card["number"])
            if card["visual_set_id"]:
                files.extend(book / "images" / "picture_sets" / f"{card['visual_set_id']}-{c}.svg" for c in "ABCD")
        recordings = []
        for ident, numbers in grouped.items():
            track = manifest[ident]
            source_numbers = {int(i.split("-Q")[1]) for i in track["item_ids"]}
            if (ident in used_tracks or source_numbers != {cards[str(n)]["source_number"] for n in numbers}
                    or len(numbers) != TIMINGS[family][2]):
                raise ValueError("Preserve each unique recording and its complete question group.")
            used_tracks.add(ident)
            audio = book / track["output_wav"]
            inspect_wav(audio)
            files.append(audio)
            recordings.append({"id": ident, "numbers": numbers, "source_audio": str(audio),
                               "source_sha256": sha256_file(audio), "source_manifest": track,
                               "text": " ".join(s["text_original"] for s in track["segments"])})
        groups.append({**group, "instruction": instructions[family], "recordings": recordings})
    if len(cards) != 16 or len(used_tracks) != 14:
        raise ValueError("This episode requires the approved 16-question / 14-recording selection.")
    if len(episode["groups"][3]["source_questions"]) != instructions["street_interview"]["selected_speaker_count"]:
        raise ValueError("The spoken street-interview count must match the selected speakers.")
    return episode, book, cards, groups, files


def planned_speech(episode, cards, groups):
    texts = [("title", episode["title"]), ("setup", episode["setup"])]
    texts += [(f"instruction_{g['family']}", g["instruction"]["tts_text"]) for g in groups]
    if reveal_mode(episode) == "after_attempt":
        texts.append(("solutions_intro", episode["solutions_intro"]))
    for number, item in cards.items():
        texts.append((f"solution_{number}",
                      f"Question {NUMBERS[int(number) - 1]}. Réponse {item['answer']}. {item['explanation']}"))
    texts.append(("cta", episode["cta"]))
    return [{"id": ident, "text": text, "speaker": "narrator", "name": "French Compass",
             "pause_after": 0} for ident, text in texts]


def schedule(episode, groups, measured):
    events, cursor = [], 0
    mode = reveal_mode(episode)
    chime = chime_enabled(episode)

    def event(ident, kind, *, audio_id=None, seconds=None, **fields):
        nonlocal cursor
        info = measured[audio_id] if audio_id else None
        frames = math.ceil(info["frames"] / FRAME_SAMPLES) if info else round(seconds * FPS)
        if frames <= 0:
            raise ValueError("Every event must occupy at least one frame.")
        row = {"id": ident, "kind": kind, "start_frame": cursor, "end_frame": cursor + frames,
               "start": cursor / FPS, "end": (cursor + frames) / FPS, "duration": frames / FPS, **fields}
        if info:
            row.update(audio_id=audio_id, audio=info["audio"], sha256=info["sha256"],
                       audio_samples=info["frames"], text=info["text"])
        events.append(row)
        cursor += frames

    for ident in ("title", "setup"):
        event(ident, "speech", audio_id=ident, visible=True)
    for group in groups:
        family = group["family"]
        event(f"instruction_{family}", "speech", audio_id=f"instruction_{family}",
              family=family, visible=True)
        for recording in group["recordings"]:
            shared = {"family": family, "numbers": recording["numbers"], "recording_id": recording["id"]}
            event(f"read_{recording['id']}", "silence", seconds=TIMINGS[family][0], phase="Lisez les réponses", **shared)
            event(f"listen_{recording['id']}", "recording", audio_id=recording["id"], phase="Écoutez une seule fois", **shared)
            event(f"answer_{recording['id']}", "silence", seconds=TIMINGS[family][1], phase="Choisissez votre réponse", **shared)
            if mode == "after_exercise":
                if chime:
                    event(f"chime_{recording['id']}", "sfx", audio_id="reveal_chime",
                          number=recording["numbers"][0], reveal_numbers=recording["numbers"],
                          recording_id=recording["id"], visible=False)
                for number in recording["numbers"]:
                    event(f"solution_{number}", "speech", audio_id=f"solution_{number}", number=number,
                          reveal_numbers=recording["numbers"], recording_id=recording["id"], visible=False)
    if mode == "after_attempt":
        event("solutions_intro", "speech", audio_id="solutions_intro", visible=True)
        for group in groups:
            for recording in group["recordings"]:
                for number in recording["numbers"]:
                    event(f"solution_{number}", "speech", audio_id=f"solution_{number}", number=number, visible=False)
    event("cta", "speech", audio_id="cta", visible=True)
    event("outro", "silence", seconds=episode["outro_seconds"], phase="Continuez à vous entraîner")
    if cursor >= episode["duration_limit_seconds"] * FPS:
        raise ValueError(f"TEF video must be strictly below 900 seconds, measured {cursor / FPS:.3f}.")
    turns = [{**measured[e["audio_id"]], "id": e["id"], "start": e["start"], "end": e["end"],
              "visible": e.get("visible", False), "kind": e["kind"]} for e in events
             if "audio_id" in e and e["kind"] != "sfx"]
    return {"language": "fr", "fps": FPS, "sample_rate": RATE, "total_frames": cursor,
            "duration": cursor / FPS, "events": events, "turns": turns,
            "practice_mode": "reduced_all_eight_types", "chime_enabled": chime,
            "reveal_chime": chime, "answer_reveal": mode}


def prepare(build, plan_only=False, speech_cache_from=None, config_path=EPISODE):
    episode, book, cards, groups, files = sources(config_path)
    registry_path = book / "audio" / "voices" / "voices.json"
    registry = read(registry_path)
    voice = next(v for v in registry["voices"] if v["voice_id"] == episode["narrator_voice"])
    reference = book / voice["reference_audio"]
    if not voice["availability"] or not voice["voice_id"].startswith("fr_ca_qc"):
        raise ValueError("Select an available Québec narrator reference.")
    inspect_wav(reference)
    transcript = ROOT.parent / "pilot_3d" / "assets" / "voices" / "fr_ca_qc_narrator_f01_reference.txt"
    if transcript.read_text(encoding="utf-8").strip() != voice["reference_text"].strip():
        raise ValueError("Voice-registry and approved reference transcript disagree.")
    files += [registry_path, reference, transcript]
    build = build.resolve()
    build.mkdir(parents=True, exist_ok=True)
    pins = {str(p.resolve()): sha256_file(p) for p in files}
    pin_path = build / "input_pin.json"
    if pin_path.exists() and read(pin_path)["files"] != pins:
        raise ValueError("Preparation inputs changed; use a new build rather than overwrite pins.")
    atomic_json(pin_path, {"files": pins, "authorization": episode["authorization"]})
    for path in files[:8] + ([REVEAL_CHIME, CHIME_SOURCES] if chime_enabled(episode) else []):
        target = build / "preparation_sources" / path.name
        target.parent.mkdir(exist_ok=True)
        if target.exists() and sha256_file(target) != sha256_file(path):
            raise ValueError("A preserved preparation snapshot changed.")
        shutil.copy2(path, target)
    turns = planned_speech(episode, cards, groups)
    atomic_json(build / "speech_plan.json", {"turns": turns})
    atomic_json(build / "content.json", {"episode": episode, "cards": cards, "groups": groups})
    atomic_json(build / "voice_references.json", {
        "narrator": {**voice, "audio": str(reference), "sha256": sha256_file(reference)},
        "recordings": {r["id"]: [{"voice_id": s["voice_id"], "locale": s["voice_locale"]}
                                for s in r["source_manifest"]["segments"]]
                       for g in groups for r in g["recordings"]},
        "human_listening": False, "note": "Reused book recordings retain their original mixed casting; new narration is cloned Québec French."})
    script = "\n\n".join(f"[{t['id']}]\n{t['text']}" for t in turns)
    (build / "script_review.txt").write_text(script + "\n", encoding="utf-8")
    print(f"TEF: {len(cards)} questions, 14 complete book recordings, {len(turns)} new narration clips.", flush=True)
    if plan_only:
        return
    audio = build / "audio"
    audio.mkdir(exist_ok=True)
    from huggingface_hub import snapshot_download
    local_model = snapshot_download(repo_id=MODEL, local_files_only=True)
    raw = synthesize({"language": "fr", "voices": {
        "narrator": {"audio": str(reference), "reference_text": voice["reference_text"]}},
        "turns": turns}, ROOT, audio, local_model, "cpu", 8,
        cache_from=speech_cache_from.resolve() if speech_cache_from else None)
    measured = {}
    for turn, recording in zip(turns, raw):
        clean = prepare_turn_audio(turn["id"], recording, audio)
        target = audio / f"{turn['id']}.wav"
        measured[turn["id"]] = {
            **turn, **normalize(Path(clean["audio"]), target), "audio": str(target),
            "sha256": sha256_file(target), "raw_audio": recording["audio"],
            "raw_sha256": sha256_file(Path(recording["audio"])), "processed_audio": clean["audio"],
            "processed_sha256": sha256_file(Path(clean["audio"])), "speech_tempo": 1.0}
    for group in groups:
        for recording in group["recordings"]:
            target = audio / f"{recording['id']}.wav"
            measured[recording["id"]] = {
                **recording, **normalize(Path(recording["source_audio"]), target),
                "audio": str(target), "sha256": sha256_file(target), "speaker": "book_recording",
                "speech_tempo": 1.0}
    if chime_enabled(episode):
        measured["reveal_chime"] = prepare_reveal_chime(audio)
    timeline = schedule(episode, groups, measured)
    write_wav(build / "dialogue.wav", mix_events(timeline["events"]))
    atomic_json(build / "audio_manifest.json", measured)
    atomic_json(build / "timeline.json", timeline)
    verify_files(pins)
    print(f"TEF measured audio: {timeline['total_frames']} frames / {timeline['duration']:.3f}s.", flush=True)


def process(build):
    from align_words import align_build, validate_words
    timeline = read(build / "timeline.json")
    inputs = build / "alignment_inputs"
    inputs.mkdir(exist_ok=True)
    selected = [copy.deepcopy(t) for t in timeline["turns"] if t["visible"]]
    atomic_json(inputs / "timeline.json", {"language": "fr", "turns": selected})
    align_build(inputs)
    aligned = read(inputs / "timeline.json")
    by_id = {t["id"]: t for t in aligned["turns"]}
    for turn in timeline["turns"]:
        if turn["visible"]:
            measured = by_id[turn["id"]]
            turn.update(words=measured["words"], alignment_key=measured["alignment_key"])
            validate_words(turn["words"], turn["text"], turn["wav_duration"])
    timeline["word_alignment"] = aligned["word_alignment"]
    atomic_json(build / "timeline.json", timeline)
    shutil.copyfile(inputs / "word_alignment.json", build / "word_alignment.json")


def review(build):
    import torch
    from faster_whisper import WhisperModel
    from review_sample_audio import tokens
    torch.set_num_threads(4)
    model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=4, local_files_only=True)
    target = build / "speech_review_small.json"
    previous = {r["id"]: r for r in read(target)["turns"]} if target.exists() else {}
    results = []
    for ident, item in read(build / "audio_manifest.json").items():
        if item.get("kind") == "sfx":
            continue
        saved = previous.get(ident)
        if not saved or saved["audio_sha256"] != item["sha256"] or saved["expected"] != item["text"]:
            segments, _ = model.transcribe(item["audio"], language="fr", beam_size=5, vad_filter=False)
            recognized = " ".join(s.text.strip() for s in segments)
            saved = {"id": ident, "audio_sha256": item["sha256"], "expected": item["text"],
                     "recognized": recognized, "matches": tokens(item["text"]) == tokens(recognized)}
        results.append(saved)
        atomic_json(target, {"model": "faster-whisper-small", "human_listening": False,
                            "complete": False, "turns": results})
        print(f"TEF ASR {ident}: {'match' if saved['matches'] else 'review flag'}", flush=True)
    atomic_json(target, {"model": "faster-whisper-small", "human_listening": False,
                        "complete": True, "turns": results})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("plan", "prepare", "align", "review"))
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--speech-cache-from", type=Path)
    parser.add_argument("--episode", type=Path, default=EPISODE)
    args = parser.parse_args()
    if args.stage in ("plan", "prepare"):
        prepare(args.build, args.stage == "plan", args.speech_cache_from, args.episode.resolve())
    else:
        {"align": process, "review": review}[args.stage](args.build.resolve())
