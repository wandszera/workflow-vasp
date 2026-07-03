from __future__ import annotations

import json
import shutil
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.cluster_config import load_cluster_config
from backend.app.services.ecn_service import EcnService
from backend.app.services.executor_registry import ExecutorRegistry
from backend.app.services.mlff_training_executor import MlffTrainingExecutor
from backend.app.services.mock_cluster import MockClusterService
from backend.app.services.sqlite_workflow_store import WorkflowStore
from backend.app.services.ssh_slurm_executor import SshSlurmExecutor
from backend.app.services.vasp_agent import VaspWorkflowAgent
from backend.app.services.vasp_analysis_service import VaspAnalysisService
from backend.app.services.vasp_template_service import VaspTemplateService
from backend.app.services.workflow_service import WorkflowService


class VaspWorkflowAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = VaspWorkflowAgent()
        self.workspace_tmp = Path(__file__).resolve().parent / ".tmp"
        self.workspace_tmp.mkdir(exist_ok=True)

    def make_calc_dir(self) -> Path:
        calc_dir = self.workspace_tmp / str(uuid.uuid4())
        calc_dir.mkdir(parents=True, exist_ok=False)
        self.addCleanup(lambda: shutil.rmtree(calc_dir, ignore_errors=True))
        return calc_dir

    def test_detects_converged_run(self) -> None:
        root = self.make_calc_dir()
        (root / "INCAR").write_text("NSW = 100\n", encoding="utf-8")
        (root / "OUTCAR").write_text(
            " reached required accuracy \n free  energy   TOTEN  =      -10.5000 eV\n",
            encoding="utf-8",
        )

        response = self.agent.inspect(str(root), goal="geometry optimization")

        self.assertEqual(response.status, "converged")
        self.assertEqual(response.extracted_results["final_energy_ev"], -10.5)

    def test_suggests_fix_for_zbrent(self) -> None:
        root = self.make_calc_dir()
        (root / "INCAR").write_text("NSW = 80\n", encoding="utf-8")
        (root / "OUTCAR").write_text(" ZBRENT: fatal error in bracketing \n", encoding="utf-8")

        response = self.agent.inspect(str(root), apply_fixes=False)

        self.assertEqual(response.status, "failed")
        self.assertIn("ZBRENT fatal error", response.detected_errors)
        self.assertTrue(any("POTIM" in fix.description or "Reduzir POTIM" in fix.description for fix in response.suggested_fixes))

    def test_prepares_dos_heuristic(self) -> None:
        root = self.make_calc_dir()
        (root / "INCAR").write_text("NSW = 60\n", encoding="utf-8")

        response = self.agent.inspect(str(root), goal="run DOS after optimization", apply_fixes=False)

        descriptions = [fix.description for fix in response.suggested_fixes]
        self.assertTrue(any("DOS" in description for description in descriptions))

    def test_interprets_mlff_validation_status(self) -> None:
        root = self.make_calc_dir()
        (root / "INCAR").write_text("ML_LMLFF = .TRUE.\nML_MODE = validate\n", encoding="utf-8")
        (root / "ML_LOG.json").write_text(
            json.dumps(
                {
                    "status": "converged",
                    "stage_name": "validate",
                    "reference_count": 64,
                    "min_reference_count": 40,
                    "train_rmse": 0.02,
                    "test_rmse": 0.03,
                    "target_rmse": 0.04,
                    "ready_for_production": True,
                }
            ),
            encoding="utf-8",
        )

        response = self.agent.inspect(str(root), goal="mlff training")

        self.assertEqual(response.status, "converged")
        self.assertTrue(response.extracted_results["ml_ready_for_production"])
        self.assertIn("Promover o potencial", response.next_step)

    def test_scientific_workflow_heuristics(self) -> None:
        # Band structure without CHGCAR
        root = self.make_calc_dir()
        (root / "INCAR").write_text("ICHARG = 11\nNSW = 0\n", encoding="utf-8")
        response = self.agent.inspect(str(root), goal="band structure evaluation")
        self.assertIn("Missing CHGCAR density for band structure run", response.detected_errors)
        self.assertTrue(any("densidade CHGCAR" in fix.description for fix in response.suggested_fixes))

        # Band structure with ICHARG != 11
        root2 = self.make_calc_dir()
        (root2 / "INCAR").write_text("ICHARG = 2\n", encoding="utf-8")
        (root2 / "CHGCAR").write_text("Mock CHGCAR\n", encoding="utf-8")
        response2 = self.agent.inspect(str(root2), goal="band structure evaluation")
        self.assertTrue(any("Forcar ICHARG=11" in fix.description for fix in response2.suggested_fixes))

        # NEB without IMAGES
        root3 = self.make_calc_dir()
        (root3 / "INCAR").write_text("NSW = 100\n", encoding="utf-8")
        response3 = self.agent.inspect(str(root3), goal="neb calculation")
        self.assertTrue(any("IMAGES=3" in fix.description for fix in response3.suggested_fixes))

        # Phonons with loose EDIFF
        root4 = self.make_calc_dir()
        (root4 / "INCAR").write_text("EDIFF = 1e-4\nEDIFFG = -0.05\n", encoding="utf-8")
        response4 = self.agent.inspect(str(root4), goal="phonon calculation")
        self.assertIn("Phonon relaxation precision below threshold (EDIFF > 1e-6)", response4.detected_errors)
        self.assertIn("Phonon relaxation force threshold too loose (EDIFFG < -0.01)", response4.detected_errors)



class VaspAnalysisServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = VaspAnalysisService()
        self.workspace_tmp = Path(__file__).resolve().parent / ".analysis_tmp"
        self.workspace_tmp.mkdir(exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.workspace_tmp, ignore_errors=True)

    def make_calc_dir(self) -> Path:
        calc_dir = self.workspace_tmp / str(uuid.uuid4())
        calc_dir.mkdir(parents=True, exist_ok=False)
        return calc_dir

    def test_generates_analysis_bundle_from_vasp_files(self) -> None:
        calc_dir = self.make_calc_dir()
        (calc_dir / "POSCAR").write_text(
            "POSCAR\n1.0\n1 0 0\n0 1 0\n0 0 1\nH\n1\nDirect\n0.0 0.0 0.0\n",
            encoding="utf-8",
        )
        (calc_dir / "CONTCAR").write_text(
            "CONTCAR\n1.0\n1 0 0\n0 1 0\n0 0 1\nH\n1\nDirect\n0.1 0.0 0.0\n",
            encoding="utf-8",
        )
        (calc_dir / "OUTCAR").write_text(
            " reached required accuracy \n free  energy   TOTEN  =      -11.5000 eV\n",
            encoding="utf-8",
        )
        (calc_dir / "OSZICAR").write_text(" 10 F= -.11500 E0= -.11000 d E =-.0001\n", encoding="utf-8")
        (calc_dir / "CHGCAR").write_text("charge density\n", encoding="utf-8")

        results = self.service.analyze_workflow(str(calc_dir))

        self.assertEqual(len(results), 10)
        energy_summary = next(result for result in results if result["tool"] == "energy_summary")
        structure_diff = next(result for result in results if result["tool"] == "structure_diff")
        recommendation = next(result for result in results if result["tool"] == "next_calculation_recommendation")
        self.assertEqual(energy_summary["status"], "ready")
        self.assertEqual(energy_summary["details"]["final_energy_ev"], -11.5)
        self.assertEqual(structure_diff["status"], "warning")
        self.assertIn(
            recommendation["details"]["recommended_step"],
            {"revisar_relaxacao", "rodar_dos", "rodar_phonons", "validar_artefatos"},
        )

    def test_reports_mlff_quality_and_recommends_promotion(self) -> None:
        calc_dir = self.make_calc_dir()
        (calc_dir / "INCAR").write_text("ML_LMLFF = .TRUE.\nML_MODE = validate\n", encoding="utf-8")
        (calc_dir / "OUTCAR").write_text(
            " reached required accuracy \n free  energy   TOTEN  =      -11.5000 eV\n",
            encoding="utf-8",
        )
        (calc_dir / "OSZICAR").write_text(" 10 F= -.11500 E0= -.11000 d E =-.0001\n", encoding="utf-8")
        (calc_dir / "ML_LOG.json").write_text(
            json.dumps(
                {
                    "status": "converged",
                    "stage_name": "validate",
                    "reference_count": 64,
                    "min_reference_count": 40,
                    "train_rmse": 0.021,
                    "test_rmse": 0.034,
                    "target_rmse": 0.04,
                    "ready_for_production": True,
                }
            ),
            encoding="utf-8",
        )

        results = self.service.analyze_workflow(str(calc_dir))

        mlff_quality = next(result for result in results if result["tool"] == "mlff_quality_check")
        recommendation = next(result for result in results if result["tool"] == "next_calculation_recommendation")
        self.assertEqual(mlff_quality["status"], "ready")
        self.assertTrue(mlff_quality["details"]["ready_for_production"])
        self.assertEqual(recommendation["details"]["recommended_step"], "promover_mlff")

    def test_computes_binding_energy_from_target_and_references(self) -> None:
        target_dir = self.make_calc_dir()
        reference_a_dir = self.make_calc_dir()
        reference_b_dir = self.make_calc_dir()

        (target_dir / "OUTCAR").write_text(
            " reached required accuracy \n free  energy   TOTEN  =      -25.0000 eV\n",
            encoding="utf-8",
        )
        (reference_a_dir / "OUTCAR").write_text(
            " reached required accuracy \n free  energy   TOTEN  =      -10.0000 eV\n",
            encoding="utf-8",
        )
        (reference_b_dir / "OUTCAR").write_text(
            " reached required accuracy \n free  energy   TOTEN  =      -12.5000 eV\n",
            encoding="utf-8",
        )

        result = self.service.compute_binding_energy(
            target_calc_path=target_dir,
            reference_calc_paths=[reference_a_dir, reference_b_dir],
        )

        self.assertEqual(result["binding_energy_ev"], -2.5)
        self.assertEqual(result["reference_count"], 2)

    def test_neb_path_check_and_band_gap_check(self) -> None:
        calc_dir = self.make_calc_dir()
        
        # Test NEB path check when images are not present
        results = self.service.analyze_workflow(str(calc_dir))
        neb_check = next(result for result in results if result["tool"] == "neb_path_check")
        self.assertEqual(neb_check["status"], "unavailable")
        self.assertEqual(neb_check["details"]["image_count"], 0)

        # Test NEB path check when images are present and converged
        for img in range(5):
            img_dir = calc_dir / f"{img:02d}"
            img_dir.mkdir()
            (img_dir / "OUTCAR").write_text(" reached required accuracy \n NEB: max force  0.01500\n", encoding="utf-8")
        
        # Also test Band Gap check with eigenvalues present
        (calc_dir / "OUTCAR").write_text(
            " E-fermi :      4.5200     XC(E_c)=-123.45\n"
            " k-point   1 :       0.0000    0.0000    0.0000\n"
            "  band No.  band energies     occupation\n"
            "      1     -10.5000      2.0000\n"
            "      2      -5.2000      2.0000\n"
            "      3       1.5200      2.0000\n"
            "      4       3.8400      0.0000\n"
            "      5       6.1000      0.0000\n",
            encoding="utf-8"
        )
        (calc_dir / "INCAR").write_text("ICHARG = 11\n", encoding="utf-8")

        results = self.service.analyze_workflow(str(calc_dir))
        neb_check = next(result for result in results if result["tool"] == "neb_path_check")
        self.assertEqual(neb_check["status"], "ready")
        self.assertEqual(neb_check["details"]["image_count"], 5)
        self.assertEqual(neb_check["details"]["converged_images_count"], 5)
        self.assertEqual(neb_check["details"]["max_force"], 0.015)

        band_gap_check = next(result for result in results if result["tool"] == "band_gap_check")
        self.assertEqual(band_gap_check["status"], "ready")
        self.assertEqual(band_gap_check["details"]["band_gap_ev"], 2.32) # 3.84 - 1.52 = 2.32


class EcnServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = EcnService()
        self.workspace_tmp = Path(__file__).resolve().parent / ".ecn_tmp"
        self.workspace_tmp.mkdir(exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.workspace_tmp, ignore_errors=True)

    def test_computes_ecn_from_simple_poscar(self) -> None:
        poscar = self.workspace_tmp / "POSCAR"
        poscar.write_text(
            "\n".join(
                [
                    "Pd2",
                    "1.0",
                    "10.0 0.0 0.0",
                    "0.0 10.0 0.0",
                    "0.0 0.0 10.0",
                    "Pd",
                    "2",
                    "Direct",
                    "0.0 0.0 0.0",
                    "0.2 0.0 0.0",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        result = self.service.compute_from_poscar(poscar)

        self.assertEqual(result["n_atoms"], 2)
        self.assertEqual(result["species_labels"], ["Pd"])
        self.assertEqual(result["species_counts"], [2])
        self.assertEqual(len(result["ecn_by_atom"]), 2)
        self.assertTrue(all(value > 0.0 for value in result["ecn_by_atom"]))
        self.assertGreater(result["average_ecn"], 0.0)
        self.assertEqual(result["supercell_atom_count"], 250)


if __name__ == "__main__":
    unittest.main()


class MockClusterServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace_tmp = Path(__file__).resolve().parent / ".mock_cluster_tmp"
        self.workspace_tmp.mkdir(exist_ok=True)
        self.service = MockClusterService(base_dir=self.workspace_tmp)

    def tearDown(self) -> None:
        shutil.rmtree(self.workspace_tmp, ignore_errors=True)

    def test_creates_running_job_and_advances_to_converged(self) -> None:
        response = self.service.create_job(
            project_name="demo_run",
            scenario="running",
            goal="geometry optimization",
        )

        self.assertEqual(response.status, "running")
        self.assertTrue((Path(response.calc_path) / "OSZICAR").exists())

        advanced = self.service.advance_job(response.job_id)

        self.assertEqual(advanced.status, "converged")
        self.assertTrue((Path(advanced.calc_path) / "OUTCAR").exists())

    def test_creates_error_scenario_for_agent_debugging(self) -> None:
        response = self.service.create_job(
            project_name="demo_error",
            scenario="zbrent_error",
            goal="geometry optimization",
        )

        outcar = (Path(response.calc_path) / "OUTCAR").read_text(encoding="utf-8")
        self.assertIn("ZBRENT", outcar)


class WorkflowServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace_tmp = Path(__file__).resolve().parent / ".workflow_tmp"
        self.mock_runs_dir = self.workspace_tmp / "mock_runs"
        self.store_path = self.workspace_tmp / "workflows.db"
        self.mock_runs_dir.mkdir(parents=True, exist_ok=True)

        self.service = WorkflowService(
            executor=MockClusterService(base_dir=self.mock_runs_dir),
            agent=VaspWorkflowAgent(),
            store=WorkflowStore(db_path=self.store_path),
            executor_registry=ExecutorRegistry(
                mock_executor=MockClusterService(base_dir=self.mock_runs_dir),
                ssh_slurm_executor=SshSlurmExecutor(base_dir=self.workspace_tmp / "remote_runs"),
                mlff_training_executor=MlffTrainingExecutor(base_dir=self.workspace_tmp / "mlff_runs"),
            ),
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.workspace_tmp, ignore_errors=True)

    def test_creates_persisted_workflow(self) -> None:
        workflow = self.service.create_workflow(
            project_name="pd_h2_demo",
            executor_name="mock",
            scenario="success",
            goal="geometry optimization",
            auto_apply_fixes=False,
        )

        self.assertEqual(workflow.job_status, "converged")
        self.assertEqual(workflow.agent_status, "converged")
        self.assertEqual(len(workflow.history), 1)
        self.assertTrue(self.store_path.exists())

    def test_advances_workflow_and_appends_history(self) -> None:
        workflow = self.service.create_workflow(
            project_name="pd_h2_demo",
            executor_name="mock",
            scenario="running",
            goal="geometry optimization",
            auto_apply_fixes=False,
        )

        advanced = self.service.advance_workflow(workflow.workflow_id)

        self.assertEqual(advanced.job_status, "converged")
        self.assertEqual(advanced.current_stage, 1)
        self.assertEqual(len(advanced.history), 2)

    def test_creates_workflow_with_ssh_slurm_executor(self) -> None:
        workflow = self.service.create_workflow(
            project_name="pd_h2_remote",
            executor_name="ssh_slurm",
            scenario="running",
            goal="geometry optimization",
            auto_apply_fixes=False,
            job_settings={
                "structure_source": "Test structure\n1.0\n1 0 0\n0 1 0\n0 0 1\nH\n1\nDirect\n0 0 0\n",
                "kpoints_mesh": [3, 3, 1],
                "calculation_type": "relax",
            },
        )

        self.assertEqual(workflow.executor, "ssh_slurm")
        self.assertIn("ssh_target", workflow.execution_metadata)
        self.assertTrue(Path(workflow.calc_path, "submit_vasp.slurm").exists())
        self.assertEqual(workflow.job_settings["kpoints_mesh"], [3, 3, 1])
        self.assertTrue(Path(workflow.calc_path, "POSCAR").exists())
        self.assertTrue(Path(workflow.calc_path, "KPOINTS").exists())


class SshSlurmExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace_tmp = Path(__file__).resolve().parent / ".ssh_executor_tmp"
        self.workspace_tmp.mkdir(exist_ok=True)
        self.executor = SshSlurmExecutor(base_dir=self.workspace_tmp)

    def tearDown(self) -> None:
        shutil.rmtree(self.workspace_tmp, ignore_errors=True)

    def test_creates_dry_run_remote_plan(self) -> None:
        job = self.executor.create_job(
            project_name="remote_demo",
            scenario="running",
            goal="run DOS after optimization",
            job_settings={
                "structure_source": "Inline POSCAR\n1.0\n1 0 0\n0 1 0\n0 0 1\nH\n1\nDirect\n0 0 0\n",
                "kpoints_mesh": [5, 5, 5],
                "calculation_type": "dos",
            },
        )

        self.assertEqual(job.metadata["executor"], "ssh_slurm")
        self.assertTrue(Path(job.calc_path, "REMOTE_PLAN.txt").exists())
        self.assertTrue(Path(job.calc_path, "submit_vasp.slurm").exists())
        self.assertTrue(Path(job.calc_path, "job_manifest.json").exists())
        self.assertEqual(job.metadata["template_type"], "dos")
        self.assertIn("OSZICAR", job.metadata["synced_artifacts"])
        self.assertEqual(job.metadata["scheduler_state"], "PENDING_LOCAL_PREP")
        self.assertIn("POSCAR", (Path(job.calc_path) / "job_manifest.json").read_text(encoding="utf-8"))

    def test_uses_real_template_directory_when_named(self) -> None:
        job = self.executor.create_job(
            project_name="substrate_real",
            scenario="running",
            goal="surface relaxation on graphene",
            job_settings={"template_name": "03_substrate_GRPR_OK"},
        )

        self.assertEqual(job.metadata["template_name"], "03_substrate_GRPR_OK")
        self.assertEqual(job.metadata["template_source"], "real")
        incar = Path(job.calc_path, "INCAR").read_text(encoding="utf-8")
        kpoints = Path(job.calc_path, "KPOINTS").read_text(encoding="utf-8")
        script = Path(job.calc_path, "submit_vasp.slurm").read_text(encoding="utf-8")
        self.assertIn("IVDW = 11", incar)
        self.assertIn("4  4  1", kpoints)
        self.assertIn("#SBATCH --partition=simstack", script)

    def test_builds_multistage_recipe_for_aimd_relax_dos_phonons(self) -> None:
        job = self.executor.create_job(
            project_name="multistage_demo",
            scenario="running",
            goal="run aimd then relax then dos then phonons",
            job_settings={"workflow_recipe": "aimd_relax_dos_phonons"},
        )

        self.assertEqual(job.metadata["current_stage_name"], "aimd")
        self.assertEqual(job.metadata["workflow_stages"], ["aimd", "relax", "dos", "phonons"])

        stage_two = self.executor.advance_job(job.job_id)
        self.assertEqual(stage_two.metadata["current_stage_name"], "relax")
        self.assertTrue(Path(stage_two.calc_path, "POSCAR").exists())
        self.assertTrue(Path(stage_two.calc_path, "CHGCAR").exists())

        stage_three = self.executor.advance_job(job.job_id)
        self.assertEqual(stage_three.metadata["current_stage_name"], "dos")
        self.assertTrue(Path(stage_three.calc_path, "STAGE_HANDOFF.txt").exists())

        stage_four = self.executor.advance_job(job.job_id)
        self.assertEqual(stage_four.metadata["current_stage_name"], "phonons")

    def test_builds_recipe_band_structure(self) -> None:
        job = self.executor.create_job(
            project_name="band_demo",
            scenario="success",
            goal="band structure calculation",
            job_settings={"workflow_recipe": "band_structure"},
        )
        self.assertEqual(job.metadata["current_stage_name"], "relax")
        self.assertEqual(job.metadata["workflow_stages"], ["relax", "scf", "band"])

        stage_two = self.executor.advance_job(job.job_id)
        self.assertEqual(stage_two.metadata["current_stage_name"], "scf")

        stage_three = self.executor.advance_job(job.job_id)
        self.assertEqual(stage_three.metadata["current_stage_name"], "band")
        self.assertTrue(Path(stage_three.calc_path, "STAGE_HANDOFF.txt").exists())
        self.assertIn("ICHARG = 11", Path(stage_three.calc_path, "INCAR").read_text(encoding="utf-8"))

    def test_builds_recipe_aimd(self) -> None:
        job = self.executor.create_job(
            project_name="aimd_demo",
            scenario="success",
            goal="aimd calculation",
            job_settings={"workflow_recipe": "aimd"},
        )
        self.assertEqual(job.metadata["current_stage_name"], "relax")
        self.assertEqual(job.metadata["workflow_stages"], ["relax", "aimd"])

        stage_two = self.executor.advance_job(job.job_id)
        self.assertEqual(stage_two.metadata["current_stage_name"], "aimd")

    def test_builds_recipe_neb(self) -> None:
        job = self.executor.create_job(
            project_name="neb_demo",
            scenario="success",
            goal="neb calculation",
            job_settings={"workflow_recipe": "neb"},
        )
        self.assertEqual(job.metadata["current_stage_name"], "relax_endpoints")
        self.assertEqual(job.metadata["workflow_stages"], ["relax_endpoints", "neb"])

        stage_two = self.executor.advance_job(job.job_id)
        self.assertEqual(stage_two.metadata["current_stage_name"], "neb")
        self.assertTrue(Path(stage_two.calc_path, "STAGE_HANDOFF.txt").exists())
        # Check image folders
        for img in range(5):
            self.assertTrue(Path(stage_two.calc_path, f"{img:02d}", "POSCAR").exists())

    def test_builds_recipe_phonons(self) -> None:
        job = self.executor.create_job(
            project_name="phonon_demo",
            scenario="success",
            goal="phonon calculation",
            job_settings={"workflow_recipe": "phonons"},
        )
        self.assertEqual(job.metadata["current_stage_name"], "relax_high_prec")
        self.assertEqual(job.metadata["workflow_stages"], ["relax_high_prec", "phonons"])

        stage_two = self.executor.advance_job(job.job_id)
        self.assertEqual(stage_two.metadata["current_stage_name"], "phonons")

    def test_builds_recipe_surface_adsorption(self) -> None:
        job = self.executor.create_job(
            project_name="adsorption_demo",
            scenario="success",
            goal="surface adsorption calculation",
            job_settings={"workflow_recipe": "surface_adsorption"},
        )
        self.assertEqual(job.metadata["current_stage_name"], "surface_relax")
        self.assertEqual(job.metadata["workflow_stages"], ["surface_relax", "adsorbate_relax", "adsorption_relax", "binding_energy"])

        stage_two = self.executor.advance_job(job.job_id)
        self.assertEqual(stage_two.metadata["current_stage_name"], "adsorbate_relax")

        stage_three = self.executor.advance_job(job.job_id)
        self.assertEqual(stage_three.metadata["current_stage_name"], "adsorption_relax")

        stage_four = self.executor.advance_job(job.job_id)
        self.assertEqual(stage_four.metadata["current_stage_name"], "binding_energy")
        self.assertTrue(Path(stage_four.calc_path, "STAGE_HANDOFF.txt").exists())

    def test_builds_recipe_mlff_complete(self) -> None:
        job = self.executor.create_job(
            project_name="mlff_demo",
            scenario="success",
            goal="mlff complete workflow",
            job_settings={"workflow_recipe": "mlff_complete"},
        )
        self.assertEqual(job.metadata["current_stage_name"], "mlff_select")
        self.assertEqual(job.metadata["workflow_stages"], ["mlff_select", "mlff_train", "mlff_validate"])

        stage_two = self.executor.advance_job(job.job_id)
        self.assertEqual(stage_two.metadata["current_stage_name"], "mlff_train")

        stage_three = self.executor.advance_job(job.job_id)
        self.assertEqual(stage_three.metadata["current_stage_name"], "mlff_validate")

    def test_syncs_remote_artifacts_back_to_local_workflow(self) -> None:
        job = self.executor.create_job(
            project_name="remote_sync",
            scenario="running",
            goal="geometry optimization",
        )

        advanced = self.executor.advance_job(job.job_id)

        self.assertEqual(advanced.status, "converged")
        self.assertIn("OUTCAR", advanced.metadata["synced_artifacts"])
        self.assertIn("CONTCAR", advanced.metadata["synced_artifacts"])
        self.assertTrue(Path(advanced.calc_path, "remote_sync_manifest.json").exists())
        sync_manifest = json.loads(Path(advanced.calc_path, "remote_sync_manifest.json").read_text(encoding="utf-8"))
        self.assertIn("downloaded", sync_manifest)
        self.assertIn("missing", sync_manifest)

    def test_lists_cluster_jobs_in_dry_run_mode(self) -> None:
        self.executor.create_job(
            project_name="queued_demo",
            scenario="running",
            goal="geometry optimization",
        )

        jobs = self.executor.list_cluster_jobs()

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["name"], "queued_demo")
        self.assertIn(jobs[0]["state"], {"PENDING_LOCAL_PREP", "SUBMITTED"})

    def test_parses_cluster_jobs_from_scheduler_output(self) -> None:
        class Result:
            def __init__(self, stdout: str = "") -> None:
                self.returncode = 0
                self.stdout = stdout
                self.stderr = ""

        def fake_runner(command: list[str], workdir: Path):
            return Result("4321|pd_demo|wand|RUNNING|compute|01:22|2\n8765|dos_demo|alice|PENDING|long|00:00|1\n")

        executor = SshSlurmExecutor(
            base_dir=self.workspace_tmp / "cluster_list",
            dry_run=False,
            command_runner=fake_runner,
        )

        jobs = executor.list_cluster_jobs()

        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["scheduler_job_id"], "4321")
        self.assertEqual(jobs[0]["owner"], "wand")
        self.assertEqual(jobs[0]["state"], "RUNNING")
        self.assertEqual(jobs[1]["queue"], "long")

    def test_loads_cluster_config_from_file(self) -> None:
        config_path = self.workspace_tmp / "cluster_config.json"
        config_path.write_text(
            json.dumps(
                {
                    "ssh_host": "hpc.local",
                    "ssh_user": "wand",
                    "remote_base_dir": "/scratch/wand",
                    "dry_run": False,
                    "identity_file": "C:/keys/id_rsa",
                }
            ),
            encoding="utf-8",
        )

        config = load_cluster_config(config_path)

        self.assertEqual(config.ssh_host, "hpc.local")
        self.assertEqual(config.ssh_user, "wand")
        self.assertFalse(config.dry_run)
        self.assertEqual(config.identity_file, "C:/keys/id_rsa")

    def test_executes_commands_when_dry_run_is_disabled(self) -> None:
        executed_commands: list[list[str]] = []

        class Result:
            def __init__(self, stdout: str = "ok") -> None:
                self.returncode = 0
                self.stdout = stdout
                self.stderr = ""

        def fake_runner(command: list[str], workdir: Path):
            executed_commands.append(command)
            command_text = " ".join(command)
            if "sbatch" in command_text:
                return Result("Submitted batch job 4321\n")
            if "squeue" in command_text:
                return Result("RUNNING\n")
            if "sacct" in command_text:
                return Result("COMPLETED\n")
            if "POTCAR_READY" in command_text or "POTCAR_MISSING" in command_text:
                return Result("POTCAR_READY\n")
            return Result()

        executor = SshSlurmExecutor(
            base_dir=self.workspace_tmp / "real_mode",
            dry_run=False,
            command_runner=fake_runner,
        )

        job = executor.create_job(
            project_name="remote_real",
            scenario="running",
            goal="geometry optimization",
        )

        self.assertFalse(job.metadata["dry_run"])
        self.assertEqual(len(executed_commands), 4)
        self.assertTrue(Path(job.calc_path, "command_log.json").exists())

        advanced = executor.advance_job(job.job_id)

        self.assertEqual(len(executed_commands), 11)
        self.assertIn("OUTCAR", advanced.metadata["synced_artifacts"])
        self.assertEqual(advanced.metadata["scheduler_job_id"], "4321")
        self.assertEqual(advanced.metadata["scheduler_state"], "COMPLETED")

    def test_ssh_slurm_executor_password_provider_and_masking(self) -> None:
        executed_commands: list[list[str]] = []
        class Result:
            def __init__(self) -> None:
                self.returncode = 0
                self.stdout = "Submitted batch job 5555\n"
                self.stderr = ""

        def fake_runner(command: list[str], workdir: Path):
            executed_commands.append(command)
            return Result()

        # Configurar executor com provedor de senha
        executor = SshSlurmExecutor(
            base_dir=self.workspace_tmp / "password_masking",
            dry_run=False,
            command_runner=fake_runner,
            password_provider=lambda: "minha_senha_super_secreta_123",
        )

        job = executor.create_job(
            project_name="passwd_test",
            scenario="running",
            goal="geometry optimization",
        )

        # 1. Assegurar que o comando de execucao real contem a senha bruta passada ao subprocesso
        self.assertTrue(len(executed_commands) > 0)
        self.assertEqual(executed_commands[0][0], "sshpass")
        self.assertEqual(executed_commands[0][1], "-p")
        self.assertEqual(executed_commands[0][2], "minha_senha_super_secreta_123")

        # 2. Assegurar que o plan local REMOTE_PLAN.txt enmascara a senha
        plan_content = Path(job.calc_path, "REMOTE_PLAN.txt").read_text(encoding="utf-8")
        self.assertIn("sshpass -p ******", plan_content)
        self.assertNotIn("minha_senha_super_secreta_123", plan_content)

        # 3. Assegurar que o command_log.json enmascara a senha
        log_content = Path(job.calc_path, "command_log.json").read_text(encoding="utf-8")
        log_data = json.loads(log_content)
        self.assertTrue(len(log_data) > 0)
        self.assertEqual(log_data[0]["command"][0], "sshpass")
        self.assertEqual(log_data[0]["command"][1], "-p")
        self.assertEqual(log_data[0]["command"][2], "******")
        self.assertNotIn("minha_senha_super_secreta_123", log_content)


class MlffTrainingExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace_tmp = Path(__file__).resolve().parent / ".mlff_executor_tmp"
        self.workspace_tmp.mkdir(exist_ok=True)
        self.executor = MlffTrainingExecutor(base_dir=self.workspace_tmp)

    def tearDown(self) -> None:
        shutil.rmtree(self.workspace_tmp, ignore_errors=True)

    def test_creates_mlff_training_job(self) -> None:
        job = self.executor.create_job(
            project_name="mlff_seed",
            scenario="running",
            goal="Treinar MLFF para dataset de adsorcao",
            job_settings={
                "mlff_dataset_source": "aimd_seed_dataset",
                "mlff_reference_count": 32,
                "mlff_force_tolerance": 0.04,
                "mlff_temperature_schedule": "300K->1500K",
            },
        )

        self.assertEqual(job.metadata["workflow_kind"], "mlff_training")
        self.assertEqual(job.metadata["mlff_mode"], "train")
        self.assertEqual(job.status, "running")
        self.assertTrue(Path(job.calc_path, "ML_ABN").exists())
        self.assertTrue(Path(job.calc_path, "ML_LOG.json").exists())
        incar = Path(job.calc_path, "INCAR").read_text(encoding="utf-8")
        self.assertIn("ML_LMLFF = .TRUE.", incar)
        self.assertIn("ML_MODE = select", incar)

    def test_advances_mlff_training_job_to_converged(self) -> None:
        job = self.executor.create_job(
            project_name="mlff_seed",
            scenario="running",
            goal="Treinar MLFF para dataset de adsorcao",
            job_settings={"mlff_reference_count": 48},
        )

        second_stage = self.executor.advance_job(job.job_id)
        self.assertEqual(second_stage.status, "running")
        self.assertEqual(second_stage.metadata["current_stage_name"], "train")

        advanced = self.executor.advance_job(job.job_id)
        self.assertEqual(advanced.status, "converged")
        self.assertEqual(advanced.metadata["current_stage_name"], "validate")
        self.assertTrue(Path(advanced.calc_path, "ML_FFN").exists())
        report = json.loads(Path(advanced.calc_path, "ML_LOG.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "converged")
        self.assertLess(report["test_rmse"], 0.05)
        self.assertTrue(report["ready_for_production"])


class DashboardTests(unittest.TestCase):
    def test_dashboard_root_returns_html(self) -> None:
        client = TestClient(app)
        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Workflow VASP Dashboard", response.text)
        self.assertIn("/static/app.js", response.text)

    def test_analysis_dashboard_returns_html(self) -> None:
        client = TestClient(app)
        response = client.get("/analysis")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Workflow VASP Analises", response.text)
        self.assertIn("/static/app.js", response.text)

    def test_cluster_dashboard_returns_html(self) -> None:
        client = TestClient(app)
        response = client.get("/cluster")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Workflow VASP Cluster", response.text)
        self.assertIn("/static/app.js", response.text)

    def test_cluster_config_endpoint_returns_payload(self) -> None:
        client = TestClient(app)
        response = client.get("/cluster/config")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("ssh_host", payload)
        self.assertIn("ssh_target", payload)
        self.assertIn("dry_run", payload)

    def test_cluster_config_endpoint_updates_payload(self) -> None:
        client = TestClient(app)
        response = client.post(
            "/cluster/config",
            json={
                "ssh_host": "hpc.test.local",
                "ssh_user": "wand",
                "remote_base_dir": "/scratch/wand/vasp",
                "dry_run": True,
                "identity_file": "C:/Users/wand/.ssh/id_rsa",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["ssh_host"], "hpc.test.local")
        self.assertEqual(payload["ssh_user"], "wand")
        self.assertEqual(payload["ssh_target"], "wand@hpc.test.local")
        self.assertEqual(payload["remote_base_dir"], "/scratch/wand/vasp")

    def test_cluster_session_password_endpoint_marks_password_as_loaded(self) -> None:
        client = TestClient(app)
        response = client.post(
            "/cluster/session-password",
            json={"password": "segredo-temporario"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["has_session_password"])

    def test_templates_endpoint_returns_catalog(self) -> None:
        client = TestClient(app)
        response = client.get("/templates")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(any(entry["name"] == "03_substrate_GRPR_OK" for entry in payload))
        self.assertTrue(all("calc_type" in entry for entry in payload))

    def test_cluster_jobs_endpoint_returns_remote_jobs(self) -> None:
        client = TestClient(app)
        create_response = client.post(
            "/workflows/mock",
            json={
                "project_name": "cluster_panel_demo",
                "goal": "geometry optimization",
                "executor": "ssh_slurm",
                "scenario": "running",
            },
        )

        self.assertEqual(create_response.status_code, 200)

        cluster_response = client.get("/cluster/jobs")

        self.assertEqual(cluster_response.status_code, 200)
        payload = cluster_response.json()
        self.assertTrue(any(entry["project_name"] == "cluster_panel_demo" for entry in payload))
        self.assertTrue(all("scheduler_job_id" in entry for entry in payload))

    def test_cluster_jobs_endpoint_accepts_all_scope(self) -> None:
        client = TestClient(app)

        response = client.get("/cluster/jobs?scope=all")

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_workflow_analysis_endpoint_returns_analysis_bundle(self) -> None:
        client = TestClient(app)
        create_response = client.post(
            "/workflows/mock",
            json={
                "project_name": "analysis_demo",
                "goal": "geometry optimization",
                "executor": "ssh_slurm",
                "scenario": "running",
            },
        )

        self.assertEqual(create_response.status_code, 200)
        workflow_id = create_response.json()["workflow_id"]

        analysis_response = client.get(f"/workflows/{workflow_id}/analysis")

        self.assertEqual(analysis_response.status_code, 200)
        payload = analysis_response.json()
        self.assertTrue(any(entry["tool"] == "energy_summary" for entry in payload))
        self.assertTrue(any(entry["tool"] == "regression_check" for entry in payload))
        self.assertTrue(any(entry["tool"] == "run_report" for entry in payload))

    def test_binding_energy_endpoint_returns_energy_difference(self) -> None:
        client = TestClient(app)
        target_response = client.post(
            "/workflows/mock",
            json={
                "project_name": "binding_target",
                "goal": "geometry optimization",
                "executor": "mock",
                "scenario": "success",
            },
        )
        reference_response = client.post(
            "/workflows/mock",
            json={
                "project_name": "binding_reference",
                "goal": "geometry optimization",
                "executor": "mock",
                "scenario": "success",
            },
        )

        self.assertEqual(target_response.status_code, 200)
        self.assertEqual(reference_response.status_code, 200)

        binding_response = client.post(
            "/analysis/binding-energy",
            json={
                "target_workflow_id": target_response.json()["workflow_id"],
                "reference_workflow_ids": [reference_response.json()["workflow_id"]],
            },
        )

        self.assertEqual(binding_response.status_code, 200)
        payload = binding_response.json()
        self.assertIn("binding_energy_ev", payload)
        self.assertEqual(payload["target"]["project_name"], "binding_target")
        self.assertEqual(len(payload["references"]), 1)

    def test_workflow_ecn_endpoint_returns_ecn_bundle(self) -> None:
        client = TestClient(app)
        create_response = client.post(
            "/workflows/mock",
            json={
                "project_name": "ecn_demo",
                "goal": "geometry optimization",
                "executor": "ssh_slurm",
                "scenario": "running",
                "structure_source": "Pd2\n1.0\n10 0 0\n0 10 0\n0 0 10\nPd\n2\nDirect\n0.0 0.0 0.0\n0.2 0.0 0.0\n",
            },
        )

        self.assertEqual(create_response.status_code, 200)
        workflow_id = create_response.json()["workflow_id"]

        ecn_response = client.get(f"/workflows/{workflow_id}/ecn")

        self.assertEqual(ecn_response.status_code, 200)
        payload = ecn_response.json()
        self.assertEqual(payload["project_name"], "ecn_demo")
        self.assertEqual(payload["n_atoms"], 2)
        self.assertEqual(payload["species_labels"], ["Pd"])
        self.assertEqual(payload["species_counts"], [2])
        self.assertEqual(len(payload["ecn_by_atom"]), 2)

    def test_apply_recommendation_endpoint_creates_followup_workflow(self) -> None:
        client = TestClient(app)
        create_response = client.post(
            "/workflows/mock",
            json={
                "project_name": "recommend_demo",
                "goal": "geometry optimization",
                "executor": "ssh_slurm",
                "scenario": "running",
            },
        )

        self.assertEqual(create_response.status_code, 200)
        workflow_id = create_response.json()["workflow_id"]

        recommendation_response = client.post(f"/workflows/{workflow_id}/apply-recommendation")

        self.assertEqual(recommendation_response.status_code, 200)
        payload = recommendation_response.json()
        self.assertEqual(payload["executor"], "ssh_slurm")
        self.assertIn(payload["job_settings"]["calculation_type"], {"relax", "dos", "phonons"})
        self.assertTrue(payload["project_name"].startswith("recommend_demo-"))

    def test_recommendation_preview_endpoint_exposes_materialization_plan(self) -> None:
        client = TestClient(app)
        create_response = client.post(
            "/workflows/mock",
            json={
                "project_name": "recommend_preview_demo",
                "goal": "geometry optimization",
                "executor": "ssh_slurm",
                "scenario": "running",
            },
        )

        self.assertEqual(create_response.status_code, 200)
        workflow_id = create_response.json()["workflow_id"]

        preview_response = client.get(f"/workflows/{workflow_id}/recommendation-preview")

        self.assertEqual(preview_response.status_code, 200)
        payload = preview_response.json()
        self.assertIn(payload["calculation_type"], {"relax", "dos", "phonons"})
        self.assertIn(
            payload["recommended_step"],
            {"continuar_relaxacao", "revisar_relaxacao", "rodar_dos", "rodar_phonons", "validar_artefatos"},
        )
        self.assertIn(payload["structure_origin"], {"POSCAR", "CONTCAR"})
        self.assertTrue(payload["goal"])

    def test_workflow_files_preview_endpoint_returns_job_inputs(self) -> None:
        client = TestClient(app)
        create_response = client.post(
            "/workflows/mock",
            json={
                "project_name": "preview_demo",
                "goal": "geometry optimization",
                "executor": "ssh_slurm",
                "scenario": "running",
                "template_name": "03_substrate_GRPR_OK",
            },
        )

        self.assertEqual(create_response.status_code, 200)
        workflow_id = create_response.json()["workflow_id"]

        preview_response = client.get(f"/workflows/{workflow_id}/files-preview")

        self.assertEqual(preview_response.status_code, 200)
        payload = preview_response.json()
        self.assertTrue(any(entry["name"] == "INCAR" and entry["exists"] for entry in payload))
        self.assertTrue(any(entry["name"] == "submit_vasp.slurm" and entry["exists"] for entry in payload))

    def test_workflow_files_update_endpoint_persists_edits(self) -> None:
        client = TestClient(app)
        create_response = client.post(
            "/workflows/mock",
            json={
                "project_name": "edit_demo",
                "goal": "geometry optimization",
                "executor": "ssh_slurm",
                "scenario": "running",
            },
        )

        self.assertEqual(create_response.status_code, 200)
        workflow = create_response.json()
        workflow_id = workflow["workflow_id"]
        calc_path = Path(workflow["calc_path"])

        update_response = client.post(
            f"/workflows/{workflow_id}/files",
            json={
                "incar": "ENCUT = 700\nNSW = 10\n",
                "kpoints": "Automatic mesh\n0\nGamma\n3 3 1\n0 0 0\n",
            },
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertIn("ENCUT = 700", (calc_path / "INCAR").read_text(encoding="utf-8"))
        self.assertIn("3 3 1", (calc_path / "KPOINTS").read_text(encoding="utf-8"))

        preview_response = client.get(f"/workflows/{workflow_id}/files-preview")
        payload = preview_response.json()
        self.assertTrue(any(entry["name"] == "INCAR" and "ENCUT = 700" in entry["content"] for entry in payload))

    def test_create_workflow_with_multistage_recipe(self) -> None:
        client = TestClient(app)
        response = client.post(
            "/workflows/mock",
            json={
                "project_name": "recipe_demo",
                "goal": "AIMD, optimize structure, calculate DOS and phonons",
                "executor": "ssh_slurm",
                "scenario": "running",
                "workflow_recipe": "aimd_relax_dos_phonons",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["execution_metadata"]["current_stage_name"], "aimd")
        self.assertEqual(payload["execution_metadata"]["workflow_stages"], ["aimd", "relax", "dos", "phonons"])

    def test_create_mlff_training_workflow(self) -> None:
        client = TestClient(app)
        response = client.post(
            "/workflows/mock",
            json={
                "project_name": "mlff_train_demo",
                "goal": "Treinar MLFF para superficies Pd-H",
                "executor": "mlff_training",
                "scenario": "running",
                "mlff_dataset_source": "aimd_seed_dataset",
                "mlff_reference_count": 48,
                "mlff_force_tolerance": 0.03,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["executor"], "mlff_training")
        self.assertEqual(payload["job_status"], "running")
        self.assertEqual(payload["execution_metadata"]["workflow_kind"], "mlff_training")
        self.assertEqual(payload["job_settings"]["mlff_reference_count"], 48)
        self.assertEqual(payload["execution_metadata"]["current_stage_name"], "select")
        self.assertTrue(Path(payload["calc_path"], "ML_LOG.json").exists())

    def test_create_workflow_with_new_recipes(self) -> None:
        client = TestClient(app)
        recipes = {
            "band_structure": ["relax", "scf", "band"],
            "aimd": ["relax", "aimd"],
            "neb": ["relax_endpoints", "neb"],
            "phonons": ["relax_high_prec", "phonons"],
            "surface_adsorption": ["surface_relax", "adsorbate_relax", "adsorption_relax", "binding_energy"],
            "mlff_complete": ["mlff_select", "mlff_train", "mlff_validate"],
        }
        for recipe_name, expected_stages in recipes.items():
            response = client.post(
                "/workflows/mock",
                json={
                    "project_name": f"test_{recipe_name}",
                    "goal": f"Execute {recipe_name} workflow recipe",
                    "executor": "ssh_slurm",
                    "scenario": "running",
                    "workflow_recipe": recipe_name,
                },
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["execution_metadata"]["workflow_stages"], expected_stages)


class VaspTemplateServiceTests(unittest.TestCase):
    def test_lists_real_templates(self) -> None:
        service = VaspTemplateService()
        names = [template["name"] for template in service.list_available_templates()]

        self.assertIn("03_substrate_GRPR_OK", names)
        self.assertIn("Pd4_paw_pbe_500eV_gam_otm_OK", names)
