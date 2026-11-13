"""Prepare approved original B2 listening speech on the frame/sample clock."""

import argparse
import copy
import json
import math
from pathlib import Path

from prepare_full import voices
from prepare_sample import (
    ROOT, FPS, RATE, FRAME_SAMPLES, MODEL, CHIME_FILTER, atomic_json,
    inspect_wav, mix_events, normalize, prepare_turn_audio, sha256_file,
    synthesize, tempo_turn_audio, write_wav,
)

EPISODE = ROOT / "episodes" / "oeif_b2_listening_01.json"
REVIEW = ROOT / "builds" / "oeif_b2_listening_script_review_r1"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def approved_episode():
    episode = read(EPISODE)
    review, approval = read(REVIEW / "review_resolution.json"), read(REVIEW / "user_approval.json")
    digest = sha256_file(EPISODE)
    if not (digest == approval["episode_sha256"] == review["reviewed_episode_sha256"]
            and review["changed_item_recheck"]["decision"] == "pass"
            and review["changed_item_recheck"]["mandatory_fixes_remaining"] == 0):
        raise ValueError("B2 script review and user approval must bind the exact episode.")
    return episode


def plan(episode):
    turns, events, cards = [], [], {}

    def speech(ident, text, card, phase, part, speaker="narrator"):
        turns.append(dict(id=ident, speaker=speaker, name=speaker, text=text, pause_after=0))
        events.append(dict(id=ident, kind="speech", audio_id=ident, card=card, phase=phase, part=part))

    def timed(ident, kind, card, phase, part, seconds=None, audio_id=None):
        event = dict(id=ident, kind=kind, card=card, phase=phase, part=part)
        if seconds is not None:
            event["seconds"] = seconds
        if audio_id:
            event["audio_id"] = audio_id
        events.append(event)

    speech("title", episode["opening"]["text"], "title", "Titel", 0)
    for section in episode["sections"]:
        part = section["part"]
        speech(f"instruction_{part}", section["instruction"], f"instruction_{part}", "Anleitung", part)
        groups = section["groups"]
        for group in groups:
            cards[group["id"]] = {
                "type": "statements", "part": part, "questions": copy.deepcopy(group["questions"]),
                "label": f"Teil {part} · Richtig oder falsch?",
            }
        first_card = groups[0]["id"]
        if part < 3:
            timed(f"part_{part}_read", "silence", first_card, "Lesen", part,
                  episode["timing"][f"part_{part}"]["read_seconds"])
            timed(f"part_{part}_start", "chime", first_card, "Jetzt hören", part,
                  audio_id="chime_start")
        for group in groups:
            card = group["id"]
            if part == 3:
                speech(f"{card}_cue", group["number_cue"], card, "Aufgabe", part)
            for turn in group["recording"]:
                speech(turn["id"], turn["text"], card, "Jetzt hören", part, turn["speaker"])
            if part == 2:
                speech("checking_instruction", section["checking_instruction"], "checking_instruction",
                       "Antworten prüfen", part)
                timed(f"{card}_answer", "silence", card, "Antworten prüfen", part, 30)
            else:
                timed(f"{card}_answer", "silence", card, "Antwort notieren", part, 15)
            timed(f"{card}_reveal", "reveal", card, "Lösung ansehen", part, 3, "chime_remove")
            timed(f"{card}_transition", "chime", card, "Nächste Aufgabe" if part == 3 else "Teil beendet",
                  part, audio_id="chime_back")
        speech("end_test" if part == 3 else f"end_part_{part}", section["ending"], "end",
               "Hören beendet" if part == 3 else "Teil beendet", part)
    timed("summary_read", "silence", "summary", "Lösungen vergleichen", 0, 15)
    speech("cta", episode["promotion"]["cta"], "cta", "Mehr üben", 0)
    return dict(turns=turns, events=events, cards=cards)


def schedule(planned, measured):
    result, cursor = [], 0
    for original in planned:
        event = copy.deepcopy(original)
        item = measured.get(event.get("audio_id"))
        frames = (round(event["seconds"] * FPS) if "seconds" in event
                  else math.ceil(item["frames"] / FRAME_SAMPLES))
        event.update(start_frame=cursor, end_frame=cursor + frames, start=cursor / FPS,
                     end=(cursor + frames) / FPS, duration=frames / FPS)
        if item:
            if item["frames"] > frames * FRAME_SAMPLES:
                raise ValueError(f"Audio tail exceeds {event['id']}.")
            event.update(audio=item["audio"], sha256=item["sha256"],
                         audio_samples=item["frames"], text=item.get("text"), speaker=item.get("speaker"))
        result.append(event)
        cursor += frames
    turns = [{**measured[e["audio_id"]], "id": e["id"], "audio_id": e["audio_id"],
              "start": e["start"], "end": e["end"]} for e in result if e["kind"] == "speech"]
    return dict(language="de", scope="full", fps=FPS, sample_rate=RATE, practice_mode="guided",
                answer_reveal_seconds=3, duration=cursor / FPS, total_frames=cursor,
                events=result, turns=turns)


