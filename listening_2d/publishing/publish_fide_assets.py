"""Prepare measured fide listening descriptions and Swiss crop-safe covers locally."""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from listening_2d.preparation.prepare_fide import EPISODE, ROOT, atomic_json, read, sha256_file, verify_files
from listening_2d.publishing.publication_assets import CREAM, GREEN, INK, LOGO, SAGE, pill, text, timestamp

SAFE = (90, 460, 900, 1240)
CROPS = {"square": (0, 420, 1080, 1500), "4x5": (0, 285, 1080, 1635),
         "3x4": (0, 240, 1080, 1680)}


def contains(outer, inner):
    return outer[0] <= inner[0] < inner[2] <= outer[2] and outer[1] <= inner[1] < inner[3] <= outer[3]


def caption(platform, episode, timeline):
    events = {event["id"]: event for event in timeline["events"]}
    body = (
        "fide A2-B1 Verstehen | Prüfungssimulation mit Lösungen und Modellantworten\n\n"
        "12 Aufgaben aus dem Schweizer Alltag: Wie viel verstehst du?\n"
        "A2 (7–12): Wähle das passende Bild. B1 (13–18): Antworte mündlich.\n"
        "Zuerst die Frage, dann der Hörtext, danach dieselbe Frage und deine Antwort.\n"
        "Alle Lösungen folgen erst nach dem gesamten Test: A2 mit Bild und Erklärung, "
        "B1 mit möglichen Antworten. Andere passende Formulierungen sind ebenfalls richtig.\n\n"
        "Übungseinstellungen: 0,8-faches Sprechtempo; A2 fünf Sekunden Bilder ansehen "
        "und zehn Sekunden antworten; B1 zwanzig Sekunden antworten. "
        "Jeder Hörtext einmal. Bei Bedarf einmal zum Anfang des vollständigen Hörtextes zurückspringen "
        "oder für mehr Antwortzeit pausieren.\n"
        "Der echte fide-Test ist individuell prüfungsgeleitet; diese festen Pausen und "
        "das verlangsamte Tempo sind Übungsanpassungen, keine offiziellen Zeitvorgaben.\n")
    if platform == "youtube":
        chapter_ids = [
            (None, "Start und Anleitung"), ("context_a2_sbb", "A2 · Bahnhof · Aufgaben 7–9"),
            ("context_a2_tram", "A2 · Tram · Aufgaben 10–12"), ("transition", "Wechsel zu B1"),
            ("context_b1_verwaltung", "B1 · Hausverwaltung · Aufgaben 13–15"),
            ("context_b1_nachbarn", "B1 · Nachbarschaft · Aufgaben 16–18"),
            ("solution_7", "A2 · Lösungen"), ("solution_13", "B1 · Modellantworten"),
            ("cta", "Mehr üben mit dem Buch")]
        body += "\nKapitel:\n" + "\n".join(
            f'{timestamp(0 if ident is None else events[ident]["start"])} {label}'
            for ident, label in chapter_ids) + "\n"
    body += "\nHörtexte zum einmaligen Wiederholen:\n"
    body += "\n".join(f'{timestamp(events[f"recording_{number}"]["start"])} · Aufgabe {number}'
                      for number in range(7, 19))
    body += (
        "\n\nMehr Hörübungen, Transkripte und Modelldialoge im fide A2-B1 Komplettband "
        "(Sprechen, Schreiben und Hören).\n"
        f'Amazon: {episode["promotion"]["amazon_url"]}'
        + (" – Link auch in der Bio." if platform != "youtube" else "") +
        "\n\nEigenständiges Übungsmaterial von Deutsch Kompass, keine offizielle fide-Prüfung. "
        "KI-generierte Stimmen; keine Musik oder Soundeffekte. "
        "Die Übung ist keine Bewertung oder Garantie eines Prüfungsergebnisses.\n"
        "\n#fideTest #DeutschLernen #DeutschSchweiz #A2Deutsch #B1Deutsch #Hörverstehen\n")
    return body


