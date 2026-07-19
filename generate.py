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
from datetime import datetime, timedelta, timezone
from pathlib import Path

import scoring

HIER = Path(__file__).resolve().parent


def toernooi_afgelopen(uitslagen):
    """True zodra de WK-kampioen bekend is (finale verwerkt). Trigger voor de
    winnaar-onthulling bovenaan het dashboard."""
    return uitslagen.get("kampioen") is not None

# Stages op chronologische volgorde (football-data.org v4).
STAGE_VOLGORDE = ["GROUP_STAGE", "LAST_32", "LAST_16", "QUARTER_FINALS",
                  "SEMI_FINALS", "THIRD_PLACE", "FINAL"]
# Per knock-outstage: (poule-rondelabel, deelnemer-voorspelveld 'gaat door',
# punten die de winst ontsluit, weergavelabel voor de punten).
KO_STAGE = {
    "LAST_32": ("Zestiende finales", "zestiende_winnaars", "3 pt"),
    "LAST_16": ("Achtste finales", "achtste_winnaars", "5 pt"),
    "QUARTER_FINALS": ("Kwartfinales", "kwart_winnaars", "10 pt"),
    "SEMI_FINALS": ("Halve finales", "halve_winnaars", "15 pt"),
    "THIRD_PLACE": ("Troostfinale", None, "15 / 10 pt"),
    "FINAL": ("Finale", "kampioen", "40 / 20 pt"),
}

NL_DAGEN = ["ma", "di", "wo", "do", "vr", "za", "zo"]
NL_MAANDEN = ["jan", "feb", "mrt", "apr", "mei", "jun",
              "jul", "aug", "sep", "okt", "nov", "dec"]


def nl_speeltijd(utc_iso):
    """UTC-aftrap -> Nederlandse zomertijd (UTC+2, vast voor juni/juli 2026).

    Geeft bv. 'za 13 jun 20:00', of None als er geen tijd bekend is."""
    if not utc_iso:
        return None
    try:
        dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    dt = dt.astimezone(timezone.utc) + timedelta(hours=2)
    return (f"{NL_DAGEN[dt.weekday()]} {dt.day} {NL_MAANDEN[dt.month - 1]} "
            f"{dt.hour:02d}:{dt.minute:02d}")

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


def _doorgevoorspeld(deelnemer, veld):
    """Genormaliseerde set landen die deze deelnemer in dat veld liet doorgaan."""
    if veld == "kampioen":
        k = deelnemer.get("kampioen")
        return {scoring.norm(k)} if k else set()
    return {scoring.norm(l) for l in deelnemer.get(veld, {}).values() if l}


def programma(data, uitslagen):
    """Wedstrijden van de huidige ronde: gespeelde uitslagen + nog te spelen
    wedstrijden met Nederlandse aftraptijd, punten en deelnemers-inzet.

    'Huidige ronde' = de vroegste stage met nog niet-gespeelde wedstrijden."""
    schema = uitslagen.get("wedstrijdschema") or []
    if not schema:
        return None

    # Vroegste stage met een niet-afgeronde wedstrijd; anders de laatste
    # stage waar überhaupt wedstrijden voor bestaan (toernooi afgelopen).
    huidige, laatste = None, None
    for stage in STAGE_VOLGORDE:
        matches = [m for m in schema if m.get("stage") == stage]
        if not matches:
            continue
        laatste = stage
        if any(m.get("status") != "FINISHED" for m in matches):
            huidige = stage
            break
    stage = huidige or laatste
    if not stage:
        return None

    matches = [m for m in schema if m.get("stage") == stage]
    matches.sort(key=lambda m: m.get("utcDate") or "")

    if stage == "GROUP_STAGE":
        label, veld, punten_label = "Groepswedstrijden", None, "max 3 pt"
    else:
        label, veld, punten_label = KO_STAGE.get(
            stage, (stage.title(), None, ""))

    # Deelnemers-inzet: hoe vaak is elk land in dit veld doorvoorspeld?
    inzet = Counter()
    if veld:
        for d in data["deelnemers"]:
            for land in _doorgevoorspeld(d, veld):
                inzet[land] += 1

    wedstrijden = []
    for m in matches:
        gespeeld = m.get("status") == "FINISHED"
        thuis, uit = m.get("thuis"), m.get("uit")
        ts, us = m.get("thuis_score"), m.get("uit_score")
        rij = {
            "thuis": thuis, "uit": uit,
            "gespeeld": gespeeld,
            "speeltijd": nl_speeltijd(m.get("utcDate")),
            "inzet_thuis": inzet.get(scoring.norm(thuis)) if thuis else None,
            "inzet_uit": inzet.get(scoring.norm(uit)) if uit else None,
        }
        if gespeeld:
            reg, ver, pen = m.get("regulier"), m.get("verlenging"), m.get("penalties")
            reg_compleet = reg and None not in reg
            ver_compleet = ver and None not in ver
            if reg_compleet and ver_compleet:
                hoofd = [reg[0] + ver[0], reg[1] + ver[1]]  # stand na verlenging
            elif reg_compleet:
                hoofd = reg
            else:
                hoofd = [ts, us]                             # reguliere speeltijd
            rij["uitslag"] = f'{hoofd[0]}–{hoofd[1]}' if ts is not None else None
            if m.get("duration") == "PENALTY_SHOOTOUT" and pen and None not in pen:
                rij["penalties"] = f'{pen[0]}–{pen[1]}'       # los, in het paars
            elif m.get("duration") == "EXTRA_TIME":
                rij["scorelabel"] = "na verlenging"
            # Winnaar op basis van fullTime (verrekent de strafschoppen correct).
            rij["winnaar"] = ("thuis" if (ts or 0) > (us or 0) else
                              "uit" if (us or 0) > (ts or 0) else None)
        else:
            rij["punten"] = punten_label
        wedstrijden.append(rij)

    return {
        "ronde": label,
        "toont_inzet": bool(veld),
        "wedstrijden": wedstrijden,
    }


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
        "programma": programma(data, uitslagen),
        "verrassing": verrassing(data, uitslagen),
        "groepswedstrijden": uitslagen["groepswedstrijden"],
        "validatie": [v for v in data.get("validatie", []) if v["fouten"]],
        # Trigger voor de winnaar-onthulling bovenaan het dashboard.
        "toernooi_afgelopen": toernooi_afgelopen(uitslagen),
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
