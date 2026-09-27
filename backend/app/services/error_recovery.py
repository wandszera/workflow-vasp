from __future__ import annotations

from pathlib import Path
from .incar_validator import IncarValidator


class ErrorRecoveryService:
    @staticmethod
    def detect_and_fix_errors(calc_path: str | Path) -> dict[str, any]:
        root = Path(calc_path).expanduser().resolve()
        outcar = root / "OUTCAR"
        incar = root / "INCAR"

        if not outcar.exists() or not incar.exists():
            return {
                "error_detected": False,
                "error_type": None,
                "fix_applied": False,
                "message": "Arquivos OUTCAR ou INCAR ausentes."
            }

        # Read OUTCAR to find error signatures
        content = ""
        try:
            with open(outcar, "r", encoding="utf-8", errors="ignore") as f:
                # Read last 2000 lines for efficiency
                lines = f.readlines()
                content = "".join(lines[-2000:])
        except Exception as e:
            return {
                "error_detected": False,
                "error_type": None,
                "fix_applied": False,
                "message": f"Erro ao ler OUTCAR: {e}"
            }

        error_detected = False
        error_type = None
        fixes_needed = {}
        message = ""

        # 1. Check EDDDAV: Call to ZHEGV failed
        if "EDDDAV" in content or "ZHEGV" in content:
            error_detected = True
            error_type = "EDDDAV"
            fixes_needed = {"ALGO": "Fast"}
            message = "Erro de diagonalizacao EDDDAV detectado. Alterado ALGO para Fast."

        # 2. Check BRMIX: very serious problems
        elif "BRMIX: very serious problems" in content:
            error_detected = True
            error_type = "BRMIX"
            fixes_needed = {"AMIX": "0.2", "BMIX": "0.0001", "ALGO": "Damped"}
            message = "Erro de divergencia de densidade BRMIX detectado. Ajustado AMIX=0.2 e BMIX=0.0001."

        # 3. Check LREAL warning for small cells
        elif "LREAL" in content and "not recommended" in content:
            error_detected = True
            error_type = "LREAL_SMALL_CELL"
            fixes_needed = {"LREAL": ".FALSE."}
            message = "Aviso critico: LREAL=.TRUE. nao recomendado para celula pequena. Alterado para .FALSE."

        if error_detected and fixes_needed:
            # Apply changes to INCAR
            res_fix = IncarValidator.fix_tags(incar, fixes_needed)
            return {
                "error_detected": True,
                "error_type": error_type,
                "fix_applied": res_fix["success"],
                "message": message,
                "backup": res_fix.get("backup")
            }

        return {
            "error_detected": False,
            "error_type": None,
            "fix_applied": False,
            "message": "Nenhum erro conhecido detectado no OUTCAR."
        }
