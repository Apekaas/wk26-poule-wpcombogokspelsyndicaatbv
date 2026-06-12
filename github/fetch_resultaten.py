#!/usr/bin/env python3
"""Haal werkelijke WK 2026-uitslagen op en werk data/uitslagen.json bij.

Bron: football-data.org v4 (gratis tier). Vereist omgevingsvariabele
FOOTBALL_DATA_KEY en de competitie-code (FD_COMPETITIE, standaard 'WC').

Naast uitslagen en plaatsingen haalt dit script per afgeronde wedstrijd
één detail-call op voor de kaarten (bookings/statistics) en het
/scorers-endpoint voor de topscorer-tussenstand. Een cache
(data/kaarten-cache.json) zorgt dat elke wedstrijd maar één keer wordt
opgevraagd; per run maximaal MAX_DETAILCALLS calls met een pauze
ertussen (gratis tier: 10 calls/minuut).

Handmatige fallback: vul data/uitslagen.json zelf in en draai de
workflow zonder API-key — dit script slaat zichzelf dan over.
Handmatig ingevulde kaarten-tellers worden alleen overschreven als de
API daadwerkelijk kaartendata levert.
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
UITSLAGEN = REPO / "data" / "uitslagen.json"
KAARTEN_CACHE = REPO / "data" / "kaarten-cache.json"
MAX_DETAILCALLS = 24          # per run; 10/min-limiet -> pauze tussen calls
CALL_PAUZE = 6.5              # seconden

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


def kaarten_uit_match(detail):
    """Tel kaarten uit een match-detail. Geeft None als de data ontbreekt.

    RED en YELLOW_RED tellen als rode kaart; YELLOW en YELLOW_RED tellen
    als gele kaart (een tweede gele is immers ook een getoonde gele)."""
    bookings = detail.get("bookings")
    if bookings:
        rood = sum(1 for b in bookings if b.get("card") in ("RED", "YELLOW_RED"))
        geel_per_team = {}
        for b in bookings:
            if b.get("card") in ("YELLOW", "YELLOW_RED"):
                naam = b.get("team", {}).get("name", "")
                geel_per_team[naam] = geel_per_team.get(naam, 0) + 1
        return {"rood": rood, "geel_per_team": geel_per_team}
    # fallback: team-statistieken
    stats_aanwezig = False
    rood, geel_per_team = 0, {}
    for kant in ("homeTeam", "awayTeam"):
        st = (detail.get(kant) or {}).get("statistics") or {}
        if "red_cards" in st or "yellow_cards" in st:
            stats_aanwezig = True
            rood += (st.get("red_cards") or 0) + (st.get("yellow_red_cards") or 0)
            geel_per_team[detail[kant]["name"]] = \
                (st.get("yellow_cards") or 0) + (st.get("yellow_red_cards") or 0)
    return {"rood": rood, "geel_per_team": geel_per_team} if stats_aanwezig else None


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

    # 7. Kaarten: detail-call per afgeronde wedstrijd, met cache
    cache = {}
    if KAARTEN_CACHE.exists():
        try:
            cache = json.load(open(KAARTEN_CACHE, encoding="utf-8"))
        except Exception:
            cache = {}
    nieuw = [m for m in klaar if str(m["id"]) not in cache][:MAX_DETAILCALLS]
    zonder_data = 0
    for idx, m in enumerate(nieuw):
        if idx:
            time.sleep(CALL_PAUZE)  # 10 calls/min-limiet respecteren
        try:
            detail = api(f"matches/{m['id']}", key)
        except Exception as e:
            print(f"Detail {m['id']} niet opgehaald ({e}); volgende run opnieuw.")
            continue
        k = kaarten_uit_match(detail)
        if k is None:
            zonder_data += 1
            cache[str(m["id"])] = {"rood": 0, "geel_nl": 0, "geen_data": True}
        else:
            geel_nl = sum(n for team, n in k["geel_per_team"].items()
                          if nl(team, onbekend) == "Nederland")
            cache[str(m["id"])] = {"rood": k["rood"], "geel_nl": geel_nl}
    KAARTEN_CACHE.write_text(json.dumps(cache, indent=2), encoding="utf-8")

    met_data = [c for c in cache.values() if not c.get("geen_data")]
    if met_data:
        bt["toernooi_rood"] = sum(c["rood"] for c in met_data)
        bt["nl_geel"] = sum(c["geel_nl"] for c in met_data)
        print(f"Kaarten: {len(met_data)} wedstrijden met data; "
              f"rood totaal {bt['toernooi_rood']}, geel NL {bt['nl_geel']}.")
    else:
        print("LET OP: geen kaartendata in de API-respons — handmatige "
              "tellers in bonus_tussenstand blijven leidend.")
    if zonder_data:
        print(f"LET OP: {zonder_data} wedstrijd(en) zonder bookings/statistics "
              f"in deze run.")

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
    print(f"Uitslagen bijgewerkt: {len(klaar)} gespeelde wedstrijden, "
          f"{len(nieuw)} nieuwe detail-calls.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
