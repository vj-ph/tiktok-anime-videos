"""Compose original B2 listening with approved readable interview pagination."""

import argparse
import copy
import html
import json
from pathlib import Path
import shutil

from compose_full import visual_events
from prepare_b2 import EPISODE, read
from prepare_sample import ROOT, atomic_json, sha256_file
from process_b2 import VISIBLE_INSTRUCTIONS

STYLES = """
    .clip.scene.statements { padding:30px 34px; display:flex; flex-direction:column; }
    .statements .eyebrow { margin-bottom:18px; }
    .statement-board { display:grid; gap:10px; margin-bottom:16px; }
    .statement-row { display:grid; grid-template-columns:max-content minmax(0,1fr); gap:12px;
      border:1px solid #b8cbc3; border-radius:14px; padding:8px 12px; align-items:start; }
    .statement-number { color:#376a5b; font-size:34px; font-weight:700; line-height:1.16;
      white-space:nowrap; }
    .statement-text { font-size:34px; line-height:1.16; }
    .dense .statement-board { grid-template-columns:repeat(2,minmax(0,1fr));
      grid-template-rows:repeat(5,auto); grid-auto-flow:column; gap:6px 20px; }
    .dense .statement-row { gap:8px; padding:5px; }
    .dense .statement-number, .dense .statement-text { font-size:28px; }
    .statements .phase { margin-top:auto; }
    .statements > * { flex-shrink:0; }
    .single .statement-text, .single .statement-number { font-size:52px; }
    .single .statement-row { padding:30px 24px; }
    .answer-board { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }
    .answer-cell { border:2px solid #44806d; border-radius:14px; padding:14px 20px;
      color:#215640; background:#e0f1e7; display:flex; gap:24px;
      align-items:center; font-size:42px; }
    .summary .answer-board { grid-template-columns:repeat(5,minmax(0,1fr)); gap:12px; }
    .summary .answer-cell { flex-direction:column; gap:4px; padding:12px; font-size:34px; }
    .clip.scene.summary { padding:30px 34px; }
    .reveal h1, .summary h1 { font-size:52px; }
    html[data-resolution="portrait"] .clip.scene.statements { padding:28px 30px; }
    html[data-resolution="portrait"] .statements .eyebrow { font-size:30px; margin-bottom:14px; }
    html[data-resolution="portrait"] .statement-board { gap:8px; }
    html[data-resolution="portrait"] .statement-row { padding:6px 12px; gap:12px; }
    html[data-resolution="portrait"] .statement-text,
    html[data-resolution="portrait"] .statement-number { font-size:42px; }
    html[data-resolution="portrait"] .statements .phase {
      font-size:30px; padding-top:14px; margin-top:auto; }
    html[data-resolution="portrait"] .single .statement-row { padding:28px 18px; }
    html[data-resolution="portrait"] .single .statement-text,
    html[data-resolution="portrait"] .single .statement-number { font-size:54px; }
    html[data-resolution="portrait"] .answer-cell { font-size:44px; padding:18px; }
    html[data-resolution="portrait"] .summary .answer-board {
      grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }
    html[data-resolution="portrait"] .summary .answer-cell { font-size:40px; padding:12px 6px; }
    html[data-resolution="portrait"] .reveal h1,
    html[data-resolution="portrait"] .summary h1 { font-size:56px; }
"""


def visual_plan(timeline, layout):
    scenes = visual_events(timeline["events"])
    if layout == "landscape":
        return scenes
    switch = next(e["start_frame"] for e in timeline["events"] if e["id"] == "interview_q51")
    result = []
    for original in scenes:
        event = copy.deepcopy(original)
        if event["card"] != "b2_p2_learning" or event["kind"] == "reveal":
            result.append(event)
            continue
        cut = None
        if event["kind"] == "silence":
            cut = (event["start_frame"] + event["end_frame"]) // 2
        elif event["start_frame"] < switch < event["end_frame"]:
            cut = switch
        if cut is not None:
            first, second = copy.deepcopy(event), copy.deepcopy(event)
            first.update(end_frame=cut, end=cut / 24,
                         duration=(cut - first["start_frame"]) / 24, page=1)
            second.update(start_frame=cut, start=cut / 24,
                          duration=(second["end_frame"] - cut) / 24, page=2)
            result.extend((first, second))
        else:
            event["page"] = 1 if event["end_frame"] <= switch else 2
            result.append(event)
    return result


def word_mapping(timeline, text, ident):
    turn = next(t for t in timeline["turns"] if t["id"] == ident)
    if [w["word"] for w in turn["words"]] != text.split():
        raise ValueError("B2 instruction display text differs from measured alignment.")
    return [{"index": i, "label": w["word"], "start": turn["start"] + w["start"],
             "end": turn["start"] + w["end"], "selector": f"#{ident}-word-{i}"}
            for i, w in enumerate(turn["words"])]


def answers(questions):
    return '<div class="answer-board">' + "".join(
        f'<div class="answer-cell" data-answer="{q["number"]}:{"richtig" if q["answer"] else "falsch"}">'
        f'<strong>{q["number"]}</strong><span class="answer-label">'
        f'{"Richtig" if q["answer"] else "Falsch"}</span></div>' for q in questions) + "</div>"


