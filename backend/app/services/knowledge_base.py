from __future__ import annotations

import json
from pathlib import Path


class VaspKnowledgeBase:
    def __init__(self, kb_path: Path | None = None) -> None:
        default_path = Path(__file__).resolve().parent.parent / "data" / "vasp_error_kb.json"
        self.kb_path = kb_path or default_path
        self.entries = self._load_entries()

    def _load_entries(self) -> list[dict[str, object]]:
        with self.kb_path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def match(self, text: str) -> list[dict[str, object]]:
        haystack = text.lower()
        matches: list[dict[str, object]] = []
        for entry in self.entries:
            triggers = [trigger.lower() for trigger in entry.get("triggers", [])]
            if any(trigger in haystack for trigger in triggers):
                matches.append(entry)
        return matches
