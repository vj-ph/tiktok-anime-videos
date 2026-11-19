import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

import soundfile as sf
import torch
from huggingface_hub import snapshot_download
from qwen_tts import Qwen3TTSModel

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build/winter"
MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
REF = ROOT.parents[1] / "shared-voices/gemini_3.8_flash_tts/german"
PINS = {
    "middle_female.wav": "791c8108a4948eb1d279f3bb4b2b7bcfef0f8eadbd821963ec5829a5eead51c5",
    "text.txt": "6c357280a47fa5735bc262e5d3ae018076a2552753017f8950800888c90c281f",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--retry", type=int, nargs="+")
    parser.add_argument("--reuse", type=Path)
    args = parser.parse_args()
    for name, digest in PINS.items():
        if hashlib.sha256((REF / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"DTZ reference changed: {name}")
    script = (ROOT / "winter.json").read_bytes()
    folder = BUILD / "speech" / hashlib.sha256(script).hexdigest()[:16]
    folder.mkdir(parents=True, exist_ok=True)
    lines = [text for _, _, phrases in json.loads(script) for text, _ in phrases]
    if args.reuse:
        old_script = args.reuse.read_bytes()
        old_folder = BUILD / "speech" / hashlib.sha256(old_script).hexdigest()[:16]
        old_lines = [text for _, _, phrases in json.loads(old_script) for text, _ in phrases]
        for i, text in enumerate(lines):
            output = folder / f"{i:02}.wav"
            if text in old_lines and not output.exists():
                import shutil
                shutil.copyfile(old_folder / f"{old_lines.index(text):02}.wav", output)
    pending = [(i, text) for i, text in enumerate(lines) if
               (i in args.retry if args.retry else not (folder / f"{i:02}.wav").exists())]
    synthesize(folder, pending, MODEL, REF / "middle_female.wav", REF / "text.txt",
               "German", .85, sampling=bool(args.retry))


def synthesize(folder, pending, model_id, ref_audio, ref_text, language, tempo, *, sampling):
    if not pending:
        return
    torch.manual_seed(20261201)
    torch.set_num_threads(5)
    cuda = torch.cuda.is_available()
    model = Qwen3TTSModel.from_pretrained(
        snapshot_download(model_id, local_files_only=True),
        device_map="cuda:0" if cuda else "cpu", dtype=torch.bfloat16 if cuda else torch.float32,
        local_files_only=True,
    )
    prompt = model.create_voice_clone_prompt(
        ref_audio=str(ref_audio), ref_text=ref_text.read_text(encoding="utf-8").strip(),
    )
    batch_size = 1 if sampling else 3
    for offset in range(0, len(pending), batch_size):
        batch = pending[offset:offset + batch_size]
        wavs, rate = model.generate_voice_clone(
            text=[text for _, text in batch], language=[language] * len(batch),
            voice_clone_prompt=prompt * len(batch), non_streaming_mode=True,
            max_new_tokens=min(180, 34 + 9 * max(len(t.split()) for _, t in batch)),
            do_sample=sampling, subtalker_dosample=sampling,
        )
        for (i, _), pcm in zip(batch, wavs, strict=True):
            raw, processed = folder / f"{i:02}.raw.wav", folder / f"{i:02}.tmp.wav"
            sf.write(raw, pcm, rate)
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af",
                 f"atempo={tempo},alimiter=limit=0.79:level=false:latency=true", "-ar", "48000",
                 "-ac", "1", str(processed)], check=True,
            )
            os.replace(processed, folder / f"{i:02}.wav")
            raw.unlink()
            print(f"Recorded {i:02}", flush=True)


if __name__ == "__main__":
    main()
