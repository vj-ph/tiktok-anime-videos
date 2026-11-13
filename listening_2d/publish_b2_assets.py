"""Create B2 platform drafts and Samir covers without changing frozen videos."""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from prepare_sample import ROOT, atomic_json, sha256_file
from publication_assets import (
    CAST_SOURCE, CREAM, FONT, FORMATS, GREEN, INK, LEA_SOURCE, LOGO, SAGE,
    WARM, font, pill, place_avatar, text, timestamp,
)
from prepare_b2 import read

SAMIR_CROP = (985, 20, 1325, 360)
HEAD_GUARD = (1080, 60, 1230, 285)
SUBJECT = "ÖIF B2 Hören"
PART_NAMES = {1: "Nachrichten", 2: "Interview", 3: "Kurze Hörtexte"}
NUMBERS = {1: [41, 42], 2: [49], 3: [56, 57]}
TOTALS = {1: 5, 2: 10, 3: 5}
HOOKS = {
    1: "Zwei Meldungen, zwei Entscheidungen: Hörst du die entscheidenden Details?",
    2: "Ein Interviewausschnitt, eine Aussage: Wie genau hörst du zu?",
    3: "Zwei kurze Hörtexte: Erkennst du, was wirklich gesagt wird?",
}


def samir_avatar():
    cast = read(CAST_SOURCE)
    assert cast["cast"]["candidate_b"] == "Samir"
    assert cast["thumbnail"]["cast"][2] == "candidate_b"
    with Image.open(LEA_SOURCE) as source:
        assert source.size == (1920, 750)
        cropped = source.convert("RGB").crop(SAMIR_CROP)
    mask = Image.new("L", cropped.size)
    ImageDraw.Draw(mask).ellipse((2, 2, 337, 337), fill=255)
    x0, y0, x1, y1 = HEAD_GUARD
    for x, y in ((x0, y0), (x0, y1), (x1, y0), (x1, y1)):
        assert mask.getpixel((x - SAMIR_CROP[0], y - SAMIR_CROP[1])) == 255
    cropped = cropped.convert("RGBA")
    cropped.putalpha(mask)
    return cropped.resize((800, 800), Image.Resampling.LANCZOS)


def cover(platform, part, avatar, date, edition):
    size = FORMATS[platform]
    image = Image.new("RGB", size, "#f2f6f1")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((24, 24, size[0] - 24, size[1] - 24), 44,
                           fill=CREAM, outline=SAGE, width=3)
    with Image.open(LOGO) as raw:
        logo = raw.convert("RGBA")
        logo.thumbnail((110, 110), Image.Resampling.LANCZOS)
        logo_xy = (84, 276 if platform == "tiktok" else 74)
        image.paste(logo, logo_xy, logo)
    entries = []
    label = "Geführte Übung · alle 3 Teile" if part is None else f"Teil {part} · Verkürzte Übung"
    if platform == "youtube":
        entries.append(text(image, "Deutsch Kompass", (216, 108), 42, 680, GREEN))
        entries.append(text(image, "ÖIF B2", (94, 255), 112, 1040))
        entries.append(text(image, "Hören", (86, 389), 176, 1040, GREEN))
        entries.append(text(image, "Prüfungssimulation", (94, 597), 86, 1070))
        entries.append(pill(image, label, (94, 746, 1130, 840), 48))
        entries.append(text(image, date, (94, 892), 57, 650, WARM))
        entries.append(text(image, edition, (760, 902), 44, 350, WARM))
        avatar_box = (1240, 273, 1800, 833)
        place_avatar(image, avatar, avatar_box)
        entries.append(text(image, "Samir", (1520, 880), 46, 500, GREEN, True))
    else:
        tik = platform == "tiktok"
        title_y = 434 if tik else 242
        entries.append(text(image, "Deutsch Kompass", (216, 310 if tik else 108), 42, 738, GREEN))
        entries.append(text(image, SUBJECT, (540, title_y), 100, 896, INK, True))
        entries.append(text(image, "Prüfungssimulation", (540, title_y + 138), 78, 896, GREEN, True))
        avatar_box = (300, 758, 780, 1238) if tik else (345, 494, 735, 884)
        place_avatar(image, avatar, avatar_box)
        entries.append(text(image, "Samir", (540, avatar_box[3] + 34), 44, 600, GREEN, True))
        badge_y = 1354 if tik else 1000
        entries.append(pill(image, label, (80, badge_y, 1000, badge_y + 88), 44))
        entries.append(text(image, date, (540, badge_y + 132), 60, 896, WARM, True))
        entries.append(text(image, edition, (540, badge_y + 216), 54, 896, WARM, True))
    regions = [dict(text="logo", bounds=[*logo_xy, logo_xy[0] + logo.width, logo_xy[1] + logo.height]),
               dict(text="Samir portrait", bounds=list(avatar_box)), *entries]
    for i, first in enumerate(regions):
        a = first["bounds"]
        assert 60 <= a[0] < a[2] <= size[0] - 60 and 0 <= a[1] < a[3] <= size[1]
        for second in regions[i + 1:]:
            b = second["bounds"]
            assert min(a[2], b[2]) <= max(a[0], b[0]) or min(a[3], b[3]) <= max(a[1], b[1]), (
                first["text"], second["text"])
    return image, dict(size=list(size), text=entries, regions=regions,
                      samir_identity="candidate_b / Samir", source_crop=list(SAMIR_CROP),
                      head_guard=list(HEAD_GUARD))


