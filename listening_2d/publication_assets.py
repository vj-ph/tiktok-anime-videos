"""Create local episode-1 captions and Lea covers, without uploading."""

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from prepare_sample import ROOT, atomic_json, sha256_file
from reduce_full import SELECTIONS, TOTALS, read_json

REPOSITORY = ROOT.parent
LEA_SOURCE = (REPOSITORY / "pilot_3d" / "builds" / "oeif_b1_speaking_long_contact_r7" /
              "native" / "youtube_group.png")
CAST_SOURCE = LEA_SOURCE.parents[1] / "episode.json"
LOGO = REPOSITORY / "pilot_3d" / "assets" / "deutschkompass-logo.png"
FONT = Path(r"C:\Windows\Fonts\arialbd.ttf")
LEA_CROP = (600, 82, 940, 422)
INK, GREEN, SAGE, CREAM, WARM = "#283e3c", "#3f685b", "#dce9df", "#fffefb", "#875a3b"
DATE = "November 2026"
EPISODE = "Episode 1"
SUBJECT = "ÖIF B1 Hören"
FORMATS = {"youtube": (1920, 1080), "tiktok": (1080, 1920), "instagram": (1080, 1350)}
PART_NAMES = {1: "Ansagen und Mitteilungen", 2: "Radiomeldungen",
              3: "Gespräche", 4: "Meinungen zuordnen"}
HOOKS = {
    1: "Zwei Ansagen, zwei Fragen: Hörst du die entscheidenden Details?",
    2: "Was ist wirklich gemeint? Trainiere dein Hörverstehen mit zwei Radiomeldungen.",
    3: "Zwei Gespräche, vier Fragen: Erkennst du Aussage und Absicht?",
    4: "Welche Meinung passt? Lies zuerst die sechs Aussagen und ordne dann zu.",
}


def font(size):
    return ImageFont.truetype(str(FONT), size)


def text(image, label, xy, size, maximum, fill=INK, centered=False):
    draw = ImageDraw.Draw(image)
    chosen = font(size)
    while draw.textlength(label, font=chosen) > maximum and size > 36:
        size -= 1
        chosen = font(size)
    assert draw.textlength(label, font=chosen) <= maximum, label
    x, y = xy
    if centered:
        x -= draw.textlength(label, font=chosen) / 2
    bounds = draw.textbbox((x, y), label, font=chosen, anchor="lt")
    assert 0 <= bounds[0] < bounds[2] <= image.width
    assert 0 <= bounds[1] < bounds[3] <= image.height
    draw.text((x, y), label, font=chosen, fill=fill, anchor="lt")
    return {"text": label, "font_px": size, "bounds": list(bounds)}


def pill(image, label, box, size=44, fill=GREEN):
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(box, radius=24, fill=fill)
    entry = text(image, label, ((box[0] + box[2]) / 2, box[1] + 19), size,
                 box[2] - box[0] - 36, CREAM, True)
    assert entry["bounds"][3] <= box[3] - 12
    return entry


def avatar():
    cast = read_json(CAST_SOURCE)
    assert cast["cast"]["candidate_a"] == "Lea"
    assert cast["thumbnail"]["cast"][1] == "candidate_a"
    with Image.open(LEA_SOURCE) as source:
        assert source.size == (1920, 750)
        cropped = source.convert("RGB").crop(LEA_CROP).resize((800, 800), Image.Resampling.LANCZOS)
    mask = Image.new("L", cropped.size)
    ImageDraw.Draw(mask).ellipse((4, 4, 795, 795), fill=255)
    cropped = cropped.convert("RGBA")
    cropped.putalpha(mask)
    return cropped


def place_avatar(image, lea, box):
    size = box[2] - box[0]
    draw = ImageDraw.Draw(image)
    draw.ellipse((box[0] - 14, box[1] - 14, box[2] + 14, box[3] + 14), fill="#ffffff")
    image.paste(lea.resize((size, size), Image.Resampling.LANCZOS), box[:2],
                lea.resize((size, size), Image.Resampling.LANCZOS))
    draw.ellipse((box[0] - 14, box[1] - 14, box[2] + 14, box[3] + 14), outline=GREEN, width=5)


