"""Publish local fide full/social captions and crop-checked Swiss covers."""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from prepare_fide import EPISODE, ROOT, atomic_json, read, sha256_file, verify_files
from publication_assets import CREAM, GREEN, INK, LOGO, SAGE, pill, text, timestamp
from publish_fide_assets import CROPS, SAFE, contains

FLAG = ROOT.parent / "pilot_3d" / "assets" / "flags" / "switzerland.png"
FONT = Path(r"C:\Windows\Fonts\arialbd.ttf")
PAIRS = ((7, 8), (9, 10), (11, 12), (13, 14), (15, 16), (17, 18))
TOPICS = ("Bahnhof", "Bahnhof & Tram", "Tram", "Hausverwaltung",
          "Wohnen & Nachbarn", "Nachbarschaft")
HOOKS = (
    "Verstehst du die wichtigen Informationen am Bahnhof?",
    "Vom Bahnhof ins Tram: Welche Information ist entscheidend?",
    "Hör genau hin: Was ändert sich bei der Tramfahrt?",
    "Ein Problem im Haus: Kannst du die Fragen dazu beantworten?",
    "Hausverwaltung und Nachbarn: Verstehst du beide Nachrichten?",
    "Eine Nachricht aus der Nachbarschaft: Was ist wirklich gemeint?",
)
SFX = ("SFX: Mixkit Software interface remove (0,8x, leichter Nachhall). "
       "Lizenz: https://mixkit.co/license/#sfxFree")


def caption(platform, episode, timeline, part=None):
    events = {event["id"]: event for event in timeline["events"]}
    numbers = list(range(7, 19)) if part is None else list(PAIRS[part - 1])
    url = episode["promotion"]["amazon_url"]
    assert url == "https://amzn.eu/d/0dDgJ1ZT"
    if part is None:
        body = (
            "fide A2-B1 Verstehen | Hörverstehen mit Lösungen und Modellantworten\n\n"
            "Wie viel Deutsch verstehst du im Schweizer Alltag? Übe alle 12 Aufgaben "
            "dieser A2-B1-Serie: Bahnhof, Tram, Hausverwaltung und Nachbarschaft.\n"
            "A2 (7–12): Wähle das passende Bild. B1 (13–18): Antworte laut.\n")
    else:
        level = "A2" if numbers[0] < 13 else "B1"
        body = (
            f"fide A2-B1 Verstehen | Video {part}/6 · {TOPICS[part - 1]}\n\n"
            f"{HOOKS[part - 1]}\n"
            f"{level} · Aufgaben {numbers[0]}–{numbers[1]} · 2 von 12 Aufgaben der Serie.\n"
            "Verkürzte Übung mit zwei vollständigen Aufgaben, kein kompletter Test.\n"
            + ("Wähle zu jeder Frage das passende Bild: A, B oder C.\n"
               if level == "A2" else
               "Beantworte die Fragen laut und vergleiche mit der Modellantwort. "
               "Andere passende Formulierungen sind möglich.\n"))
    body += (
        "\nFrage → Hörtext → gleiche Frage → deine Antwort. Erst nach der ganzen "
        "Antwortpause: Lösungsklang, gesprochene Lösung/Modellantwort, zwei Sekunden Haltezeit.\n"
        "Übungstempo: 0,8x Schweizer Standarddeutsch; jeder Hörtext einmal.\n")
    if part is None or numbers[0] < 13:
        body += "A2: fünf Sekunden Bilder ansehen, zehn Sekunden Antwortzeit.\n"
    if part is None or numbers[0] >= 13:
        body += "B1: zwanzig Sekunden Antwortzeit.\n"
    if part is not None:
        body += ("Aufnahmen und Aufgabenpausen sind gegenüber der Langfassung unverändert. "
                 "Die sechs Videos decken zusammen Aufgaben 7–18 ab.\n")
    body += (
        "Bei Bedarf einmal den vollständigen Hörtext wiederholen oder für mehr Zeit pausieren. "
        "Feste Pausen und verlangsamtes Tempo sind Übungsanpassungen, "
        "keine offiziellen Zeitvorgaben.\n")
    if platform == "youtube" and part is None:
        chapters = (
            (None, "Start und Anleitung"),
            ("context_a2_sbb", "A2 · Bahnhof · Aufgaben 7–9"),
            ("context_a2_tram", "A2 · Tram · Aufgaben 10–12"),
            ("transition", "Wechsel zu B1"),
            ("context_b1_verwaltung", "B1 · Hausverwaltung · Aufgaben 13–15"),
            ("context_b1_nachbarn", "B1 · Nachbarschaft · Aufgaben 16–18"),
            ("cta", "Mehr üben mit dem Buch"))
        body += "\nKapitel:\n" + "\n".join(
            f'{timestamp(0 if ident is None else events[ident]["start"])} {label}'
            for ident, label in chapters) + "\n"
    body += "\nHörtexte zum Wiederholen:\n" + "\n".join(
        f'{timestamp(events[f"recording_{n}"]["start"])} · Aufgabe {n}' for n in numbers)
    cue = "Link in der Beschreibung" if platform == "youtube" else "Link in der Bio / Beschreibung"
    body += (
        "\n\nMehr Aufgaben, Hörübungen und Modelldialoge im fide A2-B1 Komplettband "
        "(Sprechen, Schreiben und Hören).\n"
        f"👇 Amazon: {cue}\n{url}\n\n"
        "Speichern und noch einmal ohne Hilfe üben!"
        "\nEigenständige geführte Übung von Deutsch Kompass, keine offizielle fide-Prüfung. "
        f"KI-generierte Stimmen; keine Musik. {SFX}\n\n"
        "#fideTest #DeutschSchweiz #DeutschLernen #Hörverstehen #A2Deutsch #B1Deutsch\n")
    assert len(body) <= (5000 if platform == "youtube" else 2200)
    return body


