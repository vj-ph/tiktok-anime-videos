import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import urllib.request

import numpy as np
import soundfile as sf
import torch
import whisperx

ROOT = Path(__file__).resolve().parent
RATE = 48000
FRAME = RATE // 24
BETWEEN_PHRASES = 18
SECTION_LEAD = 18
SECTION_HOLD = 12
END_HOLD = 34
CARD_IMPACTS = (18, 32, 50)
CARD_REVEAL = 20
FLAGS = {
    "fr": '<svg class="opening-flag" viewBox="0 0 90 60" role="img" aria-label="France">'
          '<path fill="#002395" d="M0 0h30v60H0z"/><path fill="#fff" d="M30 0h30v60H30z"/>'
          '<path fill="#ed2939" d="M60 0h30v60H60z"/></svg>',
    "at": '<svg class="opening-flag" viewBox="0 0 90 60" role="img" aria-label="Österreich">'
          '<path fill="#ed2939" d="M0 0h90v60H0z"/><path fill="#fff" d="M0 20h90v20H0z"/></svg>',
    "ca": '<svg class="opening-flag" viewBox="0 0 120 60" role="img" aria-label="Canada">'
          '<path fill="#fff" d="M0 0h120v60H0z"/><path fill="#d80621" d="M0 0h30v60H0zm90 0h30v60H90z"/>'
          '<path fill="#d80621" d="m60 6 4 9 4-2-2 12 6-5 2 4 7-2-2 8 4 2-12 9 1 4-11-2 1 11h-4l1-11-11 2 1-4-12-9 4-2-2-8 7 2 2-4 6 5-2-12 4 2z"/></svg>',
}


def display_words(aligned, spelling, dtz_dates=False):
    """Keep written forms and merge the measured intervals of spoken numbers."""
    max_words = max((len(text.split()) for text in spelling), default=0)
    i = 0
    while i < len(aligned):
        for count in range(min(len(aligned) - i, max_words), 0, -1):
            part = aligned[i:i+count]
            text = " ".join(w["word"] for w in part)
            match = re.fullmatch(r"([\w -]+)([.,!?;:]?)", text)
            if match and match[1].lower() in spelling:
                yield spelling[match[1].lower()] + match[2], part[0]["start"], part[-1]["end"]
                i += count
                break
        else:
            w = aligned[i]
            next_word = aligned[i+1]["word"] if i + 1 < len(aligned) else ""
            ordinal = {"ersten": "1.", "vierzehnten": "14."}.get(w["word"].lower())
            date = next_word == "Dezember" or (w["word"].lower() == "ersten" and next_word == "bis")
            yield (ordinal if dtz_dates and ordinal and date else w["word"]), w["start"], w["end"]
            i += 1


def sec(sample):
    return f"{sample / RATE:.9f}"


def clip(start, end, track):
    return f'data-start="{sec(start)}" data-duration="{sec(end-start)}" data-track-index="{track}"'


def stock_audio(assets):
    cache = ROOT / "build/stock-audio"
    cache.mkdir(parents=True, exist_ok=True)
    for role, asset in assets.items():
        file = cache / f'{asset["file"]}.mp3'
        if not file.exists():
            request = urllib.request.Request(asset["download"], headers={"User-Agent": "DTZ Advent video generator"})
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != asset["sha256"]:
                raise ValueError(f"Unexpected stock audio bytes: {role}")
            file.write_bytes(data)
        if hashlib.sha256(file.read_bytes()).hexdigest() != asset["sha256"]:
            raise ValueError(f"Unexpected cached stock audio bytes: {role}")
        decoded = subprocess.check_output([
            "ffmpeg", "-v", "error", "-i", str(file), "-ac", "1", "-ar", str(RATE), "-f", "f32le", "-"
        ])
        yield role, np.frombuffer(decoded, dtype="<f4")


