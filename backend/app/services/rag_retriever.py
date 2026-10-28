from __future__ import annotations

import json
import math
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_TOKEN_RE = re.compile(r"[a-zA-Z0-9_.+-]+")


@dataclass(frozen=True)
class RetrievedDocument:
    document_id: str
    title: str
    source: str
    text: str
    metadata: dict[str, Any]
    score: float

    def citation(self, excerpt_size: int = 360) -> dict[str, Any]:
        excerpt = " ".join(self.text.split())
        if len(excerpt) > excerpt_size:
            excerpt = excerpt[: excerpt_size - 1].rstrip() + "…"
        return {
            "document_id": self.document_id,
            "title": self.title,
            "source": self.source,
            "excerpt": excerpt,
            "score": round(self.score, 4),
            "metadata": self.metadata,
        }


class LocalHybridRetriever:
    """Small auditable baseline retriever.

    It combines token overlap, inverse document frequency and metadata filters.
    The interface is intentionally storage-agnostic so a vector backend can replace
    it without changing the diagnosis graph.
    """

    def __init__(self, knowledge_path: Path | None = None) -> None:
        default_path = Path(__file__).resolve().parent.parent / "data" / "rag_knowledge.json"
        self.knowledge_path = knowledge_path or default_path
        self.documents = self._load()
        self._reindex()

    def _reindex(self) -> None:
        self._document_tokens = [self._tokens(f"{doc['title']} {doc['text']}") for doc in self.documents]
        self._idf = self._build_idf(self._document_tokens)

    def _load(self) -> list[dict[str, Any]]:
        with self.knowledge_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, list):
            raise ValueError("A base RAG deve ser uma lista JSON de documentos.")
        return [entry for entry in payload if isinstance(entry, dict)]

    def add_document(
        self,
        *,
        title: str,
        source: str,
        text: str,
        metadata: dict[str, Any],
        document_id: str | None = None,
    ) -> dict[str, Any]:
        identifier = document_id or str(uuid.uuid4())
        if any(str(item.get("id")) == identifier for item in self.documents):
            raise ValueError(f"Ja existe um documento com id {identifier}.")
        document = {
            "id": identifier,
            "title": title,
            "source": source,
            "text": text,
            "metadata": metadata,
        }
        self.documents.append(document)
        temporary_path = self.knowledge_path.with_suffix(self.knowledge_path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(self.documents, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary_path.replace(self.knowledge_path)
        self._reindex()
        return document

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {token.lower() for token in _TOKEN_RE.findall(text) if len(token) > 1}

    @staticmethod
    def _build_idf(documents: list[set[str]]) -> dict[str, float]:
        counts: dict[str, int] = {}
        for tokens in documents:
            for token in tokens:
                counts[token] = counts.get(token, 0) + 1
        total = max(1, len(documents))
        return {token: math.log((total + 1) / (count + 1)) + 1.0 for token, count in counts.items()}

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        failure_class: str | None = None,
        calculation_type: str | None = None,
    ) -> list[RetrievedDocument]:
        query_tokens = self._tokens(query)
        if not query_tokens:
            return []

        results: list[RetrievedDocument] = []
        for doc, tokens in zip(self.documents, self._document_tokens):
            metadata = dict(doc.get("metadata") or {})
            doc_failure = str(metadata.get("failure_class", "unknown"))
            doc_calc = str(metadata.get("calculation_type", "any"))
            if failure_class and doc_failure not in {failure_class, "unknown"}:
                continue
            if calculation_type and doc_calc not in {calculation_type, "any"}:
                continue

            overlap = query_tokens & tokens
            if not overlap:
                continue
            lexical = sum(self._idf.get(token, 1.0) for token in overlap) / max(1.0, len(query_tokens) ** 0.5)
            metadata_bonus = 0.0
            if failure_class and doc_failure == failure_class:
                metadata_bonus += 1.25
            if calculation_type and doc_calc == calculation_type:
                metadata_bonus += 0.5
            if metadata.get("validated") is True:
                metadata_bonus += 0.25
            score = lexical + metadata_bonus
            results.append(
                RetrievedDocument(
                    document_id=str(doc["id"]),
                    title=str(doc["title"]),
                    source=str(doc["source"]),
                    text=str(doc["text"]),
                    metadata=metadata,
                    score=score,
                )
            )

        results.sort(key=lambda item: (-item.score, item.document_id))
        return results[:top_k]