def scene_body(event, content, mappings):
    card, part = event["card"], event["part"]
    classes, label = [], "ÖIF B2 Hören"
    if card == "title":
        body = "<h1>ÖIF B2 Hören</h1>"
    elif card in VISIBLE_INSTRUCTIONS:
        label = "Antworten prüfen" if card == "checking_instruction" else f"Anleitung · Teil {part}"
        spans = [f'<span class="instruction-word" id="{card}-word-{w["index"]}">'
                 f'{html.escape(w["label"])}</span>' for w in mappings[card]]
        body = f'<h2>{label}</h2><p class="instruction">{" ".join(spans)}</p>'
    elif card in content["cards"]:
        questions = content["cards"][card]["questions"]
        label = content["cards"][card]["label"]
        if event["kind"] == "reveal":
            classes.append("reveal")
            body = "<h1>Deine Lösungen</h1>" + answers(questions)
        else:
            classes.append("statements")
            if event.get("page"):
                page = event["page"]
                questions = questions[(page - 1) * 5:page * 5]
                label += f" · {questions[0]['number']}–{questions[-1]['number']}"
            elif len(questions) == 10:
                classes.append("dense")
            if len(questions) == 1:
                classes.append("single")
            body = '<div class="statement-board">' + "".join(
                f'<div class="statement-row"><strong class="statement-number">{q["number"]}.</strong>'
                f'<span class="statement-text">{html.escape(q["question"])}</span></div>'
                for q in questions) + "</div>"
    elif card == "end":
        body = "<h1>Hören beendet</h1>" if part == 3 else f"<h1>Teil {part} beendet</h1>"
    elif card == "summary":
        classes.append("summary")
        questions = [q for s in content["episode"]["sections"] for g in s["groups"] for q in g["questions"]]
        body = "<h1>Lösungen im Überblick</h1>" + answers(questions)
    else:
        label = "Dein nächster Schritt"
        body = ("<h1>Weiter hören.<br>Sicherer antworten.</h1>"
                "<p>Mehr Hörübungen, Transkripte und Erklärungen im Buch.</p>")
    return body, label, classes


def compose(build):
    timeline, content = read(build / "timeline.json"), read(build / "sample_content.json")
    texts = {f"instruction_{s['part']}": s["instruction"] for s in content["episode"]["sections"]}
    texts["checking_instruction"] = content["episode"]["sections"][1]["checking_instruction"]
    mappings = {ident: word_mapping(timeline, text, ident) for ident, text in texts.items()}
    all_words = [word for words in mappings.values() for word in words]
    template = (ROOT / "composition" / "index.html").read_text(encoding="utf-8")
    receipt = dict(template_sha256=sha256_file(ROOT / "composition" / "index.html"),
                   generator_sha256=sha256_file(Path(__file__)),
                   timeline_sha256=sha256_file(build / "timeline.json"),
                   instruction_mapping=all_words, layouts=["landscape", "portrait"], scenes={})
    for layout, width, height in (("landscape", 1920, 1080), ("portrait", 1080, 1920)):
        scene_events, scenes, pauses = visual_plan(timeline, layout), [], []
        receipt["scenes"][layout] = scene_events
        for index, event in enumerate(scene_events):
            body, label, classes = scene_body(event, content, mappings)
            counter = ""
            if event["kind"] == "silence":
                counter = f'<span class="countdown" id="count-{index}">{round(event["duration"])} s</span>'
                pauses.append(dict(index=index, start=event["start"], duration=event["duration"]))
            status = (f'<div class="phase"><span class="phase-label">{html.escape(event["phase"])}</span>'
                      f"{counter}</div>")
            if counter:
                status += f'<div class="progress"><div class="progress-fill" id="fill-{index}"></div></div>'
            scenes.append(
                f'<section id="scene-{index}" class="clip scene {" ".join(classes)}" '
                f'data-start="{event["start"]}" data-duration="{event["duration"]}" '
                f'data-track-index="0"><div class="eyebrow">{html.escape(label)}</div>{body}{status}</section>')
        target, assets = build / layout, build / layout / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        sources = {
            "gsap.min.js": ROOT / "node_modules" / "gsap" / "dist" / "gsap.min.js",
            "arial.ttf": Path(r"C:\Windows\Fonts\arial.ttf"),
            "arialbd.ttf": Path(r"C:\Windows\Fonts\arialbd.ttf"),
            "logo.png": ROOT.parent / "pilot_3d" / "assets" / "deutschkompass-logo.png",
            "book.jpg": EPISODE.parent / content["episode"]["promotion"]["cover_source"],
            "dialogue.wav": build / "dialogue.wav",
        }
        for name, source in sources.items():
            shutil.copyfile(source, assets / name)
        document = template.replace("ÖIF B1", "ÖIF B2")
        replacements = {
            "{{LAYOUT}}": layout, "{{WIDTH}}": str(width), "{{HEIGHT}}": str(height),
            "{{DURATION}}": str(timeline["duration"]), "{{SCENES}}": "\n".join(scenes),
            "{{PAUSES}}": json.dumps(pauses), "{{TITLE_WORDS}}": "[]",
            "{{INSTRUCTION_WORDS}}": json.dumps(all_words, ensure_ascii=False),
            "{{EXTRA_STYLES}}": STYLES, "{{SCOPE_LABEL}}": "ÖIF B2 Hören · Aufgaben 41–60",
            "{{FOOTER_NOTE}}": "", "{{AMAZON}}": html.escape(content["episode"]["promotion"][
                "youtube_label" if layout == "landscape" else "social_label"]),
        }
        for key, value in replacements.items():
            document = document.replace(key, value)
        document = document.replace("pause.start + pause.duration - tl.time()",
                                    "pause.start + pause.duration - tl.time() - 1e-7")
        if "{{" in document:
            raise ValueError("Unresolved B2 composition placeholder.")
        (target / "index.html").write_text(document, encoding="utf-8")
        atomic_json(target / "hyperframes.json", {"media": {"autoProxy": False}})
        atomic_json(target / "assets_manifest.json", {name: sha256_file(assets / name) for name in sources})
    atomic_json(build / "composition_receipt.json", receipt)
    print("B2 native composition ready, including approved portrait interview pages.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    compose(parser.parse_args().build.resolve())
