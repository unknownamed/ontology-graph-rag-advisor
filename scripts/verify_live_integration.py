"""Exercise the running localhost API with a synthetic upload and real Ollama."""
from __future__ import annotations

import base64
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from curriculum_assistant.verifier import verify_payload  # noqa: E402


def post(path: str, value: dict, port: int) -> dict:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(value, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.load(response)


def main(port: int) -> None:
    pdf = (ROOT / "tests/fixtures/synthetic-transcript.pdf").read_bytes()
    extracted = post("/api/extract", {"filename": "synthetic-transcript.pdf",
                                      "content_base64": base64.b64encode(pdf).decode()}, port)
    assert extracted["candidate_count"] == 1 and extracted["requires_user_confirmation"]
    candidate = extracted["candidates"][0]
    assert (candidate["course_id"], candidate["extraction_status"], candidate["completion_status"]) == (
        "CDA0163", "UNVERIFIED", "UNKNOWN")
    student = {
        "student_state_id": "SYNTHETIC-DEMO", "student_id": "SYNTHETIC", "admission_year": 2026,
        "department_id": "DEPT-COMPUTER-ENGINEERING", "credit_policy_year": 2026,
        "catalog_year": 2026, "applicability_status": "VERIFIED", "program_type": "SINGLE",
        "completion_coverage": "PARTIAL", "course_attempts": [
            {"attempt_id": "SYNTHETIC-A1", "course_id": "CDA0143", "completion_status": "COMPLETED",
             "verification_status": "VERIFIED", "evidence_id": "SYNTHETIC-INPUT-A1", "earned_credits": 3},
            {"attempt_id": candidate["candidate_id"], "course_id": "CDA0163",
             "completion_status": "COMPLETED", "verification_status": "VERIFIED",
             "evidence_id": f"USER-CONFIRMED-{candidate['candidate_id']}", "earned_credits": 3,
             "evidence_type": "USER_CONFIRMED_UPLOAD",
             "evidence_locator": {"source_sha256": extracted["source_id"],
                                  "filename": "synthetic-transcript.pdf", "location": candidate["location"]}},
        ],
    }
    base = {"student_state": student, "utterance": "지금까지 전공학점 몇 학점 인정받았어?"}
    deterministic = post("/api/query", {**base, "use_local_llm": False}, port)
    with_model = post("/api/query", {**base, "use_local_llm": True}, port)
    for result in (deterministic, with_model):
        verify_payload(result)
        assert result["credited_amount"]["by_area"]["MAJOR_TOTAL"] == 6
        assert result["decision"]["graduation_outcome"] == "NOT_REQUESTED"
    for field in ("decision", "requirement_results", "credited_amount", "missing_amount",
                  "missing_courses", "needs_information", "evidence", "execution_trace"):
        assert deterministic[field] == with_model[field], field
    assert with_model["llm_expression"]["status"] == "VERIFIED_STYLE"
    source_pages = sorted({source["pdf_page_start"] for source in with_model["evidence"]["source_locators"].values()})
    print(f"PASS upload→confirmed input→Korean query→decision; {with_model['decision']['decision_id']}; "
          f"{len(with_model['evidence']['relationship_details'])} relations; "
          f"{len(with_model['requirement_results'])} rules; "
          f"{len(with_model['execution_trace']['events'])} trace events; "
          f"PDF pages {source_pages}; LLM invariance")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 18473)
