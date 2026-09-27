from __future__ import annotations

import unittest
from pathlib import Path
import tempfile
from backend.app.services.phonon_parser import PhononParser


class TestPhononParser(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.test_dir.name)

    def tearDown(self) -> None:
        self.test_dir.cleanup()

    def test_get_phonon_data_missing(self) -> None:
        data = PhononParser.get_phonon_data(self.dir_path)
        self.assertIsNone(data)

    def test_get_phonon_data_success(self) -> None:
        content = """# Phonopy thermal properties
thermal_properties:
- temp: 0.0000000
  free_energy: 15.1234
  entropy: 0.0000
  heat_capacity: 0.0000
- temp: 10.0000000
  free_energy: 15.1012
  entropy: 0.0543
  heat_capacity: 0.1234
"""
        yaml_file = self.dir_path / "thermal_properties.yaml"
        yaml_file.write_text(content, encoding="utf-8")

        data = PhononParser.get_phonon_data(self.dir_path)
        self.assertIsNotNone(data)
        self.assertEqual(data["temperatures"], [0.0, 10.0])
        self.assertEqual(data["free_energy"], [15.1234, 15.1012])
        self.assertEqual(data["entropy"], [0.0, 0.0543])
        self.assertEqual(data["heat_capacity"], [0.0, 0.1234])


if __name__ == "__main__":
    unittest.main()
