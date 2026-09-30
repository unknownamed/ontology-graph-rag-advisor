"""Reviewer checks for silent graph corruption and query bypasses."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from build_catalog import build  # noqa: E402
from curriculum_assistant.graph import Graph  # noqa: E402
from curriculum_assistant.engine import execute  # noqa: E402


class GraphIntegrityCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = build()

    def test_unknown_operation_rejected_even_for_unknown_curriculum(self):
        graph = Graph(Path(":memory:"), self.catalog)
        try:
            with self.assertRaises(ValueError):
                graph.query("DELETE_ALL", curriculum_id="BOGUS")
        finally:
            graph.close()

    def test_reopened_graph_detects_missing_relationship(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "graph.sqlite"
            graph = Graph(path, self.catalog)
            graph.db.execute("DELETE FROM edges WHERE id='E-CURR-CDA0143'")
            graph.db.commit()
            graph.close()
            with self.assertRaisesRegex(ValueError, "count differs"):
                Graph(path, self.catalog)

    def test_invalid_student_record_is_rejected_at_boundary(self):
        graph = Graph(Path(":memory:"), self.catalog)
        state = {"student_state_id": "X", "department_id": "DEPT-COMPUTER-ENGINEERING",
                 "program_type": "SINGLE", "completion_coverage": "PARTIAL",
                 "applicability_status": "VERIFIED", "course_attempts": ["CDA0143"]}
        try:
            with self.assertRaisesRegex(ValueError, "CourseAttempt must be an object"):
                execute(graph, state, {"intent": "CREDIT_SUMMARY"})
        finally:
            graph.close()


if __name__ == "__main__":
    unittest.main()
