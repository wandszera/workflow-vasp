from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ClusterConfig:
    ssh_host: str = "cluster.example.org"
    ssh_user: str = "researcher"
    remote_base_dir: str = "/scratch/vasp-workflows"
    dry_run: bool = True
    identity_file: str | None = None

    @property
    def ssh_target(self) -> str:
        return f"{self.ssh_user}@{self.ssh_host}"


def load_cluster_config(config_path: Path | None = None) -> ClusterConfig:
    app_root = Path(__file__).resolve().parent.parent
    path = config_path or app_root / "data" / "cluster_config.json"
    if not path.exists():
        return ClusterConfig()

    payload = json.loads(path.read_text(encoding="utf-8"))
    return ClusterConfig(
        ssh_host=str(payload.get("ssh_host", "cluster.example.org")),
        ssh_user=str(payload.get("ssh_user", "researcher")),
        remote_base_dir=str(payload.get("remote_base_dir", "/scratch/vasp-workflows")),
        dry_run=bool(payload.get("dry_run", True)),
        identity_file=str(payload["identity_file"]) if payload.get("identity_file") else None,
    )


def save_cluster_config(config: ClusterConfig, config_path: Path | None = None) -> ClusterConfig:
    app_root = Path(__file__).resolve().parent.parent
    path = config_path or app_root / "data" / "cluster_config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ssh_host": config.ssh_host,
        "ssh_user": config.ssh_user,
        "remote_base_dir": config.remote_base_dir,
        "dry_run": config.dry_run,
        "identity_file": config.identity_file,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return config
