"""Compose native Canadian TEF practice cards with measured narration highlights."""

import argparse
import html
import json
from pathlib import Path
import shutil
from urllib.parse import urlsplit

from prepare_tef import ROOT, atomic_json, read, sha256_file, verify_files

STYLES = """
body { background:#f7f4f0;color:#253342; }
header { top:48px;height:96px; }
.brand { width:330px; }
.series { color:#8d172c; }
.flag { background:url("assets/flag.png") center/contain no-repeat;border-radius:0; }
.clip.scene { left:72px;top:184px;width:1290px;height:796px;padding:34px;
  display:flex;flex-direction:column;background:#fffefd;border-color:#dbcdd0; }
.eyebrow { font-size:27px;color:#8d172c;margin-bottom:16px;flex-shrink:0; }
.main { flex:1;min-height:0;display:flex;flex-direction:column;justify-content:center;gap:22px; }
.main h1,.main h2,.main p { margin:0; }
.main h1 { font-size:64px;line-height:1.24; }
.main h2 { font-size:43px;line-height:1.25; }
.main p,.main .instruction { font-size:39px;line-height:1.5; }
.instruction-word { white-space:nowrap; }
.questions { display:grid;grid-template-columns:1fr;gap:22px; }
.question { min-width:0; }
.question h2 { font-size:40px;line-height:1.3;margin:0 0 24px; }
.option { font-size:35px;line-height:1.28;padding:15px 20px;margin-bottom:12px;gap:18px; }
.option > span:last-child { min-width:0;flex:1;overflow-wrap:break-word; }
.letter { color:#8d172c; }
.paired { grid-template-columns:1fr 1fr;gap:24px; }
.paired .question h2 { font-size:33px;min-height:0;margin-bottom:12px; }
.paired .option { font-size:31px;line-height:1.25;padding:9px 15px;margin-bottom:8px;gap:12px; }
.pictures { display:grid;grid-template-columns:1fr 1fr;gap:16px; }
.picture { position:relative;border:2px solid #b8c2ca;border-radius:16px;background:white;
  padding:12px;display:flex;align-items:center;gap:12px;min-width:0; }
.picture .letter { font-size:36px;align-self:flex-start; }
.picture img { height:190px;width:100%;min-width:0;object-fit:contain; }
.phase { flex-shrink:0;border-color:#cdbec1;margin-top:18px;padding-top:14px;min-height:58px;font-size:29px; }
.phase-label { color:#8d172c; }
.countdown { color:#8d172c;font-size:38px; }
.progress { flex-shrink:0;background:#eadfe1; }
.progress-fill { background:#a9253d; }
.note { font-size:29px !important;color:#536273; }
.solution-answer { padding:26px;border:2px solid #317354;border-radius:18px;background:#e8f4ec;
  color:#215640;font-size:43px !important; }
.correct-picture { height:340px;max-width:100%;object-fit:contain; }
.paired-solutions .solution-answer { font-size:32px !important;line-height:1.3;padding:18px; }
aside { right:72px;top:218px;width:412px;height:714px;border-color:#dbcdd0;background:#f1e6e7;padding:26px; }
.cover { height:330px;width:220px;object-fit:contain;margin-bottom:14px; }
aside h2 { font-size:32px;line-height:1.22;margin-bottom:14px; }
aside p { font-size:27px;margin-bottom:14px; }
.amazon { color:#8d172c; }
.amazon a { color:inherit; }
footer { color:#536273;font-size:22px; }
html[data-resolution="portrait"] header { top:118px;height:104px; }
html[data-resolution="portrait"] .series { font-size:28px;gap:14px; }
html[data-resolution="portrait"] .clip.scene { top:266px;height:1114px;padding:30px; }
html[data-resolution="portrait"] .main { gap:22px; }
html[data-resolution="portrait"] .main h1 { font-size:58px;line-height:1.3; }
html[data-resolution="portrait"] .main p,
html[data-resolution="portrait"] .main .instruction { font-size:41px;line-height:1.5; }
html[data-resolution="portrait"] .eyebrow { font-size:29px;margin-bottom:18px; }
html[data-resolution="portrait"] .question h2 { font-size:41px;margin-bottom:24px; }
html[data-resolution="portrait"] .option { font-size:39px;padding:21px 20px;line-height:1.28;margin-bottom:16px; }
html[data-resolution="portrait"] .paired { grid-template-columns:1fr;gap:20px; }
html[data-resolution="portrait"] .paired .question h2 { font-size:33px;min-height:0;margin-bottom:12px; }
html[data-resolution="portrait"] .paired .option { font-size:32px;padding:10px 16px;
  margin-bottom:9px;line-height:1.25; }
html[data-resolution="portrait"] .picture img { height:300px; }
html[data-resolution="portrait"] .picture .letter { font-size:40px; }
html[data-resolution="portrait"] .phase { font-size:30px;margin-top:18px;padding-top:14px;min-height:58px; }
html[data-resolution="portrait"] aside { top:1420px;height:294px;padding:18px 26px; }
html[data-resolution="portrait"] .cover { height:254px;width:164px;margin-right:28px; }
html[data-resolution="portrait"] aside h2 { font-size:31px;margin:12px 0; }
html[data-resolution="portrait"] aside p { font-size:29px;line-height:1.3;margin-bottom:12px; }
html[data-resolution="portrait"] footer { bottom:126px;font-size:23px; }
html[data-resolution="portrait"] .correct-picture { height:430px; }
"""


