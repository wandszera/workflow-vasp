from __future__ import annotations

import json
import re
import subprocess
import uuid
from pathlib import Path
from typing import Callable

from .cluster_config import ClusterConfig, load_cluster_config
from .executor import ExecutionJob
from .vasp_template_service import VaspTemplateService


class SshSlurmExecutor:
    executor_name = "ssh_slurm"
    RECIPE_STAGE_MAP = {
        "aimd_relax_dos_phonons": [
            {"name": "aimd", "calculation_type": "aimd", "goal": "AIMD equilibration", "template_name": None},
            {"name": "relax", "calculation_type": "relax", "goal": "Structural optimization", "template_name": None},
            {"name": "dos", "calculation_type": "dos", "goal": "Density of states", "template_name": None},
            {"name": "phonons", "calculation_type": "phonons", "goal": "Phonon calculation", "template_name": None},
        ],
        "band_structure": [
            {"name": "relax", "calculation_type": "relax", "goal": "Structural optimization", "template_name": None},
            {"name": "scf", "calculation_type": "relax", "goal": "Static charge density run", "template_name": None},
            {"name": "band", "calculation_type": "band", "goal": "Band structure evaluation", "template_name": None},
        ],
        "aimd": [
            {"name": "relax", "calculation_type": "relax", "goal": "Pre-relaxation for AIMD", "template_name": None},
            {"name": "aimd", "calculation_type": "aimd", "goal": "AIMD thermal equilibration", "template_name": None},
        ],
        "neb": [
            {"name": "relax_endpoints", "calculation_type": "relax", "goal": "Otimizar estados inicial e final", "template_name": None},
            {"name": "neb", "calculation_type": "neb", "goal": "Calculo de caminho de transicao NEB", "template_name": None},
        ],
        "phonons": [
            {"name": "relax_high_prec", "calculation_type": "relax", "goal": "Otimizacao estrutural de alta precisao", "template_name": None},
            {"name": "phonons", "calculation_type": "phonons", "goal": "Calculo de forcas e fonons", "template_name": None},
        ],
        "surface_adsorption": [
            {"name": "surface_relax", "calculation_type": "surface_relax", "goal": "Otimizacao da superficie limpa", "template_name": None},
            {"name": "adsorbate_relax", "calculation_type": "relax", "goal": "Otimizacao do adsorbato livre", "template_name": None},
            {"name": "adsorption_relax", "calculation_type": "surface_relax", "goal": "Otimizacao do sistema adsorvido", "template_name": None},
            {"name": "binding_energy", "calculation_type": "dos", "goal": "Analise de energia de ligacao", "template_name": None},
        ],
        "mlff_complete": [
            {"name": "mlff_select", "calculation_type": "mlff_training", "goal": "Selecao ativa de estruturas MLFF", "template_name": None},
            {"name": "mlff_train", "calculation_type": "mlff_training", "goal": "Treinamento do potencial MLFF", "template_name": None},
            {"name": "mlff_validate", "calculation_type": "mlff_training", "goal": "Validacao e producao do MLFF", "template_name": None},
        ]
    }

    def __init__(
        self,
        base_dir: Path | None = None,
        ssh_host: str | None = None,
        ssh_user: str | None = None,
        remote_base_dir: str | None = None,
        dry_run: bool | None = None,
        identity_file: str | None = None,
        config_path: Path | None = None,
        command_runner=None,
        template_service: VaspTemplateService | None = None,
        password_provider: Callable[[], str | None] | None = None,
    ) -> None:
        app_root = Path(__file__).resolve().parent.parent
        self.base_dir = base_dir or app_root / "remote_runs"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        config = load_cluster_config(config_path)
        self.config = ClusterConfig(
            ssh_host=ssh_host or config.ssh_host,
            ssh_user=ssh_user or config.ssh_user,
            remote_base_dir=(remote_base_dir or config.remote_base_dir).rstrip("/"),
            dry_run=config.dry_run if dry_run is None else dry_run,
            identity_file=identity_file if identity_file is not None else config.identity_file,
        )
        self.command_runner = command_runner or self._run_command
        self.template_service = template_service or VaspTemplateService()
        self.password_provider = password_provider

    def list_cluster_jobs(self, scope: str = "user") -> list[dict[str, str | None]]:
        if self.config.dry_run:
            return self._list_dry_run_jobs(scope)

        command = self._cluster_jobs_command(scope)
        result = self.command_runner(command, self.base_dir)
        return self._parse_cluster_jobs_output(result.stdout)

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

        remote_path = f"{self.config.remote_base_dir}/{project_name}_{job_id[:8]}"
        metadata = {
            "job_id": job_id,
            "project_name": project_name,
            "scenario": scenario,
            "goal": goal,
            "stage": 0,
            "remote_path": remote_path,
            "sbatch_script": "submit_vasp.slurm",
            "dry_run": self.config.dry_run,
            "ssh_target": self.config.ssh_target,
            "identity_file": self.config.identity_file,
            "synced_artifacts": [],
            "last_sync_stage": -1,
            "scheduler_job_id": None,
            "scheduler_state": "PENDING_LOCAL_PREP",
            "job_settings": settings,
        }
        metadata["workflow_stages"] = self._build_workflow_stages(goal, settings)
        metadata["current_workflow_stage"] = 0
        stage_definition = self._current_stage_definition(metadata)
        template_manifest = self.template_service.materialize_job(
            calc_dir,
            project_name=project_name,
            goal=str(stage_definition["goal"]),
            scenario=scenario,
            structure_source=self._string_setting(settings, "structure_source"),
            kpoints_mesh=self._mesh_setting(settings.get("kpoints_mesh")),
            calculation_type=str(stage_definition["calculation_type"]),
            template_name=str(stage_definition["template_name"]) if stage_definition.get("template_name") else None,
        )
        metadata["template_type"] = str(template_manifest["calc_type"])
        metadata["template_name"] = str(template_manifest["template_name"])
        metadata["template_source"] = str(template_manifest["template_source"])
        metadata["current_stage_name"] = str(stage_definition["name"])
        metadata["uploaded_files"] = ",".join(
            [*template_manifest["generated_files"], "submit_vasp.slurm", "job_manifest.json"]
        )
        self._write_metadata(calc_dir, metadata)
        self._materialize_stage(calc_dir, metadata)
        self._execute_or_plan(calc_dir, metadata, stage=0)
        return self._build_job(calc_dir, metadata)

    def advance_job(self, job_id: str) -> ExecutionJob:
        calc_dir = self._find_calc_dir(job_id)
        metadata = self._read_metadata(calc_dir)
        previous_stage_definition = self._current_stage_definition(metadata)
        metadata["stage"] = int(metadata["stage"]) + 1
        metadata["current_workflow_stage"] = min(
            int(metadata.get("current_workflow_stage", 0)) + 1,
            max(len(self._workflow_stages(metadata)) - 1, 0),
        )
        settings = dict(metadata.get("job_settings", {}))
        stage_definition = self._current_stage_definition(metadata)
        template_manifest = self.template_service.materialize_job(
            calc_dir,
            project_name=str(metadata["project_name"]),
            goal=str(stage_definition["goal"]),
            scenario=str(metadata["scenario"]),
            structure_source=self._string_setting(settings, "structure_source"),
            kpoints_mesh=self._mesh_setting(settings.get("kpoints_mesh")),
            calculation_type=str(stage_definition["calculation_type"]),
            template_name=str(stage_definition["template_name"]) if stage_definition.get("template_name") else None,
        )
        metadata["template_type"] = str(template_manifest["calc_type"])
        metadata["template_name"] = str(template_manifest["template_name"])
        metadata["template_source"] = str(template_manifest["template_source"])
        metadata["current_stage_name"] = str(stage_definition["name"])
        self._apply_stage_handoff(calc_dir, previous_stage_definition, stage_definition)
        self._write_metadata(calc_dir, metadata)
        self._materialize_stage(calc_dir, metadata)
        self._execute_or_plan(calc_dir, metadata, stage=int(metadata["stage"]))
        return self._build_job(calc_dir, metadata)

    def _find_calc_dir(self, job_id: str) -> Path:
        for metadata_path in self.base_dir.glob("*/remote_job.json"):
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("job_id") == job_id:
                return metadata_path.parent
        raise FileNotFoundError(f"Remote dry-run job nao encontrado: {job_id}")

    def _materialize_stage(self, calc_dir: Path, metadata: dict[str, object]) -> None:
        scenario = str(metadata["scenario"])
        stage = int(metadata["stage"])
        stage_name = str(metadata.get("current_stage_name") or "relax")
        if stage == 0:
            (calc_dir / "OSZICAR").write_text(" 1 F= -.10000 E0= -.09900 d E =-.001\n", encoding="utf-8")
            (calc_dir / "vasp.out").write_text(f"Submitting {stage_name} VASP job through SLURM...\n", encoding="utf-8")
            if scenario == "zbrent_error":
                (calc_dir / "OUTCAR").write_text(" ZBRENT: fatal error in bracketing\n", encoding="utf-8")
            elif scenario in {"running"}:
                if (calc_dir / "OUTCAR").exists():
                    (calc_dir / "OUTCAR").unlink()
            else:
                (calc_dir / "OUTCAR").write_text(
                    " reached required accuracy \n free  energy   TOTEN  =      -25.0000 eV\n",
                    encoding="utf-8",
                )
        else:
            (calc_dir / "OUTCAR").write_text(
                " reached required accuracy \n"
                " free  energy   TOTEN  =      -25.8000 eV\n"
                " number of electron    32.000 magnetization =      0.0000\n",
                encoding="utf-8",
            )
            (calc_dir / "OSZICAR").write_text(" 14 F= -.25800 E0= -.25000 d E =-.0001\n", encoding="utf-8")
            (calc_dir / "CONTCAR").write_text(
                "Generated converged structure\n1.0\n1 0 0\n0 1 0\n0 0 1\nH\n1\nDirect\n0 0 0\n",
                encoding="utf-8",
            )
            (calc_dir / "CHGCAR").write_text("Mock charge density for next workflow stage.\n", encoding="utf-8")
            (calc_dir / "slurm-1001.out").write_text("VASP completed successfully.\n", encoding="utf-8")
            (calc_dir / "vasp.out").write_text(f"DAV: convergence achieved for stage {stage_name}.\n", encoding="utf-8")

    def _build_job(self, calc_dir: Path, metadata: dict[str, object]) -> ExecutionJob:
        scenario = str(metadata["scenario"])
        stage = int(metadata["stage"])
        status = self._infer_status(scenario, stage, str(metadata.get("scheduler_state") or ""))
        return ExecutionJob(
            job_id=str(metadata["job_id"]),
            calc_path=str(calc_dir),
            scenario=scenario,
            stage=stage,
            status=status,
            message=self._build_message(stage, status),
            metadata={
                "executor": self.executor_name,
                "dry_run": self.config.dry_run,
                "ssh_target": str(metadata["ssh_target"]),
                "remote_path": str(metadata["remote_path"]),
                "sbatch_script": str(Path(calc_dir) / "submit_vasp.slurm"),
                "identity_file": metadata.get("identity_file"),
                "command_log": str(Path(calc_dir) / "command_log.json"),
                "template_type": metadata.get("template_type"),
                "template_name": metadata.get("template_name"),
                "template_source": metadata.get("template_source"),
                "current_stage_name": metadata.get("current_stage_name"),
                "workflow_stages": [stage.get("name", "") for stage in self._workflow_stages(metadata)],
                "uploaded_files": metadata.get("uploaded_files"),
                "synced_artifacts": metadata.get("synced_artifacts"),
                "last_sync_stage": metadata.get("last_sync_stage"),
                "sync_manifest": str(Path(calc_dir) / "remote_sync_manifest.json"),
                "scheduler_job_id": metadata.get("scheduler_job_id"),
                "scheduler_state": metadata.get("scheduler_state"),
            },
        )

    @staticmethod
    def _infer_status(scenario: str, stage: int, scheduler_state: str) -> str:
        normalized_state = scheduler_state.upper()
        if normalized_state in {"RUNNING", "PENDING", "SUBMITTED"}:
            return "running"
        if normalized_state in {"FAILED", "CANCELLED", "TIMEOUT"}:
            return "failed"
        if normalized_state == "COMPLETED":
            return "converged"
        if scenario == "running" and stage == 0:
            return "running"
        if scenario == "zbrent_error" and stage == 0:
            return "failed"
        return "converged"

    def _build_message(self, stage: int, status: str) -> str:
        if self.config.dry_run and stage == 0:
            return "Dry-run SSH/SLURM preparado com plano de submissao remota."
        if not self.config.dry_run and stage == 0:
            return "Execucao SSH/SLURM submetida com comandos remotos configurados."
        if status == "running":
            return "Workflow SSH/SLURM em execucao remota monitorada pelo scheduler."
        if status == "converged":
            return "Workflow SSH/SLURM avancado para estado convergido."
        return "Executor SSH/SLURM preparado."

    @staticmethod
    def _write_metadata(calc_dir: Path, metadata: dict[str, object]) -> None:
        (calc_dir / "remote_job.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    @staticmethod
    def _read_metadata(calc_dir: Path) -> dict[str, object]:
        return json.loads((calc_dir / "remote_job.json").read_text(encoding="utf-8"))

    def _execute_or_plan(self, calc_dir: Path, metadata: dict[str, object], stage: int) -> None:
        self._sync_remote_artifacts(calc_dir, metadata, stage)
        commands = self._command_specs(calc_dir, metadata, stage)

        # Enmascarar comandos para salvaguardar credenciais de sesión no-persistentes
        masked_commands = []
        for cmd in commands:
            masked_cmd = []
            skip_next = False
            for idx, arg in enumerate(cmd):
                if skip_next:
                    masked_cmd.append("******")
                    skip_next = False
                elif arg == "-p" and idx > 0 and cmd[idx-1] == "sshpass":
                    masked_cmd.append("-p")
                    skip_next = True
                else:
                    masked_cmd.append(arg)
            masked_commands.append(masked_cmd)

        plan_path = calc_dir / "REMOTE_PLAN.txt"
        plan_path.write_text("\n".join(" ".join(cmd) for cmd in masked_commands) + "\n", encoding="utf-8")

        log_entries = []
        status_outputs: list[str] = []
        for idx, command in enumerate(commands):
            masked_command = masked_commands[idx]
            entry = {"command": masked_command, "executed": not self.config.dry_run, "returncode": None, "stdout": "", "stderr": ""}
            if not self.config.dry_run:
                result = self.command_runner(command, calc_dir)
                entry["returncode"] = result.returncode
                entry["stdout"] = result.stdout
                entry["stderr"] = result.stderr
                if stage == 0 and "sbatch" in command[-1]:
                    scheduler_job_id = self._parse_sbatch_job_id(result.stdout)
                    metadata["scheduler_job_id"] = scheduler_job_id
                    metadata["scheduler_state"] = "SUBMITTED" if scheduler_job_id else "SUBMIT_UNKNOWN"
                if stage > 0 and self._is_scheduler_query(command):
                    status_outputs.append(result.stdout)
            log_entries.append(entry)

        (calc_dir / "command_log.json").write_text(json.dumps(log_entries, indent=2), encoding="utf-8")
        if stage > 0:
            metadata["scheduler_state"] = self._infer_scheduler_state(status_outputs, str(metadata["scenario"]), stage)
        self._write_metadata(calc_dir, metadata)

    def _command_specs(self, calc_dir: Path, metadata: dict[str, object], stage: int) -> list[list[str]]:
        ssh_target = str(metadata["ssh_target"])
        remote_path = str(metadata["remote_path"])
        identity_file = str(metadata["identity_file"]) if metadata.get("identity_file") else None

        ssh_opts = ["-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10"]
        scp_opts = ["-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10"]
        
        password = self.password_provider() if self.password_provider else None
        if not password:
            ssh_opts.extend(["-o", "BatchMode=yes"])
            scp_opts.extend(["-o", "BatchMode=yes"])

        ssh_prefix = ["ssh", *ssh_opts]
        scp_prefix = ["scp", *scp_opts]
        if identity_file:
            ssh_prefix.extend(["-i", identity_file])
            scp_prefix.extend(["-i", identity_file])
            
        if password:
            ssh_prefix = ["sshpass", "-p", password] + ssh_prefix
            scp_prefix = ["sshpass", "-p", password] + scp_prefix

        upload_files = ["INCAR", "POSCAR", "KPOINTS", "submit_vasp.slurm", "job_manifest.json"]
        remote_path_quoted = f'"{remote_path}"'
        if stage == 0:
            return [
                [*ssh_prefix, ssh_target, f"mkdir -p {remote_path_quoted}"],
                [*scp_prefix, *upload_files, f"{ssh_target}:{remote_path}/"],
                [
                    *ssh_prefix,
                    ssh_target,
                    f"cd {remote_path_quoted} && test -f POTCAR && echo POTCAR_READY || echo POTCAR_MISSING",
                ],
                [*ssh_prefix, ssh_target, f"cd {remote_path} && sbatch submit_vasp.slurm"],
            ]
        scheduler_job_id = str(metadata.get("scheduler_job_id") or "")
        return [
            [
                *ssh_prefix,
                ssh_target,
                f"squeue -h -j {scheduler_job_id} -o %T || true" if scheduler_job_id else "squeue -h -u $USER -o %T || true",
            ],
            [
                *ssh_prefix,
                ssh_target,
                f"sacct -n -j {scheduler_job_id} --format=State || true" if scheduler_job_id else "echo UNKNOWN",
            ],
            [*scp_prefix, f"{ssh_target}:{remote_path}/OUTCAR", "OUTCAR"],
            [*scp_prefix, f"{ssh_target}:{remote_path}/OSZICAR", "OSZICAR"],
            [*scp_prefix, f"{ssh_target}:{remote_path}/vasp.out", "vasp.out"],
            [*scp_prefix, f"{ssh_target}:{remote_path}/CONTCAR", "CONTCAR"],
            [*scp_prefix, f"{ssh_target}:{remote_path}/slurm-*.out", "."],
        ]

    def _cluster_jobs_command(self, scope: str) -> list[str]:
        ssh_opts = ["-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10"]
        password = self.password_provider() if self.password_provider else None
        if not password:
            ssh_opts.extend(["-o", "BatchMode=yes"])

        ssh_prefix = ["ssh", *ssh_opts]
        if self.config.identity_file:
            ssh_prefix.extend(["-i", self.config.identity_file])
            
        if password:
            ssh_prefix = ["sshpass", "-p", password] + ssh_prefix

        queue_scope = "-u $USER" if scope == "user" else ""
        return [
            *ssh_prefix,
            self.config.ssh_target,
            f"squeue -h {queue_scope} -o '%i|%j|%u|%T|%P|%M|%D'",
        ]

    def _list_dry_run_jobs(self, scope: str) -> list[dict[str, str | None]]:
        jobs: list[dict[str, str | None]] = []
        for metadata_path in sorted(self.base_dir.glob("*/remote_job.json")):
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            scheduler_state = str(metadata.get("scheduler_state") or "PENDING_LOCAL_PREP")
            if scheduler_state.upper() not in {"RUNNING", "PENDING", "SUBMITTED", "PENDING_LOCAL_PREP"}:
                continue
            owner = self.config.ssh_user
            if scope == "all" and metadata.get("scenario") == "success":
                continue
            jobs.append(
                {
                    "scheduler_job_id": str(metadata.get("scheduler_job_id") or f"dryrun-{str(metadata.get('job_id', ''))[:8]}"),
                    "name": str(metadata.get("project_name") or metadata_path.parent.name),
                    "owner": owner,
                    "state": scheduler_state,
                    "queue": "dry-run",
                    "runtime": "-",
                    "nodes": "1",
                    "remote_path": str(metadata.get("remote_path") or ""),
                    "project_name": str(metadata.get("project_name") or ""),
                }
            )
        return jobs

    @staticmethod
    def _parse_cluster_jobs_output(stdout: str) -> list[dict[str, str | None]]:
        jobs: list[dict[str, str | None]] = []
        for line in stdout.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            parts = [part.strip() for part in stripped.split("|")]
            if len(parts) < 7:
                continue
            jobs.append(
                {
                    "scheduler_job_id": parts[0],
                    "name": parts[1],
                    "owner": parts[2] or None,
                    "state": parts[3],
                    "queue": parts[4] or None,
                    "runtime": parts[5] or None,
                    "nodes": parts[6] or None,
                    "remote_path": None,
                    "project_name": parts[1] or None,
                }
            )
        return jobs

    def _sync_remote_artifacts(self, calc_dir: Path, metadata: dict[str, object], stage: int) -> None:
        sync_status = self._collect_sync_status(calc_dir)
        synced_artifacts = sync_status["downloaded"]
        metadata["synced_artifacts"] = synced_artifacts
        metadata["last_sync_stage"] = stage
        sync_manifest = {
            "job_id": metadata["job_id"],
            "remote_path": metadata["remote_path"],
            "stage": stage,
            "downloaded": sync_status["downloaded"],
            "missing": sync_status["missing"],
            "failed": sync_status["failed"],
        }
        (calc_dir / "remote_sync_manifest.json").write_text(json.dumps(sync_manifest, indent=2), encoding="utf-8")
        self._write_metadata(calc_dir, metadata)

    @staticmethod
    def _collect_sync_status(calc_dir: Path) -> dict[str, list[str]]:
        tracked_files = ["OUTCAR", "OSZICAR", "vasp.out", "CONTCAR", "CHGCAR"]
        downloaded = [name for name in tracked_files if (calc_dir / name).exists()]
        downloaded.extend(sorted(path.name for path in calc_dir.glob("slurm-*.out")))
        missing = [name for name in tracked_files if name not in downloaded]
        return {"downloaded": downloaded, "missing": missing, "failed": []}

    def _apply_stage_handoff(
        self,
        calc_dir: Path,
        previous_stage: dict[str, object],
        next_stage: dict[str, object],
    ) -> None:
        previous_name = str(previous_stage.get("name") or "")
        next_name = str(next_stage.get("name") or "")
        calculation_type = str(next_stage.get("calculation_type") or "")

        # Reuse the converged geometry as the next stage input structure.
        contcar_path = calc_dir / "CONTCAR"
        if contcar_path.exists() and (next_name in {"relax", "dos", "phonons", "scf", "band", "surface_relax", "adsorbate_relax", "adsorption_relax"} or calculation_type in {"relax", "surface_relax"}):
            (calc_dir / "POSCAR").write_text(contcar_path.read_text(encoding="utf-8"), encoding="utf-8")

        # Reuse charge density before DOS, band structure and phonon-like post-processing stages.
        chgcar_path = calc_dir / "CHGCAR"
        if chgcar_path.exists() and (next_name in {"dos", "phonons", "band"} or calculation_type in {"dos", "band"}):
            handoff_marker = calc_dir / "STAGE_HANDOFF.txt"
            handoff_marker.write_text(
                f"Using CHGCAR from stage {previous_name or 'unknown'} for stage {next_name}.\n",
                encoding="utf-8",
            )
            # Para calculo de bandas, o INCAR precisa do ICHARG=11 para nao recalcular a densidade
            if next_name == "band" or calculation_type == "band":
                incar_path = calc_dir / "INCAR"
                if incar_path.exists():
                    lines = incar_path.read_text(encoding="utf-8").splitlines()
                    updated_lines = []
                    icharg_set = False
                    for line in lines:
                        if line.strip().upper().startswith("ICHARG"):
                            updated_lines.append("ICHARG = 11")
                            icharg_set = True
                        else:
                            updated_lines.append(line)
                    if not icharg_set:
                        updated_lines.append("ICHARG = 11")
                    incar_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")

        # Handoff especial para NEB
        if next_name == "neb" or calculation_type == "neb":
            # Em calculo real de NEB, geramos imagens.
            # Aqui simulamos a geracao de subdiretorios de imagens 00, 01, 02, 03, 04 para o VASP rodar NEB.
            images_count = 5 # 3 imagens intermediarias + 2 endpoints
            for img in range(images_count):
                img_dir = calc_dir / f"{img:02d}"
                img_dir.mkdir(parents=True, exist_ok=True)
                # POSCAR placeholder para cada imagem
                img_poscar = img_dir / "POSCAR"
                img_poscar.write_text(
                    f"NEB Image {img:02d} structure\n1.0\n8.0 0.0 0.0\n0.0 8.0 0.0\n0.0 0.0 8.0\nH\n1\nDirect\n{0.1*img:.3f} 0.0 0.0\n",
                    encoding="utf-8"
                )
            handoff_marker = calc_dir / "STAGE_HANDOFF.txt"
            handoff_marker.write_text(
                f"Generated NEB linear interpolation with 5 images for {next_name} stage.\n",
                encoding="utf-8",
            )

        # Handoff para energia de ligacao (binding energy)
        if next_name == "binding_energy":
            # Escreve um log com as energias obtidas nas etapas anteriores do workflow
            handoff_marker = calc_dir / "STAGE_HANDOFF.txt"
            handoff_marker.write_text(
                f"Ready for binding energy calculation. Composing energies from surface and adsorbate.\n",
                encoding="utf-8",
            )

    @staticmethod
    def _parse_sbatch_job_id(stdout: str) -> str | None:
        match = re.search(r"Submitted batch job\s+(\d+)", stdout)
        return match.group(1) if match else None

    @staticmethod
    def _is_scheduler_query(command: list[str]) -> bool:
        command_text = " ".join(command)
        return "squeue" in command_text or "sacct" in command_text

    def _infer_scheduler_state(self, outputs: list[str], scenario: str, stage: int) -> str:
        text = "\n".join(outputs).upper()
        for candidate in ["COMPLETED", "RUNNING", "PENDING", "FAILED", "CANCELLED", "TIMEOUT"]:
            if candidate in text:
                return candidate
        if self.config.dry_run:
            if scenario == "running" and stage == 1:
                return "COMPLETED"
            if scenario == "running":
                return "RUNNING"
            if scenario == "zbrent_error" and stage == 0:
                return "FAILED"
            return "COMPLETED"
        return "UNKNOWN"

    def _build_workflow_stages(self, goal: str | None, settings: dict[str, object]) -> list[dict[str, object]]:
        recipe = settings.get("workflow_recipe")
        if isinstance(recipe, str) and recipe in self.RECIPE_STAGE_MAP:
            return [dict(stage) for stage in self.RECIPE_STAGE_MAP[recipe]]
        inferred_calc_type = self._infer_calc_type_from_goal(goal)
        return [
            {
                "name": str(settings.get("calculation_type") or inferred_calc_type),
                "calculation_type": str(settings.get("calculation_type") or inferred_calc_type),
                "goal": goal or "Single-step VASP workflow",
                "template_name": settings.get("template_name"),
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

    @staticmethod
    def _workflow_stages(metadata: dict[str, object]) -> list[dict[str, object]]:
        stages = metadata.get("workflow_stages")
        return stages if isinstance(stages, list) else []

    def _current_stage_definition(self, metadata: dict[str, object]) -> dict[str, object]:
        stages = self._workflow_stages(metadata)
        if not stages:
            return {
                "name": "relax",
                "calculation_type": self._infer_calc_type_from_goal(str(metadata.get("goal") or "")),
                "goal": metadata.get("goal") or "Single-step VASP workflow",
                "template_name": None,
            }
        index = min(int(metadata.get("current_workflow_stage", 0)), len(stages) - 1)
        stage = stages[index]
        if isinstance(stage, dict):
            return stage
        return {
            "name": "relax",
            "calculation_type": "relax",
            "goal": metadata.get("goal") or "Single-step VASP workflow",
            "template_name": None,
        }

    @staticmethod
    def _string_setting(settings: dict[str, object], key: str) -> str | None:
        value = settings.get(key)
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _mesh_setting(value: object) -> list[int] | None:
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError("kpoints_mesh deve ser uma lista de inteiros.")
        return [int(item) for item in value]

    @staticmethod
    def _run_command(command: list[str], workdir: Path):
        return subprocess.run(command, cwd=workdir, capture_output=True, text=True, check=False)
