from __future__ import annotations

import json
import os
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from ..schemas import AgentInspectionResponse
from .sqlite_workflow_store import WorkflowStore
from .vasp_agent import VaspWorkflowAgent
from .executor_registry import ExecutorRegistry


class TaskQueue:
    def __init__(
        self,
        store: WorkflowStore,
        agent: VaspWorkflowAgent,
        executor_registry: ExecutorRegistry
    ) -> None:
        self.store = store
        self.agent = agent
        self.executor_registry = executor_registry
        self.active_tasks: dict[str, threading.Thread] = {}
        
        app_root = Path(__file__).resolve().parent.parent
        self.log_dir = app_root / "data" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def get_log_path(self, workflow_id: str) -> Path:
        return self.log_dir / f"{workflow_id}.log"

    def write_log(self, workflow_id: str, message: str) -> None:
        log_path = self.get_log_path(workflow_id)
        with open(log_path, "a", encoding="utf-8") as f:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {message}\n")

    def read_logs(self, workflow_id: str) -> str:
        log_path = self.get_log_path(workflow_id)
        if not log_path.exists():
            return "Nenhum log gravado para este workflow ainda."
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def submit_advance_task(self, workflow_id: str) -> None:
        if workflow_id in self.active_tasks and self.active_tasks[workflow_id].is_alive():
            self.write_log(workflow_id, "AVISO: Uma tarefa ja esta em execucao em background para este workflow.")
            return

        thread = threading.Thread(target=self._run_advance, args=(workflow_id,))
        self.active_tasks[workflow_id] = thread
        thread.start()

    def _run_advance(self, workflow_id: str) -> None:
        self.write_log(workflow_id, "INICIANDO: Avanco de etapa de workflow em background...")
        try:
            workflow = self.store.get_workflow(workflow_id)
            executor_name = workflow.get("executor", "mock")
            executor = self.executor_registry.get(executor_name)
            
            # Set statuses to running
            workflow["job_status"] = "running"
            workflow["agent_status"] = "running"
            self.store.save_workflow(workflow)
            
            self.write_log(workflow_id, f"Conectando ao executor '{executor_name}' para avancar o job '{workflow['job_id']}'...")
            job = executor.advance_job(workflow["job_id"])
            self.write_log(workflow_id, f"Executor retornou. Status do job: '{job.status}' na etapa {job.stage}.")
            
            self.write_log(workflow_id, "Iniciando inspecao dos arquivos de calculo via VASP Agent...")
            inspection = self.agent.inspect(
                job.calc_path,
                goal=workflow["goal"],
                apply_fixes=bool(workflow["auto_apply_fixes"]),
            )
            
            workflow_stages = job.metadata.get("workflow_stages")
            current_stage_name = job.metadata.get("current_stage_name")
            agent_next_step = inspection.next_step
            if isinstance(workflow_stages, list) and current_stage_name in workflow_stages:
                index = workflow_stages.index(current_stage_name)
                if index + 1 < len(workflow_stages):
                    latest_next_step = f"{agent_next_step} Depois disso, avancar para a etapa {workflow_stages[index + 1]}."
                else:
                    latest_next_step = agent_next_step
            else:
                latest_next_step = agent_next_step
                
            workflow["calc_path"] = job.calc_path
            workflow["current_stage"] = job.stage
            workflow["job_status"] = job.status
            workflow["agent_status"] = inspection.status
            workflow["latest_summary"] = inspection.summary
            workflow["latest_next_step"] = latest_next_step
            workflow["latest_results"] = inspection.extracted_results
            workflow["execution_metadata"] = job.metadata
            
            history_entry = {
                "step": job.stage,
                "job_status": job.status,
                "agent_status": inspection.status,
                "summary": inspection.summary,
                "next_step": latest_next_step,
            }
            workflow["history"].append(history_entry)
            
            self.store.save_workflow(workflow)
            self.write_log(workflow_id, f"CONCLUIDO: Avanco finalizado. Status final do agente: '{inspection.status}'.")

            # Auto-chaining pipeline execution
            if inspection.status == "converged" or job.status == "converged":
                child_id = self.store.get_child_id(workflow_id)
                if child_id:
                    self.write_log(workflow_id, f"PIPELINE CHAINING: Workflow pai convergiu. Inicializando workflow filho '{child_id}'...")
                    try:
                        child_wf = self.store.get_workflow(child_id)
                        parent_contcar = Path(job.calc_path) / "CONTCAR"
                        child_poscar = Path(child_wf["calc_path"]) / "POSCAR"

                        if parent_contcar.exists():
                            import shutil
                            child_poscar.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(parent_contcar, child_poscar)
                            self.write_log(workflow_id, f"Estrutura geometrica copiada de '{parent_contcar}' para '{child_poscar}'.")
                        else:
                            self.write_log(workflow_id, "AVISO: CONTCAR do pai nao encontrado. Prosseguindo sem copiar estrutura.")

                        # Start running the child job in background
                        self.submit_advance_task(child_id)
                    except Exception as chain_err:
                        self.write_log(workflow_id, f"ERRO ao iniciar workflow filho no pipeline: {chain_err}")
        except Exception as e:
            tb = traceback.format_exc()
            self.write_log(workflow_id, f"ERRO CRITICO: Falha na execucao em background: {str(e)}\nTraceback:\n{tb}")
            try:
                workflow = self.store.get_workflow(workflow_id)
                workflow["job_status"] = "failed"
                workflow["agent_status"] = "failed"
                self.store.save_workflow(workflow)
            except Exception:
                pass
