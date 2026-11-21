"""Compose native Swiss fide picture-choice and oral-answer layouts."""

import argparse
import html
import json
from pathlib import Path
import shutil

from listening_2d.preparation.prepare_fide import EPISODE, ROOT, approved_episode, atomic_json, read, sha256_file, verify_files
from align_words import validate_words

CROP_BOTTOM = {"E042.png": 410, "E043.png": 540, "E044.png": 305,
               "E045.png": 465, "E046.png": 425, "E047.png": 380}
STYLES = """
body { background:#f2f6f1; }
.flag, html[data-resolution="portrait"] .flag {
  width:54px;height:54px;flex-shrink:0;background:url("assets/flag.png") center/contain no-repeat; }
.clip.scene { padding:34px;display:flex;flex-direction:column; }
.eyebrow { font-size:28px;line-height:1.2;margin-bottom:12px;color:#8f2d35; }
.main { flex:1;min-height:0;display:flex;flex-direction:column;justify-content:center;gap:20px; }
.main h1,.main h2,.main p { margin:0; }
.main h1 { font-size:72px;line-height:1.18; }
.main h2 { font-size:48px;line-height:1.2; }
.main p,.main .instruction { font-size:38px;line-height:1.36; }
.main .instruction { text-wrap:pretty; }
.main .instruction-word { white-space:nowrap; }
.phase { flex-shrink:0;margin-top:18px;padding-top:16px;min-height:59px;font-size:30px; }
.progress { flex-shrink:0; }
.pictures { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px; }
.picture-option { min-width:0;height:450px;display:flex;flex-direction:column;align-items:center;
  justify-content:center;gap:10px;padding:12px;border:2px solid #b8cbc3;border-radius:18px;background:white; }
.picture-option img { width:100%;height:345px;object-fit:contain; }
.option-label { display:flex;align-items:center;justify-content:center;gap:16px;
  font-size:48px;line-height:1.2;font-weight:700;color:#283e3c; }
.option-number { font-size:50px; }
.oral { align-items:center;text-align:center;gap:34px; }
.oral svg { width:140px;height:140px;color:#8f2d35; }
.correct-picture { height:280px;max-width:620px;align-self:center;object-fit:contain; }
.solution-answer { padding:22px;border:2px solid #44806d;border-radius:18px;background:#e0f1e7;color:#215640; }
.main .note { font-size:28px;line-height:1.3;color:#536861; }
aside { top:230px;height:620px;padding:24px; }
.cover { width:180px;height:240px;margin-bottom:12px; }
aside h2 { font-size:30px;line-height:1.2;margin-bottom:12px; }
aside p { font-size:28px;line-height:1.35;margin-bottom:16px; }
aside p:last-child { margin-bottom:0; }
html[data-resolution="portrait"] .clip.scene { padding:28px; }
html[data-resolution="portrait"] .eyebrow { font-size:30px;margin-bottom:10px; }
html[data-resolution="portrait"] .main { gap:16px; }
html[data-resolution="portrait"] .main h1 { font-size:68px; }
html[data-resolution="portrait"] .main h2 { font-size:48px; }
html[data-resolution="portrait"] .main p,
html[data-resolution="portrait"] .main .instruction { font-size:42px;line-height:1.32; }
html[data-resolution="portrait"] .pictures { grid-template-columns:1fr;gap:8px; }
html[data-resolution="portrait"] .picture-option { height:240px;flex-direction:row;padding:8px;gap:18px; }
html[data-resolution="portrait"] .picture-option img { width:650px;height:220px;min-width:0; }
html[data-resolution="portrait"] .option-label { flex-direction:column;gap:12px;min-width:70px;font-size:48px; }
html[data-resolution="portrait"] .option-number { font-size:50px; }
html[data-resolution="portrait"] .phase { font-size:32px;margin-top:14px;padding-top:14px;min-height:59px; }
html[data-resolution="portrait"] .correct-picture { height:380px;max-width:100%; }
html[data-resolution="portrait"] .main .note { font-size:30px; }
html[data-resolution="portrait"] aside { top:1420px;height:276px;padding:20px 28px; }
html[data-resolution="portrait"] .cover { width:136px;height:230px;margin-right:28px; }
html[data-resolution="portrait"] aside h2 { font-size:32px;margin:12px 0; }
html[data-resolution="portrait"] aside p { font-size:30px;margin:0 0 12px; }
"""


def word_mapping(turn):
    words = validate_words(turn["words"], turn["text"], turn["wav_duration"])
    labels = turn.get("display_text", turn["text"]).split()
    groups = turn.get("display_word_groups", [[i] for i in range(len(words))])
    if (len(labels) != len(groups)
            or [i for group in groups for i in group] != list(range(len(words)))):
        raise ValueError(f"Incomplete real speech/display mapping: {turn['id']}")
    return [{"index": index, "label": label,
             "start": turn["start"] + words[group[0]]["start"],
             "end": turn["start"] + words[group[-1]]["end"],
             "selector": f"#word-{turn['id']}-{index}"}
            for index, (label, group) in enumerate(zip(labels, groups))]


