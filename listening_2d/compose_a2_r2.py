"""Compose native A2 layouts with readable shared-message and overview cards."""

import argparse
import html
import json
from pathlib import Path
import shutil

from compose_full import visual_events
from prepare_a2_r2 import EPISODE, read
from prepare_sample import ROOT, atomic_json, sha256_file

STYLES = """
    .answer-grid { display:grid; grid-template-columns:repeat(5,1fr); gap:18px; }
    .answer-cell { border:2px solid #b8cbc3; border-radius:14px; padding:18px;
      font-size:32px; background:#e0f1e7; color:#215640; }
    .answer-cell strong { margin-right:18px; }
    .clip.scene.compact, .clip.scene.overview { padding:30px 36px; }
    .compact .eyebrow, .overview .eyebrow { margin-bottom:12px; }
    .compact-row { margin-bottom:8px; }
    .compact-row h2 { font-size:28px; line-height:1.16; margin:0 0 4px; }
    .compact-options { display:flex; flex-wrap:wrap; gap:6px 12px; }
    .compact-option { display:inline-flex; gap:6px; align-items:baseline; font-size:26px;
      line-height:1.2; border:2px solid transparent; border-radius:9px; padding:2px 6px; }
    .compact-option strong { color:#376a5b; }
    .compact-option.correct { border-color:#44806d; background:#e0f1e7; color:#215640; }
    .compact .phase, .overview .phase { font-size:26px; margin-top:12px; padding-top:12px; }
    .overview .compact-row { margin-bottom:18px; }
    .overview .compact-row h2 { font-size:32px; margin-bottom:8px; }
    .overview .compact-option { font-size:28px; }
    .binary-options { display:flex; gap:22px; }
    .binary-options .option { flex:1; justify-content:center; }
    .scope-notice { position:absolute; top:151px; left:80px; right:80px;
      font-size:28px; font-weight:700; color:#875a3b; text-align:center; }
    html[data-resolution="portrait"] .clip.scene.compact,
    html[data-resolution="portrait"] .clip.scene.overview { padding:32px 34px; }
    html[data-resolution="portrait"] .compact .eyebrow,
    html[data-resolution="portrait"] .overview .eyebrow { font-size:30px; margin-bottom:12px; }
    html[data-resolution="portrait"] .compact-row { margin-bottom:10px; }
    html[data-resolution="portrait"] .compact-row h2 { font-size:42px; margin-bottom:4px;
      line-height:1.16; }
    html[data-resolution="portrait"] .compact-option { font-size:40px; padding:2px 0; gap:5px; }
    html[data-resolution="portrait"] .compact .compact-options { column-gap:6px; }
    html[data-resolution="portrait"] .compact .compact-option { gap:8px; border-width:1px; }
    html[data-resolution="portrait"] .compact .compact-row { margin-bottom:4px; }
    html[data-resolution="portrait"] .compact .phase,
    html[data-resolution="portrait"] .overview .phase { font-size:30px; margin-top:12px; padding-top:12px; }
    html[data-resolution="portrait"] .overview .compact-row { margin-bottom:22px; }
    html[data-resolution="portrait"] .mc h2 { font-size:56px; }
    html[data-resolution="portrait"] .mc .option { font-size:48px; padding:22px 24px; }
    html[data-resolution="portrait"] .binary h2 { font-size:56px; margin-bottom:40px; }
    html[data-resolution="portrait"] .binary .option { font-size:48px; }
    html[data-resolution="portrait"] .answer-grid { grid-template-columns:repeat(3,1fr); gap:18px; }
    html[data-resolution="portrait"] .answer-cell { padding:20px 14px; font-size:38px; }
    html[data-resolution="portrait"] .scope-notice { top:264px; font-size:27px; }
"""


