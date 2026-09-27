from __future__ import annotations

import unittest
from pathlib import Path
import tempfile
from backend.app.services.kpoints_validator import KpointsValidator


class TestKpointsValidator(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.test_dir.name)

    def tearDown(self) -> None:
        self.test_dir.cleanup()

    def test_parse_kpoints(self) -> None:
        content = """Automatic mesh
0
Monkhorst-Pack
4 4 4
0 0 0
"""
        kpoints_file = self.dir_path / "KPOINTS"
        kpoints_file.write_text(content, encoding="utf-8")

        k_data = KpointsValidator.parse_kpoints(kpoints_file)
        self.assertIsNotNone(k_data)
        self.assertEqual(k_data["type"], "monkhorst-pack")
        self.assertEqual(k_data["mesh"], (4, 4, 4))

    def test_validate_kpoints_density(self) -> None:
        content = "Automatic mesh\n0\nMonkhorst-Pack\n4 4 2\n0 0 0\n"
        kpoints_file = self.dir_path / "KPOINTS"
        kpoints_file.write_text(content, encoding="utf-8")

        # Silicon-like lattice length = 5.43 A.
        # Densities: 4*5.43 = 21.72 A (insufficient Z direction)
        # 2*5.43 = 10.86 A (insufficient)
        res = KpointsValidator.validate(kpoints_file, (5.43, 5.43, 5.43))
        self.assertFalse(res["valid"])
        self.assertEqual(len(res["warnings"]), 3)
        self.assertEqual(res["suggested_mesh"], (6, 6, 6))

    def test_generate_kpoints(self) -> None:
        kpoints_file = self.dir_path / "KPOINTS"
        res = KpointsValidator.generate_kpoints(kpoints_file, (6, 6, 6))
        self.assertTrue(res["success"])
        self.assertIsNone(res["backup"])
        self.assertTrue(kpoints_file.exists())

        k_data = KpointsValidator.parse_kpoints(kpoints_file)
        self.assertEqual(k_data["mesh"], (6, 6, 6))


if __name__ == "__main__":
    unittest.main()