def option_markup(item):
    result = []
    for index, letter in enumerate("ABC"):
        numeric = item["options"][index].split()[-1] if item["number"] in (8, 10) else ""
        number = f'<span class="option-number">{numeric}</span>' if numeric else ""
        result.append(f'<div class="picture-option"><span class="option-label">{letter}{number}</span>'
                      f'<img src="assets/item-{item["number"]}-{letter}.png" alt="Bild {letter}"></div>')
    return '<div class="pictures">' + "".join(result) + "</div>"


def scene_body(event, episode, cards, mappings):
    escaped, card = html.escape, event["card"]
    if card == "title" and not event.get("visible"):
        return f'<h1 class="intro-title">{escaped(episode["title"])}</h1>', "fide · A2-B1"
    if event.get("visible"):
        words = mappings[event["id"]]
        content = " ".join(f'<span class="instruction-word" id="word-{event["id"]}-{w["index"]}">'
                           f'{escaped(w["label"])}</span>' for w in words)
        if card == "title":
            return f'<h1 class="intro-title">{content}</h1>', "fide · A2-B1"
        heading = {"setup": "So üben Sie", "a2_instruction": "A2 · Drei Bilder",
                   "b1_instruction": "B1 · Mündlich antworten", "transition": episode["transition"]["heading"],
                   "end_test": "Geschafft!", "solutions_instruction": "Lösungen und Modellantworten"}
        heading.update({"context_" + s["id"]: s["heading"] for s in episode["situations"]})
        return f'<h2>{escaped(heading[card])}</h2><p class="instruction">{content}</p>', "Verstehen"
    if card.startswith("item_"):
        item = cards[card]
        heading = f'<h2>Aufgabe {item["number"]}</h2>'
        if item["level"] == "A2":
            return heading + option_markup(item), "A2 · Passendes Bild wählen"
        microphone = ('<svg viewBox="0 0 100 100" fill="none" stroke="currentColor" stroke-width="5" aria-hidden="true">'
                      '<rect x="35" y="8" width="30" height="52" rx="15"></rect>'
                      '<path d="M22 44v6a28 28 0 0 0 56 0v-6M50 78v15M32 93h36"></path></svg>')
        return heading + microphone + "<p>Hören Sie die Frage.<br>Antworten Sie danach laut.</p>", "B1 · Verstehen"
    if card.startswith("solution_"):
        number = int(card.split("_")[-1])
        item = cards[f"item_{number}"]
        if item["level"] == "A2":
            key = item["answer"]
            return (f'<h2>Frage {number} · Lösung {key}</h2>'
                    f'<img class="correct-picture" src="assets/item-{number}-{key}.png" alt="Lösung {key}">'
                    f'<p class="solution-answer" data-answer="{number}:{key}">{escaped(item["solution"])}</p>'), "A2 · Lösungen"
        return (f'<h2>Frage {number}</h2><p>{escaped(item["question"])}</p>'
                f'<p class="solution-answer" data-answer="{number}:model">{escaped(item["solution"])}</p>'
                '<p class="note">Beispielantwort · Andere passende Formulierungen sind möglich.</p>'), "B1 · Modellantwort"
    if card == "cta":
        return ("<h1>Mehr Aufgaben<br>im Komplettband</h1><p>fide A2-B1<br>Sprechen · Schreiben · Hören</p>"
                "<p>Amazon: Link in der<br>Beschreibung oder Bio</p>"), "Weiter üben"
    raise ValueError(f"Unknown fide card: {card}")


def crop_options(episode, assets):
    from PIL import Image
    result = {}
    for situation in episode["situations"][:2]:
        for item in situation["items"]:
            source = (EPISODE.parent / item["image"]).resolve(strict=True)
            with Image.open(source) as image:
                width, height = image.size
                bottom = CROP_BOTTOM[source.name]
                if not 0 < bottom < height:
                    raise ValueError("Invalid measured picture crop.")
                for index, letter in enumerate("ABC"):
                    bounds = (round(width * index / 3), 0, round(width * (index + 1) / 3), bottom)
                    name = f"item-{item['number']}-{letter}.png"
                    image.crop(bounds).convert("RGB").save(assets / name)
                    result[name] = {"source": str(source), "source_sha256": sha256_file(source),
                                    "crop": list(bounds), "sha256": sha256_file(assets / name)}
    return result


