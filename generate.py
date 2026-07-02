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


# Knockoutrondes, diepst-eerst: (uitslag-lijst, deelnemer-voorspelveld, label).
KNOCKOUT_RONDES = [
    ("finalisten", "halve_winnaars", "de finale"),
    ("halvefinalisten", "kwart_winnaars", "de halve finale"),
    ("kwartfinalisten", "achtste_winnaars", "de kwartfinale"),
    ("achtste_finalisten", "zestiende_winnaars", "de achtste finale"),
]


def _verrassing_groep(data, uitslagen):
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
    if not kandidaten:
        return None
    k = kandidaten[0]
    return {
        "type": "groep",
        "kop": k["wedstrijd"],
        "tekst": f'eindigde in {k["uitslag"]} — slechts {k["goed"]} van de '
                 f'{k["totaal"]} deelnemers ({k["pct"]}%) had deze toto goed.',
        **k,  # wedstrijd/uitslag/goed/totaal/pct blijven beschikbaar
    }


def _verrassing_knockout(data, uitslagen):
    """Grootste plaatsingsverrassing van de huidige (diepst besliste) knockoutronde.

    Vergelijkt de 'gevallen favoriet' (meest voorspelde ploeg die de ronde niet
    haalde) met de 'verrassende stunt' (ploeg die de ronde wél haalde terwijl
    bijna niemand het voorspelde) en toont de grootste van de twee."""
    for actkey, veld, label in KNOCKOUT_RONDES:
        bereikt = uitslagen.get(actkey) or []
        if not bereikt:
            continue  # ronde nog niet begonnen

        bereikt_n = {scoring.norm(l) for l in bereikt if l}
        uit = {scoring.norm(l) for l in uitslagen.get("uitgeschakeld", []) if l}

        # Per genormaliseerd land: aantal deelnemers dat het in deze ronde voorspelde.
        telling, noemer, weergave = {}, 0, {}
        for d in data["deelnemers"]:
            landen = {scoring.norm(l): l for l in d[veld].values() if l}
            if not landen:
                continue
            noemer += 1
            for n, orig in landen.items():
                telling[n] = telling.get(n, 0) + 1
                weergave.setdefault(n, orig)
        if not noemer:
            continue

        # Gevallen favoriet: uitgeschakeld, ronde niet gehaald, hoogste share.
        favoriet = None
        for n, aantal in telling.items():
            if n in uit and n not in bereikt_n:
                waarde = aantal / noemer
                if favoriet is None or waarde > favoriet[1]:
                    favoriet = (n, waarde, aantal)

        # Verrassende stunt: haalde de ronde, laagste share.
        stunt = None
        for n in bereikt_n:
            aantal = telling.get(n, 0)
            waarde = 1 - aantal / noemer
            if stunt is None or waarde > stunt[1]:
                stunt = (n, waarde, aantal)

        # Grootste van de twee (bij gelijke waarde wint de gevallen favoriet).
        keuze = None
        if favoriet and (stunt is None or favoriet[1] >= stunt[1]):
            n, _, aantal = favoriet
            keuze = {
                "kop": weergave.get(n, bereikt[0]),
                "tekst": f'stond bij {round(100 * aantal / noemer)}% van de '
                         f'deelnemers nog in {label} — en werd toch uitgeschakeld. '
                         f'De verrassing van deze ronde.',
            }
        elif stunt:
            n, _, aantal = stunt
            landnaam = next((l for l in bereikt if scoring.norm(l) == n), n)
            keuze = {
                "kop": landnaam,
                "tekst": f'haalde {label} terwijl slechts '
                         f'{round(100 * aantal / noemer)}% van de deelnemers het '
                         f'voorspelde. De verrassing van deze ronde.',
            }
        if keuze:
            keuze["type"] = "knockout"
            return keuze
        return None  # ronde begonnen maar geen bruikbare kandidaat
    return None


def verrassing(data, uitslagen):
    """Knockoutverrassing zodra die fase loopt, anders de groepsfase-verrassing."""
    return _verrassing_knockout(data, uitslagen) or _verrassing_groep(data, uitslagen)


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
