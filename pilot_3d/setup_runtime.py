"""Install checksum-pinned tools, fonts and optional rigs on Windows or Linux/WSL2."""

import argparse
import hashlib
from pathlib import Path
import platform
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
BLENDER_URL = "https://download.blender.org/release/Blender4.5/"
RHUBARB_URL = "https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v1.14.0/"
TOOLS = {
    "windows": (
        ("blender", BLENDER_URL + "blender-4.5.9-windows-x64.zip",
         "41da973b9bf95bb312cbeff4d1982feb13259b43c821686b9bafea4dfe5477cf",
         "blender-4.5.9-windows-x64", "blender.exe"),
        ("rhubarb", RHUBARB_URL + "Rhubarb-Lip-Sync-1.14.0-Windows.zip",
         "62fa416a8d5e382a3828ee4bef358ce520d0b4cabdeaea75a7ac266d098d1fe3",
         "Rhubarb-Lip-Sync-1.14.0-Windows", "rhubarb.exe"),
    ),
    "linux": (
        ("blender", BLENDER_URL + "blender-4.5.9-linux-x64.tar.xz",
         "dcdc3eca6c9825bb35a8033b689c053f3cb5a9b0cd2a61b2eac2a49436b4ad3d",
         "blender-4.5.9-linux-x64", "blender"),
        ("rhubarb", RHUBARB_URL + "Rhubarb-Lip-Sync-1.14.0-Linux.zip",
         "a9a9074862cff47b2d59b8bf399a678a3b0b74f9452ad6ad94cb292913dd8667",
         "Rhubarb-Lip-Sync-1.14.0-Linux", "rhubarb"),
    ),
}
RIGS = (
    ("snow-v4", "https://studio.blender.org/download-source/files/ba/0f/ba0fe6d810333b1d73c1c359e4dc03cb-6.zip",
     "98d58ef3a07083ede14140bc462cccb55d317062846aa0eb652d2e4a7ac422a6",
     "Snow/snow_v4.2.blend"),
    ("rain-v3", "https://studio.blender.org/download-source/files/ee/a7/eea73e55dba1cea31c09848df6a794b2-4.zip",
     "80217f163f6392dc829233d63c2cfb5e1376775bc34101ad14f39631fea70d24",
     "Rain v3.3/rain_v3.2.blend"),
)
FONT_URL = "https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.zip"
FONT_SHA = "7576310b219e04159d35ff61dd4a4ec4cdba4f35c00e002a136f00e96a908b0a"
FFMPEG_WINDOWS = (
    "https://github.com/GyanD/codexffmpeg/releases/download/6.1.1/ffmpeg-6.1.1-essentials_build.zip",
    "742e32fc9f92681f9f254b925e1b613fdd8074ba40749d4879aefdb009b94cc5",
    "ffmpeg-6.1.1-essentials_build/bin",
)


def download(url, digest, destination):
    destination = Path(destination)
    if not destination.is_file():
        partial = destination.with_name(destination.name + ".part")
        print(f"Downloading {url}", flush=True)
        try:
            urllib.request.urlretrieve(url, partial)
            if hashlib.sha256(partial.read_bytes()).hexdigest() != digest:
                raise ValueError(f"Checksum mismatch: {url}")
            partial.replace(destination)
        finally:
            partial.unlink(missing_ok=True)
    if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
        raise ValueError(f"Checksum mismatch: {destination}; remove this archive and retry.")


def extract(archive, destination):
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as source:
            for name in source.namelist():
                if not (destination / name).resolve().is_relative_to(destination.resolve()):
                    raise ValueError(f"Unsafe archive member: {name}")
            source.extractall(destination)
    else:
        with tarfile.open(archive) as source:
            source.extractall(destination, filter="data")


def install(url, digest, target, folder, expected, archive=None):
    if (target / expected).is_file():
        print(f"Already installed: {target}", flush=True)
        return
    if target.exists():
        raise ValueError(f"Incomplete installation at {target}; move it aside before retrying.")
    downloads = ROOT / ".tools" / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    archive = Path(archive) if archive is not None else downloads / url.rsplit("/", 1)[-1]
    download(url, digest, archive)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
        extracted = Path(temporary)
        extract(archive, extracted)
        source = extracted / folder if folder else extracted
        if not (source / expected).is_file():
            raise ValueError(f"Archive missing {expected}")
        if sys.platform != "win32" and expected in ("blender", "rhubarb"):
            executable = source / expected
            executable.chmod(executable.stat().st_mode | 0o111)
        shutil.copytree(source, target)


def install_fonts():
    target = ROOT / ".tools" / "fonts"
    install(FONT_URL, FONT_SHA, target, "dejavu-fonts-ttf-2.37", "ttf/DejaVuSans.ttf")
    for name in ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"):
        shutil.copy2(target / "ttf" / name, target / name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=("tools", "fonts", "characters", "ffmpeg"),
                        help="Install one group; ffmpeg is an optional Windows compatibility build.")
    args = parser.parse_args()
    system = {"win32": "windows", "linux": "linux"}.get(sys.platform)
    if system is None or platform.machine().lower() not in ("amd64", "x86_64"):
        parser.error("Pinned tools require Windows x64 or Linux x64 (including WSL2).")
    if args.only == "ffmpeg":
        if system != "windows":
            parser.error("The optional FFmpeg build is Windows-only; use your Linux package manager.")
        url, digest, folder = FFMPEG_WINDOWS
        install(url, digest, ROOT / ".tools" / system / "ffmpeg", folder, "ffmpeg.exe")
        return
    if args.only in (None, "tools"):
        for name, url, digest, folder, expected in TOOLS[system]:
            install(url, digest, ROOT / ".tools" / system / name, folder, expected)
    if args.only in (None, "fonts"):
        install_fonts()
    if args.only in (None, "characters"):
        for name, url, digest, expected in RIGS:
            archive = ROOT / "assets" / "studio" / f"{name}.zip"
            install(url, digest, ROOT / "assets" / "studio" / name, "", expected,
                    archive=archive if archive.is_file() else None)


if __name__ == "__main__":
    main()
