import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path("/home/ronggong/lang/german/tiktok_anime_videos")
OUT = ROOT / "posts/tef_canada_listening_01_publishing_r2"
FULL = ROOT / "listening_2d/builds/tef_canada_listening_01_inline_chime_r1"
SPLIT = ROOT / "listening_2d/builds/tef_canada_listening_01_social_six_r2"
ASSETS = FULL / "landscape/assets"
BASE_TITLE = "TEF Canada | Compréhension orale | Simulation d’examen corrigée"
RED, INK, PAPER = "#b51f32", "#112f43", "#faf6f0"
GEOMETRY = {}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def paste(image, path, box):
    with Image.open(path) as source:
        layer = source.convert("RGBA")
    layer.thumbnail(box[2:], Image.Resampling.LANCZOS)
    image.paste(layer, box[:2], layer)


def cover(target, portrait, part, topic, numbers):
    size = (1080, 1920) if portrait else (1280, 720)
    image = Image.new("RGB", size, PAPER)
    draw = ImageDraw.Draw(image)
    boxes = []
    draw.rectangle((0, 0, 19, size[1]), fill=RED)

    def text(value, x, y, font_size, width, color=INK, bold=True, critical=False):
        while True:
            font = ImageFont.truetype(str(ASSETS / ("arialbd.ttf" if bold else "arial.ttf")), font_size)
            box = draw.textbbox((x, y), value, font=font, anchor="lt")
            if box[2] - x <= width:
                break
            font_size -= 1
            if font_size < 24:
                raise ValueError(f"Text will not fit: {value}")
        assert 0 <= box[0] < box[2] <= size[0] and 0 <= box[1] < box[3] <= size[1]
        if portrait and critical:
            assert box[0] >= 100 and box[2] <= 980 and 420 <= box[1] < box[3] <= 1500
        draw.text((x, y), value, font=font, fill=color, anchor="lt")
        boxes.append({"text": value, "bounds": box, "font_size": font_size, "critical": critical})

    badge = f"PARTIE {part}/6" if part else "16 QUESTIONS"
    span = f"Questions {numbers[0]}–{numbers[-1]}"
    if portrait:
        paste(image, ASSETS / "logo.png", (110, 300, 225, 75))
        paste(image, ASSETS / "flag.png", (790, 454, 160, 80))
        text("TEF Canada", 110, 440, 96, 650, critical=True)
        text("Compréhension", 110, 590, 78, 840, critical=True)
        text("orale", 110, 690, 78, 840, critical=True)
        draw.rounded_rectangle((110, 806, 960, 896), radius=16, fill=RED)
        text("SIMULATION D’EXAMEN", 138, 831, 48, 790, "white", critical=True)
        draw.rounded_rectangle((110, 940, 490, 1026), radius=14, outline=RED, width=3)
        text(badge, 138, 964, 46, 330, RED, critical=True)
        text(topic, 110, 1080, 45, 840, critical=True)
        text(span, 110, 1170, 38, 800, bold=False, critical=True)
        paste(image, FULL / "source_artwork/book_cover.png", (760, 1240, 160, 240))
        text("Avec le livre", 110, 1300, 33, 580, bold=False)
        text("French Compass", 110, 1355, 43, 590, RED)
        text("Entraînement indépendant", 110, 1450, 28, 590, bold=False)
        draw.rectangle((20, 1620, 1079, 1720), fill=RED)
        text("VERSION COURTE · CORRIGÉS INCLUS", 110, 1655, 37, 850, "white")
    else:
        paste(image, ASSETS / "logo.png", (60, 35, 205, 68))
        paste(image, ASSETS / "flag.png", (1036, 32, 184, 92))
        text("TEF Canada", 60, 133, 94, 800, critical=True)
        text("Compréhension", 60, 255, 68, 800, critical=True)
        text("orale", 60, 337, 68, 800, critical=True)
        draw.rounded_rectangle((60, 429, 860, 494), radius=12, fill=RED)
        text("SIMULATION D’EXAMEN", 82, 446, 39, 756, "white", critical=True)
        text(topic, 64, 522, 34, 800, critical=True)
        draw.rounded_rectangle((60, 582, 395, 638), radius=10, outline=RED, width=2)
        text(badge, 80, 597, 31, 295, RED, critical=True)
        text(span if part else "Version réduite", 420, 600, 27, 430, bold=False)
        draw.rounded_rectangle((910, 171, 1205, 602), radius=14, fill="#e6dfd5")
        paste(image, FULL / "source_artwork/book_cover.png", (925, 184, 265, 398))
        text("FRENCH COMPASS", 931, 617, 23, 280, RED)
        draw.rectangle((20, 661, 1279, 719), fill=RED)
        text("CORRIGÉS APRÈS CHAQUE EXERCICE", 64, 679, 30, 1150, "white")
    image.save(target, quality=94, subsampling=0)
    assert target.stat().st_size < 2_000_000
    with Image.open(target) as encoded:
        assert encoded.size == size and encoded.format == "JPEG"
        encoded.verify()
    GEOMETRY[str(target.relative_to(OUT))] = boxes