def prepare(build, plan_only=False, cache_from=None):
    build = build.resolve()
    episode = approved_episode()
    all_bindings, all_refs = voices()
    roles = {"narrator": "narrator", "radio_female": "radio_female",
             "dialogue_male": "dialogue_male", "dialogue_female": "dialogue_female",
             "announcement_male": "announcement_male", "announcement_female": "opinion_mature"}
    bindings = {role: all_bindings[source] for role, source in roles.items()}
    refs = {role: all_refs[source] for role, source in roles.items()}
    files = [EPISODE, Path(__file__), ROOT / "prepare_full.py", ROOT / "prepare_sample.py",
             ROOT.parent / "pilot_3d" / "prepare_audio.py",
             REVIEW / "review_resolution.json", REVIEW / "user_approval.json",
             EPISODE.parent / episode["source"]["book"],
             EPISODE.parent / episode["source"]["model_transcript"]["path"],
             ROOT / "assets" / "sfx" / "sources.json"]
    if cache_from:
        cache_from = cache_from.resolve(strict=True)
        for cache in sorted(cache_from.glob("*.cache.json")):
            files.extend((cache, cache.with_suffix("").with_suffix(".wav")))
    pins = dict(files={str(p.resolve()): sha256_file(p) for p in files}, voices=refs,
                book={str((EPISODE.parent / episode["promotion"]["cover_source"]).resolve()):
                      episode["promotion"]["cover_sha256"]})
    sfx = read(ROOT / "assets" / "sfx" / "sources.json")
    selected_sfx = {}
    for ident, role in (("chime_start", "start"), ("chime_back", "end"), ("chime_remove", "reveal")):
        asset = next(a for a in sfx["assets"] if a["file"] == sfx["selected_cues"][role])
        source = ROOT / "assets" / "sfx" / asset["file"]
        if sha256_file(source) != asset["sha256"]:
            raise ValueError("Original sound effect changed.")
        selected_sfx[ident] = (source, asset)
    for relative, expected in ((episode["source"]["book"], episode["source"]["book_sha256"]),
                               (episode["source"]["model_transcript"]["path"],
                                episode["source"]["model_transcript"]["sha256"]),
                               (episode["promotion"]["cover_source"], episode["promotion"]["cover_sha256"])):
        if sha256_file(EPISODE.parent / relative) != expected:
            raise ValueError(f"B2 source changed: {relative}")
    build.mkdir(parents=True, exist_ok=True)
    if (build / "input_pin.json").exists() and read(build / "input_pin.json") != pins:
        raise ValueError("B2 preparation inputs changed; use a fresh build.")
    atomic_json(build / "input_pin.json", pins)
    atomic_json(build / "voice_references.json", refs)
    speech_plan = plan(episode)
    atomic_json(build / "speech_plan.json", speech_plan)
    atomic_json(build / "sample_content.json", dict(
        episode=episode, cards=speech_plan["cards"],
        portrait_interview=read(REVIEW / "user_approval.json")["portrait_interview_layout"]))
    print(f"B2 plan: {len(speech_plan['turns'])} speech turns; {len(speech_plan['events'])} events.", flush=True)
    if plan_only:
        return
    audio = build / "audio"
    audio.mkdir(exist_ok=True)
    measured = {}
    for ident, (source, asset) in selected_sfx.items():
        target = audio / f"{ident}.wav"
        measured[ident] = {**normalize(source, target, CHIME_FILTER), "audio": str(target),
                           "sha256": sha256_file(target), "original_sha256": asset["sha256"],
                           "filter": CHIME_FILTER}
    if measured["chime_remove"]["frames"] > 3 * RATE:
        raise ValueError("Complete remove chime tail exceeds the three-second reveal.")
    raw = synthesize(dict(language="de", voices=bindings, turns=speech_plan["turns"]),
                     ROOT, audio, MODEL, "cpu", 8, cache_from=cache_from)
    for turn, result in zip(speech_plan["turns"], raw):
        cleaned = prepare_turn_audio(turn["id"], result, audio)
        slowed = tempo_turn_audio(turn["id"], cleaned, audio, 0.8)
        target = audio / f"{turn['id']}.wav"
        measured[turn["id"]] = {
            **turn, **normalize(Path(slowed["audio"]), target), "audio": str(target),
            "sha256": sha256_file(target), "raw_audio": result["audio"],
            "raw_sha256": sha256_file(Path(result["audio"])), "processed_audio": slowed["audio"],
            "processed_sha256": sha256_file(Path(slowed["audio"])), "atempo": 0.8,
        }
    timeline = schedule(speech_plan["events"], measured)
    write_wav(build / "dialogue.wav", mix_events(timeline["events"]))
    atomic_json(build / "audio_manifest.json", measured)
    atomic_json(build / "timeline.json", timeline)
    print(f"B2 measured audio ready: {timeline['total_frames']} frames / {timeline['duration']:.3f}s.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--reuse-cache", type=Path)
    args = parser.parse_args()
    prepare(args.build, args.plan_only, args.reuse_cache)
