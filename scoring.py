#!/usr/bin/env python3
"""Scoring engine WK 2026 Poule — implementeert het reglement uit de PRD (sectie 5).

Input:  deelnemers.json (parser.py) + uitslagen.json (werkelijke uitslagen)
Output: stand-dict per deelnemer met punten per categorie, per ronde,
        cumulatief verloop en maximaal haalbare eindscore.

Rondes: groep-1, groep-2, groep-3, zestiende, achtste, kwart, halve, finale, bonus.
"""
import json
import re
import unicodedata

RONDES = ["groep-1", "groep-2", "groep-3", "zestiende", "achtste",
          "kwart", "halve", "finale", "bonus"]

# --- Grap-handicap (tijdelijk) --------------------------------------------
# Vaste extra punten bovenop de formulierscore, per deelnemer (op naam).
# Knipoog naar René Charlataan, die vroeger zelf het scorebord in een
# gigantische Excel bijhield en zichzelf steevast bovenaan zette.
# VERWIJDEREN: zet HANDICAP = {} (of maak deze regel leeg). Niets anders
# hoeft te veranderen; de handicap verdwijnt dan uit totaal en verloop.
HANDICAP = {
    "René Charlataan": 50,
}

# Punten per categorie (reglement)
PT_UITSLAG, PT_TOTO = 3, 1
PT_PLEK_JUIST, PT_TOP2 = 3, 2
PT_ACHTSTE, PT_KWART, PT_HALVE, PT_FINALE = 3, 5, 10, 15
PT_KAMPIOEN, PT_TWEEDE, PT_DERDE, PT_VIERDE = 40, 20, 15, 10
PT_TOPSCORER = 5
MAX_BONUS = 3 + 3 + 3 + 3 + 5 + 5  # alle bonusvragen exact


def norm(s):
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().casefold()


# Canonieke topscorernamen. Varianten ("mbappe", "Kylian Mbappé", "yamal")
# worden op de volledige naam gemapt via exacte of achternaam-match.
# Achternamen moeten uniek zijn binnen deze lijst.
TOPSCORERS = [
    "Kylian Mbappé", "Erling Haaland", "Harry Kane", "Lamine Yamal",
    "Lautaro Martínez", "Lionel Messi", "Cristiano Ronaldo",
    "Vinícius Júnior", "Jude Bellingham", "Julián Álvarez",
    "Antoine Griezmann", "Bukayo Saka", "Jamal Musiala", "Florian Wirtz",
    "Memphis Depay", "Cody Gakpo", "Romelu Lukaku", "Richarlison",
    "Marcus Rashford", "Phil Foden", "Álvaro Morata", "Serhou Guirassy",
]
_TS_INDEX = None


def _ts_index():
    global _TS_INDEX
    if _TS_INDEX is None:
        idx = {}
        for vol in TOPSCORERS:
            idx[norm(vol)] = vol
            idx.setdefault(norm(vol).split()[-1], vol)
        _TS_INDEX = idx
    return _TS_INDEX


def topscorer_canoniek(naam):
    """Map een ingevulde topscorernaam op de volledige spelersnaam.

    Onbekende namen blijven ongewijzigd staan (origineel, getrimd)."""
    if not naam:
        return None
    kaal = re.sub(r"\(.*?\)", " ", str(naam))       # '(arg)' en dergelijke weg
    kaal = re.sub(r"[^a-z ]", " ", norm(kaal))      # leestekens weg
    kaal = re.sub(r"\s+", " ", kaal).strip()
    if not kaal:
        return str(naam).strip()
    idx = _ts_index()
    if kaal in idx:
        return idx[kaal]
    for woord in kaal.split():                       # achternaam-match
        if woord in idx:
            return idx[woord]
    return str(naam).strip()


def _toto(a, b):
    return "T" if a > b else ("U" if a < b else "G")


