#!/usr/bin/env python3
"""CLI for generating styled speech with Qwen3-TTS VoiceDesign."""

from __future__ import annotations

import argparse
import math
from pathlib import Path


DEFAULT_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate styled speech using Qwen3-TTS VoiceDesign."
    )
    text_group = parser.add_mutually_exclusive_group(required=True)
    text_group.add_argument("--text", help="Text to synthesize.")
    text_group.add_argument(
        "--text-file",
        type=Path,
        help="UTF-8 text file to synthesize.",
    )
    parser.add_argument(
        "--style",
        required=True,
        help=(
            "Natural-language voice and delivery description, for example: "
            "'Warm, reassuring German male narrator in his early thirties, "
            "calm pace, clear pronunciation.'"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output WAV path.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Qwen VoiceDesign model ID or local checkpoint path.",
    )
    parser.add_argument(
        "--language",
        default="German",
        help="Speech language passed to Qwen3-TTS.",
    )
    parser.add_argument(
        "--device",
        default="auto",
        help="Device map: auto, cpu, cuda, cuda:0, and so on.",
    )
    parser.add_argument(
        "--dtype",
        choices=("auto", "float32", "float16", "bfloat16"),
        default="auto",
        help="Model loading dtype.",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=positive_int,
        help="Maximum generated audio tokens; defaults based on text length.",
    )
    parser.add_argument(
        "--threads",
        type=positive_int,
        help="Optional PyTorch CPU thread count.",
    )
    return parser


def read_text(args: argparse.Namespace) -> str:
    if args.text is not None:
        text = args.text
    else:
        try:
            text = args.text_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise SystemExit(f"Text file not found: {args.text_file}")
    text = text.strip()
    if not text:
        raise SystemExit("Input text must not be empty.")
    return text


def resolve_device(torch, requested_device: str) -> str:
    if requested_device != "auto":
        return requested_device
    return "cuda:0" if torch.cuda.is_available() else "cpu"


def resolve_dtype(torch, requested_dtype: str, device: str):
    if requested_dtype == "float32":
        return torch.float32
    if requested_dtype == "float16":
        return torch.float16
    if requested_dtype == "bfloat16":
        return torch.bfloat16
    return torch.bfloat16 if device.startswith("cuda") else torch.float32


def default_max_new_tokens(text: str) -> int:
    return max(300, min(6000, math.ceil(len(text) * 11)))


def main() -> None:
    args = get_parser().parse_args()
    text = read_text(args)
    style = args.style.strip()
    if not style:
        raise SystemExit("Style prompt must not be empty.")

    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel

    if args.threads is not None:
        torch.set_num_threads(args.threads)
        torch.set_num_interop_threads(max(1, min(args.threads, 4)))

    device = resolve_device(torch, args.device)
    dtype = resolve_dtype(torch, args.dtype, device)
    print(f"Loading {args.model} on {device} with {dtype}.")
    model = Qwen3TTSModel.from_pretrained(
        args.model,
        device_map=device,
        dtype=dtype,
    )

    model_type = getattr(model.model, "tts_model_type", None)
    if model_type != "voice_design":
        raise SystemExit(
            f"Model '{args.model}' is '{model_type}', not a VoiceDesign model. "
            "Use a Qwen3-TTS VoiceDesign checkpoint for --style prompts."
        )

    max_new_tokens = args.max_new_tokens or default_max_new_tokens(text)
    print(f"Generating audio with max_new_tokens={max_new_tokens}.")
    wavs, sample_rate = model.generate_voice_design(
        text=text,
        instruct=style,
        language=args.language,
        non_streaming_mode=True,
        max_new_tokens=max_new_tokens,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(args.output, wavs[0], sample_rate)
    print(f"Wrote {args.output} at {sample_rate} Hz.")


if __name__ == "__main__":
    main()