def compose(build, *, episode=None, fonts=None):
    if episode is None:
        episode = approved_episode()
    content, timeline = read(build / "sample_content.json"), read(build / "timeline.json")
    if content["episode"] != episode:
        raise ValueError("Composed content must match the reviewed, user-approved script.")
    verify_files(read(build / "input_pin.json")["files"])
    mappings = {t["id"]: word_mapping(t) for t in timeline["turns"] if t["visible"]}
    aligned = read(build / "word_alignment.json")
    if {t["id"] for t in aligned["turns"]} != set(mappings):
        raise ValueError("All visible narration needs actual measured alignment.")
    template = (ROOT / "composition" / "index.html").read_text(encoding="utf-8")
    template = template.replace('aria-label="Österreich"', 'aria-label="Schweiz"')
    template = template.replace("ÖIF B1 Hören – Übungsbuch mit Audio", "fide A2-B1 Komplettband")
    template = template.replace("ÖIF B1 Hören", "fide A2-B1 Verstehen")
    template = template.replace("Hörübungen, Transkripte<br>und Erklärungen", "Sprechen · Schreiben<br>und Hören")
    layouts = {}
    for layout, width, height in (("landscape", 1920, 1080), ("portrait", 1080, 1920)):
        target, scenes, pauses, highlights = build / layout, [], [], []
        assets = target / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        sources = {
            "gsap.min.js": ROOT / "node_modules" / "gsap" / "dist" / "gsap.min.js",
            "arial.ttf": Path(r"C:\Windows\Fonts\arial.ttf"),
            "arialbd.ttf": Path(r"C:\Windows\Fonts\arialbd.ttf"),
            "logo.png": ROOT.parent / "pilot_3d" / "assets" / "deutschkompass-logo.png",
            "book.jpg": (EPISODE.parent / episode["promotion"]["cover"]).resolve(strict=True),
            "flag.png": ROOT.parent / "pilot_3d" / "assets" / "flags" / "switzerland.png",
            "dialogue.wav": build / "dialogue.wav",
        }
        sources.update(fonts or {})
        for name, path in sources.items():
            shutil.copyfile(path, assets / name)
        pictures = crop_options(episode, assets)
        for index, event in enumerate(timeline["events"]):
            body, heading = scene_body(event, episode, content["cards"], mappings)
            counter = ""
            if event["kind"] == "silence":
                counter = f'<span class="countdown" id="count-{index}">{event["duration"]:g} s</span>'
                pauses.append({"index": index, "start": event["start"], "duration": event["duration"]})
            phase = f'<div class="phase"><span class="phase-label">{html.escape(event["phase"])}</span>{counter}</div>'
            if counter:
                phase += f'<div class="progress"><div class="progress-fill" id="fill-{index}"></div></div>'
            oral = event["card"].startswith("item_") and content["cards"][event["card"]]["level"] == "B1"
            scenes.append(
                f'<section id="scene-{index}" class="clip scene" data-start="{event["start"]}" '
                f'data-duration="{event["duration"]}" data-track-index="0" data-event-id="{event["id"]}">'
                f'<div class="eyebrow">{html.escape(heading)}</div>'
                f'<div class="main{" oral" if oral else ""}">{body}</div>{phase}</section>')
            if event.get("visible"):
                highlights.extend(mappings[event["id"]])
        replacements = {
            "{{LAYOUT}}": layout, "{{WIDTH}}": str(width), "{{HEIGHT}}": str(height),
            "{{DURATION}}": str(timeline["duration"]), "{{SCENES}}": "\n".join(scenes),
            "{{PAUSES}}": json.dumps(pauses), "{{TITLE_WORDS}}": "[]",
            "{{INSTRUCTION_WORDS}}": json.dumps(highlights, ensure_ascii=False),
            "{{EXTRA_STYLES}}": STYLES, "{{SCOPE_LABEL}}": "A2 · 7–12 / B1 · 13–18",
            "{{FOOTER_NOTE}}": "",
            "{{AMAZON}}": "👇 Amazon: Link in der Beschreibung" if layout == "landscape" else "Amazon: Bio / Beschreibung",
        }
        document = template
        for key, value in replacements.items():
            document = document.replace(key, value)
        if "{{" in document:
            raise ValueError("Unresolved fide layout placeholder.")
        (target / "index.html").write_text(document, encoding="utf-8")
        atomic_json(target / "hyperframes.json", {"media": {"autoProxy": False}})
        atomic_json(target / "assets_manifest.json", {
            p.name: sha256_file(p) for p in assets.iterdir() if p.is_file()})
        layouts[layout] = {"html_sha256": sha256_file(target / "index.html"), "picture_crops": pictures}
    atomic_json(build / "composition_receipt.json", {
        "generator_sha256": sha256_file(Path(__file__)),
        "template_sha256": sha256_file(ROOT / "composition" / "index.html"),
        "timeline_sha256": sha256_file(build / "timeline.json"),
        "layouts": layouts, "word_mappings": mappings,
        "exam_questions_and_recordings_subtitled": False})
    print("Fide native landscape/portrait compositions ready.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    compose(parser.parse_args().build.resolve())
