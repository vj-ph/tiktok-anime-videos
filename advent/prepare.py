"""Prepare frame-aligned narration, captions and the HyperFrames project."""

import hashlib
import html
import io
import json
import shutil
import subprocess
import wave
from pathlib import Path

from piper import PiperVoice, SynthesisConfig

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
FPS, RATE = 24, 48000
FRAME = RATE // FPS
VOICE = {
    "de_DE-thorsten-high.onnx": "9df1c43c61149ef9b39e618e2b861fbe41e1fcea9390b2dac62e8761573ea4f1",
    "de_DE-thorsten-high.onnx.json": "6de734444e4c3f9e33b7ebe2746dbc19b71e85f613e79c65acf623200b99a76a",
}


def synthesize(voice, text):
    with io.BytesIO() as raw:
        with wave.open(raw, "wb") as file:
            voice.synthesize_wav(text, file, syn_config=SynthesisConfig(length_scale=1.05))
        return subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "wav", "-i", "-", "-af", "volume=-3dB",
             "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
            input=raw.getvalue(), capture_output=True, check=True,
        ).stdout


def seconds(frame):
    return f"{frame / FPS:.9f}"


def stamp(frame):
    total = round(frame * 1000 / FPS)
    m, s = divmod(total, 60000)
    s, ms = divmod(s, 1000)
    h, m = divmod(m, 60)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def main():
    for name, digest in VOICE.items():
        file = BUILD / "voice" / name
        if hashlib.sha256(file.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Voice asset hash mismatch: {file}")
    voice = PiperVoice.load(BUILD / "voice" / next(iter(VOICE)))
    episode = json.loads((ROOT / "episode.json").read_text(encoding="utf-8"))
    pcm = bytearray()
    captions, scenes, markers = [], [], []

    def silence(frames):
        pcm.extend(bytes(frames * FRAME * 2))

    def clock():
        return len(pcm) // (FRAME * 2)

    for i, scene in enumerate(episode["scenes"], 1):
        start = clock()
        silence(15)
        overlays = []
        for line in scene["speech"]:
            begin = clock()
            audio = synthesize(voice, line)
            pcm.extend(audio)
            pcm.extend(bytes(-len(audio) % (2 * FRAME)))
            end = clock()
            captions.append(f"{len(captions) + 1}\n{stamp(begin)} --> {stamp(end)}\n{line}\n")
            overlays.append(
                f'<p class="clip caption" data-start="{seconds(begin)}" '
                f'data-duration="{seconds(end - begin)}" data-track-index="2">{html.escape(line)}</p>'
            )
            silence(8)
        silence(48 if scene["art"] == "advent" else 10)
        duration = clock() - start
        markers.append({"title": scene["title"], "start_frame": start, "frames": duration})
        cards = "".join(f"<li>{html.escape(card)}</li>" for card in scene["cards"])
        scenes.append(
            f'<section class="clip scene" data-start="{seconds(start)}" data-duration="{seconds(duration)}" '
            f'data-track-index="1" style="--accent:{scene["color"]}">'
            f'<div class="brand">DEUTSCH · B1</div><div class="count">{i:02} / {len(episode["scenes"]):02}</div>'
            f'<div class="hero"><svg class="icon" viewBox="0 0 320 320" aria-hidden="true">'
            f'<use href="#{scene["art"]}"/></svg></div>'
            f'<div class="content"><p class="kicker">{html.escape(scene["label"])}</p>'
            f'<h1>{html.escape(scene["title"])}</h1><ul>{cards}</ul></div>'
            f'<div class="progress"><div style="width:{i / len(episode["scenes"]):.1%}"></div></div></section>'
        )
        scenes.extend(overlays)
    with wave.open(str(BUILD / "narration.wav"), "wb") as file:
        file.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        file.writeframes(pcm)
    html_page = (ROOT / "composition.html").read_text(encoding="utf-8")
    (BUILD / "index.html").write_text(
        html_page.replace("{{DURATION}}", seconds(clock())).replace("{{SCENES}}", "\n".join(scenes)),
        encoding="utf-8",
    )
    (BUILD / "dtz-b1-advent.srt").write_text("\n".join(captions), encoding="utf-8")
    (BUILD / "timeline.json").write_text(
        json.dumps({"fps": FPS, "frames": clock(), "scenes": markers}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    shutil.copyfile(ROOT / "node_modules/gsap/dist/gsap.min.js", BUILD / "gsap.min.js")
    print(f"{len(markers)} scenes; {clock()} frames at {FPS} fps")


if __name__ == "__main__":
    main()
