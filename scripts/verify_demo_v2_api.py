"""Prepare ten synthetic demo scenarios and independent API evidence for UI QA."""
from __future__ import annotations

import argparse
import base64
import json
import html
import sys
import urllib.request
import urllib.error
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from curriculum_assistant.authority import RuleSetStore
from curriculum_assistant.verifier import verify_payload
from verify_mock_2026_pdf_e2e import review_from_candidates


def display_value(value: object) -> str:
    """Match JavaScript's primitive display without changing expected values."""
    if value is None:
        return "미확인"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18473)
    args = parser.parse_args()
    catalog = RuleSetStore(ROOT / "data/processed/ruleset_versions").load_active()
    assert catalog["curriculum_ruleset"]["ruleset_version"] == 2
    directory = ROOT / "logs/demo-v2"
    directory.mkdir(parents=True, exist_ok=True)

    def post(route: str, request: dict) -> dict:
        req = urllib.request.Request(f"http://127.0.0.1:{args.port}{route}",
                                     data=json.dumps(request, ensure_ascii=False).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"{route}: {error.read().decode('utf-8')}; question={request.get('utterance')}") from error

    def profile(name: str) -> dict:
        fixture = json.loads((ROOT / f"evaluation/fixtures/remaining_2026/{name}.json").read_text(encoding="utf-8"))
        assert fixture["notice"].startswith("SYNTHETIC")
        return fixture["student_state"]

    complete = json.loads((ROOT / "tests/fixtures/core_eligible_synthetic.json").read_text(encoding="utf-8"))["student_state"]
    boundary = deepcopy(complete)
    boundary["student_state_id"] = "TEST-DEMO-V2-BOUNDARY"
    boundary["course_attempts"] = [a for a in boundary["course_attempts"] if a["course_id"] != "CDA0088"]
    rows = [
        ("D01", "과목 조회", "고자구 몇 학점이야?", None),
        ("D02", "학생 없는 정책·상한 계산", "교양 47학점 취득한 경우 인정 한도는?", None),
        ("D03", "현재 졸업 상태", "지금 졸업 가능해?", profile("year1_early")),
        ("D04", "남은 요건과 후보 요약", "앞으로 뭐 더 들어야 해?", profile("year1_early")),
        ("D05", "교양 영역별 부족·후보", "교양 뭐 더 들어야 해?", profile("year1_early")),
        ("D06", "전공 남은 요건", "전공에서 남은 거 알려줘.", profile("year3_late")),
        ("D07", "총학점 충족·필수 누락", "전필 뭐 남았어?", profile("required_missing")),
        ("D08", "0학점 필수 추가 simulation", "CDA0088 추가로 들으면 졸업 가능해?", boundary),
        ("D09", "모든 증빙 충족 졸업", "지금 졸업 가능해?", complete),
    ]
    fixture_id = "mock_2026_missing_info"
    pdf = ROOT / f"evaluation/fixtures/student_records/{fixture_id}.pdf"
    content = base64.b64encode(pdf.read_bytes()).decode()
    extracted = post("/api/extract", {"filename": pdf.name, "content_base64": content})
    review = review_from_candidates(extracted)
    normalized = post("/api/normalize-upload", {"filename": pdf.name, "content_base64": content,
                                                "source_id": extracted["source_id"], "review": review})
    rows.append(("D10", "PDF 업로드·정보 부족", "지금 졸업 가능해?", normalized["student_state"]))
    manifest = []
    public = []
    for sid, title, question, state in rows:
        before = json.dumps(state, sort_keys=True)
        request = {"utterance": question, "use_local_llm": True}
        if state is not None:
            request["student_state"] = state
        payload = post("/api/query", request)
        verify_payload(payload)
        assert payload["decision"]["ruleset_version"] == 2
        assert json.dumps(state, sort_keys=True) == before
        entry = {"id": sid, "title": title, "question": question, "student_state": state,
                 "payload": payload}
        if sid == "D10":
            entry.update({"upload_file": str(pdf), "upload_review": review,
                          "upload_candidate_count": extracted["candidate_count"],
                          "usable_record_count": normalized["usable_record_count"]})
        manifest.append(entry)
        public.append({"id": sid, "title": title, "question": question,
                       "decision_id": payload["decision"]["decision_id"],
                       "execution_id": payload["execution_trace"]["execution_id"],
                       "intent": payload["decision"]["intent"],
                       "graduation_outcome": payload["decision"]["graduation_outcome"],
                       "ruleset_version": 2, "provenance_verification": "PASS"})
    (directory / "scenarios.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    for index, entry in enumerate(manifest):
        payload = entry["payload"]
        evidence = payload["evidence"]
        browser_entry = {key: value for key, value in entry.items() if key != "payload"}
        browser_entry["expected"] = {
            "answer": payload["answer_text"], "decision_id": payload["decision"]["decision_id"],
            "outcome": payload["decision"]["graduation_outcome"],
            "requirement_lines": [f"{r['rule_id']}: {r['status']} · 관찰 {display_value(r['observed'])} / 요구 {display_value(r['required'])}" for r in payload["requirement_results"]],
            "event_lines": [f"{e['sequence']}. {e['event_type']}" + (f" · {e['operation']}" if e.get('operation') else '') + (f" · {e['rule_id']}" if e.get('rule_id') else '') for e in payload["execution_trace"]["events"]],
            "relationship_ids": evidence["relationships"],
            "node_titles": [f"{n['kind']}: {n['id']}" for n in evidence["nodes"]],
            "pdf_pages": sorted({s["pdf_page_start"] for s in evidence["source_locators"].values()} | {f["source"]["pdf_page"] for f in evidence["facts"] if f.get("source", {}).get("pdf_page")}),
            "amount": payload["credited_amount"], "scenario_delta": payload.get("scenario_delta"),
            "policy_calculations": (payload["decision"].get("lookup_result") or {}).get("calculations", []),
            "candidates": [{key: c[key] for key in ("course_id", "course_name", "candidate_status", "credits", "satisfies_requirement_ids", "relationship_ids")} for c in payload["decision"].get("candidate_courses", [])],
        }
        content = html.escape(json.dumps(browser_entry, ensure_ascii=False))
        (directory / f"c{index}.html").write_text(f'<!doctype html><meta charset="utf-8"><title>Synthetic demo case {index}</title><pre>{content}</pre>', encoding="utf-8")
    result = {"notice": "SYNTHETIC DEMO ONLY / 실제 학생 자료 아님", "document_set_version": 1,
              "ruleset_version": 2, "api_scenarios": public,
              "ui_verification": "NOT_EXECUTED_BY_THIS_SCRIPT",
              "ui_result_file": "evaluation/results/core_v2_demo_ui_results.json"}
    (ROOT / "evaluation/results/core_v2_demo_api_results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {len(public)} v2 API scenarios prepared; UI verification pending")


if __name__ == "__main__":
    main()
