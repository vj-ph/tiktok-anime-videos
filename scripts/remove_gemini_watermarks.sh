#!/usr/bin/env bash
set -euo pipefail

WATERMARK_TOOL="${WATERMARK_TOOL:-/home/ronggong/lang/gemini_watermark/GeminiWatermarkTool}"

if [[ $# -ne 2 ]]; then
  printf 'Usage: %s INPUT_FOLDER OUTPUT_FOLDER\n' "$0" >&2
  exit 2
fi

INPUT_FOLDER="$1"
OUTPUT_FOLDER="$2"

if [[ ! -x "$WATERMARK_TOOL" ]]; then
  printf 'GeminiWatermarkTool executable not found: %s\n' "$WATERMARK_TOOL" >&2
  exit 1
fi

if [[ ! -d "$INPUT_FOLDER" ]]; then
  printf 'Input folder not found: %s\n' "$INPUT_FOLDER" >&2
  exit 1
fi

if [[ -e "$OUTPUT_FOLDER" && ! -d "$OUTPUT_FOLDER" ]]; then
  printf 'Output path is not a folder: %s\n' "$OUTPUT_FOLDER" >&2
  exit 1
fi

mkdir -p "$OUTPUT_FOLDER"

"$WATERMARK_TOOL" \
  -i "$INPUT_FOLDER" \
  -o "$OUTPUT_FOLDER" \
  --no-banner \
  --no-legacy \
  --fallback-region br:80,80,160,160 \
  --snap \
  --snap-min-size 16 \
  --snap-max-size 64 \
  --snap-threshold 0.30 \
  --denoise ai \
  --sigma 13 \
  --strength 175 \
  --verbose
