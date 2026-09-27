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
                    latest_next_step
                FROM workflows
                ORDER BY updated_at DESC, workflow_id DESC
                """
            ).fetchall()

            workflows = []
            for row in rows:
                w_id = row["workflow_id"]
                
                # Fetch results
                res_rows = connection.execute("SELECT key, value FROM workflow_results WHERE workflow_id = ?", (w_id,)).fetchall()
                latest_results = {}
                for r in res_rows:
                    try:
                        latest_results[r["key"]] = json.loads(r["value"])
                    except Exception:
                        latest_results[r["key"]] = r["value"]

                # Fetch settings
                set_rows = connection.execute("SELECT key, value FROM workflow_settings WHERE workflow_id = ?", (w_id,)).fetchall()
                job_settings = {}
                for r in set_rows:
                    try:
                        job_settings[r["key"]] = json.loads(r["value"])
                    except Exception:
                        job_settings[r["key"]] = r["value"]

                # Fetch metadata
                meta_rows = connection.execute("SELECT key, value FROM workflow_metadata WHERE workflow_id = ?", (w_id,)).fetchall()
                execution_metadata = {}
                for r in meta_rows:
                    try:
                        execution_metadata[r["key"]] = json.loads(r["value"])
                    except Exception:
                        execution_metadata[r["key"]] = r["value"]

                w_dict = {
                    "workflow_id": row["workflow_id"],
                    "project_name": row["project_name"],
                    "goal": row["goal"],
                    "executor": row["executor"],
                    "scenario": row["scenario"],
                    "auto_apply_fixes": bool(row["auto_apply_fixes"]),
                    "job_id": row["job_id"],
                    "calc_path": row["calc_path"],
                    "current_stage": row["current_stage"],
                    "job_status": row["job_status"],
                    "agent_status": row["agent_status"],
                    "latest_summary": row["latest_summary"],
                    "latest_next_step": row["latest_next_step"],
                    "latest_results": latest_results,
                    "job_settings": job_settings,
                    "execution_metadata": execution_metadata,
                    "history": []
                }
                workflows.append(w_dict)
            return workflows

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
                    latest_next_step
                FROM workflows
                WHERE workflow_id = ?
                """,
                (workflow_id,),
            ).fetchone()

            if row is None:
                raise FileNotFoundError(f"Workflow nao encontrado: {workflow_id}")

            # Fetch results
            res_rows = connection.execute("SELECT key, value FROM workflow_results WHERE workflow_id = ?", (workflow_id,)).fetchall()
            latest_results = {}
            for r in res_rows:
                try:
                    latest_results[r["key"]] = json.loads(r["value"])
                except Exception:
                    latest_results[r["key"]] = r["value"]

            # Fetch settings
            set_rows = connection.execute("SELECT key, value FROM workflow_settings WHERE workflow_id = ?", (workflow_id,)).fetchall()
            job_settings = {}
            for r in set_rows:
                try:
                    job_settings[r["key"]] = json.loads(r["value"])
                except Exception:
                    job_settings[r["key"]] = r["value"]

            # Fetch metadata
            meta_rows = connection.execute("SELECT key, value FROM workflow_metadata WHERE workflow_id = ?", (workflow_id,)).fetchall()
            execution_metadata = {}
            for r in meta_rows:
                try:
                    execution_metadata[r["key"]] = json.loads(r["value"])
                except Exception:
                    execution_metadata[r["key"]] = r["value"]

            history_rows = connection.execute(
                """
                SELECT step, job_status, agent_status, summary, next_step
                FROM workflow_history
                WHERE workflow_id = ?
                ORDER BY step ASC, id ASC
                """,
                (workflow_id,),
            ).fetchall()

        w_dict = {
            "workflow_id": row["workflow_id"],
            "project_name": row["project_name"],
            "goal": row["goal"],
            "executor": row["executor"],
            "scenario": row["scenario"],
            "auto_apply_fixes": bool(row["auto_apply_fixes"]),
            "job_id": row["job_id"],
            "calc_path": row["calc_path"],
            "current_stage": row["current_stage"],
            "job_status": row["job_status"],
            "agent_status": row["agent_status"],
            "latest_summary": row["latest_summary"],
            "latest_next_step": row["latest_next_step"],
            "latest_results": latest_results,
            "job_settings": job_settings,
            "execution_metadata": execution_metadata,
            "history": [dict(history_row) for history_row in history_rows]
        }
        return w_dict

    def save_workflow(self, workflow: dict[str, Any]) -> dict[str, Any]:
        history = workflow.get("history", [])
        w_id = workflow["workflow_id"]
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
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
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
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    w_id,
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
                ),
            )

            # Update results
            connection.execute("DELETE FROM workflow_results WHERE workflow_id = ?", (w_id,))
            for key, val in workflow.get("latest_results", {}).items():
                connection.execute(
                    "INSERT INTO workflow_results (workflow_id, key, value) VALUES (?, ?, ?)",
                    (w_id, key, json.dumps(val))
                )

            # Update settings
            connection.execute("DELETE FROM workflow_settings WHERE workflow_id = ?", (w_id,))
            for key, val in workflow.get("job_settings", {}).items():
                connection.execute(
                    "INSERT INTO workflow_settings (workflow_id, key, value) VALUES (?, ?, ?)",
                    (w_id, key, json.dumps(val))
                )

            # Update metadata
            connection.execute("DELETE FROM workflow_metadata WHERE workflow_id = ?", (w_id,))
            for key, val in workflow.get("execution_metadata", {}).items():
                connection.execute(
                    "INSERT INTO workflow_metadata (workflow_id, key, value) VALUES (?, ?, ?)",
                    (w_id, key, json.dumps(val))
                )

            connection.execute("DELETE FROM workflow_history WHERE workflow_id = ?", (w_id,))
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
                        w_id,
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

    def get_stats(self) -> dict[str, any]:
        with self._connect() as connection:
            total_workflows = connection.execute("SELECT COUNT(*) FROM workflows").fetchone()[0] or 0
            running_workflows = connection.execute("SELECT COUNT(*) FROM workflows WHERE job_status = 'running'").fetchone()[0] or 0
            failed_workflows = connection.execute("SELECT COUNT(*) FROM workflows WHERE job_status = 'failed' OR agent_status = 'failed'").fetchone()[0] or 0
            converged_workflows = connection.execute("SELECT COUNT(*) FROM workflows WHERE agent_status = 'converged'").fetchone()[0] or 0
            
            avg_steps_row = connection.execute(
                """
                SELECT AVG(CAST(value AS INTEGER))
                FROM workflow_results
                WHERE key = 'ionic_steps'
                """
            ).fetchone()
            avg_ionic_steps = round(avg_steps_row[0], 1) if avg_steps_row and avg_steps_row[0] is not None else 0.0

            return {
                "total_workflows": total_workflows,
                "running_workflows": running_workflows,
                "failed_workflows": failed_workflows,
                "converged_workflows": converged_workflows,
                "avg_ionic_steps": avg_ionic_steps
            }

    def _initialize(self) -> None:
        with self._connect() as connection:
            # Check if workflows table exists
            table_exists = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='workflows'"
            ).fetchone()
            
            needs_migration = False
            if table_exists:
                # Check if it has JSON columns
                columns = {row["name"] for row in connection.execute("PRAGMA table_info(workflows)").fetchall()}
                if "latest_results" in columns:
                    needs_migration = True

            if needs_migration:
                connection.execute("ALTER TABLE workflows RENAME TO workflows_old")

            # Create new tables
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
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS workflow_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT,
                    FOREIGN KEY(workflow_id) REFERENCES workflows(workflow_id) ON DELETE CASCADE,
                    UNIQUE(workflow_id, key)
                );

                CREATE TABLE IF NOT EXISTS workflow_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT,
                    FOREIGN KEY(workflow_id) REFERENCES workflows(workflow_id) ON DELETE CASCADE,
                    UNIQUE(workflow_id, key)
                );

                CREATE TABLE IF NOT EXISTS workflow_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT,
                    FOREIGN KEY(workflow_id) REFERENCES workflows(workflow_id) ON DELETE CASCADE,
                    UNIQUE(workflow_id, key)
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

                CREATE TABLE IF NOT EXISTS workflow_chains (
                    parent_id TEXT NOT NULL,
                    child_id TEXT NOT NULL,
                    PRIMARY KEY (parent_id, child_id)
                );
                """
            )

            if needs_migration:
                old_rows = connection.execute(
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
                        execution_metadata,
                        updated_at
                    FROM workflows_old
                    """
                ).fetchall()

                for row in old_rows:
                    w_id = row["workflow_id"]
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
                            updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            w_id,
                            row["project_name"],
                            row["goal"],
                            row["executor"],
                            row["scenario"],
                            row["auto_apply_fixes"],
                            row["job_id"],
                            row["calc_path"],
                            row["current_stage"],
                            row["job_status"],
                            row["agent_status"],
                            row["latest_summary"],
                            row["latest_next_step"],
                            row["updated_at"],
                        )
                    )

                    # Migrate results
                    try:
                        results = json.loads(row["latest_results"])
                        for k, v in results.items():
                            connection.execute(
                                "INSERT OR REPLACE INTO workflow_results (workflow_id, key, value) VALUES (?, ?, ?)",
                                (w_id, k, json.dumps(v))
                            )
                    except Exception:
                        pass

                    # Migrate settings
                    try:
                        settings = json.loads(row["job_settings"])
                        for k, v in settings.items():
                            connection.execute(
                                "INSERT OR REPLACE INTO workflow_settings (workflow_id, key, value) VALUES (?, ?, ?)",
                                (w_id, k, json.dumps(v))
                            )
                    except Exception:
                        pass

                    # Migrate metadata
                    try:
                        metadata = json.loads(row["execution_metadata"])
                        for k, v in metadata.items():
                            connection.execute(
                                "INSERT OR REPLACE INTO workflow_metadata (workflow_id, key, value) VALUES (?, ?, ?)",
                                (w_id, k, json.dumps(v))
                            )
                    except Exception:
                        pass

                connection.execute("DROP TABLE workflows_old")
            
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
            "executor": row["executor"],
            "scenario": row["scenario"],
            "auto_apply_fixes": bool(row["auto_apply_fixes"]),
            "job_id": row["job_id"],
            "calc_path": row["calc_path"],
            "current_stage": row["current_stage"],
            "job_status": row["job_status"],
            "agent_status": row["agent_status"],
            "latest_summary": row["latest_summary"],
            "latest_next_step": row["latest_next_step"],
            "latest_results": {},
            "job_settings": {},
            "execution_metadata": {},
            "history": [],
        }

    def add_chain_link(self, parent_id: str, child_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO workflow_chains (parent_id, child_id) VALUES (?, ?)",
                (parent_id, child_id)
            )
            connection.commit()

    def get_child_id(self, parent_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT child_id FROM workflow_chains WHERE parent_id = ?",
                (parent_id,)
            ).fetchone()
            return row["child_id"] if row else None