def mix_stock(audio, starts, stamp_cues, stock, music_gain=.24):
    assets = dict(stock_audio(stock))
    if "music" in assets and len(assets["music"]) < len(audio):
        raise ValueError("Stock music is shorter than the video")
    bed = assets["music"][:len(audio)] * music_gain if "music" in assets else np.zeros_like(audio)
    fade = min(2 * RATE, len(bed))
    bed[-fade:] *= np.linspace(1, 0, fade)
    effects = np.zeros_like(audio)

    def place(clip, start, peak):
        end = min(start + len(clip), len(effects))
        effects[start:end] += clip[:end-start] * (peak / np.max(np.abs(clip)))

    if "section_bells" in assets:
        for start in starts:
            place(assets["section_bells"], start, .045)
    if "stamp" in assets and stamp_cues:
        # Keep the first strike only and align its main transient to the animation.
        stamp = assets["stamp"][round(.04 * RATE):round(.24 * RATE)].copy()
        stamp[-RATE // 50:] *= np.linspace(1, 0, RATE // 50)
        offset = int(np.argmax(np.abs(stamp)))
        for start, peak in stamp_cues:
            place(stamp, start - offset, peak)
    return audio * .89 + bed + effects


def result_cards(reveal):
    def icon(name):
        return f'<svg viewBox="0 0 100 85"><use href="#icon-{name}"/></svg>'

    cards = []
    for i, (icons, grade) in enumerate((
        (icon("speak"), "B1"),
        (icon("listen") + "<span>+</span>" + icon("read"), "B1"),
        (icon("write"), "A2"),
    )):
        cover = '<span class="mystery">?</span>' if i == 2 else ""
        cards.append(
            f'<div class="result-card" data-impact="{CARD_IMPACTS[i] / 24:.6f}">'
            f'<div class="card-icon">{icons}{cover}</div><b class="grade grade-{grade.lower()}">{grade}</b></div>'
        )
    mode = "reveal" if reveal else "opening"
    label = '<div class="example-label">Ein mögliches Ergebnis</div>' if reveal else ""
    return f'<div class="result-cards {mode}" data-reveal="{CARD_REVEAL / 24:.6f}">{"".join(cards)}</div>{label}'


def prepare(build, episode):
    torch.set_num_threads(3)
    from advent_pipeline import pinned_file

    folder = build / "speech"
    language = episode["language"]
    segments, beats, graphics = (episode[key] for key in ("scenes", "beats", "artwork"))
    for name, spec in episode["visual_assets"].items():
        destination = build / name
        if (episode["base"] / spec["path"]).is_file() or "download" not in spec:
            shutil.copyfile(pinned_file(episode["base"], spec), destination)
        else:
            request = urllib.request.Request(spec["download"], headers={"User-Agent": "Advent exam video generator"})
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != spec["sha256"]:
                raise ValueError(f"Unexpected visual asset bytes: {name}")
            destination.write_bytes(data)
    model, meta = whisperx.load_align_model(language_code=language, device="cpu")
    starts, pcm, markup, evidence, stamp_cues = [], [], [], [], []
    elapsed = index = 0

    def append(samples):
        nonlocal elapsed
        pcm.append(samples)
        elapsed += len(samples)

    for j, (name, title, phrases) in enumerate(segments):
        start = elapsed
        starts.append(start)
        append(np.zeros((2 if j == 0 else SECTION_LEAD) * FRAME))
        overlays = []
        tag, *visuals = beats[name]
        hold = END_HOLD if name == "advent" else SECTION_HOLD
        for k, ((text, translated), visual) in enumerate(zip(phrases, visuals, strict=True)):
            source = folder / f"{index:02}.wav"
            samples, rate = sf.read(source, dtype="float32")
            if rate != RATE or samples.ndim != 1:
                raise ValueError(f"Unexpected audio format: {source}")
            audio = whisperx.load_audio(str(source))
            if not 0.19 * len(text.split()) <= len(audio) / 16000 <= 0.85 * len(text.split()) + 1.5:
                raise ValueError(f"Unusable delivery length for phrase {index}: {len(audio)/16000:.2f}s")
            result = whisperx.align(
                [{"start": 0, "end": len(audio) / 16000, "text": text}], model, meta, audio, "cpu",
            )["word_segments"]
            if [x["word"] for x in result] != text.split() or any(
                not (0 <= x.get("start", -1) < x.get("end", -1) <= len(audio) / 16000 + .01)
                for x in result
            ):
                raise ValueError(f"Missing measured words in phrase {index}: {result}")
            if result[-1]["end"] - result[0]["start"] < .14 * len(result) or len(audio) / 16000 - result[-1]["end"] > 1.4:
                raise ValueError(f"Unreliable alignment for phrase {index}")
            displayed = list(display_words(result, episode.get("spelling", {}), language == "de"))
            words = " ".join(
                f'<span data-word-start="{sec(elapsed + round(begin*RATE))}" '
                f'data-word-end="{sec(elapsed + round(end*RATE))}">{html.escape(w)}</span>'
                for w, begin, end in displayed
            )
            tail = ((len(samples) + FRAME - 1) // FRAME + BETWEEN_PHRASES) * FRAME
            art_start = start if k == 0 else elapsed
            settle = hold * FRAME if k == len(phrases) - 1 else 0
            art_end = elapsed + tail + settle
            if visual == "question":
                graphic = result_cards(False)
                stamp_cues.extend((art_start + frame * FRAME, .14 if i == 2 else .105)
                                  for i, frame in enumerate(CARD_IMPACTS))
            elif visual == "result-a2":
                graphic = result_cards(True)
                stamp_cues.append((art_start + CARD_REVEAL * FRAME, .11))
            else:
                graphic = graphics[visual]
            def reveal_at_word(match):
                token = match[1]
                times = [begin for word, begin, _ in displayed if word == token]
                if len(times) != 1:
                    raise ValueError(f"Graphic {visual} needs one measured occurrence of {token!r}")
                return f'data-word-reveal="{sec(elapsed + round(times[0] * RATE))}"'

            graphic = re.sub(r'data-reveal-word="([^"]+)"', reveal_at_word, graphic)
            impact = ""
            if index == 0 and (stamp_frame := episode.get("opening_stamp_frame")) is not None:
                stamp_at = art_start + stamp_frame * FRAME
                if stamp_at + 6 * FRAME >= art_end:
                    raise ValueError("Opening stamp does not fit its artwork clip")
                stamp_cues.append((stamp_at, .105))
                impact = f' data-stamp-impact="{sec(stamp_at)}"'
            opening_class = " opening-art" if j == 0 and episode.get("opening_flag") else ""
            overlays.append(
                f'<div id="art-{index}" class="clip artwork {visual}{opening_class}" {clip(art_start,art_end,5)} '
                f'aria-hidden="true"{impact}>{graphic}</div>'
            )
            overlays.append(
                f'<div id="phrase-{index}" class="clip caption" {clip(elapsed,art_end,2)}>'
                f'<p class="spoken" lang="{language}">{words}</p><p class="en" lang="en">{html.escape(translated)}</p></div>'
            )
            evidence.append({"id": index, "scene": name, "start_sample": elapsed, "words": result,
                             "display": displayed, "visual": visual, "visual_frame": art_start // FRAME})
            append(np.pad(samples, (0, tail - len(samples))))
            index += 1
        append(np.zeros(hold * FRAME))
        dots = "".join('<i class="seen"></i>' if k <= j else "<i></i>" for k in range(len(segments)))
        flag = FLAGS.get(episode.get("opening_flag"), "") if j == 0 else ""
        markup.append(
            f'<section id="beat-{name}" class="clip beat {name}" {clip(start,elapsed,1)}>'
            f'{flag}<div class="tag">{html.escape(tag)}</div><h1>{html.escape(title)}</h1></section>'
            f'<div id="trail-{name}" class="clip trail" {clip(start,elapsed,3)} aria-hidden="true">{dots}</div>'
        )
        markup.extend(overlays)
    audio = np.concatenate(pcm)
    mixed = mix_stock(audio, starts, stamp_cues, episode.get("stock_audio", {}), episode.get("music_gain", .24))
    if max(abs(mixed)) > .99:
        raise ValueError("Mix clips")
    sf.write(build / "mix.wav", mixed, RATE, subtype="PCM_16")
    source = (ROOT / "winter.html").read_text(encoding="utf-8")
    (build / "alignment.json").write_text(json.dumps({
        "fps": 24, "frames": elapsed // FRAME, "safe_rect": [96, 270, 852, 1248],
        "scene_start_frames": [start // FRAME for start in starts],
        "stamp_cue_frames": [sample // FRAME for sample, _ in stamp_cues],
        "pause_frames": {"within_section": BETWEEN_PHRASES, "section_lead": SECTION_LEAD, "section_hold": SECTION_HOLD},
        "sample_rate": RATE, "phrases": evidence,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copyfile(ROOT / "node_modules/gsap/dist/gsap.min.js", build / "gsap.min.js")
    (build / "index.html").write_text(
        source.replace("{{DURATION}}", sec(elapsed)).replace("{{LANG}}", language)
        .replace("{{BACKGROUND}}", "market.svg" if "market.svg" in episode["visual_assets"] else "market.jpg")
        .replace("{{TITLE}}", html.escape(episode["title"])).replace("{{CONTENT}}", "\n".join(markup)), encoding="utf-8"
    )
    print(f"{elapsed / RATE:.2f} seconds, {index} bilingual phrases, all words aligned")
