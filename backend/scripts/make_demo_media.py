"""Generate six renovation-stage images of the same kitchen wall (fixed camera).

stage_0 bare studs → stage_1 drywall → stage_2 painted → stage_3 base cabinets
→ stage_4 countertop + uppers → stage_5 backsplash, lights, finished floor.

Used in DEMO_MODE as the morning/evening snapshots (the Ring sandbox serves one
still for every timestamp). Replace with real photos if you have them.

Note: demo_media/ now holds Unsplash photos (see demo_media/CREDITS.md). Running this
script overwrites them with drawings; the drawn originals are also kept in demo_media/drawn/.

    python scripts/make_demo_media.py
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

W, H = 960, 600
FLOOR_Y = 470
OUT = Path(__file__).resolve().parent.parent / "demo_media"


def _wall(d: ImageDraw.ImageDraw, stage: int) -> None:
    if stage == 0:
        d.rectangle([0, 0, W, FLOOR_Y], fill=(58, 52, 46))  # dark cavity
        for x in range(30, W, 64):  # studs
            d.rectangle([x, 20, x + 14, FLOOR_Y], fill=(196, 160, 112), outline=(150, 118, 78))
        d.rectangle([0, 10, W, 26], fill=(186, 150, 104))  # top plate
        d.rectangle([0, FLOOR_Y - 14, W, FLOOR_Y], fill=(186, 150, 104))  # bottom plate
        d.line([(80, 140), (420, 140), (420, 300), (700, 300)], fill=(220, 200, 40), width=5)  # wiring
        d.line([(500, 26), (500, 220)], fill=(190, 110, 60), width=8)  # copper pipe
        for bx in (240, 620):
            d.rectangle([bx, 280, bx + 26, 316], fill=(70, 120, 200))  # electrical boxes
    elif stage == 1:
        d.rectangle([0, 0, W, FLOOR_Y], fill=(186, 188, 186))
        for x in range(0, W, 240):
            d.line([(x, 0), (x, FLOOR_Y)], fill=(236, 236, 230), width=10)  # taped seams
        d.line([(0, 240), (W, 240)], fill=(236, 236, 230), width=10)
        for x in range(60, W, 120):
            for y in (60, 180, 300, 420):
                d.ellipse([x, y, x + 6, y + 6], fill=(236, 236, 230))  # screw mud
    else:
        d.rectangle([0, 0, W, FLOOR_Y], fill=(236, 230, 214))


def _floor(d: ImageDraw.ImageDraw, stage: int, rng: random.Random) -> None:
    if stage < 5:
        d.rectangle([0, FLOOR_Y, W, H], fill=(176, 146, 100))  # subfloor plywood
        for x in range(0, W, 240):
            d.line([(x, FLOOR_Y), (x, H)], fill=(140, 112, 72), width=2)
    else:
        for i, x in enumerate(range(0, W, 80)):
            tone = 110 + (i % 3) * 12
            d.rectangle([x, FLOOR_Y, x + 80, H], fill=(tone, tone - 34, tone - 70))
            d.line([(x, FLOOR_Y), (x, H)], fill=(80, 56, 36), width=2)
    if stage == 0:  # debris
        for _ in range(26):
            x, y = rng.randint(20, W - 60), rng.randint(FLOOR_Y + 10, H - 20)
            d.rectangle([x, y, x + rng.randint(14, 50), y + rng.randint(4, 10)], fill=(120, 110, 100))
        d.rectangle([700, FLOOR_Y + 30, 900, FLOOR_Y + 110], fill=(70, 70, 76))  # dumpster bag


def _cabinets(d: ImageDraw.ImageDraw, stage: int) -> None:
    if stage >= 3:  # base cabinets
        top = 330
        d.rectangle([60, top, 900, FLOOR_Y], fill=(52, 76, 98))
        for x in range(60, 900, 140):
            d.rectangle([x + 6, top + 10, x + 134, FLOOR_Y - 8], outline=(36, 54, 72), width=4)
            d.rectangle([x + 62, top + 24, x + 78, top + 30], fill=(200, 196, 186))  # handles
    if stage >= 4:
        d.rectangle([48, 312, 912, 332], fill=(232, 232, 228))  # quartz top
        d.rectangle([60, 60, 900, 190], fill=(52, 76, 98))  # uppers
        for x in range(60, 900, 140):
            d.rectangle([x + 6, 68, x + 134, 182], outline=(36, 54, 72), width=4)
        d.rectangle([380, 300, 560, 312], fill=(150, 150, 156))  # sink
    if stage >= 5:
        for y in range(190, 312, 22):  # subway tile backsplash
            off = 0 if (y // 22) % 2 else 22
            for x in range(60 - off, 900, 44):
                d.rectangle([max(60, x), y, min(900, x + 42), y + 20], fill=(250, 250, 246), outline=(210, 210, 204))
        for cx in (260, 480, 700):  # pendant lights
            d.line([(cx, 0), (cx, 30)], fill=(30, 30, 30), width=3)
            d.pieslice([cx - 26, 22, cx + 26, 70], 180, 360, fill=(30, 30, 30))
            d.ellipse([cx - 10, 40, cx + 10, 54], fill=(255, 226, 150))
        d.line([(470, 300), (470, 262), (500, 262)], fill=(60, 60, 60), width=6)  # faucet


def _overlay(d: ImageDraw.ImageDraw, stage: int) -> None:
    d.rectangle([0, 0, 250, 26], fill=(0, 0, 0))
    d.text((8, 7), f"KITCHEN CAM  |  demo stage {stage}", fill=(255, 255, 255))


def render(stage: int) -> Image.Image:
    rng = random.Random(stage)
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    _wall(d, stage)
    _floor(d, stage, rng)
    _cabinets(d, stage)
    if stage >= 1:  # tools/materials while work is ongoing
        if stage < 5:
            d.rectangle([780, FLOOR_Y + 20, 860, FLOOR_Y + 90], fill=(240, 180, 40))  # bucket/ladder stand-in
            d.line([(800, FLOOR_Y + 20), (830, 260)], fill=(200, 200, 200), width=6)
            d.line([(850, FLOOR_Y + 20), (870, 260)], fill=(200, 200, 200), width=6)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    _overlay(ImageDraw.Draw(img), stage)
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for s in range(6):
        render(s).save(OUT / f"stage_{s}.png", optimize=True)
    render(5).save(OUT / "default.png", optimize=True)  # ring-sandbox --media-dir fallback still
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
