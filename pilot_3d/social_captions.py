"""Measured, word-timed social captions with an explicitly conservative safe area."""

import json
import math
import subprocess
from pathlib import Path

from align_words import validate_words
from episode_config import instruction_turn, section_windows, takeaway_seconds, task_window
from picture_presentation import (NOTICE_COMPACT_PANEL, NOTICE_REVEAL_PANEL,
                                  picture_layout, picture_windows)
from episode_profiles import language_profile
from runtime_config import caption_fonts, font_path

SAFE = (88, 200, 512, 752)
LEFT, RIGHT = 104, 496
FONT = str(font_path())
BOLD_FONT = str(font_path(bold=True))
MIN_PAGE_SECONDS = 1.8
MAX_PAGE_CPS = 20.0
HOOK_BOTTOM = 742
HOOK_SIZE = 31
HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Text,DejaVu Sans,29,&H00FFFFFF,&H00FFFFFF,&H00221810,&H00221810,0,0,0,0,100,100,0,0,1,2,0,7,0,0,0,1
Style: Box,DejaVu Sans,20,&H00221810,&H000000FF,&H00221810,&H00221810,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
NOTICE_STYLE_BOUNDS = {
    "NoticeReadingBox": NOTICE_REVEAL_PANEL,
    "NoticeReferenceBox": NOTICE_COMPACT_PANEL,
    "NoticeReferenceText": (96, 758, 432, 790),
}
SOURCES = {
    "checked": "2026-10-20",
    "tiktok": "https://ads.tiktok.com/help/article/tiktok-auction-in-feed-ads?lang=en",
    "tiktok_template": "https://lf-tt4b.tiktokcdn.com/obj/i18nblog/tt4b_cms/en-US/5jqet0ab9qci-10e7f5Vig4uhAscNP8XPB0.zip",
    "meta": "https://www.facebook.com/business/ads/facebook-instagram-reels-ads",
    "meta_checker": "https://www.facebook.com/business/help/980593475366490",
    "limitation": "Meta detailed guidance redirected to login. Bounds are a conservative project policy, "
                  "not a platform certification. Expanded captions, extra anchors, crops and UI changes "
                  "can cover content; check the actual placement preview before publishing.",
    "template_reading_720x1280": "Measured 2880x5120 template scaled to 720x1280: internal side gutters "
                               "80px each, top 160px, bottom 440px. An additional lower-right 120px "
                               "exclusion starts at x=520, y=560. Shared rectangle is inset from all of these.",
}


def measured_lines(text, size, bold=False, width=RIGHT - LEFT):
    from PIL import ImageFont

    font = ImageFont.truetype(BOLD_FONT if bold else FONT, size)
    lines = []
    for token in text.split():
        if font.getlength(token) > width:
            raise ValueError(f"Text cannot fit without breaking a word: {token!r}")
        if not lines or font.getlength(lines[-1] + " " + token) > width:
            lines.append(token)
        else:
            lines[-1] += " " + token
    return lines


def chunks(words, size=31):
    """At most two measured lines per stable subtitle phrase."""
    result, current = [], []
    for word in words:
        candidate = current + [word]
        if len(measured_lines(" ".join(item["word"] for item in candidate), size)) > 2:
            result.append(current)
            current = [word]
        else:
            current = candidate
        if current[-1]["word"].endswith((".", "?", "!")):
            result.append(current)
            current = []
    if current:
        result.append(current)
    return result


def active_word(words, seconds):
    return next((i for i, word in enumerate(words) if word["start"] <= seconds < word["end"]), None)


def displayed_seconds(start, end, fps):
    return (math.ceil(end * fps - 1e-9) - math.ceil(start * fps - 1e-9)) / fps


