"""Reflow the complete measured listening practice into both native layouts."""

import argparse
import html
import json
from pathlib import Path
import shutil

from compose_sample import ROOT, instruction_intervals, options_html, title_intervals
from prepare_sample import atomic_json, sha256_file

STYLES = """
    .clip.scene.pair, .clip.scene.matching { padding: 38px 44px; }
    .pair .eyebrow { margin-bottom: 14px; }
    .pair h2 { font-size: 32px; line-height: 1.22; margin-bottom: 12px; }
    .pair .option { font-size: 28px; padding: 12px 18px; margin-bottom: 10px; }
    .question-group { margin-bottom: 16px; }
    .binary-options { display: flex; gap: 18px; }
    .binary-options .option { flex: 1; justify-content: center; }
    .pair .solution { font-size: 26px; margin-top: 12px; }
    .pair .phase { margin-top: 16px; font-size: 26px; padding-top: 14px; }
    .matching h2 { font-size: 40px; margin-bottom: 14px; }
    .matching .option { font-size: 26px; padding: 8px 20px; margin-bottom: 8px; }
    .matching .phase { margin-top: 18px; font-size: 26px; padding-top: 14px; }
    .matching .solution { font-size: 26px; margin-top: 10px; }
    .instruction-long .instruction { font-size: 35px; }
    .answer-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
    .answer-cell { border: 2px solid #b8cbc3; border-radius: 14px; padding: 16px;
      font-size: 30px; background: #e0f1e7; color: #215640; }
    .answer-cell strong { margin-right: 16px; }
    html[data-resolution="portrait"] .clip.scene.pair,
    html[data-resolution="portrait"] .clip.scene.matching { padding: 36px; }
    html[data-resolution="portrait"] .pair .eyebrow { font-size: 28px; margin-bottom: 16px; }
    html[data-resolution="portrait"] .pair h2 { font-size: 34px; margin-bottom: 12px; }
    html[data-resolution="portrait"] .pair .option { font-size: 30px;
      padding: 12px 16px; margin-bottom: 14px; }
    html[data-resolution="portrait"] .pair .phase { font-size: 30px; margin-top: 20px; }
    html[data-resolution="portrait"] .matching h2 { font-size: 43px; margin-bottom: 18px; }
    html[data-resolution="portrait"] .matching .option { font-size: 31px;
      padding: 12px 20px; margin-bottom: 14px; }
    html[data-resolution="portrait"] .matching .phase { font-size: 30px; margin-top: 22px; }
    html[data-resolution="portrait"] .instruction-long .instruction {
      font-size: 40px; line-height: 1.38; }
"""


def card_body(card, reveal=False):
    if card["type"] != "pair":
        question = card["questions"][0]
        return (f'<h2>{html.escape(question["question"])}</h2>' +
                options_html(question, reveal, annotate=True))
    pieces, answers = [], []
    for index, question in enumerate(card["questions"]):
        number = question.get("number")
        label = f"{number}. " if number else ""
        prompt = question.get("statement", question.get("question"))
        body = f'<div class="question-group"><h2>{label}{html.escape(prompt)}</h2>'
        if "statement" in question:
            body += '<div class="binary-options">'
            for answer in ("richtig", "falsch"):
                correct = reveal and answer == question["answer"]
                attribute = f' data-answer="{answer}"' if correct else ""
                classes = "option correct" if correct else "option"
                body += f'<div class="{classes}"{attribute}>{answer.capitalize()}</div>'
            body += "</div>"
        else:
            body += options_html(question, reveal, show_solution=False, annotate=True)
        pieces.append(body + "</div>")
        answers.append(f'{number if number else index + 1}: {html.escape(question["answer"])}')
    if reveal:
        pieces.append(f'<div class="solution">Richtige Antworten: {" · ".join(answers)}</div>')
    return "".join(pieces)


def visual_events(events):
    result = []
    for event in events:
        if (result and event["kind"] == "speech" and result[-1]["kind"] == "speech"
                and all(event[key] == result[-1][key] for key in ("card", "phase", "part"))
                and event["start_frame"] == result[-1]["end_frame"]):
            previous = result[-1]
            previous.update(end=event["end"], end_frame=event["end_frame"],
                            duration=event["end"] - previous["start"])
            previous["event_ids"].append(event["id"])
        else:
            result.append({**event, "event_ids": [event["id"]]})
    return result


