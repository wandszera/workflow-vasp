from __future__ import annotations

import unittest
from pathlib import Path
import tempfile
from backend.app.services.poscar_validator import PoscarValidator


class TestPoscarValidator(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.test_dir.name)

    def tearDown(self) -> None:
        self.test_dir.cleanup()

    def test_valid_direct_poscar(self) -> None:
        content = """Silicon Crystal
1.0
 5.43 0.00 0.00
 0.00 5.43 0.00
 0.00 0.00 5.43
Si
2
Direct
0.00 0.00 0.00
0.25 0.25 0.25
"""
        poscar_file = self.dir_path / "POSCAR"
        poscar_file.write_text(content, encoding="utf-8")

        res = PoscarValidator.validate(poscar_file)
        self.assertTrue(res["valid"])
        self.assertEqual(res["colliding_pairs"], [])
        # Distance between (0,0,0) and (0.25, 0.25, 0.25) in Cartesian:
        # sqrt(3 * (0.25 * 5.43)^2) = 2.351 A
        self.assertAlmostEqual(res["min_distance_ang"], 2.35126, places=3)
        self.assertEqual(res["crystal_system"], "Cubico")
        self.assertEqual(res["lattice_lengths"], (5.43, 5.43, 5.43))
        self.assertEqual(res["lattice_angles"], (90.0, 90.0, 90.0))
        self.assertAlmostEqual(res["vacuum_thickness_ang"], 4.0725, places=3)

    def test_colliding_direct_poscar(self) -> None:
        content = """Silicon Crystal Colliding
1.0
 5.43 0.00 0.00
 0.00 5.43 0.00
 0.00 0.00 5.43
Si
2
Direct
0.00 0.00 0.00
0.01 0.01 0.01
"""
        poscar_file = self.dir_path / "POSCAR"
        poscar_file.write_text(content, encoding="utf-8")

        res = PoscarValidator.validate(poscar_file, threshold_ang=0.8)
        self.assertFalse(res["valid"])
        self.assertEqual(len(res["colliding_pairs"]), 1)
        self.assertEqual(res["colliding_pairs"][0][0], 0)
        self.assertEqual(res["colliding_pairs"][0][1], 1)
        self.assertAlmostEqual(res["min_distance_ang"], 0.09405, places=3)

    def test_valid_cartesian_poscar(self) -> None:
        content = """Graphene
1.0
 2.46 0.00 0.00
 -1.23 2.13 0.00
  0.00 0.00 10.00
C
2
Cartesian
0.00 0.00 0.00
0.00 1.42 0.00
"""
        poscar_file = self.dir_path / "POSCAR"
        poscar_file.write_text(content, encoding="utf-8")

        res = PoscarValidator.validate(poscar_file)
        self.assertTrue(res["valid"])
        self.assertAlmostEqual(res["min_distance_ang"], 1.42, places=3)
        self.assertEqual(res["crystal_system"], "Hexagonal")
        self.assertAlmostEqual(res["lattice_lengths"][0], 2.46, places=2)
        self.assertAlmostEqual(res["lattice_lengths"][1], 2.46, places=2)
        self.assertEqual(res["lattice_lengths"][2], 10.0)
        self.assertAlmostEqual(res["lattice_angles"][2], 120.0, places=1)
        self.assertAlmostEqual(res["vacuum_thickness_ang"], 10.0, places=2)


if __name__ == "__main__":
    unittest.main()
