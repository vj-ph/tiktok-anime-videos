#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

QWEN_PYTHON="${QWEN_PYTHON:-/home/ronggong/lang/german/.venvs/qwen-tts-test/bin/python}"
QWEN_MODEL="${QWEN_MODEL:-Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign}"
QWEN_DEVICE="${QWEN_DEVICE:-auto}"
THREADS="${THREADS:-4}"

if [[ $# -ne 3 ]]; then
  printf 'Usage: %s NARRATION_FILE STYLE_PROMPT_FILE OUTPUT_WAV\n' "$0" >&2
  exit 2
fi

NARRATION_FILE="$1"
STYLE_PROMPT_FILE="$2"
OUTPUT="$3"
TTS_SCRIPT="$SCRIPT_DIR/qwen_style_tts.py"

for required_file in "$NARRATION_FILE" "$STYLE_PROMPT_FILE" "$TTS_SCRIPT"; do
  if [[ ! -f "$required_file" ]]; then
    printf 'Required file not found: %s\n' "$required_file" >&2
    exit 1
  fi
done

if [[ ! -x "$QWEN_PYTHON" ]]; then
  printf 'Qwen Python executable not found: %s\n' "$QWEN_PYTHON" >&2
  exit 1
fi

STYLE_PROMPT="$(<"$STYLE_PROMPT_FILE")"

"$QWEN_PYTHON" "$TTS_SCRIPT" \
  --text-file "$NARRATION_FILE" \
  --style "$STYLE_PROMPT" \
  --output "$OUTPUT" \
  --model "$QWEN_MODEL" \
  --device "$QWEN_DEVICE" \
  --threads "$THREADS"
