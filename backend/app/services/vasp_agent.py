from __future__ import annotations

from pathlib import Path

from ..schemas import AgentInspectionResponse, SuggestedFix
from .knowledge_base import VaspKnowledgeBase
from .vasp_parser import parse_incar, parse_ml_log, parse_oszicar, parse_outcar


class VaspWorkflowAgent:
    def __init__(self) -> None:
        self.knowledge_base = VaspKnowledgeBase()

    def inspect(self, calc_path: str, goal: str | None = None, apply_fixes: bool = False) -> AgentInspectionResponse:
        root = Path(calc_path).expanduser().resolve()
        if not root.exists():
            raise FileNotFoundError(f"Diretorio nao encontrado: {root}")

        incar_path = root / "INCAR"
        outcar_path = root / "OUTCAR"
        oszicar_path = root / "OSZICAR"
        ml_log_path = root / "ML_LOG.json"

        incar = parse_incar(incar_path)
        outcar = parse_outcar(outcar_path)
        oszicar = parse_oszicar(oszicar_path)
        ml_log = parse_ml_log(ml_log_path)

        detected_errors: list[str] = []
        suggested_fixes: list[SuggestedFix] = []

        raw_text = "\n".join(
            text for text in [str(outcar.get("raw_text", "")), str(oszicar.get("raw_text", ""))] if text
        )

        status = self._infer_status(incar, outcar, oszicar, ml_log)

        for match in self.knowledge_base.match(raw_text):
            error_name = str(match["error"])
            detected_errors.append(error_name)
            for action in match.get("actions", []):
                fix = self._build_fix_from_action(action, incar_path, incar, apply_fixes)
                suggested_fixes.append(fix)

        heuristic_fixes, heuristic_errors = self._heuristic_fixes(goal, incar_path, incar, outcar, ml_log, apply_fixes)
        suggested_fixes.extend(heuristic_fixes)
        detected_errors.extend(heuristic_errors)

        summary = self._build_summary(status, detected_errors, outcar, oszicar, ml_log)
        next_step = self._decide_next_step(status, goal, detected_errors, outcar, ml_log)

        extracted_results = {
            "goal": goal,
            "has_incar": incar_path.exists(),
            "has_outcar": outcar_path.exists(),
            "has_oszicar": oszicar_path.exists(),
            "final_energy_ev": outcar.get("final_energy_ev") or oszicar.get("final_free_energy_ev"),
            "magnetization": outcar.get("magnetization"),
            "ionic_steps": outcar.get("ionic_steps"),
            "electronic_converged": outcar.get("electronic_converged"),
            "has_ml_log": ml_log.get("exists"),
            "ml_stage_name": ml_log.get("stage_name"),
            "ml_status": ml_log.get("status"),
            "ml_train_rmse": ml_log.get("train_rmse"),
            "ml_test_rmse": ml_log.get("test_rmse"),
            "ml_reference_count": ml_log.get("reference_count"),
            "ml_ready_for_production": ml_log.get("ready_for_production"),
        }

        return AgentInspectionResponse(
            calc_path=str(root),
            status=status,
            summary=summary,
            detected_errors=self._unique(detected_errors),
            extracted_results=extracted_results,
            suggested_fixes=self._dedupe_fixes(suggested_fixes),
            next_step=next_step,
        )

    def _infer_status(
        self,
        incar: dict[str, str],
        outcar: dict[str, object],
        oszicar: dict[str, object],
        ml_log: dict[str, object],
    ) -> str:
        if ml_log.get("exists"):
            ml_status = str(ml_log.get("status") or "")
            if ml_status == "failed":
                return "failed"
            if bool(ml_log.get("ready_for_production")):
                return "converged"
            if ml_status == "converged":
                return "warning"
            if ml_status == "running":
                return "running"
        if not incar:
            return "ready"
        if outcar.get("converged"):
            return "converged"
        if self.knowledge_base.match(str(outcar.get("raw_text", ""))):
            return "failed"
        if outcar.get("exists") and not outcar.get("converged"):
            return "warning"
        if oszicar.get("exists"):
            return "running"
        return "unknown"

    def _build_fix_from_action(
        self,
        action: dict[str, object],
        incar_path: Path,
        incar: dict[str, str],
        apply_fixes: bool,
    ) -> SuggestedFix:
        description = str(action.get("description", "Ajuste heuristico sugerido."))
        applied = False
        updates = action.get("updates")
        if isinstance(updates, dict) and apply_fixes:
            self._update_incar(incar_path, incar, {str(key): str(value) for key, value in updates.items()})
            applied = True
        return SuggestedFix(
            source="knowledge_base",
            description=description,
            file=str(incar_path) if updates else None,
            applied=applied,
        )

    def _heuristic_fixes(
        self,
        goal: str | None,
        incar_path: Path,
        incar: dict[str, str],
        outcar: dict[str, object],
        ml_log: dict[str, object],
        apply_fixes: bool,
    ) -> tuple[list[SuggestedFix], list[str]]:
        fixes: list[SuggestedFix] = []
        errors: list[str] = []

        if outcar.get("exists") and not outcar.get("converged"):
            nsw = int(incar.get("NSW", "0")) if incar.get("NSW", "0").isdigit() else 0
            if 0 < nsw < 200:
                applied = False
                if apply_fixes:
                    self._update_incar(incar_path, incar, {"NSW": str(nsw + 50)})
                    applied = True
                fixes.append(
                    SuggestedFix(
                        source="heuristic",
                        description=f"Aumentar NSW de {nsw} para {nsw + 50} para dar mais passos ionicos.",
                        file=str(incar_path),
                        applied=applied,
                    )
                )
                errors.append("Ionic convergence not reached")

        normalized_goal = (goal or "").lower()
        if "dos" in normalized_goal and incar.get("ICHARG") != "11":
            applied = False
            if apply_fixes:
                self._update_incar(incar_path, incar, {"NSW": "0", "ICHARG": "11", "NEDOS": "2000"})
                applied = True
            fixes.append(
                SuggestedFix(
                    source="heuristic",
                    description="Preparar calculo de DOS com NSW=0, ICHARG=11 e NEDOS=2000.",
                    file=str(incar_path),
                    applied=applied,
                )
            )

        if "LCHARG" not in incar:
            applied = False
            if apply_fixes:
                self._update_incar(incar_path, incar, {"LCHARG": ".TRUE."})
                applied = True
            fixes.append(
                SuggestedFix(
                    source="heuristic",
                    description="Adicionar LCHARG=.TRUE. para garantir escrita de CHGCAR.",
                    file=str(incar_path),
                    applied=applied,
                )
            )

        # Heuristics for Band Structure
        if "band" in normalized_goal:
            chgcar_exists = (incar_path.parent / "CHGCAR").exists()
            if not chgcar_exists:
                errors.append("Missing CHGCAR density for band structure run")
                fixes.append(
                    SuggestedFix(
                        source="heuristic",
                        description="O calculo de estrutura de bandas (ICHARG=11) requer o arquivo de densidade CHGCAR da etapa SCF anterior.",
                        file=str(incar_path),
                        applied=False,
                    )
                )
            if incar.get("ICHARG") != "11":
                applied = False
                if apply_fixes:
                    self._update_incar(incar_path, incar, {"ICHARG": "11", "NSW": "0"})
                    applied = True
                fixes.append(
                    SuggestedFix(
                        source="heuristic",
                        description="Forcar ICHARG=11 e NSW=0 para rodar a estrutura de bandas nao-autoconsistente.",
                        file=str(incar_path),
                        applied=applied,
                    )
                )

        # Heuristics for NEB
        if "neb" in normalized_goal:
            if "IMAGES" not in incar:
                applied = False
                if apply_fixes:
                    self._update_incar(incar_path, incar, {"IMAGES": "3", "SPRING": "-5.0", "LCLIMB": ".TRUE."})
                    applied = True
                fixes.append(
                    SuggestedFix(
                        source="heuristic",
                        description="Configurar variaveis elasticas NEB padrao (IMAGES=3, SPRING=-5.0, LCLIMB=.TRUE.).",
                        file=str(incar_path),
                        applied=applied,
                    )
                )

        # Heuristics for Phonons
        if "phonon" in normalized_goal:
            try:
                ediff = float(incar.get("EDIFF", "1e-4"))
            except ValueError:
                ediff = 1e-4

            try:
                ediffg = float(incar.get("EDIFFG", "-0.02"))
            except ValueError:
                ediffg = -0.02

            if ediff > 1e-6:
                errors.append("Phonon relaxation precision below threshold (EDIFF > 1e-6)")
                fixes.append(
                    SuggestedFix(
                        source="heuristic",
                        description="Aumentar precisao eletronica EDIFF para 1E-7 ou 1E-8 antes do calculo de fonons.",
                        file=str(incar_path),
                        applied=False,
                    )
                )
            if ediffg < -0.01:
                errors.append("Phonon relaxation force threshold too loose (EDIFFG < -0.01)")
                fixes.append(
                    SuggestedFix(
                        source="heuristic",
                        description="Ajustar threshold de forcas EDIFFG para -0.005 ou -0.01 para fonons.",
                        file=str(incar_path),
                        applied=False,
                    )
                )

        if ml_log.get("exists"):
            reference_count = ml_log.get("reference_count")
            min_reference_count = ml_log.get("min_reference_count")
            test_rmse = ml_log.get("test_rmse")
            target_rmse = ml_log.get("target_rmse")
            if isinstance(reference_count, int) and isinstance(min_reference_count, int) and reference_count < min_reference_count:
                fixes.append(
                    SuggestedFix(
                        source="heuristic",
                        description=(
                            f"Expandir o dataset de referencias de {reference_count} para pelo menos "
                            f"{min_reference_count} estruturas antes da validacao final do MLFF."
                        ),
                        file=str(incar_path),
                        applied=False,
                    )
                )
                errors.append("MLFF reference coverage below minimum threshold")
            if isinstance(test_rmse, float) and isinstance(target_rmse, float) and test_rmse > target_rmse:
                fixes.append(
                    SuggestedFix(
                        source="heuristic",
                        description=(
                            f"Adicionar novas configuracoes desafiadoras ao treino porque o test RMSE "
                            f"({test_rmse:.3f}) ainda esta acima da meta ({target_rmse:.3f})."
                        ),
                        file=str(incar_path),
                        applied=False,
                    )
                )
                errors.append("MLFF validation RMSE above target")

        return fixes, errors

    def _build_summary(
        self,
        status: str,
        detected_errors: list[str],
        outcar: dict[str, object],
        oszicar: dict[str, object],
        ml_log: dict[str, object],
    ) -> str:
        if ml_log.get("exists"):
            stage_name = ml_log.get("stage_name") or "train"
            test_rmse = ml_log.get("test_rmse")
            reference_count = ml_log.get("reference_count")
            if status == "converged":
                return (
                    f"Treino MLFF validado na etapa {stage_name} com test RMSE {test_rmse} "
                    f"e {reference_count} estruturas de referencia."
                )
            if detected_errors:
                return f"Workflow MLFF com pendencias detectadas na etapa {stage_name}."
            return f"Workflow MLFF em andamento na etapa {stage_name}."
        energy = outcar.get("final_energy_ev") or oszicar.get("final_free_energy_ev")
        if status == "converged":
            return f"Calculo convergiu com energia final {energy} eV."
        if detected_errors:
            return f"Foram detectados {len(detected_errors)} problemas potenciais no calculo."
        if outcar.get("exists"):
            return "Calculo iniciado, mas ainda sem convergencia ionica confirmada."
        return "Diretorio pronto para iniciar ou complementar um calculo VASP."

    def _decide_next_step(
        self,
        status: str,
        goal: str | None,
        detected_errors: list[str],
        outcar: dict[str, object],
        ml_log: dict[str, object],
    ) -> str:
        if ml_log.get("exists"):
            if detected_errors:
                return "Coletar mais referencias e repetir o ciclo de treino/validacao do MLFF."
            if bool(ml_log.get("ready_for_production")):
                return "Promover o potencial treinado para inferencia e preparar benchmarking externo."
            stage_name = str(ml_log.get("stage_name") or "")
            if stage_name == "select":
                return "Continuar a selecao ativa de estruturas antes de iniciar o treino principal."
            if stage_name == "train":
                return "Completar o treino e avancar para a validacao do MLFF."
            return "Revisar metricas de validacao e decidir se o potencial ja pode ser promovido."
        if detected_errors:
            return "Revisar e aplicar as correcoes sugeridas antes de submeter novamente."
        if status == "converged" and goal and "dos" in goal.lower():
            return "Usar a densidade convergida como base e disparar o calculo de DOS/PDOS."
        if status == "converged":
            return "Extrair resultados e encadear a proxima etapa do workflow."
        if outcar.get("exists"):
            return "Monitorar o job ou reexecutar com os ajustes sugeridos se o calculo estiver parado."
        return "Gerar arquivos de entrada e submeter o primeiro job do workflow."

    def _update_incar(self, incar_path: Path, incar: dict[str, str], updates: dict[str, str]) -> None:
        merged = {**incar, **{key.upper(): value for key, value in updates.items()}}
        lines = [f"{key} = {value}" for key, value in sorted(merged.items())]
        incar_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        incar.update({key.upper(): value for key, value in updates.items()})

    @staticmethod
    def _unique(items: list[str]) -> list[str]:
        return list(dict.fromkeys(items))

    @staticmethod
    def _dedupe_fixes(fixes: list[SuggestedFix]) -> list[SuggestedFix]:
        unique: list[SuggestedFix] = []
        seen: set[tuple[str, str, str | None]] = set()
        for fix in fixes:
            key = (fix.source, fix.description, fix.file)
            if key in seen:
                continue
            seen.add(key)
            unique.append(fix)
        return unique
