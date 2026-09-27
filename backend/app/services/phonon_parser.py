from __future__ import annotations

from pathlib import Path
import re


class PhononParser:
    @staticmethod
    def get_phonon_data(calc_path: str | Path) -> dict[str, any] | None:
        root = Path(calc_path).expanduser().resolve()
        yaml_path = root / "thermal_properties.yaml"
        if not yaml_path.exists():
            return None

        temperatures = []
        free_energies = []
        entropies = []
        heat_capacities = []

        # Simple, robust YAML line parser
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                current_temp = None
                current_fe = None
                current_entropy = None
                current_cv = None

                for line in f:
                    stripped = line.strip()
                    if stripped.startswith("- temp:"):
                        # If we have collected a full set, save it
                        if current_temp is not None:
                            temperatures.append(current_temp)
                            free_energies.append(current_fe if current_fe is not None else 0.0)
                            entropies.append(current_entropy if current_entropy is not None else 0.0)
                            heat_capacities.append(current_cv if current_cv is not None else 0.0)

                        current_temp = float(stripped.split(":")[1].strip())
                        current_fe = None
                        current_entropy = None
                        current_cv = None
                    elif stripped.startswith("free_energy:"):
                        current_fe = float(stripped.split(":")[1].strip())
                    elif stripped.startswith("entropy:"):
                        current_entropy = float(stripped.split(":")[1].strip())
                    elif stripped.startswith("heat_capacity:"):
                        current_cv = float(stripped.split(":")[1].strip())

                # Append last block
                if current_temp is not None:
                    temperatures.append(current_temp)
                    free_energies.append(current_fe if current_fe is not None else 0.0)
                    entropies.append(current_entropy if current_entropy is not None else 0.0)
                    heat_capacities.append(current_cv if current_cv is not None else 0.0)

        except Exception:
            return None

        if not temperatures:
            return None

        return {
            "temperatures": temperatures,
            "free_energy": free_energies,
            "entropy": entropies,
            "heat_capacity": heat_capacities
        }
