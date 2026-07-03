from __future__ import annotations

import json
import uuid
from pathlib import Path

from .executor import ExecutionJob


class MlffTrainingExecutor:
    executor_name = "mlff_training"

    def __init__(self, base_dir: Path | None = None) -> None:
        app_root = Path(__file__).resolve().parent.parent
        self.base_dir = base_dir or app_root / "mlff_runs"
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

        settings = dict(job_settings or {})
        metadata = {
            "job_id": job_id,
            "project_name": project_name,
            "scenario": scenario,
            "goal": goal,
            "stage": 0,
            "mlff_mode": "train",
            "dataset_source": str(settings.get("mlff_dataset_source") or "dataset_curado_local"),
            "reference_count": int(settings.get("mlff_reference_count") or 24),
            "force_tolerance": float(settings.get("mlff_force_tolerance") or 0.05),
            "temperature_schedule": str(settings.get("mlff_temperature_schedule") or "300K->1200K"),
            "target_rmse": float(settings.get("mlff_target_rmse") or 0.04),
            "min_reference_count": int(settings.get("mlff_min_reference_count") or 40),
        }
        self._write_metadata(calc_dir, metadata)
        self._materialize_stage(calc_dir, metadata)
        return self._build_response(calc_dir, metadata)

    def advance_job(self, job_id: str) -> ExecutionJob:
        calc_dir = self._find_calc_dir(job_id)
        metadata = self._read_metadata(calc_dir)
        metadata["stage"] = int(metadata["stage"]) + 1
        self._write_metadata(calc_dir, metadata)
        self._materialize_stage(calc_dir, metadata)
        return self._build_response(calc_dir, metadata)

    def _find_calc_dir(self, job_id: str) -> Path:
        for metadata_path in self.base_dir.glob("*/mlff_job.json"):
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("job_id") == job_id:
                return metadata_path.parent
        raise FileNotFoundError(f"Workflow MLFF nao encontrado: {job_id}")

    def _materialize_stage(self, calc_dir: Path, metadata: dict[str, object]) -> None:
        stage = int(metadata["stage"])
        scenario = str(metadata["scenario"])
        reference_count = int(metadata["reference_count"])
        force_tolerance = float(metadata["force_tolerance"])
        dataset_source = str(metadata["dataset_source"])
        temperature_schedule = str(metadata["temperature_schedule"])
        target_rmse = float(metadata["target_rmse"])
        min_reference_count = int(metadata["min_reference_count"])

        incar = "\n".join(
            [
                "PREC = Accurate",
                "ENCUT = 520",
                "EDIFF = 1E-6",
                "NSW = 400",
                "IBRION = 0",
                "POTIM = 1.0",
                "ML_LMLFF = .TRUE.",
                f"ML_MODE = {self._stage_name(stage)}",
                "ML_ISTART = 0",
                "ML_MCONF_NEW = 5",
                f"ML_CTIFOR = {force_tolerance:.3f}",
            ]
        )
        (calc_dir / "INCAR").write_text(incar + "\n", encoding="utf-8")
        (calc_dir / "POSCAR").write_text(
            "MLFF training seed\n1.0\n10 0 0\n0 10 0\n0 0 10\nPd H\n1 2\nDirect\n0.0 0.0 0.0\n0.3 0.3 0.3\n0.7 0.7 0.7\n",
            encoding="utf-8",
        )
        (calc_dir / "KPOINTS").write_text("Automatic mesh\n0\nGamma\n1 1 1\n0 0 0\n", encoding="utf-8")
        (calc_dir / "ML_ABN").write_text(
            "\n".join(
                [
                    "# dataset_source=" + dataset_source,
                    "# temperature_schedule=" + temperature_schedule,
                    f"# reference_count={reference_count}",
                    "# mock active-learning batches",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (calc_dir / "submit_vasp.slurm").write_text(
            "\n".join(
                [
                    "#!/bin/bash",
                    "#SBATCH --job-name=mlff-train",
                    "#SBATCH --nodes=1",
                    "#SBATCH --ntasks-per-node=32",
                    "vasp_std > vasp.out",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        report = {
            "mode": "train",
            "stage_name": self._stage_name(stage),
            "dataset_source": dataset_source,
            "reference_count": reference_count,
            "temperature_schedule": temperature_schedule,
            "stage": stage,
            "target_rmse": target_rmse,
            "min_reference_count": min_reference_count,
        }
        if scenario == "failed" and stage == 0:
            (calc_dir / "OUTCAR").write_text(" MLFF training aborted: insufficient reference diversity\n", encoding="utf-8")
            (calc_dir / "OSZICAR").write_text(" 1 F= -.10000 E0= -.09500 d E =-.0100\n", encoding="utf-8")
            report.update(
                {
                    "status": "failed",
                    "train_rmse": None,
                    "test_rmse": None,
                    "completed_batches": 1,
                    "ready_for_production": False,
                }
            )
        elif stage == 0:
            (calc_dir / "OUTCAR").write_text(
                " MLFF reference selection in progress\n"
                f" ML_MB = 1 reference_count = {reference_count}\n",
                encoding="utf-8",
            )
            (calc_dir / "OSZICAR").write_text(" 1 F= -.12000 E0= -.11000 d E =-.0050\n", encoding="utf-8")
            report.update(
                {
                    "status": "running",
                    "train_rmse": 0.180,
                    "test_rmse": 0.245,
                    "completed_batches": 2,
                    "ready_for_production": False,
                }
            )
        elif stage == 1:
            (calc_dir / "OUTCAR").write_text(
                " MLFF training in progress\n"
                " active-learning batch optimization running\n",
                encoding="utf-8",
            )
            (calc_dir / "OSZICAR").write_text(" 8 F= -.30000 E0= -.28500 d E =-.0012\n", encoding="utf-8")
            report.update(
                {
                    "status": "running",
                    "train_rmse": 0.052,
                    "test_rmse": 0.071,
                    "completed_batches": 5,
                    "ready_for_production": False,
                }
            )
        else:
            (calc_dir / "OUTCAR").write_text(
                " reached required accuracy \n"
                " free  energy   TOTEN  =      -40.1250 eV\n"
                " MLFF validation converged after active learning iterations\n",
                encoding="utf-8",
            )
            (calc_dir / "OSZICAR").write_text(" 12 F= -.40125 E0= -.39800 d E =-.0001\n", encoding="utf-8")
            (calc_dir / "ML_FFN").write_text("# mock trained force-field payload\n", encoding="utf-8")
            report.update(
                {
                    "status": "converged",
                    "train_rmse": 0.021,
                    "test_rmse": 0.034,
                    "completed_batches": 7,
                    "ready_for_production": reference_count >= min_reference_count and 0.034 <= target_rmse,
                }
            )

        (calc_dir / "ML_LOG.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    def _build_response(self, calc_dir: Path, metadata: dict[str, object]) -> ExecutionJob:
        stage = int(metadata["stage"])
        scenario = str(metadata["scenario"])
        status = self._infer_status(stage, scenario)
        return ExecutionJob(
            job_id=str(metadata["job_id"]),
            calc_path=str(calc_dir),
            scenario=scenario,
            stage=stage,
            status=status,
            message=self._build_message(status),
            metadata={
                "executor": self.executor_name,
                "workflow_kind": "mlff_training",
                "mlff_mode": "train",
                "dataset_source": str(metadata["dataset_source"]),
                "reference_count": int(metadata["reference_count"]),
                "force_tolerance": float(metadata["force_tolerance"]),
                "temperature_schedule": str(metadata["temperature_schedule"]),
                "target_rmse": float(metadata["target_rmse"]),
                "min_reference_count": int(metadata["min_reference_count"]),
                "current_stage_name": self._stage_name(stage),
                "workflow_stages": ["select", "train", "validate"],
                "local_path": str(calc_dir),
                "dry_run": True,
            },
        )

    @staticmethod
    def _infer_status(stage: int, scenario: str) -> str:
        if scenario == "failed" and stage == 0:
            return "failed"
        if stage in {0, 1}:
            return "running"
        return "converged"

    @staticmethod
    def _build_message(status: str) -> str:
        if status == "failed":
            return "Workflow MLFF falhou durante a montagem inicial do treino."
        if status == "running":
            return "Workflow MLFF em treino, acumulando estruturas de referencia."
        return "Workflow MLFF concluiu o treino inicial do potencial."

    @staticmethod
    def _stage_name(stage: int) -> str:
        stages = ["select", "train", "validate"]
        return stages[stage] if stage < len(stages) else stages[-1]

    @staticmethod
    def _write_metadata(calc_dir: Path, metadata: dict[str, object]) -> None:
        (calc_dir / "mlff_job.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    @staticmethod
    def _read_metadata(calc_dir: Path) -> dict[str, object]:
        return json.loads((calc_dir / "mlff_job.json").read_text(encoding="utf-8"))