def cover(episode, portrait=False):
    size = (1080, 1920) if portrait else (1920, 1080)
    image = Image.new("RGB", size, "#f2f6f1")
    draw = ImageDraw.Draw(image)
    card = (88, 444, 908, 1254) if portrait else (32, 32, 1888, 1048)
    draw.rounded_rectangle(card, radius=32, fill=CREAM, outline=SAGE, width=3)
    entries, regions = [], []
    with Image.open(LOGO) as original:
        logo = original.convert("RGBA")
        logo.thumbnail((60, 60) if portrait else (100, 100), Image.Resampling.LANCZOS)
        xy = (112, 474) if portrait else (80, 65)
        image.paste(logo, xy, logo)
        regions.append({"text": "Deutsch Kompass logo", "bounds": [*xy, xy[0] + logo.width, xy[1] + logo.height]})
    with Image.open(ROOT.parent / "pilot_3d" / "assets" / "flags" / "switzerland.png") as original:
        flag = original.convert("RGBA")
        box = (804, 474, 874, 544) if portrait else (1690, 80, 1810, 200)
        flag = flag.resize((box[2] - box[0], box[3] - box[1]), Image.Resampling.LANCZOS)
        image.paste(flag, box[:2], flag)
        regions.append({"text": "Swiss flag", "bounds": list(box)})
    if portrait:
        entries.extend([
            text(image, "Deutsch Kompass", (188, 490), 32, 560, GREEN),
            text(image, "fide A2-B1", (112, 590), 88, 760),
            text(image, "Verstehen", (112, 705), 104, 760, "#982d37"),
            text(image, "Prüfungssimulation", (112, 845), 62, 760),
            text(image, "12 Aufgaben", (112, 975), 48, 540, GREEN),
            text(image, "Mit Lösungen", (112, 1050), 48, 540, GREEN),
            text(image, "B1: Modellantworten", (112, 1130), 38, 540)])
        book_box = (690, 940, 874, 1216)
    else:
        entries.extend([
            text(image, "Deutsch Kompass", (208, 98), 40, 1000, GREEN),
            text(image, "fide A2-B1", (90, 215), 116, 1130),
            text(image, "Verstehen", (84, 367), 154, 1130, "#982d37"),
            text(image, "Prüfungssimulation", (90, 568), 88, 1130),
            text(image, "12 Aufgaben · Mit Lösungen", (90, 719), 56, 1130, GREEN),
            pill(image, "A2: Bilder · B1: mündlich", (90, 850, 1170, 950), 48)])
        book_box = (1330, 290, 1730, 890)
    source = (EPISODE.parent / episode["promotion"]["cover"]).resolve(strict=True)
    with Image.open(source) as original:
        book = ImageOps.contain(original.convert("RGB"),
                                (book_box[2] - book_box[0], book_box[3] - book_box[1]),
                                Image.Resampling.LANCZOS)
        xy = (book_box[0] + (book_box[2] - book_box[0] - book.width) // 2, book_box[1])
        image.paste(book, xy)
        regions.append({"text": "Book cover", "bounds": [*xy, xy[0] + book.width, xy[1] + book.height]})
    regions.extend(entries)
    for index, first in enumerate(regions):
        bounds = first["bounds"]
        if portrait:
            assert contains(SAFE, bounds) and all(contains(crop, bounds) for crop in CROPS.values()), first
        for second in regions[index + 1:]:
            other = second["bounds"]
            assert min(bounds[2], other[2]) <= max(bounds[0], other[0]) or min(bounds[3], other[3]) <= max(bounds[1], other[1]), (first, second)
    return image, {"size": list(size), "regions": regions, "social_safe_bounds": list(SAFE) if portrait else None,
                   "center_crop_checks": CROPS if portrait else {}, "new_ai_image_generation": False}


def publish(build, output):
    if output.exists():
        raise ValueError("Use a fresh publication directory.")
    delivery = read(build / "delivery_manifest.json")
    verify_files({str(build / name): digest for name, digest in delivery["files"].items()})
    verify_files(delivery["code_inputs"])
    episode = read(build / "sample_content.json")["episode"]
    timeline = read(build / "timeline.json")
    output.mkdir(parents=True)
    layouts = {}
    for platform in ("youtube", "tiktok", "instagram"):
        (output / f"{platform}.txt").write_text(caption(platform, episode, timeline), encoding="utf-8")
        image, layouts[platform] = cover(episode, portrait=platform != "youtube")
        image.save(output / f"thumbnail_{platform}.jpg", quality=94, subsampling=0)
    social = Image.open(output / "thumbnail_instagram.jpg")
    previews = []
    for label, box in CROPS.items():
        crop = social.crop(box)
        crop.thumbnail((360, 480), Image.Resampling.LANCZOS)
        previews.append((label, crop))
    sheet = Image.new("RGB", (1920, 1170), "#f2f6f1")
    youtube = Image.open(output / "thumbnail_youtube.jpg")
    youtube.thumbnail((960, 540))
    sheet.paste(youtube, (0, 0))
    portrait = social.copy()
    portrait.thumbnail((360, 640))
    sheet.paste(portrait, (990, 0))
    for index, (label, crop) in enumerate(previews):
        sheet.paste(crop, (index * 420, 650))
        ImageDraw.Draw(sheet).text((index * 420, 1140), label, fill=INK)
    sheet.save(output / "thumbnail_contact_sheet.jpg", quality=94)
    atomic_json(output / "layout_checks.json", layouts)
    inputs = {str(build / "delivery_manifest.json"): sha256_file(build / "delivery_manifest.json"),
              str(build / "timeline.json"): sha256_file(build / "timeline.json"),
              str(Path(__file__)): sha256_file(Path(__file__)),
              str(ROOT / "publishing/publication_assets.py"): sha256_file(ROOT / "publishing/publication_assets.py"),
              str(LOGO): sha256_file(LOGO),
              str(ROOT.parent / "pilot_3d" / "assets" / "flags" / "switzerland.png"):
                  sha256_file(ROOT.parent / "pilot_3d" / "assets" / "flags" / "switzerland.png"),
              str((EPISODE.parent / episode["promotion"]["cover"]).resolve()):
                  sha256_file((EPISODE.parent / episode["promotion"]["cover"]).resolve())}
    atomic_json(output / "publication_manifest.json", {
        "inputs": inputs, "source_build": str(build), "video_hashes": delivery["outputs"],
        "assets": {p.name: sha256_file(p) for p in output.iterdir() if p.is_file()},
        "measured_duration": timeline["duration"], "uploaded": False})
    print(f"Fide descriptions and three platform covers ready: {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    publish(args.build.resolve(), args.output.resolve())
