from __future__ import annotations

import unittest
from pathlib import Path
import tempfile
from backend.app.services.poscar_validator import PoscarValidator
from backend.app.services.poscar_corrector import PoscarCorrector


class TestPoscarCorrector(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.test_dir.name)

    def tearDown(self) -> None:
        self.test_dir.cleanup()

    def test_correct_colliding_poscar(self) -> None:
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

        # Confirm there is a collision initially
        initial_check = PoscarValidator.validate(poscar_file, threshold_ang=0.8)
        self.assertFalse(initial_check["valid"])

        # Run correction
        res = PoscarCorrector.fix(poscar_file, threshold_ang=0.8, target_separation_ang=1.1)
        self.assertTrue(res["success"])
        self.assertTrue(res["fixed"])

        # Check if backup exists
        backup_file = self.dir_path / "POSCAR.poscar.bak"
        self.assertTrue(backup_file.exists())
        self.assertIn("0.01 0.01 0.01", backup_file.read_text(encoding="utf-8"))

        # Confirm there is no collision now
        final_check = PoscarValidator.validate(poscar_file, threshold_ang=0.8)
        self.assertTrue(final_check["valid"])
        self.assertGreaterEqual(final_check["min_distance_ang"], 1.0)


if __name__ == "__main__":
    unittest.main()
