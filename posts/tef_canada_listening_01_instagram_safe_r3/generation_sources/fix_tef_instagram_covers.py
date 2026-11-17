import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps


ROOT = Path("/home/ronggong/lang/german/tiktok_anime_videos")
SOURCE = ROOT / "posts/tef_canada_listening_01_publishing_r2"
OUT = ROOT / "posts/tef_canada_listening_01_instagram_safe_r3"
ASSETS = SOURCE / "generation_sources"
SIZE = (1080, 1920)
SAFE = (100, 480, 850, 1130)
CROPS = {
    "grid_3x4": (0, 240, 1080, 1680),
    "feed_4x5": (0, 285, 1080, 1635),
    "square": (0, 420, 1080, 1500),
    "square_zoom10": (49, 469, 1031, 1451),
}
UI_MASKS = {
    "top": (0, 0, 1080, 300),
    "bottom": (0, 1152, 1080, 1920),
    "right": (850, 300, 1080, 1920),
    "left": (0, 0, 65, 1920),
}
RED, INK, PAPER = "#b51f32", "#112f43", "#faf6f0"


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


def contains(outer, inner):
    return outer[0] <= inner[0] < inner[2] <= outer[2] and outer[1] <= inner[1] < inner[3] <= outer[3]


def font(size, bold=True):
    return ImageFont.truetype(str(ASSETS / ("arialbd.ttf" if bold else "arial.ttf")), size)


def audit(alpha):
    bounds = alpha.getbbox()
    if bounds is None or not contains(SAFE, bounds):
        raise ValueError(f"Foreground outside conservative region: {bounds}")
    count = alpha.point(lambda value: 255 if value else 0).histogram()[255]
    for name, crop in CROPS.items():
        if not contains(crop, bounds):
            raise ValueError(f"Foreground clipped by {name}")
        if alpha.crop(crop).point(lambda value: 255 if value else 0).histogram()[255] != count:
            raise ValueError(f"Foreground pixels lost in {name}")
    for name, box in UI_MASKS.items():
        mask = Image.new("L", SIZE)
        ImageDraw.Draw(mask).rectangle(box, fill=255)
        if ImageChops.multiply(alpha, mask).getbbox():
            raise ValueError(f"Foreground overlaps {name} UI stress mask")
    return {"foreground_bounds": bounds, "foreground_pixels": count,
            "safe_box": SAFE, "pixel_preserving_crops": list(CROPS),
            "zero_overlap_ui_masks": list(UI_MASKS)}


def selftests():
    valid = Image.new("L", SIZE)
    ImageDraw.Draw(valid).rectangle((120, 500, 840, 1110), fill=255)
    audit(valid)
    for box in ((790, 454, 950, 534), (760, 1240, 920, 1480),
                (110, 1655, 960, 1695), (110, 300, 185, 375)):
        invalid = valid.copy()
        ImageDraw.Draw(invalid).rectangle(box, fill=255)
        try:
            audit(invalid)
        except ValueError:
            continue
        raise AssertionError(f"Failed to reject old unsafe placement: {box}")


