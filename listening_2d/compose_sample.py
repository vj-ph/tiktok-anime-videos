"""Generate self-contained HyperFrames layouts from the measured sample."""

import argparse
import html
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "pilot_3d"))
from prepare_audio import atomic_json, sha256_file
from align_words import validate_words


def title_intervals(timeline):
    turn = next(t for t in timeline["turns"] if t["id"] == "title")
    words = validate_words(turn["words"], turn["text"], turn["wav_duration"])
    labels = [("ÖIF", 0, 3), ("B1", 3, 5), ("Hören", 5, 6),
              ("Unabhängige", 6, 7), ("Prüfungssimulation", 7, 8)]
    if len(words) != 8:
        raise ValueError("Title speech tokens changed; update the explicit measured mapping.")
    return [{"index": i, "label": label,
             "start": turn["start"] + words[first]["start"],
             "end": turn["start"] + words[last - 1]["end"]}
            for i, (label, first, last) in enumerate(labels)]


def instruction_intervals(timeline, text, turn_id="instruction"):
    turn = next(t for t in timeline["turns"] if t["id"] == turn_id)
    if turn["text"] != text:
        raise ValueError("Displayed Anleitung differs from the aligned speech.")
    words = validate_words(turn["words"], text, turn["wav_duration"])
    return [{"index": i, "label": word["word"],
             "start": turn["start"] + word["start"], "end": turn["start"] + word["end"]}
            for i, word in enumerate(words)]


def options_html(question, reveal=False, show_solution=True, annotate=False):
    body = ""
    for letter, text in question["options"].items():
        correct = reveal and letter == question["answer"]
        classes = "option correct" if correct else "option"
        attribute = f' data-answer="{html.escape(letter)}"' if correct and annotate else ""
        body += (f'<div class="{classes}"{attribute}><span class="letter">{html.escape(letter)}</span>'
                 f'<span>{html.escape(text)}</span></div>')
    if reveal and show_solution:
        body += f'<div class="solution">Richtige Antwort: {html.escape(question["answer"])}</div>'
    return body