def cover(platform, part, lea):
    size = FORMATS[platform]
    image = Image.new("RGB", size, "#f2f6f1")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((24, 24, size[0] - 24, size[1] - 24), 44, fill=CREAM, outline=SAGE, width=3)
    entries = []
    with Image.open(LOGO) as raw:
        logo = raw.convert("RGBA")
        logo.thumbnail((110, 110), Image.Resampling.LANCZOS)
        image.paste(logo, (84, 74 if platform != "tiktok" else 276), logo)
    if platform == "youtube":
        entries.append(text(image, "Deutsch Kompass", (216, 108), 42, 680, GREEN))
        entries.append(text(image, "ÖIF B1", (94, 255), 112, 1040))
        entries.append(text(image, "Hören", (86, 389), 176, 1040, GREEN))
        entries.append(text(image, "Prüfungssimulation", (94, 597), 86, 1070))
        label = "Geführte Übung · alle 4 Teile" if part is None else f"Teil {part} · Verkürzte Übung"
        entries.append(pill(image, label, (94, 746, 1130, 840), 48))
        entries.append(text(image, DATE, (94, 892), 57, 650, WARM))
        entries.append(text(image, EPISODE, (760, 902), 44, 350, WARM))
        place_avatar(image, lea, (1240, 273, 1800, 833))
        entries.append(text(image, "Lea", (1520, 880), 46, 500, GREEN, True))
    else:
        tik = platform == "tiktok"
        title_y = 434 if tik else 242
        entries.append(text(image, "Deutsch Kompass", (216, 310 if tik else 108), 42, 738, GREEN))
        entries.append(text(image, SUBJECT, (540, title_y), 100, 896, INK, True))
        entries.append(text(image, "Prüfungssimulation", (540, title_y + 138), 78, 896, GREEN, True))
        box = (300, 758, 780, 1238) if tik else (345, 494, 735, 884)
        place_avatar(image, lea, box)
        entries.append(text(image, "Lea", (540, box[3] + 34), 44, 600, GREEN, True))
        label = "Geführte Übung · alle 4 Teile" if part is None else f"Teil {part} · Verkürzte Übung"
        badge_y = 1354 if tik else 1000
        entries.append(pill(image, label, (80, badge_y, 1000, badge_y + 88), 44))
        entries.append(text(image, DATE, (540, badge_y + 132), 60, 896, WARM, True))
        entries.append(text(image, EPISODE, (540, badge_y + 216), 54, 896, WARM, True))
    for entry in entries:
        bounds = entry["bounds"]
        assert bounds[2] <= size[0] - 60 and bounds[0] >= 60
    for index, first in enumerate(entries):
        a = first["bounds"]
        for second in entries[index + 1:]:
            b = second["bounds"]
            assert min(a[2], b[2]) <= max(a[0], b[0]) or min(a[3], b[3]) <= max(a[1], b[1]), (
                first["text"], second["text"])
    return image, entries


def timestamp(seconds):
    whole = int(seconds)
    return f"{whole // 60:02d}:{whole % 60:02d}"


def caption(platform, part, full, short, book_link):
    youtube = platform == "youtube"
    title = f"{SUBJECT}: Prüfungssimulation mit Lösungen | {DATE} · {EPISODE}"
    if part is not None:
        title = f"{SUBJECT} · Teil {part} | Verkürzte Prüfungssimulation | {DATE} · {EPISODE}"
    assert len(title) <= 100
    heading = title + "\n\n"
    if part is None:
        body = (
            "Vier Teile, 20 Aufgaben: Wie viele löst du richtig? 🎧\n\n"
            "Trainiere mit Ansagen, Radiomeldungen, Gesprächen und Meinungen.\n"
            "Lies die Aufgaben, höre zu und notiere zuerst deine eigene Antwort.\n"
            "Nach jeder vollständigen Antwortpause erscheint die Lösung für drei Sekunden.\n"
            "Mit drei Beispielgruppen, hervorgehobenen Anleitungen und Lösungsübersicht.\n")
        if youtube:
            chapters = [("00:00", "Vorbereitung")]
            names = {f"instruction_{p}": f"Teil {p} – {PART_NAMES[p]}" for p in SELECTIONS}
            names.update(review_transition="Lösungen vergleichen", cta="Mehr üben mit dem Buch")
            chapters.extend((timestamp(e["start"]), names[e["id"]])
                            for e in full["events"] if e["id"] in names)
            body += "\nKapitel:\n" + "\n".join(f"{time} {name}" for time, name in chapters) + "\n"
    else:
        cards = read_json(Path(short["content_path"]))["cards"]
        numbers = [q["number"] for card in SELECTIONS[part] for q in cards[card]["questions"]]
        body = (
            f"{HOOKS[part]} 🎧\n\n"
            f"Teil {part} – {PART_NAMES[part]}. Aufgaben {numbers[0]}–{numbers[-1]}.\n"
            f"Verkürzte Übung: {len(numbers)} von {TOTALS[part]} Aufgaben, "
            "ohne Anleitung und Beispiel.\n"
            "Weniger Aufgaben, nicht weniger Zeit zum Antworten: "
            "Lese- und Antwortpausen bleiben unverändert.\n"
            "Antworte selbst; danach erscheint die Lösung für drei Sekunden.\n")
        if part == 4:
            body += "Die 60 Sekunden Lesezeit und alle sechs Aussagen bleiben erhalten.\n"
        body += "\nSpeichere die Übung und übe auch die anderen drei Teile.\n"
    body += (
        "\nGeführte Prüfungsvorbereitung mit Lösungen, keine ununterbrochene "
        "Prüfungssimulation.\nUnabhängig erstellte Aufgaben; keine offizielle ÖIF-Prüfung.\n"
        "KI-generierte Stimmen, für die Übung auf 0,8-faches Tempo verlangsamt.\n\n"
        "Mehr Hörübungen, Transkripte und Erklärungen im Buch.\n"
        "Werbung für unser Buch: ÖIF B1 Hören – Übungsbuch mit Audio.\n")
    body += ("👇 Amazon: Link in der Beschreibung\n" if youtube else "👇 Amazon: Link in der Bio\n")
    body += book_link + "\n\n"
    effects = "start/back/remove" if part is None else "back/remove"
    body += (
        f"SFX: Mixkit Software interface {effects}; verlangsamt und mit leichtem Nachhall.\n"
        "Mixkit Sound Effects Free License: https://mixkit.co/license/#sfxFree\n\n"
        "#ÖIFB1 #B1Hören #DeutschLernen #Hörverstehen #DeutschKompass\n")
    result = heading + body
    assert len(result) <= (5000 if youtube else 2200)
    return result


