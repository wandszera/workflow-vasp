from __future__ import annotations

import json
import uuid
from pathlib import Path

from ..schemas import MockJobResponse
from .executor import ExecutionJob


class MockClusterService:
    RECIPE_STAGE_MAP = {
        "aimd_relax_dos_phonons": [
            {"name": "aimd", "calculation_type": "aimd", "goal": "AIMD equilibration"},
            {"name": "relax", "calculation_type": "relax", "goal": "Structural optimization"},
            {"name": "dos", "calculation_type": "dos", "goal": "Density of states"},
            {"name": "phonons", "calculation_type": "phonons", "goal": "Phonon calculation"},
        ],
        "band_structure": [
            {"name": "relax", "calculation_type": "relax", "goal": "Structural optimization"},
            {"name": "scf", "calculation_type": "relax", "goal": "Static charge density run"},
            {"name": "band", "calculation_type": "band", "goal": "Band structure evaluation"},
        ],
        "aimd": [
            {"name": "relax", "calculation_type": "relax", "goal": "Pre-relaxation for AIMD"},
            {"name": "aimd", "calculation_type": "aimd", "goal": "AIMD thermal equilibration"},
        ],
        "neb": [
            {"name": "relax_endpoints", "calculation_type": "relax", "goal": "Otimizar estados inicial e final"},
            {"name": "neb", "calculation_type": "neb", "goal": "Calculo de caminho de transicao NEB"},
        ],
        "phonons": [
            {"name": "relax_high_prec", "calculation_type": "relax", "goal": "Otimizacao estrutural de alta precisao"},
            {"name": "phonons", "calculation_type": "phonons", "goal": "Calculo de forcas e fonons"},
        ],
        "surface_adsorption": [
            {"name": "surface_relax", "calculation_type": "surface_relax", "goal": "Otimizacao da superficie limpa"},
            {"name": "adsorbate_relax", "calculation_type": "relax", "goal": "Otimizacao do adsorbato livre"},
            {"name": "adsorption_relax", "calculation_type": "surface_relax", "goal": "Otimizacao do sistema adsorvido"},
            {"name": "binding_energy", "calculation_type": "dos", "goal": "Analise de energia de ligacao"},
        ],
        "mlff_complete": [
            {"name": "mlff_select", "calculation_type": "mlff_training", "goal": "Selecao ativa de estruturas MLFF"},
            {"name": "mlff_train", "calculation_type": "mlff_training", "goal": "Treinamento do potencial MLFF"},
            {"name": "mlff_validate", "calculation_type": "mlff_training", "goal": "Validacao e producao do MLFF"},
        ]
    }

    def __init__(self, base_dir: Path | None = None) -> None:
        app_root = Path(__file__).resolve().parent.parent
        self.base_dir = base_dir or app_root / "mock_runs"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_job(
        self,
        project_name: str,
        scenario: str,
        goal: str | None = None,
        job_settings: dict[str, object] | None = None,
    ) -> ExecutionJob:
        job_id = str(uuid.uuid4())
        calc_dir = self.base_dir / f"{project_name}_{job_id[:8]}"
        calc_dir.mkdir(parents=True, exist_ok=False)
        settings = job_settings or {}

        metadata = {
            "job_id": job_id,
            "project_name": project_name,
            "scenario": scenario,
            "goal": goal,
            "stage": 0,
            "job_settings": settings,
        }
        metadata["workflow_stages"] = self._build_workflow_stages(goal, settings)
        metadata["current_workflow_stage"] = 0
        stage_def = self._current_stage_definition(metadata)
        metadata["current_stage_name"] = stage_def["name"]

        self._write_metadata(calc_dir, metadata)
        self._materialize_stage(calc_dir, metadata)
        return self._build_response(calc_dir, metadata)

    def advance_job(self, job_id: str) -> ExecutionJob:
        calc_dir = self._find_calc_dir(job_id)
        metadata = self._read_metadata(calc_dir)
        metadata["stage"] = int(metadata["stage"]) + 1
        metadata["current_workflow_stage"] = min(
            int(metadata.get("current_workflow_stage", 0)) + 1,
            max(len(metadata.get("workflow_stages", [])) - 1, 0),
        )
        stage_def = self._current_stage_definition(metadata)
        metadata["current_stage_name"] = stage_def["name"]

        # Handoff simulation
        self._apply_mock_handoff(calc_dir, metadata)

        self._write_metadata(calc_dir, metadata)
        self._materialize_stage(calc_dir, metadata)
        return self._build_response(calc_dir, metadata)

    def _find_calc_dir(self, job_id: str) -> Path:
        for metadata_path in self.base_dir.glob("*/mock_job.json"):
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("job_id") == job_id:
                return metadata_path.parent
        raise FileNotFoundError(f"Mock job nao encontrado: {job_id}")

    def _apply_mock_handoff(self, calc_dir: Path, metadata: dict[str, object]) -> None:
        stage_def = self._current_stage_definition(metadata)
        next_name = stage_def["name"]
        calc_type = stage_def["calculation_type"]

        contcar = calc_dir / "CONTCAR"
        if contcar.exists():
            (calc_dir / "POSCAR").write_text(contcar.read_text(encoding="utf-8"), encoding="utf-8")

        if (calc_dir / "CHGCAR").exists():
            (calc_dir / "STAGE_HANDOFF.txt").write_text(
                f"Using CHGCAR for stage {next_name}.\n", encoding="utf-8"
            )

        if next_name == "neb" or calc_type == "neb":
            images_count = 5
            for img in range(images_count):
                img_dir = calc_dir / f"{img:02d}"
                img_dir.mkdir(parents=True, exist_ok=True)
                (img_dir / "POSCAR").write_text(
                    f"NEB Image {img:02d} structure\n1.0\n8.0 0.0 0.0\n0.0 8.0 0.0\n0.0 0.0 8.0\nH\n1\nDirect\n{0.1*img:.3f} 0.0 0.0\n",
                    encoding="utf-8",
                )
            (calc_dir / "STAGE_HANDOFF.txt").write_text(
                "Generated NEB linear interpolation with 5 images.\n", encoding="utf-8"
            )

    def _materialize_stage(self, calc_dir: Path, metadata: dict[str, object]) -> None:
        scenario = str(metadata["scenario"])
        stage = int(metadata["stage"])
        goal = str(metadata.get("goal") or "")
        stage_def = self._current_stage_definition(metadata)
        stage_name = stage_def["name"]
        calc_type = stage_def["calculation_type"]

        # Default INCAR parameters
        incar_lines = ["ENCUT = 400", "EDIFF = 1E-5", "ISMEAR = 0", "SIGMA = 0.05", "NSW = 80"]

        # Modify INCAR parameters based on calculations
        if calc_type == "dos" or "dos" in goal.lower() or scenario == "dos_ready":
            incar_lines.extend(["ICHARG = 11", "NEDOS = 2000", "NSW = 0"])
        elif calc_type == "aimd" or stage_name == "aimd":
            incar_lines.extend(["IBRION = 0", "NSW = 1000", "TEBEG = 300", "MDALGO = 2"])
        elif calc_type == "neb" or stage_name == "neb":
            incar_lines.extend(["IMAGES = 3", "SPRING = -5.0", "LCLIMB = .TRUE."])
        elif calc_type == "band" or stage_name == "band":
            incar_lines.extend(["ICHARG = 11", "NSW = 0", "LORBIT = 11"])
        elif stage_name == "relax_high_prec":
            incar_lines = ["ENCUT = 500", "EDIFF = 1E-8", "EDIFFG = -0.005", "ISMEAR = 0", "NSW = 150"]
        elif calc_type == "mlff_training" or "mlff" in calc_type or "mlff" in goal.lower():
            incar_lines.extend(["ML_LMLFF = .TRUE.", "NSW = 1000", "IBRION = 0"])
            if stage_name == "mlff_select":
                incar_lines.append("ML_MODE = select")
            elif stage_name == "mlff_train":
                incar_lines.append("ML_MODE = train")
            elif stage_name == "mlff_validate":
                incar_lines.append("ML_MODE = validate")

        (calc_dir / "INCAR").write_text("\n".join(incar_lines) + "\n", encoding="utf-8")

        # Mocking Outputs
        outcar_content = ""
        oszicar_content = ""

        # Default success markers
        if scenario == "success" or scenario == "dos_ready" or (scenario == "running" and stage > 0):
            outcar_content = (
                " reached required accuracy \n"
                f" free  energy   TOTEN  =      {-21.43 - stage * 0.8:.4f} eV\n"
                " number of electron    20.000 magnetization =      2.0000\n"
            )
            oszicar_content = f" {12 + stage * 2} F= {-21.43 - stage * 0.8:.4f} E0= {-21.4 - stage * 0.8:.4f} d E =-.0001\n"

            # If band structure stage, write eigenvalues
            if calc_type == "band" or stage_name == "band":
                outcar_content += (
                    " E-fermi :      4.5200     XC(E_c)=-123.45\n"
                    " spin component 1\n"
                    " k-point   1 :       0.0000    0.0000    0.0000\n"
                    "  band No.  band energies     occupation\n"
                    "      1     -10.5000      2.0000\n"
                    "      2      -5.2000      2.0000\n"
                    "      3       1.5200      2.0000\n"
                    "      4       3.8400      0.0000\n"
                    "      5       6.1000      0.0000\n"
                    " k-point   2 :       0.5000    0.0000    0.0000\n"
                    "  band No.  band energies     occupation\n"
                    "      1     -10.3000      2.0000\n"
                    "      2      -5.0000      2.0000\n"
                    "      3       1.6000      2.0000\n"
                    "      4       3.7000      0.0000\n"
                    "      5       6.3000      0.0000\n"
                )

            # If NEB stage, write OUTCAR in intermediate image subdirs
            if calc_type == "neb" or stage_name == "neb":
                for img in [1, 2, 3]:
                    img_dir = calc_dir / f"{img:02d}"
                    img_dir.mkdir(parents=True, exist_ok=True)
                    (img_dir / "OUTCAR").write_text(
                        " reached required accuracy \n"
                        f" free  energy   TOTEN  =      {-20.5 - img * 0.1:.4f} eV\n"
                        " NEB: max force  0.02456\n",
                        encoding="utf-8",
                    )
                # write endpoints too
                for img in [0, 4]:
                    img_dir = calc_dir / f"{img:02d}"
                    img_dir.mkdir(parents=True, exist_ok=True)
                    (img_dir / "OUTCAR").write_text(" reached required accuracy \n", encoding="utf-8")

            # Write CHGCAR for stages that converged
            (calc_dir / "CHGCAR").write_text("Mock charge density\n", encoding="utf-8")
            (calc_dir / "CONTCAR").write_text(
                "CONTCAR structure\n1.0\n1 0 0\n0 1 0\n0 0 1\nH\n1\nDirect\n0.05 0.0 0.0\n",
                encoding="utf-8",
            )

        elif scenario == "running" and stage == 0:
            oszicar_content = " 1 F= -.12345 E0= -.12000 d E =-.001\n"

        elif scenario == "zbrent_error" and stage == 0:
            outcar_content = " ZBRENT: fatal error in bracketing\n"
            oszicar_content = " 8 F= -.19875 E0= -.19000 d E =-.0002\n"

        # MLFF logs mock
        if calc_type == "mlff_training" or "mlff" in calc_type or "mlff" in goal.lower():
            ml_ready = stage_name == "mlff_validate"
            ml_status = "converged" if ml_ready else "running"
            ml_log_content = {
                "status": ml_status,
                "mode": calc_type,
                "stage_name": stage_name,
                "dataset_source": "mock_dataset",
                "reference_count": 50 if ml_ready else 25,
                "min_reference_count": 40,
                "completed_batches": 10,
                "train_rmse": 0.015,
                "test_rmse": 0.025,
                "target_rmse": 0.035,
                "ready_for_production": ml_ready,
            }
            (calc_dir / "ML_LOG.json").write_text(json.dumps(ml_log_content), encoding="utf-8")
            if ml_ready:
                (calc_dir / "ML_FFN").write_text("Mock MLFF potential file\n", encoding="utf-8")

        self._safe_write(calc_dir / "OUTCAR", outcar_content)
        self._safe_write(calc_dir / "OSZICAR", oszicar_content)

    def _build_response(self, calc_dir: Path, metadata: dict[str, object]) -> ExecutionJob:
        scenario = str(metadata["scenario"])
        stage = int(metadata["stage"])
        status = self._infer_status(scenario, stage)

        stages = metadata.get("workflow_stages", [])
        stage_names = [st.get("name", "") for st in stages]

        return ExecutionJob(
            job_id=str(metadata["job_id"]),
            calc_path=str(calc_dir),
            scenario=scenario,
            stage=stage,
            status=status,
            message=self._build_message(scenario, stage, status),
            metadata={
                "executor": "mock",
                "dry_run": True,
                "local_path": str(calc_dir),
                "workflow_stages": stage_names,
                "current_stage_name": metadata.get("current_stage_name"),
            },
        )

    @staticmethod
    def _infer_status(scenario: str, stage: int) -> str:
        if scenario == "running" and stage == 0:
            return "running"
        if scenario == "zbrent_error" and stage == 0:
            return "failed"
        return "converged"

    @staticmethod
    def _build_message(scenario: str, stage: int, status: str) -> str:
        if scenario == "running" and stage == 0:
            return "Job simulado em execucao, sem convergencia ainda."
        if scenario == "zbrent_error" and stage == 0:
            return "Job simulado falhou com erro numerico para testar autocorrecao."
        if scenario == "dos_ready":
            return "Job simulado pronto para validar um workflow de DOS."
        if status == "converged":
            return "Job simulado convergiu e ja pode ser inspecionado pelo agente."
        return "Job simulado criado."

    @staticmethod
    def _safe_write(path: Path, content: str) -> None:
        if content:
            path.write_text(content, encoding="utf-8")
        elif path.exists():
            path.unlink()

    @staticmethod
    def _write_metadata(calc_dir: Path, metadata: dict[str, object]) -> None:
        (calc_dir / "mock_job.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    @staticmethod
    def _read_metadata(calc_dir: Path) -> dict[str, object]:
        return json.loads((calc_dir / "mock_job.json").read_text(encoding="utf-8"))

    def _build_workflow_stages(self, goal: str | None, settings: dict[str, object]) -> list[dict[str, object]]:
        recipe = settings.get("workflow_recipe")
        if isinstance(recipe, str) and recipe in self.RECIPE_STAGE_MAP:
            return [dict(stage) for stage in self.RECIPE_STAGE_MAP[recipe]]

        inferred = self._infer_calc_type_from_goal(goal)
        return [
            {
                "name": str(settings.get("calculation_type") or inferred),
                "calculation_type": str(settings.get("calculation_type") or inferred),
                "goal": goal or "Single-step VASP workflow",
            }
        ]

    @staticmethod
    def _infer_calc_type_from_goal(goal: str | None) -> str:
        normalized_goal = (goal or "").lower()
        if "aimd" in normalized_goal:
            return "aimd"
        if "dos" in normalized_goal:
            return "dos"
        if "phonon" in normalized_goal:
            return "phonons"
        return "relax"

    def _current_stage_definition(self, metadata: dict[str, object]) -> dict[str, object]:
        stages = metadata.get("workflow_stages", [])
        if not stages:
            return {
                "name": "relax",
                "calculation_type": "relax",
                "goal": metadata.get("goal") or "Single-step VASP workflow",
            }
        index = min(int(metadata.get("current_workflow_stage", 0)), len(stages) - 1)
        return stages[index]
