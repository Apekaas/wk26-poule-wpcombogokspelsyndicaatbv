#!/usr/bin/env python3
"""Unit tests scoring engine — dekt elke regel uit PRD sectie 5 incl. randgevallen.

Draaien: python3 -m unittest discover -s tests -v   (vanuit build/)
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scoring  # noqa: E402


def deelnemer(**kw):
    d = {
        "naam": "Test", "bestand": "test.xlsx",
        "groepswedstrijden": [],
        "groepseindstand": {},
        "zestiende_winnaars": {}, "achtste_winnaars": {},
        "kwart_winnaars": {}, "halve_winnaars": {},
        "kampioen": None, "tweede": None,
        "bonus": {"nl_doelpunten_voor": None, "nl_doelpunten_tegen": None,
                  "nl_geel": None, "toernooi_doelpunten": None,
                  "toernooi_rood": None, "topscorer": None},
    }
    d.update(kw)
    return d


def uitslagen(**kw):
    u = {
        "groepswedstrijden": [],
        "groepseindstand": {},
        "achtste_finalisten": [], "kwartfinalisten": [],
        "halvefinalisten": [], "finalisten": [],
        "kampioen": None, "tweede": None, "derde": None, "vierde": None,
        "uitgeschakeld": [],
        "bonus": {"nl_doelpunten_voor": None, "nl_doelpunten_tegen": None,
                  "nl_geel": None, "toernooi_doelpunten": None,
                  "toernooi_rood": None, "topscorer": None},
    }
    u.update(kw)
    return u


def wedstrijd(thuis, uit, vt, vu):
    return {"datum": "2026-06-11", "thuis": thuis, "uit": uit,
            "thuis_score": vt, "uit_score": vu}


def w_uitslag(thuis, uit, st, su, ronde="groep-1"):
    return {"datum": "2026-06-11", "thuis": thuis, "uit": uit,
            "thuis_score": st, "uit_score": su, "ronde": ronde}


class TestGroepswedstrijden(unittest.TestCase):
    def test_exacte_uitslag_3pt(self):
        d = deelnemer(groepswedstrijden=[wedstrijd("Mexico", "Zuid-Afrika", 2, 0)])
        u = uitslagen(groepswedstrijden=[w_uitslag("Mexico", "Zuid-Afrika", 2, 0)])
        pr, pot = scoring.score_groepswedstrijden(d, u)
        self.assertEqual(pr, {"groep-1": 3})
        self.assertEqual(pot, 0)

    def test_juiste_toto_1pt(self):
        d = deelnemer(groepswedstrijden=[wedstrijd("Mexico", "Zuid-Afrika", 2, 0)])
        u = uitslagen(groepswedstrijden=[w_uitslag("Mexico", "Zuid-Afrika", 3, 1)])
        pr, _ = scoring.score_groepswedstrijden(d, u)
        self.assertEqual(pr, {"groep-1": 1})

    def test_gelijkspel_toto(self):
        d = deelnemer(groepswedstrijden=[wedstrijd("A1", "B1", 0, 0)])
        u = uitslagen(groepswedstrijden=[w_uitslag("A1", "B1", 2, 2)])
        pr, _ = scoring.score_groepswedstrijden(d, u)
        self.assertEqual(pr, {"groep-1": 1})

    def test_fout_0pt(self):
        d = deelnemer(groepswedstrijden=[wedstrijd("A1", "B1", 1, 0)])
        u = uitslagen(groepswedstrijden=[w_uitslag("A1", "B1", 0, 1)])
        pr, _ = scoring.score_groepswedstrijden(d, u)
        self.assertEqual(pr, {"groep-1": 0})

    def test_niet_gespeeld_potentieel(self):
        d = deelnemer(groepswedstrijden=[wedstrijd("A1", "B1", 1, 0)])
        u = uitslagen(groepswedstrijden=[w_uitslag("A1", "B1", None, None)])
        pr, pot = scoring.score_groepswedstrijden(d, u)
        self.assertEqual(sum(pr.values()), 0)
        self.assertEqual(pot, 3)

    def test_ronde_toewijzing(self):
        d = deelnemer(groepswedstrijden=[wedstrijd("A1", "B1", 1, 0)])
        u = uitslagen(groepswedstrijden=[w_uitslag("A1", "B1", 1, 0, ronde="groep-2")])
        pr, _ = scoring.score_groepswedstrijden(d, u)
        self.assertEqual(pr, {"groep-2": 3})


class TestGroepseindstand(unittest.TestCase):
    def test_beide_juiste_plek_6pt(self):
        d = deelnemer(groepseindstand={"A": ["X", "Y", "Z", "Q"]})
        u = uitslagen(groepseindstand={"A": ["X", "Y", "Z", "Q"]})
        pt, pot = scoring.score_groepseindstand(d, u)
        self.assertEqual((pt, pot), (6, 0))

    def test_top2_verkeerde_plek_4pt(self):
        d = deelnemer(groepseindstand={"A": ["Y", "X", "Z", "Q"]})
        u = uitslagen(groepseindstand={"A": ["X", "Y", "Z", "Q"]})
        pt, _ = scoring.score_groepseindstand(d, u)
        self.assertEqual(pt, 4)  # 2 + 2

    def test_een_juist_een_fout(self):
        d = deelnemer(groepseindstand={"A": ["X", "Z", "Y", "Q"]})
        u = uitslagen(groepseindstand={"A": ["X", "Y", "Z", "Q"]})
        pt, _ = scoring.score_groepseindstand(d, u)
        self.assertEqual(pt, 3)  # X juist (3), Z niet in top 2 (0)

    def test_groep_onbeslist_potentieel(self):
        d = deelnemer(groepseindstand={"A": ["X", "Y", "Z", "Q"]})
        u = uitslagen(groepseindstand={})
        pt, pot = scoring.score_groepseindstand(d, u)
        self.assertEqual((pt, pot), (0, 6))

    def test_nr3_en_4_tellen_niet(self):
        d = deelnemer(groepseindstand={"A": ["F1", "F2", "X", "Y"]})
        u = uitslagen(groepseindstand={"A": ["A1", "A2", "X", "Y"]})
        pt, _ = scoring.score_groepseindstand(d, u)
        self.assertEqual(pt, 0)


class TestPlaatsing(unittest.TestCase):
    def test_achtste_3pt_per_ploeg(self):
        pt, _ = scoring._score_plaatsing(["A", "B", "C"], ["A", "C", "D"], 16, 3, set())
        self.assertEqual(pt, 6)

    def test_volgorde_irrelevant(self):
        pt, _ = scoring._score_plaatsing(["A", "B"], ["B", "A"], 2, 15, set())
        self.assertEqual(pt, 30)

    def test_ronde_afgerond_geen_potentieel(self):
        _, pot = scoring._score_plaatsing(["A", "B"], ["B", "C"], 2, 15, set())
        self.assertEqual(pot, 0)

    def test_potentieel_zonder_uitgeschakelde(self):
        _, pot = scoring._score_plaatsing(
            ["A", "B", "C"], ["A"], 16, 3, {scoring.norm("B")})
        self.assertEqual(pot, 3)  # alleen C nog mogelijk; A al binnen, B eruit

    def test_kwart_halve_finale_punten(self):
        self.assertEqual(scoring._score_plaatsing(["A"], ["A"], 8, 5, set())[0], 5)
        self.assertEqual(scoring._score_plaatsing(["A"], ["A"], 4, 10, set())[0], 10)
        self.assertEqual(scoring._score_plaatsing(["A"], ["A"], 2, 15, set())[0], 15)


class TestEinduitslag(unittest.TestCase):
    def base(self):
        return deelnemer(
            kampioen="Spanje", tweede="Argentinië",
            kwart_winnaars={"25": "Frankrijk", "26": "Spanje",
                            "27": "Engeland", "28": "Argentinië"},
            halve_winnaars={"29": "Spanje", "30": "Argentinië"})

    def test_kampioen_40_tweede_20(self):
        u = uitslagen(kampioen="Spanje", tweede="Argentinië",
                      derde="Brazilië", vierde="Duitsland")
        pt, _ = scoring.score_einduitslag(self.base(), u, set())
        self.assertEqual(pt, 60)

    def test_huisregel_derde_15(self):
        u = uitslagen(kampioen="X", tweede="Y", derde="Frankrijk", vierde="Z")
        pt, _ = scoring.score_einduitslag(self.base(), u, set())
        self.assertEqual(pt, 15)  # Frankrijk = voorspelde halve-finale-verliezer

    def test_huisregel_dubbele_treffer_25(self):
        u = uitslagen(kampioen="X", tweede="Y",
                      derde="Frankrijk", vierde="Engeland")
        pt, _ = scoring.score_einduitslag(self.base(), u, set())
        self.assertEqual(pt, 25)  # 15 + 10, beide verliezers in top 3/4

    def test_finalist_telt_niet_als_derde(self):
        u = uitslagen(kampioen="X", tweede="Y", derde="Spanje", vierde="Z")
        pt, _ = scoring.score_einduitslag(self.base(), u, set())
        self.assertEqual(pt, 0)  # Spanje was voorspeld als finalist, niet verliezer

    def test_potentieel_vervalt_bij_uitschakeling(self):
        u = uitslagen()  # niets beslist
        pt, pot = scoring.score_einduitslag(
            self.base(), u, {scoring.norm("Spanje")})
        self.assertEqual(pt, 0)
        self.assertEqual(pot, 20 + 15 + 10)  # kampioen (Spanje) vervalt


class TestBonus(unittest.TestCase):
    def base(self):
        return deelnemer(bonus={"nl_doelpunten_voor": 7, "nl_doelpunten_tegen": 5,
                                "nl_geel": 9, "toernooi_doelpunten": 285,
                                "toernooi_rood": 7, "topscorer": "Mbappé"})

    def test_alles_exact(self):
        u = uitslagen(bonus={"nl_doelpunten_voor": 7, "nl_doelpunten_tegen": 5,
                             "nl_geel": 9, "toernooi_doelpunten": 285,
                             "toernooi_rood": 7, "topscorer": "Kylian Mbappe"})
        pt, pot = scoring.score_bonus(self.base(), u)
        self.assertEqual((pt, pot), (scoring.MAX_BONUS, 0))  # 22, incl. accentloze naam-match

    def test_marges_nl_vragen(self):
        u = uitslagen(bonus={"nl_doelpunten_voor": 8,    # 1 ernaast -> 2
                             "nl_doelpunten_tegen": 3,   # 2 ernaast -> 1
                             "nl_geel": 12,              # 3 ernaast -> 0
                             "toernooi_doelpunten": None,
                             "toernooi_rood": None, "topscorer": None})
        pt, _ = scoring.score_bonus(self.base(), u)
        self.assertEqual(pt, 3)

    def test_marges_toernooi_doelpunten(self):
        for werkelijk, verwacht in ((285, 3), (290, 2), (280, 2), (295, 1), (296, 0)):
            u = uitslagen(bonus={"toernooi_doelpunten": werkelijk})
            u["bonus"].setdefault("topscorer", None)
            pt, _ = scoring.score_bonus(self.base(), u)
            self.assertEqual(pt, verwacht, f"werkelijk={werkelijk}")

    def test_marges_rode_kaarten(self):
        for werkelijk, verwacht in ((7, 5), (8, 3), (5, 1), (4, 0)):
            u = uitslagen(bonus={"toernooi_rood": werkelijk})
            pt, _ = scoring.score_bonus(self.base(), u)
            self.assertEqual(pt, verwacht, f"werkelijk={werkelijk}")

    def test_topscorer_fout(self):
        u = uitslagen(bonus={"topscorer": "Haaland"})
        pt, _ = scoring.score_bonus(self.base(), u)
        self.assertEqual(pt, 0)

    def test_open_vragen_potentieel(self):
        pt, pot = scoring.score_bonus(self.base(), uitslagen())
        self.assertEqual((pt, pot), (0, scoring.MAX_BONUS))


class TestStandIntegraal(unittest.TestCase):
    def test_posities_gedeeld_bij_gelijke_stand(self):
        d1 = deelnemer(naam="A", groepswedstrijden=[wedstrijd("X", "Y", 1, 0)])
        d2 = deelnemer(naam="B", groepswedstrijden=[wedstrijd("X", "Y", 1, 0)])
        d3 = deelnemer(naam="C", groepswedstrijden=[wedstrijd("X", "Y", 0, 1)])
        u = uitslagen(groepswedstrijden=[w_uitslag("X", "Y", 1, 0)])
        res = scoring.bereken_stand({"deelnemers": [d1, d2, d3]}, u)
        posities = {s["naam"]: s["positie"] for s in res["stand"]}
        self.assertEqual(posities, {"A": 1, "B": 1, "C": 3})

    def test_cumulatief_loopt_op(self):
        d = deelnemer(naam="A",
                      groepswedstrijden=[wedstrijd("X", "Y", 1, 0)],
                      zestiende_winnaars={"1": "X"})
        u = uitslagen(groepswedstrijden=[w_uitslag("X", "Y", 1, 0, ronde="groep-1")],
                      achtste_finalisten=["X"])
        res = scoring.bereken_stand({"deelnemers": [d]}, u)
        s = res["stand"][0]
        self.assertEqual(s["per_ronde"]["groep-1"], 3)
        self.assertEqual(s["per_ronde"]["zestiende"], 3)
        self.assertEqual(s["cumulatief"][-1], s["totaal"])
        self.assertEqual(s["totaal"], 6)

    def test_max_haalbaar_bij_lege_uitslagen(self):
        d = deelnemer(naam="A", kampioen="Spanje",
                      groepswedstrijden=[wedstrijd("X", "Y", 1, 0)])
        u = uitslagen(groepswedstrijden=[w_uitslag("X", "Y", None, None)])
        res = scoring.bereken_stand({"deelnemers": [d]}, u)
        s = res["stand"][0]
        # 3 (open wedstrijd) + 40 (kampioen); bonus leeg voorspeld telt niet mee
        self.assertEqual(s["totaal"], 0)
        self.assertEqual(s["max_haalbaar"], 43)

    def test_lege_bonusvoorspelling_geen_potentieel(self):
        d = deelnemer(naam="A")  # bonus volledig leeg
        pt, pot = scoring.score_bonus(d, uitslagen())
        self.assertEqual((pt, pot), (0, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
