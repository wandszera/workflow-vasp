from __future__ import annotations

import re
from pathlib import Path

from .vasp_parser import (
    parse_ml_log,
    parse_oszicar,
    parse_outcar,
    read_text_if_exists,
    parse_outcar_eigenvalues,
    parse_incar,
)


class VaspAnalysisService:
    def analyze_workflow(self, calc_path: str) -> list[dict[str, object]]:
        root = Path(calc_path).expanduser().resolve()
        if not root.exists():
            raise FileNotFoundError(f"Diretorio nao encontrado: {root}")

        energy_summary = self._energy_summary(root)
        structure_diff = self._structure_diff(root)
        dos_ready = self._dos_ready_check(root)
        phonon_ready = self._phonon_ready_check(root)
        mlff_quality = self._mlff_quality_check(root)
        neb_path = self._neb_path_check(root)
        band_gap = self._band_gap_check(root)
        regression_check = self._regression_check(root, energy_summary, structure_diff)
        next_calculation = self._next_calculation_recommendation(
            root,
            energy_summary=energy_summary,
            dos_ready=dos_ready,
            phonon_ready=phonon_ready,
            mlff_quality=mlff_quality,
            regression_check=regression_check,
            neb_path=neb_path,
            band_gap=band_gap,
        )
        run_report = self._run_report(root)

        return [
            energy_summary,
            structure_diff,
            dos_ready,
            phonon_ready,
            mlff_quality,
            neb_path,
            band_gap,
            regression_check,
            next_calculation,
            run_report,
        ]


    def get_final_energy(self, calc_path: str | Path) -> float:
        root = Path(calc_path).expanduser().resolve()
        outcar = parse_outcar(root / "OUTCAR")
        oszicar = parse_oszicar(root / "OSZICAR")
        final_energy = outcar.get("final_energy_ev") or oszicar.get("final_free_energy_ev")
        if not isinstance(final_energy, float):
            raise ValueError(f"Energia final indisponivel em {root}")
        return final_energy

    def compute_binding_energy(
        self,
        target_calc_path: str | Path,
        reference_calc_paths: list[str | Path],
    ) -> dict[str, object]:
        target_energy = self.get_final_energy(target_calc_path)
        reference_energies = [self.get_final_energy(path) for path in reference_calc_paths]
        binding_energy = round(target_energy - sum(reference_energies), 6)
        return {
            "binding_energy_ev": binding_energy,
            "target_energy_ev": target_energy,
            "reference_energies_ev": reference_energies,
            "reference_count": len(reference_energies),
        }

    def _energy_summary(self, root: Path) -> dict[str, object]:
        outcar = parse_outcar(root / "OUTCAR")
        oszicar = parse_oszicar(root / "OSZICAR")
        final_energy = outcar.get("final_energy_ev") or oszicar.get("final_free_energy_ev")
        ionic_steps = int(outcar.get("ionic_steps") or 0)
        status = "ready" if outcar.get("converged") else "warning" if outcar.get("exists") or oszicar.get("exists") else "unavailable"
        return {
            "tool": "energy_summary",
            "title": "Resumo energetico",
            "status": status,
            "summary": (
                f"Energia final estimada: {final_energy} eV com {ionic_steps} passos ionicos."
                if final_energy is not None
                else "Energia final ainda nao disponivel."
            ),
            "details": {
                "final_energy_ev": final_energy,
                "ionic_steps": ionic_steps,
                "electronic_converged": bool(outcar.get("electronic_converged")),
                "outcar_converged": bool(outcar.get("converged")),
            },
        }

    def _structure_diff(self, root: Path) -> dict[str, object]:
        poscar = self._extract_coordinates(root / "POSCAR")
        contcar = self._extract_coordinates(root / "CONTCAR")
        if not poscar or not contcar:
            return {
                "tool": "structure_diff",
                "title": "Diferenca estrutural",
                "status": "unavailable",
                "summary": "POSCAR ou CONTCAR indisponivel para comparar a geometria.",
                "details": {
                    "coordinate_pairs_compared": 0,
                    "max_abs_coordinate_delta": None,
                    "mean_abs_coordinate_delta": None,
                },
            }

        pair_count = min(len(poscar), len(contcar))
        deltas = [
            abs(contcar[index][axis] - poscar[index][axis])
            for index in range(pair_count)
            for axis in range(3)
        ]
        max_delta = max(deltas) if deltas else 0.0
        mean_delta = sum(deltas) / len(deltas) if deltas else 0.0
        status = "ready" if max_delta < 0.05 else "warning"
        return {
            "tool": "structure_diff",
            "title": "Diferenca estrutural",
            "status": status,
            "summary": f"Comparacao entre POSCAR e CONTCAR com desvio maximo {max_delta:.4f}.",
            "details": {
                "coordinate_pairs_compared": pair_count,
                "max_abs_coordinate_delta": round(max_delta, 6),
                "mean_abs_coordinate_delta": round(mean_delta, 6),
            },
        }

    def _dos_ready_check(self, root: Path) -> dict[str, object]:
        chgcar_exists = (root / "CHGCAR").exists()
        wavecar_exists = (root / "WAVECAR").exists()
        outcar = parse_outcar(root / "OUTCAR")
        status = "ready" if chgcar_exists and outcar.get("converged") else "warning"
        missing_inputs = [name for name, exists in {"CHGCAR": chgcar_exists, "WAVECAR": wavecar_exists}.items() if not exists]
        return {
            "tool": "dos_ready_check",
            "title": "Pronto para DOS",
            "status": status,
            "summary": (
                "Estrutura e densidade parecem prontas para uma etapa de DOS."
                if status == "ready"
                else "Ainda faltam artefatos importantes para uma etapa confiavel de DOS."
            ),
            "details": {
                "has_chgcar": chgcar_exists,
                "has_wavecar": wavecar_exists,
                "converged_geometry": bool(outcar.get("converged")),
                "missing_inputs": ", ".join(missing_inputs) if missing_inputs else "-",
            },
        }

    def _phonon_ready_check(self, root: Path) -> dict[str, object]:
        outcar = parse_outcar(root / "OUTCAR")
        contcar_exists = (root / "CONTCAR").exists()
        status = "ready" if outcar.get("converged") and contcar_exists else "warning"
        return {
            "tool": "phonon_ready_check",
            "title": "Pronto para phonons",
            "status": status,
            "summary": (
                "A relaxacao parece suficiente para avancar a um calculo de phonons."
                if status == "ready"
                else "Convem confirmar a convergencia estrutural antes de seguir para phonons."
            ),
            "details": {
                "has_contcar": contcar_exists,
                "converged_geometry": bool(outcar.get("converged")),
                "magnetization": outcar.get("magnetization"),
            },
        }

    def _run_report(self, root: Path) -> dict[str, object]:
        outcar = parse_outcar(root / "OUTCAR")
        oszicar = parse_oszicar(root / "OSZICAR")
        ml_log = parse_ml_log(root / "ML_LOG.json")
        files_present = [
            name for name in ["INCAR", "POSCAR", "KPOINTS", "OUTCAR", "OSZICAR", "CONTCAR", "CHGCAR", "ML_LOG.json", "ML_FFN"]
            if (root / name).exists()
        ]
        status = "ready" if outcar.get("exists") or oszicar.get("exists") or ml_log.get("exists") else "unavailable"
        return {
            "tool": "run_report",
            "title": "Relatorio consolidado",
            "status": status,
            "summary": f"Calc path com {len(files_present)} arquivos-chave presentes para inspecao.",
            "details": {
                "calc_path": str(root),
                "present_files": ", ".join(files_present) if files_present else "-",
                "final_energy_ev": outcar.get("final_energy_ev") or oszicar.get("final_free_energy_ev"),
                "ml_stage_name": ml_log.get("stage_name"),
                "ml_ready_for_production": ml_log.get("ready_for_production"),
                "has_scheduler_output": any(root.glob('slurm-*.out')),
            },
        }

    def _regression_check(
        self,
        root: Path,
        energy_summary: dict[str, object],
        structure_diff: dict[str, object],
    ) -> dict[str, object]:
        outcar = parse_outcar(root / "OUTCAR")
        oszicar = parse_oszicar(root / "OSZICAR")
        final_energy = outcar.get("final_energy_ev")
        free_energy = oszicar.get("final_free_energy_ev")
        energy_gap = None
        if isinstance(final_energy, float) and isinstance(free_energy, float):
            energy_gap = round(abs(final_energy - free_energy), 6)
        geometry_delta = structure_diff.get("details", {}).get("max_abs_coordinate_delta")
        has_handoff_marker = (root / "STAGE_HANDOFF.txt").exists()
        severe_geometry_shift = isinstance(geometry_delta, float) and geometry_delta > 0.2
        severe_energy_gap = isinstance(energy_gap, float) and energy_gap > 1.0
        status = "failed" if severe_geometry_shift or severe_energy_gap else "ready"
        summary = (
            "Sinais de regressao detectados entre as ultimas etapas do workflow."
            if status == "failed"
            else "Sem regressao evidente entre os artefatos principais da execucao."
        )
        return {
            "tool": "regression_check",
            "title": "Check de regressao",
            "status": status,
            "summary": summary,
            "details": {
                "energy_gap_ev": energy_gap,
                "max_abs_coordinate_delta": geometry_delta,
                "has_stage_handoff_marker": has_handoff_marker,
                "current_energy_status": energy_summary.get("status"),
            },
        }

    def _next_calculation_recommendation(
        self,
        root: Path,
        energy_summary: dict[str, object],
        dos_ready: dict[str, object],
        phonon_ready: dict[str, object],
        mlff_quality: dict[str, object],
        regression_check: dict[str, object],
        neb_path: dict[str, object] | None = None,
        band_gap: dict[str, object] | None = None,
    ) -> dict[str, object]:
        outcar = parse_outcar(root / "OUTCAR")
        ml_log = parse_ml_log(root / "ML_LOG.json")
        has_chgcar = (root / "CHGCAR").exists()
        has_contcar = (root / "CONTCAR").exists()
        has_wavecar = (root / "WAVECAR").exists()

        if neb_path and neb_path.get("status") == "warning":
            recommended = "continuar_neb"
            status = "warning"
            summary = "Algumas imagens do caminho NEB ainda nao convergiram. Recomenda-se continuar a otimizacao."
        elif neb_path and neb_path.get("status") == "ready":
            recommended = "analisar_barreira_neb"
            status = "ready"
            summary = "Todas as imagens NEB convergiram! A barreira de ativacao ja pode ser calculada."
        elif band_gap and band_gap.get("status") == "ready":
            bg = band_gap["details"]["band_gap_ev"]
            recommended = "analisar_bandas"
            status = "ready"
            if bg is not None and bg > 0.0:
                summary = f"Estrutura de bandas avaliada com sucesso. O band gap estimado e de {bg:.4f} eV."
            else:
                summary = "Estrutura de bandas avaliada com sucesso. Comportamento metalico detectado."
        elif ml_log.get("exists") and bool(ml_log.get("ready_for_production")):
            recommended = "promover_mlff"
            status = "ready"
            summary = "O potencial MLFF atingiu os criterios minimos e pode seguir para benchmark/inferencia."
        elif ml_log.get("exists") and mlff_quality.get("status") == "warning":
            recommended = "expandir_dataset_mlff"
            status = "warning"
            summary = "Antes de promover o MLFF, vale expandir o dataset e repetir a validacao."
        elif regression_check.get("status") == "failed":
            recommended = "revisar_relaxacao"
            status = "failed"
            summary = "Revisar a ultima etapa e repetir a relaxacao antes de avancar o pipeline."
        elif not outcar.get("converged"):
            recommended = "continuar_relaxacao"
            status = "warning"
            summary = "O melhor proximo passo ainda e concluir a relaxacao estrutural."
        elif has_chgcar and has_contcar and not has_wavecar:
            recommended = "rodar_dos"
            status = "ready"
            summary = "A geometria parece madura; o proximo calculo mais forte e uma etapa de DOS."
        elif phonon_ready.get("status") == "ready":
            recommended = "rodar_phonons"
            status = "ready"
            summary = "A estrutura esta estavel o suficiente para partir para phonons."
        else:
            recommended = "validar_artefatos"
            status = "warning"
            summary = "Antes do proximo calculo, vale validar artefatos e convergencia com mais cuidado."

        return {
            "tool": "next_calculation_recommendation",
            "title": "Proximo calculo recomendado",
            "status": status,
            "summary": summary,
            "details": {
                "recommended_step": recommended,
                "energy_status": energy_summary.get("status"),
                "dos_readiness": dos_ready.get("status"),
                "phonon_readiness": phonon_ready.get("status"),
                "mlff_quality": mlff_quality.get("status"),
                "has_chgcar": has_chgcar,
                "has_contcar": has_contcar,
                "has_wavecar": has_wavecar,
                "neb_status": neb_path.get("status") if neb_path else None,
                "band_gap_status": band_gap.get("status") if band_gap else None,
            },
        }

    def _mlff_quality_check(self, root: Path) -> dict[str, object]:
        ml_log = parse_ml_log(root / "ML_LOG.json")
        if not ml_log.get("exists"):
            return {
                "tool": "mlff_quality_check",
                "title": "Qualidade do MLFF",
                "status": "unavailable",
                "summary": "Nao ha artefatos de treino MLFF neste workflow.",
                "details": {
                    "stage_name": None,
                    "train_rmse": None,
                    "test_rmse": None,
                    "reference_count": None,
                    "ready_for_production": False,
                },
            }

        test_rmse = ml_log.get("test_rmse")
        target_rmse = ml_log.get("target_rmse")
        reference_count = ml_log.get("reference_count")
        min_reference_count = ml_log.get("min_reference_count")
        ready_for_production = bool(ml_log.get("ready_for_production"))
        status = "ready" if ready_for_production else "warning"
        summary = (
            "O potencial MLFF ja atende os criterios minimos de validacao."
            if ready_for_production
            else "O potencial MLFF ainda precisa de mais dados ou melhor ajuste antes da promocao."
        )
        return {
            "tool": "mlff_quality_check",
            "title": "Qualidade do MLFF",
            "status": status,
            "summary": summary,
            "details": {
                "stage_name": ml_log.get("stage_name"),
                "train_rmse": ml_log.get("train_rmse"),
                "test_rmse": test_rmse,
                "target_rmse": target_rmse,
                "reference_count": reference_count,
                "min_reference_count": min_reference_count,
                "ready_for_production": ready_for_production,
            },
        }

    def _neb_path_check(self, root: Path) -> dict[str, object]:
        image_dirs = sorted([d for d in root.glob("[0-9][0-9]") if d.is_dir()])
        if not image_dirs:
            return {
                "tool": "neb_path_check",
                "title": "Check do caminho NEB",
                "status": "unavailable",
                "summary": "Nao foram encontradas pastas de imagens (00, 01, ...) neste diretorio.",
                "details": {
                    "image_count": 0,
                    "images_found": [],
                    "converged_images_count": 0,
                    "max_force": None,
                },
            }

        converged_count = 0
        max_forces = []

        for img_dir in image_dirs:
            outcar_path = img_dir / "OUTCAR"
            if outcar_path.exists():
                outcar_data = parse_outcar(outcar_path)
                if outcar_data.get("converged"):
                    converged_count += 1
                content = outcar_data.get("raw_text", "")
                force_match = re.search(
                    r"NEB:\s*max\s*force\s*([-0-9.]+)", content, flags=re.IGNORECASE
                )
                if force_match:
                    max_forces.append(float(force_match.group(1)))
                else:
                    max_forces.append(0.03 if outcar_data.get("converged") else 0.15)
            else:
                max_forces.append(0.2)

        total_images = len(image_dirs)
        status = "ready" if converged_count == total_images else "warning"

        summary = (
            f"Caminho NEB com {total_images} imagens detectadas. Todas as imagens parecem convergidas."
            if status == "ready"
            else f"Caminho NEB com {total_images} imagens. {converged_count} convergidas. Algumas imagens ainda necessitam de mais passos."
        )

        return {
            "tool": "neb_path_check",
            "title": "Check do caminho NEB",
            "status": status,
            "summary": summary,
            "details": {
                "image_count": total_images,
                "images_found": [d.name for d in image_dirs],
                "converged_images_count": converged_count,
                "max_force": max(max_forces) if max_forces else None,
            },
        }

    def _band_gap_check(self, root: Path) -> dict[str, object]:
        outcar_path = root / "OUTCAR"
        if not outcar_path.exists():
            return {
                "tool": "band_gap_check",
                "title": "Analise de Band Gap",
                "status": "unavailable",
                "summary": "OUTCAR indisponivel para analisar a estrutura de bandas.",
                "details": {
                    "e_fermi": None,
                    "vbm": None,
                    "cbm": None,
                    "band_gap_ev": None,
                    "kpoint_count": 0,
                },
            }

        content = read_text_if_exists(outcar_path)
        data = parse_outcar_eigenvalues(content)

        incar = parse_incar(root / "INCAR") if (root / "INCAR").exists() else {}
        is_band = incar.get("ICHARG") == "11"

        if not data["kpoint_count"]:
            return {
                "tool": "band_gap_check",
                "title": "Analise de Band Gap",
                "status": "unavailable",
                "summary": "Nao foram encontrados autovalores (eigenvalues) no OUTCAR.",
                "details": {
                    "e_fermi": data["e_fermi"],
                    "vbm": None,
                    "cbm": None,
                    "band_gap_ev": None,
                    "kpoint_count": 0,
                },
            }

        status = "ready" if is_band else "warning"
        bg = data["band_gap"]

        if bg is not None and bg > 0.0:
            summary = f"Estrutura de bandas analisada. Band gap semicondutor/isolante detectado: {bg:.4f} eV."
        elif bg is not None:
            summary = "Estrutura de bandas analisada. Comportamento metalico detectado (band gap zero)."
        else:
            summary = "Estrutura de bandas incompleta ou impossivel de determinar o gap."

        return {
            "tool": "band_gap_check",
            "title": "Analise de Band Gap",
            "status": status,
            "summary": summary,
            "details": {
                "e_fermi": data["e_fermi"],
                "vbm": data["vbm"],
                "cbm": data["cbm"],
                "band_gap_ev": bg,
                "kpoint_count": data["kpoint_count"],
            },
        }


    @staticmethod
    def _extract_coordinates(path: Path) -> list[tuple[float, float, float]]:
        content = read_text_if_exists(path)
        if not content:
            return []
        coordinates: list[tuple[float, float, float]] = []
        for line in content.splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            try:
                coords = tuple(float(parts[index]) for index in range(3))
            except ValueError:
                continue
            if all(abs(value) <= 10 for value in coords):
                coordinates.append(coords)
        return coordinates
