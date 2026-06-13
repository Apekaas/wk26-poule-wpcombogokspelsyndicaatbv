#!/usr/bin/env python3
"""Haal werkelijke WK 2026-uitslagen op en werk data/uitslagen.json bij.

Bron: football-data.org v4 (gratis tier). Vereist omgevingsvariabele
FOOTBALL_DATA_KEY en de competitie-code (FD_COMPETITIE, standaard 'WC').

Het script werkt automatisch bij: poule-uitslagen, groepseindstanden,
knock-outplaatsingen, doelpunten-tussenstand en de topscorer (/scorers).

Kaarten komen van een tweede, gratis bron: de (key-loze) ESPN-API.
football-data.org levert kaarten namelijk alleen in betaalde tiers, en de
gratis alternatieven (API-Football, TheSportsDB) hebben geen of incomplete
kaartdata voor het WK 2026. ESPN geeft per wedstrijd een betrouwbare
'details'-lijst met rode/gele kaarten; één scoreboard-call over de hele
toernooiperiode volstaat. Lukt de ESPN-call niet, dan blijven de
handmatig ingevulde tellers in bonus_tussenstand staan.

Handmatige fallback: vul data/uitslagen.json zelf in en draai de
workflow zonder API-key — dit script slaat zichzelf dan over.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
UITSLAGEN = REPO / "data" / "uitslagen.json"
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

NAAM_NL = {
    "Mexico": "Mexico", "South Africa": "Zuid-Afrika", "Korea Republic": "Zuid-Korea",
    "South Korea": "Zuid-Korea", "Czechia": "Tsjechië", "Czech Republic": "Tsjechië",
    "Canada": "Canada", "Bosnia and Herzegovina": "Bosnië-Herzegovina",
    "Bosnia-Herzegovina": "Bosnië-Herzegovina",
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
STADIUM_NAAR_LIJST = {
    "LAST_32": "achtste_finalisten",
    "LAST_16": "kwartfinalisten",
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


def espn(pad):
    req = urllib.request.Request(
        f"{ESPN_BASE}/{pad}",
        headers={"User-Agent": "Mozilla/5.0 (wk26-poule dashboard)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def kaarten_via_espn(onbekend):
    """Tel kaarten via de gratis, key-loze ESPN-API.

    Eén scoreboard-call over de toernooiperiode bevat per wedstrijd een
    'details'-lijst met kaart-events (betrouwbare redCard/yellowCard-
    booleans en team-id). Telt over alle afgeronde wedstrijden de rode
    kaarten (toernooi-totaal) en de gele kaarten van Nederland.
    Geeft (toernooi_rood, nl_geel) terug, of None bij een fout.

    Instelbaar via ESPN_LIGA (standaard 'fifa.world') en ESPN_DATES
    (YYYYMMDD-YYYYMMDD, standaard de hele WK 2026-periode)."""
    liga = os.environ.get("ESPN_LIGA", "fifa.world")
    dates = os.environ.get("ESPN_DATES", "20260611-20260720")
    try:
        sb = espn(f"{liga}/scoreboard?dates={dates}&limit=300")
    except Exception as e:
        print(f"ESPN scoreboard niet opgehaald ({e}); kaarten ongemoeid.")
        return None
    rood_totaal, nl_geel, afgerond = 0, 0, 0
    for ev in sb.get("events", []):
        if not ev.get("status", {}).get("type", {}).get("completed"):
            continue
        afgerond += 1
        comp = (ev.get("competitions") or [{}])[0]
        team_naam = {(c.get("team") or {}).get("id"):
                     nl((c.get("team") or {}).get("displayName", ""), onbekend)
                     for c in comp.get("competitors", [])}
        for d in comp.get("details", []):
            if d.get("redCard"):
                rood_totaal += 1
            if d.get("yellowCard") and \
                    team_naam.get((d.get("team") or {}).get("id")) == "Nederland":
                nl_geel += 1
    print(f"ESPN-kaarten: {afgerond} afgeronde wedstrijden; "
          f"rood totaal {rood_totaal}, geel NL {nl_geel}.")
    return rood_totaal, nl_geel


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
            if sum(r["playedGames"] for r in tafel) == 12:
                uitslagen["groepseindstand"][groep] = [
                    nl(r["team"]["name"], onbekend) for r in tafel]
    except Exception as e:
        print(f"Standings niet opgehaald ({e}); groepseindstanden ongemoeid.")

    # 3. Knock-out: geplaatste ploegen per fase
    for fase, veld in STADIUM_NAAR_LIJST.items():
        winnaars = []
        for m in klaar:
            if m["stage"] == fase and m["score"].get("winner"):
                kant = "homeTeam" if m["score"]["winner"] == "HOME_TEAM" else "awayTeam"
                winnaars.append(nl(m[kant]["name"], onbekend))
        if winnaars:
            uitslagen[veld] = sorted(set(uitslagen.get(veld, [])) | set(winnaars))

    # 4. Finale + troostfinale
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

    # 5. Uitgeschakelde ploegen (verliezers knock-out)
    uitgeschakeld = set(uitslagen.get("uitgeschakeld", []))
    for m in klaar:
        if m["stage"] in (*STADIUM_NAAR_LIJST, "FINAL") and m["score"].get("winner"):
            kant = "awayTeam" if m["score"]["winner"] == "HOME_TEAM" else "homeTeam"
            uitgeschakeld.add(nl(m[kant]["name"], onbekend))
    uitslagen["uitgeschakeld"] = sorted(uitgeschakeld)

    # 6. Doelpunten-tussenstand (uit de wedstrijdenlijst zelf)
    nl_voor = nl_tegen = tot_doelpunten = 0
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
    bt = uitslagen["bonus_tussenstand"]
    bt["nl_doelpunten_voor"] = nl_voor
    bt["nl_doelpunten_tegen"] = nl_tegen
    bt["toernooi_doelpunten"] = tot_doelpunten

    # 7. Kaarten via de gratis ESPN-API. Lukt het niet, dan blijven de
    #    handmatig ingevulde tellers in bonus_tussenstand staan.
    espn_kaarten = kaarten_via_espn(onbekend)
    if espn_kaarten is not None:
        bt["toernooi_rood"], bt["nl_geel"] = espn_kaarten

    # 8. Topscorer-tussenstand via /scorers
    try:
        scorers = api(f"competitions/{comp}/scorers?limit=3", key).get("scorers", [])
        if scorers:
            bt["topscorer"] = " · ".join(
                f"{s['player']['name']} ({s.get('goals') or 0})" for s in scorers)
    except Exception as e:
        print(f"Scorers niet opgehaald ({e}); topscorer-teller ongemoeid.")

    uitslagen["laatste_update"] = datetime.now(timezone.utc).isoformat(
        timespec="seconds")
    UITSLAGEN.write_text(json.dumps(uitslagen, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    if onbekend:
        print("LET OP — onbekende teamnamen (mapping aanvullen):", sorted(onbekend))
    print(f"Uitslagen bijgewerkt: {len(klaar)} gespeelde wedstrijden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
