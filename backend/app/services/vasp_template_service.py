from __future__ import annotations

import json
from pathlib import Path
import shutil


class VaspTemplateService:
    REQUIRED_INPUT_FILES = ("INCAR", "KPOINTS", "POSCAR")
    JOB_SCRIPT_CANDIDATES = ("submit_vasp.slurm", "job.slurm", "submit_vasp.sh")

    def __init__(self, templates_dir: Path | None = None, real_templates_dir: Path | None = None) -> None:
        app_root = Path(__file__).resolve().parent.parent
        self.templates_dir = templates_dir or app_root / "templates" / "vasp"
        self.real_templates_dir = real_templates_dir or app_root.parent / "templates"

    def materialize_job(
        self,
        target_dir: Path,
        project_name: str,
        goal: str | None = None,
        scenario: str | None = None,
        structure_source: str | None = None,
        kpoints_mesh: list[int] | None = None,
        calculation_type: str | None = None,
        template_name: str | None = None,
    ) -> dict[str, object]:
        selected_template = self._resolve_selected_template(template_name, calculation_type, goal, scenario)
        manifest = self._materialize_from_template(
            target_dir=target_dir,
            project_name=project_name,
            selected_template=selected_template,
            goal=goal,
            structure_source=structure_source,
            kpoints_mesh=kpoints_mesh,
        )
        (target_dir / "job_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest

    def list_available_templates(self) -> list[dict[str, str]]:
        templates: list[dict[str, str]] = []
        for path in sorted(self._candidate_template_dirs()):
            calc_type = self._classify_template_dir(path)
            templates.append(
                {
                    "name": path.name,
                    "source": "real" if self.real_templates_dir in path.parents else "builtin",
                    "path": str(path),
                    "calc_type": calc_type,
                }
            )
        return templates

    def _materialize_from_template(
        self,
        target_dir: Path,
        project_name: str,
        selected_template: dict[str, object],
        goal: str | None,
        structure_source: str | None,
        kpoints_mesh: list[int] | None,
    ) -> dict[str, object]:
        template_dir = Path(str(selected_template["path"]))
        calc_type = str(selected_template["calc_type"])
        context = {
            "project_name": project_name,
            "goal": goal or "",
            "calc_type": calc_type,
        }
        generated_files: list[str] = []

        for filename in self.REQUIRED_INPUT_FILES:
            source = self._resolve_source_file(template_dir, filename)
            if source is None:
                continue
            contents = source.read_text(encoding="utf-8", errors="ignore")
            if filename == "POSCAR" and structure_source:
                contents = self._resolve_structure(project_name, structure_source)
            elif filename == "KPOINTS" and kpoints_mesh:
                contents = self._build_kpoints(kpoints_mesh)
            (target_dir / filename).write_text(contents, encoding="utf-8")
            generated_files.append(filename)

        if "POSCAR" not in generated_files:
            (target_dir / "POSCAR").write_text(self._resolve_structure(project_name, structure_source), encoding="utf-8")
            generated_files.append("POSCAR")
        if "KPOINTS" not in generated_files:
            (target_dir / "KPOINTS").write_text(self._build_kpoints(kpoints_mesh), encoding="utf-8")
            generated_files.append("KPOINTS")

        incar_path = self._resolve_source_file(template_dir, "INCAR")
        if incar_path is not None and "INCAR" not in generated_files:
            (target_dir / "INCAR").write_text(
                self._render_text(incar_path.read_text(encoding="utf-8", errors="ignore"), context),
                encoding="utf-8",
            )
            generated_files.append("INCAR")

        script_name = self._copy_job_script(template_dir, target_dir, context)
        if script_name:
            generated_files.append(script_name)

        return {
            "calc_type": calc_type,
            "template_name": str(selected_template["name"]),
            "template_source": str(selected_template["source"]),
            "generated_files": generated_files,
            "placeholders": [],
            "requires_remote_potcar": True,
            "kpoints_mesh": kpoints_mesh or self._parse_kpoints_mesh(target_dir / "KPOINTS"),
            "structure_source_kind": self._structure_source_kind(structure_source),
        }

    def _resolve_selected_template(
        self,
        template_name: str | None,
        calculation_type: str | None,
        goal: str | None,
        scenario: str | None,
    ) -> dict[str, object]:
        if template_name:
            resolved = self._find_named_template(template_name)
            if resolved is not None:
                return resolved

        if calculation_type:
            resolved = self._find_named_template(calculation_type)
            if resolved is not None:
                return resolved

        inferred = self._infer_calc_type(goal, scenario)
        builtin_dir = self.templates_dir / inferred
        return {"name": inferred, "path": builtin_dir, "source": "builtin", "calc_type": inferred}

    def _find_named_template(self, template_name: str) -> dict[str, object] | None:
        normalized = template_name.strip().lower()
        for path in self._candidate_template_dirs():
            if path.name.lower() == normalized:
                return {
                    "name": path.name,
                    "path": path,
                    "source": "real" if self.real_templates_dir in path.parents else "builtin",
                    "calc_type": self._classify_template_dir(path),
                }
        return None

    def _candidate_template_dirs(self) -> list[Path]:
        candidates: list[Path] = []
        if self.real_templates_dir.exists():
            for path in self.real_templates_dir.rglob("*"):
                if path.is_dir() and all((path / filename).exists() for filename in self.REQUIRED_INPUT_FILES):
                    candidates.append(path)
        if self.templates_dir.exists():
            for path in self.templates_dir.iterdir():
                if path.is_dir():
                    candidates.append(path)
        return candidates

    def _copy_job_script(self, template_dir: Path, target_dir: Path, context: dict[str, str]) -> str | None:
        for candidate in self.JOB_SCRIPT_CANDIDATES:
            source = self._resolve_source_file(template_dir, candidate)
            if source is not None:
                rendered = self._render_text(source.read_text(encoding="utf-8", errors="ignore"), context)
                (target_dir / "submit_vasp.slurm").write_text(rendered, encoding="utf-8")
                return "submit_vasp.slurm"

        for source in template_dir.iterdir():
            if source.is_file() and source.name.lower().startswith("job"):
                shutil.copyfile(source, target_dir / "submit_vasp.slurm")
                return "submit_vasp.slurm"
        return None

    @staticmethod
    def _resolve_source_file(template_dir: Path, filename: str) -> Path | None:
        direct = template_dir / filename
        if direct.exists():
            return direct
        templated = template_dir / f"{filename}.template"
        if templated.exists():
            return templated
        return None

    @staticmethod
    def _render_text(template: str, context: dict[str, str]) -> str:
        rendered = template
        for key, value in context.items():
            rendered = rendered.replace(f"{{{{ {key} }}}}", value)
        return rendered

    @staticmethod
    def _infer_calc_type(goal: str | None, scenario: str | None) -> str:
        normalized_goal = (goal or "").lower()
        if "aimd" in normalized_goal or "molecular dynamics" in normalized_goal:
            return "aimd"
        if "dos" in normalized_goal or scenario == "dos_ready":
            return "dos"
        if "phonon" in normalized_goal:
            return "phonons"
        if "band" in normalized_goal or "estrutura de bandas" in normalized_goal:
            return "band"
        if "neb" in normalized_goal or "barrier" in normalized_goal:
            return "neb"
        if "surface" in normalized_goal or "adsorption" in normalized_goal or "superficie" in normalized_goal:
            return "surface_relax"
        if "mlff" in normalized_goal or "potencial" in normalized_goal:
            return "mlff_training"
        return "relax"

    def _classify_template_dir(self, path: Path) -> str:
        name = path.name.lower()
        if name == "dos":
            return "dos"
        if name == "aimd":
            return "aimd"
        if name == "phonons":
            return "phonons"
        if name == "relax":
            return "relax"
        if name == "band":
            return "band"
        if name == "neb":
            return "neb"
        if name == "surface_relax" or name == "surface":
            return "surface_relax"
        if name == "mlff_training" or name == "mlff":
            return "mlff_training"
        incar_path = self._resolve_source_file(path, "INCAR")
        incar_text = incar_path.read_text(encoding="utf-8", errors="ignore").lower() if incar_path is not None else ""
        if "ml_lmlff" in incar_text or "ml_mode" in incar_text:
            return "mlff_training"
        if "images" in incar_text or "spring" in incar_text:
            return "neb"
        if "icharg = 11" in incar_text or "icharg=11" in incar_text:
            return "band"
        if "ibrion = 0" in incar_text or "smass" in incar_text or "tebeg" in incar_text:
            return "aimd"
        if "icharg" in incar_text and "nedos" in incar_text:
            return "dos"
        if "ibrion = 6" in incar_text or "nfree" in incar_text:
            return "phonons"
        if "substrate" in name or "graphene" in incar_text or "ivdw" in incar_text:
            return "surface_relax"
        if "cluster" in name or "gam" in name:
            return "cluster_relax"
        return "relax"

    @staticmethod
    def _resolve_structure(project_name: str, structure_source: str | None) -> str:
        if structure_source:
            source_path = Path(structure_source)
            if source_path.exists() and source_path.is_file():
                return source_path.read_text(encoding="utf-8")
            if "\n" in structure_source:
                return structure_source if structure_source.endswith("\n") else structure_source + "\n"
        return f"{project_name} structure placeholder\n1.0\n1 0 0\n0 1 0\n0 0 1\nH\n1\nDirect\n0 0 0\n"

    @staticmethod
    def _build_kpoints(kpoints_mesh: list[int] | None) -> str:
        mesh = kpoints_mesh or [4, 4, 4]
        if len(mesh) != 3:
            raise ValueError("kpoints_mesh deve conter exatamente tres inteiros.")
        return (
            "Automatic mesh\n"
            "0\n"
            "Gamma\n"
            f"{mesh[0]} {mesh[1]} {mesh[2]}\n"
            "0 0 0\n"
        )

    @staticmethod
    def _parse_kpoints_mesh(path: Path) -> list[int]:
        if not path.exists():
            return [4, 4, 4]
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.split("!", maxsplit=1)[0].strip()
            parts = stripped.split()
            if len(parts) == 3 and all(part.lstrip("-").isdigit() for part in parts):
                return [int(part) for part in parts]
        return [4, 4, 4]

    @staticmethod
    def _structure_source_kind(structure_source: str | None) -> str:
        if not structure_source:
            return "generated_placeholder"
        source_path = Path(structure_source)
        if source_path.exists() and source_path.is_file():
            return "file_path"
        return "inline"
