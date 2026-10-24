#!/usr/bin/env python3
"""Generate this pilot's Qwen speech, Rhubarb mouth cues and frame-exact audio.

Run with the Qwen environment's Python. Imports of torch/numpy/soundfile are
deliberately lazy: timing, validation and cache tests need only the stdlib.
The output directory contains timeline.json, dialogue.wav, subtitles.srt and
audio/{id}-{content_hash}.wav, {id}.mouth.json and cache/provenance sidecars.
Raw synthesized WAVs remain unchanged. Separately fingerprinted .prepared.wav
files shorten only leading quiet >0.5s or trailing quiet >0.8s at -45dBFS,
preserving 180ms of sample padding. No interior samples are removed or altered.
Timeline turn boundaries include frame padding; wav_duration is unpadded.
Subtitles end at the measured WAV end, not at an invented word boundary.
"""

from __future__ import annotations

import argparse
import array
import hashlib
import importlib.metadata
import json
import math
import re
import shutil
import subprocess
import sys
import textwrap
import time
import wave
from fractions import Fraction
from pathlib import Path
from typing import Any

from build_paths import BUILDS, build_directory, resolve_build_reference
from episode_profiles import language_code, language_profile

ROOT = Path(__file__).resolve().parent
MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
DEFAULT_TTS_THREADS = 8
SAMPLE_RATE = 48_000
CACHE_SCHEMA = 1
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
SHAPES = frozenset("ABCDEFGHX")


def number(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number.")
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f"{label} must be finite and {'positive' if positive else 'nonnegative'}.")
    return float(value)


def nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string.")
    return value


def validate_episode(episode: Any) -> None:
    if not isinstance(episode, dict):
        raise ValueError("Episode must be a JSON object.")
    language_code(episode)
    fps = episode.get("fps")
    if isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= 240:
        raise ValueError("fps must be an integer between 1 and 240.")
    if SAMPLE_RATE % fps:
        raise ValueError("fps must divide 48000 for sample-exact frame boundaries.")
    for field in ("intro_seconds", "outro_seconds"):
        number(episode.get(field), field)
    voices = episode.get("voices")
    if not isinstance(voices, dict) or not voices:
        raise ValueError("voices must be a nonempty object.")
    for role, voice in voices.items():
        if not isinstance(role, str) or not SAFE_ID.fullmatch(role):
            raise ValueError(f"Unsafe voice role: {role!r}")
        if not isinstance(voice, dict):
            raise ValueError(f"voices.{role} must be an object.")
        nonempty(voice.get("audio"), f"voices.{role}.audio")
        if ("transcript" in voice) == ("reference_text" in voice):
            raise ValueError(f"voices.{role} needs exactly one of transcript or reference_text.")
        field = "transcript" if "transcript" in voice else "reference_text"
        nonempty(voice.get(field), f"voices.{role}.{field}")
    turns = episode.get("turns")
    if not isinstance(turns, list) or not turns:
        raise ValueError("turns must be a nonempty array.")
    ids: set[str] = set()
    for index, turn in enumerate(turns):
        if not isinstance(turn, dict):
            raise ValueError(f"turns[{index}] must be an object.")
        turn_id = turn.get("id")
        if not isinstance(turn_id, str) or not SAFE_ID.fullmatch(turn_id):
            raise ValueError(f"Unsafe turn id: {turn_id!r}")
        if turn_id in ids:
            raise ValueError(f"Duplicate turn id: {turn_id}")
        ids.add(turn_id)
        role = turn.get("speaker")
        if not isinstance(role, str) or role not in voices:
            raise ValueError(f"Turn {turn_id}: unknown speaker role {role!r}.")
        if "role" in turn and turn["role"] != role:
            raise ValueError(f"Turn {turn_id}: role and speaker disagree.")
        nonempty(turn.get("name"), f"turn {turn_id}.name")
        text = nonempty(turn.get("text"), f"turn {turn_id}.text")
        if any(char in text for char in ("\r", "\n", "\x00")):
            raise ValueError(f"Turn {turn_id}: text must be a single spoken paragraph.")
        number(turn.get("pause_after"), f"turn {turn_id}.pause_after")