def word_mapping(turn):
    from align_words import validate_words
    words = validate_words(turn["words"], turn["text"], turn["wav_duration"])
    return [{"index": n, "label": w["word"], "start": turn["start"] + w["start"],
             "end": turn["start"] + w["end"], "selector": f"#word-{turn['id']}-{n}"}
            for n, w in enumerate(words)]


def picture_filename(item, choice):
    return item.get("picture_assets", {}).get(choice, f'{item["visual_set_id"]}-{choice}.svg')


def load_visual_assets(build, content):
    path = build / "visual_assets.json"
    if not path.exists():
        return {}
    visual = read(path)
    verify_files(visual["files"])
    url = urlsplit(visual["amazon_url"])
    if url.scheme != "https" or not url.netloc:
        raise ValueError("The book purchase link must be an absolute HTTPS URL.")
    for item in content["cards"].values():
        selected = visual["picture_sets"].get(item["visual_set_id"])
        if selected:
            item["picture_assets"] = {c: Path(selected["panels"][c]).name for c in "ABCD"}
            item["picture_labels_embedded"] = selected["labels_embedded"]
    return visual


def question_markup(item):
    esc = html.escape
    heading = f'<h2>Question {item["number"]} · {esc(item["question"])}</h2>'
    if item["visual_set_id"]:
        body = '<div class="pictures">' + "".join(
            '<div class="picture">' +
            ("" if item.get("picture_labels_embedded") else f'<span class="letter">{c}</span>') +
            f'<img src="assets/{esc(picture_filename(item, c))}" alt="Dessin {c}"></div>'
            for c in "ABCD") + "</div>"
    else:
        body = "".join(f'<div class="option"><span class="letter">{c}</span>'
                       f'<span>{esc(item["options"][c])}</span></div>' for c in "ABCD")
    return f'<div class="question" data-question="{item["number"]}">{heading}{body}</div>'


def scene_body(event, content, mappings):
    esc = html.escape
    episode, cards = content["episode"], content["cards"]
    if event.get("visible"):
        words = " ".join(f'<span class="instruction-word" id="word-{event["id"]}-{w["index"]}">'
                         f'{esc(w["label"])}</span>' for w in mappings[event["id"]])
        if event["id"] == "title":
            note = ("16 questions · Correction après chaque exercice"
                    if episode.get("answer_reveal") == "after_exercise"
                    else "Entraînement réduit · 16 questions · 8 types")
            return f'<h1>{words}</h1><p class="note">{note}</p>'
        return f'<p class="instruction">{words}</p>'
    if event["id"].startswith("solution_") or event.get("kind") == "sfx":
        numbers = event.get("reveal_numbers", [event["number"]])
        if len(numbers) == 2:
            return '<div class="questions paired paired-solutions">' + "".join(
                f'<div class="question"><h2 data-reveal-question="{n}">Question {n} · '
                f'{esc(cards[str(n)]["question"])}</h2><p class="solution-answer">'
                f'{cards[str(n)]["answer"]}. {esc(cards[str(n)]["options"][cards[str(n)]["answer"]])}'
                '</p></div>' for n in numbers) + "</div>"
        item = cards[str(event["number"])]
        answer = item["answer"]
        body = (f'<h2 data-reveal-question="{item["number"]}">Question {item["number"]} · Réponse {answer}</h2>'
                f'<p>{esc(item["question"])}</p>')
        if item["visual_set_id"]:
            return body + f'<img class="correct-picture" src="assets/{esc(picture_filename(item, answer))}" alt="Dessin {answer}">'
        return body + f'<p class="solution-answer">{answer}. {esc(item["options"][answer])}</p>'
    if event["id"] == "outro":
        return ('<h1>Continuez avec<br>French Compass</h1>'
                '<p>TEF Canada :<br>Compréhension orale</p>'
                '<p class="note">380 exercices · Audio, transcriptions et explications</p>')
    items = [cards[str(n)] for n in event["numbers"]]
    return '<div class="questions' + (' paired' if len(items) == 2 else '') + '">' + "".join(
        question_markup(item) for item in items) + "</div>"


