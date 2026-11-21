"""Compile every dialogue turn of a book mock into a separate long preview."""

import copy
import json
from pathlib import Path
import re

from episode_config import read_episode, validate_template
from prepare_audio import atomic_json, sha256_file


def extract_dialogues(text, heading):
    chapter = text.split("## " + heading + "\n", 1)[1]
    chapter = chapter.split("### Why this works:", 1)[0]
    result = {}
    for section, stop in (("A", "### Section B model dialogue"),
                          ("B", None)):
        content = chapter.split(f"### Section {section} model dialogue\n", 1)[1]
        if stop:
            content = content.split(stop, 1)[0]
        result[section] = re.findall(r"^\*\*(Candidate|Partner|Friend):\*\* (.+)$", content, re.M)
        if not result[section] or result[section][0][0] != "Candidate":
            raise ValueError(f"Missing complete Section {section} model.")
    if (len(result["A"]), len(result["B"])) != (20, 28):
        raise ValueError("Mock Test 1 must retain all 20 A and 28 B dialogue turns.")
    return result


def compile_episode(path):
    path = Path(path).resolve(strict=True)
    config = json.loads(path.read_text(encoding="utf-8"))
    if (config.get("template") != "tef_speaking_full_preview"
            or config.get("duration_limit_seconds") != 1800
            or not config.get("duration_exception")):
        raise ValueError("Full TEF preview requires its explicit long-form duration contract.")
    base_path = (path.parent / config["base_episode"]).resolve(strict=True)
    episode = read_episode(base_path)
    source_book = (base_path.parent / episode["source"]["book"]).resolve(strict=True)
    dialogues = extract_dialogues(source_book.read_text(encoding="utf-8"), config["source_heading"])
    episode = copy.deepcopy(episode)
    episode.update(template=config["template"], id=config["id"], title=config["title"],
                   book_cover=str(Path(config["book_cover"]).resolve(strict=True)),
                   label="TEF Canada · Simulation guidée · Dialogues complets",
                   disclaimer="Entraînement indépendant ; durée des modèles adaptée, pas un chronométrage officiel.",
                   cta=["Livre disponible sur Amazon", config["visible_url"], "Expression orale et écrite"])
    episode["header"]["topic"] = "Sections A et B · Test blanc 1"
    episode["promotion"] = {key: config[key] for key in ("promotion", "visible_url", "purchase_url")}
    episode["promotion"]["description_hint"] = "Lien dans la description"
    episode["source"].update(book=str(source_book), exercise=config["source_heading"],
                             authoring_config=str(path), authoring_config_sha256=sha256_file(path),
                             book_sha256=sha256_file(source_book),
                             duration_limit_seconds=1800, duration_exception=config["duration_exception"],
                             purchase_url=config["purchase_url"],
                             scope="Complete Mock Test 1 model dialogues, in a guided landscape preview.",
                             adaptation="All 48 model turns retained verbatim; add spoken opening, "
                                        "two-section overview, practice instructions, eight-second "
                                        "notice holds with silent countdown/progress and book CTA. "
                                        "No claim of official preparation or exact 5/10-minute section timing.")
    for section, value in episode["preview_notices"].items():
        episode["preview_notices"][section] = str((base_path.parent / value).resolve(strict=True))
    episode["publication"] = {
        "intro": "Simulation guidée du test blanc 1 : bibliothèque et atelier de poterie. "
                 "Les deux dialogues modèles du livre sont présentés intégralement.",
        "disclosure": "Entraînement indépendant, ni sujet officiel ni épreuve administrée. "
                      "La durée des dialogues modèles ne reproduit pas le chronométrage officiel.",
        "hashtags": ["#TEFCanada", "#ExpressionOrale", "#FrenchCompass"],
    }

    def turn(identifier, text, *, speaker="examiner", section=None, kind="model", pause=.8):
        value = {"id": identifier, "speaker": speaker,
                 "name": "Candidate" if speaker == "candidate_a" else
                         "Ami" if section == "B" and kind == "model" else
                         "Agent d'accueil" if kind == "model" else "Examinateur",
                 "text": text, "camera": speaker if kind == "model" else "wide",
                 "action": "ask" if speaker == "candidate_a" and section == "A" else
                           "propose" if speaker == "candidate_a" else
                           "consider" if section == "B" and kind == "model" else
                           "answer" if kind == "model" else "explain",
                 "look_at": "examiner" if speaker == "candidate_a" else "candidate_a",
                 "pause_after": pause, "phase": "dialogue", "kind": kind}
        if section:
            value["section"] = section
        return value

    turns = [turn("opening", episode["title"], kind="opening", pause=1),
             turn("setup", "Bienvenue ! L'épreuve d'expression orale comporte deux sections. "
                  "Dans la section A, vous demandez des renseignements. "
                  "Dans la section B, vous présentez une activité et vous essayez de convaincre un ami. "
                  "Voici les deux dialogues modèles complets. "
                  "Vous pouvez faire une pause pour préparer vos réponses. "
                  "La durée de cette démonstration est adaptée aux échanges du livre. "
                  "Commençons par la section A.",
                  kind="setup", pause=1)]
    instructions = {
        "A": "Section A. Vous avez vu cette annonce pour une carte de bibliothèque. "
             "Vous téléphonez pour obtenir des renseignements et préparer votre inscription. "
             "Je joue le rôle de l'agent d'accueil.",
        "B": "Passons à la section B. Vous avez découvert cet atelier de poterie pour débutants. "
             "Présentez cette activité à votre ami et essayez de le convaincre d'y participer. "
             "Répondez à ses objections. Je joue votre ami.",
    }
    coverage = {}
    for section in ("A", "B"):
        turns.append(turn(section + "_notice", instructions[section], section=section,
                          kind="notice", pause=8))
        for index, (role, text) in enumerate(dialogues[section], 1):
            identifier = f"{section}_{index:02d}"
            turns.append(turn(identifier, text, section=section,
                              speaker="candidate_a" if role == "Candidate" else "examiner"))
            coverage[identifier] = {"section": section, "source_role": role, "text": text}
    turns.append(turn("closing", "À vous de parler ! Retrouvez davantage de tâches et de dialogues modèles "
                      "dans notre livre TEF Canada, expression orale et écrite. "
                      "Le livre est disponible sur Amazon. Le lien est affiché à l'écran.",
                      kind="cta", pause=1))
    episode["turns"] = turns
    episode["source"]["coverage"] = coverage
    validate_template(episode, check_assets=True)
    return episode