def frame_safe_time(seconds, fps):
    # Rounding a frame boundary upward can hide its first frame in libass.
    frame = round(seconds * fps)
    if fps <= 100 and abs(frame / fps - seconds) < 1e-8:
        return (frame * 100 // fps) / 100
    return seconds


def readable_pages(words, start, end, fps=24):
    """Balance up to three lines, keeping measured spoken words on their page."""
    if not words or end < start + words[-1]["end"] - 0.005:
        raise ValueError("Subtitle window would truncate spoken words.")
    boundaries = [round(frame_safe_time(start, fps) * 100)]
    boundaries += [round((start + (a["end"] + b["start"]) / 2) * 100)
                   for a, b in zip(words, words[1:])]
    boundaries.append(round(frame_safe_time(end, fps) * 100))
    best = {0: (0, [])}
    weak_endings = {"aber", "und", "oder", "um", "die", "der", "das", "am", "im",
                    "in", "mit", "einen", "einem", "von", "zu", "eine",
                    "vor", "nach", "bis", "gegen", "ohne"}
    for first in range(len(words)):
        if first not in best:
            continue
        for stop in range(first + 1, len(words) + 1):
            group = words[first:stop]
            value = " ".join(word["word"] for word in group)
            if len(measured_lines(value, 31)) > 3:
                break
            duration = (boundaries[stop] - boundaries[first]) / 100
            visible = displayed_seconds(boundaries[first] / 100, boundaries[stop] / 100, fps)
            if min(duration, visible) < MIN_PAGE_SECONDS or len(value) / min(duration, visible) > MAX_PAGE_CPS:
                continue
            last = group[-1]["word"]
            penalty = 0 if last.endswith((".", "?", "!")) else 0.75
            if last.lower().strip(".,?!:") in weak_endings:
                penalty += 2
            cost = best[first][0] + 1 + 0.03 * max(0, len(value) / duration - 16) ** 2 + penalty
            page = {"words": group, "start": boundaries[first] / 100,
                    "end": boundaries[stop] / 100, "text": value}
            if stop not in best or cost < best[stop][0]:
                best[stop] = (cost, best[first][1] + [page])
    if len(words) not in best:
        raise ValueError(f"Subtitle cannot meet {MIN_PAGE_SECONDS}s minimum / {MAX_PAGE_CPS:g} "
                         "characters per second within three lines. Extend the available reading time.")
    return best[len(words)][1]


def caption_pages(episode, timeline):
    pages = []
    reveals = {w["turn"]: w["start"] for w in picture_windows(episode, timeline) if w["mode"] == "reveal"}
    for index, turn in enumerate(timeline["turns"]):
        words = validate_words(turn["words"], turn["text"], turn["wav_duration"])
        if episode.get("subtitle_mode") == "readable":
            end = (timeline["turns"][index + 1]["start"] if index + 1 < len(timeline["turns"])
                   else timeline["duration"] - (0 if episode.get("social_kind") == "exchange"
                                               else episode["outro_seconds"]))
            instruction = instruction_turn(timeline["turns"])
            if turn.get("id") in reveals:
                end = reveals[turn["id"]]
            elif episode.get("social_kind") not in ("exchange", "promo") and instruction is turn:
                window = task_window(timeline)
                end = window[0] if window is not None else turn["end"]
            try:
                groups = readable_pages(words, turn["start"], end, timeline.get("fps", 24))
            except ValueError as error:
                raise ValueError(f"Turn {turn.get('id', index)} ({turn['name']}): {error}") from error
        else:
            groups = [{"words": group, "start": turn["start"] + group[0]["start"],
                       "end": turn["start"] + group[-1]["end"],
                       "text": " ".join(word["word"] for word in group)} for group in chunks(words)]
        for group in groups:
            pages.append({**group, "name": turn["name"], "turn_start": turn["start"],
                          "turn_id": turn.get("id", str(index)), "camera": turn.get("camera"),
                          "readable": episode.get("subtitle_mode") == "readable"})
    return pages


def write_caption_timing(build, episode, timeline):
    from prepare_audio import srt_timestamp

    pages = caption_pages(episode, timeline)
    report = {
        "mode": episode.get("subtitle_mode", "legacy"),
        "minimum_seconds": MIN_PAGE_SECONDS, "maximum_characters_per_second": MAX_PAGE_CPS,
        "pages": [{"turn": page["turn_id"], "text": page["text"], "start": page["start"],
                   "end": page["end"], "duration": page["end"] - page["start"],
                   "characters_per_second": len(page["text"]) / (page["end"] - page["start"]),
                   "encoded_display_seconds": displayed_seconds(page["start"], page["end"], timeline.get("fps", 24))}
                  for page in pages],
    }
    (build / "subtitle_timing_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if episode.get("subtitle_mode") != "readable":
        return
    (build / "subtitles.srt").write_text("\n".join(
        f"{index}\n{srt_timestamp(page['start'])} --> {srt_timestamp(page['end'])}\n"
        + "\n".join(measured_lines(page["text"], 31)) + "\n"
        for index, page in enumerate(pages, 1)), encoding="utf-8")


def hook_bounds(episode):
    count = len(measured_lines(episode.get("hook", ""), HOOK_SIZE, True))
    if count > 4:
        raise ValueError("Opening hook exceeds four lines; shorten it to keep the entrance visible.")
    return 96, HOOK_BOTTOM - 20 - count * (HOOK_SIZE + 5), 504, HOOK_BOTTOM


def editorial_rows(episode):
    header = episode.get("header", {})
    rows = {"header": [], "hook": [], "task": [], "takeaway": [], "cta": []}
    for value, y, size, bold, color in (
        (header.get("brand", episode.get("branding", "")), 212, 18, True, "CDECD9"),
        (header.get("topic", episode.get("title", "")), 241, 22, True, "FFFFFF"),
    ):
        if value:
            rows["header"].append((value, y, size, bold, color))
    if episode.get("hook"):
        rows["hook"].append((episode["hook"], hook_bounds(episode)[1] + 10, HOOK_SIZE, True, "FFFFFF"))
    if episode.get("task_card"):
        summary = episode.get("task_summary", episode.get("title", ""))
        rows["task"] = [(episode.get("task_title", "DEINE AUFGABE"), 303, 24, True, "CDECD9"),
                        (summary, 344, 24, False, "FFFFFF")]
        y = max(392, 344 + len(measured_lines(summary, 24)) * 29 + 10)
        for point in episode["task_card"]:
            value = "• " + point
            rows["task"].append((value, y, 23, False, "FFFFFF"))
            y += len(measured_lines(value, 23)) * 28 + 6
        rows["task"].append((episode.get("task_hint", "Video bei Bedarf anhalten."), 615, 19, False, "FFFFFF"))
    if episode.get("takeaway"):
        rows["takeaway"] = [(episode.get("takeaway_title", "TIPPS FÜR EUREN DIALOG"), 323, 23, True, "CDECD9")]
        rows["takeaway"] += [(value, 391 + i * 56, 25, False, "FFFFFF")
                             for i, value in enumerate(episode["takeaway"])]
    for value, (y, size, bold, color) in zip(episode.get("cta", []), (
        (567, 24, True, "FFFFFF"), (607, 24, False, "FFFFFF"), (663, 22, True, "CDECD9"),
    )):
        rows["cta"].append((value, y, size, bold, color))
    return rows


def validate_layout(episode):
    """Cheap static layout checks before synthesis; the export still audits real libass pixels."""
    rows = editorial_rows(episode)
    limits = {"header": 271, "hook": HOOK_BOTTOM - 10, "task": 663, "takeaway": 612, "cta": 742}
    for card, values in rows.items():
        previous_bottom = 0
        for value, y, size, bold, _color in values:
            bottom = y + len(measured_lines(value, size, bold)) * (size + 5)
            if y < previous_bottom or bottom > limits[card]:
                raise ValueError(f"{card} text overlaps or exceeds the safe area: {value!r}; shorten the text.")
            previous_bottom = bottom
    for label in episode.get("sections", {}).values():
        if 241 + len(measured_lines(label, 22, True)) * 27 > limits["header"]:
            raise ValueError(f"Section header overlaps or exceeds the safe area: {label!r}; shorten the text.")
    for picture in episode.get("pictures", {}).values():
        if len(measured_lines(picture["label"], 24, True)) != 1:
            raise ValueError("Picture reading-card labels must fit one line.")
        if picture_layout(picture) == "notice_detail":
            if len(measured_lines(language_profile(episode)["notice_prefix"] + picture["label"],
                                  18, True, width=320)) != 1:
                raise ValueError("Notice detail labels must fit above the 320px reference.")
            continue
        if len(measured_lines(language_profile(episode)["picture_prefix"] + picture["label"],
                              19, True, width=220)) != 1:
            raise ValueError("Compact picture labels must fit beside the speaker.")
    return rows


def cover_bounds(path):
    from PIL import Image

    with Image.open(path) as image:
        width = round(image.width * 224 / image.height / 2) * 2
    x, y = round((LEFT + RIGHT - width) / 2), 332
    bounds = (x, y, x + width, y + 224)
    if x < SAFE[0] or bounds[2] > SAFE[2] or y < SAFE[1] or bounds[3] > SAFE[3]:
        raise ValueError("The book cover does not fit the social safe area; use a portrait cover.")
    return bounds


def make_ass(episode, timeline):
    from render import ass_time, escape_ass

    if episode.get("credit_policy") != "publishing_caption":
        raise ValueError("Social exports require explicit accompanying publishing-caption attribution.")
    header = HEADER
    if any(picture_layout(p) == "notice_detail" for p in episode.get("pictures", {}).values()):
        styles = []
        for name in NOTICE_STYLE_BOUNDS:
            original = "Text" if name.endswith("Text") else "Box"
            template = next(line for line in HEADER.splitlines() if line.startswith(f"Style: {original},"))
            styles.append(template.replace(f"Style: {original},", f"Style: {name},", 1))
        header = header.replace("[Events]", "\n".join(styles) + "\n[Events]")
    lines = [header]
    language = language_profile(episode)

    def event(start, end, text, style="Text"):
        if end <= start:
            raise ValueError("Caption interval must be positive.")
        start = frame_safe_time(start, timeline.get("fps", 24))
        end = frame_safe_time(end, timeline.get("fps", 24))
        lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},{style},,0,0,0,,{text}\n")

    def panel(start, end, top, bottom, opacity="18"):
        event(start, end, r"{\pos(0,0)\p1\alpha&H" + opacity + "&}"
              + f"m 96 {top} l 504 {top} 504 {bottom} 96 {bottom}" + r"{\p0}", "Box")

    def text(start, end, value, y, size=26, bold=False, color="FFFFFF", *, style="Text", bounds=None):
        width = RIGHT - LEFT if bounds is None else bounds[2] - LEFT - 8
        wrapped = measured_lines(value, size, bold, width=width)
        if (y + len(wrapped) * (size + 5) > (SAFE[3] - 5 if bounds is None else bounds[3])
                or bounds is not None and y < bounds[1]):
            raise ValueError(f"Text exceeds the safe bottom: {value!r}")
        for index, line in enumerate(wrapped):
            event(start, end, f"{{\\an7\\pos({LEFT},{y + index * (size + 5)})"
                  f"\\fs{size}\\b{int(bold)}\\c&H{color}&}}" + escape_ass(line), style)

    def emit(rows, start, end):
        for row in rows:
            text(start, end, *row)

    rows = validate_layout(episode)
    duration = timeline["duration"]
    panel(0, duration, 204, 271)
    for row in rows["header"]:
        if row[1] == 241:
            for window in section_windows(episode, timeline):
                text(window["start"], window["end"], window["label"], *row[1:])
        else:
            emit([row], 0, duration)
    for page in caption_pages(episode, timeline):
        start, end = page["start"], page["end"]
        readable = page["readable"]
        # This camera frames the examiner's mouth lower than the candidates'.
        examiner = readable and page["camera"] == "examiner"
        panel(start, end, 612 if examiner else 578 if readable else 604, 746 if examiner else 742)
        text(start, end, language["speaker_prefix"] + page["name"],
             622 if examiner else 588 if readable else 614, 19, True, "CDECD9")
        wrapped = measured_lines(page["text"], 31)
        boundaries = {start, end}
        boundaries.update(min(end, max(start, page["turn_start"] + word[field]))
                          for word in page["words"] for field in ("start", "end"))
        boundaries = sorted(boundaries)
        for a, b in zip(boundaries, boundaries[1:]):
            highlighted = active_word(page["words"], (a + b) / 2 - page["turn_start"])
            offset = 0
            for index, line in enumerate(wrapped):
                rendered = []
                for token in line.split():
                    color = "50E5FF" if offset == highlighted else "FFFFFF"
                    rendered.append(r"{\c&H" + color + "&}" + escape_ass(token))
                    offset += 1
                y = 650 + index * 33 if examiner else 625 + index * 35 if readable else 651 + index * 38
                event(a, b, f"{{\\an7\\pos({LEFT},{y})\\fs{29 if examiner else 31}}}" + " ".join(rendered))

    for picture in picture_windows(episode, timeline):
        start, end = picture["start"], picture["end"]
        label = episode["pictures"][picture["picture"]]["label"]
        if picture.get("layout") == "notice_detail":
            reveal = picture["mode"] == "reveal"
            style = "NoticeReadingBox" if reveal else "NoticeReferenceBox"
            left, top, right, bottom = NOTICE_STYLE_BOUNDS[style]
            event(start, end, r"{\pos(0,0)\p1\alpha&H08&}"
                  + f"m {left} {top} l {right} {top} {right} {bottom} {left} {bottom}"
                  + r"{\p0}", style)
            if reveal:
                text(start, end, language["notice_title"], 288, 24, True, "CDECD9")
                text(start, end, language["learning_pause"], 322, 19)
            else:
                text(start, end, language["notice_prefix"] + label, 764, 18, True, "CDECD9",
                     style="NoticeReferenceText", bounds=NOTICE_STYLE_BOUNDS["NoticeReferenceText"])
            continue
        if picture["mode"] == "reveal":
            panel(start, end, 287, 742, "08")
            text(start, end, label, 303, 24, True, "CDECD9")
            if picture.get("purpose") == "task":
                text(start, end, language["task_picture_prompt"], 650, 24)
            else:
                text(start, end, language["picture_prompt"], 579, 24)
                text(start, end, language["experience_prompt"], 620, 24)
            text(start, end, language["learning_pause"], 700, 19)
        else:
            event(start, end, r"{\pos(0,0)\p1\alpha&H08&}"
                  + "m 96 280 l 332 280 332 437 96 437" + r"{\p0}", "Box")
            text(start, end, language["picture_prefix"] + label, 284, 19, True, "CDECD9")
    if episode.get("social_kind") == "exchange":
        return "".join(lines)
    intro_end = timeline["turns"][0]["start"]
    if intro_end > 0 and rows["hook"]:
        _left, top, _right, bottom = hook_bounds(episode)
        panel(0, intro_end, top, bottom)
        emit(rows["hook"], 0, intro_end)
    window = task_window(timeline)
    if episode.get("social_kind") != "promo" and rows["task"] and window is not None:
        start, end = window
        panel(start, end, 287, 663, "08")
        emit(rows["task"], start, end)
    if episode["outro_seconds"] == 0:
        return "".join(lines)
    outro = duration - episode["outro_seconds"]
    take_end = outro + takeaway_seconds(episode)
    if take_end > outro:
        panel(outro, take_end, 300, 612, "08")
        emit(rows["takeaway"], outro, take_end)
    panel(take_end, duration, 287, 742, "08")
    emit(rows["cta"], take_end, duration)
    return "".join(lines)


def write_publication(build, episode):
    language = language_profile(episode)
    credit = (Path(__file__).resolve().parent / "assets/studio/CREDITS.txt").read_text(encoding="utf-8")
    publication = episode.get("publication", {})
    picture_credit = "\n".join(dict.fromkeys(p["credit"] for p in episode.get("pictures", {}).values()))
    if picture_credit:
        picture_credit += "\n\n"
        credit += "\nPicture stimuli\n" + picture_credit
    caption = (
        f"{episode['title']} | {episode.get('label', '')}\n\n"
        + publication.get("intro", episode.get("hook", "")) + "\n"
        + " ".join(episode.get("cta", [])) + "\n\n"
        + publication.get("disclosure", episode.get("disclaimer", ""))
        + "\n" + language["ai_disclosure"] + "\n\n"
        + picture_credit +
        "Snow Rig (CC) Blender Foundation | studio.blender.org\n"
        "https://studio.blender.org/characters/snow/v4/\n"
        "Rain Rig (CC) Blender Foundation | studio.blender.org\n"
        "https://studio.blender.org/characters/rain/v3/\n"
        "CC BY 4.0: https://creativecommons.org/licenses/by/4.0/\n"
        + language["rig_adaptation"] + "\n\n"
        + " ".join(publication.get("hashtags", [])) + "\n"
    )
    (build / "publishing_caption.txt").write_text(caption, encoding="utf-8")
    (build / "CREDITS.txt").write_text(credit, encoding="utf-8")


def audit_ass(build, ass, *, raise_on_unsafe=True):
    """Rasterize EVERY distinct text/highlight/panel state with the actual libass."""
    from PIL import Image
    from render import ass_time
    caption_fonts(build)

    states = list(dict.fromkeys(line.split(",", 9)[-1] + "\t" + line.split(",", 9)[3]
                                for line in ass.splitlines() if line.startswith("Dialogue:")))
    audit = [ass[:ass.index("Dialogue:")]]
    for index, state in enumerate(states):
        text, style = state.rsplit("\t", 1)
        audit.append(f"Dialogue: 0,{ass_time(index)},{ass_time(index + 1)},{style},,0,0,0,,{text}\n")
    (build / "safe_zone_audit.ass").write_text("".join(audit), encoding="utf-8")
    command = [
        "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
        f"color=c=black:s=720x1280:r=1:d={len(states)}",
        "-vf", "ass=safe_zone_audit.ass:fontsdir=caption_fonts", "-pix_fmt", "gray", "-f", "rawvideo", "pipe:1",
    ]
    bounds, unsafe, notice_states = [], [], []
    with (build / "safe_zone_audit.log").open("w") as errors:
        process = subprocess.Popen(command, cwd=build, stdout=subprocess.PIPE, stderr=errors)
        try:
            for index, state in enumerate(states):
                needed, data = 720 * 1280, bytearray()
                while len(data) < needed:
                    part = process.stdout.read(needed - len(data))
                    if not part:
                        raise RuntimeError(f"Caption raster audit stopped at {index}; see safe_zone_audit.log")
                    data.extend(part)
                bbox = Image.frombytes("L", (720, 1280), bytes(data)).point(lambda p: 255 if p > 5 else 0).getbbox()
                if bbox is None:
                    raise ValueError(f"Caption state rendered no visible pixels: {state}")
                style = state.rsplit("\t", 1)[1]
                allowed = NOTICE_STYLE_BOUNDS.get(style, SAFE)
                if style in NOTICE_STYLE_BOUNDS:
                    notice_states.append({"bounds": bbox, "policy_bounds": allowed, "state": state})
                if bbox[0] < allowed[0] or bbox[1] < allowed[1] or bbox[2] > allowed[2] or bbox[3] > allowed[3]:
                    unsafe.append({"bounds": bbox, "state": state})
                bounds.append({"bounds": bbox, "state": state})
            if process.wait() != 0:
                raise RuntimeError("Caption raster audit failed; see safe_zone_audit.log")
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.terminate()
                process.wait()
    report = {"canvas": [720, 1280], "safe_rectangle": SAFE, "sources": SOURCES,
              "method": "Every unique libass-rendered text, highlighted-word state and panel pixel bounds.",
              "states_checked": len(bounds), "states": bounds, "all_inside": not unsafe,
              "unsafe_states": unsafe}
    if notice_states:
        report["notice_graphic_policy"] = {
            "states": notice_states, "bounds": NOTICE_STYLE_BOUNDS,
            "standard_states_inside_baseline": not any(
                item["state"].rsplit("\t", 1)[1] not in NOTICE_STYLE_BOUNDS for item in unsafe),
            "note": "Explicit user-approved notice graphic bounds outside the baseline rectangle; "
                    "not Instagram/TikTok safe-zone certification. Ordinary text/subtitle/panel "
                    "states still use the unchanged baseline rectangle.",
        }
    by_state = {item["state"]: item["bounds"] for item in bounds}
    text_events = []

    def centiseconds(value):
        hours, minutes, seconds = value.split(":")
        whole, fraction = seconds.split(".")
        return ((int(hours) * 60 + int(minutes)) * 60 + int(whole)) * 100 + int(fraction)

    for line in ass.splitlines():
        if not line.startswith("Dialogue:"):
            continue
        fields = line.split(",", 9)
        if fields[3] in ("Text", "NoticeReferenceText"):
            text_events.append((centiseconds(fields[1]), centiseconds(fields[2]),
                                by_state[fields[-1] + "\t" + fields[3]], fields[-1]))
    overlaps = []
    for index, a in enumerate(text_events):
        for b in text_events[index + 1:]:
            if max(a[0], b[0]) >= min(a[1], b[1]):
                continue
            if max(a[2][0], b[2][0]) < min(a[2][2], b[2][2]) and max(a[2][1], b[2][1]) < min(a[2][3], b[2][3]):
                overlaps.append([a[3], b[3]])
    report["overlapping_text_states"] = overlaps
    (build / "safe_zone_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if unsafe and raise_on_unsafe:
        raise ValueError(f"Unsafe rendered text/panel pixels: {unsafe[0]}")
    if overlaps and raise_on_unsafe:
        raise ValueError(f"Simultaneously visible text overlaps: {overlaps[0]}")
    return report
