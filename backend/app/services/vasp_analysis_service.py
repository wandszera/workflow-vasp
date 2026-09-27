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
    def analyze_workflow(self, calc_path: str, goal: str | None = None) -> list[dict[str, object]]:
        root = Path(calc_path).expanduser().resolve()
        if not root.exists():
            raise FileNotFoundError(f"Diretorio nao encontrado: {root}")

        energy_summary = self._energy_summary(root)
        structure_diff = self._structure_diff(root)
        dos_ready = self._dos_ready_check(root)
        phonon_ready = self._phonon_ready_check(root)
        mlff_quality = self._mlff_quality_check(root)
        mlff_validation = self._mlff_validation_check(root)
        mlff_descriptor = self._mlff_descriptor_scan(root)
        poscar_semantic = self._poscar_semantic_check(root)
        
        lattice_lengths = poscar_semantic.get("details", {}).get("lattice_lengths")
        incar_semantic = self._incar_semantic_check(root, goal)
        kpoints_semantic = self._kpoints_semantic_check(root, lattice_lengths)
        
        incar_tags = None
        if (root / "INCAR").exists():
            from .incar_validator import IncarValidator
            incar_tags = IncarValidator.parse_incar(root / "INCAR")
        potcar_semantic = self._potcar_semantic_check(root, incar_tags)
        error_recovery = self._error_recovery_check(root)
        
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
            mlff_validation,
            mlff_descriptor,
            poscar_semantic,
            incar_semantic,
            kpoints_semantic,
            potcar_semantic,
            error_recovery,
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
            is_already_dos = False
            incar_path = root / "INCAR"
            if incar_path.exists():
                from .incar_validator import IncarValidator
                tags = IncarValidator.parse_incar(incar_path)
                # Check if tags specify ICHARG = 11 or if we have NEDOS
                if tags.get("ICHARG") == "11" or tags.get("NEDOS") is not None:
                    is_already_dos = True
            
            if is_already_dos and phonon_ready.get("status") == "ready":
                recommended = "rodar_phonons"
                status = "ready"
                summary = "Calculo de DOS concluido. A estrutura esta estavel o suficiente para partir para phonons."
            else:
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

    @staticmethod
    def _get_natoms_from_poscar(poscar_path: Path) -> int:
        try:
            with open(poscar_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = [f.readline().strip() for _ in range(10)]
            for line in lines[5:8]:
                parts = line.split()
                if parts and all(p.isdigit() for p in parts):
                    return sum(int(p) for p in parts)
        except Exception:
            pass
        return 42

    @staticmethod
    def _get_energy_outcar(filename: Path) -> float:
        energy = None
        pattern = re.compile(r"free\s+energy(?:\s+ML)?\s+TOTEN\s*=\s*([-+0-9.Ee]+)", re.IGNORECASE)
        with open(filename, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                match = pattern.search(line)
                if match:
                    energy = float(match.group(1))
        if energy is None:
            raise RuntimeError(f"Nenhuma energia encontrada em {filename.name}")
        return energy

    @staticmethod
    def _get_forces_outcar(filename: Path, natoms: int) -> list[list[float]]:
        forces = []
        found = False
        with open(filename, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        for idx in range(len(lines) - 1, -1, -1):
            if "TOTAL-FORCE" in lines[idx]:
                start_idx = idx + 2
                for j in range(start_idx, start_idx + natoms):
                    parts = lines[j].split()
                    fx = float(parts[3])
                    fy = float(parts[4])
                    fz = float(parts[5])
                    forces.append([fx, fy, fz])
                found = True
                break
        if not found:
            raise RuntimeError(f"TOTAL-FORCE nao encontrado em {filename.name}")
        return forces

    def _mlff_validation_check(self, root: Path) -> dict[str, object]:
        teste_configs_dir = root / "teste_configs"
        if not teste_configs_dir.exists():
            return {
                "tool": "mlff_validation_check",
                "title": "Validacao de Paridade MLFF vs DFT",
                "status": "unavailable",
                "summary": "Diretorio 'teste_configs' nao encontrado para esta etapa.",
                "details": {
                    "has_configs": False
                }
            }

        try:
            import numpy as np
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            
            configs = sorted([d.name for d in teste_configs_dir.iterdir() if d.is_dir() and d.name.startswith("config_")])
            if not configs:
                return {
                    "tool": "mlff_validation_check",
                    "title": "Validacao de Paridade MLFF vs DFT",
                    "status": "warning",
                    "summary": "Nenhum diretorio 'config_*' encontrado dentro de teste_configs.",
                    "details": {
                        "has_configs": False
                    }
                }

            natoms = 42
            first_poscar = teste_configs_dir / configs[0] / "DFT" / "POSCAR"
            if first_poscar.exists():
                natoms = self._get_natoms_from_poscar(first_poscar)

            energies_dft = []
            energies_mlff = []
            forces_dft = []
            forces_mlff = []

            for cfg in configs:
                dft_outcar = teste_configs_dir / cfg / "DFT" / "OUTCAR"
                mlff_outcar = teste_configs_dir / cfg / "MLFF" / "OUTCAR"

                if dft_outcar.exists() and mlff_outcar.exists():
                    try:
                        e_dft = self._get_energy_outcar(dft_outcar)
                        e_mlff = self._get_energy_outcar(mlff_outcar)
                        f_dft = self._get_forces_outcar(dft_outcar, natoms)
                        f_mlff = self._get_forces_outcar(mlff_outcar, natoms)

                        energies_dft.append(e_dft)
                        energies_mlff.append(e_mlff)
                        forces_dft.append(f_dft)
                        forces_mlff.append(f_mlff)
                    except Exception:
                        continue

            if not energies_dft:
                return {
                    "tool": "mlff_validation_check",
                    "title": "Validacao de Paridade MLFF vs DFT",
                    "status": "warning",
                    "summary": "Falha ao extrair energias/forcas dos arquivos OUTCAR.",
                    "details": {
                        "has_configs": True,
                        "extracted_count": 0
                    }
                }

            energies_dft = np.array(energies_dft)
            energies_mlff = np.array(energies_mlff)

            errors_en = energies_mlff - energies_dft
            rmse_en = float(np.sqrt(np.mean(errors_en**2)))
            mae_en = float(np.mean(np.abs(errors_en)))
            max_error_en = float(np.max(np.abs(errors_en)))
            r2_en = float(np.corrcoef(energies_dft, energies_mlff)[0, 1]**2) if len(energies_dft) > 1 else 1.0

            forces_dft = np.array(forces_dft)
            forces_mlff = np.array(forces_mlff)
            fdft_flat = forces_dft.flatten()
            fmlff_flat = forces_mlff.flatten()

            errors_f = fmlff_flat - fdft_flat
            rmse_f = float(np.sqrt(np.mean(errors_f**2)))
            mae_f = float(np.mean(np.abs(errors_f)))
            max_error_f = float(np.max(np.abs(errors_f)))
            r2_f = float(np.corrcoef(fdft_flat, fmlff_flat)[0, 1]**2) if len(fdft_flat) > 1 else 1.0

            # Plot Energy Parity
            plt.figure(figsize=(6, 5))
            plt.scatter(energies_dft, energies_mlff, color='#6366f1', alpha=0.8, s=60, edgecolors='white', linewidth=0.5)
            xmin_en = min(energies_dft.min(), energies_mlff.min())
            xmax_en = max(energies_dft.max(), energies_mlff.max())
            margin_en = 0.05 * (xmax_en - xmin_en) if xmax_en != xmin_en else 1.0
            plt.plot([xmin_en - margin_en, xmax_en + margin_en], [xmin_en - margin_en, xmax_en + margin_en], "--", color='#ef4444', linewidth=1.5, label="Ideal")
            plt.xlabel("Energia DFT (eV)", fontsize=10, fontweight='bold', color='#374151')
            plt.ylabel("Energia MLFF (eV)", fontsize=10, fontweight='bold', color='#374151')
            plt.title(f"Paridade de Energia (DFT vs MLFF)\nRMSE = {rmse_en:.5f} eV | R^2 = {r2_en:.5f}", fontsize=11, fontweight='bold', color='#1f2937')
            plt.grid(True, linestyle=':', alpha=0.6)
            plt.legend()
            plt.tight_layout()
            plt.savefig(root / "energy_parity_comparison.png", dpi=200)
            plt.close()

            # Plot Force Parity
            plt.figure(figsize=(6, 5))
            plt.scatter(fdft_flat, fmlff_flat, color='#10b981', alpha=0.3, s=8)
            xmin_f = min(fdft_flat.min(), fmlff_flat.min())
            xmax_f = max(fdft_flat.max(), fmlff_flat.max())
            margin_f = 0.05 * (xmax_f - xmin_f) if xmax_f != xmin_f else 1.0
            plt.plot([xmin_f - margin_f, xmax_f + margin_f], [xmin_f - margin_f, xmax_f + margin_f], "--", color='#ef4444', linewidth=1.5, label="Ideal")
            plt.xlabel("Forca DFT (eV/A)", fontsize=10, fontweight='bold', color='#374151')
            plt.ylabel("Forca MLFF (eV/A)", fontsize=10, fontweight='bold', color='#374151')
            plt.title(f"Paridade de Forcas (DFT vs MLFF)\nRMSE = {rmse_f:.5f} eV/A | R^2 = {r2_f:.5f}", fontsize=11, fontweight='bold', color='#1f2937')
            plt.grid(True, linestyle=':', alpha=0.6)
            plt.legend()
            plt.tight_layout()
            plt.savefig(root / "force_parity_comparison.png", dpi=200)
            plt.close()

            return {
                "tool": "mlff_validation_check",
                "title": "Validacao de Paridade MLFF vs DFT",
                "status": "ready",
                "summary": f"Validacao concluida com {len(energies_dft)} configuracoes. R^2 de forcas = {r2_f:.4f}.",
                "details": {
                    "config_count": len(configs),
                    "energy_rmse_ev": round(rmse_en, 6),
                    "energy_mae_ev": round(mae_en, 6),
                    "energy_r2": round(r2_en, 6),
                    "force_rmse_ev_ang": round(rmse_f, 6),
                    "force_mae_ev_ang": round(mae_f, 6),
                    "force_r2": round(r2_f, 6),
                    "force_max_error_ev_ang": round(max_error_f, 6),
                    "energy_plot": "energy_parity_comparison.png",
                    "force_plot": "force_parity_comparison.png"
                }
            }

        except Exception as e:
            return {
                "tool": "mlff_validation_check",
                "title": "Validacao de Paridade MLFF vs DFT",
                "status": "failed",
                "summary": f"Erro durante analise de paridade: {str(e)}",
                "details": {}
            }

    def _mlff_descriptor_scan(self, root: Path) -> dict[str, object]:
        descritores = ["RCUT1", "RCUT2", "ML_WFORCE", "ML_WTOTEN", "ML_CDOUB", "ML_CTIFOR"]
        found_descriptors = [d for d in descritores if (root / d).exists()]
        if not found_descriptors:
            return {
                "tool": "mlff_descriptor_scan",
                "title": "Varredura de Parametros MLFF",
                "status": "unavailable",
                "summary": "Nenhum diretorio de descritor (RCUT1, RCUT2, etc.) encontrado para esta etapa.",
                "details": {}
            }

        try:
            import numpy as np
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            summary_data = {}
            generated_plots = {}

            for descritor in found_descriptors:
                pasta = root / descritor
                valores = []
                rmse_energy = []
                rmse_force = []
                rmse_stress = []
                
                subdirs = []
                for item in pasta.iterdir():
                    if item.is_dir():
                        try:
                            val = float(item.name)
                            subdirs.append((val, item))
                        except ValueError:
                            continue
                
                subdirs = sorted(subdirs, key=lambda x: x[0])
                
                for val, camin in subdirs:
                    logfile = camin / "ML_LOGFILE"
                    if not logfile.exists():
                        continue
                    
                    ultimo = None
                    with open(logfile, "r", encoding="utf-8", errors="ignore") as f:
                        for linha in f:
                            if linha.startswith("ERR"):
                                dados = linha.split()
                                if len(dados) >= 5:
                                    ultimo = dados
                                    
                    if ultimo is not None:
                        valores.append(val)
                        rmse_energy.append(float(ultimo[2]))
                        rmse_force.append(float(ultimo[3]))
                        rmse_stress.append(float(ultimo[4]))

                if not valores:
                    continue

                best_energy_idx = rmse_energy.index(min(rmse_energy))
                best_force_idx = rmse_force.index(min(rmse_force))

                # Plot Force
                plt.figure(figsize=(5, 3.5))
                plt.plot(valores, rmse_force, "o-", color='#10b981', linewidth=2, label="RMSE Forca")
                plt.scatter(valores[best_force_idx], rmse_force[best_force_idx], color='#ef4444', s=100, zorder=5, label=f"Melhor = {valores[best_force_idx]}")
                plt.xlabel(descritor, fontsize=9, fontweight='bold')
                plt.ylabel("RMSE Forca (eV/A)", fontsize=9, fontweight='bold')
                plt.title(f"Ajuste de {descritor} (Forcas)", fontsize=10, fontweight='bold')
                plt.grid(True, linestyle=':', alpha=0.6)
                plt.legend()
                plt.tight_layout()
                force_plot_filename = f"{descritor}_force.png"
                plt.savefig(root / force_plot_filename, dpi=200)
                plt.close()

                # Plot Energy
                plt.figure(figsize=(5, 3.5))
                plt.plot(valores, rmse_energy, "o-", color='#6366f1', linewidth=2, label="RMSE Energia")
                plt.scatter(valores[best_energy_idx], rmse_energy[best_energy_idx], color='#ef4444', s=100, zorder=5, label=f"Melhor = {valores[best_energy_idx]}")
                plt.xlabel(descritor, fontsize=9, fontweight='bold')
                plt.ylabel("RMSE Energia (eV/atomo)", fontsize=9, fontweight='bold')
                plt.title(f"Ajuste de {descritor} (Energia)", fontsize=10, fontweight='bold')
                plt.grid(True, linestyle=':', alpha=0.6)
                plt.legend()
                plt.tight_layout()
                energy_plot_filename = f"{descritor}_energy.png"
                plt.savefig(root / energy_plot_filename, dpi=200)
                plt.close()

                summary_data[descritor] = {
                    "best_energy_val": valores[best_energy_idx],
                    "best_energy_rmse": round(rmse_energy[best_energy_idx], 6),
                    "best_force_val": valores[best_force_idx],
                    "best_force_rmse": round(rmse_force[best_force_idx], 6),
                    "tested_values": valores
                }
                generated_plots[descritor] = {
                    "force_plot": force_plot_filename,
                    "energy_plot": energy_plot_filename
                }

            if not summary_data:
                return {
                    "tool": "mlff_descriptor_scan",
                    "title": "Varredura de Parametros MLFF",
                    "status": "warning",
                    "summary": "Diretorios de descritores encontrados, mas sem ML_LOGFILEs validos.",
                    "details": {}
                }

            opt_summary = "Varredura concluida. " + ", ".join([f"{k} (F_otimo={v['best_force_val']})" for k, v in summary_data.items()])

            return {
                "tool": "mlff_descriptor_scan",
                "title": "Varredura de Parametros MLFF",
                "status": "ready",
                "summary": opt_summary,
                "details": {
                    "summary_data": summary_data,
                    "generated_plots": generated_plots
                }
            }

        except Exception as e:
            return {
                "tool": "mlff_descriptor_scan",
                "title": "Varredura de Parametros MLFF",
                "status": "failed",
                "summary": f"Erro durante varredura de descritores: {str(e)}",
                "details": {}
            }

    def _poscar_semantic_check(self, root: Path) -> dict[str, object]:
        poscar_path = root / "POSCAR"
        if not poscar_path.exists():
            return {
                "tool": "poscar_semantic_check",
                "title": "Validador Semantico de POSCAR",
                "status": "unavailable",
                "summary": "Arquivo POSCAR nao encontrado para inspecao.",
                "details": {}
            }

        from .poscar_validator import PoscarValidator
        res = PoscarValidator.validate(poscar_path)
        
        details = {
            "valid": res["valid"],
            "min_distance_ang": res["min_distance_ang"],
            "colliding_count": len(res["colliding_pairs"]),
            "lattice_lengths": list(res["lattice_lengths"]),
            "lattice_angles": list(res["lattice_angles"]),
            "crystal_system": res["crystal_system"],
            "vacuum_thickness_ang": res["vacuum_thickness_ang"],
            "errors": res["errors"]
        }

        if not res["valid"]:
            return {
                "tool": "poscar_semantic_check",
                "title": "Validador Semantico de POSCAR",
                "status": "failed",
                "summary": f"Sobreposicao atômica detectada! Distancia minima: {res['min_distance_ang']} A.",
                "details": details
            }
        
        return {
            "tool": "poscar_semantic_check",
            "title": "Validador Semantico de POSCAR",
            "status": "ready",
            "summary": f"Estrutura ({res['crystal_system']}) consistente. Distancia minima: {res['min_distance_ang']} A.",
            "details": details
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

    def _incar_semantic_check(self, root: Path, goal: str | None = None) -> dict[str, object]:
        incar_path = root / "INCAR"
        if not incar_path.exists():
            return {
                "tool": "incar_semantic_check",
                "title": "Validador de INCAR",
                "status": "unavailable",
                "summary": "Arquivo INCAR nao encontrado.",
                "details": {}
            }

        from .incar_validator import IncarValidator
        res = IncarValidator.validate(incar_path, goal=goal or "relax")
        return {
            "tool": "incar_semantic_check",
            "title": "Validador de INCAR",
            "status": "ready" if res["valid"] else "warning",
            "summary": "Parametros do INCAR compativeis com o objetivo." if res["valid"] else f"Inconsistencias detectadas no INCAR: {', '.join(res['warnings'])}",
            "details": res
        }

    def _kpoints_semantic_check(self, root: Path, lattice_lengths: tuple[float, float, float] | None = None) -> dict[str, object]:
        kpoints_path = root / "KPOINTS"
        if not kpoints_path.exists():
            return {
                "tool": "kpoints_semantic_check",
                "title": "Validador de KPOINTS",
                "status": "unavailable",
                "summary": "Arquivo KPOINTS nao encontrado.",
                "details": {}
            }

        if not lattice_lengths or lattice_lengths == (0.0, 0.0, 0.0):
            poscar_path = root / "POSCAR"
            if poscar_path.exists():
                from .poscar_validator import PoscarValidator
                pos_res = PoscarValidator.validate(poscar_path)
                lattice_lengths = pos_res.get("lattice_lengths")
            
        if not lattice_lengths or lattice_lengths == (0.0, 0.0, 0.0):
            return {
                "tool": "kpoints_semantic_check",
                "title": "Validador de KPOINTS",
                "status": "unavailable",
                "summary": "POSCAR indisponivel para medir malha do KPOINTS.",
                "details": {}
            }

        from .kpoints_validator import KpointsValidator
        res = KpointsValidator.validate(kpoints_path, lattice_lengths)
        return {
            "tool": "kpoints_semantic_check",
            "title": "Validador de KPOINTS",
            "status": "ready" if res["valid"] else "warning",
            "summary": "Malha de KPOINTS saudavel e convergente." if res["valid"] else f"Alertas de malha KPOINTS: {', '.join(res['warnings'])}",
            "details": res
        }

    def _potcar_semantic_check(self, root: Path, incar_tags: dict[str, str] | None = None) -> dict[str, object]:
        potcar_path = root / "POTCAR"
        poscar_path = root / "POSCAR"
        
        if not potcar_path.exists():
            return {
                "tool": "potcar_semantic_check",
                "title": "Validador de POTCAR",
                "status": "unavailable",
                "summary": "Arquivo POTCAR nao encontrado.",
                "details": {}
            }

        from .potcar_validator import PotcarValidator
        res = PotcarValidator.validate(potcar_path, poscar_path, incar_tags)
        return {
            "tool": "potcar_semantic_check",
            "title": "Validador de POTCAR",
            "status": "ready" if res["valid"] else ("failed" if res["critical"] else "warning"),
            "summary": "Sequencia de pseudopotenciais e cutoff corretos." if res["valid"] else f"Alertas do POTCAR: {', '.join(res['warnings'])}",
            "details": res
        }

    def _error_recovery_check(self, root: Path) -> dict[str, object]:
        from .error_recovery import ErrorRecoveryService
        res = ErrorRecoveryService.detect_and_fix_errors(root)
        return {
            "tool": "error_recovery_check",
            "title": "Auto-Recuperacao de Erros (Self-Healing)",
            "status": "ready" if not res["error_detected"] else "warning",
            "summary": res["message"],
            "details": res
        }
