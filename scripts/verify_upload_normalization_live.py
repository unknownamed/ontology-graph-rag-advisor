"""Exercise synthetic transcript extraction and normalization through the live user API."""
from __future__ import annotations

import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "src")]
from test_student_upload_normalization import completed_review, transcript  # noqa: E402
from curriculum_assistant.verifier import verify_payload  # noqa: E402


def post(port: int, path: str, body: dict) -> dict:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.load(response)


def main(port: int) -> None:
    data = transcript([
        ["2026-1학기", "CDA0163", "웹프로그래밍", "3", "전공선택", "이수"],
        ["2026-1학기", "CDA0143", "고급자료구조", "3", "전공필수", "이수"],
        ["2026-2학기", "CDA0143", "고급자료구조", "3", "전공필수", "이수"],
        ["2026-2학기", "XYZ9999", "가상과목", "3", "전공선택", "이수"],
    ])
    upload = {"filename": "TEST_FIXTURE_student_upload.docx",
              "content_base64": base64.b64encode(data).decode("ascii")}
    extracted = post(port, "/api/extract", upload)
    assert extracted["candidate_count"] == 4
    assert [c["resolution_status"] for c in extracted["candidates"]] == [
        "RESOLVED_TO_CATALOG", "DUPLICATE_CANDIDATE", "DUPLICATE_CANDIDATE", "UNRESOLVED"]
    normalized = post(port, "/api/normalize-upload", {
        **upload, "source_id": extracted["source_id"], "review": completed_review(extracted)})
    state = normalized["student_state"]
    assert normalized["usable_record_count"] == 1 and normalized["unresolved_record_count"] == 3
    assert state["student_state_id"].startswith("UPLOAD-") and state["student_id"] == "2026123456"
    assert state["completion_coverage"] == "PARTIAL" and state["applicability_status"] == "UNVERIFIED"
    assert all(a["attempt_id"] != "SYNTHETIC-A1" for a in state["course_attempts"])
    assert [a["verification_status"] for a in state["course_attempts"]] == [
        "VERIFIED", "UNVERIFIED", "UNVERIFIED", "UNVERIFIED"]
    assert (normalized["ruleset_id"], normalized["ruleset_version"]) == ("CRS-CE-2026-CORE", 1)
    decision = post(port, "/api/query", {"student_state": state,
                                          "utterance": "이 상태로 졸업 가능한가?", "use_local_llm": False})
    verify_payload(decision)
    assert decision["decision"]["graduation_outcome"] == "UNKNOWN"
    assert decision["decision"]["decision_status"] == "NEEDS_INFORMATION"
    try:
        post(port, "/api/normalize-upload", {**upload, "source_id": "wrong-hash",
                                               "review": completed_review(extracted)})
    except urllib.error.HTTPError as error:
        assert error.code == 400
    else:
        raise AssertionError("Changed upload hash was accepted")
    print("PASS synthetic file → /api/extract → reviewed /api/normalize-upload → "
          "partial StudentState → safe /api/query; 1 usable, 3 unresolved; RuleSet v1")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 18473)
