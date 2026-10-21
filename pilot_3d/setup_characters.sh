#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p assets/studio

fetch_asset() {
  local name="$1" url="$2" sha="$3" expected="$4"
  local archive="assets/studio/$name.zip"
  if [[ ! -f "$archive" ]]; then
    curl --fail --location --retry 3 --output "$archive.part" "$url"
    echo "$sha  $archive.part" | sha256sum --check
    mv "$archive.part" "$archive"
  fi
  echo "$sha  $archive" | sha256sum --check
  if [[ ! -f "assets/studio/$name/$expected" ]]; then
    mkdir -p "assets/studio/$name"
    unzip -q "$archive" -d "assets/studio/$name"
  fi
  test -s "assets/studio/$name/$expected"
}

fetch_asset snow-v4 \
  https://studio.blender.org/download-source/files/ba/0f/ba0fe6d810333b1d73c1c359e4dc03cb-6.zip \
  98d58ef3a07083ede14140bc462cccb55d317062846aa0eb652d2e4a7ac422a6 \
  Snow/snow_v4.2.blend
fetch_asset rain-v3 \
  https://studio.blender.org/download-source/files/ee/a7/eea73e55dba1cea31c09848df6a794b2-4.zip \
  80217f163f6392dc829233d63c2cfb5e1376775bc34101ad14f39631fea70d24 \
  "Rain v3.3/rain_v3.2.blend"
printf 'Licensed studio rigs are ready. See assets/studio/CREDITS.txt.\n'
