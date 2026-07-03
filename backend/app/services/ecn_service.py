from __future__ import annotations

from math import exp, sqrt
from pathlib import Path


class EcnService:
    def compute_from_poscar(self, poscar_path: str | Path) -> dict[str, object]:
        lattice, cartesian_positions, species_labels, counts = self._read_poscar(Path(poscar_path))
        nscell = len(cartesian_positions)
        if nscell == 0:
            raise ValueError("POSCAR sem coordenadas atomicas para calcular ECN.")

        large_positions: list[tuple[float, float, float]] = []
        large_symbols: list[int] = []
        for i1 in range(-2, 3):
            for j1 in range(-2, 3):
                for k1 in range(-2, 3):
                    shift = self._cartesian_from_fractional((i1, j1, k1), lattice)
                    for index, position in enumerate(cartesian_positions, start=1):
                        large_positions.append(
                            (
                                position[0] + shift[0],
                                position[1] + shift[1],
                                position[2] + shift[2],
                            )
                        )
                        large_symbols.append(index)

        distances: list[list[float]] = []
        for source in cartesian_positions:
            row: list[float] = []
            for target in large_positions:
                row.append(
                    sqrt(
                        (source[0] - target[0]) ** 2
                        + (source[1] - target[1]) ** 2
                        + (source[2] - target[2]) ** 2
                    )
                )
            distances.append(row)

        rmin = []
        nearest_neighbors: list[int] = []
        for row in distances:
            candidates = [(distance, idx) for idx, distance in enumerate(row) if distance >= 1.0]
            if not candidates:
                raise ValueError("Nao foi possivel determinar o menor comprimento de ligacao para um dos atomos.")
            distance, idx = min(candidates, key=lambda item: item[0])
            rmin.append(distance)
            nearest_neighbors.append(large_symbols[idx])

        rwabl = self._solve_rwabl(distances, rmin)

        ecn_by_atom = []
        for atom_index, row in enumerate(distances):
            total = 0.0
            for distance in row:
                weight = exp(1.0 - (distance / rwabl[atom_index]) ** 6)
                if weight <= 1.0e-3:
                    weight = 0.0
                total += weight
            total -= exp(1.0)
            ecn_by_atom.append(round(total, 6))

        average_ecn = round(sum(ecn_by_atom) / nscell, 6)
        total_ecn = round(sum(ecn_by_atom), 6)
        weighted_average_bond_length = round(sum(rwabl) / nscell, 6)

        return {
            "n_atoms": nscell,
            "species_labels": species_labels,
            "species_counts": counts,
            "nearest_neighbors": nearest_neighbors,
            "rmin_by_atom": [round(value, 6) for value in rmin],
            "rwabl_by_atom": [round(value, 6) for value in rwabl],
            "ecn_by_atom": ecn_by_atom,
            "average_ecn": average_ecn,
            "total_ecn": total_ecn,
            "weighted_average_bond_length": weighted_average_bond_length,
            "supercell_atom_count": len(large_positions),
        }

    def _solve_rwabl(self, distances: list[list[float]], rmin: list[float]) -> list[float]:
        current = [float(value) for value in rmin]
        for _ in range(200):
            rwabl: list[float] = []
            for atom_index, row in enumerate(distances):
                sum1 = 0.0
                sum2 = 0.0
                for distance in row:
                    weight = exp(1.0 - (distance / current[atom_index]) ** 6)
                    if weight <= 1.0e-3:
                        weight = 0.0
                    sum1 += distance * weight
                    sum2 += weight
                sum2 -= exp(1.0)
                if sum2 == 0.0:
                    raise ValueError("Falha ao obter Awabl: denominador nulo.")
                rwabl.append(sum1 / sum2)
            if all(abs(rwabl[index] - current[index]) < 1.0e-4 for index in range(len(current))):
                return rwabl
            current = rwabl
        raise ValueError("Processo autoconsistente do ECN nao convergiu em 200 iteracoes.")

    def _read_poscar(
        self,
        path: Path,
    ) -> tuple[
        list[tuple[float, float, float]],
        list[tuple[float, float, float]],
        list[str],
        list[int],
    ]:
        if not path.exists():
            raise FileNotFoundError(f"POSCAR nao encontrado: {path}")

        lines = [line.rstrip() for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
        if len(lines) < 8:
            raise ValueError("POSCAR incompleto para calcular ECN.")

        scale = float(lines[1].split()[0])
        lattice = []
        for offset in range(2, 5):
            vector = tuple(float(value) * scale for value in lines[offset].split()[:3])
            lattice.append(vector)

        species_line = lines[5].split()
        counts_line_index = 6
        species_labels: list[str]
        if not all(self._is_int(token) for token in species_line):
            species_labels = species_line
            counts_line_index = 6
            counts_tokens = lines[counts_line_index].split()
        else:
            species_labels = [f"species_{index + 1}" for index in range(len(species_line))]
            counts_line_index = 5
            counts_tokens = species_line
        counts = [int(token) for token in counts_tokens]
        total_atoms = sum(counts)

        coord_mode_index = counts_line_index + 1
        selective = lines[coord_mode_index].lower().startswith("s")
        if selective:
            coord_mode_index += 1
        coordinate_mode = lines[coord_mode_index].strip().lower()
        start = coord_mode_index + 1
        coordinate_lines = lines[start:start + total_atoms]
        if len(coordinate_lines) != total_atoms:
            raise ValueError("Numero de coordenadas no POSCAR nao bate com o numero de atomos.")

        positions = []
        for line in coordinate_lines:
            coords = tuple(float(value) for value in line.split()[:3])
            if coordinate_mode.startswith("d"):
                positions.append(self._cartesian_from_fractional(coords, lattice))
            else:
                positions.append(coords)
        return lattice, positions, species_labels, counts

    @staticmethod
    def _cartesian_from_fractional(
        coords: tuple[float, float, float],
        lattice: list[tuple[float, float, float]],
    ) -> tuple[float, float, float]:
        x, y, z = coords
        a1, a2, a3 = lattice
        return (
            x * a1[0] + y * a2[0] + z * a3[0],
            x * a1[1] + y * a2[1] + z * a3[1],
            x * a1[2] + y * a2[2] + z * a3[2],
        )

    @staticmethod
    def _is_int(token: str) -> bool:
        try:
            int(token)
        except ValueError:
            return False
        return True
