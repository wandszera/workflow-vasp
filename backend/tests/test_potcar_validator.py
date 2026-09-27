from __future__ import annotations

import unittest
from pathlib import Path
import tempfile
from backend.app.services.potcar_validator import PotcarValidator


class TestPotcarValidator(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.test_dir.name)

    def tearDown(self) -> None:
        self.test_dir.cleanup()

    def test_parse_potcar(self) -> None:
        content = """PAW_PBE Fe 05Jan2001
   ENMAX  =  268.000; ENMIN  =  200.000 eV
   VRHFIN =Fe: d7s1
PAW_PBE C 05Jan2001
   ENMAX  =  400.000; ENMIN  =  300.000 eV
   VRHFIN =C: s2p2
"""
        potcar_file = self.dir_path / "POTCAR"
        potcar_file.write_text(content, encoding="utf-8")

        res = PotcarValidator.parse_potcar(potcar_file)
        self.assertEqual(res["elements"], ["Fe", "C"])
        self.assertEqual(res["enmax_list"], [268.0, 400.0])
        self.assertEqual(res["max_enmax"], 400.0)

    def test_validate_matching_potcar(self) -> None:
        pot_content = """PAW_PBE Fe
   ENMAX  =  268.000
   VRHFIN =Fe: d7s1
PAW_PBE C
   ENMAX  =  400.000
   VRHFIN =C: s2p2
"""
        potcar_file = self.dir_path / "POTCAR"
        potcar_file.write_text(pot_content, encoding="utf-8")

        pos_content = "Silicon-Iron\n1.0\n5.4 0 0\n0 5.4 0\n0 0 5.4\nFe C\n1 1\nDirect\n0 0 0\n0.5 0.5 0.5\n"
        poscar_file = self.dir_path / "POSCAR"
        poscar_file.write_text(pos_content, encoding="utf-8")

        # Matching sequence Fe C, ENCUT = 520 (suggested = 1.3*400 = 520)
        res = PotcarValidator.validate(potcar_file, poscar_file, {"ENCUT": "520"})
        self.assertTrue(res["valid"])
        self.assertFalse(res["critical"])

    def test_validate_mismatch_potcar(self) -> None:
        pot_content = """PAW_PBE C
   ENMAX  =  400.000
   VRHFIN =C: s2p2
PAW_PBE Fe
   ENMAX  =  268.000
   VRHFIN =Fe: d7s1
"""
        potcar_file = self.dir_path / "POTCAR"
        potcar_file.write_text(pot_content, encoding="utf-8")

        pos_content = "Silicon-Iron\n1.0\n5.4 0 0\n0 5.4 0\n0 0 5.4\nFe C\n1 1\nDirect\n0 0 0\n0.5 0.5 0.5\n"
        poscar_file = self.dir_path / "POSCAR"
        poscar_file.write_text(pos_content, encoding="utf-8")

        # Divergent sequence: POSCAR expects Fe C, POTCAR has C Fe
        res = PotcarValidator.validate(potcar_file, poscar_file, {"ENCUT": "520"})
        self.assertFalse(res["valid"])
        self.assertTrue(res["critical"])
        self.assertTrue(any("Divergencia de sequencia" in w for w in res["warnings"]))


if __name__ == "__main__":
    unittest.main()