def render(number, topic, questions):
    background = Image.new("RGBA", SIZE, PAPER)
    ImageDraw.Draw(background).rectangle((0, 0, 19, 1919), fill=RED)
    layer = Image.new("RGBA", SIZE)
    draw = ImageDraw.Draw(layer)
    records = []

    def text(value, x, y, size, width, color=INK, bold=True):
        face = font(size, bold)
        box = draw.textbbox((x, y), value, font=face, anchor="lt")
        if box[2] - x > width or not contains(SAFE, box):
            raise ValueError(f"Text does not fit: {value}")
        draw.text((x, y), value, font=face, fill=color, anchor="lt")
        records.append({"kind": "text", "text": value, "bounds": box, "font_size": size})

    def picture(name, x, y, width, height):
        with Image.open(ASSETS / name) as original:
            image = original.convert("RGBA")
        image.thumbnail((width, height), Image.Resampling.LANCZOS)
        bounds = (x, y, x + image.width, y + image.height)
        if not contains(SAFE, bounds):
            raise ValueError(f"Artwork does not fit: {name}")
        layer.alpha_composite(image, (x, y))
        records.append({"kind": "artwork", "file": name, "bounds": bounds})

    picture("logo.png", 120, 500, 52, 52)
    text("French Compass", 190, 515, 25, 490, RED)
    picture("flag.png", 720, 500, 120, 60)
    text("TEF Canada", 120, 580, 78, 720)
    text("Compréhension orale", 120, 675, 54, 720)
    draw.rounded_rectangle((120, 755, 840, 815), radius=12, fill=RED)
    records.append({"kind": "panel", "bounds": (120, 755, 841, 816)})
    text("SIMULATION D’EXAMEN", 140, 771, 39, 680, "white")
    draw.rounded_rectangle((120, 842, 412, 902), radius=10, outline=RED, width=3)
    records.append({"kind": "panel", "bounds": (120, 842, 413, 903)})
    text(f"PARTIE {number}/6", 140, 857, 38, 252, RED)
    text(f"Questions {questions[0]}–{questions[-1]}", 440, 860, 30, 390, bold=False)
    words, lines, line = topic.split(), [], ""
    for word in words:
        candidate = (line + " " + word).strip()
        if draw.textbbox((0, 0), candidate, font=font(34))[2] > 555:
            if not line:
                raise ValueError("Topic contains an overlong word.")
            lines.append(line)
            line = word
        else:
            line = candidate
    lines.append(line)
    if len(lines) > 2 or " ".join(lines) != topic:
        raise ValueError("Topic must fit intact on at most two lines.")
    for index, value in enumerate(lines):
        text(value, 120, 935 + index * 44, 34, 555)
    picture("book_cover.png", 720, 935, 112, 168)
    text("Version courte · Corrigés inclus", 120, 1040, 26, 570, RED)
    text("Entraînement indépendant", 120, 1090, 23, 570, bold=False)
    for index, item in enumerate(records):
        if item["kind"] == "panel":
            continue
        for other in records[index + 1:]:
            if other["kind"] == "panel":
                continue
            a, b = item["bounds"], other["bounds"]
            if max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3]):
                raise ValueError(f"Foreground elements overlap: {item}, {other}")
    check = audit(layer.getchannel("A"))
    image = Image.alpha_composite(background, layer).convert("RGB")
    return image, {"elements": records, **check}