def chapters(timeline):
    labels = {"instruction_2": "Teil 2 – Interview",
              "instruction_3": "Teil 3 – Kurze Hörtexte",
              "summary_read": "Lösungen im Überblick und Buch"}
    points = [(0, "Start und Teil 1 – Nachrichten")]
    points.extend((int(e["start_frame"] / 24), labels[e["id"]])
                  for e in timeline["events"] if e["id"] in labels)
    assert len(points) == 4
    assert all(b - a >= 10 for a, b in zip(
        [p[0] for p in points], [*[p[0] for p in points[1:]], timeline["duration"]]))
    return points


def caption(platform, part, timeline, episode):
    date = f'{episode["edition"]["month"]} {episode["edition"]["year"]}'
    edition = f'Episode {episode["edition"]["episode"]}'
    title = f"{SUBJECT}: Prüfungssimulation mit Lösungen | {date} · {edition}"
    if part is not None:
        title = f"{SUBJECT} · Teil {part} | Verkürzte Übung mit Lösungen | {date} · {edition}"
    assert len(title) <= 100
    body = title + "\n\n"
    if part is None:
        body += (
            "20 Aussagen, drei Teile: Wie viele löst du richtig? 🎧\n\n"
            "Trainiere mit einer Nachrichtensendung, einem Interview und fünf kurzen Hörtexten.\n"
            "Alle 20 Aufgaben (41–60), jede Aufnahme einmal. Antworte zuerst selbst.\n"
            "Teil 1: 30 Sekunden lesen, nach dem Hören 15 Sekunden Antwortzeit.\n"
            "Teil 2: 60 Sekunden lesen; nach dem Interview und Kontrollhinweis "
            "30 Sekunden prüfen.\n"
            "Teil 3: nach jedem Hörtext 15 Sekunden Antwortzeit.\n"
            "Erst danach erscheinen die Lösungen direkt an den Aussagen: Richtig grün, Falsch rot.\n"
            "Teil 1 gemeinsam für drei Sekunden, Teil 2 in zwei Gruppen "
            "(46–50 / 51–55) für je drei Sekunden, Teil 3 je Aufgabe für drei Sekunden.\n")
        if platform == "youtube":
            body += "\nKapitel:\n" + "\n".join(f"{timestamp(s)} {label}" for s, label in chapters(timeline)) + "\n"
    else:
        selected = NUMBERS[part]
        assert timeline["selected_numbers"] == selected
        assert timeline["total_questions"] == TOTALS[part] and timeline["adapted_pauses"] is True
        numbers = " / ".join(map(str, selected))
        task_label = "Aufgabe" if len(selected) == 1 else "Aufgaben"
        body += (
            f"{HOOKS[part]} 🎧\n\n"
            f"Teil {part} – {PART_NAMES[part]}. {task_label} {numbers}.\n"
            f"Verkürzte Übung: {len(selected)} von {TOTALS[part]} Aussagen, "
            f"ca. {timestamp(timeline['duration'])} Minuten.\n")
        body += {
            1: "Zwei vollständige ausgewählte Nachrichtenmeldungen, nicht die ganze Sendung.\n",
            2: "Eine vollständige Interviewfrage samt Antwort, nicht das gesamte Interview.\n",
            3: "Zwei vollständige Hörtexte mit ihren gesprochenen Nummern.\n",
        }[part]
        if part in (1, 2):
            body += (
                "Separate gesprochene Anleitung mit Wortmarkierung, anschließend "
                "15 stille Sekunden zum Lesen.\n"
                "Nach dem Hören 10 stille Sekunden zum Antworten oder Prüfen.\n")
        else:
            body += "Keine zusätzliche Lesephase; nach jedem Hörtext 15 stille Sekunden Antwortzeit.\n"
        body += (
            "Angepasste Kurzpraxis mit ausgewählten Aufgaben und eigenen Übungspausen, "
            "kein vollständiger Prüfungsteil.\n"
            "Danach drei Sekunden Lösung direkt an der Aussage: Richtig grün, Falsch rot.\n"
            "Speichere die Übung und trainiere auch die anderen Teile!\n")
    body += (
        "\nGeführte Prüfungsvorbereitung mit Lösungen, keine ununterbrochene Prüfungssimulation.\n"
        "Unabhängig erstellte Aufgaben; keine offizielle ÖIF-Prüfung.\n"
        "Die Pausen wurden für diese Übung festgelegt; keine Zusage exakter offizieller Prüfungszeiten.\n"
        "KI-generierte Stimmen, für die Übung auf 0,8-faches Tempo verlangsamt.\n\n"
        "Mehr Hörübungen, Transkripte und Erklärungen im Buch.\n"
        "Werbung für unser Buch: ÖIF B2 Hören – Übungsbuch.\n")
    body += "👇 Amazon: Link in der Beschreibung\n" if platform == "youtube" else "👇 Amazon: Link in der Bio\n"
    body += episode["promotion"]["amazon_url"] + "\n\n"
    used = {e["audio_id"] for e in timeline["events"]
            if (e.get("audio_id") or "").startswith("chime_")}
    known = {"chime_start": "start", "chime_back": "back", "chime_remove": "remove"}
    assert used <= known.keys()
    effects = "/".join(label for key, label in known.items() if key in used)
    body += (
        f"SFX: Mixkit Software interface {effects}; verlangsamt und mit leichtem Nachhall.\n"
        "Mixkit Sound Effects Free License: https://mixkit.co/license/#sfxFree\n\n"
        "#ÖIFB2 #B2Hören #DeutschLernen #Hörverstehen #DeutschKompass\n")
    assert len(body) <= (5000 if platform == "youtube" else 2200)
    return body


