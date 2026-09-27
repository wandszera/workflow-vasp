from __future__ import annotations

from pathlib import Path
import re


class PotcarValidator:
    @staticmethod
    def parse_potcar(potcar_path: str | Path) -> dict[str, any]:
        path = Path(potcar_path)
        if not path.exists():
            return {
                "elements": [],
                "enmax_list": [],
                "max_enmax": 0.0
            }

        elements = []
        enmax_list = []
        
        # Regex patterns
        vrhfin_pattern = re.compile(r"^\s*VRHFIN\s*=\s*([A-Za-z]+)\s*:")
        enmax_pattern = re.compile(r"^\s*ENMAX\s*=\s*([0-9.]+)")

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                vrh_match = vrhfin_pattern.search(line)
                if vrh_match:
                    elements.append(vrh_match.group(1).strip())
                
                enmax_match = enmax_pattern.search(line)
                if enmax_match:
                    enmax_list.append(float(enmax_match.group(1)))

        max_enmax = max(enmax_list) if enmax_list else 0.0

        return {
            "elements": elements,
            "enmax_list": enmax_list,
            "max_enmax": max_enmax
        }

    @staticmethod
    def validate(potcar_path: str | Path, poscar_path: str | Path, incar_tags: dict[str, str] = None) -> dict[str, any]:
        path = Path(potcar_path)
        pos_path = Path(poscar_path)

        if not path.exists():
            return {
                "valid": False,
                "warnings": ["Arquivo POTCAR nao encontrado."],
                "details": {
                    "elements": [],
                    "max_enmax": 0.0
                }
            }

        if not pos_path.exists():
            return {
                "valid": False,
                "warnings": ["Arquivo POSCAR nao encontrado para cruzar dados do POTCAR."],
                "details": {
                    "elements": [],
                    "max_enmax": 0.0
                }
            }

        # Parse POTCAR data
        pot_data = PotcarValidator.parse_potcar(path)
        pot_elements = pot_data["elements"]
        max_enmax = pot_data["max_enmax"]

        # Parse POSCAR elements
        pos_elements = []
        try:
            with open(pos_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
            if len(lines) >= 6:
                parts_6 = lines[5].split()
                # If parts_6 are digits (old VASP without elements line), POSCAR elements are unknown directly
                if not all(p.isdigit() for p in parts_6):
                    pos_elements = parts_6
        except Exception:
            pass

        warnings = []
        critical = False

        if pos_elements:
            # Check element matching
            if len(pos_elements) != len(pot_elements):
                warnings.append(
                    f"CRITICO: Numero de pseudopotenciais no POTCAR ({len(pot_elements)}) "
                    f"e diferente do numero de elementos no POSCAR ({len(pos_elements)})."
                )
                critical = True
            else:
                for idx, (pos_el, pot_el) in enumerate(zip(pos_elements, pot_elements)):
                    if pos_el.upper() != pot_el.upper():
                        warnings.append(
                            f"CRITICO: Divergencia de sequencia na posicao {idx+1}. "
                            f"POSCAR espera '{pos_el}', mas POTCAR possui '{pot_el}'. "
                            "Isso causara erros fisicos serios no VASP sem travar a execucao!"
                        )
                        critical = True

        # Check ENCUT vs ENMAX
        suggested_encut = round(1.3 * max_enmax) if max_enmax > 0 else 0
        if incar_tags and max_enmax > 0:
            encut_str = incar_tags.get("ENCUT")
            if encut_str:
                try:
                    encut = float(encut_str)
                    if encut < max_enmax:
                        warnings.append(
                            f"ENCUT do INCAR ({encut} eV) e menor que a energia maxima do POTCAR ({max_enmax} eV). "
                            f"Perigo de nao-convergencia. Sugerido ENCUT >= {suggested_encut} eV."
                        )
                    elif encut < 1.3 * max_enmax:
                        warnings.append(
                            f"ENCUT do INCAR ({encut} eV) esta proximo do limite. "
                            f"Para calculos precisos, sugere-se ENCUT >= {suggested_encut} eV (1.3 * ENMAX)."
                        )
                except ValueError:
                    pass
            else:
                warnings.append(
                    f"Tag 'ENCUT' nao especificada no INCAR. "
                    f"VASP usara o default do POTCAR. Para segurança, recomenda-se explicitar ENCUT = {suggested_encut} eV."
                )

        return {
            "valid": len(warnings) == 0,
            "critical": critical,
            "warnings": warnings,
            "details": {
                "potcar_elements": pot_elements,
                "poscar_elements": pos_elements,
                "max_enmax": max_enmax,
                "suggested_encut": suggested_encut
            }
        }
