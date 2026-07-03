from __future__ import annotations

import json
import re
from pathlib import Path


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def parse_incar(path: Path) -> dict[str, str]:
    content = read_text_if_exists(path)
    params: dict[str, str] = {}
    for line in content.splitlines():
        clean_line = line.split("!", maxsplit=1)[0].strip()
        if not clean_line or "=" not in clean_line:
            continue
        key, value = clean_line.split("=", maxsplit=1)
        params[key.strip().upper()] = value.strip()
    return params


def parse_outcar(path: Path) -> dict[str, object]:
    content = read_text_if_exists(path)
    lower_content = content.lower()

    energy_match = re.findall(r"free\s+energy\s+toten\s*=\s*([-0-9.]+)", content, flags=re.IGNORECASE)
    magnetization_match = re.search(
        r"number of electron\s+[-0-9.]+\s+magnetization\s*=\s*([-0-9.]+)",
        content,
        flags=re.IGNORECASE,
    )

    return {
        "exists": path.exists(),
        "raw_text": content,
        "converged": "reached required accuracy" in lower_content,
        "electronic_converged": "aborting loop because ediff is reached" in lower_content,
        "ionic_steps": lower_content.count("free  energy   toten"),
        "final_energy_ev": float(energy_match[-1]) if energy_match else None,
        "magnetization": float(magnetization_match.group(1)) if magnetization_match else None,
    }


def parse_oszicar(path: Path) -> dict[str, object]:
    content = read_text_if_exists(path)
    final_f_match = re.findall(r"F=\s*([-0-9.]+)", content)
    return {
        "exists": path.exists(),
        "raw_text": content,
        "final_free_energy_ev": float(final_f_match[-1]) if final_f_match else None,
    }


def parse_ml_log(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "exists": False,
            "raw_text": "",
            "status": None,
            "mode": None,
            "stage_name": None,
            "dataset_source": None,
            "reference_count": None,
            "completed_batches": None,
            "train_rmse": None,
            "test_rmse": None,
            "target_rmse": None,
            "min_reference_count": None,
            "ready_for_production": False,
        }

    raw_text = read_text_if_exists(path)
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        payload = {}

    return {
        "exists": True,
        "raw_text": raw_text,
        "status": payload.get("status"),
        "mode": payload.get("mode"),
        "stage_name": payload.get("stage_name"),
        "dataset_source": payload.get("dataset_source"),
        "reference_count": payload.get("reference_count"),
        "completed_batches": payload.get("completed_batches"),
        "train_rmse": payload.get("train_rmse"),
        "test_rmse": payload.get("test_rmse"),
        "target_rmse": payload.get("target_rmse"),
        "min_reference_count": payload.get("min_reference_count"),
        "ready_for_production": bool(payload.get("ready_for_production")),
    }


def parse_outcar_eigenvalues(content: str) -> dict[str, float | int | None]:
    # Find E-fermi
    fermi_match = re.search(r"E-fermi\s*:\s*([-0-9.]+)", content, flags=re.IGNORECASE)
    e_fermi = float(fermi_match.group(1)) if fermi_match else None

    # Parse bands
    kpoints = []
    current_kpoint = None
    lines = content.splitlines()
    in_bands = False

    for line in lines:
        if "k-point" in line:
            k_match = re.search(
                r"k-point\s+(\d+)\s*:\s*([-0-9.]+)\s+([-0-9.]+)\s+([-0-9.]+)",
                line,
                flags=re.IGNORECASE,
            )
            if k_match:
                current_kpoint = {
                    "index": int(k_match.group(1)),
                    "coords": (
                        float(k_match.group(2)),
                        float(k_match.group(3)),
                        float(k_match.group(4)),
                    ),
                    "bands": [],
                }
                kpoints.append(current_kpoint)
                in_bands = False
        elif "band No." in line:
            in_bands = True
        elif in_bands:
            parts = line.split()
            if len(parts) >= 3 and parts[0].isdigit():
                try:
                    band_idx = int(parts[0])
                    energy = float(parts[1])
                    occ = float(parts[2])
                    if current_kpoint:
                        current_kpoint["bands"].append(
                            {"index": band_idx, "energy": energy, "occupation": occ}
                        )
                except ValueError:
                    in_bands = False
            else:
                in_bands = False

    vbm = -999.0
    cbm = 999.0
    has_bands = False

    for kp in kpoints:
        for b in kp["bands"]:
            has_bands = True
            energy = b["energy"]
            occ = b["occupation"]
            if occ > 0.01:
                if energy > vbm:
                    vbm = energy
            else:
                if energy < cbm:
                    cbm = energy

    band_gap = 0.0
    if has_bands:
        if cbm > vbm:
            band_gap = round(cbm - vbm, 6)
        else:
            band_gap = 0.0

    return {
        "e_fermi": e_fermi,
        "vbm": vbm if vbm != -999.0 else None,
        "cbm": cbm if cbm != 999.0 else None,
        "band_gap": band_gap if has_bands else None,
        "kpoint_count": len(kpoints),
    }

