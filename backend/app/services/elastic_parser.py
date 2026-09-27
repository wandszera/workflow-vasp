from __future__ import annotations

from pathlib import Path
import re


class ElasticParser:
    @staticmethod
    def get_elastic_data(calc_path: str | Path) -> dict[str, any] | None:
        root = Path(calc_path).expanduser().resolve()
        outcar_path = root / "OUTCAR"
        if not outcar_path.exists():
            return None

        # Look for the elastic stiffness tensor block in OUTCAR
        # VASP outputs: "TOTAL ELASTIC STIFFNESS TENSOR (kBar)"
        tensor_found = False
        matrix_lines = []

        try:
            with open(outcar_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            for idx, line in enumerate(lines):
                if "TOTAL ELASTIC STIFFNESS TENSOR" in line:
                    tensor_found = True
                    # Skip header lines (Direction, dashed line)
                    start_idx = idx + 3
                    for offset in range(6):
                        matrix_lines.append(lines[start_idx + offset].strip())
                    break

        except Exception:
            return None

        if not tensor_found or len(matrix_lines) < 6:
            return None

        # Parse 6x6 matrix
        C = []
        try:
            for line in matrix_lines:
                # Line example: "XX        1234.5678    123.4567    123.4567      0.0000      0.0000      0.0000"
                parts = line.split()
                # Elements are in parts[1:7]
                row = [float(x) for x in parts[1:7]]
                C.append(row)
        except Exception:
            return None

        if len(C) != 6 or any(len(row) != 6 for row in C):
            return None

        # Convert kBar to GPa (1 GPa = 10 kBar)
        C_gpa = [[round(val / 10.0, 2) for val in row] for row in C]

        # Calculate Voigt mechanical moduli (using GPa values)
        # C_gpa index mapping (0-based):
        # 0: XX (11), 1: YY (22), 2: ZZ (33), 3: XY (44), 4: YZ (55), 5: ZX (66)
        # Note: Voigt indices for shear C44, C55, C66 are C[3][3], C[4][4], C[5][5]
        c11 = C_gpa[0][0]
        c22 = C_gpa[1][1]
        c33 = C_gpa[2][2]
        
        c12 = C_gpa[0][1]
        c23 = C_gpa[1][2]
        c13 = C_gpa[0][2]

        c44 = C_gpa[3][3]
        c55 = C_gpa[4][4]
        c66 = C_gpa[5][5]

        # Voigt Bulk Modulus (B)
        B = ((c11 + c22 + c33) + 2.0 * (c12 + c23 + c13)) / 9.0

        # Voigt Shear Modulus (G)
        G = ((c11 + c22 + c33) - (c12 + c23 + c13) + 3.0 * (c44 + c55 + c66)) / 15.0

        # Young's Modulus (E)
        if (3.0 * B + G) > 0:
            E = (9.0 * B * G) / (3.0 * B + G)
            nu = (3.0 * B - 2.0 * G) / (2.0 * (3.0 * B + G))
        else:
            E = 0.0
            nu = 0.0

        return {
            "matrix": C_gpa,
            "bulk_modulus": round(B, 2),
            "shear_modulus": round(G, 2),
            "young_modulus": round(E, 2),
            "poisson_ratio": round(nu, 3)
        }
