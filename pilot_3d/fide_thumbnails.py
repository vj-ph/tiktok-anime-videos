"""Compose fide thumbnails from verified native stills without changing video builds."""

import argparse
from pathlib import Path
import shutil

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from long_speaking import ACCENT, BG, INK, text_box
from prepare_audio import atomic_json, sha256_file
from revise_fide_book import read

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "builds" / "fide_a2_b1_single_book_r1"
SOURCE_DIGEST = "967b10ca531f51c41b64ebd040f2130e62a5928d89169bd29c029beecc9a005d"
SOCIAL_SAFE = (90, 460, 900, 1240)
SOCIAL_CROPS = {
    "3:4": (0, 240, 1080, 1680),
    "4:5": (0, 285, 1080, 1635),
    "1:1": (0, 420, 1080, 1500),
}
CLIPS = (
    ("video_1_a2", "fide_20", "fide A2 Sprechen", ("Alle drei Aufgaben",)),
    ("video_2_b1_erfahrung_ablauf", "fide_31", "fide B1 Sprechen", ("Erfahrungen", "und Abläufe")),
    ("video_3_b1_meinung", "fide_45", "fide B1 Sprechen", ("Meinung", "und Wünsche")),
)


def contains(outer, inner):
    return outer[0] <= inner[0] < inner[2] <= outer[2] and outer[1] <= inner[1] < inner[3] <= outer[3]


def head_boxes(record, size, crop, destination):
    result = []
    for head in record["head_bounds"]:
        x0, y0, x1, y1 = head["bounds"]
        original = (x0 * size[0], (1 - y1) * size[1],
                    x1 * size[0], (1 - y0) * size[1])
        if not head["in_front"] or not contains(crop, original):
            raise ValueError(f"Thumbnail crop clips a head or hair: {head['actor']}")
        result.append({
            "actor": head["actor"],
            "box": [destination[0] + (original[i] - crop[0]) * (destination[2] - destination[0]) / (crop[2] - crop[0])
                    if i % 2 == 0 else
                    destination[1] + (original[i] - crop[1]) * (destination[3] - destination[1]) / (crop[3] - crop[1])
                    for i in range(4)],
        })
    if not result:
        raise ValueError("A thumbnail needs verified visible faces.")
    return result


def render(native, record, flag, *, index=None, title=None, hooks=()):
    portrait = index is not None
    size = (1080, 1920) if portrait else (1920, 1080)
    image = Image.new("RGB", size, BG)
    draw = ImageDraw.Draw(image)
    checks = []
    if portrait:
        texture = ImageOps.fit(native, size).filter(ImageFilter.GaussianBlur(55))
        image = Image.blend(image, texture, .12)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((88, 444, 908, 1254), radius=30, fill=BG,
                               outline="#37515c", width=2)
        checks.append(text_box(draw, "Deutsch Kompass", (112, 470, 730, 510),
                               size=28, minimum=28, bold=True))
        draw.rounded_rectangle((112, 515, 460, 585), radius=14, fill=ACCENT)
        checks.append(text_box(draw, f"Video {index}/3", (132, 515, 448, 580),
                               size=50, minimum=50, color=BG, bold=True))
        checks.append(text_box(draw, title, (112, 600, 884, 677),
                               size=58, minimum=54, bold=True))
        for line, hook in enumerate(hooks):
            top = 677 + line * 51
            checks.append(text_box(draw, hook, (112, top, 884, top + 59),
                                   size=44, minimum=42, color=ACCENT, bold=True))
        flag_box = (811, 470, 881, 540)
        crop, destination = (280, 0, 920, 352), (112, 800, 884, 1224)
    else:
        checks.append(text_box(draw, "Deutsch Kompass", (80, 25, 1300, 70),
                               size=32, minimum=32, bold=True))
        checks.append(text_box(draw, "fide A2-B1 Sprechen", (80, 88, 1570, 233),
                               size=116, minimum=106, color=ACCENT, bold=True))
        checks.append(text_box(draw, "Prüfungssimulation", (80, 228, 1570, 356),
                               size=98, minimum=92, bold=True))
        flag_box = (1648, 95, 1828, 275)
        crop, destination = (0, 0, native.width, 458), (0, 356, 1920, 1080)
    heads = head_boxes(record, native.size, crop, destination)
    photo = native.crop(crop).resize((destination[2] - destination[0],
                                     destination[3] - destination[1]), Image.Resampling.LANCZOS)
    image.paste(photo, destination[:2])
    if not portrait:
        ImageDraw.Draw(image).rectangle((0, 352, 1919, 355), fill=ACCENT)
    image.paste(flag.resize((flag_box[2] - flag_box[0], flag_box[3] - flag_box[1]),
                           Image.Resampling.LANCZOS), flag_box[:2])
    critical = [c["box"] for c in checks] + [flag_box] + [h["box"] for h in heads]
    if portrait:
        for box in critical:
            if not contains(SOCIAL_SAFE, box) or not all(contains(c, box) for c in SOCIAL_CROPS.values()):
                raise ValueError("Social thumbnail essentials leave the central crop-safe region.")
    return image, {
        "size": list(size), "text": checks, "swiss_flag_box": list(flag_box),
        "heads": heads, "source_crop": list(crop), "scene_box": list(destination),
        "critical_boxes": critical, "safe_box": list(SOCIAL_SAFE) if portrait else None,
        "crop_checks": list(SOCIAL_CROPS) if portrait else [],
    }


