from __future__ import annotations

import unittest
from pathlib import Path
import tempfile
from backend.app.services.sqlite_workflow_store import WorkflowStore


class TestWorkflowStats(unittest.TestCase):
    def setUp(self) -> None:
        self.test_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.test_dir.name) / "test_workflows.db"
        self.store = WorkflowStore(self.db_path)

    def tearDown(self) -> None:
        self.store = None
        import gc
        gc.collect()
        self.test_dir.cleanup()

    def test_get_stats_empty(self) -> None:
        stats = self.store.get_stats()
        self.assertEqual(stats["total_workflows"], 0)
        self.assertEqual(stats["running_workflows"], 0)
        self.assertEqual(stats["failed_workflows"], 0)
        self.assertEqual(stats["converged_workflows"], 0)
        self.assertEqual(stats["avg_ionic_steps"], 0.0)

    def test_get_stats_aggregated(self) -> None:
        # Create a mock running workflow
        w1 = {
            "workflow_id": "w1",
            "project_name": "project1",
            "goal": "mlff training",
            "executor": "mlff_training",
            "scenario": "success",
            "auto_apply_fixes": False,
            "job_id": "j1",
            "calc_path": "/path/1",
            "current_stage": 1,
            "job_status": "running",
            "agent_status": "warning",
            "latest_summary": "Calculando...",
            "latest_next_step": "Aguardar",
            "latest_results": {"ionic_steps": 50},
            "job_settings": {},
            "execution_metadata": {},
            "history": []
        }
        
        # Create a mock converged workflow
        w2 = {
            "workflow_id": "w2",
            "project_name": "project2",
            "goal": "relax",
            "executor": "ssh_slurm",
            "scenario": "success",
            "auto_apply_fixes": True,
            "job_id": "j2",
            "calc_path": "/path/2",
            "current_stage": 0,
            "job_status": "converged",
            "agent_status": "converged",
            "latest_summary": "Convergido",
            "latest_next_step": "Pronto",
            "latest_results": {"ionic_steps": 150},
            "job_settings": {},
            "execution_metadata": {},
            "history": []
        }

        self.store.save_workflow(w1)
        self.store.save_workflow(w2)

        stats = self.store.get_stats()
        self.assertEqual(stats["total_workflows"], 2)
        self.assertEqual(stats["running_workflows"], 1)
        self.assertEqual(stats["failed_workflows"], 0)
        self.assertEqual(stats["converged_workflows"], 1)
        # Average of 50 and 150 is 100.0
        self.assertEqual(stats["avg_ionic_steps"], 100.0)


if __name__ == "__main__":
    unittest.main()
