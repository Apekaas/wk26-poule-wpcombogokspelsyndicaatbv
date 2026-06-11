#!/usr/bin/env python3
"""Genereer het WK 2026 Poule Dashboard (statische HTML).

Stappen:
  1. Lees deelnemers.json + uitslagen.json
  2. Bereken de stand (scoring.py) en de delta t.o.v. de vorige run
  3. Bereken extra's: kampioenskaart, NL-bonusmeter, verrassing van de ronde
  4. Injecteer alles als JSON in template.html -> docs/index.html

Gebruik:
    python3 generate.py [deelnemers.json] [uitslagen.json] [output-map]
Standaard: data/deelnemers.json data/uitslagen.json docs/
"""
import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import scoring

HIER = Path(__file__).resolve().parent

RONDE_LABELS = {
    "groep-1": "Groepsronde 1", "groep-2": "Groepsronde 2",
    "groep-3": "Groepsronde 3", "zestiende": "Zestiende finales",
    "achtste": "Achtste finales", "kwart": "Kwartfinales",
    "halve": "Halve finales", "finale": "Finale", "bonus": "Bonusvragen",
}


def kampioenskaart(data, uitslagen):
    """Per voorspelde kampioen: aantal deelnemers + status in het toernooi."""
    uitgeschakeld = {scoring.norm(l) for l in uitslagen.get("uitgeschakeld", [])}
    telling = Counter(d["kampioen"] for d in data["deelnemers"] if d["kampioen"])
    kaart = []
    for land, n in telling.most_common():
        status = "uitgeschakeld" if scoring.norm(land) in uitgeschakeld else "actief"
        if uitslagen.get("kampioen"):
            status = ("kampioen" if scoring.norm(land) == scoring.norm(uitslagen["kampioen"])
                      else "uitgeschakeld")
        kaart.append({"land": land, "aantal": n, "status": status})
    return kaart


def nl_bonusmeter(data, uitslagen):
    """Live tellers naast de spreiding van de voorspellingen."""
    vragen = [
        ("nl_doelpunten_voor", "Doelpunten vóór NL"),
        ("nl_doelpunten_tegen", "Tegendoelpunten NL"),
        ("nl_geel", "Gele kaarten NL"),
        ("toernooi_doelpunten", "Doelpunten toernooi"),
        ("toernooi_rood", "Rode kaarten toernooi"),
    ]
    tussen = uitslagen.get("bonus_tussenstand", {})
    meter = []
    for sleutel, label in vragen:
        waarden = [d["bonus"].get(sleutel) for d in data["deelnemers"]
                   if isinstance(d["bonus"].get(sleutel), (int, float))]
        meter.append({
            "label": label,
            "actueel": tussen.get(sleutel),
            "definitief": uitslagen["bonus"].get(sleutel),
            "min": min(waarden) if waarden else None,
            "max": max(waarden) if waarden else None,
            "mediaan": statistics.median(waarden) if waarden else None,
        })
    topscorers = Counter(
        scoring.topscorer_canoniek(d["bonus"].get("topscorer"))
        for d in data["deelnemers"] if d["bonus"].get("topscorer"))
    return {"vragen": meter,
            "topscorer_actueel": tussen.get("topscorer"),
            "topscorer_keuzes": [{"naam": n, "aantal": a}
                                 for n, a in topscorers.most_common(8)]}


def verrassing(data, uitslagen):
    """De gespeelde groepsuitslag (toto) die door de minste deelnemers was voorspeld."""
    kandidaten = []
    for w in uitslagen["groepswedstrijden"]:
        if w["thuis_score"] is None or w["uit_score"] is None:
            continue
        toto_w = scoring._toto(w["thuis_score"], w["uit_score"])
        goed, totaal = 0, 0
        for d in data["deelnemers"]:
            for v in d["groepswedstrijden"]:
                if (scoring.norm(v["thuis"]), scoring.norm(v["uit"])) == \
                   (scoring.norm(w["thuis"]), scoring.norm(w["uit"])):
                    if v["thuis_score"] is not None and v["uit_score"] is not None:
                        totaal += 1
                        if scoring._toto(v["thuis_score"], v["uit_score"]) == toto_w:
                            goed += 1
        if totaal:
            kandidaten.append({
                "wedstrijd": f'{w["thuis"]} – {w["uit"]}',
                "uitslag": f'{w["thuis_score"]}–{w["uit_score"]}',
                "goed": goed, "totaal": totaal,
                "pct": round(100 * goed / totaal),
            })
    kandidaten.sort(key=lambda k: k["pct"])
    return kandidaten[0] if kandidaten else None


def main(deelnemers_pad, uitslagen_pad, outmap):
    data = json.load(open(deelnemers_pad, encoding="utf-8"))
    uitslagen = json.load(open(uitslagen_pad, encoding="utf-8"))
    stand = scoring.bereken_stand(data, uitslagen)

    # Delta t.o.v. vorige run (stand.json wordt elke run gecommit in de repo)
    standpad = HIER / "data" / "stand.json"
    vorige = {}
    if standpad.exists():
        try:
            oud = json.load(open(standpad, encoding="utf-8"))
            vorige = {s["naam"]: s for s in oud.get("stand", [])}
        except Exception:
            vorige = {}
    for s in stand["stand"]:
        v = vorige.get(s["naam"])
        s["delta"] = s["totaal"] - v["totaal"] if v else 0
        s["positie_delta"] = (v["positie"] - s["positie"]) if v else 0

    payload = {
        "gegenereerd": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rondes": stand["rondes"],
        "ronde_labels": RONDE_LABELS,
        "stand": stand["stand"],
        "kampioenskaart": kampioenskaart(data, uitslagen),
        "nl_bonusmeter": nl_bonusmeter(data, uitslagen),
        "verrassing": verrassing(data, uitslagen),
        "groepswedstrijden": uitslagen["groepswedstrijden"],
        "validatie": [v for v in data.get("validatie", []) if v["fouten"]],
    }

    standpad.parent.mkdir(parents=True, exist_ok=True)
    standpad.write_text(json.dumps(stand, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    template = (HIER / "template.html").read_text(encoding="utf-8")
    html = template.replace("\"__POULE_DATA__\"",
                            json.dumps(payload, ensure_ascii=False))
    # Trump-puntenwolk (optioneel, uit tools/punten_van_afbeelding.py)
    trumppad = HIER / "data" / "trump-punten.json"
    trump = trumppad.read_text(encoding="utf-8") if trumppad.exists() else "null"
    html = html.replace("\"__TRUMP_PUNTEN__\"", trump)
    outmap = Path(outmap)
    outmap.mkdir(parents=True, exist_ok=True)
    (outmap / "index.html").write_text(html, encoding="utf-8")
    print(f"Dashboard gegenereerd: {outmap / 'index.html'} "
          f"({len(stand['stand'])} deelnemers)")


if __name__ == "__main__":
    argv = sys.argv[1:]
    main(argv[0] if len(argv) > 0 else HIER / "data" / "deelnemers.json",
         argv[1] if len(argv) > 1 else HIER / "data" / "uitslagen.json",
         argv[2] if len(argv) > 2 else HIER / "docs")
