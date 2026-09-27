from __future__ import annotations

import unittest
from pathlib import Path
from fastapi.testclient import TestClient
import tempfile
import shutil

from backend.app.main import app, workflow_service


class TestDosBandEndpoints(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        mock_runs_dir = Path(__file__).resolve().parents[1] / "app" / "mock_runs"
        mock_runs_dir.mkdir(parents=True, exist_ok=True)
        self.test_dir = tempfile.TemporaryDirectory(dir=mock_runs_dir)
        self.dir_path = Path(self.test_dir.name)

        # Create mock workflow in service store
        self.workflow_data = {
            "workflow_id": "test-dos-band-wf",
            "project_name": "Test DOS Band",
            "calc_path": str(self.dir_path),
            "goal": "relax",
            "executor": "mock",
            "scenario": "relax",
            "auto_apply_fixes": True,
            "job_id": "test-job",
            "job_status": "converged",
            "agent_status": "ready",
            "current_stage": 0,
            "history": [],
            "job_settings": {},
            "execution_metadata": {},
            "settings": {},
            "latest_summary": "Test run",
            "latest_next_step": "None",
            "latest_results": {}
        }
        workflow_service.store.save_workflow(self.workflow_data)

        # Write mock DOSCAR
        self.dos_content = """Mock header line 1
Line 2
Line 3
Line 4
Line 5
   1.00000   2.00000   10   2.50000   1.00000
 -1.00000   0.50000   0.10000
  0.00000   1.20000   0.30000
  1.00000   0.80000   0.50000
"""
        (self.dir_path / "DOSCAR").write_text(self.dos_content, encoding="utf-8")

        # Write mock EIGENVAL
        self.eigenval_content = """Mock header 1
Line 2
Line 3
Line 4
Line 5
  8  2  4
 0.0 0.0 0.0 0.025
1  -5.0000
2  -3.0000
3   1.0000
4   2.0000
 0.5 0.5 0.5 0.025
1  -4.8000
2  -2.9000
3   1.1000
4   2.2000
"""
        (self.dir_path / "EIGENVAL").write_text(self.eigenval_content, encoding="utf-8")

    def tearDown(self) -> None:
        conn = workflow_service.store._connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM workflows WHERE workflow_id = ?", ("test-dos-band-wf",))
        conn.commit()
        conn.close()

        self.test_dir.cleanup()

    def test_get_doscar_file(self) -> None:
        res = self.client.get("/workflows/test-dos-band-wf/file/DOSCAR")
        self.assertEqual(res.status_code, 200)
        self.assertIn("1.00000   2.00000   10", res.text)

    def test_get_eigenval_file(self) -> None:
        res = self.client.get("/workflows/test-dos-band-wf/file/EIGENVAL")
        self.assertEqual(res.status_code, 200)
        self.assertIn("8  2  4", res.text)


if __name__ == "__main__":
    unittest.main()
