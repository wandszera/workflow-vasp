from __future__ import annotations

import uuid
from typing import Any

from ..schemas import AgentInspectionResponse, WorkflowHistoryEntry, WorkflowResponse
from .executor import WorkflowExecutor
from .executor_registry import ExecutorRegistry
from .vasp_agent import VaspWorkflowAgent
from .sqlite_workflow_store import WorkflowStore


class WorkflowService:
    def __init__(
        self,
        executor: WorkflowExecutor | None,
        agent: VaspWorkflowAgent,
        store: WorkflowStore | None = None,
        executor_registry: ExecutorRegistry | None = None,
    ) -> None:
        self.executor = executor
        self.agent = agent
        self.store = store or WorkflowStore()
        self.executor_registry = executor_registry or ExecutorRegistry()

    def create_workflow(
        self,
        project_name: str,
        executor_name: str,
        scenario: str,
        goal: str,
        auto_apply_fixes: bool = False,
        job_settings: dict[str, object] | None = None,
    ) -> WorkflowResponse:
        workflow_id = str(uuid.uuid4())
        executor = self._resolve_executor(executor_name)
        job = executor.create_job(
            project_name=project_name,
            scenario=scenario,
            goal=goal,
            job_settings=job_settings,
        )
        inspection = self.agent.inspect(job.calc_path, goal=goal, apply_fixes=auto_apply_fixes)
        latest_next_step = self._build_next_step(job.metadata, inspection.next_step)

        workflow = {
            "workflow_id": workflow_id,
            "project_name": project_name,
            "goal": goal,
            "executor": executor_name,
            "scenario": scenario,
            "auto_apply_fixes": auto_apply_fixes,
            "job_id": job.job_id,
            "calc_path": job.calc_path,
            "current_stage": job.stage,
            "job_status": job.status,
            "agent_status": inspection.status,
            "latest_summary": inspection.summary,
            "latest_next_step": latest_next_step,
            "latest_results": inspection.extracted_results,
            "execution_metadata": job.metadata,
            "job_settings": job_settings or {},
            "history": [self._history_entry(job.stage, job.status, inspection, latest_next_step)],
        }
        self.store.save_workflow(workflow)
        return WorkflowResponse(**workflow)

    def advance_workflow(self, workflow_id: str) -> WorkflowResponse:
        workflow = self.store.get_workflow(workflow_id)
        executor = self._resolve_executor(str(workflow.get("executor", "mock")))
        job = executor.advance_job(workflow["job_id"])
        inspection = self.agent.inspect(
            job.calc_path,
            goal=workflow["goal"],
            apply_fixes=bool(workflow["auto_apply_fixes"]),
        )
        latest_next_step = self._build_next_step(job.metadata, inspection.next_step)

        workflow["calc_path"] = job.calc_path
        workflow["current_stage"] = job.stage
        workflow["job_status"] = job.status
        workflow["agent_status"] = inspection.status
        workflow["latest_summary"] = inspection.summary
        workflow["latest_next_step"] = latest_next_step
        workflow["latest_results"] = inspection.extracted_results
        workflow["execution_metadata"] = job.metadata
        workflow["job_settings"] = workflow.get("job_settings", {})
        workflow["history"].append(self._history_entry(job.stage, job.status, inspection, latest_next_step))

        self.store.save_workflow(workflow)
        return WorkflowResponse(**workflow)

    def get_workflow(self, workflow_id: str) -> WorkflowResponse:
        return WorkflowResponse(**self.store.get_workflow(workflow_id))

    def list_workflows(self) -> list[WorkflowResponse]:
        return [WorkflowResponse(**workflow) for workflow in self.store.list_workflows()]

    def list_cluster_jobs(self, scope: str = "user") -> list[dict[str, Any]]:
        executor = self._resolve_executor("ssh_slurm")
        jobs = executor.list_cluster_jobs(scope=scope) if hasattr(executor, "list_cluster_jobs") else []
        workflow_lookup = {
            str(workflow["job_id"]): workflow
            for workflow in self.store.list_workflows()
            if workflow.get("executor") == "ssh_slurm"
        }
        enriched_jobs: list[dict[str, Any]] = []
        for job in jobs:
            matched_workflow = None
            scheduler_job_id = str(job.get("scheduler_job_id") or "")
            remote_path = str(job.get("remote_path") or "")
            for workflow in workflow_lookup.values():
                execution_metadata = workflow.get("execution_metadata", {})
                if str(execution_metadata.get("scheduler_job_id") or "") == scheduler_job_id:
                    matched_workflow = workflow
                    break
                if remote_path and str(execution_metadata.get("remote_path") or "") == remote_path:
                    matched_workflow = workflow
                    break

            enriched = dict(job)
            enriched["workflow_id"] = str(matched_workflow["workflow_id"]) if matched_workflow else None
            enriched["project_name"] = (
                str(matched_workflow["project_name"])
                if matched_workflow
                else str(job.get("project_name") or job.get("name") or "")
            )
            enriched_jobs.append(enriched)
        return enriched_jobs

    def _resolve_executor(self, executor_name: str) -> WorkflowExecutor:
        if self.executor is not None and getattr(self.executor, "executor_name", None) == executor_name:
            return self.executor
        return self.executor_registry.get(executor_name)

    @staticmethod
    def _history_entry(
        stage: int,
        job_status: str,
        inspection: AgentInspectionResponse,
        next_step: str,
    ) -> dict[str, Any]:
        entry = WorkflowHistoryEntry(
            step=stage,
            job_status=job_status,
            agent_status=inspection.status,
            summary=inspection.summary,
            next_step=next_step,
        )
        return entry.model_dump()

    @staticmethod
    def _build_next_step(execution_metadata: dict[str, Any], agent_next_step: str) -> str:
        workflow_stages = execution_metadata.get("workflow_stages")
        current_stage_name = execution_metadata.get("current_stage_name")
        if isinstance(workflow_stages, list) and current_stage_name in workflow_stages:
            index = workflow_stages.index(current_stage_name)
            if index + 1 < len(workflow_stages):
                return f"{agent_next_step} Depois disso, avancar para a etapa {workflow_stages[index + 1]}."
        return agent_next_step
