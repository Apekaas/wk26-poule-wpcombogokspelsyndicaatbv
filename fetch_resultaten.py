#!/usr/bin/env python3
"""Haal werkelijke WK 2026-uitslagen op en werk data/uitslagen.json bij.

Bron: football-data.org v4 (gratis tier). Vereist omgevingsvariabele
FOOTBALL_DATA_KEY en de competitie-id voor het WK 2026 (FD_COMPETITIE,
standaard 'WC'). Fase 0-validatie bepaalt of deze API volstaat; het
script werkt defensief en laat velden ongemoeid die het niet kan vullen.

Handmatige fallback: vul data/uitslagen.json zelf in en draai de
workflow zonder API-key — dit script slaat zichzelf dan over.

Gebruik (vanuit de repo-root): python3 github/fetch_resultaten.py
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
UITSLAGEN = REPO / "data" / "uitslagen.json"

# Naam-mapping API (Engels) -> formulier (Nederlands). Aanvullen in fase 0
# zodra de echte API-namen bekend zijn; onbekende namen worden gerapporteerd.
NAAM_NL = {
    "Mexico": "Mexico", "South Africa": "Zuid-Afrika", "Korea Republic": "Zuid-Korea",
    "South Korea": "Zuid-Korea", "Czechia": "Tsjechië", "Czech Republic": "Tsjechië",
    "Canada": "Canada", "Bosnia and Herzegovina": "Bosnië-Herzegovina",
    "Qatar": "Qatar", "Switzerland": "Zwitserland", "Brazil": "Brazilië",
    "Morocco": "Marokko", "Haiti": "Haïti", "Scotland": "Schotland",
    "United States": "Verenigde Staten", "USA": "Verenigde Staten",
    "Paraguay": "Paraguay", "Australia": "Australië", "Turkey": "Turkije",
    "Türkiye": "Turkije", "Germany": "Duitsland", "Curacao": "Curaçao",
    "Curaçao": "Curaçao", "Ivory Coast": "Ivoorkust", "Côte d'Ivoire": "Ivoorkust",
    "Ecuador": "Ecuador", "Netherlands": "Nederland", "Japan": "Japan",
    "Sweden": "Zweden", "Tunisia": "Tunesië", "Belgium": "België",
    "Egypt": "Egypte", "Iran": "Iran", "IR Iran": "Iran",
    "New Zealand": "Nieuw-Zeeland", "Spain": "Spanje", "Cape Verde": "Kaapverdië",
    "Cabo Verde": "Kaapverdië", "Saudi Arabia": "Saoedi-Arabië",
    "Uruguay": "Uruguay", "France": "Frankrijk", "Senegal": "Senegal",
    "Iraq": "Irak", "Norway": "Noorwegen", "Argentina": "Argentinië",
    "Algeria": "Algerije", "Austria": "Oostenrijk", "Jordan": "Jordanië",
    "Portugal": "Portugal", "DR Congo": "DR Congo", "Congo DR": "DR Congo",
    "Uzbekistan": "Oezbekistan", "Colombia": "Colombia", "England": "Engeland",
    "Croatia": "Kroatië", "Ghana": "Ghana", "Panama": "Panama",
}
STADIUM_NAAR_LIJST = {           # API-fasecode -> veld in uitslagen.json
    "LAST_32": "achtste_finalisten",     # winnaars zestiende -> achtste
    "LAST_16": "kwartfinalisten",        # winnaars achtste -> kwart
    "QUARTER_FINALS": "halvefinalisten",
    "SEMI_FINALS": "finalisten",
}


def api(pad, key):
    req = urllib.request.Request(
        f"https://api.football-data.org/v4/{pad}",
        headers={"X-Auth-Token": key})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def nl(naam, onbekend):
    if naam in NAAM_NL:
        return NAAM_NL[naam]
    onbekend.add(naam)
    return naam


def main():
    key = os.environ.get("FOOTBALL_DATA_KEY")
    if not key:
        print("Geen FOOTBALL_DATA_KEY gezet — fetch overgeslagen "
              "(handmatige uitslagen blijven leidend).")
        return 0
    comp = os.environ.get("FD_COMPETITIE", "WC")
    uitslagen = json.load(open(UITSLAGEN, encoding="utf-8"))
    onbekend = set()

    wedstrijden = api(f"competitions/{comp}/matches", key)["matches"]
    klaar = [m for m in wedstrijden if m["status"] == "FINISHED"]

    # 1. De 13 poulewedstrijden van het formulier bijwerken
    for w in uitslagen["groepswedstrijden"]:
        for m in klaar:
            if m["stage"] != "GROUP_STAGE":
                continue
            t = nl(m["homeTeam"]["name"], onbekend)
            u = nl(m["awayTeam"]["name"], onbekend)
            if {t, u} == {w["thuis"], w["uit"]}:
                ft = m["score"]["fullTime"]
                if t == w["thuis"]:
                    w["thuis_score"], w["uit_score"] = ft["home"], ft["away"]
                else:
                    w["thuis_score"], w["uit_score"] = ft["away"], ft["home"]

    # 2. Groepseindstanden (zodra een groep klaar is)
    try:
        standen = api(f"competitions/{comp}/standings", key)["standings"]
        for s in standen:
            if s.get("type") != "TOTAL" or not s.get("group"):
                continue
            groep = s["group"].replace("GROUP_", "").replace("Group ", "").strip()
            tafel = s["table"]
            gespeeld = sum(r["playedGames"] for r in tafel)
            if gespeeld == 12:  # 6 duels x 2 teams: groep afgerond
                uitslagen["groepseindstand"][groep] = [
                    nl(r["team"]["name"], onbekend) for r in tafel]
    except Exception as e:
        print(f"Standings niet opgehaald ({e}); groepseindstanden ongemoeid.")

    # 3. Knock-out: geplaatste ploegen per fase = winnaars van de vorige fase
    for fase, veld in STADIUM_NAAR_LIJST.items():
        winnaars = []
        for m in klaar:
            if m["stage"] == fase and m["score"].get("winner"):
                kant = "homeTeam" if m["score"]["winner"] == "HOME_TEAM" else "awayTeam"
                winnaars.append(nl(m[kant]["name"], onbekend))
        if winnaars:
            bestaand = set(uitslagen.get(veld, []))
            uitslagen[veld] = sorted(bestaand | set(winnaars))

    # 4. Finale + troostfinale -> einduitslag
    for m in klaar:
        win = m["score"].get("winner")
        if not win:
            continue
        w_, v_ = (("homeTeam", "awayTeam") if win == "HOME_TEAM"
                  else ("awayTeam", "homeTeam"))
        if m["stage"] == "FINAL":
            uitslagen["kampioen"] = nl(m[w_]["name"], onbekend)
            uitslagen["tweede"] = nl(m[v_]["name"], onbekend)
        if m["stage"] == "THIRD_PLACE":
            uitslagen["derde"] = nl(m[w_]["name"], onbekend)
            uitslagen["vierde"] = nl(m[v_]["name"], onbekend)

    # 5. Uitgeschakelde ploegen afleiden (verliezers knock-out)
    uitgeschakeld = set(uitslagen.get("uitgeschakeld", []))
    for m in klaar:
        if m["stage"] in (*STADIUM_NAAR_LIJST, "FINAL") and m["score"].get("winner"):
            kant = "awayTeam" if m["score"]["winner"] == "HOME_TEAM" else "homeTeam"
            uitgeschakeld.add(nl(m[kant]["name"], onbekend))
    uitslagen["uitgeschakeld"] = sorted(uitgeschakeld)

    # 6. Bonus-tussenstand: NL-doelpunten uit gespeelde NL-wedstrijden
    nl_voor = nl_tegen = 0
    tot_doelpunten = 0
    for m in klaar:
        ft = m["score"]["fullTime"]
        if ft["home"] is None:
            continue
        tot_doelpunten += ft["home"] + ft["away"]
        namen = {nl(m["homeTeam"]["name"], onbekend): ft["home"],
                 nl(m["awayTeam"]["name"], onbekend): ft["away"]}
        if "Nederland" in namen:
            nl_voor += namen.pop("Nederland")
            nl_tegen += next(iter(namen.values()))
    uitslagen["bonus_tussenstand"]["nl_doelpunten_voor"] = nl_voor
    uitslagen["bonus_tussenstand"]["nl_doelpunten_tegen"] = nl_tegen
    uitslagen["bonus_tussenstand"]["toernooi_doelpunten"] = tot_doelpunten
    # Kaarten en topscorer: niet betrouwbaar in de gratis tier ->
    # handmatig bijhouden in bonus_tussenstand (zie README).

    uitslagen["laatste_update"] = datetime.now(timezone.utc).isoformat(
        timespec="seconds")
    UITSLAGEN.write_text(json.dumps(uitslagen, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    if onbekend:
        print("LET OP — onbekende teamnamen (mapping aanvullen):", sorted(onbekend))
    print(f"Uitslagen bijgewerkt: {len(klaar)} gespeelde wedstrijden verwerkt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