def compact_question(question, reveal):
    body = (f'<div class="compact-row"><h2>{question["number"]}. '
            f'{html.escape(question["question"])}</h2><div class="compact-options">')
    for key, label in question["options"].items():
        correct = reveal and key == question["answer"]
        attribute = f' data-answer="{key}"' if correct else ""
        classes = "compact-option correct" if correct else "compact-option"
        prefix = "" if key in ("richtig", "falsch") else f"<strong>{key})</strong>"
        body += f'<div class="{classes}"{attribute}>{prefix}{html.escape(label)}</div>'
    return body + "</div></div>"


def card_body(card, reveal):
    if card["type"] in ("compact", "overview"):
        return "".join(compact_question(q, reveal) for q in card["questions"])
    question = card["questions"][0]
    body = f'<h2>{question["number"]}. {html.escape(question["question"])}</h2>'
    if card["type"] == "binary":
        body += '<div class="binary-options">'
    for key, label in question["options"].items():
        correct = reveal and key == question["answer"]
        attribute = f' data-answer="{key}"' if correct else ""
        classes = "option correct" if correct else "option"
        prefix = "" if card["type"] == "binary" else f'<span class="letter">{key}</span>'
        body += f'<div class="{classes}"{attribute}>{prefix}{html.escape(label)}</div>'
    if card["type"] == "binary":
        body += "</div>"
    return body


def word_mapping(timeline, text, ident, selector):
    turn = next(t for t in timeline["turns"] if t["id"] == ident)
    if [w["word"] for w in turn["words"]] != text.split():
        raise ValueError("Instruction display text differs from aligned speech.")
    return [{"index": i, "label": w["word"], "start": turn["start"] + w["start"],
             "end": turn["start"] + w["end"], "selector": selector.format(i=i)}
            for i, w in enumerate(turn["words"])]