def compose(build):
    build = build.resolve()
    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    content = json.loads((build / "sample_content.json").read_text(encoding="utf-8"))
    episode = content["episode"]
    guided = timeline.get("practice_mode") == "guided"
    title_words = title_intervals(timeline)
    instruction_words = instruction_intervals(
        timeline, content["instructions"]["sections"][0]["instruction"])
    template = (ROOT / "composition" / "index.html").read_text(encoding="utf-8")
    question_cards = {
        "example": episode["sections"][0]["example"],
        "task1": episode["sections"][0]["tasks"][0],
    }
    escaped = html.escape
    dirs = []
    for layout, width, height in (("landscape", 1920, 1080), ("portrait", 1080, 1920)):
        target = build / layout
        assets = target / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        sources = {
            "gsap.min.js": ROOT / "node_modules" / "gsap" / "dist" / "gsap.min.js",
            "arial.ttf": Path(r"C:\Windows\Fonts\arial.ttf"),
            "arialbd.ttf": Path(r"C:\Windows\Fonts\arialbd.ttf"),
            "logo.png": ROOT.parent / "pilot_3d" / "assets" / "deutschkompass-logo.png",
            "book.jpg": ROOT / "episodes" / episode["promotion"]["cover_source"],
            "dialogue.wav": build / "dialogue.wav",
        }
        for name, source in sources.items():
            shutil.copyfile(source, assets / name)
        scenes, pauses = [], []
        for index, event in enumerate(timeline["events"]):
            card, phase = event["card"], event["phase"]
            title = {"title": "Unabhängige Prüfungssimulation", "setup": "Vorschau",
                     "instruction": "Anleitung", "example": "Beispiel",
                     "task1": "Aufgabe 1"}.get(card, "Vorschau")
            if card == "title":
                spans = [f'<span class="title-word" id="title-word-{w["index"]}">{w["label"]}</span>'
                         for w in title_words]
                body = f'<h1 class="intro-title">{" ".join(spans[:3])}<br>{" ".join(spans[3:])}</h1>'
                if not guided:
                    body += "<p>Eine unabhängige Hörübung<br>von Deutsch Kompass</p>"
            elif card == "setup":
                body = ("<h1>Bereit zum Hören?</h1><p>Papier und Stift bereitlegen.</p>"
                        "<p>Diese Vorschau zeigt ein Beispiel und Aufgabe 1.</p>")
                body += ("<p>Erst selbst antworten. Danach die Lösung vergleichen.</p>"
                         if guided else "<p>Die Antwort zu Aufgabe 1 wird hier nicht eingeblendet.</p>")
            elif card == "instruction":
                spans = [f'<span class="instruction-word" id="instruction-word-{w["index"]}">'
                         f'{escaped(w["label"])}</span>' for w in instruction_words]
                body = f'<h2>Hören · Teil 1</h2><p class="instruction">{" ".join(spans)}</p>'
            elif card in question_cards:
                q = question_cards[card]
                body = f'<h2>{escaped(q["question"])}</h2>'
                reveal = event["kind"] == "reveal" or (
                    not guided and card == "example" and event["id"] == "example_answer")
                body += options_html(q, reveal)
                title = "Beispiel" if card == "example" else "Aufgabe 1"
            elif card == "end":
                title = "Vorschau"
                body = ("<h1>So geht es weiter</h1><p>In der vollständigen Simulation folgen "
                        "Aufgabe 2 und die übrigen drei Teile.</p>")
                body += ("<p>Erst selbst antworten, dann die Lösung vergleichen.</p>"
                         if guided else "<p>Die Lösungen stehen erst nach dem gesamten Test.</p>")
            else:
                title = "Dein nächster Schritt"
                body = ("<h1>Weiter hören.<br>Sicherer antworten.</h1>"
                        "<p>Mehr Hörübungen, Transkripte und Erklärungen im Buch.</p>")
            counter = ""
            if event["kind"] == "silence":
                counter = f'<span class="countdown" id="count-{index}">{round(event["duration"])} s</span>'
                pauses.append({"index": index, "start": event["start"], "duration": event["duration"]})
            status = f'<div class="phase"><span class="phase-label">{escaped(phase)}</span>{counter}</div>'
            if counter:
                status += f'<div class="progress"><div class="progress-fill" id="fill-{index}"></div></div>'
            scenes.append(
                f'<section id="scene-{index}" class="clip scene" data-start="{event["start"]}" '
                f'data-duration="{event["duration"]}" data-track-index="0">'
                f'<div class="eyebrow">{escaped(title)} · Teil 1</div>{body}{status}</section>'
            )
        replacements = {
            "{{LAYOUT}}": layout, "{{WIDTH}}": str(width), "{{HEIGHT}}": str(height),
            "{{DURATION}}": str(timeline["duration"]), "{{SCENES}}": "\n".join(scenes),
            "{{PAUSES}}": json.dumps(pauses),
            "{{TITLE_WORDS}}": json.dumps(title_words, ensure_ascii=False),
            "{{INSTRUCTION_WORDS}}": json.dumps(instruction_words, ensure_ascii=False),
            "{{EXTRA_STYLES}}": "",
            "{{SCOPE_LABEL}}": "VORSCHAU · Teil 1, Beispiel + Aufgabe 1",
            "{{FOOTER_NOTE}}": "" if guided else
            "<span>Unabhängige Übung · Keine offizielle ÖIF-Prüfung</span>",
            "{{AMAZON}}": escaped(episode["promotion"][
                "youtube_label" if layout == "landscape" else "social_label"]),
        }
        result = template
        for placeholder, value in replacements.items():
            result = result.replace(placeholder, value)
        if "{{" in result:
            raise ValueError("Unresolved HTML template placeholder.")
        (target / "index.html").write_text(result, encoding="utf-8")
        atomic_json(target / "hyperframes.json", {"media": {"autoProxy": False}})
        atomic_json(target / "package.json", {
            "name": f"listening-sample-{layout}", "private": True,
            "scripts": {
                "check": "python -X utf8 ..\\..\\..\\hyperframes_local.py check --json",
                "render": "python -X utf8 ..\\..\\..\\hyperframes_local.py render",
            },
        })
        atomic_json(target / "assets_manifest.json", {
            name: sha256_file(assets / name) for name in sources
        })
        dirs.append(str(target))
    atomic_json(build / "composition_receipt.json", {
        "template_sha256": sha256_file(ROOT / "composition" / "index.html"),
        "generator_sha256": sha256_file(Path(__file__)),
        "timeline_sha256": sha256_file(build / "timeline.json"),
        "layouts": dirs, "title_mapping": title_words, "instruction_mapping": instruction_words,
    })
    print("Generated native landscape and portrait compositions.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    compose(parser.parse_args().build)
