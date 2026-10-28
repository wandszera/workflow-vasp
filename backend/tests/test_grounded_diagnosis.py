from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.app.services.diagnosis_graph import GroundedDiagnosisGraph
from backend.app.services.diagnosis_store import DiagnosisStore
from backend.app.services.rag_retriever import LocalHybridRetriever


class GroundedDiagnosisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = DiagnosisStore(self.root / "diagnoses.db")
        self.graph = GroundedDiagnosisGraph(store=self.store)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_zbrent_diagnosis_is_grounded_and_waits_for_human(self) -> None:
        calc = self.root / "calc"
        calc.mkdir()
        (calc / "INCAR").write_text("NSW = 100\nPOTIM = 0.5\n", encoding="utf-8")
        (calc / "OUTCAR").write_text("ZBRENT: fatal error in bracketing\n", encoding="utf-8")

        result = self.graph.diagnose(str(calc), goal="relax geometry")

        self.assertEqual(result["failure_class"], "ionic_or_structural")
        self.assertEqual(result["status"], "awaiting_approval")
        self.assertTrue(result["citations"])
        self.assertIn("local-zbrent-001", {item["document_id"] for item in result["citations"]})
        self.assertIn("solicitar_aprovacao_humana", result["graph_trace"])
        self.assertEqual((calc / "INCAR").read_text(encoding="utf-8"), "NSW = 100\nPOTIM = 0.5\n")

    def test_unknown_failure_cannot_be_approved(self) -> None:
        calc = self.root / "unknown"
        calc.mkdir()
        (calc / "INCAR").write_text("ENCUT = 500\n", encoding="utf-8")
        (calc / "OUTCAR").write_text("unexpected opaque failure 934\n", encoding="utf-8")

        result = self.graph.diagnose(str(calc))

        self.assertEqual(result["status"], "insufficient_evidence")
        with self.assertRaises(ValueError):
            self.store.decide(result["diagnosis_id"], True, "approve anyway")

    def test_decision_is_persisted_in_audit_trail(self) -> None:
        calc = self.root / "electronic"
        calc.mkdir()
        (calc / "INCAR").write_text("ALGO = Fast\n", encoding="utf-8")
        (calc / "OUTCAR").write_text("BRMIX: very serious problems\n", encoding="utf-8")
        result = self.graph.diagnose(str(calc))

        decided = self.store.decide(result["diagnosis_id"], False, "revisar estrutura primeiro")
        reloaded = self.store.get(result["diagnosis_id"])

        self.assertEqual(decided["status"], "rejected")
        self.assertEqual(reloaded["human_note"], "revisar estrutura primeiro")
        self.assertIn("registrar_feedback", reloaded["graph_trace"])


class LocalHybridRetrieverTests(unittest.TestCase):
    def test_metadata_filter_keeps_failure_compatible_documents(self) -> None:
        retriever = LocalHybridRetriever()
        results = retriever.search(
            "BRMIX very serious problems electronic convergence",
            failure_class="electronic_convergence",
            top_k=3,
        )
        self.assertTrue(results)
        self.assertTrue(
            all(item.metadata["failure_class"] in {"electronic_convergence", "unknown"} for item in results)
        )

    def test_ingested_document_is_immediately_searchable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            kb_path = Path(directory) / "knowledge.json"
            kb_path.write_text("[]\n", encoding="utf-8")
            retriever = LocalHybridRetriever(kb_path)
            retriever.add_document(
                document_id="case-001",
                title="Caso de memoria SLURM",
                source="case://lab/001",
                text="Falha oom-kill resolvida apos revisar memoria e ranks MPI do job.",
                metadata={"failure_class": "resources_or_slurm", "calculation_type": "any"},
            )

            results = retriever.search("oom-kill memoria ranks", failure_class="resources_or_slurm")

            self.assertEqual(results[0].document_id, "case-001")


if __name__ == "__main__":
    unittest.main()
