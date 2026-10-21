#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p .tools/downloads

if [[ ! -x .tools/blender/blender ]]; then
  archive=.tools/downloads/blender-4.5.9-linux-x64.tar.xz
  curl --fail --location --retry 3 --output "$archive" \
    https://download.blender.org/release/Blender4.5/blender-4.5.9-linux-x64.tar.xz
  echo "dcdc3eca6c9825bb35a8033b689c053f3cb5a9b0cd2a61b2eac2a49436b4ad3d  $archive" | sha256sum --check
  tar -xf "$archive" -C .tools
  mv .tools/blender-4.5.9-linux-x64 .tools/blender
  rm "$archive"
fi

if [[ ! -x .tools/rhubarb/rhubarb ]]; then
  archive=.tools/downloads/rhubarb-1.14.0.zip
  curl --fail --location --retry 3 --output "$archive" \
    https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v1.14.0/Rhubarb-Lip-Sync-1.14.0-Linux.zip
  echo "a9a9074862cff47b2d59b8bf399a678a3b0b74f9452ad6ad94cb292913dd8667  $archive" | sha256sum --check
  unzip -q "$archive" -d .tools
  mv .tools/Rhubarb-Lip-Sync-1.14.0-Linux .tools/rhubarb
  chmod +x .tools/rhubarb/rhubarb
  sha256sum "$archive" > .tools/rhubarb-download.sha256
  rm "$archive"
fi

.tools/blender/blender --version | head -1
.tools/rhubarb/rhubarb --version
command -v ffmpeg