def compose(build, layout_only=False):
    build = build.resolve()
    verify_files(read(build / "input_pin.json")["files"])
    content, timeline = read(build / "content.json"), read(build / "timeline.json")
    visual = load_visual_assets(build, content)
    if timeline["total_frames"] >= 21600:
        raise ValueError("The complete video including reveal chimes must be under 15 minutes.")
    if timeline.get("layout_only", False) != layout_only:
        raise ValueError("Layout-only fixtures and measured audio builds must remain separate.")
    mappings = {t["id"]: ([{"index": i, "label": token} for i, token in enumerate(t["text"].split())]
                          if layout_only else word_mapping(t))
                for t in timeline["turns"] if t["visible"]}
    template = (ROOT / "composition" / "index.html").read_text(encoding="utf-8")
    countdown = 'Math.ceil(pause.start + pause.duration - tl.time())'
    if countdown not in template:
        raise ValueError("The base countdown changed; verify its encoded frame boundaries.")
    template = template.replace(
        countdown, 'Math.ceil((Math.round((pause.start + pause.duration) * 24) - Math.round(tl.time() * 24)) / 24)')
    template = template.replace('lang="de"', 'lang="fr"')
    template = template.replace('aria-label="Österreich"', 'aria-label="Canada"')
    template = template.replace("Deutsch<br>Kompass", "French<br>Compass")
    template = template.replace("ÖIF B1 Hören – Übungsbuch mit Audio", html.escape(
        visual.get("book_image_alt", "Page de titre du livre TEF Canada : Compréhension orale")))
    template = template.replace("ÖIF B1 Hören", "TEF Canada · Écoute")
    template = template.replace("Mehr üben mit dem Buch", "Le livre French Compass")
    template = template.replace("Hörübungen, Transkripte<br>und Erklärungen", "380 exercices · Audio<br>Transcriptions et explications")
    template = template.replace('src="assets/book.jpg"', 'src="assets/book.png"')
    book = Path(content["groups"][0]["recordings"][0]["source_audio"]).parents[3]
    layouts = {}
    for layout, width, height in (("landscape", 1920, 1080), ("portrait", 1080, 1920)):
        target = build / layout
        assets = target / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        sources = {
            "gsap.min.js": ROOT / "node_modules" / "gsap" / "dist" / "gsap.min.js",
            "arial.ttf": Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            "arialbd.ttf": Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            "font-license.txt": Path("/usr/share/doc/fonts-dejavu-core/copyright"),
            "logo.png": ROOT.parent / "pilot_3d" / "assets" / "frenchcompass-logo.png",
            "logo-provenance.txt": ROOT.parent / "pilot_3d" / "assets" / "frenchcompass-logo.txt",
            "flag.png": ROOT.parent / "pilot_3d" / "assets" / "props" / "canada-flag.png",
            "flag-provenance.json": ROOT.parent / "pilot_3d" / "assets" / "props" / "canada.provenance.json",
            "book.png": Path(visual.get("book_image", build / "book_title_page.png")),
            "dialogue.wav": build / "dialogue.wav"}
        for item in content["cards"].values():
            if item["visual_set_id"]:
                for c in "ABCD":
                    name = picture_filename(item, c)
                    selected = visual.get("picture_sets", {}).get(item["visual_set_id"])
                    sources[name] = (Path(selected["panels"][c]) if selected
                                     else book / "images" / "picture_sets" / name)
        for name, source in sources.items():
            if not source.is_file():
                raise FileNotFoundError(f"Missing composition asset: {source}")
            shutil.copyfile(source, assets / name)
        scenes, pauses, highlights = [], [], []
        for index, event in enumerate(timeline["events"]):
            body = scene_body(event, content, mappings)
            family = event.get("family")
            group = next((g for g in content["groups"] if g["family"] == family), None)
            heading = group["heading"] if group else (
                "Corrections · Après l’entraînement" if event["id"].startswith("solution") else "Entraînement réduit · French Compass")
            if timeline.get("answer_reveal") == "after_exercise":
                if event["id"].startswith("solution_") or event["kind"] == "sfx":
                    heading = "Correction de l’exercice"
                elif not family:
                    heading = "Entraînement corrigé · French Compass"
            if event.get("numbers"):
                originals = " / ".join(str(content["cards"][str(n)]["source_number"]) for n in event["numbers"])
                heading += f" · Audio du livre : {originals}"
            counter = ""
            if event["kind"] == "silence" and event["id"] != "outro":
                counter = f'<span class="countdown" id="count-{index}">{event["duration"]:g} s</span>'
                pauses.append({"index": index, "start": event["start"], "duration": event["duration"]})
            phase = f'<div class="phase"><span class="phase-label">{esc(event.get("phase", "Consignes" if family else "French Compass"))}</span>{counter}</div>'
            if counter:
                phase += f'<div class="progress"><div class="progress-fill" id="fill-{index}"></div></div>'
            scenes.append(
                f'<section id="scene-{index}" class="clip scene" data-start="{event["start"]}" '
                f'data-duration="{event["duration"]}" data-track-index="0" data-event-id="{event["id"]}"'
                f'{" data-hold" if event["kind"] in ("recording", "sfx") or event["id"].startswith("solution") or event["id"] == "outro" else ""}>'
                f'<div class="eyebrow">{esc(heading)}</div><div class="main">{body}</div>{phase}</section>')
            if event.get("visible") and not layout_only:
                highlights.extend(mappings[event["id"]])
        replacements = {
            "{{LAYOUT}}": layout, "{{WIDTH}}": str(width), "{{HEIGHT}}": str(height),
            "{{DURATION}}": str(timeline["duration"]), "{{SCENES}}": "\n".join(scenes),
            "{{PAUSES}}": json.dumps(pauses), "{{TITLE_WORDS}}": "[]",
            "{{INSTRUCTION_WORDS}}": json.dumps(highlights, ensure_ascii=False),
            "{{EXTRA_STYLES}}": STYLES,
            "{{SCOPE_LABEL}}": "16 questions · 8 types · Une seule écoute",
            "{{FOOTER_NOTE}}": ("<span>MAQUETTE MUETTE · Sans synchronisation mesurée</span>" if layout_only
                                else "<span>Préparation indépendante · Ce n’est pas une épreuve officielle</span>"),
            "{{AMAZON}}": ('Disponible sur Amazon<br><a href="' + esc(visual["amazon_url"]) + '">'
                           + esc(visual["amazon_url"].removeprefix("https://")) + "</a>"
                           if visual else "Disponible sur Amazon · French Compass")}
        document = template
        for key, value in replacements.items():
            document = document.replace(key, value)
        if "{{" in document:
            raise ValueError("Unresolved TEF composition placeholder.")
        (target / "index.html").write_text(document, encoding="utf-8")
        atomic_json(target / "hyperframes.json", {"media": {"autoProxy": False}})
        atomic_json(target / "package.json", {"private": True, "scripts": {
            "check": "node ../../../node_modules/hyperframes/bin/hyperframes.mjs check . --json --no-browser-gpu --samples 12"}})
        atomic_json(target / "assets_manifest.json", {p.name: sha256_file(p) for p in assets.iterdir() if p.is_file()})
        layouts[layout] = {"html_sha256": sha256_file(target / "index.html"),
                           "sources": {name: {"path": str(path), "sha256": sha256_file(path)}
                                       for name, path in sources.items()}}
    atomic_json(build / "composition_receipt.json", {
        "generator_sha256": sha256_file(Path(__file__)),
        "template_sha256": sha256_file(ROOT / "composition" / "index.html"),
        "timeline_sha256": sha256_file(build / "timeline.json"), "layouts": layouts,
        "word_mappings": {} if layout_only else mappings, "layout_only": layout_only,
        "visual_assets_sha256": sha256_file(build / "visual_assets.json") if visual else None,
        "exam_transcripts_subtitled": False, "added_sfx": False})
    print("TEF native landscape and portrait compositions ready.", flush=True)


esc = html.escape

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--layout-only", action="store_true")
    args = parser.parse_args()
    compose(args.build, args.layout_only)
