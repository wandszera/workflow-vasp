from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MetadataValue = str | float | int | bool | None | list[str] | list[int]


class AgentInspectionRequest(BaseModel):
    calc_path: str = Field(..., description="Diretorio do calculo VASP a ser analisado.")
    goal: str | None = Field(
        default=None,
        description="Objetivo do workflow, por exemplo: otimizacao, DOS, adsorcao.",
    )
    apply_fixes: bool = Field(
        default=False,
        description="Aplica correcoes diretamente no INCAR quando possivel.",
    )


class SuggestedFix(BaseModel):
    source: str
    description: str
    file: str | None = None
    applied: bool = False


class AgentInspectionResponse(BaseModel):
    calc_path: str
    status: Literal["ready", "running", "converged", "failed", "warning", "unknown"]
    summary: str
    detected_errors: list[str]
    extracted_results: dict[str, str | float | int | bool | None]
    suggested_fixes: list[SuggestedFix]
    next_step: str


class MockJobCreateRequest(BaseModel):
    project_name: str = Field(..., description="Nome curto do experimento local.")
    scenario: Literal["success", "zbrent_error", "running", "dos_ready"] = Field(
        ...,
        description="Cenario simulado para o job VASP.",
    )
    goal: str | None = Field(
        default=None,
        description="Objetivo do workflow associado ao job simulado.",
    )


class MockJobResponse(BaseModel):
    job_id: str
    calc_path: str
    scenario: str
    stage: int
    status: Literal["queued", "running", "converged", "failed"]
    message: str


class WorkflowCreateRequest(BaseModel):
    project_name: str = Field(..., description="Nome do workflow local.")
    executor: Literal["mock", "ssh_slurm", "mlff_training"] = Field(
        default="mock",
        description="Executor a ser usado no workflow.",
    )
    scenario: Literal["success", "zbrent_error", "running", "dos_ready"] = Field(
        ...,
        description="Cenario mock que representa o tipo de execucao inicial.",
    )
    goal: str = Field(..., description="Objetivo cientifico ou tecnico do workflow.")
    auto_apply_fixes: bool = Field(
        default=False,
        description="Se verdadeiro, o agente pode atualizar o INCAR automaticamente.",
    )
    structure_source: str | None = Field(
        default=None,
        description="Conteudo POSCAR inline ou caminho de arquivo para a estrutura inicial.",
    )
    kpoints_mesh: list[int] | None = Field(
        default=None,
        description="Malha Monkhorst-Pack/Gamma em tres inteiros, por exemplo [4,4,4].",
    )
    calculation_type: Literal["relax", "dos", "aimd", "phonons", "band", "neb", "surface_relax", "mlff_training"] | None = Field(
        default=None,
        description="Tipo explicito de calculo para selecionar o template.",
    )
    template_name: str | None = Field(
        default=None,
        description="Nome de um template real em backend/templates ou de um preset builtin.",
    )
    workflow_recipe: Literal["aimd_relax_dos_phonons", "band_structure", "aimd", "neb", "phonons", "surface_adsorption", "mlff_complete"] | None = Field(
        default=None,
        description="Preset de workflow multi-etapa para encadear calculos VASP.",
    )
    mlff_dataset_source: str | None = Field(
        default=None,
        description="Caminho ou descricao da origem dos dados usados no treino MLFF.",
    )
    mlff_reference_count: int | None = Field(
        default=None,
        description="Numero esperado de estruturas de referencia para o treino MLFF.",
    )
    mlff_force_tolerance: float | None = Field(
        default=None,
        description="Tolerancia alvo de forca usada como heuristica de treino MLFF.",
    )
    mlff_temperature_schedule: str | None = Field(
        default=None,
        description="Descricao livre do cronograma de temperatura usado para gerar o dataset.",
    )
    mlff_target_rmse: float | None = Field(
        default=None,
        description="RMSE alvo para considerar o potencial MLFF pronto para uso.",
    )
    mlff_min_reference_count: int | None = Field(
        default=None,
        description="Numero minimo de estruturas de referencia antes da validacao final.",
    )


