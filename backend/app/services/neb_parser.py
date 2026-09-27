from __future__ import annotations

from pathlib import Path
import re


class NebParser:
    @staticmethod
    def get_neb_data(calc_path: str | Path) -> dict[str, any] | None:
        root = Path(calc_path).expanduser().resolve()
        if not root.exists():
            return None

        # Look for two-digit or single-digit subdirectories (e.g., '00', '01', etc.)
        image_dirs = []
        for p in root.iterdir():
            if p.is_dir() and p.name.isdigit():
                image_dirs.append(p)

        if not image_dirs:
            return None

        # Sort folders numerically
        image_dirs.sort(key=lambda x: int(x.name))

        images = []
        energies = []
        
        # Helper to parse energy from OUTCAR or OSZICAR
        for d in image_dirs:
            outcar = d / "OUTCAR"
            oszicar = d / "OSZICAR"
            energy = None

            if outcar.exists():
                try:
                    # Find last occurrence of free energy in OUTCAR
                    with open(outcar, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            if "free  energy   TOTEN" in line:
                                parts = line.strip().split()
                                energy = float(parts[4])
                except Exception:
                    pass

            if energy is None and oszicar.exists():
                try:
                    # Find last F= in OSZICAR
                    with open(oszicar, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            if "F=" in line:
                                match = re.search(r"F\s*=\s*([-\d.]+)", line)
                                if match:
                                    energy = float(match.group(1))
                except Exception:
                    pass

            if energy is not None:
                images.append(d.name)
                energies.append(energy)

        if not energies:
            return None

        # Compute relative energy (eV) relative to initial image (index 0)
        base_energy = energies[0]
        relative_energies = [round(e - base_energy, 4) for e in energies]

        return {
            "images": images,
            "energies": energies,
            "relative_energies": relative_energies,
            "activation_energy": round(max(relative_energies) - relative_energies[0], 4)
        }