def score_groepswedstrijden(deelnemer, uitslagen):
    """Cat. A: 3 pt exacte uitslag, anders 1 pt juiste toto. Per ronde toegekend."""
    per_ronde, potentieel = {}, 0
    werkelijk = {(norm(w["thuis"]), norm(w["uit"])): w
                 for w in uitslagen["groepswedstrijden"]}
    for v in deelnemer["groepswedstrijden"]:
        w = werkelijk.get((norm(v["thuis"]), norm(v["uit"])))
        if w is None:
            continue  # wedstrijd niet in uitslagenlijst: telt niet mee
        ronde = w.get("ronde", "groep-1")
        if w["thuis_score"] is None or w["uit_score"] is None:
            potentieel += PT_UITSLAG  # nog niet gespeeld
            continue
        if v["thuis_score"] is None or v["uit_score"] is None:
            continue  # deelnemer vulde niets in: 0 punten
        if (v["thuis_score"], v["uit_score"]) == (w["thuis_score"], w["uit_score"]):
            pt = PT_UITSLAG
        elif _toto(v["thuis_score"], v["uit_score"]) == _toto(w["thuis_score"], w["uit_score"]):
            pt = PT_TOTO
        else:
            pt = 0
        per_ronde[ronde] = per_ronde.get(ronde, 0) + pt
    return per_ronde, potentieel


def score_groepseindstand(deelnemer, uitslagen):
    """Cat. B: nrs 1 en 2 per groep — 3 pt juiste plek, 2 pt juiste top-2-ploeg."""
    punten, potentieel = 0, 0
    for groep, voorspeld in deelnemer["groepseindstand"].items():
        werkelijk = uitslagen["groepseindstand"].get(groep)
        if not werkelijk or werkelijk[0] is None or werkelijk[1] is None:
            potentieel += 2 * PT_PLEK_JUIST  # groep nog niet beslist
            continue
        top2_werkelijk = {norm(werkelijk[0]), norm(werkelijk[1])}
        for plaats in (0, 1):  # plaats 1 en 2
            land = voorspeld[plaats] if plaats < len(voorspeld) else None
            if land is None:
                continue
            if norm(land) == norm(werkelijk[plaats]):
                punten += PT_PLEK_JUIST
            elif norm(land) in top2_werkelijk:
                punten += PT_TOP2
    return punten, potentieel


def _score_plaatsing(voorspeld_landen, werkelijk_landen, verwacht_aantal,
                     pt_per_ploeg, uitgeschakeld):
    """Cat. C: punten per juiste geplaatste ploeg (setvergelijking)."""
    actual = {norm(l) for l in werkelijk_landen if l}
    preds = [norm(l) for l in voorspeld_landen if l]
    punten = sum(pt_per_ploeg for p in preds if p in actual)
    if len(actual) >= verwacht_aantal:
        potentieel = 0  # ronde afgerond
    else:
        potentieel = sum(pt_per_ploeg for p in preds
                         if p not in actual and p not in uitgeschakeld)
    return punten, potentieel


def score_einduitslag(deelnemer, uitslagen, uitgeschakeld):
    """Cat. D: kampioen 40, tweede 20; 3e/4e via huisregel (voorspelde
    verliezers halve finales, zonder volgorde)."""
    punten, potentieel = 0, 0
    for sleutel, pt in (("kampioen", PT_KAMPIOEN), ("tweede", PT_TWEEDE)):
        pred, act = deelnemer[sleutel], uitslagen[sleutel]
        if act:
            if norm(pred) == norm(act):
                punten += pt
        elif pred and norm(pred) not in uitgeschakeld:
            potentieel += pt
    # Huisregel 3e/4e: voorspelde halvefinalisten minus voorspelde finalisten
    halvefinalisten = {norm(l) for l in deelnemer["kwart_winnaars"].values() if l}
    finalisten = {norm(l) for l in deelnemer["halve_winnaars"].values() if l}
    verliezers = halvefinalisten - finalisten
    for sleutel, pt in (("derde", PT_DERDE), ("vierde", PT_VIERDE)):
        act = uitslagen[sleutel]
        if act:
            if norm(act) in verliezers:
                punten += pt
        elif any(v not in uitgeschakeld for v in verliezers):
            potentieel += pt
    return punten, potentieel


def _diff_score(voorspeld, werkelijk, schaal):
    """schaal: lijst van (max_afwijking, punten), oplopend gesorteerd."""
    if voorspeld is None or werkelijk is None:
        return None
    diff = abs(float(voorspeld) - float(werkelijk))
    for grens, pt in schaal:
        if diff <= grens:
            return pt
    return 0


