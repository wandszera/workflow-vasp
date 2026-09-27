from __future__ import annotations

import math
from pathlib import Path
import numpy as np


class PoscarValidator:
    @staticmethod
    def validate(poscar_path: str | Path, threshold_ang: float = 0.8) -> dict[str, any]:
        path = Path(poscar_path)
        if not path.exists():
            return {
                "valid": False,
                "min_distance_ang": 0.0,
                "colliding_pairs": [],
                "errors": [f"Arquivo nao encontrado: {path.name}"]
            }

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = [line.strip() for line in f if line.strip()]

            if len(lines) < 8:
                return {
                    "valid": False,
                    "min_distance_ang": 0.0,
                    "colliding_pairs": [],
                    "errors": ["Arquivo POSCAR truncado ou malformatado."]
                }

            # Line 1: Comment (ignored)
            # Line 2: Scale factor
            scale = float(lines[1])
            if scale < 0:
                # Negative scale factor means target volume, not scaling.
                # In most typical structures, we can treat the absolute value as volume scale,
                # but to be simple and robust, we assume absolute scale.
                scale = abs(scale)

            # Lines 3-5: Lattice vectors
            lattice = []
            for i in range(2, 5):
                parts = [float(x) for x in lines[i].split()]
                if len(parts) != 3:
                    return {
                        "valid": False,
                        "min_distance_ang": 0.0,
                        "colliding_pairs": [],
                        "errors": [f"Vetor de rede invalido na linha {i+1}."]
                    }
                lattice.append(parts)
            
            lattice = np.array(lattice)
            if scale != 1.0:
                lattice = lattice * scale

            # Line 6 & 7: Elements and Counts
            parts_6 = lines[5].split()
            parts_7 = lines[6].split()

            # VASP 5 has element symbols on Line 6 and counts on Line 7
            # VASP 4 has counts on Line 6
            if all(p.isdigit() for p in parts_6):
                counts = [int(p) for p in parts_6]
                line_offset = 7
            else:
                counts = [int(p) for p in parts_7]
                line_offset = 7
                if all(p.isdigit() for p in parts_7):
                    line_offset = 7
                else:
                    return {
                        "valid": False,
                        "min_distance_ang": 0.0,
                        "colliding_pairs": [],
                        "errors": ["Nao foi possivel extrair o numero de atomos do POSCAR."]
                    }

            total_atoms = sum(counts)

            # Check for Selective Dynamics
            is_selective = False
            if lines[line_offset].lower().startswith("s"):
                is_selective = True
                line_offset += 1

            # Coordinate type (Direct/Fractional vs Cartesian)
            coord_type_str = lines[line_offset].lower()
            is_direct = coord_type_str.startswith("d") or coord_type_str.startswith("f")
            line_offset += 1

            # Parse coordinates
            coords = []
            for idx in range(line_offset, line_offset + total_atoms):
                if idx >= len(lines):
                    return {
                        "valid": False,
                        "min_distance_ang": 0.0,
                        "colliding_pairs": [],
                        "errors": [f"Faltam coordenadas para o atomo {idx - line_offset + 1}."]
                    }
                parts = lines[idx].split()
                # Coords are the first 3 elements
                coords.append([float(parts[0]), float(parts[1]), float(parts[2])])

            coords = np.array(coords)
            inv_lattice = np.linalg.inv(lattice)

            # Convert to Fractional if Cartesian
            if not is_direct:
                # Cartesian coordinates to fractional: multiply by inverse of lattice
                try:
                    coords = np.dot(coords, inv_lattice)
                except np.linalg.LinAlgError:
                    return {
                        "valid": False,
                        "min_distance_ang": 0.0,
                        "colliding_pairs": [],
                        "lattice_lengths": (0.0, 0.0, 0.0),
                        "lattice_angles": (0.0, 0.0, 0.0),
                        "crystal_system": "Desconhecido",
                        "vacuum_thickness_ang": 0.0,
                        "errors": ["Matriz de rede singular. Nao e possivel inverter."]
                    }

            # Wrap fractional coordinates inside [0, 1)
            coords = coords % 1.0

            # Calculate lattice parameters
            v1, v2, v3 = lattice[0], lattice[1], lattice[2]
            a_len = float(np.linalg.norm(v1))
            b_len = float(np.linalg.norm(v2))
            c_len = float(np.linalg.norm(v3))
            
            alpha = float(np.arccos(np.dot(v2, v3) / (b_len * c_len))) * 180.0 / np.pi if b_len * c_len > 0 else 0.0
            beta = float(np.arccos(np.dot(v3, v1) / (c_len * a_len))) * 180.0 / np.pi if c_len * a_len > 0 else 0.0
            gamma = float(np.arccos(np.dot(v1, v2) / (a_len * b_len))) * 180.0 / np.pi if a_len * b_len > 0 else 0.0

            # Crystal system classification
            crystal_system = "Triclinico"
            tol_len = 0.05
            tol_ang = 0.5
            
            eq_ab = abs(a_len - b_len) < tol_len
            eq_bc = abs(b_len - c_len) < tol_len
            
            ang_90 = lambda x: abs(x - 90.0) < tol_ang
            ang_120 = lambda x: abs(x - 120.0) < tol_ang
            
            if eq_ab and eq_bc and ang_90(alpha) and ang_90(beta) and ang_90(gamma):
                crystal_system = "Cubico"
            elif eq_ab and ang_90(alpha) and ang_90(beta) and ang_90(gamma):
                crystal_system = "Tetragonal"
            elif ang_90(alpha) and ang_90(beta) and ang_90(gamma):
                crystal_system = "Ortorrombico"
            elif eq_ab and ang_90(alpha) and ang_90(beta) and ang_120(gamma):
                crystal_system = "Hexagonal"
            elif ang_90(alpha) and ang_90(gamma) and not ang_90(beta):
                crystal_system = "Monoclinico"
            elif abs(alpha - beta) < tol_ang and abs(beta - gamma) < tol_ang and eq_ab and eq_bc:
                crystal_system = "Trigonal/Romboedrico"

            # Vacuum thickness in Z direction
            z_coords = coords[:, 2]
            z_sorted = np.sort(z_coords)
            
            if len(z_sorted) > 1:
                gaps = np.diff(z_sorted)
                p_gap = 1.0 - z_sorted[-1] + z_sorted[0]
                max_gap_direct = float(max(np.max(gaps), p_gap))
            else:
                max_gap_direct = 1.0
            
            vacuum_thickness_ang = max_gap_direct * abs(v3[2])

            # Compute pairwise distances under PBC
            min_dist = float("inf")
            colliding = []

            for i in range(total_atoms):
                for j in range(i + 1, total_atoms):
                    # Difference vector in fractional space
                    diff = coords[i] - coords[j]
                    
                    # Periodic Boundary Conditions: shift to range [-0.5, 0.5]
                    diff = diff - np.round(diff)

                    # Convert to Cartesian space
                    cart_diff = np.dot(diff, lattice)

                    # Compute Euclidean distance
                    dist = float(np.linalg.norm(cart_diff))

                    if dist < min_dist:
                        min_dist = dist

                    if dist < threshold_ang:
                        colliding.append((i, j, round(dist, 4)))

            errors = []
            if colliding:
                errors.append(
                    f"Colisao atômica física detectada! {len(colliding)} pares de atomos a menos de {threshold_ang} A."
                )

            return {
                "valid": len(colliding) == 0,
                "min_distance_ang": round(min_dist, 5) if min_dist != float("inf") else 0.0,
                "colliding_pairs": colliding,
                "lattice_lengths": (round(a_len, 4), round(b_len, 4), round(c_len, 4)),
                "lattice_angles": (round(alpha, 2), round(beta, 2), round(gamma, 2)),
                "crystal_system": crystal_system,
                "vacuum_thickness_ang": round(vacuum_thickness_ang, 4),
                "errors": errors
            }

        except Exception as e:
            return {
                "valid": False,
                "min_distance_ang": 0.0,
                "colliding_pairs": [],
                "lattice_lengths": (0.0, 0.0, 0.0),
                "lattice_angles": (0.0, 0.0, 0.0),
                "crystal_system": "Desconhecido",
                "vacuum_thickness_ang": 0.0,
                "errors": [f"Falha de processamento de POSCAR: {str(e)}"]
            }