def build_full(path, build, jobs=2, until="export", speech_cache_from=None):
    from build_paths import build_directory
    from tef_speaking_preview import build_preview

    episode = compile_episode(path)
    build = build_directory(build)
    compiled = build.with_name(build.name + "_episode.json")
    if compiled.exists():
        if json.loads(compiled.read_text(encoding="utf-8")) != episode:
            raise ValueError("Full preview inputs changed; use a fresh build directory.")
    else:
        compiled.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(compiled, episode)
    return build_preview(compiled, build, jobs=jobs, until=until, speech_cache_from=speech_cache_from)


def caption_preflight(build, episode):
    from PIL import Image
    from episode_config import check_timeline
    from social_captions import caption_pages
    from tef_speaking_preview import compose

    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    check_timeline(episode, timeline)
    pages = caption_pages(episode, timeline)
    scale = 2 if episode.get("template") == "tef_speaking_full_production" else 1
    native = Image.new("RGB", (640 * scale, 320 * scale), "#617065")
    for page in pages:
        frame = round((page["start"] + page["end"]) * timeline["fps"] / 2)
        compose(episode, timeline, pages, frame, native)
    for turn in timeline["turns"]:
        if turn.get("kind") == "notice":
            for offset in (-1, 0, 1, turn["pause_after_frames"] // 2, turn["pause_after_frames"] - 1,
                           turn["pause_after_frames"]):
                compose(episode, timeline, pages, turn["end_frame"] + offset, native)
    folder = build / "preflight"
    folder.mkdir(exist_ok=True)
    atomic_json(folder / "landscape_captions.json", {
        "pages": pages, "native_landscape_layout_checked": True,
        "portrait_ass_not_used": True, "minimum_page_seconds": 1.8, "maximum_characters_per_second": 20,
    })
