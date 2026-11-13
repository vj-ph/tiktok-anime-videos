"""Compose native portrait B2 shorts with inline answers and explicit subset scope."""

import argparse
import html
import json
from pathlib import Path
import shutil

from compose_b2_r3 import STYLES, scene_body
from compose_full import visual_events
from prepare_b2 import EPISODE, read
from prepare_b2_reduced import SELECTIONS, TOTALS
from prepare_sample import ROOT, atomic_json, sha256_file

SHORT_STYLES = """
    html[data-resolution="portrait"] .scene.statements .statement-board { gap:18px; }
    html[data-resolution="portrait"] .scene.statements .statement-row { padding:20px 18px; gap:16px; }
    html[data-resolution="portrait"] .scene.statements .statement-text,
    html[data-resolution="portrait"] .scene.statements .statement-number,
    html[data-resolution="portrait"] .scene.statements .statement-content {
      font-size:52px; line-height:1.18; }
    html[data-resolution="portrait"] .scene.statements .inline-answer {
      font-size:44px; line-height:1.18; }
    html[data-resolution="portrait"] footer {
      top:1720px; bottom:auto; font-size:28px; line-height:1.3; }
"""


def document_for(clip):
    timeline, content = read(clip / "timeline.json"), read(clip / "sample_content.json")
    part = timeline["part"]
    scenes, pauses = [], []
    events = visual_events(timeline["events"])
    for index, event in enumerate(events):
        body, label, classes = scene_body(event, content, {})
        if event["card"] == "title":
            body, label = f"<h1>ÖIF B2 Hören<br>Teil {part}</h1>", "Verkürzte Übung"
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
    template = (ROOT / "composition" / "index.html").read_text(encoding="utf-8").replace("ÖIF B1", "ÖIF B2")
    numbers = " / ".join(map(str, SELECTIONS[part]))
    replacements = {
        "{{LAYOUT}}": "portrait", "{{WIDTH}}": "1080", "{{HEIGHT}}": "1920",
        "{{DURATION}}": str(timeline["duration"]), "{{SCENES}}": "\n".join(scenes),
        "{{PAUSES}}": json.dumps(pauses), "{{TITLE_WORDS}}": "[]", "{{INSTRUCTION_WORDS}}": "[]",
        "{{EXTRA_STYLES}}": STYLES + SHORT_STYLES,
        "{{SCOPE_LABEL}}": f"Teil {part} · Aufgaben {numbers} · {len(SELECTIONS[part])} von {TOTALS[part]}",
        "{{FOOTER_NOTE}}": '<span class="reduced-notice">Verkürzte Übung · Ausgewählte Aufgaben</span>',
        "{{AMAZON}}": html.escape(content["episode"]["promotion"]["social_label"]),
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    template = template.replace("pause.start + pause.duration - tl.time()",
                                "pause.start + pause.duration - tl.time() - 1e-7")
    assert "{{" not in template
    return template, events


def compose(build):
    for part in SELECTIONS:
        clip = build / f"teil_{part}"
        content = read(clip / "sample_content.json")
        target, assets = clip / "portrait", clip / "portrait" / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        sources = {
            "gsap.min.js": ROOT / "node_modules" / "gsap" / "dist" / "gsap.min.js",
            "arial.ttf": Path(r"C:\Windows\Fonts\arial.ttf"),
            "arialbd.ttf": Path(r"C:\Windows\Fonts\arialbd.ttf"),
            "logo.png": ROOT.parent / "pilot_3d" / "assets" / "deutschkompass-logo.png",
            "book.jpg": EPISODE.parent / content["episode"]["promotion"]["cover_source"],
            "dialogue.wav": clip / "dialogue.wav",
        }
        for name, source in sources.items():
            shutil.copyfile(source, assets / name)
        document, scenes = document_for(clip)
        (target / "index.html").write_text(document, encoding="utf-8")
        atomic_json(target / "hyperframes.json", {"media": {"autoProxy": False}})
        atomic_json(target / "assets_manifest.json", {n: sha256_file(assets / n) for n in sources})
        atomic_json(clip / "composition_receipt.json", {
            "generator_sha256": sha256_file(Path(__file__)),
            "template_sha256": sha256_file(ROOT / "composition" / "index.html"),
            "timeline_sha256": sha256_file(clip / "timeline.json"),
            "selected_numbers": SELECTIONS[part], "scenes": scenes,
        })
        print(f"Composed B2 reduced Teil {part}: {len(scenes)} native portrait scenes.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    compose(parser.parse_args().build.resolve())