def contact_sheet(paths, target, portrait):
    tile = (360, 640) if portrait else (640, 360)
    columns = 3 if portrait else 2
    rows = (len(paths) + columns - 1) // columns
    sheet = Image.new("RGB", (tile[0] * columns, (tile[1] + 30) * rows), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(str(ASSETS / "arial.ttf"), 18)
    for index, path in enumerate(paths):
        x, y = index % columns * tile[0], index // columns * (tile[1] + 30)
        draw.text((x + 8, y + 5), path.parent.name, font=font, fill=INK)
        with Image.open(path) as image:
            sheet.paste(ImageOps.contain(image, tile), (x, y + 30))
    sheet.save(target, quality=94)


assert not OUT.exists(), "Use a fresh publishing revision."
OUT.mkdir()
archive = OUT / "generation_sources"
archive.mkdir()
shutil.copyfile(__file__, archive / Path(__file__).name)
inputs = {}
for path in (
    FULL / "source_artwork/book_cover.png",
    ASSETS / "flag.png", ASSETS / "flag-provenance.json",
    ASSETS / "logo.png", ASSETS / "logo-provenance.txt",
    ASSETS / "arial.ttf", ASSETS / "arialbd.ttf", ASSETS / "font-license.txt",
    FULL / "delivery_manifest.json", SPLIT / "delivery_manifest.json",
):
    inputs[str(path.relative_to(ROOT))] = sha(path)
    shutil.copyfile(path, archive / path.name if path.name != "delivery_manifest.json" else archive / (path.parent.name + "_manifest.json"))

entries, youtube_covers, instagram_covers = [], [], []
parts = read(SPLIT / "reels.json")["exports"]
for number in range(7):
    folder = OUT / ("youtube_full" if number == 0 else f"part_{number:02d}")
    folder.mkdir()
    title = BASE_TITLE + (" – 16 questions" if number == 0 else f" – Partie {number}/6")
    assert len(title) <= 100
    (folder / "title.txt").write_text(title + "\n", encoding="utf-8")
    if number == 0:
        original = ROOT / "posts/tef_canada_listening_01_inline_chime/youtube.txt"
        body = original.read_text(encoding="utf-8").split("\n", 1)[1].lstrip()
        body = body.replace("Entraînement guidé couvrant", "Simulation d’examen corrigée, en version réduite, couvrant", 1)
        topic, numbers = "8 types d’écoute · Version réduite", list(range(1, 17))
        video = FULL / "preview_landscape.mp4"
        expected = read(FULL / "delivery_manifest.json")["files"]["preview_landscape.mp4"]
    else:
        original = ROOT / f"posts/tef_canada_listening_01_social_six/part_{number:02d}/instagram.txt"
        body = original.read_text(encoding="utf-8").split("\n", 1)[1].lstrip()
        edit = read(SPLIT / f"part_{number:02d}/edit_decisions.json")
        topic = edit["part"]["label"]
        numbers = edit["numbers"]
        body = topic + "\n" + body
        video = SPLIT / parts[number - 1]["file"]
        expected = parts[number - 1]["sha256"]
    assert sha(video) == expected
    inputs[str(original.relative_to(ROOT))] = sha(original)
    shutil.copyfile(original, archive / f"{folder.name}_original_description.txt")
    description = title + "\n\n" + body
    assert all(value in description for value in ("https://a.co/d/013rkncS", "Publicité", "IA", "indépendante", "Mixkit"))
    assert "examen officiel complet" in description
    assert len(description) < 5000
    (folder / "youtube.txt").write_text(description, encoding="utf-8")
    if number:
        assert len(description) < 2200
        (folder / "instagram.txt").write_text(description, encoding="utf-8")
        portrait = folder / "thumbnail_instagram.jpg"
        cover(portrait, True, number, topic, numbers)
        instagram_covers.append(portrait)
    wide = folder / "thumbnail_youtube.jpg"
    cover(wide, False, number, topic, numbers)
    youtube_covers.append(wide)
    entries.append({
        "id": folder.name, "title": title, "title_characters": len(title),
        "description_characters": len(description), "questions": numbers,
        "video": str(video.relative_to(ROOT)), "video_sha256": expected,
        "youtube_description": str((folder / "youtube.txt").relative_to(OUT)),
        "youtube_thumbnail": str(wide.relative_to(OUT)),
        "instagram_description": f"{folder.name}/instagram.txt" if number else None,
        "instagram_thumbnail": f"{folder.name}/thumbnail_instagram.jpg" if number else None,
    })

contact_sheet(youtube_covers, OUT / "review_youtube.jpg", False)
contact_sheet(instagram_covers, OUT / "review_instagram.jpg", True)
for path, expected in inputs.items():
    assert sha(ROOT / path) == expected, f"Original input changed: {path}"
save(OUT / "publishing_index.json", {
    "edition": "Canadian-themed exam-simulation posting assets, revision 2",
    "entries": entries, "input_hashes": inputs, "text_geometry": GEOMETRY,
    "visual_inspection": False, "publication": False,
    "notes": "New promotional compositions, not replacement video frames. Existing full and split videos, frozen manifests and previous posts remain unchanged. Simulation is explicitly reduced guided practice with immediate corrections.",
})
print(f"Generated {len(youtube_covers)} YouTube and {len(instagram_covers)} Instagram covers.")
print(f"Posting descriptions and titles: {OUT}")
