#!/usr/bin/env python3
"""Zet een karikatuur-afbeelding om naar een 3D-puntenwolk voor het podium.

Afgestemd op de Trump-karikatuur (witte achtergrond): alle niet-witte pixels
worden bemonsterd tot max ~5200 punten. Per punt: [x, y, z, kleurklasse]:
  x/y  genormaliseerd naar [-1, 1] (y omhoog)
  z    reliëf: lichtere partijen liggen dichterbij, plus lichte ruis
  kleurklasse: 0 = huid/overig (bone-wit), 1 = kuif (amber),
               2 = das (plum), 3 = pak (as-grijs)

Gebruik:
    python3 tools/punten_van_afbeelding.py <afbeelding> [data/trump-punten.json]

Draai daarna generate.py opnieuw; het podium pakt de wolk automatisch op.
"""
import json
import random
import sys
from pathlib import Path

from PIL import Image

MAX_PUNTEN = 5200
MAX_BREEDTE = 220
# Herweging per kleurklasse: gezicht en kuif krijgen meer punten dan het
# (grote, donkere) pak, zodat het herkenbare deel de meeste details houdt.
FACTOR = {0: 1.6, 1: 1.2, 2: 1.0, 3: 0.4}


def kleurklasse(r, g, b):
    if r > 140 and g > 100 and b < 150 and (r + g) > 2.1 * b:
        return 1                                  # goudgele kuif
    if r > 110 and g < 95 and b < 95 and r > 1.5 * g:
        return 2                                  # rode das
    if max(r, g, b) < 90:
        return 3                                  # donker pak
    return 0                                      # huid / overig


def main(inpad, outpad):
    img = Image.open(inpad).convert("RGB")
    if img.width > MAX_BREEDTE:
        img = img.resize((MAX_BREEDTE, int(img.height * MAX_BREEDTE / img.width)))
    w, h = img.size
    px = img.load()

    kandidaten = []
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if r > 238 and g > 238 and b > 238:
                continue                          # witte achtergrond
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            sat = max(r, g, b) - min(r, g, b)
            gewicht = (1 + sat / 64 + (255 - lum) / 96) * FACTOR[kleurklasse(r, g, b)]
            kandidaten.append((gewicht, x, y, r, g, b, lum))
    if not kandidaten:
        sys.exit("Geen niet-witte pixels gevonden.")

    random.seed(2026)
    n = min(MAX_PUNTEN, len(kandidaten))
    gekozen = random.choices(kandidaten,
                             weights=[k[0] for k in kandidaten], k=n)

    schaal = max(w, h) / 2
    cx, cy = w / 2, h / 2
    punten = []
    for _, x, y, r, g, b, lum in gekozen:
        punten.append([
            round((x - cx) / schaal, 3),
            round(-(y - cy) / schaal, 3),
            round((lum / 255 - 0.45) * 0.45 + random.uniform(-0.05, 0.05), 3),
            kleurklasse(r, g, b),
        ])
    Path(outpad).parent.mkdir(parents=True, exist_ok=True)
    Path(outpad).write_text(json.dumps(punten, separators=(",", ":")),
                            encoding="utf-8")
    telling = {k: sum(1 for p in punten if p[3] == k) for k in (0, 1, 2, 3)}
    print(f"{len(punten)} punten -> {outpad} "
          f"(huid: {telling[0]}, kuif: {telling[1]}, das: {telling[2]}, "
          f"pak: {telling[3]}). Draai nu generate.py opnieuw.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    out = sys.argv[2] if len(sys.argv) > 2 else \
        Path(__file__).resolve().parent.parent / "data" / "trump-punten.json"
    main(sys.argv[1], out)
