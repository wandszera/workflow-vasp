from __future__ import annotations

import unittest
from pathlib import Path
import tempfile
from backend.app.services.incar_validator import IncarValidator


class TestIncarValidator(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.test_dir.name)

    def tearDown(self) -> None:
        self.test_dir.cleanup()

    def test_parse_incar(self) -> None:
        content = """# Comment line
SYSTEM = Silicon
NSW = 100   # number of ionic steps
IBRION = 2;   comment
# another comment
"""
        incar_file = self.dir_path / "INCAR"
        incar_file.write_text(content, encoding="utf-8")

        tags = IncarValidator.parse_incar(incar_file)
        self.assertEqual(tags.get("SYSTEM"), "Silicon")
        self.assertEqual(tags.get("NSW"), "100")
        self.assertEqual(tags.get("IBRION"), "2")

    def test_validate_mlff_goal(self) -> None:
        # Invalid INCAR for MLFF
        content = "NSW = 0\nIBRION = -1\n"
        incar_file = self.dir_path / "INCAR"
        incar_file.write_text(content, encoding="utf-8")

        res = IncarValidator.validate(incar_file, goal="mlff training")
        self.assertFalse(res["valid"])
        self.assertIn("ML_LMLFF", res["missing_keys"])
        self.assertIn("NSW", res["missing_keys"])
        self.assertIn("IBRION", res["missing_keys"])

    def test_fix_incar(self) -> None:
        content = "SYSTEM = Si\nNSW = 0\n"
        incar_file = self.dir_path / "INCAR"
        incar_file.write_text(content, encoding="utf-8")

        res_val = IncarValidator.validate(incar_file, goal="relax")
        self.assertFalse(res_val["valid"])

        res_fix = IncarValidator.fix_tags(incar_file, res_val["missing_keys"])
        self.assertTrue(res_fix["success"])
        self.assertTrue(res_fix["fixed"])

        # Check if backup exists
        backup_file = self.dir_path / "INCAR.incar.bak"
        self.assertTrue(backup_file.exists())

        # Check updated values
        updated_tags = IncarValidator.parse_incar(incar_file)
        self.assertEqual(updated_tags.get("NSW"), "200")
        self.assertEqual(updated_tags.get("IBRION"), "2")


if __name__ == "__main__":
    unittest.main()
