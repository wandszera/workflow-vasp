from __future__ import annotations

import unittest
from pathlib import Path
import tempfile
from backend.app.services.error_recovery import ErrorRecoveryService


class TestErrorRecovery(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.test_dir.name)

    def tearDown(self) -> None:
        self.test_dir.cleanup()

    def test_detect_no_files(self) -> None:
        res = ErrorRecoveryService.detect_and_fix_errors(self.dir_path)
        self.assertFalse(res["error_detected"])

    def test_detect_edddav_and_fix(self) -> None:
        # Create INCAR
        incar = self.dir_path / "INCAR"
        incar.write_text("ALGO = Normal\nEDIFF = 1e-5\n", encoding="utf-8")

        # Create OUTCAR with error signature
        outcar = self.dir_path / "OUTCAR"
        outcar.write_text("Warning: EDDDAV: Call to ZHEGV failed\n", encoding="utf-8")

        res = ErrorRecoveryService.detect_and_fix_errors(self.dir_path)
        self.assertTrue(res["error_detected"])
        self.assertEqual(res["error_type"], "EDDDAV")
        self.assertTrue(res["fix_applied"])

        # Assert INCAR has been patched
        incar_content = incar.read_text(encoding="utf-8")
        self.assertIn("ALGO = Fast", incar_content)


if __name__ == "__main__":
    unittest.main()
