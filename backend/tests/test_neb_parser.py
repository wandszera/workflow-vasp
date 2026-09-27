from __future__ import annotations

import unittest
from pathlib import Path
import tempfile
from backend.app.services.neb_parser import NebParser


class TestNebParser(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.test_dir.name)

    def tearDown(self) -> None:
        self.test_dir.cleanup()

    def test_get_neb_data_empty(self) -> None:
        data = NebParser.get_neb_data(self.dir_path)
        self.assertIsNone(data)

    def test_get_neb_data_success(self) -> None:
        # Create image directories
        for img in ["00", "01", "02"]:
            img_dir = self.dir_path / img
            img_dir.mkdir()
            
            # Write mock OSZICAR
            if img == "00":
                osz = " 10 F= -10.5000 E0= -10.5000\n"
            elif img == "01":
                osz = " 10 F= -9.8000 E0= -9.8000\n"
            else:
                osz = " 10 F= -10.3000 E0= -10.3000\n"
            
            (img_dir / "OSZICAR").write_text(osz, encoding="utf-8")

        data = NebParser.get_neb_data(self.dir_path)
        self.assertIsNotNone(data)
        self.assertEqual(data["images"], ["00", "01", "02"])
        self.assertEqual(data["energies"], [-10.5, -9.8, -10.3])
        # Relative energies: [-10.5 - (-10.5), -9.8 - (-10.5), -10.3 - (-10.5)]
        self.assertEqual(data["relative_energies"], [0.0, 0.7, 0.2])
        self.assertEqual(data["activation_energy"], 0.7)


if __name__ == "__main__":
    unittest.main()
