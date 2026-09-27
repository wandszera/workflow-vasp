import os
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import app, validate_calc_path
from backend.app.services.ssh_slurm_executor import SshSlurmExecutor


class SecurityBoundaryTests(unittest.TestCase):
    def test_public_health_remains_available_with_api_key_configured(self):
        with patch.dict(os.environ, {"VASP_API_KEY": "test-secret"}):
            response = TestClient(app).get("/health")
        self.assertEqual(response.status_code, 200)

    def test_api_routes_require_api_key_when_configured(self):
        with patch.dict(os.environ, {"VASP_API_KEY": "test-secret"}):
            client = TestClient(app)
            self.assertEqual(client.get("/templates").status_code, 401)
            self.assertEqual(client.get("/templates", headers={"X-API-Key": "test-secret"}).status_code, 200)

    def test_calc_path_rejects_paths_outside_allowed_directories(self):
        with self.assertRaises(Exception):
            validate_calc_path(str(Path("..") / ".." / "etc"))

    def test_project_names_reject_shell_metacharacters(self):
        for name in ("bad;name", "$(touch pwned)", "name with spaces", 'name"quoted'):
            with self.assertRaises(ValueError):
                SshSlurmExecutor._sanitize_project_name(name)

    def test_project_names_accept_safe_characters(self):
        self.assertEqual(SshSlurmExecutor._sanitize_project_name("vasp-run_01.v2"), "vasp-run_01.v2")


if __name__ == "__main__":
    unittest.main()
