"""Independent adversarial PDF upload cases built only from synthetic catalog rows."""
from __future__ import annotations

import base64
import copy
import json
import sys
import tempfile
import threading
import unittest
from http.server import HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from curriculum_assistant.graph import Graph  # noqa: E402
from curriculum_assistant.server import Handler  # noqa: E402
from curriculum_assistant.verifier import verify_payload  # noqa: E402
from generate_mock_2026_transcripts import catalog_v1, make_rows, select_complete_courses, write_pdf  # noqa: E402
from verify_mock_2026_pdf_e2e import (post, review_from_candidates,
                                       attach_explicit_test_attestations)  # noqa: E402


class MockPdfReviewerCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = catalog_v1()
        cls.complete_codes = select_complete_courses(cls.catalog)
        cls.by_code = {course["course_id"]: course for course in cls.catalog["courses"]}
        cls.base_rows = make_rows(cls.complete_codes, cls.catalog, None)

        class BoundHandler(Handler):
            pass

        cls.server = HTTPServer(("127.0.0.1", 0), BoundHandler)
        cls.ready = threading.Event()

        def serve():
            graph = Graph(Path(":memory:"), cls.catalog)
            BoundHandler.graph = graph
            cls.ready.set()
            try:
                cls.server.serve_forever()
            finally:
                graph.close()

        cls.thread = threading.Thread(target=serve, daemon=True)
        cls.thread.start()
        assert cls.ready.wait(10)
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def _case(self, name: str, rows: list[dict]) -> tuple[dict, dict, dict]:
        with tempfile.TemporaryDirectory(prefix="mock-ce-review-") as temp:
            path = Path(temp) / f"{name}.pdf"
            write_pdf(path, name, rows, "2026000999")
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            extracted = post(self.port, "/api/extract", {"filename": path.name, "content_base64": encoded})
            normalized = post(self.port, "/api/normalize-upload", {"filename": path.name,
                                                                      "content_base64": encoded,
                                                                      "source_id": extracted["source_id"],
                                                                      "review": review_from_candidates(extracted)})
            state = attach_explicit_test_attestations(normalized["student_state"], name)
            payload = post(self.port, "/api/query", {"student_state": state,
                                                      "utterance": "이 학생 졸업할 수 있어?",
                                                      "use_local_llm": False})
            verify_payload(payload)
            return extracted, normalized, payload

    def test_duplicate_completed_course_is_not_double_counted(self):
        rows = copy.deepcopy(self.base_rows)
        candidate = next(row for row in rows if self.by_code[row["catalog_course_id"]]["classification"] == "MAJOR_ELECTIVE"
                         and row["credits"] > 0)
        repeated = copy.deepcopy(candidate)
        repeated["term"] = "2" if candidate["term"] == "1" else "1"
        rows.append(repeated)
        extracted, normalized, payload = self._case("reviewer_duplicate", rows)
        self.assertEqual(len(rows), extracted["candidate_count"])
        self.assertEqual(2, sum(r["resolution_status"] == "DUPLICATE_CANDIDATE" for r in normalized["records"]))
        self.assertEqual("UNKNOWN", payload["decision"]["graduation_outcome"])
        self.assertTrue(any(x["reason"] == "REPEAT_RESOLUTION_UNKNOWN" for x in payload["decision"]["excluded"]))

    def test_code_name_conflict_stays_ambiguous(self):
        rows = copy.deepcopy(self.base_rows)
        target = next(row for row in rows if row["classification"] == "전공선택" and row["credits"] > 0)
        other = next(row for row in rows if row["course_code"] != target["course_code"]
                     and row["classification"] == "전공선택")
        target["course_name"] = other["course_name"]
        _, normalized, payload = self._case("reviewer_name_conflict", rows)
        self.assertEqual(1, sum(r["resolution_status"] == "AMBIGUOUS" for r in normalized["records"]))
        self.assertEqual("UNKNOWN", payload["decision"]["graduation_outcome"])

    def test_other_zero_credit_required_still_blocks_graduation(self):
        zero = sorted(code for code in self.complete_codes
                      if self.by_code[code]["classification"] == "MAJOR_REQUIRED"
                      and self.by_code[code]["catalog_credits"] == 0)
        self.assertGreaterEqual(len(zero), 2)
        rows = [copy.deepcopy(row) for row in self.base_rows if row["catalog_course_id"] != zero[-1]]
        _, _, payload = self._case("reviewer_other_zero_required", rows)
        self.assertEqual("NOT_ELIGIBLE_PDF", payload["decision"]["graduation_outcome"])
        self.assertEqual(sum(row["credits"] for row in self.base_rows),
                         payload["decision"]["credited_amount"]["total"])
        required = next(r for r in payload["requirement_results"] if r["rule_id"] == "R-CE-2026-REQUIRED-COURSES")
        self.assertEqual([zero[-1]], required["missing_course_ids"])

    def test_row_order_does_not_change_semantic_decision(self):
        _, _, forward = self._case("reviewer_order_forward", copy.deepcopy(self.base_rows))
        _, _, backward = self._case("reviewer_order_backward", list(reversed(copy.deepcopy(self.base_rows))))
        self.assertEqual(forward["decision"]["graduation_outcome"], backward["decision"]["graduation_outcome"])
        self.assertEqual(forward["credited_amount"], backward["credited_amount"])
        self.assertEqual({r["rule_id"]: r["status"] for r in forward["requirement_results"]},
                         {r["rule_id"]: r["status"] for r in backward["requirement_results"]})

    def test_nonexistent_course_code_never_becomes_catalog_credit(self):
        rows = copy.deepcopy(self.base_rows)
        target = next(row for row in rows if row["classification"] == "전공선택" and row["credits"] > 0)
        target["course_code"] = "ZZZ9999"  # Explicit adversarial invalid code, not a catalog fixture.
        _, normalized, payload = self._case("reviewer_unknown_code", rows)
        self.assertEqual(1, sum(r["resolution_status"] == "UNRESOLVED" for r in normalized["records"]))
        self.assertEqual("UNKNOWN", payload["decision"]["graduation_outcome"])
        self.assertTrue(any(r["reason"] == "MISSING_COURSE_ID" for r in payload["decision"]["excluded"]))

    def test_upload_classification_conflict_cannot_override_catalog(self):
        rows = copy.deepcopy(self.base_rows)
        target = next(row for row in rows if row["classification"] == "균형교양")
        target["classification"] = "기초교양"
        _, normalized, payload = self._case("reviewer_classification_conflict", rows)
        self.assertEqual(1, sum(r["resolution_status"] == "AMBIGUOUS" for r in normalized["records"]))
        self.assertEqual("UNKNOWN", payload["decision"]["graduation_outcome"])

    def test_missing_code_row_is_retained_and_requires_information(self):
        rows = copy.deepcopy(self.base_rows)
        target = next(row for row in rows if self.by_code[row["catalog_course_id"]]["classification"] == "MAJOR_REQUIRED"
                      and row["credits"] == 0)
        target["course_code"] = None
        extracted, normalized, payload = self._case("reviewer_missing_code", rows)
        self.assertEqual(len(rows), extracted["candidate_count"])
        unresolved = [r for r in normalized["records"] if r["resolution_status"] == "UNRESOLVED"]
        self.assertEqual(1, len(unresolved))
        self.assertEqual(0, unresolved[0]["raw_values"]["earned_credits"])
        self.assertEqual("UNKNOWN", payload["decision"]["graduation_outcome"])
        self.assertTrue(any("UNRESOLVED_COMPLETION_RECORD" in reason
                            for reason in payload["decision"]["needs_information"]))


if __name__ == "__main__":
    unittest.main()