def ceil_frames(seconds: float, fps: int) -> int:
    number(seconds, "seconds")
    value = Fraction(str(seconds)) * fps
    return (value.numerator + value.denominator - 1) // value.denominator


def wav_frames_to_video_frames(samples: int, sample_rate: int, fps: int) -> int:
    if samples <= 0 or sample_rate <= 0 or fps <= 0:
        raise ValueError("Sample count, sample rate and fps must be positive.")
    return (samples * fps + sample_rate - 1) // sample_rate


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def content_hash(value: Any) -> str:
    serialized = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    partial = path.with_name(path.name + ".part")
    partial.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    partial.replace(path)


def atomic_text(path: Path, text: str) -> None:
    partial = path.with_name(path.name + ".part")
    partial.write_text(text, encoding="utf-8")
    partial.replace(path)


def inspect_wav(path: Path) -> dict[str, Any]:
    with wave.open(str(path), "rb") as handle:
        frames, rate = handle.getnframes(), handle.getframerate()
        if handle.getnchannels() != 1 or handle.getsampwidth() != 2 or handle.getcomptype() != "NONE":
            raise ValueError(f"{path}: expected mono PCM16 WAV.")
        if frames <= 0 or rate <= 0:
            raise ValueError(f"{path}: empty/invalid WAV.")
        data = handle.readframes(frames)
        if len(data) != frames * 2:
            raise ValueError(f"{path}: truncated WAV samples.")
        if not any(data):
            raise ValueError(f"{path}: refusing all-silent speech.")
    return {"frames": frames, "sample_rate": rate, "wav_duration": frames / rate}


def synthesis_settings(model: str, device: str, threads: int, text: str,
                       language: str = "de") -> dict[str, Any]:
    return {
        "model": model,
        "device": device,
        "dtype": "float32",
        "attn_implementation": "sdpa",
        "threads": threads,
        "interop_threads": min(threads, 4),
        "seed": 0,
        "language": language_profile({"language": language})["tts"],
        "x_vector_only_mode": False,
        "non_streaming_mode": True,
        "max_new_tokens": max(256, min(1536, math.ceil(len(text) * 6))),
        "do_sample": True,
        "top_k": 50,
        "top_p": 1.0,
        "temperature": 0.9,
        "repetition_penalty": 1.05,
        "subtalker_dosample": True,
        "subtalker_top_k": 50,
        "subtalker_top_p": 1.0,
        "subtalker_temperature": 0.9,
        "output_subtype": "PCM_16",
        "reference_input": "soundfile_float32_mono_tuple",
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("qwen-tts", "torch", "transformers", "soundfile", "numpy")
        },
    }


def make_cache_payload(turn: dict[str, Any], reference_audio: Path, transcript: Path | None,
                       settings: dict[str, Any], *, reference_text: str | None = None) -> dict[str, Any]:
    if transcript is not None:
        if reference_text is not None:
            raise ValueError("Choose a transcript file or inline reference_text, not both.")
        reference_text = transcript.read_text(encoding="utf-8").strip()
        transcript_hash = sha256_file(transcript)
    else:
        nonempty(reference_text, "reference_text")
        reference_text = reference_text.strip()
        transcript_hash = hashlib.sha256(reference_text.encode("utf-8")).hexdigest()
    nonempty(reference_text, f"Reference transcript {transcript}")
    return {
        "schema": CACHE_SCHEMA,
        "speaker": turn["speaker"],
        "text": turn["text"],
        "reference_audio_sha256": sha256_file(reference_audio),
        "reference_transcript_sha256": transcript_hash,
        "reference_text": reference_text,
        "settings": settings,
    }


