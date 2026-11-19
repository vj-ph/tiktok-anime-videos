"""Run the Advent explainer pipeline from an exam-specific episode file."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent
EXAMS = {
    "dtz-b1": ("de", "German"),
    "oeif-b1": ("de", "German"),
    "fide-a2-b1": ("de", "German"),
    "tcf-irn": ("fr", "French"),
    "tef-canada": ("fr", "French"),
}
LANGUAGES = {"de": "German", "fr": "French", "it": "Italian"}
ID = re.compile(r"[a-z][a-z0-9-]*")
SHA = re.compile(r"[0-9a-f]{64}")


def load_episode(path):
    base = path.resolve().parent
    data = json.loads(path.read_text(encoding="utf-8"))
    profile = data["exam"]
    if profile not in EXAMS:
        raise ValueError(f"Unknown exam: {profile}")
    language, _ = EXAMS[profile]
    language = data.get("language", language)
    if language not in (("de", "fr", "it") if profile == "fide-a2-b1" else (EXAMS[profile][0],)):
        raise ValueError(f"Unsupported language {language!r} for {profile}")
    qwen_language = LANGUAGES[language]
    voice = data["voice"]
    if not voice["model"].strip() or not 0.5 <= voice["tempo"] <= 1:
        raise ValueError("voice.tempo must be between 0.5 and 1")
    for role in ("audio", "transcript"):
        pin = voice[role]
        if not SHA.fullmatch(pin["sha256"]) or not pin["path"].strip():
            raise ValueError(f"Missing SHA-256 for voice {role}")
    scenes_path = base / data["script"]
    graphics_path = base / data["graphics"]
    scenes = json.loads(scenes_path.read_text(encoding="utf-8"))
    graphics = json.loads(graphics_path.read_text(encoding="utf-8"))
    beats = data["beats"]
    names = [name for name, _, _ in scenes]
    if len(names) != len(set(names)) or set(names) != set(beats) or names[:1] != ["hook"] or names[-1:] != ["advent"]:
        raise ValueError("Scenes must match their beats, start with hook, and end with advent")
    special = [key for name in names for key in beats[name][1:] if key in ("question", "result-a2")]
    if special and (special != ["question", "result-a2"] or profile != "dtz-b1"
                    or beats["hook"][1] != "question"):
        raise ValueError("The DTZ result-card example requires a DTZ opening question and a later reveal")
    for name, title, phrases in scenes:
        tag, *visuals = beats[name]
        if not ID.fullmatch(name) or not title.strip() or not tag.strip() or not phrases or len(phrases) != len(visuals):
            raise ValueError(f"Invalid scene or visual count: {name}")
        for (spoken, translation), visual in zip(phrases, visuals, strict=True):
            if not spoken.strip() or not translation.strip() or not ID.fullmatch(visual):
                raise ValueError(f"Missing speech, English translation, or invalid visual in {name}")
            if visual not in special and not graphics.get(visual, "").strip():
                raise ValueError(f"Missing graphic: {visual}")
    if not data["official_sources"] or any(not url.startswith("https://") for url in data["official_sources"]):
        raise ValueError("Supply official exam references in official_sources")
    for name, asset in data["visual_assets"].items():
        if (not re.fullmatch(r"[a-z0-9][a-z0-9.-]*\.(?:jpg|jpeg|png|webp)", name)
                or not SHA.fullmatch(asset["sha256"]) or not asset["path"].strip()):
            raise ValueError(f"Invalid visual asset: {name}")
        if "download" in asset and not asset["download"].startswith("https://"):
            raise ValueError(f"Visual download must use HTTPS: {name}")
    if "market.jpg" not in data["visual_assets"]:
        raise ValueError("Supply market.jpg for the winter backdrop")
    if not data["title"].strip():
        raise ValueError("Missing episode title")
    stock_path = base / data["stock_manifest"] if data.get("stock_manifest") else None
    stock = json.loads(stock_path.read_text(encoding="utf-8"))["audio"]["stock"] if stock_path else {}
    for role, asset in stock.items():
        if (role not in ("music", "section_bells", "stamp") or not ID.fullmatch(asset["file"])
                or not SHA.fullmatch(asset["sha256"]) or not asset["download"].startswith("https://")
                or not asset["license"] or not asset["source"]):
            raise ValueError(f"Invalid stock audio: {role}")
    data.update(base=base, language=language, qwen_language=qwen_language, scenes=scenes, artwork=graphics,
                stock_audio=stock)
    digest = hashlib.sha256()
    for source in (path, scenes_path, graphics_path, *((stock_path,) if stock_path else ())):
        digest.update(hashlib.sha256(source.read_bytes()).digest())
    data["fingerprint"] = digest.hexdigest()
    return data


def pinned_file(base, spec):
    file = base / spec["path"]
    if hashlib.sha256(file.read_bytes()).hexdigest() != spec["sha256"]:
        raise ValueError(f"SHA-256 mismatch: {file}")
    return file.resolve()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("plan", "speech", "prepare", "check", "render"))
    parser.add_argument("--episode", required=True, type=Path)
    parser.add_argument("--build", type=Path)
    parser.add_argument("--retry", type=int, nargs="+", help="Replace selected zero-based speech clips before prepare")
    args = parser.parse_args()
    try:
        episode = load_episode(args.episode)
        if args.retry and args.stage != "speech":
            parser.error("--retry is only valid for speech")
        if args.stage == "plan":
            print(json.dumps({key: episode[key] for key in
                              ("exam", "title", "language", "qwen_language", "official_sources", "scenes")},
                             ensure_ascii=False, indent=2))
            return
        if not args.build:
            parser.error("--build is required except for plan")
        build = args.build.resolve()
        binding = build / "episode.sha256"
        if args.stage == "speech" and not binding.exists():
            build.mkdir(parents=True, exist_ok=False)
            binding.write_text(episode["fingerprint"], encoding="ascii")
        if not binding.exists() or binding.read_text(encoding="ascii") != episode["fingerprint"]:
            raise ValueError("Build is unbound or episode inputs changed; use a fresh --build")
        if args.stage == "speech":
            from winter_speech import synthesize

            if (build / "index.html").exists():
                raise ValueError("Composition already exists; preserve it and use a fresh build")
            voice = episode["voice"]
            lines = [text for _, _, phrases in episode["scenes"] for text, _ in phrases]
            if args.retry and any(i < 0 or i >= len(lines) for i in args.retry):
                raise ValueError("Speech retry index out of range")
            audio, transcript = (pinned_file(episode["base"], voice[key]) for key in ("audio", "transcript"))
            folder = build / "speech"
            folder.mkdir(exist_ok=True)
            pending = [(i, text) for i, text in enumerate(lines) if
                       (i in args.retry if args.retry else not (folder / f"{i:02}.wav").exists())]
            synthesize(folder, pending,
                       voice["model"], audio, transcript, episode["qwen_language"], voice["tempo"],
                       sampling=bool(args.retry))
        elif args.stage == "prepare":
            if (build / "index.html").exists():
                raise ValueError("Composition already exists; preserve it and use a fresh build")
            from winter_prepare import prepare

            prepare(build, episode)
        else:
            if not all((build / file).is_file() for file in ("index.html", "alignment.json", "mix.wav", "gsap.min.js")):
                raise ValueError("Run prepare before check or render")
            if args.stage == "render":
                output = build / "advent.mp4"
                if output.exists():
                    raise ValueError(f"Refusing to overwrite {output}")
            subprocess.run(["node", str(ROOT / "winter_check.cjs"), str(build)], check=True)
            if args.stage == "render":
                subprocess.run([str(ROOT / "node_modules/.bin/hyperframes"), "render", str(build),
                                "--fps", "24", "--quality", "standard", "--workers", "2", "-o", str(output)],
                               check=True)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
