from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class WorkflowStore:
    def __init__(self, db_path: Path | None = None) -> None:
        app_root = Path(__file__).resolve().parent.parent
        self.db_path = db_path or app_root / "data" / "workflows.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def list_workflows(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    workflow_id,
                    project_name,
                    goal,
                    executor,
                    scenario,
                    auto_apply_fixes,
                    job_id,
                    calc_path,
                    current_stage,
                    job_status,
                    agent_status,
                    latest_summary,
                    latest_next_step,
                    latest_results,
                    job_settings,
                    execution_metadata
                FROM workflows
                ORDER BY updated_at DESC, rowid DESC
                """
            ).fetchall()

        return [self._row_to_workflow(row) for row in rows]

    def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    workflow_id,
                    project_name,
                    goal,
                    executor,
                    scenario,
                    auto_apply_fixes,
                    job_id,
                    calc_path,
                    current_stage,
                    job_status,
                    agent_status,
                    latest_summary,
                    latest_next_step,
                    latest_results,
                    job_settings,
                    execution_metadata
                FROM workflows
                WHERE workflow_id = ?
                """,
                (workflow_id,),
            ).fetchone()

            if row is None:
                raise FileNotFoundError(f"Workflow nao encontrado: {workflow_id}")

            history_rows = connection.execute(
                """
                SELECT step, job_status, agent_status, summary, next_step
                FROM workflow_history
                WHERE workflow_id = ?
                ORDER BY step ASC, id ASC
                """,
                (workflow_id,),
            ).fetchall()

        workflow = self._row_to_workflow(row)
        workflow["history"] = [dict(history_row) for history_row in history_rows]
        return workflow

    def save_workflow(self, workflow: dict[str, Any]) -> dict[str, Any]:
        history = workflow.get("history", [])
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workflows (
                    workflow_id,
                    project_name,
                    goal,
                    executor,
                    scenario,
                    auto_apply_fixes,
                    job_id,
                    calc_path,
                    current_stage,
                    job_status,
                    agent_status,
                    latest_summary,
                    latest_next_step,
                    latest_results,
                    job_settings,
                    execution_metadata,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(workflow_id) DO UPDATE SET
                    project_name = excluded.project_name,
                    goal = excluded.goal,
                    executor = excluded.executor,
                    scenario = excluded.scenario,
                    auto_apply_fixes = excluded.auto_apply_fixes,
                    job_id = excluded.job_id,
                    calc_path = excluded.calc_path,
                    current_stage = excluded.current_stage,
                    job_status = excluded.job_status,
                    agent_status = excluded.agent_status,
                    latest_summary = excluded.latest_summary,
                    latest_next_step = excluded.latest_next_step,
                    latest_results = excluded.latest_results,
                    job_settings = excluded.job_settings,
                    execution_metadata = excluded.execution_metadata,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    workflow["workflow_id"],
                    workflow["project_name"],
                    workflow["goal"],
                    workflow.get("executor", "mock"),
                    workflow["scenario"],
                    int(bool(workflow["auto_apply_fixes"])),
                    workflow["job_id"],
                    workflow["calc_path"],
                    workflow["current_stage"],
                    workflow["job_status"],
                    workflow["agent_status"],
                    workflow["latest_summary"],
                    workflow["latest_next_step"],
                    json.dumps(workflow["latest_results"]),
                    json.dumps(workflow.get("job_settings", {})),
                    json.dumps(workflow.get("execution_metadata", {})),
                ),
            )

            connection.execute("DELETE FROM workflow_history WHERE workflow_id = ?", (workflow["workflow_id"],))
            connection.executemany(
                """
                INSERT INTO workflow_history (
                    workflow_id,
                    step,
                    job_status,
                    agent_status,
                    summary,
                    next_step
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        workflow["workflow_id"],
                        entry["step"],
                        entry["job_status"],
                        entry["agent_status"],
                        entry["summary"],
                        entry["next_step"],
                    )
                    for entry in history
                ],
            )
            connection.commit()
        return workflow

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflows (
                    workflow_id TEXT PRIMARY KEY,
                    project_name TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    executor TEXT NOT NULL DEFAULT 'mock',
                    scenario TEXT NOT NULL,
                    auto_apply_fixes INTEGER NOT NULL,
                    job_id TEXT NOT NULL,
                    calc_path TEXT NOT NULL,
                    current_stage INTEGER NOT NULL,
                    job_status TEXT NOT NULL,
                    agent_status TEXT NOT NULL,
                    latest_summary TEXT NOT NULL,
                    latest_next_step TEXT NOT NULL,
                    latest_results TEXT NOT NULL,
                    job_settings TEXT NOT NULL DEFAULT '{}',
                    execution_metadata TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS workflow_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id TEXT NOT NULL,
                    step INTEGER NOT NULL,
                    job_status TEXT NOT NULL,
                    agent_status TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    next_step TEXT NOT NULL,
                    FOREIGN KEY(workflow_id) REFERENCES workflows(workflow_id) ON DELETE CASCADE
                );
                """
            )
            existing_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(workflows)").fetchall()
            }
            if "executor" not in existing_columns:
                connection.execute("ALTER TABLE workflows ADD COLUMN executor TEXT NOT NULL DEFAULT 'mock'")
            if "execution_metadata" not in existing_columns:
                connection.execute("ALTER TABLE workflows ADD COLUMN execution_metadata TEXT NOT NULL DEFAULT '{}'")
            if "job_settings" not in existing_columns:
                connection.execute("ALTER TABLE workflows ADD COLUMN job_settings TEXT NOT NULL DEFAULT '{}'")
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _row_to_workflow(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "workflow_id": row["workflow_id"],
            "project_name": row["project_name"],
            "goal": row["goal"],
            "executor": row["executor"] if "executor" in row.keys() else "mock",
            "scenario": row["scenario"],
            "auto_apply_fixes": bool(row["auto_apply_fixes"]),
            "job_id": row["job_id"],
            "calc_path": row["calc_path"],
            "current_stage": row["current_stage"],
            "job_status": row["job_status"],
            "agent_status": row["agent_status"],
            "latest_summary": row["latest_summary"],
            "latest_next_step": row["latest_next_step"],
            "latest_results": json.loads(row["latest_results"]),
            "job_settings": json.loads(row["job_settings"]) if "job_settings" in row.keys() else {},
            "execution_metadata": json.loads(row["execution_metadata"]) if "execution_metadata" in row.keys() else {},
            "history": [],
        }