def load_audio_cache(path: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    metadata_path = path.with_suffix(".cache.json")
    if not path.exists() and not metadata_path.exists():
        return None
    if not path.is_file() or not metadata_path.is_file():
        print(f"Regenerating incomplete audio cache: {path.name}", flush=True)
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("cache metadata must be an object")
        if metadata["cache_key"] != content_hash(payload) or metadata["payload"] != payload:
            raise ValueError("cache settings/reference hash mismatch")
        info = inspect_wav(path)
        if metadata["wav_sha256"] != sha256_file(path) or metadata["audio_info"] != info:
            raise ValueError("cached WAV content/measurement mismatch")
    except (OSError, ValueError, KeyError, TypeError, EOFError, wave.Error) as error:
        print(f"Regenerating malformed audio cache {path.name}: {error}", flush=True)
        return None
    return info


def import_audio_cache(cache_dir: Path, target: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    source = cache_dir / target.name
    info = load_audio_cache(source, payload)
    if info is None:
        return None
    for original, destination in ((source, target), (source.with_suffix(".cache.json"), target.with_suffix(".cache.json"))):
        partial = destination.with_name(destination.name + ".part")
        shutil.copy2(original, partial)
        partial.replace(destination)
    verified = load_audio_cache(target, payload)
    if verified is None:
        raise ValueError(f"Speech cache changed while importing: {source}")
    print(f"Imported verified speech cache: {source}", flush=True)
    return verified


def synthesize(episode: dict[str, Any], episode_dir: Path, audio_dir: Path,
               model_name: str, device: str, threads: int,
               cache_from: Path | None = None) -> list[dict[str, Any]]:
    references = {}
    for role, voice in episode["voices"].items():
        reference_audio = (episode_dir / voice["audio"]).resolve(strict=True)
        transcript = ((episode_dir / voice["transcript"]).resolve(strict=True)
                      if "transcript" in voice else None)
        inspect_wav(reference_audio)
        references[role] = (reference_audio, transcript)
    model = sf = torch = None
    prompts: dict[str, Any] = {}
    results = []
    for turn in episode["turns"]:
        settings = synthesis_settings(model_name, device, threads, turn["text"], language_code(episode))
        reference_audio, transcript = references[turn["speaker"]]
        payload = make_cache_payload(turn, reference_audio, transcript, settings,
                                     reference_text=episode["voices"][turn["speaker"]].get("reference_text"))
        key = content_hash(payload)
        audio_path = audio_dir / f"{turn['id']}-{key[:20]}.wav"
        info = load_audio_cache(audio_path, payload)
        if info is None and cache_from is not None:
            info = import_audio_cache(cache_from, audio_path, payload)
        if info is None:
            if model is None:
                import numpy as np
                import soundfile as sf
                import torch
                from qwen_tts import Qwen3TTSModel

                torch.set_num_threads(threads)
                torch.set_num_interop_threads(min(threads, 4))
                torch.manual_seed(settings["seed"])
                print(f"Loading {model_name} on {device}, float32, {threads} threads", flush=True)
                model = Qwen3TTSModel.from_pretrained(
                    model_name, device_map=device, dtype=torch.float32, attn_implementation="sdpa",
                )
            role = turn["speaker"]
            if role not in prompts:
                reference, reference_rate = sf.read(reference_audio, dtype="float32", always_2d=False)
                if reference.ndim != 1 or not np.isfinite(reference).all():
                    raise ValueError(f"Invalid mono reference samples for {role}")
                print(f"Creating reusable clone prompt: {role}", flush=True)
                prompts[role] = model.create_voice_clone_prompt(
                    ref_audio=(reference, reference_rate),
                    ref_text=payload["reference_text"],
                    x_vector_only_mode=settings["x_vector_only_mode"],
                )
            kwargs = {name: settings[name] for name in (
                "language", "non_streaming_mode", "max_new_tokens", "do_sample",
                "top_k", "top_p", "temperature", "repetition_penalty", "subtalker_dosample",
                "subtalker_top_k", "subtalker_top_p", "subtalker_temperature",
            )}
            started = time.monotonic()
            print(f"Synthesizing {turn['id']} ({role}): {turn['text']}", flush=True)
            torch.manual_seed(settings["seed"])
            wavs, sample_rate = model.generate_voice_clone(
                text=turn["text"], voice_clone_prompt=prompts[role], **kwargs,
            )
            if len(wavs) != 1 or sample_rate <= 0:
                raise ValueError(f"Turn {turn['id']}: invalid Qwen output count/sample rate.")
            samples = np.asarray(wavs[0])
            if samples.ndim != 1 or samples.size == 0 or not np.isfinite(samples).all():
                raise ValueError(f"Turn {turn['id']}: invalid Qwen waveform.")
            if np.max(np.abs(samples)) == 0 or np.max(np.abs(samples)) > 1:
                raise ValueError(f"Turn {turn['id']}: silent or out-of-range Qwen waveform.")
            if samples.size / sample_rate >= (settings["max_new_tokens"] - 2) / 12.5:
                raise RuntimeError(
                    f"Turn {turn['id']}: possible token-limit truncation "
                    f"({samples.size / sample_rate:.3f}s, budget {settings['max_new_tokens']}); "
                    "inspect generation settings before retrying."
                )
            partial = audio_path.with_name(audio_path.name + ".part")
            sf.write(partial, samples, sample_rate, format="WAV", subtype="PCM_16")
            info = inspect_wav(partial)
            partial.replace(audio_path)
            atomic_json(audio_path.with_suffix(".cache.json"), {
                "cache_key": key,
                "payload": payload,
                "wav_sha256": sha256_file(audio_path),
                "audio_info": info,
                "synthesis_seconds": time.monotonic() - started,
            })
            print(f"  {info['wav_duration']:.3f}s audio; {time.monotonic() - started:.1f}s synthesis", flush=True)
        else:
            print(f"Audio cache hit {turn['id']}: {info['wav_duration']:.3f}s", flush=True)
        results.append({"audio": str(audio_path.resolve()), **info})
    return results


def preprocessing_settings() -> dict[str, Any]:
    return {
        "algorithm": "pcm16_peak_edge_quiet_v1",
        "quiet_threshold_dbfs": -45.0,
        "trim_lead_if_exceeds_seconds": 0.5,
        "trim_tail_if_exceeds_seconds": 0.8,
        "padding_seconds": 0.18,
        "full_scale": 32768,
        "interior_trimming": False,
        "time_stretch": False,
    }


def quiet_trim_bounds(pcm: bytes, sample_rate: int, settings: dict[str, Any]) -> dict[str, int]:
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, int) or sample_rate <= 0:
        raise ValueError("Trimming sample rate must be a positive integer.")
    if not pcm or len(pcm) % 2:
        raise ValueError("Trimming requires complete, nonempty PCM16 samples.")
    threshold_db = settings["quiet_threshold_dbfs"]
    if (isinstance(threshold_db, bool) or not isinstance(threshold_db, (int, float))
            or not math.isfinite(threshold_db) or not -96 <= threshold_db <= -40):
        raise ValueError("Quiet threshold must be finite and between -96 and -40 dBFS.")
    if settings["full_scale"] != 32768 or settings["interior_trimming"] or settings["time_stretch"]:
        raise ValueError("Only unchanged PCM16 samples and edge trimming are supported.")
    lead_limit = number(settings["trim_lead_if_exceeds_seconds"], "leading quiet limit")
    tail_limit = number(settings["trim_tail_if_exceeds_seconds"], "trailing quiet limit")
    padding = number(settings["padding_seconds"], "edge padding", positive=True)
    samples = array.array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    threshold = math.floor(settings["full_scale"] * 10 ** (threshold_db / 20))
    first = next((index for index, value in enumerate(samples) if abs(value) > threshold), None)
    if first is None:
        raise ValueError("No samples exceed the conservative quiet threshold; refusing to trim this WAV.")
    last = len(samples) - next(
        index for index, value in enumerate(reversed(samples)) if abs(value) > threshold
    )
    padding_count = math.ceil(Fraction(str(padding)) * sample_rate)
    tail = len(samples) - last
    start = max(0, first - padding_count) if Fraction(first, sample_rate) > Fraction(str(lead_limit)) else 0
    end = min(len(samples), last + padding_count) if Fraction(tail, sample_rate) > Fraction(str(tail_limit)) else len(samples)
    return {
        "start_sample": start,
        "end_sample_exclusive": end,
        "first_active_sample": first,
        "last_active_sample_exclusive": last,
        "lead_quiet_samples": first,
        "tail_quiet_samples": tail,
        "removed_lead_samples": start,
        "removed_tail_samples": len(samples) - end,
        "padding_samples": padding_count,
        "quiet_threshold_pcm16": threshold,
    }


def preprocessing_payload(raw_sha256: str, raw_info: dict[str, Any], settings: dict[str, Any],
                          bounds: dict[str, int]) -> dict[str, Any]:
    return {
        "schema": 1,
        "stage": "edge_quiet_preprocessing",
        "raw_sha256": raw_sha256,
        "raw_audio_info": raw_info,
        "settings": settings,
        "sample_bounds": bounds,
    }


def prepare_turn_audio(turn_id: str, raw: dict[str, Any], audio_dir: Path) -> dict[str, Any]:
    source = Path(raw["audio"])
    if "preprocessing" in raw or source.name.endswith(".prepared.wav"):
        raise ValueError("Preprocessing requires raw synthesis audio, never a previously trimmed WAV.")
    source = source.resolve(strict=True)
    raw_info = inspect_wav(source)
    if any(raw_info[field] != raw[field] for field in raw_info):
        raise ValueError(f"Turn {turn_id}: raw WAV measurements changed before preprocessing.")
    with wave.open(str(source), "rb") as handle:
        pcm = handle.readframes(raw_info["frames"])
    settings = preprocessing_settings()
    bounds = quiet_trim_bounds(pcm, raw_info["sample_rate"], settings)
    raw_hash = sha256_file(source)
    payload = preprocessing_payload(raw_hash, raw_info, settings, bounds)
    key = content_hash(payload)
    target = audio_dir / f"{turn_id}-{key[:20]}.prepared.wav"
    info = load_audio_cache(target, payload)
    expected_count = bounds["end_sample_exclusive"] - bounds["start_sample"]
    if info is not None and (
        info["frames"] != expected_count or info["sample_rate"] != raw_info["sample_rate"]
    ):
        print(f"Regenerating malformed preprocessing cache {turn_id}: sample bounds disagree", flush=True)
        info = None
    if info is None:
        partial = target.with_name(target.name + ".part")
        with wave.open(str(partial), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(raw_info["sample_rate"])
            output.writeframes(pcm[bounds["start_sample"] * 2:bounds["end_sample_exclusive"] * 2])
        info = inspect_wav(partial)
        if info["frames"] != expected_count or info["sample_rate"] != raw_info["sample_rate"]:
            raise ValueError(f"Turn {turn_id}: preprocessing changed samples unexpectedly.")
        partial.replace(target)
        atomic_json(target.with_suffix(".cache.json"), {
            "cache_key": key,
            "payload": payload,
            "raw_audio": str(source),
            "wav_sha256": sha256_file(target),
            "audio_info": info,
        })
    removed = bounds["removed_lead_samples"] + bounds["removed_tail_samples"]
    print(f"Prepared {turn_id}: {raw_info['wav_duration']:.6f}s -> {info['wav_duration']:.6f}s; "
          f"removed {removed} edge-quiet samples", flush=True)
    return {
        "audio": str(target.resolve()),
        **info,
        "raw_audio": str(source),
        "raw_sample_count": raw_info["frames"],
        "raw_wav_duration": raw_info["wav_duration"],
        "preprocessing": {"cache_key": key, **payload},
    }


def validate_cues(cues: Any, duration: float) -> list[dict[str, Any]]:
    number(duration, "WAV duration", positive=True)
    if not isinstance(cues, list) or not cues:
        raise ValueError("Rhubarb mouthCues must be a nonempty array.")
    validated = []
    previous_end = 0.0
    for index, cue in enumerate(cues):
        if not isinstance(cue, dict):
            raise ValueError(f"Mouth cue {index} must be an object.")
        start = number(cue.get("start"), f"mouth cue {index}.start")
        end = number(cue.get("end"), f"mouth cue {index}.end")
        value = cue.get("value")
        if not isinstance(value, str) or value not in SHAPES:
            raise ValueError(f"Mouth cue {index}: invalid shape {value!r}.")
        if end <= start or start < previous_end:
            raise ValueError(f"Mouth cue {index}: reversed or overlapping interval.")
        # Rhubarb serializes seconds to centiseconds; only its final rounding
        # (at most half a centisecond) may extend past the exact sample count.
        if start >= duration or end > duration + 0.005001:
            raise ValueError(f"Mouth cue {index}: interval exceeds WAV duration {duration}.")
        end = min(end, duration)
        validated.append({"start": start, "end": end, "value": value})
        previous_end = end
    return validated


def run_rhubarb(turn: dict[str, Any], audio: dict[str, Any], audio_dir: Path,
                binary: Path, binary_hash: str, threads: int) -> list[dict[str, Any]]:
    mouth_path = audio_dir / f"{turn['id']}.mouth.json"
    metadata_path = audio_dir / f"{turn['id']}.mouth.cache.json"
    dialog_path = audio_dir / f"{turn['id']}.txt"
    payload = {
        "schema": CACHE_SCHEMA,
        "wav_sha256": sha256_file(Path(audio["audio"])),
        "text": turn["text"],
        "rhubarb_sha256": binary_hash,
        "recognizer": "phonetic",
        "format": "json",
        "extendedShapes": "GHX",
        "threads": threads,
        "preprocessing_key": audio.get("preprocessing", {}).get("cache_key"),
    }
    key = content_hash(payload)
    if mouth_path.is_file() and metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict):
                raise ValueError("mouth cache metadata must be an object")
            if metadata["cache_key"] != key or metadata["mouth_sha256"] != sha256_file(mouth_path):
                raise ValueError("mouth cache fingerprint mismatch")
            result = json.loads(mouth_path.read_text(encoding="utf-8"))
            if not isinstance(result, dict):
                raise ValueError("mouth result must be an object")
            cues = validate_cues(result["mouthCues"], audio["wav_duration"])
        except (OSError, ValueError, TypeError, KeyError) as error:
            print(f"Regenerating malformed/stale mouth cache {turn['id']}: {error}", flush=True)
        else:
            print(f"Mouth cache hit {turn['id']}: {len(cues)} cues", flush=True)
            return cues
    atomic_text(dialog_path, turn["text"] + "\n")
    partial = mouth_path.with_name(mouth_path.name + ".part")
    print(f"Rhubarb phonetic {turn['id']}", flush=True)
    subprocess.run([
        str(binary), "-r", "phonetic", "-f", "json", "--extendedShapes", "GHX",
        "--threads", str(threads), "-d", str(dialog_path), "-o", str(partial), audio["audio"],
    ], check=True)
    result = json.loads(partial.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError(f"Turn {turn['id']}: Rhubarb JSON must be an object.")
    duration = number(result.get("metadata", {}).get("duration"), "Rhubarb metadata.duration", positive=True)
    # Rhubarb truncates its metadata duration to centiseconds.
    if abs(duration - audio["wav_duration"]) > 0.010001:
        raise ValueError(f"Turn {turn['id']}: Rhubarb duration disagrees with measured WAV.")
    cues = validate_cues(result.get("mouthCues"), audio["wav_duration"])
    result["mouthCues"] = cues
    atomic_json(mouth_path, result)
    atomic_json(metadata_path, {
        "cache_key": key, "payload": payload, "mouth_sha256": sha256_file(mouth_path),
    })
    return cues


def build_timeline(episode: dict[str, Any], audio: list[dict[str, Any]],
                   cues: list[list[dict[str, Any]]]) -> dict[str, Any]:
    validate_episode(episode)
    if len(audio) != len(episode["turns"]) or len(cues) != len(audio):
        raise ValueError("Turn/audio/cue counts disagree.")
    fps = episode["fps"]
    intro_frames = ceil_frames(episode["intro_seconds"], fps)
    outro_frames = ceil_frames(episode["outro_seconds"], fps)
    cursor = intro_frames
    turns = []
    for turn, info, mouth_cues in zip(episode["turns"], audio, cues):
        samples, rate = info["frames"], info["sample_rate"]
        length = wav_frames_to_video_frames(samples, rate, fps)
        duration = samples / rate
        gap = ceil_frames(turn["pause_after"], fps)
        turns.append({
            **turn,
            **{field: info[field] for field in (
                "raw_audio", "raw_sample_count", "raw_wav_duration", "preprocessing",
            ) if field in info},
            "start": cursor / fps,
            "end": (cursor + length) / fps,
            "duration": length / fps,
            "start_frame": cursor,
            "end_frame": cursor + length,
            "pause_after_frames": gap,
            "pause_after_seconds": gap / fps,
            "wav_duration": duration,
            "sample_rate": rate,
            "sample_count": samples,
            "audio": str(Path(info["audio"]).resolve()),
            "mouth_cues": validate_cues(mouth_cues, duration),
        })
        cursor += length + gap
    total_frames = cursor + outro_frames
    timeline = {
        "fps": fps,
        "intro_seconds": intro_frames / fps,
        "outro_seconds": outro_frames / fps,
        "duration": total_frames / fps,
        "total_frames": total_frames,
        "turns": turns,
    }
    if "language" in episode:
        timeline["language"] = language_code(episode)
    return timeline


def srt_timestamp(seconds: float) -> str:
    milliseconds = round(number(seconds, "subtitle seconds") * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def subtitles(timeline: dict[str, Any]) -> str:
    return "\n".join(
        f"{index}\n{srt_timestamp(turn['start'])} --> "
        f"{srt_timestamp(turn['start'] + turn['wav_duration'])}\n"
        f"{textwrap.fill(turn['text'], width=42, break_long_words=False, break_on_hyphens=False)}\n"
        for index, turn in enumerate(timeline["turns"], 1)
    ) + "\n"


def assemble_dialogue(timeline: dict[str, Any], output_dir: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise FileNotFoundError("ffmpeg is required for explicit 48 kHz PCM16 resampling.")
    resampled = []
    for turn in timeline["turns"]:
        target = output_dir / "audio" / f"{Path(turn['audio']).stem}.48k.wav"
        partial = target.with_name(target.name + ".part")
        subprocess.run([
            ffmpeg, "-nostdin", "-v", "error", "-y", "-i", turn["audio"], "-vn",
            "-map_metadata", "-1", "-ac", "1", "-ar", str(SAMPLE_RATE),
            "-c:a", "pcm_s16le", "-f", "wav", str(partial),
        ], check=True)
        info = inspect_wav(partial)
        expected = Fraction(turn["sample_count"] * SAMPLE_RATE, turn["sample_rate"])
        if info["sample_rate"] != SAMPLE_RATE or abs(Fraction(info["frames"]) - expected) > 1:
            raise ValueError(f"Turn {turn['id']}: ffmpeg changed duration/sample rate unexpectedly.")
        allocated = (turn["end_frame"] - turn["start_frame"]) * (SAMPLE_RATE // timeline["fps"])
        if info["frames"] > allocated:
            raise ValueError(f"Turn {turn['id']}: resampled audio would be truncated by frame allocation.")
        partial.replace(target)
        resampled.append((turn, target, info))
    target = output_dir / "dialogue.wav"
    partial = target.with_name(target.name + ".part")
    samples_per_frame = SAMPLE_RATE // timeline["fps"]
    total_samples = timeline["total_frames"] * samples_per_frame
    position = 0
    silence = bytes(SAMPLE_RATE * 2)
    with wave.open(str(partial), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)

        def write_silence(count: int) -> None:
            if count < 0:
                raise ValueError("Overlapping dialogue audio onsets.")
            while count:
                chunk = min(count, SAMPLE_RATE)
                output.writeframesraw(silence[:chunk * 2])
                count -= chunk

        for turn, source, info in resampled:
            start_sample = turn["start_frame"] * samples_per_frame
            write_silence(start_sample - position)
            with wave.open(str(source), "rb") as input_wav:
                output.writeframesraw(input_wav.readframes(info["frames"]))
            position = start_sample + info["frames"]
        write_silence(total_samples - position)
    actual = inspect_wav(partial)
    if actual["sample_rate"] != SAMPLE_RATE or actual["frames"] != total_samples:
        raise ValueError("Assembled dialogue length does not match the complete frame timeline.")
    partial.replace(target)
    with wave.open(str(target), "rb") as final:
        position = 0
        for turn, source, info in resampled:
            start = turn["start_frame"] * samples_per_frame
            final.setpos(position)
            if any(final.readframes(start - position)):
                raise ValueError(f"Non-silent intro/pause before {turn['id']}.")
            final.setpos(start)
            with wave.open(str(source), "rb") as reference:
                if final.readframes(info["frames"]) != reference.readframes(info["frames"]):
                    raise ValueError(f"Turn {turn['id']}: assembled samples differ from resampled speech.")
            position = start + info["frames"]
        final.setpos(position)
        if any(final.readframes(total_samples - position)):
            raise ValueError("Non-silent dialogue outro.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", type=Path, default=ROOT / "episode.json")
    parser.add_argument("--output-dir", type=Path, default=BUILDS / "pilot_v1")
    from runtime_config import tool_path
    parser.add_argument("--rhubarb", type=Path, default=tool_path("rhubarb"))
    parser.add_argument("--threads", type=int, default=DEFAULT_TTS_THREADS,
                        help="Qwen intra-operation CPU threads (default: %(default)s).")
    parser.add_argument("--rhubarb-threads", type=int, default=4,
                        help="Independent lip-sync analysis threads (default: %(default)s).")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--prepare-only", action="store_true", help="Synthesize/cache WAVs only, before Rhubarb is available.")
    parser.add_argument("--speech-cache-from", type=Path,
                        help="Read-only previous build: import only matching, hash-verified raw speech.")
    args = parser.parse_args()
    if args.threads <= 0:
        parser.error("--threads must be positive")
    if args.rhubarb_threads <= 0:
        parser.error("--rhubarb-threads must be positive")
    if not args.device.strip() or not args.model.strip():
        parser.error("--device and --model cannot be empty")
    started = time.monotonic()
    episode_path = resolve_build_reference(args.episode).resolve(strict=True)
    from episode_config import read_episode
    episode = read_episode(episode_path)
    validate_episode(episode)
    output_dir = build_directory(args.output_dir)
    audio_dir = output_dir / "audio"
    cache_from = None
    if args.speech_cache_from is not None:
        cache_from = resolve_build_reference(args.speech_cache_from).resolve(strict=True) / "audio"
        if not cache_from.is_dir() or cache_from == audio_dir:
            parser.error("--speech-cache-from must name another build containing an audio directory")
    audio_dir.mkdir(parents=True, exist_ok=True)
    raw_audio = synthesize(episode, episode_path.parent, audio_dir, args.model, args.device, args.threads, cache_from)
    if args.prepare_only:
        print(f"Cached {len(raw_audio)} real raw Qwen WAVs in {time.monotonic() - started:.1f}s.", flush=True)
        return
    audio = [
        prepare_turn_audio(turn["id"], raw, audio_dir)
        for turn, raw in zip(episode["turns"], raw_audio)
    ]
    binary = args.rhubarb.resolve(strict=True)
    binary_hash = sha256_file(binary)
    cues = [
        run_rhubarb(turn, info, audio_dir, binary, binary_hash, args.rhubarb_threads)
        for turn, info in zip(episode["turns"], audio)
    ]
    timeline = build_timeline(episode, audio, cues)
    assemble_dialogue(timeline, output_dir)
    atomic_json(output_dir / "episode.json", episode)
    atomic_json(output_dir / "audio_timeline.json", timeline)
    atomic_text(output_dir / "subtitles.srt", subtitles(timeline))
    atomic_json(output_dir / "timeline.json", timeline)
    print(f"Complete: {timeline['duration']:.3f}s, {timeline['total_frames']} frames, "
          f"{sum(item['wav_duration'] for item in audio):.3f}s speech; "
          f"runtime {time.monotonic() - started:.1f}s", flush=True)


if __name__ == "__main__":
    main()
