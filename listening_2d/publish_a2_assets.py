"""Generate A2 posting drafts and native Lea covers bound to verified videos."""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from prepare_a2 import EPISODE, read
from prepare_sample import ROOT, atomic_json, sha256_file
from publication_assets import (
    LEA_SOURCE, CAST_SOURCE, LOGO, FONT, LEA_CROP, INK, GREEN, SAGE, CREAM, WARM,
    FORMATS, avatar, place_avatar, text, pill, font, timestamp,
)

SUBJECT = "ÖIF A2 Hören"
DATE, EDITION = "November 2026", "Episode 1"
PART_NAMES = {1: "Eine Nachricht, sieben Details", 2: "Zwei kurze Nachrichten",
              3: "Drei Ansagen", 4: "Drei Gespräche"}


def cover(platform, part, lea):
    size = FORMATS[platform]
    image = Image.new("RGB", size, "#f2f6f1")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((24, 24, size[0] - 24, size[1] - 24), 44,
                           fill=CREAM, outline=SAGE, width=3)
    entries = []
    with Image.open(LOGO) as raw:
        logo = raw.convert("RGBA")
        logo.thumbnail((110, 110), Image.Resampling.LANCZOS)
        image.paste(logo, (84, 276 if platform == "tiktok" else 74), logo)
    label = "Geführte Übung · alle 4 Teile" if part is None else f"Teil {part} · Verkürzte Übung"
    if platform == "youtube":
        entries.append(text(image, "Deutsch Kompass", (216, 108), 42, 680, GREEN))
        entries.append(text(image, "ÖIF A2", (94, 255), 112, 1040))
        entries.append(text(image, "Hören", (86, 389), 176, 1040, GREEN))
        entries.append(text(image, "Prüfungssimulation", (94, 597), 86, 1070))
        entries.append(pill(image, label, (94, 746, 1130, 840), 48))
        entries.append(text(image, DATE, (94, 892), 57, 650, WARM))
        entries.append(text(image, EDITION, (760, 902), 44, 350, WARM))
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
        badge_y = 1354 if tik else 1000
        entries.append(pill(image, label, (80, badge_y, 1000, badge_y + 88), 44))
        entries.append(text(image, DATE, (540, badge_y + 132), 60, 896, WARM, True))
        entries.append(text(image, EDITION, (540, badge_y + 216), 54, 896, WARM, True))
    for i, first in enumerate(entries):
        a = first["bounds"]
        assert 60 <= a[0] and a[2] <= size[0] - 60
        for second in entries[i + 1:]:
            b = second["bounds"]
            assert min(a[2], b[2]) <= max(a[0], b[0]) or min(a[3], b[3]) <= max(a[1], b[1])
    return image, entries