def compose(build):
    build = build.resolve()
    timeline, content = read(build / "timeline.json"), read(build / "sample_content.json")
    episode = content["episode"]
    short = timeline["scope"] == "short"
    words, by_part = [], {}
    if not short:
        for section in episode["sections"]:
            part = section["part"]
            by_part[part] = word_mapping(
                timeline, section["instruction"], f"instruction_{part}",
                f"#instruction-{part}-word-{{i}}")
            words.extend(by_part[part])
    scenes, pauses = [], []
    scene_events = visual_events(timeline["events"])
    for index, event in enumerate(scene_events):
        card, part, phase = event["card"], event["part"], event["phase"]
        classes, label = [], "ÖIF A2 Hören"
        if card in ("title", "short_title"):
            body = ('<h1>ÖIF A2 Hören</h1>' if not short else
                    f'<h1>ÖIF A2 Hören<br>Teil {part}</h1><p>Verkürzte Übung</p>')
        elif card.startswith("instruction_"):
            label = f"Anleitung · Teil {part}"
            spans = [f'<span class="instruction-word" id="instruction-{part}-word-{w["index"]}">'
                     f'{html.escape(w["label"])}</span>' for w in by_part[part]]
            body = f'<h2>Hören · Teil {part}</h2><p class="instruction">{" ".join(spans)}</p>'
        elif card in content["cards"]:
            question_card = content["cards"][card]
            label = question_card["label"]
            classes.append(question_card["type"])
            body = card_body(question_card, event["kind"] == "reveal")
        elif card == "end":
            label, body = (("ÖIF A2 Hören", "<h1>Hören beendet</h1>") if part == 4
                           else (f"Teil {part}", f"<h1>Teil {part} beendet</h1>"))
        elif card == "summary":
            label, body = "Deine Antworten", '<h1>Lösungen im Überblick</h1><div class="answer-grid">'
            for section in episode["sections"]:
                for group in section["groups"]:
                    for q in group["questions"]:
                        body += (f'<div class="answer-cell"><strong>{q["number"]}</strong>'
                                 f'{html.escape(q["answer"])}</div>')
            body += "</div>"
        else:
            label = "Dein nächster Schritt"
            body = ('<h1>Weiter hören.<br>Sicherer antworten.</h1>'
                    '<p>Mehr Hörübungen, Transkripte und Erklärungen im Buch.</p>')
        counter = ""
        if event["kind"] == "silence":
            counter = f'<span class="countdown" id="count-{index}">{round(event["duration"])} s</span>'
            pauses.append({"index": index, "start": event["start"], "duration": event["duration"]})
        status = f'<div class="phase"><span class="phase-label">{html.escape(phase)}</span>{counter}</div>'
        if counter:
            status += f'<div class="progress"><div class="progress-fill" id="fill-{index}"></div></div>'
        scenes.append(
            f'<section id="scene-{index}" class="clip scene {" ".join(classes)}" '
            f'data-start="{event["start"]}" data-duration="{event["duration"]}" '
            f'data-track-index="0"><div class="eyebrow">{html.escape(label)}</div>{body}{status}</section>')
    template = (ROOT / "composition" / "index.html").read_text(encoding="utf-8")
    layouts = ["portrait"] if short else ["landscape", "portrait"]
    for layout in layouts:
        width, height = (1920, 1080) if layout == "landscape" else (1080, 1920)
        target, assets = build / layout, build / layout / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        sources = {
            "gsap.min.js": ROOT / "node_modules" / "gsap" / "dist" / "gsap.min.js",
            "arial.ttf": Path(r"C:\Windows\Fonts\arial.ttf"),
            "arialbd.ttf": Path(r"C:\Windows\Fonts\arialbd.ttf"),
            "logo.png": ROOT.parent / "pilot_3d" / "assets" / "deutschkompass-logo.png",
            "book.jpg": EPISODE.parent / episode["promotion"]["cover_source"],
            "dialogue.wav": build / "dialogue.wav",
        }
        for name, source in sources.items():
            shutil.copyfile(source, assets / name)
        footer = "ÖIF A2 Hören · 15 Aufgaben"
        notice = ""
        if short:
            selected = timeline["selected"]
            all_count = len([q for g in episode["sections"][timeline["part"] - 1]["groups"]
                             for q in g["questions"]])
            footer = (f'Teil {timeline["part"]} · Aufgaben {selected[0]}–{selected[-1]}'
                      f' · {len(selected)} von {all_count}')
            notice = ("Verkürzte Übung · Ausgewählte Aufgaben" if len(selected) < all_count
                      else "Verkürzte Übung · Ohne Anleitung")
        replacements = {
            "{{LAYOUT}}": layout, "{{WIDTH}}": str(width), "{{HEIGHT}}": str(height),
            "{{DURATION}}": str(timeline["duration"]), "{{SCENES}}": "\n".join(scenes),
            "{{PAUSES}}": json.dumps(pauses), "{{TITLE_WORDS}}": "[]",
            "{{INSTRUCTION_WORDS}}": json.dumps(words, ensure_ascii=False),
            "{{EXTRA_STYLES}}": STYLES, "{{SCOPE_LABEL}}": html.escape(footer),
            "{{FOOTER_NOTE}}": "", "{{AMAZON}}": html.escape(episode["promotion"][
                "youtube_label" if layout == "landscape" else "social_label"]),
        }
        document = template.replace("ÖIF B1", "ÖIF A2")
        for key, value in replacements.items():
            document = document.replace(key, value)
        if notice:
            document = document.replace("    <aside>", f'    <div class="scope-notice">{notice}</div>\n    <aside>')
        if "{{" in document:
            raise ValueError("Unresolved A2 composition placeholder.")
        (target / "index.html").write_text(document, encoding="utf-8")
        atomic_json(target / "hyperframes.json", {"media": {"autoProxy": False}})
        atomic_json(target / "assets_manifest.json", {name: sha256_file(assets / name) for name in sources})
    atomic_json(build / "composition_receipt.json", {
        "template_sha256": sha256_file(ROOT / "composition" / "index.html"),
        "generator_sha256": sha256_file(Path(__file__)),
        "timeline_sha256": sha256_file(build / "timeline.json"),
        "instruction_mapping": words, "scenes": scene_events, "layouts": layouts,
    })
    print(f"A2 composition: {len(scene_events)} scenes in {layouts}.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    compose(parser.parse_args().build)