class WorkflowHistoryEntry(BaseModel):
    step: int
    job_status: Literal["queued", "running", "converged", "failed"]
    agent_status: Literal["ready", "running", "converged", "failed", "warning", "unknown"]
    summary: str
    next_step: str


class TemplateCatalogEntry(BaseModel):
    name: str
    source: Literal["real", "builtin"]
    path: str
    calc_type: str


class WorkflowFilePreviewEntry(BaseModel):
    name: str
    exists: bool
    content: str


class WorkflowFileUpdateRequest(BaseModel):
    incar: str | None = Field(default=None, description="Novo conteudo do arquivo INCAR.")
    kpoints: str | None = Field(default=None, description="Novo conteudo do arquivo KPOINTS.")


class ClusterJobEntry(BaseModel):
    scheduler_job_id: str
    name: str
    state: str
    queue: str | None = None
    runtime: str | None = None
    nodes: str | None = None
    remote_path: str | None = None
    workflow_id: str | None = None
    project_name: str | None = None
    owner: str | None = None


class ClusterConfigResponse(BaseModel):
    ssh_host: str
    ssh_user: str
    remote_base_dir: str
    dry_run: bool
    identity_file: str | None = None
    ssh_target: str
    has_session_password: bool = False


class ClusterConfigUpdateRequest(BaseModel):
    ssh_host: str = Field(..., description="Hostname ou IP do cluster SSH.")
    ssh_user: str = Field(..., description="Usuario SSH para submissao no cluster.")
    remote_base_dir: str = Field(..., description="Diretorio base remoto para os workflows.")
    dry_run: bool = Field(default=True, description="Mantem execucao em modo de simulacao local.")
    identity_file: str | None = Field(default=None, description="Caminho opcional para chave SSH.")


class ClusterSessionPasswordRequest(BaseModel):
    password: str = Field(..., description="Senha temporaria usada apenas na sessao atual.")


class AnalysisResultEntry(BaseModel):
    tool: str
    title: str
    status: Literal["ready", "warning", "failed", "unavailable"]
    summary: str
    details: dict[str, MetadataValue]


class BindingEnergyRequest(BaseModel):
    target_workflow_id: str
    reference_workflow_ids: list[str] = Field(
        ...,
        description="Lista de workflows de referencia usados no calculo de energia de ligacao.",
    )


class BindingEnergyComponent(BaseModel):
    workflow_id: str
    project_name: str
    energy_ev: float


class BindingEnergyResponse(BaseModel):
    target: BindingEnergyComponent
    references: list[BindingEnergyComponent]
    binding_energy_ev: float
    formula: str
    summary: str


class EcnResponse(BaseModel):
    workflow_id: str
    project_name: str
    n_atoms: int
    species_labels: list[str]
    species_counts: list[int]
    average_ecn: float
    total_ecn: float
    weighted_average_bond_length: float
    supercell_atom_count: int
    ecn_by_atom: list[float]
    rwabl_by_atom: list[float]
    rmin_by_atom: list[float]
    nearest_neighbors: list[int]
    summary: str


class RecommendationPreviewEntry(BaseModel):
    recommended_step: str
    calculation_type: str
    goal: str
    structure_source: str | None = None
    structure_origin: str | None = None
    summary: str


class WorkflowResponse(BaseModel):
    workflow_id: str
    project_name: str
    goal: str
    executor: Literal["mock", "ssh_slurm", "mlff_training"]
    scenario: str
    auto_apply_fixes: bool
    job_id: str
    calc_path: str
    current_stage: int
    job_status: Literal["queued", "running", "converged", "failed"]
    agent_status: Literal["ready", "running", "converged", "failed", "warning", "unknown"]
    latest_summary: str
    latest_next_step: str
    latest_results: dict[str, str | float | int | bool | None]
    job_settings: dict[str, MetadataValue]
    execution_metadata: dict[str, MetadataValue]
    history: list[WorkflowHistoryEntry]
