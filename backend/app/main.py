from pathlib import Path
import uuid

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .schemas import (
    AgentInspectionRequest,
    AgentInspectionResponse,
    AnalysisResultEntry,
    BindingEnergyComponent,
    BindingEnergyRequest,
    BindingEnergyResponse,
    ClusterConfigResponse,
    ClusterSessionPasswordRequest,
    ClusterConfigUpdateRequest,
    ClusterJobEntry,
    EcnResponse,
    MockJobCreateRequest,
    MockJobResponse,
    RecommendationPreviewEntry,
    TemplateCatalogEntry,
    WorkflowFilePreviewEntry,
    WorkflowFileUpdateRequest,
    WorkflowCreateRequest,
    WorkflowResponse,
)
from .services.mock_cluster import MockClusterService
from .services.cluster_config import ClusterConfig, load_cluster_config, save_cluster_config
from .services.executor_registry import ExecutorRegistry
from .services.ecn_service import EcnService
from .services.mlff_training_executor import MlffTrainingExecutor
from .services.ssh_slurm_executor import SshSlurmExecutor
from .services.vasp_agent import VaspWorkflowAgent
from .services.vasp_analysis_service import VaspAnalysisService
from .services.sqlite_workflow_store import WorkflowStore
from .services.workflow_service import WorkflowService


app = FastAPI(
    title="Workflow VASP AI Assistant",
    version="0.1.0",
    description="MVP de agente especialista para diagnostico e automacao de workflows VASP.",
)

agent = VaspWorkflowAgent()
analysis_service = VaspAnalysisService()
ecn_service = EcnService()
mock_cluster = MockClusterService()
mlff_training_executor = MlffTrainingExecutor()
ssh_slurm_executor = SshSlurmExecutor(
    password_provider=lambda: cluster_session_secret.get("password")
)
template_service = ssh_slurm_executor.template_service
executor_registry = ExecutorRegistry(
    mock_executor=mock_cluster,
    ssh_slurm_executor=ssh_slurm_executor,
    mlff_training_executor=mlff_training_executor,
)
workflow_service = WorkflowService(
    executor=mock_cluster,
    agent=agent,
    store=WorkflowStore(),
    executor_registry=executor_registry,
)
cluster_session_secret: dict[str, str | None] = {"password": None}
static_dir = Path(__file__).resolve().parent / "static"

app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def dashboard() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/analysis")
def analysis_dashboard() -> FileResponse:
    return FileResponse(static_dir / "analysis.html")


@app.get("/cluster")
def cluster_dashboard() -> FileResponse:
    return FileResponse(static_dir / "cluster.html")


@app.get("/templates", response_model=list[TemplateCatalogEntry])
def list_templates() -> list[TemplateCatalogEntry]:
    return [TemplateCatalogEntry(**entry) for entry in template_service.list_available_templates()]


@app.get("/cluster/config", response_model=ClusterConfigResponse)
def get_cluster_config() -> ClusterConfigResponse:
    config = load_cluster_config()
    return ClusterConfigResponse(
        ssh_host=config.ssh_host,
        ssh_user=config.ssh_user,
        remote_base_dir=config.remote_base_dir,
        dry_run=config.dry_run,
        identity_file=config.identity_file,
        ssh_target=config.ssh_target,
        has_session_password=bool(cluster_session_secret.get("password")),
    )


@app.post("/cluster/config", response_model=ClusterConfigResponse)
def update_cluster_config(payload: ClusterConfigUpdateRequest) -> ClusterConfigResponse:
    config = ClusterConfig(
        ssh_host=payload.ssh_host,
        ssh_user=payload.ssh_user,
        remote_base_dir=payload.remote_base_dir,
        dry_run=payload.dry_run,
        identity_file=payload.identity_file,
    )
    saved = save_cluster_config(config)
    global ssh_slurm_executor, template_service, executor_registry, workflow_service
    ssh_slurm_executor = SshSlurmExecutor(
        password_provider=lambda: cluster_session_secret.get("password")
    )
    template_service = ssh_slurm_executor.template_service
    executor_registry = ExecutorRegistry(
        mock_executor=mock_cluster,
        ssh_slurm_executor=ssh_slurm_executor,
        mlff_training_executor=mlff_training_executor,
    )
    workflow_service.executor_registry = executor_registry
    return ClusterConfigResponse(
        ssh_host=saved.ssh_host,
        ssh_user=saved.ssh_user,
        remote_base_dir=saved.remote_base_dir,
        dry_run=saved.dry_run,
        identity_file=saved.identity_file,
        ssh_target=saved.ssh_target,
        has_session_password=bool(cluster_session_secret.get("password")),
    )