def review_sheet(items, target, columns, tile):
    rows = (len(items) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * tile[0], rows * (tile[1] + 35)), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (label, path) in enumerate(items):
        x, y = index % columns * tile[0], index // columns * (tile[1] + 35)
        draw.text((x + 5, y + 6), label, font=font(17, False), fill=INK)
        with Image.open(path) as source:
            preview = ImageOps.contain(source.convert("RGB"), tile, Image.Resampling.LANCZOS)
        sheet.paste(preview, (x + (tile[0] - preview.width) // 2, y + 32))
    sheet.save(target, quality=95)


selftests()
old_manifest = read(SOURCE / "publishing_manifest.json")
for relative, expected in old_manifest["files"].items():
    if sha(SOURCE / relative) != expected:
        raise ValueError(f"Earlier publishing revision changed: {relative}")
assert not OUT.exists(), "Use a fresh output directory."
OUT.mkdir()
archive = OUT / "generation_sources"
archive.mkdir()
shutil.copyfile(__file__, archive / Path(__file__).name)
for name in ("logo.png", "flag.png", "book_cover.png", "arial.ttf", "arialbd.ttf",
             "font-license.txt", "flag-provenance.json", "logo-provenance.txt"):
    shutil.copyfile(ASSETS / name, archive / name)
shutil.copyfile(SOURCE / "publishing_manifest.json", archive / "publishing_r2_manifest.json")
index = read(SOURCE / "publishing_index.json")
outputs, full_reviews, ui_reviews = [], [], []
crop_reviews = [[], []]
for entry in index["entries"]:
    if not entry["instagram_thumbnail"]:
        continue
    number = int(entry["id"].split("_")[1])
    target = OUT / entry["id"]
    target.mkdir()
    for name in ("title.txt", "instagram.txt"):
        shutil.copyfile(SOURCE / entry["id"] / name, target / name)
    caption = (target / "instagram.txt").read_text(encoding="utf-8")
    topic = caption.splitlines()[2]
    image, check = render(number, topic, entry["questions"])
    cover = target / "thumbnail_instagram.jpg"
    image.save(cover, quality=95, subsampling=0)
    assert cover.stat().st_size < 2_000_000
    with Image.open(cover) as encoded:
        assert encoded.size == SIZE and encoded.format == "JPEG"
        image = encoded.convert("RGB")
    proof = OUT / "proofs" / entry["id"]
    proof.mkdir(parents=True)
    for name, box in CROPS.items():
        path = proof / f"{name}.jpg"
        image.crop(box).save(path, quality=95)
        crop_reviews[(number - 1) // 3].append((f"{number}/6 {name}", path))
    overlay = image.convert("RGBA")
    ui = Image.new("RGBA", SIZE)
    draw = ImageDraw.Draw(ui)
    for box in UI_MASKS.values():
        draw.rectangle(box, fill=(30, 35, 40, 190))
    draw.rectangle(SAFE, outline=(0, 140, 60, 255), width=3)
    overlay = Image.alpha_composite(overlay, ui).convert("RGB")
    path = proof / "conservative_ui_overlay.jpg"
    overlay.save(path, quality=95)
    ui_reviews.append((f"Part {number}: test UI mask", path))
    full_reviews.append((f"Part {number}: upload cover", cover))
    old_boxes = index["text_geometry"][f"{entry['id']}/thumbnail_instagram.jpg"]
    outputs.append({
        "part": number, "file": str(cover.relative_to(OUT)), "sha256": sha(cover),
        "title": entry["title"], "topic": topic, "questions": entry["questions"],
        "source_video": entry["video"], "source_video_sha256": entry["video_sha256"],
        "old_text_outside_new_region": [item for item in old_boxes if not contains(SAFE, item["bounds"])],
        **check,
    })
assert len(outputs) == 6
review_sheet(full_reviews, OUT / "review_full.jpg", 3, (270, 480))
review_sheet(ui_reviews, OUT / "review_ui.jpg", 3, (270, 480))
for number, items in enumerate(crop_reviews, 1):
    review_sheet(items, OUT / f"review_crops_{number:02d}.jpg", 4, (270, 360))
for relative, expected in old_manifest["files"].items():
    assert sha(SOURCE / relative) == expected
save(OUT / "safe_zone_checks.json", {
    "canvas": SIZE, "conservative_foreground_region": SAFE,
    "crop_tests": CROPS, "ui_stress_masks": UI_MASKS, "outputs": outputs,
    "all_foreground_checked": "Every text, panel, logo, flag and book pixel; only background decoration may bleed.",
    "negative_controls": "Old flag, logo, book and footer placements each fail the raster audit.",
    "source_publishing_manifest_sha256": sha(SOURCE / "publishing_manifest.json"),
    "original_54_publishing_files_unchanged": True, "visual_inspection": False,
    "reference_check": {
        "status": "Meta primary help/ads pages redirected to login or returned HTTP 429; no exact current official safe-zone claim.",
        "urls": ["https://www.facebook.com/business/help/980593475366490",
                 "https://www.facebook.com/business/ads-guide/update/video/instagram-reels/outcome-engagement",
                 "https://help.instagram.com/1038071743007909"],
        "policy": "Conservative project-owned crop and UI stress tests, not app screenshots or universal Instagram UI certification.",
    },
    "videos_changed": False, "youtube_assets_changed": False, "publication": False,
})
print(f"Generated and raster-audited six Instagram covers: {OUT}")
