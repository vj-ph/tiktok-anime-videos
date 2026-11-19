import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

HERE = Path(__file__).resolve().parent
BUILD = HERE.parent / "build/winter-v7"
SIZE = (1080, 1920)
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
GOLD = "#ffda99"
CREAM = "#fff2dd"


def font(size, serif=False):
    family = "DejaVuSerif" if serif else "DejaVuSans"
    return ImageFont.truetype(str(FONT_DIR / f"{family}-Bold.ttf"), size)


def make_cover(background, safe):
    foreground = Image.new("RGBA", SIZE)
    draw = ImageDraw.Draw(foreground)
    draw.rounded_rectangle((131, 529, 819, 1170), 43, fill="#291a24ee", outline="#eab87a", width=4)
    draw.text((475, 625), "DTZ B1", font=font(90, serif=True), fill=CREAM, anchor="mm")
    draw.text((475, 725), "Advent-Übungen", font=font(65, serif=True), fill=GOLD, anchor="mm")
    draw.text((475, 808), "2 Wochen Prüfungstraining", font=font(35), fill=CREAM, anchor="mm")
    for day in range(1, 15):
        row, column = divmod(day - 1, 7)
        x, y = 247 + column * 66, 872 + row * 61
        fill = "#6b3039" if row == 0 else "#285044"
        draw.rounded_rectangle((x, y, x + 60, y + 51), 8, fill=fill, outline="#ad7958", width=2)
        draw.text((x + 30, y + 26), str(day), font=font(23), fill=CREAM, anchor="mm")
    draw.rounded_rectangle((218, 1028, 732, 1118), 22, fill=GOLD)
    draw.text((475, 1073), "1.–14. DEZEMBER 2026", font=font(34), fill="#39231e", anchor="mm")

    box = foreground.getbbox()
    x0, y0, x1, y1 = box
    crops = {
        "video_safe_area": safe,
        "cover_safe_area": [110, 510, 835, 1200],
        "square": [0, 420, 1080, 1500],
        "4:5": [0, 285, 1080, 1635],
        "3:4": [0, 240, 1080, 1680],
        "zoomed_square": [54, 474, 1026, 1446],
    }
    for name, (left, top, right, bottom) in crops.items():
        if not (left <= x0 < x1 <= right and top <= y0 < y1 <= bottom):
            raise ValueError(f"{name} cuts off foreground {box}")
    return Image.alpha_composite(background, foreground).convert("RGB"), box


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=HERE)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    with Image.open(BUILD / "market.jpg") as photo:
        background = ImageEnhance.Brightness(ImageOps.fit(photo.convert("RGB"), SIZE)).enhance(.58).convert("RGBA")
    safe = json.loads((BUILD / "alignment.json").read_text())["safe_rect"]
    report = {}
    cover, box = make_cover(background, safe)
    for platform in ("instagram", "tiktok", "youtube-shorts"):
        path = args.out / f"{platform}-cover.jpg"
        cover.save(path, quality=92, optimize=True, subsampling=0)
        with Image.open(path) as encoded:
            encoded.load()
            if encoded.size != SIZE or encoded.format != "JPEG" or path.stat().st_size >= 2_000_000:
                raise ValueError(f"Bad cover export: {path}")
        report[path.name] = {"foreground": box, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