@app.post("/cluster/session-password", response_model=ClusterConfigResponse)
def update_cluster_session_password(payload: ClusterSessionPasswordRequest) -> ClusterConfigResponse:
    cluster_session_secret["password"] = payload.password
    config = load_cluster_config()
    return ClusterConfigResponse(
        ssh_host=config.ssh_host,
        ssh_user=config.ssh_user,
        remote_base_dir=config.remote_base_dir,
        dry_run=config.dry_run,
        identity_file=config.identity_file,
        ssh_target=config.ssh_target,
        has_session_password=True,
    )


@app.get("/cluster/jobs", response_model=list[ClusterJobEntry])
def list_cluster_jobs(scope: str = Query(default="user", pattern="^(user|all)$")) -> list[ClusterJobEntry]:
    return [ClusterJobEntry(**entry) for entry in workflow_service.list_cluster_jobs(scope=scope)]


@app.post("/agent/inspect", response_model=AgentInspectionResponse)
def inspect_calculation(payload: AgentInspectionRequest) -> AgentInspectionResponse:
    try:
        return agent.inspect(
            calc_path=payload.calc_path,
            goal=payload.goal,
            apply_fixes=payload.apply_fixes,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/mock/jobs", response_model=MockJobResponse)
def create_mock_job(payload: MockJobCreateRequest) -> MockJobResponse:
    return mock_cluster.create_job(
        project_name=payload.project_name,
        scenario=payload.scenario,
        goal=payload.goal,
    )


@app.post("/mock/jobs/{job_id}/advance", response_model=MockJobResponse)
def advance_mock_job(job_id: str) -> MockJobResponse:
    try:
        return mock_cluster.advance_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/workflows", response_model=list[WorkflowResponse])
def list_workflows() -> list[WorkflowResponse]:
    return workflow_service.list_workflows()


@app.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(workflow_id: str) -> WorkflowResponse:
    try:
        return workflow_service.get_workflow(workflow_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/workflows/{workflow_id}/analysis", response_model=list[AnalysisResultEntry])
def analyze_workflow(workflow_id: str) -> list[AnalysisResultEntry]:
    try:
        workflow = workflow_service.get_workflow(workflow_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [AnalysisResultEntry(**entry) for entry in analysis_service.analyze_workflow(workflow.calc_path)]


@app.post("/analysis/binding-energy", response_model=BindingEnergyResponse)
def calculate_binding_energy(payload: BindingEnergyRequest) -> BindingEnergyResponse:
    try:
        target_workflow = workflow_service.get_workflow(payload.target_workflow_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not payload.reference_workflow_ids:
        raise HTTPException(status_code=400, detail="Informe ao menos um workflow de referencia.")

    reference_workflows = []
    for workflow_id in payload.reference_workflow_ids:
        try:
            reference_workflows.append(workflow_service.get_workflow(workflow_id))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        result = analysis_service.compute_binding_energy(
            target_calc_path=target_workflow.calc_path,
            reference_calc_paths=[workflow.calc_path for workflow in reference_workflows],
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    target_energy = float(result["target_energy_ev"])
    reference_energies = [float(value) for value in result["reference_energies_ev"]]
    formula_terms = " - ".join([f"{target_energy:.6f}"] + [f"{value:.6f}" for value in reference_energies])
    return BindingEnergyResponse(
        target=BindingEnergyComponent(
            workflow_id=target_workflow.workflow_id,
            project_name=target_workflow.project_name,
            energy_ev=target_energy,
        ),
        references=[
            BindingEnergyComponent(
                workflow_id=workflow.workflow_id,
                project_name=workflow.project_name,
                energy_ev=reference_energies[index],
            )
            for index, workflow in enumerate(reference_workflows)
        ],
        binding_energy_ev=float(result["binding_energy_ev"]),
        formula=f"E_lig = {formula_terms}",
        summary=(
            f"Energia de ligacao estimada em {result['binding_energy_ev']} eV para "
            f"{target_workflow.project_name} usando {len(reference_workflows)} referencia(s)."
        ),
    )


@app.get("/workflows/{workflow_id}/ecn", response_model=EcnResponse)
def calculate_workflow_ecn(workflow_id: str) -> EcnResponse:
    try:
        workflow = workflow_service.get_workflow(workflow_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    try:
        result = ecn_service.compute_from_poscar(Path(workflow.calc_path) / "POSCAR")
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return EcnResponse(
        workflow_id=workflow.workflow_id,
        project_name=workflow.project_name,
        n_atoms=int(result["n_atoms"]),
        species_labels=[str(value) for value in result["species_labels"]],
        species_counts=[int(value) for value in result["species_counts"]],
        average_ecn=float(result["average_ecn"]),
        total_ecn=float(result["total_ecn"]),
        weighted_average_bond_length=float(result["weighted_average_bond_length"]),
        supercell_atom_count=int(result["supercell_atom_count"]),
        ecn_by_atom=[float(value) for value in result["ecn_by_atom"]],
        rwabl_by_atom=[float(value) for value in result["rwabl_by_atom"]],
        rmin_by_atom=[float(value) for value in result["rmin_by_atom"]],
        nearest_neighbors=[int(value) for value in result["nearest_neighbors"]],
        summary=(
            f"ECN medio de {result['average_ecn']} para {workflow.project_name} "
            f"com {result['n_atoms']} atomos no POSCAR."
        ),
    )


def _build_recommendation_preview(workflow: WorkflowResponse) -> RecommendationPreviewEntry:
    analysis_results = analysis_service.analyze_workflow(workflow.calc_path)
    recommendation = next(
        (entry for entry in analysis_results if entry.get("tool") == "next_calculation_recommendation"),
        None,
    )
    if recommendation is None:
        raise HTTPException(status_code=409, detail="Nenhuma recomendacao disponivel para este workflow.")

    recommended_step = str(recommendation.get("details", {}).get("recommended_step") or "")
    calc_type_map = {
        "continuar_relaxacao": "relax",
        "revisar_relaxacao": "relax",
        "validar_artefatos": "relax",
        "rodar_dos": "dos",
        "rodar_phonons": "phonons",
        "expandir_dataset_mlff": "mlff_training",
        "promover_mlff": "mlff_training",
    }
    goal_map = {
        "continuar_relaxacao": "Continuar relaxacao estrutural com os artefatos mais recentes",
        "revisar_relaxacao": "Revisar e repetir relaxacao estrutural",
        "validar_artefatos": "Validar artefatos e repetir uma relaxacao curta",
        "rodar_dos": "Executar calculo de DOS a partir da ultima estrutura convergida",
        "rodar_phonons": "Executar calculo de phonons a partir da ultima estrutura convergida",
        "expandir_dataset_mlff": "Expandir o dataset de referencia e repetir o treino MLFF",
        "promover_mlff": "Promover o potencial MLFF validado para benchmarking e inferencia",
    }
    if recommended_step not in calc_type_map:
        raise HTTPException(status_code=409, detail=f"Recomendacao nao materializavel: {recommended_step}")

    calc_path = Path(workflow.calc_path)
    structure_source = None
    structure_origin = None
    for candidate in ["CONTCAR", "POSCAR"]:
        candidate_path = calc_path / candidate
        if candidate_path.exists():
            structure_source = str(candidate_path)
            structure_origin = candidate
            break

    return RecommendationPreviewEntry(
        recommended_step=recommended_step,
        calculation_type=calc_type_map[recommended_step],
        goal=goal_map[recommended_step],
        structure_source=structure_source,
        structure_origin=structure_origin,
        summary=str(recommendation.get("summary") or ""),
    )


@app.get("/workflows/{workflow_id}/recommendation-preview", response_model=RecommendationPreviewEntry)
def get_workflow_recommendation_preview(workflow_id: str) -> RecommendationPreviewEntry:
    try:
        workflow = workflow_service.get_workflow(workflow_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _build_recommendation_preview(workflow)

 
@app.post("/workflows/{workflow_id}/apply-recommendation", response_model=WorkflowResponse)
def apply_workflow_recommendation(workflow_id: str) -> WorkflowResponse:
    try:
        workflow = workflow_service.get_workflow(workflow_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    recommendation_preview = _build_recommendation_preview(workflow)

    derived_settings = dict(workflow.job_settings)
    derived_settings["calculation_type"] = recommendation_preview.calculation_type
    derived_settings["template_name"] = None
    derived_settings["workflow_recipe"] = None
    if recommendation_preview.structure_source:
        derived_settings["structure_source"] = recommendation_preview.structure_source

    project_suffix = recommendation_preview.recommended_step.replace("_", "-")
    derived_project_name = f"{workflow.project_name}-{project_suffix}-{str(uuid.uuid4())[:4]}"
    return workflow_service.create_workflow(
        project_name=derived_project_name,
        executor_name=workflow.executor,
        scenario="running",
        goal=recommendation_preview.goal,
        auto_apply_fixes=workflow.auto_apply_fixes,
        job_settings=derived_settings,
    )


@app.get("/workflows/{workflow_id}/files-preview", response_model=list[WorkflowFilePreviewEntry])
def get_workflow_file_previews(workflow_id: str) -> list[WorkflowFilePreviewEntry]:
    try:
        workflow = workflow_service.get_workflow(workflow_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    calc_path = Path(workflow.calc_path)
    preview_specs = {
        "INCAR": 120,
        "KPOINTS": 40,
        "submit_vasp.slurm": 80,
        "POSCAR": 40,
    }
    previews: list[WorkflowFilePreviewEntry] = []
    for filename, max_lines in preview_specs.items():
        file_path = calc_path / filename
        if file_path.exists():
            lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()[:max_lines]
            content = "\n".join(lines)
        else:
            content = ""
        previews.append(
            WorkflowFilePreviewEntry(
                name=filename,
                exists=file_path.exists(),
                content=content,
            )
        )
    return previews


@app.post("/workflows/{workflow_id}/files", response_model=WorkflowResponse)
def update_workflow_files(workflow_id: str, payload: WorkflowFileUpdateRequest) -> WorkflowResponse:
    try:
        workflow = workflow_service.get_workflow(workflow_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    calc_path = Path(workflow.calc_path)
    updated = False
    if payload.incar is not None:
        (calc_path / "INCAR").write_text(payload.incar.rstrip() + "\n", encoding="utf-8")
        updated = True
    if payload.kpoints is not None:
        (calc_path / "KPOINTS").write_text(payload.kpoints.rstrip() + "\n", encoding="utf-8")
        updated = True

    if not updated:
        return workflow

    inspection = agent.inspect(
        calc_path=workflow.calc_path,
        goal=workflow.goal,
        apply_fixes=False,
    )
    workflow.latest_summary = inspection.summary
    workflow.latest_next_step = inspection.next_step
    workflow.latest_results = inspection.extracted_results
    workflow.agent_status = inspection.status
    workflow_service.store.save_workflow(workflow.model_dump())
    return workflow_service.get_workflow(workflow_id)


@app.post("/workflows/mock", response_model=WorkflowResponse)
def create_mock_workflow(payload: WorkflowCreateRequest) -> WorkflowResponse:
    return workflow_service.create_workflow(
        project_name=payload.project_name,
        executor_name=payload.executor,
        scenario=payload.scenario,
        goal=payload.goal,
        auto_apply_fixes=payload.auto_apply_fixes,
        job_settings={
            "structure_source": payload.structure_source,
            "kpoints_mesh": payload.kpoints_mesh,
            "calculation_type": payload.calculation_type,
            "template_name": payload.template_name,
            "workflow_recipe": payload.workflow_recipe,
            "mlff_dataset_source": payload.mlff_dataset_source,
            "mlff_reference_count": payload.mlff_reference_count,
            "mlff_force_tolerance": payload.mlff_force_tolerance,
            "mlff_temperature_schedule": payload.mlff_temperature_schedule,
            "mlff_target_rmse": payload.mlff_target_rmse,
            "mlff_min_reference_count": payload.mlff_min_reference_count,
        },
    )


@app.post("/workflows/{workflow_id}/advance", response_model=WorkflowResponse)
def advance_workflow(workflow_id: str) -> WorkflowResponse:
    try:
        return workflow_service.advance_workflow(workflow_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
