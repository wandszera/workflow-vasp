from __future__ import annotations

import shutil
from pathlib import Path
import numpy as np


class PoscarCorrector:
    @staticmethod
    def fix(poscar_path: str | Path, threshold_ang: float = 0.8, target_separation_ang: float = 1.1) -> dict[str, any]:
        path = Path(poscar_path)
        if not path.exists():
            return {"success": False, "error": f"Arquivo nao encontrado: {path.name}"}

        # Backup the original file
        backup_path = path.with_suffix(".poscar.bak")
        shutil.copy2(path, backup_path)

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = [line.strip() for line in f]

            # We need to preserve spacing and lines. Let's parse structured data.
            # Remove empty lines from end/middle for easy coordinate mapping, but keep format
            clean_lines = [l for l in lines if l]

            scale = float(clean_lines[1])
            if scale < 0:
                scale = abs(scale)

            lattice = []
            for i in range(2, 5):
                lattice.append([float(x) for x in clean_lines[i].split()])
            lattice = np.array(lattice)
            if scale != 1.0:
                lattice = lattice * scale

            parts_6 = clean_lines[5].split()
            parts_7 = clean_lines[6].split()

            if all(p.isdigit() for p in parts_6):
                counts = [int(p) for p in parts_6]
                line_offset = 7
            else:
                counts = [int(p) for p in parts_7]
                line_offset = 7

            total_atoms = sum(counts)

            is_selective = False
            if clean_lines[line_offset].lower().startswith("s"):
                is_selective = True
                line_offset += 1

            coord_type_str = clean_lines[line_offset].lower()
            is_direct = coord_type_str.startswith("d") or coord_type_str.startswith("f")
            line_offset += 1

            coords = []
            flags = [] # Selective dynamics flags if present
            for idx in range(line_offset, line_offset + total_atoms):
                parts = clean_lines[idx].split()
                coords.append([float(parts[0]), float(parts[1]), float(parts[2])])
                if len(parts) >= 6 and is_selective:
                    flags.append(parts[3:6])
                else:
                    flags.append(None)

            coords = np.array(coords)
            inv_lattice = np.linalg.inv(lattice)

            # Convert to Direct if Cartesian
            if not is_direct:
                coords = np.dot(coords, inv_lattice)

            # Wrap coordinates
            coords = coords % 1.0

            # Iterative relaxation of colliding pairs
            max_iterations = 20
            fixed_any = False
            
            for iteration in range(max_iterations):
                collisions_resolved_this_step = 0
                for i in range(total_atoms):
                    for j in range(i + 1, total_atoms):
                        diff = coords[i] - coords[j]
                        # PBC
                        diff = diff - np.round(diff)
                        # Cartesian diff
                        cart_diff = np.dot(diff, lattice)
                        dist = np.linalg.norm(cart_diff)

                        if dist < threshold_ang:
                            fixed_any = True
                            collisions_resolved_this_step += 1
                            if dist < 1e-5:
                                # Atoms exactly on top of each other. Shift along a random direction.
                                cart_shift_direction = np.random.randn(3)
                                cart_shift_direction /= np.linalg.norm(cart_shift_direction)
                                shift_dist = target_separation_ang
                            else:
                                cart_shift_direction = cart_diff / dist
                                shift_dist = target_separation_ang - dist

                            # Symmetric shift
                            shift_i = cart_shift_direction * (shift_dist / 2.0)
                            shift_j = -cart_shift_direction * (shift_dist / 2.0)

                            # Convert shift back to direct space
                            dir_shift_i = np.dot(shift_i, inv_lattice)
                            dir_shift_j = np.dot(shift_j, inv_lattice)

                            # Apply shift
                            coords[i] = (coords[i] + dir_shift_i) % 1.0
                            coords[j] = (coords[j] + dir_shift_j) % 1.0

                if collisions_resolved_this_step == 0:
                    break

            # Convert back to Cartesian if original was Cartesian
            if not is_direct:
                coords = np.dot(coords, lattice)

            # Re-write the POSCAR file
            output_lines = []
            # Copy header lines (up to coordinate type)
            output_lines.extend(clean_lines[:line_offset])

            # Write coordinates with flags
            for i in range(total_atoms):
                c = coords[i]
                c_str = f"  {c[0]:.16f}   {c[1]:.16f}   {c[2]:.16f}"
                if flags[i] is not None and is_selective:
                    c_str += f"   {'   '.join(flags[i])}"
                output_lines.append(c_str)

            # Copy any trailing lines (like velocities)
            trailing_start = line_offset + total_atoms
            if trailing_start < len(clean_lines):
                output_lines.extend(clean_lines[trailing_start:])

            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(output_lines) + "\n")

            return {
                "success": True,
                "fixed": fixed_any,
                "backup": backup_path.name
            }

        except Exception as e:
            # Restore backup in case of failures
            if backup_path.exists():
                shutil.copy2(backup_path, path)
            return {"success": False, "error": f"Erro ao corrigir POSCAR: {str(e)}"}
