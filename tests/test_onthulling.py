#!/usr/bin/env python3
"""Unit tests winnaar-onthulling trigger — borgt dat de vlag correct schakelt.

Draaien: python3 -m unittest discover -s tests -v   (vanuit de repo-root)
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import generate  # noqa: E402


class TestToernooiAfgelopen(unittest.TestCase):
    def test_geen_kampioen_geen_onthulling(self):
        self.assertFalse(generate.toernooi_afgelopen({"kampioen": None}))

    def test_kampioen_bekend_wel_onthulling(self):
        self.assertTrue(generate.toernooi_afgelopen({"kampioen": "Argentinië"}))

    def test_veld_ontbreekt_geen_onthulling(self):
        # Defensief: uitslagen zonder kampioen-sleutel mag niet crashen.
        self.assertFalse(generate.toernooi_afgelopen({}))


if __name__ == "__main__":
    unittest.main()