def source_still(turn_id, timeline, receipts):
    turn = next(t for t in timeline["turns"] if t["id"] == turn_id)
    frame = turn["start_frame"] + (24 if turn_id != "fide_01" else 0)
    name = f"native/youtube_{frame:05d}.png"
    record = next(r for r in receipts if r["file"].replace("\\", "/") == name)
    path = SOURCE / record["file"]
    if sha256_file(path) != record["sha256"]:
        raise ValueError("A source still changed.")
    with Image.open(path) as original:
        image = original.convert("RGB")
    return image, record, path


def build(posts):
    manifest_path = SOURCE / "export_manifest.json"
    if sha256_file(manifest_path) != SOURCE_DIGEST:
        raise ValueError("Use the approved single-book fide source delivery.")
    manifest = read(manifest_path)
    for name in ("timeline.json", "native_reuse.json"):
        if sha256_file(SOURCE / name) != manifest["files_sha256"][name]:
            raise ValueError(f"Source input changed: {name}")
    timeline, receipts = read(SOURCE / "timeline.json"), read(SOURCE / "native_reuse.json")
    flag_path = ROOT / "assets" / "flags" / "switzerland.png"
    provenance = read(flag_path.parent / "provenance.json")["switzerland.png"]
    if sha256_file(flag_path) != provenance["sha256"]:
        raise ValueError("Swiss flag asset changed.")
    with Image.open(flag_path) as original:
        flag = original.convert("RGB")
    outputs, stills, images = [], {}, []

    def save(image, check, relative, source_path):
        path = posts / relative
        if path.exists():
            raise ValueError(f"Preserve existing thumbnails; select a fresh --posts root: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, quality=95, subsampling=0)
        with Image.open(path) as saved:
            saved.load()
            if saved.size != tuple(check["size"]) or path.stat().st_size >= 2_000_000:
                raise ValueError("Thumbnail dimensions or conservative upload-size budget failed.")
        outputs.append({"file": str(relative), "sha256": sha256_file(path), **check})
        stills[str(source_path)] = sha256_file(source_path)

    native, receipt, path = source_still("fide_01", timeline, receipts)
    image, check = render(native, receipt, flag)
    save(image, check, Path("fide_a2_b1_single_book") / "thumbnail_youtube.jpg", path)
    images.append(image)
    socials = []
    for index, (clip_id, turn_id, title, hooks) in enumerate(CLIPS, 1):
        native, receipt, path = source_still(turn_id, timeline, receipts)
        image, check = render(native, receipt, flag, index=index, title=title, hooks=hooks)
        relative = Path("fide_a2_b1_social_three") / clip_id / "thumbnail_instagram.jpg"
        save(image, check, relative, path)
        tiktok = posts / relative.with_name("thumbnail_tiktok.jpg")
        if tiktok.exists():
            raise ValueError(f"Preserve existing thumbnail: {tiktok}")
        shutil.copy2(posts / relative, tiktok)
        outputs.append({"file": str(tiktok.relative_to(posts)), "sha256": sha256_file(tiktok), **check})
        socials.append(image)
    folder = posts / "fide_a2_b1_social_three"
    sheet = Image.new("RGB", (1200, 950), BG)
    sheet.paste(images[0].resize((720, 405), Image.Resampling.LANCZOS), (240, 20))
    for i, image in enumerate(socials):
        sheet.paste(image.resize((270, 480), Image.Resampling.LANCZOS), (135 + i * 330, 450))
    sheet.save(folder / "thumbnail_contact_sheet.jpg", quality=95)
    preview = Image.new("RGB", (900, 1580), BG)
    draw = ImageDraw.Draw(preview)
    for row, (ratio, crop) in enumerate(SOCIAL_CROPS.items()):
        top = row * 520
        text_box(draw, f"Central {ratio} crop", (20, top + 5, 880, top + 45), size=24, minimum=24)
        for col, image in enumerate(socials):
            fitted = ImageOps.contain(image.crop(crop), (280, 455), Image.Resampling.LANCZOS)
            preview.paste(fitted, (10 + col * 300, top + 55))
    preview.save(folder / "thumbnail_crop_preview.jpg", quality=95)
    for path, digest in stills.items():
        if sha256_file(Path(path)) != digest:
            raise ValueError("Source still changed during thumbnail generation.")
    if sha256_file(manifest_path) != SOURCE_DIGEST:
        raise ValueError("The source delivery manifest changed.")
    atomic_json(folder / "thumbnail_manifest.json", {
        "outputs": outputs, "source_manifest_sha256": SOURCE_DIGEST,
        "source_stills_sha256": stills, "swiss_flag": provenance,
        "generator_sha256": sha256_file(Path(__file__)),
        "social_safety": "Conservative central design region, checked against square, 4:5 and 3:4 crops; not a universal Instagram UI guarantee.",
        "reference_check": "Meta primary help pages were inaccessible; no exact current official safe-zone claim.",
        "original_videos_changed": False, "new_native_rendering": False,
        "publication_approved": False,
    })
    for output in outputs:
        print(posts / output["file"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--posts", type=Path, default=ROOT.parent / "posts")
    args = parser.parse_args()
    build(args.posts.resolve())