def generate(build, output):
    assert not output.exists(), "Choose a fresh publication directory."
    delivery = read(build / "delivery_manifest.json")
    assert read(build / "delivery_audit.json")["manifest_sha256"] == sha256_file(build / "delivery_manifest.json")
    for name, digest in delivery["files"].items():
        assert sha256_file(build / name) == digest, name
    for name, digest in delivery["code_inputs"].items():
        assert sha256_file(Path(name)) == digest, name
    inputs = {Path(__file__), ROOT / "test_b2_publication.py", ROOT / "publication_assets.py", LEA_SOURCE,
              CAST_SOURCE, LOGO, FONT, build / "delivery_manifest.json",
              build / "delivery_audit.json"}
    episode = read(build / "full" / "sample_content.json")["episode"]
    assert episode["level"] == "B2"
    date = f'{episode["edition"]["month"]} {episode["edition"]["year"]}'
    edition = f'Episode {episode["edition"]["episode"]}'
    avatar = samir_avatar()
    output.mkdir(parents=True)
    avatar.save(output / "avatar_samir.png")
    layouts, captions, previews = {}, {}, []
    for part in (None, 1, 2, 3):
        name = "full" if part is None else f"teil_{part}"
        folder = output / name
        folder.mkdir()
        timeline = read(build / name / "timeline.json")
        inputs.update((build / name / "timeline.json", build / name / "sample_content.json"))
        for platform in FORMATS:
            draft = caption(platform, part, timeline, episode)
            (folder / f"{platform}.txt").write_text(draft, encoding="utf-8")
            captions[f"{name}/{platform}"] = dict(characters=len(draft), title=draft.splitlines()[0])
            image, layout = cover(platform, part, avatar, date, edition)
            target = folder / f"thumbnail_{platform}.png"
            image.save(target, optimize=True)
            layouts[str(target.relative_to(output))] = layout
            preview = Image.new("RGB", (480, 540), "#e8efe8")
            small = ImageOps.contain(image, (460, 495), Image.Resampling.LANCZOS)
            preview.paste(small, ((480 - small.width) // 2, 0))
            ImageDraw.Draw(preview).text((12, 510), f"{name} / {platform}", fill=INK, font=font(20))
            previews.append(preview)
    sheet = Image.new("RGB", (1440, 2160), "#e8efe8")
    for i, preview in enumerate(previews):
        sheet.paste(preview, ((i % 3) * 480, (i // 3) * 540))
    sheet.save(output / "thumbnail_contact_sheet.jpg", quality=94)
    atomic_json(output / "layout_checks.json", dict(covers=layouts, captions=captions,
                                                   full_chapters=chapters(read(build / "full" / "timeline.json"))))
    files = {str(p.relative_to(output)): sha256_file(p) for p in output.rglob("*") if p.is_file()}
    atomic_json(output / "publication_manifest.json", dict(
        episode=episode["edition"]["episode"], edition=date, video_build=str(build),
        videos=delivery["outputs"], avatar_identity="candidate_b / Samir",
        avatar_provenance="Local crop of the approved smiling third character; no new model image.",
        inputs={str(p): sha256_file(p) for p in sorted(inputs)}, files=files,
        publication="Local descriptions and covers only; nothing uploaded."))
    print(f"Generated 12 descriptions and 12 Samir covers: {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    generate(args.build.resolve(), args.output.resolve())
