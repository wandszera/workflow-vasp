from __future__ import annotations

import unittest
from pathlib import Path
import tempfile
from backend.app.services.elastic_parser import ElasticParser


class TestElasticParser(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.test_dir.name)

    def tearDown(self) -> None:
        self.test_dir.cleanup()

    def test_get_elastic_data_missing(self) -> None:
        data = ElasticParser.get_elastic_data(self.dir_path)
        self.assertIsNone(data)

    def test_get_elastic_data_success(self) -> None:
        # Mock OUTCAR containing stiffness tensor block
        outcar_content = """Some text before the block
 TOTAL ELASTIC STIFFNESS TENSOR (kBar)
 Direction     XX          YY          ZZ          XY          YZ          ZX
 --------------------------------------------------------------------------
 XX        1200.0000    200.0000    200.0000      0.0000      0.0000      0.0000
 YY         200.0000   1200.0000    200.0000      0.0000      0.0000      0.0000
 ZZ         200.0000    200.0000   1200.0000      0.0000      0.0000      0.0000
 XY           0.0000      0.0000      0.0000    400.0000      0.0000      0.0000
 YZ           0.0000      0.0000      0.0000      0.0000    400.0000      0.0000
 ZX           0.0000      0.0000      0.0000      0.0000      0.0000    400.0000
 Some text after
"""
        outcar = self.dir_path / "OUTCAR"
        outcar.write_text(outcar_content, encoding="utf-8")

        data = ElasticParser.get_elastic_data(self.dir_path)
        self.assertIsNotNone(data)
        
        # Matrix values converted to GPa (kBar / 10):
        # Diagonal XX, YY, ZZ: 120 GPa. Diagonal XY, YZ, ZX: 40 GPa.
        # Off-diagonal XY/YZ/ZX: 20 GPa.
        self.assertEqual(data["matrix"][0][0], 120.0)
        self.assertEqual(data["matrix"][0][1], 20.0)
        self.assertEqual(data["matrix"][3][3], 40.0)

        # Voigt Bulk Modulus: (120*3 + 2*(20*3)) / 9 = (360 + 120) / 9 = 480 / 9 = 53.33 GPa
        self.assertAlmostEqual(data["bulk_modulus"], 53.33, places=1)


if __name__ == "__main__":
    unittest.main()
