from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ExecutionJob:
    job_id: str
    calc_path: str
    scenario: str
    stage: int
    status: str
    message: str
    metadata: dict[str, str | float | int | bool | None | list[str]]


class WorkflowExecutor(Protocol):
    executor_name: str

    def create_job(
        self,
        project_name: str,
        scenario: str,
        goal: str | None = None,
        job_settings: dict[str, object] | None = None,
    ) -> ExecutionJob:
        ...

    def advance_job(self, job_id: str) -> ExecutionJob:
        ...
