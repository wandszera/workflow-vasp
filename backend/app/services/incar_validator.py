from __future__ import annotations

import shutil
from pathlib import Path
import re


class IncarValidator:
    @staticmethod
    def parse_incar(incar_path: str | Path) -> dict[str, str]:
        path = Path(incar_path)
        if not path.exists():
            return {}

        parsed = {}
        # Pattern to match KEY = VALUE (handles trailing comments)
        pattern = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=\s*([^#!;\s]+)")
        
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                # Strip comments
                clean_line = line.strip()
                if not clean_line or clean_line.startswith(("#", "!", ";")):
                    continue
                match = pattern.match(clean_line)
                if match:
                    key = match.group(1).upper()
                    val = match.group(2).strip()
                    parsed[key] = val
        return parsed

    @staticmethod
    def validate(incar_path: str | Path, goal: str) -> dict[str, any]:
        path = Path(incar_path)
        if not path.exists():
            return {
                "valid": False,
                "warnings": ["Arquivo INCAR nao encontrado."],
                "missing_keys": {}
            }

        tags = IncarValidator.parse_incar(path)
        warnings = []
        missing_keys = {}
        
        clean_goal = str(goal).lower().strip()

        # Validation rules
        if "mlff" in clean_goal:
            # MLFF Training
            if tags.get("ML_LMLFF") != ".TRUE.":
                warnings.append("Tag 'ML_LMLFF' deve ser '.TRUE.' para treino de Machine Learning Force Field.")
                missing_keys["ML_LMLFF"] = ".TRUE."
            
            nsw_val = tags.get("NSW")
            if not nsw_val or int(nsw_val) <= 0:
                warnings.append("Tag 'NSW' deve ser maior que 0 (sugerido NSW = 1000) para treinar MLFF com passos ionicos.")
                missing_keys["NSW"] = "1000"

            ibrion_val = tags.get("IBRION")
            if not ibrion_val or int(ibrion_val) == -1:
                warnings.append("Tag 'IBRION' deve ser maior ou igual a 0 (sugerido IBRION = 2) para permitir movimento ionico.")
                missing_keys["IBRION"] = "2"

            isif_val = tags.get("ISIF")
            if not isif_val:
                warnings.append("Tag 'ISIF' deve ser especificada para controlar graus de liberdade da celula (sugerido ISIF = 3).")
                missing_keys["ISIF"] = "3"

        elif "relax" in clean_goal:
            # Ionic relaxation
            nsw_val = tags.get("NSW")
            if not nsw_val or int(nsw_val) <= 0:
                warnings.append("Tag 'NSW' deve ser maior que 0 para relaxamento de estrutura.")
                missing_keys["NSW"] = "200"

            ibrion_val = tags.get("IBRION")
            if not ibrion_val or int(ibrion_val) == -1:
                warnings.append("Tag 'IBRION' deve ser maior ou igual a 0 (sugerido IBRION = 2).")
                missing_keys["IBRION"] = "2"

            isif_val = tags.get("ISIF")
            if not isif_val:
                warnings.append("Tag 'ISIF' deve ser especificada (sugerido ISIF = 3 para relaxar volume/celula).")
                missing_keys["ISIF"] = "3"

        elif "energy" in clean_goal or "static" in clean_goal:
            # Static energy calculation
            nsw_val = tags.get("NSW")
            if nsw_val and int(nsw_val) > 0:
                warnings.append("Tag 'NSW' deve ser 0 (ou omitida) para calculo de energia estatica (SCF).")
                missing_keys["NSW"] = "0"

            ibrion_val = tags.get("IBRION")
            if ibrion_val and int(ibrion_val) != -1:
                warnings.append("Tag 'IBRION' deve ser -1 para calculo estatico.")
                missing_keys["IBRION"] = "-1"

        return {
            "valid": len(warnings) == 0,
            "warnings": warnings,
            "missing_keys": missing_keys
        }

    @staticmethod
    def fix_tags(incar_path: str | Path, missing_keys: dict[str, str]) -> dict[str, any]:
        path = Path(incar_path)
        if not path.exists():
            return {"success": False, "error": "INCAR nao encontrado."}
        if not missing_keys:
            return {"success": True, "fixed": False}

        backup_path = path.with_suffix(".incar.bak")
        shutil.copy2(path, backup_path)

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            updated_keys = set()
            new_lines = []

            for line in lines:
                clean_line = line.strip()
                matched = False
                
                if clean_line and not clean_line.startswith(("#", "!", ";")):
                    parts = clean_line.split("=", 1)
                    if len(parts) == 2:
                        key = parts[0].strip().upper()
                        if key in missing_keys:
                            new_val = missing_keys[key]
                            new_lines.append(f"{key} = {new_val}   # atualizado pelo assistente\n")
                            updated_keys.add(key)
                            matched = True
                
                if not matched:
                    new_lines.append(line)

            for key, val in missing_keys.items():
                if key not in updated_keys:
                    new_lines.append(f"{key} = {val}   # adicionado pelo assistente\n")

            with open(path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

            return {
                "success": True,
                "fixed": True,
                "backup": backup_path.name
            }
        except Exception as e:
            if backup_path.exists():
                shutil.copy2(backup_path, path)
            return {"success": False, "error": str(e)}
