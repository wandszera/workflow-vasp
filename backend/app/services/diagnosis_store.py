from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DiagnosisStore:
    def __init__(self, db_path: Path | None = None) -> None:
        default_path = Path(__file__).resolve().parent.parent / "data" / "diagnoses.db"
        self.db_path = db_path or default_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS diagnoses (
                        diagnosis_id TEXT PRIMARY KEY,
                        payload_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = self.now()
        payload = dict(payload)
        payload.setdefault("created_at", now)
        payload["updated_at"] = now
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO diagnoses (diagnosis_id, payload_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(diagnosis_id) DO UPDATE SET
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at
                    """,
                    (payload["diagnosis_id"], json.dumps(payload, ensure_ascii=False), payload["created_at"], now),
                )
        return payload

    def get(self, diagnosis_id: str) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT payload_json FROM diagnoses WHERE diagnosis_id = ?", (diagnosis_id,)
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Diagnostico nao encontrado: {diagnosis_id}")
        return json.loads(row["payload_json"])

    def decide(self, diagnosis_id: str, approved: bool, note: str | None) -> dict[str, Any]:
        payload = self.get(diagnosis_id)
        if payload["status"] == "insufficient_evidence" and approved:
            raise ValueError("Diagnosticos sem evidencia suficiente nao podem ser aprovados.")
        payload["status"] = "approved" if approved else "rejected"
        payload["human_decision"] = payload["status"]
        payload["human_note"] = note
        payload["graph_trace"] = [*payload.get("graph_trace", []), "registrar_feedback"]
        return self.save(payload)

