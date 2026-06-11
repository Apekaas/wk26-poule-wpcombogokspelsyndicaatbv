#!/usr/bin/env python3
"""Zet een karikatuur-afbeelding om naar een puntenwolk voor het 3D-podium.

Donkere/getekende pixels worden bemonsterd tot max ~3800 punten. Per punt:
[x, y, z, kleurklasse] met x/y genormaliseerd naar [-1, 1] (y omhoog),
z een kleine willekeurige diepte, en kleurklasse: 0 = huid/lijnwerk (wit),
1 = kuif (geel/blond herkend), 2 = das (rood/blauw herkend).

Gebruik:
    python3 tools/punten_van_afbeelding.py <afbeelding> [data/trump-punten.json]

Werkt het best met een karikatuur op lichte achtergrond. Draai daarna
generate.py opnieuw; het podium gebruikt de puntenwolk automatisch.
"""
import json
import random
import sys
from pathlib import Path

from PIL import Image

MAX_PUNTEN = 3800
MAX_BREEDTE = 170


def kleurklasse(r, g, b):
    """Herken kuif (geel/blond) en das (rood of donkerblauw)."""
    if r > 170 and g > 120 and b < 120:          # geel/blond
        return 1
    if r > 140 and g < 90 and b < 90:            # rood (das)
        return 2
    if b > 110 and b > r + 30 and g < b:          # donkerblauw (das/pak)
        return 2
    return 0


def main(inpad, outpad):
    img = Image.open(inpad).convert("RGB")
    if img.width > MAX_BREEDTE:
        img = img.resize((MAX_BREEDTE, int(img.height * MAX_BREEDTE / img.width)))
    grijs = img.convert("L")
    w, h = img.size
    px, gpx = img.load(), grijs.load()

    kandidaten = []
    for y in range(h):
        for x in range(w):
            donkerte = 255 - gpx[x, y]
            if donkerte < 60:        # (vrijwel) witte achtergrond overslaan
                continue
            kandidaten.append((donkerte, x, y))
    if not kandidaten:
        sys.exit("Geen donkere pixels gevonden — is de afbeelding licht genoeg "
                 "van achtergrond?")

    # gewogen steekproef: donkerder = grotere kans, tot MAX_PUNTEN
    random.seed(2026)
    gewichten = [k[0] for k in kandidaten]
    n = min(MAX_PUNTEN, len(kandidaten))
    gekozen = random.choices(kandidaten, weights=gewichten, k=n)

    schaal = max(w, h) / 2
    cx, cy = w / 2, h / 2
    punten = []
    for _, x, y in gekozen:
        r, g, b = px[x, y]
        punten.append([
            round((x - cx) / schaal, 3),
            round(-(y - cy) / schaal, 3),          # y omhoog
            round(random.uniform(-0.08, 0.08), 3),
            kleurklasse(r, g, b),
        ])
    Path(outpad).parent.mkdir(parents=True, exist_ok=True)
    Path(outpad).write_text(json.dumps(punten, separators=(",", ":")),
                            encoding="utf-8")
    kuif = sum(1 for p in punten if p[3] == 1)
    das = sum(1 for p in punten if p[3] == 2)
    print(f"{len(punten)} punten -> {outpad} (kuif: {kuif}, das: {das}). "
          f"Draai nu generate.py opnieuw.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    out = sys.argv[2] if len(sys.argv) > 2 else \
        Path(__file__).resolve().parent.parent / "data" / "trump-punten.json"
    main(sys.argv[1], out)
