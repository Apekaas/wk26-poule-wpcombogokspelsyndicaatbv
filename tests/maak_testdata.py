#!/usr/bin/env python3
"""Maak testdata voor de done-check: 3 dummy-deelnemers naast het echte
formulier, plus een deels gevulde uitslagen-set (midden in de groepsfase).

Gebruik: python3 tests/maak_testdata.py <deelnemers.json> <uitslagen.json> <outmap>
"""
import copy
import json
import sys
from pathlib import Path


def main(deelnemers_pad, uitslagen_pad, outmap):
    data = json.load(open(deelnemers_pad, encoding="utf-8"))
    basis = data["deelnemers"][0]

    namen = ["Demi 'Dummy' de Vries", "Karel Kantine", "Petra Pronostiek"]
    for i, naam in enumerate(namen, start=1):
        d = copy.deepcopy(basis)
        d["naam"] = naam
        d["bestand"] = f"dummy-{i}.xlsx"
        # varieer voorspellingen zodat de stand uiteenloopt
        for w in d["groepswedstrijden"][:i * 3]:
            w["thuis_score"], w["uit_score"] = w["uit_score"], w["thuis_score"]
        if i == 1:
            d["kampioen"], d["tweede"] = "Frankrijk", "Brazilië"
        if i == 2:
            d["kampioen"] = "Argentinië"
            d["bonus"]["topscorer"] = "Lionel Messi"
        if i == 3:
            d["bonus"]["nl_doelpunten_voor"] = 11
            d["bonus"]["toernooi_doelpunten"] = 300
        data["deelnemers"].append(d)

    uitslagen = json.load(open(uitslagen_pad, encoding="utf-8"))
    # eerste vijf groepswedstrijden gespeeld
    gespeeld = [(2, 0), (1, 1), (0, 1), (1, 0), (3, 0)]
    for w, (a, b) in zip(uitslagen["groepswedstrijden"], gespeeld):
        w["thuis_score"], w["uit_score"] = a, b
    uitslagen["groepseindstand"] = {"A": ["Mexico", "Zuid-Korea",
                                          "Tsjechië", "Zuid-Afrika"]}
    uitslagen["uitgeschakeld"] = ["Zuid-Afrika", "Qatar"]
    uitslagen["bonus_tussenstand"].update(
        {"nl_doelpunten_voor": 1, "nl_doelpunten_tegen": 0, "nl_geel": 2,
         "toernooi_doelpunten": 19, "toernooi_rood": 1,
         "topscorer": "Mbappé (3)"})
    uitslagen["laatste_update"] = "2026-06-15T07:30:00+00:00"

    outmap = Path(outmap)
    outmap.mkdir(parents=True, exist_ok=True)
    (outmap / "deelnemers-test.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (outmap / "uitslagen-test.json").write_text(
        json.dumps(uitslagen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Testdata ({len(data['deelnemers'])} deelnemers) -> {outmap}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