def caption(platform, part, full, short, episode):
    youtube = platform == "youtube"
    title = f"{SUBJECT}: Prüfungssimulation mit Lösungen | {DATE} · {EDITION}"
    if part is not None:
        title = f"{SUBJECT} · Teil {part} | Verkürzte Prüfungssimulation | {DATE} · {EDITION}"
    assert len(title) <= 100
    body = title + "\n\n"
    if part is None:
        body += (
            "Vier Teile, 15 Aufgaben: Wie viel verstehst du? 🎧\n\n"
            "Eine Nachricht mit sieben Details, zwei weitere Nachrichten, "
            "drei Ansagen und drei Gespräche.\n"
            "Teile 1 und 2 hörst du zweimal, Teile 3 und 4 einmal.\n"
            "Lies die Fragen, höre genau zu und notiere zuerst deine eigene Antwort.\n")
        if youtube:
            chapters = [("00:00", "Start und Teil 1 – " + PART_NAMES[1])]
            names = {f"instruction_{p}": f"Teil {p} – {PART_NAMES[p]}" for p in range(2, 5)}
            names["summary_read"] = "Lösungen und Buch"
            chapters.extend((timestamp(e["start"]), names[e["id"]])
                            for e in full["events"] if e["id"] in names)
            starts = [sum(int(v) * weight for v, weight in zip(time.split(":"), (60, 1)))
                      for time, _ in chapters]
            assert len(starts) >= 3 and starts[0] == 0
            assert all(end - start >= 10 for start, end in zip(starts, [*starts[1:], full["duration"]]))
            body += "\nKapitel:\n" + "\n".join(f"{time} {name}" for time, name in chapters) + "\n"
    else:
        numbers = short["selected"]
        count = sum(len(g["questions"]) for g in episode["sections"][part - 1]["groups"])
        body += f"Teil {part} – {PART_NAMES[part]}. Aufgaben {numbers[0]}–{numbers[-1]}. 🎧\n\n"
        if len(numbers) < count:
            body += (f"Verkürzte Übung: {len(numbers)} von {count} Aufgaben, ohne lange Anleitung.\n"
                     "Weniger Aufgaben, nicht weniger Zeit zum Antworten.\n")
        else:
            body += (f"Verkürzte Übung ohne lange Anleitung: alle {count} Aufgaben dieses Teils.\n"
                     "Die Aufgabenzahl ist nicht reduziert; gekürzt ist nur die Einleitung.\n")
        body += ("30 Sekunden Lesezeit, vollständige Aufnahmen und alle Wiederholungen bleiben erhalten.\n"
                 "Auch die Antwortpausen sind unverändert.\n")
    body += (
        "\nNach jeder vollständigen Antwortpause erscheint die Lösung für drei Sekunden.\n"
        "Geführte, unabhängig erstellte Prüfungsvorbereitung; keine offizielle ÖIF-Prüfung "
        "und keine ununterbrochene Prüfungssimulation.\n"
        "Die Übung nutzt 30 Sekunden Lesezeit pro Teil, 8 Sekunden zwischen Wiederholungen "
        "und 12 Sekunden Antwortzeit: bewusst längere Übungspausen, keine exakte offizielle Prüfungszeit.\n"
        "Neue Alltagssituationen; keine Buchaufgaben oder offiziellen Aufnahmen übernommen.\n"
        "KI-generierte Stimmen, für die Übung auf 0,8-faches Tempo verlangsamt.\n\n"
        "Mehr Hörübungen, Transkripte und Erklärungen im Buch.\n"
        "Werbung für unser Buch: ÖIF A2 Hören – Übungsbuch mit Audio.\n")
    body += "👇 Amazon: Link in der Beschreibung\n" if youtube else "👇 Amazon: Link in der Bio\n"
    body += episode["promotion"]["amazon_url"] + "\n\n"
    audio_ids = {e.get("audio_id") for e in (full if part is None else short)["events"]}
    effects = "/".join(label for ident, label in (
        ("chime_start", "start"), ("chime_back", "back"), ("chime_remove", "remove"))
        if ident in audio_ids)
    body += (f"SFX: Mixkit Software interface {effects}; verlangsamt und mit leichtem Nachhall.\n"
             "Mixkit Sound Effects Free License: https://mixkit.co/license/#sfxFree\n\n"
             "#ÖIFA2 #A2Hören #DeutschLernen #Hörverstehen #DeutschKompass\n")
    assert len(body) <= (5000 if youtube else 2200)
    return body


def generate(full, short, output):
    if output.exists():
        raise ValueError("Choose a fresh A2 posts directory.")
    inputs = {EPISODE, LEA_SOURCE, CAST_SOURCE, LOGO, FONT, Path(__file__),
              ROOT / "publication_assets.py"}
    for folder in (full, *(short / f"teil_{p}" for p in range(1, 5))):
        audit = read(folder / "delivery_audit.json")
        assert audit["manifest_sha256"] == sha256_file(folder / "delivery_manifest.json")
        delivery = read(folder / "delivery_manifest.json")
        for name, digest in delivery["files"].items():
            assert sha256_file(folder / name) == digest
        for path, digest in delivery["code_inputs"].items():
            assert sha256_file(Path(path)) == digest
            inputs.add(Path(path))
        inputs.update((folder / "delivery_manifest.json", folder / "delivery_audit.json",
                       folder / "timeline.json", folder / "sample_content.json"))
    episode = read(full / "sample_content.json")["episode"]
    assert episode["level"] == "A2" and episode == read(EPISODE)
    full_clock = read(full / "timeline.json")
    output.mkdir(parents=True)
    lea = avatar()
    lea.save(output / "avatar_lea.png")
    layouts, previews, captions = {}, [], {}
    for part in (None, 1, 2, 3, 4):
        name = "full" if part is None else f"teil_{part}"
        folder = output / name
        folder.mkdir()
        short_clock = None if part is None else read(short / name / "timeline.json")
        for platform in FORMATS:
            draft = caption(platform, part, full_clock, short_clock, episode)
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
    for i, preview in enumerate(previews):
        sheet.paste(preview, ((i % 3) * 480, (i // 3) * 540))
    sheet.save(output / "thumbnail_contact_sheet.jpg", quality=94)
    atomic_json(output / "layout_checks.json", {"covers": layouts, "captions": captions})
    files = {str(p.relative_to(output)): sha256_file(p) for p in output.rglob("*") if p.is_file()}
    atomic_json(output / "publication_manifest.json", {
        "episode": 1, "edition": DATE, "full_build": str(full), "short_build": str(short),
        "inputs": {str(p): sha256_file(p) for p in sorted(inputs)}, "files": files,
        "publication": "Local A2 drafts and covers only; nothing uploaded.",
    })
    print(f"A2 publishing assets: 15 descriptions and 15 covers in {output}.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", type=Path, required=True)
    parser.add_argument("--short", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.full.resolve(), args.short.resolve(), args.output.resolve())