def generate(full, short, output):
    full, short, output = full.resolve(), short.resolve(), output.resolve()
    if output.exists():
        raise ValueError("Choose a fresh publication-asset directory.")
    full_timeline = read_json(full / "timeline.json")
    book_link = read_json(full / "sample_content.json")["episode"]["promotion"]["amazon_url"]
    sources = {LEA_SOURCE, CAST_SOURCE, LOGO, FONT, Path(__file__),
               full / "timeline.json", full / "sample_content.json"}
    for part in SELECTIONS:
        sources.update((short / f"teil_{part}" / "timeline.json",
                        short / f"teil_{part}" / "sample_content.json"))
    output.mkdir(parents=True)
    lea = avatar()
    lea.save(output / "avatar_lea.png")
    layouts, previews, captions = {}, [], {}
    for part in (None, *SELECTIONS):
        name = "full" if part is None else f"teil_{part}"
        folder = output / name
        folder.mkdir()
        binding = {} if part is None else {
            "content_path": str(short / name / "sample_content.json")}
        for platform in FORMATS:
            draft = caption(platform, part, full_timeline, binding, book_link)
            (folder / f"{platform}.txt").write_text(draft, encoding="utf-8")
            captions[f"{name}/{platform}"] = {"characters": len(draft), "title": draft.splitlines()[0]}
            image, text_entries = cover(platform, part, lea)
            target = folder / f"thumbnail_{platform}.png"
            image.save(target, optimize=True)
            layouts[str(target.relative_to(output))] = {
                "size": list(image.size), "text": text_entries,
                "lea_source_crop": list(LEA_CROP), "lea_identity": "candidate_a / Lea"}
            preview = Image.new("RGB", (480, 540), "#e8efe8")
            small = ImageOps.contain(image, (460, 495), Image.Resampling.LANCZOS)
            preview.paste(small, ((480 - small.width) // 2, 0))
            ImageDraw.Draw(preview).text((12, 510), f"{name} / {platform}", fill=INK, font=font(20))
            previews.append(preview)
    sheet = Image.new("RGB", (1440, 2700), "#e8efe8")
    for index, preview in enumerate(previews):
        sheet.paste(preview, ((index % 3) * 480, (index // 3) * 540))
    sheet.save(output / "thumbnail_contact_sheet.jpg", quality=94)
    atomic_json(output / "layout_checks.json", {"covers": layouts, "captions": captions})
    files = {str(p.relative_to(output)): sha256_file(p)
             for p in output.rglob("*") if p.is_file()}
    atomic_json(output / "publication_manifest.json", {
        "episode": 1, "edition": DATE, "full_build": str(full), "short_build": str(short),
        "avatar_provenance": "Local crop of the established smiling Lea, second from left in approved cast pose.",
        "inputs": {str(p): sha256_file(p) for p in sorted(sources)}, "files": files,
        "publication": "Local assets only; nothing uploaded."})
    print(f"Generated 15 descriptions, 15 native platform covers and Lea avatar in {output}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", type=Path, required=True)
    parser.add_argument("--short", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.full, args.short, args.output)
