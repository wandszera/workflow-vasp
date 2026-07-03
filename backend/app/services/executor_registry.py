from __future__ import annotations

from .mlff_training_executor import MlffTrainingExecutor
from .mock_cluster import MockClusterService
from .ssh_slurm_executor import SshSlurmExecutor


class ExecutorRegistry:
    def __init__(
        self,
        mock_executor: MockClusterService | None = None,
        ssh_slurm_executor: SshSlurmExecutor | None = None,
        mlff_training_executor: MlffTrainingExecutor | None = None,
    ) -> None:
        self.executors = {
            "mock": mock_executor or MockClusterService(),
            "ssh_slurm": ssh_slurm_executor or SshSlurmExecutor(),
            "mlff_training": mlff_training_executor or MlffTrainingExecutor(),
        }

    def get(self, executor_name: str):
        if executor_name not in self.executors:
            raise FileNotFoundError(f"Executor nao encontrado: {executor_name}")
        return self.executors[executor_name]