def compose(build):
    build = build.resolve()
    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    content = json.loads((build / "sample_content.json").read_text(encoding="utf-8"))
    if timeline.get("scope") != "full":
        raise ValueError("Full composition requires the measured complete timeline.")
    title_words = title_intervals(timeline)
    instruction_words, by_part = [], {}
    for section in content["instructions"]["sections"]:
        part = section["part"]
        words = instruction_intervals(timeline, section["instruction"], f"instruction_{part}")
        for word in words:
            word["selector"] = f'#instruction-{part}-word-{word["index"]}'
        by_part[part] = words
        instruction_words.extend(words)
    template = (ROOT / "composition" / "index.html").read_text(encoding="utf-8")
    scene_events = visual_events(timeline["events"])
    scenes, pauses = [], []
    for index, event in enumerate(scene_events):
        card, part, phase = event["card"], event["part"], event["phase"]
        classes, label = [], "ÖIF B1 Hören"
        if card == "title":
            spans = [f'<span class="title-word" id="title-word-{w["index"]}">{w["label"]}</span>'
                     for w in title_words]
            body = f'<h1 class="intro-title">{" ".join(spans[:3])}<br>{" ".join(spans[3:])}</h1>'
        elif card == "setup":
            label = "Vorbereitung"
            body = ("<h1>Bereit zum Hören?</h1><p>Papier und Stift bereitlegen.</p>"
                    "<p>Vier Teile · 20 Aufgaben</p>"
                    "<p>Erst selbst antworten. Danach die Lösung vergleichen.</p>")
        elif card.startswith("instruction_"):
            label = "Anleitung"
            spans = [f'<span class="instruction-word" id="instruction-{part}-word-{w["index"]}">'
                     f'{html.escape(w["label"])}</span>' for w in by_part[part]]
            body = f'<h2>Hören · Teil {part}</h2><p class="instruction">{" ".join(spans)}</p>'
            if part == 4:
                classes.append("instruction-long")
        elif card in content["cards"]:
            question_card = content["cards"][card]
            label = question_card["label"]
            classes.append(question_card["type"])
            body = card_body(question_card, event["kind"] == "reveal")
        elif card == "end":
            label = f"Teil {part}"
            body = (f'<h1>Teil {part} beendet</h1>' if part < 4 else
                    "<h1>Hören abgeschlossen</h1><p>Alle 20 Aufgaben sind bearbeitet.</p>")
        elif card == "summary":
            label = "Deine Antworten"
            keys = content["episode"]["review"]["answer_key"]
            body = "<h1>Lösungen im Überblick</h1><div class=\"answer-grid\">"
            body += "".join(f'<div class="answer-cell"><strong>{number}</strong>{html.escape(keys[str(number)])}</div>'
                            for number in range(1, 21))
            body += "</div>"
        else:
            label = "Dein nächster Schritt"
            body = ("<h1>Weiter hören.<br>Sicherer antworten.</h1>"
                    "<p>Mehr Hörübungen, Transkripte und Erklärungen im Buch.</p>")
        counter = ""
        if event["kind"] == "silence":
            counter = f'<span class="countdown" id="count-{index}">{round(event["duration"])} s</span>'
            pauses.append({"index": index, "start": event["start"], "duration": event["duration"]})
        status = f'<div class="phase"><span class="phase-label">{html.escape(phase)}</span>{counter}</div>'
        if counter:
            status += f'<div class="progress"><div class="progress-fill" id="fill-{index}"></div></div>'
        eyebrow = html.escape(label) + (f" · Teil {part}" if part and label != f"Teil {part}" else "")
        scenes.append(f'<section id="scene-{index}" class="clip scene {" ".join(classes)}" '
                      f'data-start="{event["start"]}" data-duration="{event["duration"]}" '
                      f'data-track-index="0"><div class="eyebrow">{eyebrow}</div>{body}{status}</section>')
    layouts = []
    for layout, width, height in (("landscape", 1920, 1080), ("portrait", 1080, 1920)):
        target, assets = build / layout, build / layout / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        sources = {
            "gsap.min.js": ROOT / "node_modules" / "gsap" / "dist" / "gsap.min.js",
            "arial.ttf": Path(r"C:\Windows\Fonts\arial.ttf"),
            "arialbd.ttf": Path(r"C:\Windows\Fonts\arialbd.ttf"),
            "logo.png": ROOT.parent / "pilot_3d" / "assets" / "deutschkompass-logo.png",
            "book.jpg": ROOT / "episodes" / content["episode"]["promotion"]["cover_source"],
            "dialogue.wav": build / "dialogue.wav",
        }
        for name, source in sources.items():
            shutil.copyfile(source, assets / name)
        replacements = {
            "{{LAYOUT}}": layout, "{{WIDTH}}": str(width), "{{HEIGHT}}": str(height),
            "{{DURATION}}": str(timeline["duration"]), "{{SCENES}}": "\n".join(scenes),
            "{{PAUSES}}": json.dumps(pauses), "{{TITLE_WORDS}}": json.dumps(title_words, ensure_ascii=False),
            "{{INSTRUCTION_WORDS}}": json.dumps(instruction_words, ensure_ascii=False),
            "{{EXTRA_STYLES}}": STYLES, "{{SCOPE_LABEL}}": "ÖIF B1 Hören · 20 Aufgaben",
            "{{FOOTER_NOTE}}": "", "{{AMAZON}}": html.escape(content["episode"]["promotion"][
                "youtube_label" if layout == "landscape" else "social_label"]),
        }
        document = template
        for key, value in replacements.items():
            document = document.replace(key, value)
        if "{{" in document:
            raise ValueError("Unresolved full-composition placeholder.")
        (target / "index.html").write_text(document, encoding="utf-8")
        atomic_json(target / "hyperframes.json", {"media": {"autoProxy": False}})
        atomic_json(target / "package.json", {"name": f"listening-full-{layout}", "private": True,
                    "scripts": {"check": "python -X utf8 ..\\..\\..\\hyperframes_local.py check --json",
                                "render": "python -X utf8 ..\\..\\..\\hyperframes_local.py render"}})
        atomic_json(target / "assets_manifest.json", {name: sha256_file(assets / name) for name in sources})
        layouts.append(str(target))
    atomic_json(build / "composition_receipt.json", {
        "template_sha256": sha256_file(ROOT / "composition" / "index.html"),
        "generator_sha256": sha256_file(Path(__file__)), "timeline_sha256": sha256_file(build / "timeline.json"),
        "title_mapping": title_words, "instruction_mapping": instruction_words,
        "scenes": scene_events, "layouts": layouts,
    })
    print(f"Composed full native layouts: {len(scene_events)} visual scenes.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    compose(parser.parse_args().build)
