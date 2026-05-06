#!/usr/bin/env python3
"""
Gera 25 captchas sinteticos com ground truth conhecido.

Cada imagem: texto random (digits / lower / mixed alphanumerico),
fonte e tamanho variavel, rotacao por char, ruido (linhas + speckle).
Determinístico — mesma seed produz mesmas imagens.

Saida:
  evals/gold_images/synth_NNN.png
  evals/synthetic_manifest.json   (consumido por make_gold.py)
"""
from __future__ import annotations

import json
import random
import string
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
OUT = ROOT / "gold_images"
OUT.mkdir(exist_ok=True)
MANIFEST = ROOT / "synthetic_manifest.json"

FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
    "/System/Library/Fonts/Monaco.ttf",
]

CHARSETS = {
    "digits": string.digits,
    "lower": string.ascii_lowercase,
    "mixed": string.ascii_letters + string.digits,
}

W, H = 240, 80
N_SAMPLES = 25
MASTER_SEED = 42


def render(text: str, seed: int) -> Image.Image:
    rnd = random.Random(seed)
    bg_v = rnd.randint(225, 250)
    img = Image.new("RGB", (W, H), (bg_v, bg_v, bg_v))
    draw = ImageDraw.Draw(img)

    for _ in range(rnd.randint(2, 5)):
        x1, y1 = rnd.randint(0, W), rnd.randint(0, H)
        x2, y2 = rnd.randint(0, W), rnd.randint(0, H)
        col = tuple(rnd.randint(80, 180) for _ in range(3))
        draw.line((x1, y1, x2, y2), fill=col, width=rnd.randint(1, 2))

    for _ in range(rnd.randint(60, 120)):
        x, y = rnd.randint(0, W - 1), rnd.randint(0, H - 1)
        col = tuple(rnd.randint(100, 200) for _ in range(3))
        draw.point((x, y), fill=col)

    font_path = rnd.choice([f for f in FONTS if Path(f).exists()])
    font_size = rnd.randint(36, 46)
    font = ImageFont.truetype(font_path, font_size)

    char_w = (W - 30) // len(text)
    for i, ch in enumerate(text):
        ch_img = Image.new("RGBA", (char_w + 30, H), (0, 0, 0, 0))
        ch_draw = ImageDraw.Draw(ch_img)
        col = tuple(rnd.randint(0, 90) for _ in range(3))
        ch_draw.text((10, rnd.randint(8, 22)), ch, font=font, fill=col)
        ch_img = ch_img.rotate(rnd.randint(-18, 18), resample=Image.BICUBIC)
        img.paste(ch_img, (15 + i * char_w, 0), ch_img)

    return img


def main() -> None:
    rnd = random.Random(MASTER_SEED)
    items = []
    for i in range(N_SAMPLES):
        kind = rnd.choice(["digits", "lower", "mixed"])
        length = rnd.randint(4, 7)
        text = "".join(rnd.choices(CHARSETS[kind], k=length))
        seed = rnd.randint(0, 10**9)
        img = render(text, seed)
        path = OUT / f"synth_{i+1:03d}.png"
        img.save(path)
        items.append({
            "path": f"gold_images/{path.name}",
            "expected": text,
            "source": "synthetic",
            "kind": kind,
        })
        print(f"  {path.name}: {text} ({kind}, len={length})")

    MANIFEST.write_text(json.dumps(items, indent=2) + "\n")
    print(f"\n{len(items)} sinteticos -> {MANIFEST.name}")


if __name__ == "__main__":
    main()