def cover(episode, portrait=False, part=None):
    image = Image.new("RGB", (1080, 1920) if portrait else (1920, 1080), "#edf3ef")
    draw = ImageDraw.Draw(image)
    if portrait:
        for offset, color in ((0, "#dce9df"), (1550, "#d4e2db")):
            draw.polygon([(0, offset + 320), (210, offset + 90), (390, offset + 270),
                          (620, offset + 30), (840, offset + 280), (1080, offset + 100),
                          (1080, offset + 370), (0, offset + 370)], fill=color)
    draw.rounded_rectangle((80, 444, 920, 1254) if portrait else (32, 32, 1888, 1048),
                           radius=32, fill=CREAM, outline=SAGE, width=3)
    regions = []
    for path, box, label in (
        (LOGO, (112, 478, 172, 538) if portrait else (80, 65, 180, 165), "Deutsch Kompass logo"),
        (FLAG, (804, 474, 874, 544) if portrait else (1690, 80, 1810, 200), "Swiss flag")):
        with Image.open(path) as raw:
            art = ImageOps.contain(raw.convert("RGBA"), (box[2] - box[0], box[3] - box[1]),
                                   Image.Resampling.LANCZOS)
            image.paste(art, box[:2], art)
            regions.append({"text": label, "bounds": [box[0], box[1], box[0] + art.width, box[1] + art.height]})
    if portrait:
        assert part is not None
        n1, n2 = PAIRS[part - 1]
        level = "A2" if n1 < 13 else "B1"
        regions += [
            text(image, "Deutsch Kompass", (190, 490), 32, 580, GREEN),
            text(image, "fide A2-B1", (112, 585), 88, 760),
            text(image, "Verstehen", (112, 696), 104, 760, "#982d37"),
            pill(image, f"Video {part}/6", (112, 835, 874, 945), 72, "#982d37"),
            text(image, f"{level} · Aufgaben {n1}–{n2}", (112, 985), 44, 560),
            text(image, TOPICS[part - 1], (112, 1060), 42, 560, GREEN),
            text(image, "Mit Lösungen" if level == "A2" else "Mit Modellantworten",
                 (112, 1130), 40, 560, GREEN),
            text(image, "Verkürzte Übung", (112, 1195), 36, 560)]
        book_box = (730, 1040, 874, 1216)
    else:
        regions += [
            text(image, "Deutsch Kompass", (208, 98), 40, 1000, GREEN),
            text(image, "fide A2-B1", (90, 215), 116, 1130),
            text(image, "Verstehen", (84, 367), 154, 1130, "#982d37")]
        if part is None:
            regions += [
                text(image, "Prüfungssimulation", (90, 568), 88, 1130),
                text(image, "12 Aufgaben · Mit Lösungen", (90, 719), 56, 1130, GREEN),
                pill(image, "Geführte Übung · A2 + B1", (90, 850, 1170, 950), 48)]
        else:
            n1, n2 = PAIRS[part - 1]
            regions += [
                text(image, TOPICS[part - 1], (90, 568), 80, 1130),
                text(image, f"Aufgaben {n1}–{n2} · Verkürzte Übung", (90, 713), 50, 1130, GREEN),
                pill(image, f"Video {part}/6", (90, 820, 1170, 950), 86, "#982d37")]
        book_box = (1330, 290, 1730, 890)
    book_path = (EPISODE.parent / episode["promotion"]["cover"]).resolve(strict=True)
    with Image.open(book_path) as raw:
        book = ImageOps.contain(raw.convert("RGB"), (book_box[2] - book_box[0], book_box[3] - book_box[1]),
                               Image.Resampling.LANCZOS)
        xy = (book_box[0] + (book_box[2] - book_box[0] - book.width) // 2, book_box[1])
        image.paste(book, xy)
        regions.append({"text": "Book cover", "bounds": [*xy, xy[0] + book.width, xy[1] + book.height]})
    for index, first in enumerate(regions):
        bounds = first["bounds"]
        if portrait:
            assert contains(SAFE, bounds), first
            assert all(contains(box, bounds) for box in CROPS.values()), first
        for other in regions[index + 1:]:
            b = other["bounds"]
            assert min(bounds[2], b[2]) <= max(bounds[0], b[0]) or min(bounds[3], b[3]) <= max(bounds[1], b[1]), (first, other)
    return image, {"size": list(image.size), "regions": regions,
                   "safe_bounds": list(SAFE) if portrait else None,
                   "center_crops": CROPS if portrait else {}, "new_ai_image_generation": False}


def verify_delivery(build):
    manifest = read(build / "delivery_manifest.json")
    verify_files({str(build / name): digest for name, digest in manifest["files"].items()})
    verify_files(manifest["code_inputs"])
    return manifest


def publish(full, short, output):
    if output.exists():
        raise ValueError("Use a fresh posts directory.")
    full_manifest, short_manifest = verify_delivery(full), verify_delivery(short)
    assert Path(short_manifest["source"]) == full
    assert short_manifest["source_manifest_sha256"] == sha256_file(full / "delivery_manifest.json")
    episode = read(full / "sample_content.json")["episode"]
    output.mkdir(parents=True)
    layouts, videos, previews = {}, {}, []
    for part in (None, 1, 2, 3, 4, 5, 6):
        name = "full" if part is None else f"clip_{part}"
        folder = output / name
        folder.mkdir()
        build = full if part is None else short / name
        timeline = read(build / "timeline.json")
        platforms = ("youtube",) if part is None else ("youtube", "instagram", "tiktok")
        for platform in platforms:
            (folder / f"{platform}.txt").write_text(caption(platform, episode, timeline, part), encoding="utf-8")
        for platform in (("youtube",) if part is None else ("youtube", "instagram")):
            image, report = cover(episode, platform == "instagram", part)
            image.save(folder / f"thumbnail_{platform}.jpg", quality=94, subsampling=0)
            layouts[f"{name}/{platform}"] = report
        if part is None:
            video = full / "production_landscape.mp4"
            assert sha256_file(video) == full_manifest["outputs"]["landscape"]["sha256"]
        else:
            assert timeline["selected_numbers"] == list(PAIRS[part - 1])
            video = build / "production_portrait.mp4"
            assert sha256_file(video) == short_manifest["files"][str(video.relative_to(short))]
        videos[str(video)] = sha256_file(video)
        preview = Image.open(folder / ("thumbnail_youtube.jpg" if part is None else "thumbnail_instagram.jpg"))
        if part is None:
            preview.thumbnail((630, 355))
        else:
            preview = preview.crop(CROPS["square"]).resize((360, 360), Image.Resampling.LANCZOS)
            crop_sheet = Image.new("RGB", (1080, 530), "#edf3ef")
            for index, (label, box) in enumerate(CROPS.items()):
                crop = Image.open(folder / "thumbnail_instagram.jpg").crop(box)
                crop.thumbnail((350, 480), Image.Resampling.LANCZOS)
                crop_sheet.paste(crop, (index * 360, 0))
                ImageDraw.Draw(crop_sheet).text((index * 360 + 12, 495), label, fill=INK)
            crop_sheet.save(folder / "crop_preview.jpg", quality=94)
        previews.append((name, preview))
    sheet = Image.new("RGB", (1440, 1160), "#edf3ef")
    for index, (name, preview) in enumerate(previews):
        xy = (0, 0) if index == 0 else (((index - 1) % 3) * 480, 390 + ((index - 1) // 3) * 385)
        sheet.paste(preview, xy)
        ImageDraw.Draw(sheet).text((xy[0] + 8, xy[1] + preview.height + 5), name, fill=INK)
    sheet.save(output / "thumbnail_contact_sheet.jpg", quality=94)
    atomic_json(output / "layout_checks.json", layouts)
    atomic_json(output / "safe_zone_notes.json", {
        "design_safe_rectangle": list(SAFE), "canvas": [1080, 1920], "tested_center_crops": CROPS,
        "policy": "Conservative design bounds, not a universal Instagram interface guarantee. Use centered cover positioning.",
        "official_pages_attempted_2026_11_17": [
            "https://www.facebook.com/help/instagram/1038071743007909",
            "https://www.facebook.com/business/help/980593475366490"],
        "official_page_result": "Login/temporarily-blocked pages; no current numeric Meta safe-zone specification verified."})
    paths = [full / "delivery_manifest.json", short / "delivery_manifest.json",
             full / "timeline.json", full / "sample_content.json", Path(__file__),
             ROOT / "publication_assets.py", ROOT / "publish_fide_assets.py",
             ROOT / "prepare_fide.py", FONT, LOGO, FLAG,
             (EPISODE.parent / episode["promotion"]["cover"]).resolve()]
    paths += [short / f"clip_{n}" / "timeline.json" for n in range(1, 7)]
    assets = {str(p.relative_to(output)): sha256_file(p) for p in output.rglob("*") if p.is_file()}
    atomic_json(output / "publication_manifest.json", {
        "full_build": str(full), "short_build": str(short),
        "inputs": {str(p): sha256_file(p) for p in paths}, "videos": videos, "assets": assets,
        "description_count": 19, "thumbnail_count": 13, "uploaded": False})
    verify_files({str(output / name): digest for name, digest in assets.items()})
    print(f"Ready: 19 descriptions, 13 covers and crop previews in {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", required=True, type=Path)
    parser.add_argument("--short", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    publish(args.full.resolve(), args.short.resolve(), args.output.resolve())
