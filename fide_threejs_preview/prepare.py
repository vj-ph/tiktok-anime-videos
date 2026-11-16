"""Generate local demo speech and measured words; only write inside this folder."""

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import wave

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "pilot_3d"))
from prepare_audio import MODEL, atomic_json, prepare_turn_audio, sha256_file, synthesize
from align_words import align_build


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def snapshot():
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=REPO).decode().split("\0")
    return {name: sha256_file(REPO / name) for name in names
            if name and (REPO / name).is_file() and not name.startswith(HERE.name + "/")}


def generate(build):
    build = build.resolve()
    assert build.is_relative_to(HERE / "builds"), "All outputs must stay in the new preview folder."
    build.mkdir(parents=True, exist_ok=True)
    if any(build.glob("*.mp4")):
        raise ValueError("Rendered builds are immutable; use a fresh --build.")
    if not (build / "existing_files.json").exists():
        atomic_json(build / "existing_files.json", snapshot())
    episode = read(HERE / "episode.json")
    reference_root = REPO.parent / "shared-voices" / "gemini_3.8_flash_tts" / "swiss"
    references = read(reference_root / "voices.json")
    voices = {}
    pins = {str(reference_root / "voices.json"): sha256_file(reference_root / "voices.json")}
    for role, reference in (("examiner", "male_middle_aged"), ("candidate", "female_young_adult")):
        assert any(item["voice_id"] == reference for item in references["voices"])
        voices[role] = {}
        for field in ("audio", "transcript"):
            path = reference_root / (f"{reference}.wav" if field == "audio" else f"text_{reference}.txt")
            voices[role][field] = str(path)
            pins[str(path)] = sha256_file(path)
    plan = {**episode, "voices": voices}
    atomic_json(build / "episode.json", plan)
    atomic_json(build / "voice_inputs.json", pins)
    audio = build / "audio"
    audio.mkdir(exist_ok=True)
    raw = synthesize(plan, HERE, audio, MODEL, "cpu", 8)
    turns, cursor, pieces = [], 0, []
    for turn, generated in zip(episode["turns"], raw):
        prepared = prepare_turn_audio(turn["id"], generated, audio)
        target = audio / f'{turn["id"]}.wav'
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", prepared["audio"],
                        "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(target)], check=True)
        with wave.open(str(target), "rb") as stream:
            samples = stream.getnframes()
            pcm = stream.readframes(samples)
        frames = (samples + 1999) // 2000
        pause = math.ceil(turn["pause_after"] * 24)
        item = {**turn, "audio": str(target), "sha256": sha256_file(target),
                "start_frame": cursor, "end_frame": cursor + frames,
                "start": cursor / 24, "end": (cursor + frames) / 24,
                "wav_duration": samples / 48000, "audio_samples": samples,
                "raw_sha256": sha256_file(Path(generated["audio"]))}
        turns.append(item)
        pieces.append(pcm + b"\0" * ((frames + pause) * 4000 - len(pcm)))
        cursor += frames + pause
    assert cursor < 90 * 24
    with wave.open(str(build / "dialogue.wav"), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(48000)
        stream.writeframes(b"".join(pieces))
    atomic_json(build / "timeline.json", {**episode, "turns": turns,
                                         "total_frames": cursor, "duration": cursor / 24})
    align_build(build)
    timeline = read(build / "timeline.json")
    for turn in timeline["turns"]:
        with wave.open(turn["audio"], "rb") as stream:
            import numpy as np
            values = np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2").astype(float)
        blocks = [float(np.sqrt(np.mean(values[i:i + 2000] ** 2)))
                  for i in range(0, len(values), 2000)]
        peak = max(blocks) or 1
        turn["mouth_envelope"] = [round(min(1, value / peak), 4) for value in blocks]
    atomic_json(build / "timeline.json", timeline)
    inputs = {str(p): sha256_file(p) for p in (HERE / "episode.json", Path(__file__),
              REPO / "pilot_3d" / "prepare_audio.py", REPO / "pilot_3d" / "align_words.py")}
    atomic_json(build / "audio_receipt.json", dict(
        files={str(build / "dialogue.wav"): sha256_file(build / "dialogue.wav"),
               str(build / "timeline.json"): sha256_file(build / "timeline.json")},
        inputs=inputs, voices=pins, note=episode["voice_note"]))
    print(f"Prepared {cursor} frames / {cursor / 24:.3f}s, with actual word alignments.", flush=True)


def asr(build):
    from faster_whisper import WhisperModel
    from huggingface_hub import snapshot_download
    path = snapshot_download("Systran/faster-whisper-small", local_files_only=True)
    model = WhisperModel(path, device="cpu", compute_type="int8", cpu_threads=4)
    checks = []
    for turn in read(build / "timeline.json")["turns"]:
        segments, _ = model.transcribe(turn["audio"], language="de", beam_size=5,
                                       vad_filter=False, condition_on_previous_text=False)
        recognized = " ".join(s.text.strip() for s in segments)
        checks.append(dict(id=turn["id"], expected=turn["text"], recognized=recognized))
    atomic_json(build / "speech_review.json", dict(
        model="Systran/faster-whisper-small", turns=checks,
        note="Independent unprompted ASR, not human listening or Swiss-accent certification."))
    print(json.dumps(checks, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("prepare", "asr"))
    parser.add_argument("--build", type=Path, default=HERE / "builds" / "preview_swiss_r1")
    args = parser.parse_args()
    {"prepare": generate, "asr": asr}[args.stage](args.build.resolve())
