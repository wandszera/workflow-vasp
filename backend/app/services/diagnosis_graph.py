from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, TypedDict

from .diagnosis_store import DiagnosisStore
from .rag_retriever import LocalHybridRetriever
from .vasp_agent import VaspWorkflowAgent

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # pragma: no cover - fallback keeps the core usable before dependency install
    END = START = StateGraph = None  # type: ignore[assignment]


class DiagnosisState(TypedDict, total=False):
    diagnosis_id: str
    calc_path: str
    goal: str | None
    top_k: int
    inspection: dict[str, Any]
    log_excerpt: str
    calculation_type: str | None
    failure_class: str
    citations: list[dict[str, Any]]
    hypothesis: str
    confidence: str
    limitations: list[str]
    recommendations: list[str]
    safety_checks: list[str]
    status: str
    graph_trace: list[str]
    human_decision: str | None
    human_note: str | None


class GroundedDiagnosisGraph:
    def __init__(
        self,
        agent: VaspWorkflowAgent | None = None,
        retriever: LocalHybridRetriever | None = None,
        store: DiagnosisStore | None = None,
    ) -> None:
        self.agent = agent or VaspWorkflowAgent()
        self.retriever = retriever or LocalHybridRetriever()
        self.store = store or DiagnosisStore()
        self.graph = self._compile_graph() if StateGraph is not None else None

    @property
    def runtime(self) -> str:
        return "langgraph" if self.graph is not None else "deterministic-fallback"

    def _compile_graph(self):
        builder = StateGraph(DiagnosisState)
        builder.add_node("coletar_arquivos", self._collect_files)
        builder.add_node("classificar_falha", self._classify_failure)
        builder.add_node("buscar_evidencias", self._retrieve_evidence)
        builder.add_node("gerar_hipoteses", self._generate_hypothesis)
        builder.add_node("validar_recomendacoes", self._validate_recommendations)
        builder.add_node("solicitar_aprovacao_humana", self._request_human_approval)
        builder.add_edge(START, "coletar_arquivos")
        builder.add_edge("coletar_arquivos", "classificar_falha")
        builder.add_edge("classificar_falha", "buscar_evidencias")
        builder.add_edge("buscar_evidencias", "gerar_hipoteses")
        builder.add_edge("gerar_hipoteses", "validar_recomendacoes")
        builder.add_edge("validar_recomendacoes", "solicitar_aprovacao_humana")
        builder.add_edge("solicitar_aprovacao_humana", END)
        return builder.compile()

    def _collect_files(self, state: DiagnosisState) -> dict[str, Any]:
        root = Path(state["calc_path"])
        inspection = self.agent.inspect(str(root), goal=state.get("goal"), apply_fixes=False)
        texts: list[str] = []
        for filename in ("OUTCAR", "OSZICAR", "vasp.out"):
            path = root / filename
            if path.exists():
                texts.append(path.read_text(encoding="utf-8", errors="ignore")[-12000:])
        for path in sorted(root.glob("slurm-*.out"))[-3:]:
            texts.append(path.read_text(encoding="utf-8", errors="ignore")[-6000:])
        goal = (state.get("goal") or "").lower()
        calculation_type = next(
            (name for name in ("relax", "dos", "phonon", "band", "neb", "aimd", "mlff") if name in goal),
            None,
        )
        return {
            "inspection": inspection.model_dump(),
            "log_excerpt": "\n".join(texts)[-24000:],
            "calculation_type": calculation_type,
            "graph_trace": self._append_trace(state, "coletar_arquivos"),
        }

    def _classify_failure(self, state: DiagnosisState) -> dict[str, Any]:
        inspection = state["inspection"]
        text = " ".join(inspection.get("detected_errors", [])) + " " + state.get("log_excerpt", "")
        normalized = text.lower()
        if inspection.get("status") == "converged":
            failure_class = "converged"
        elif re.search(r"out.of.memory|oom-kill|exceeded memory|bad_alloc|slurmstepd", normalized):
            failure_class = "resources_or_slurm"
        elif re.search(r"brmix|edddav|zhegv|electronic|sub-space-matrix|nelm", normalized):
            failure_class = "electronic_convergence"
        elif re.search(r"zbrent|ionic|geometry|ediffg|phonon|too close", normalized):
            failure_class = "ionic_or_structural"
        else:
            failure_class = "unknown"
        return {"failure_class": failure_class, "graph_trace": self._append_trace(state, "classificar_falha")}

    def _retrieve_evidence(self, state: DiagnosisState) -> dict[str, Any]:
        inspection = state["inspection"]
        query = " ".join(
            [
                state.get("goal") or "",
                state["failure_class"],
                *inspection.get("detected_errors", []),
                state.get("log_excerpt", "")[-4000:],
            ]
        )
        documents = self.retriever.search(
            query,
            top_k=state.get("top_k", 5),
            failure_class=state["failure_class"],
            calculation_type=state.get("calculation_type"),
        )
        return {
            "citations": [document.citation() for document in documents],
            "graph_trace": self._append_trace(state, "buscar_documentacao", "buscar_casos_similares"),
        }

    def _append_trace(self, state: DiagnosisState, *nodes: str) -> list[str]:
        return [*state.get("graph_trace", []), *nodes]

    def _generate_hypothesis(self, state: DiagnosisState) -> dict[str, Any]:
        failure_class = state["failure_class"]
        labels = {
            "electronic_convergence": "dificuldade de convergencia ou estabilidade eletronica",
            "ionic_or_structural": "instabilidade na relaxacao ionica ou na geometria",
            "resources_or_slurm": "falha de recursos ou configuracao do SLURM",
            "converged": "calculo convergido; nao ha falha a corrigir",
            "unknown": "falha ainda nao classificada",
        }
        inspection = state["inspection"]
        recommendations = [fix["description"] for fix in inspection.get("suggested_fixes", [])]
        if failure_class == "resources_or_slurm":
            recommendations.append("Revisar MaxRSS, memoria solicitada e distribuicao de ranks antes de reenviar.")
        limitations: list[str] = []
        if not state.get("citations"):
            limitations.append("Nenhuma evidencia compativel foi recuperada da base local.")
        if not state.get("log_excerpt"):
            limitations.append("Nenhum log OUTCAR, OSZICAR, vasp.out ou SLURM estava disponivel.")
        hypothesis = f"Hipotese: {labels[failure_class]}."
        confidence = "high" if len(state.get("citations", [])) >= 2 and inspection.get("detected_errors") else "medium"
        if failure_class == "unknown" or not state.get("citations"):
            confidence = "low"
        return {
            "hypothesis": hypothesis,
            "confidence": confidence,
            "recommendations": list(dict.fromkeys(recommendations)),
            "limitations": limitations,
            "graph_trace": self._append_trace(state, "gerar_hipoteses"),
        }

    def _validate_recommendations(self, state: DiagnosisState) -> dict[str, Any]:
        checks = [
            "Nenhum arquivo foi alterado durante o diagnostico.",
            "Nenhum job foi submetido ou cancelado.",
            "As recomendacoes continuam sujeitas aos validadores deterministicas do projeto.",
            "Aplicacao e submissao exigem uma acao separada depois da aprovacao humana.",
        ]
        has_evidence = bool(state.get("citations"))
        if state["failure_class"] == "unknown":
            has_evidence = False
        status = "awaiting_approval" if has_evidence else "insufficient_evidence"
        return {
            "safety_checks": checks,
            "status": status,
            "graph_trace": self._append_trace(state, "validar_recomendacoes"),
        }

    def _request_human_approval(self, state: DiagnosisState) -> dict[str, Any]:
        return {"graph_trace": self._append_trace(state, "solicitar_aprovacao_humana")}

    def diagnose(self, calc_path: str, goal: str | None = None, top_k: int = 5) -> dict[str, Any]:
        initial: DiagnosisState = {
            "diagnosis_id": str(uuid.uuid4()),
            "calc_path": str(Path(calc_path).resolve()),
            "goal": goal,
            "top_k": top_k,
            "graph_trace": [],
            "human_decision": None,
            "human_note": None,
        }
        if self.graph is not None:
            result = dict(self.graph.invoke(initial))
        else:
            result: dict[str, Any] = dict(initial)
            for node in (
                self._collect_files,
                self._classify_failure,
                self._retrieve_evidence,
                self._generate_hypothesis,
                self._validate_recommendations,
                self._request_human_approval,
            ):
                result.update(node(result))
        result.pop("inspection", None)
        result.pop("log_excerpt", None)
        result.pop("calculation_type", None)
        result.pop("goal", None)
        result.pop("top_k", None)
        return self.store.save(result)