def score_bonus(deelnemer, uitslagen):
    """Cat. E: bonusvragen, definitief gescoord zodra werkelijke waarde bekend."""
    b, act = deelnemer["bonus"], uitslagen["bonus"]
    schalen = {
        "nl_doelpunten_voor": [(0, 3), (1, 2), (2, 1)],
        "nl_doelpunten_tegen": [(0, 3), (1, 2), (2, 1)],
        "nl_geel": [(0, 3), (1, 2), (2, 1)],
        "toernooi_doelpunten": [(0, 3), (5, 2), (10, 1)],
        "toernooi_rood": [(0, 5), (1, 3), (2, 1)],
    }
    punten, potentieel = 0, 0
    for sleutel, schaal in schalen.items():
        if b.get(sleutel) is None:
            continue  # geen voorspelling ingevuld: geen punten, geen potentieel
        s = _diff_score(b.get(sleutel), act.get(sleutel), schaal)
        if s is None:
            potentieel += schaal[0][1]  # werkelijke waarde nog onbekend
        else:
            punten += s
    # Topscorer: vergelijk op canonieke volledige naam (accentongevoelig)
    pred, act_naam = b.get("topscorer"), act.get("topscorer")
    if act_naam:
        if pred and norm(topscorer_canoniek(pred)) == norm(topscorer_canoniek(act_naam)):
            punten += PT_TOPSCORER
    elif pred:
        potentieel += PT_TOPSCORER
    return punten, potentieel


def bereken_stand(data, uitslagen):
    uitgeschakeld = {norm(l) for l in uitslagen.get("uitgeschakeld", [])}
    stand = []
    for d in data["deelnemers"]:
        per_ronde = {r: 0 for r in RONDES}
        categorien, potentieel = {}, 0

        gw, pot = score_groepswedstrijden(d, uitslagen)
        for r, pt in gw.items():
            per_ronde[r] += pt
        categorien["groepswedstrijden"] = sum(gw.values())
        potentieel += pot

        pt, pot = score_groepseindstand(d, uitslagen)
        per_ronde["groep-3"] += pt
        categorien["groepseindstand"] = pt
        potentieel += pot

        for cat, preds, actkey, n, ppp, ronde in (
            ("achtste_bereikt", d["zestiende_winnaars"].values(),
             "achtste_finalisten", 16, PT_ACHTSTE, "zestiende"),
            ("kwart_bereikt", d["achtste_winnaars"].values(),
             "kwartfinalisten", 8, PT_KWART, "achtste"),
            ("halve_bereikt", d["kwart_winnaars"].values(),
             "halvefinalisten", 4, PT_HALVE, "kwart"),
            ("finale_bereikt", d["halve_winnaars"].values(),
             "finalisten", 2, PT_FINALE, "halve"),
        ):
            pt, pot = _score_plaatsing(preds, uitslagen.get(actkey, []),
                                       n, ppp, uitgeschakeld)
            per_ronde[ronde] += pt
            categorien[cat] = pt
            potentieel += pot

        pt, pot = score_einduitslag(d, uitslagen, uitgeschakeld)
        per_ronde["finale"] += pt
        categorien["einduitslag"] = pt
        potentieel += pot

        pt, pot = score_bonus(d, uitslagen)
        per_ronde["bonus"] += pt
        categorien["bonus"] = pt
        potentieel += pot

        handicap = HANDICAP.get(d["naam"], 0)
        totaal = sum(per_ronde.values()) + handicap
        # Vlakke offset zodat het verloop (cumulatief[-1]) gelijk blijft aan totaal.
        cumulatief, lopend = [], handicap
        for r in RONDES:
            lopend += per_ronde[r]
            cumulatief.append(lopend)
        stand.append({
            "naam": d["naam"],
            "totaal": totaal,
            "handicap": handicap,
            "per_ronde": per_ronde,
            "cumulatief": cumulatief,
            "categorien": categorien,
            "max_haalbaar": totaal + potentieel,
            "kampioen": d["kampioen"],
            "topscorer": topscorer_canoniek(d["bonus"].get("topscorer")),
        })
    stand.sort(key=lambda s: (-s["totaal"], s["naam"]))
    vorige, plek = None, 0
    for i, s in enumerate(stand, start=1):
        if s["totaal"] != vorige:
            plek, vorige = i, s["totaal"]
        s["positie"] = plek  # gedeelde posities bij gelijke stand
    return {"rondes": RONDES, "stand": stand}


if __name__ == "__main__":
    import sys
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    uitslagen = json.load(open(sys.argv[2], encoding="utf-8"))
    print(json.dumps(bereken_stand(data, uitslagen), ensure_ascii=False, indent=2))
