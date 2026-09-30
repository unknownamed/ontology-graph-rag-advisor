"""Run a local, explicitly hypothetical 2026 Core scenario from an uploaded PDF.

Private student states and decisions are written only below the ignored logs/ tree.
No student evidence is promoted from UNVERIFIED by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from collections import Counter
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from build_catalog import build  # noqa: E402
from curriculum_assistant.authority import RuleSetStore  # noqa: E402
from curriculum_assistant.file_extract import extract_upload, normalize_upload  # noqa: E402
from curriculum_assistant.graph import Graph, canonical  # noqa: E402
from curriculum_assistant.verifier import verify_payload  # noqa: E402

LABEL = "2026학번으로 가정한 시뮬레이션 결과"
CORE_ATTEMPT_FIELDS = ("attempt_id", "source_course_code", "source_course_name", "earned_credits",
                       "semester", "source_grade", "course_id", "completion_status",
                       "verification_status", "resolution_status")


def row_manifest(state: dict) -> str:
    """Small browser-comparable fingerprint of all original attempt fields."""
    rows = [[attempt.get(key) for key in CORE_ATTEMPT_FIELDS] for attempt in state["course_attempts"]]
    serialized = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    value = 2166136261
    for char in serialized:
        value = ((value ^ ord(char)) * 16777619) & 0xFFFFFFFF
    return f"{value:08x}"


def _completion(grade: str | None) -> str:
    if grade in {"U", "F"}:
        return "FAILED"
    if grade and re.fullmatch(r"(?:[A-D][+0-]?|S|P)", grade):
        return "COMPLETED"
    return "UNKNOWN"


def reconstruct_actual_state(pdf_path: Path, catalog: dict, original_entry_year: int,
                             expected_source_hash: str) -> tuple[dict, dict]:
    data = pdf_path.read_bytes()
    source_hash = hashlib.sha256(data).hexdigest()
    if source_hash != expected_source_hash:
        raise ValueError("The PDF differs from the current browser upload")
    extracted = extract_upload(pdf_path.name, data, catalog)
    if extracted["source_id"] != expected_source_hash:
        raise ValueError("Extraction source hash differs from the uploaded PDF")

    def single_observation(field: str) -> str:
        observations = extracted["student_fields"][field]["observations"]
        values = {item["raw"] for item in observations}
        if len(values) != 1:
            raise ValueError(f"Uploaded {field} cannot be reconstructed unambiguously")
        return values.pop()

    review = {"student_fields": {"confirmed": True,
                                 "student_id": single_observation("student_id"),
                                 "department": single_observation("department"),
                                 "admission_year": original_entry_year,
                                 "credit_policy_year": None, "catalog_year": None,
                                 "program_type": None},
              "records": []}
    for candidate in extracted["candidates"]:
        raw = candidate["raw_values"]
        review["records"].append({"candidate_id": candidate["candidate_id"],
                                  "course_code": raw["course_code"], "course_name": raw["course_name"],
                                  "earned_credits": raw["earned_credits"], "semester": raw["semester"],
                                  "classification": raw["classification"],
                                  "completion_status": _completion(raw.get("grade")), "confirmed": False})
    normalized = normalize_upload(extracted, review, catalog)
    state = normalized["student_state"]
    if state["admission_year"] != original_entry_year or state["upload_source_sha256"] != source_hash:
        raise ValueError("Actual StudentState does not preserve the source year or PDF hash")
    return state, normalized


def make_simulation(actual: dict, normalized: dict, graph: Graph, assumed_entry_year: int) -> tuple[dict, dict]:
    if len(actual["course_attempts"]) != len(normalized["records"]):
        raise ValueError("Upload record and attempt counts differ")
    simulation = deepcopy(actual)
    simulation["student_state_id"] = actual["student_state_id"] + f"-SIM-ENTRY{assumed_entry_year}"
    simulation["admission_year"] = assumed_entry_year
    # These are scenario execution settings, never claims about the actual student.
    simulation["credit_policy_year"] = assumed_entry_year
    simulation["catalog_year"] = assumed_entry_year
    simulation["applicability_status"] = "VERIFIED"
    simulation["program_type"] = "SINGLE"
    simulation["simulation_context"] = {
        "label": LABEL, "simulation_only": True,
        "original_student_state_id": actual["student_state_id"],
        "original_admission_year": actual["admission_year"],
        "assumed_admission_year": assumed_entry_year,
        "assumed_credit_policy_year": assumed_entry_year,
        "assumed_catalog_year": assumed_entry_year,
        "assumed_program_type_for_core_execution": "SINGLE",
        "actual_program_type_verified": False,
        "actual_applicability_verified": False,
        "source_attempt_manifest": row_manifest(actual),
        "classification_source": "CURRICULUM-CE-2026",
    }
    catalog_audit = []
    pre_admission_ids = []
    for attempt, record in zip(simulation["course_attempts"], normalized["records"]):
        if attempt["attempt_id"] != record["candidate_id"]:
            raise ValueError("Upload record order changed")
        source_classification = record["raw_values"]["classification"]
        semester = attempt.get("semester")
        predates_assumed_admission = bool(semester and int(semester[:4]) < assumed_entry_year)
        if predates_assumed_admission:
            pre_admission_ids.append(attempt["attempt_id"])
        code = attempt.get("course_id")
        entry = graph.query("FETCH_CATALOG_ENTRY", curriculum_id="CURRICULUM-CE-2026", course_id=code) if code else None
        official = record["official_course"]
        if bool(entry) != bool(official) or (entry and (entry["course_id"] != official["course_id"]
                                                  or entry["classification"] != official["classification"]
                                                  or entry["catalog_credits"] != official["credits"])):
            raise ValueError("Actual graph and upload catalog resolution disagree")
        attempt["source_classification"] = source_classification
        attempt["catalog_classification_2026"] = entry["classification"] if entry else None
        catalog_audit.append({"attempt_id": attempt["attempt_id"], "source_course_code": attempt["source_course_code"],
                              "source_classification": source_classification,
                              "catalog_course_id": entry["course_id"] if entry else None,
                              "catalog_classification_2026": entry["classification"] if entry else None,
                              "catalog_entry_id": entry["entry_id"] if entry else None,
                              "relationship_ids": entry["relationship_ids"] if entry else [],
                              "source": entry.get("source") if entry else None,
                              "resolution_status": attempt["resolution_status"],
                              "verification_status": attempt["verification_status"],
                              "predates_assumed_admission": predates_assumed_admission,
                              "counted_as_credit": False,
                              "audit_note": "Catalog candidate only; recognition requires verified student evidence."})
    simulation["simulation_context"]["pre_admission_attempt_ids"] = pre_admission_ids
    simulation["simulation_context"]["pre_admission_recognition_status"] = "NEEDS_OFFICIAL_REVIEW"
    if row_manifest(actual) != row_manifest(simulation):
        raise ValueError("The simulation changed an original course attempt field")
    return simulation, {"label": LABEL, "stage": "CANDIDATE_CATALOG_AUDIT_NOT_DECISION_INPUT",
                        "graph_snapshot_id": graph.snapshot_id, "records": catalog_audit}


def query_api(port: int, state: dict) -> dict:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/query",
        data=json.dumps({"student_state": state, "structured_query": {"intent": "GRADUATION_STATUS"},
                         "use_local_llm": False}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    verify_payload(payload)
    return payload


def save_private(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_private_report(path: Path, actual: dict, simulation: dict, audit: dict, payload: dict) -> None:
    """Summarize the actual execution without copying student identity into a tracked document."""
    decision = payload["decision"]
    rows = actual["course_attempts"]
    source_locators = payload["evidence"]["source_locators"]
    exclusion_counts = Counter(item["reason"] for item in decision["excluded"])
    lines = [f"# {LABEL}", "",
             f"이 결과는 실제 {actual['admission_year']}학번 졸업판정이 아니다. 실제 성적표의 이수기록은 보존하고,",
             "입학연도와 2026 Core 실행 범위만 별도 상태에서 가정했다.", "",
             f"- 적용 규칙: {decision['ruleset_id']} v{decision['ruleset_version']}",
             f"- 실제 입학연도: {actual['admission_year']}; 가정 입학연도: {simulation['admission_year']}",
             f"- 성적표 원문: {len(rows)}건, {sum(item.get('earned_credits') or 0 for item in rows)}학점",
             f"- 2026 카탈로그 후보 연결: {sum(bool(r['catalog_course_id']) for r in audit['records'])}건",
             f"- 직접 미연결: {sum(r['resolution_status'] == 'UNRESOLVED' for r in audit['records'])}건; "
             f"반복 후보: {sum(r['resolution_status'] == 'DUPLICATE_CANDIDATE' for r in audit['records'])}건",
             f"- 가정 입학연도보다 앞선 이수기록: {len(simulation['simulation_context']['pre_admission_attempt_ids'])}건 "
             "(공식 선이수 인정 근거 확인 필요)",
             f"- 확정 인정: {len(decision['recognitions'])}건, "
             f"학점 하한 {decision['credited_amount']['confirmed_minimum']}학점; 최종 인정 총학점은 미확정",
             f"- 보류: {len(decision['excluded'])}건; 사유별 {json.dumps(dict(exclusion_counts), ensure_ascii=False)}",
             f"- 결론: {decision['decision_status']} / {decision['graduation_outcome']} "
             "(2026학번 가정, 졸업 가능 여부 확인 필요)", "",
             "## 규칙별 실제 실행 결과", "",
             "| Rule ID | 상태 | 확인된 하한 | 요구값 | PDF 쪽 |",
             "| --- | --- | ---: | ---: | --- |"]
    for result in decision["requirement_results"]:
        pages = sorted({source_locators[ref]["pdf_page_start"] for ref in result["source_refs"]
                        if ref in source_locators})
        observed = result["observed"] if result["observed"] is not None else "—"
        required = result["required"] if result["required"] is not None else "—"
        lines.append(f"| {result['rule_id']} | {result['status']} | {observed} | {required} | "
                     f"{', '.join(str(page) for page in pages) or '—'} |")
    trace = payload["execution_trace"]
    lines += ["", "## 근거 펼쳐보기", "",
              f"- Decision ID: `{decision['decision_id']}`; Execution ID: `{trace['execution_id']}`.",
              f"- 실제 실행: {len(trace['events'])}개 이벤트. "
              "요건 조회 `FETCH_REQUIREMENTS`, 후보 제외, 규칙 평가, 범위 검사, 최종 판정을 기록했다.",
              f"- 실제 판정에 사용된 그래프 요건 관계: {len(payload['evidence']['relationships'])}개. "
              "인정된 학생 과목 관계는 0개다.",
              "- `catalog_candidate_audit_entry2026.json`의 과목 관계는 별도 카탈로그 후보 조회 기록이다. "
              "학점 판정에 사용된 관계로 표시하지 않는다.",
              "- 상세 Rule 계산과 원문 locator는 `simulation_decision_entry2026.json`의 "
              "`requirement_results`, `execution_trace`, `evidence`에 보존했다.", "",
              "## 보류 사유", "",
              f"업로드 {len(rows)}행의 검증 상태와 미연결 {sum(r['resolution_status'] == 'UNRESOLVED' for r in audit['records'])}건의 이수영역, "
              f"반복 후보 {sum(r['resolution_status'] == 'DUPLICATE_CANDIDATE' for r in audit['records'])}건의 이수 인정, "
              f"가정 입학연도 이전 {len(simulation['simulation_context']['pre_admission_attempt_ids'])}건의 공식 인정, "
              "전체 성적표 범위 및 논문·인증 증빙을 확정해야 한다.", "",
              f"실제 {actual['admission_year']}학번 StudentState는 별도 객체로 유지되며 변경하지 않았다.", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-pdf", type=Path, required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--expected-row-manifest", required=True)
    parser.add_argument("--original-entry-year", type=int, required=True)
    parser.add_argument("--assumed-entry-year", type=int, default=2026)
    parser.add_argument("--port", type=int, default=18473)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "logs" / "private" / "entry-year-simulation")
    args = parser.parse_args()
    if args.assumed_entry_year != 2026:
        raise ValueError("This Core RuleSet supports only the 2026 scenario")
    catalog = RuleSetStore(ROOT / "data/processed/ruleset_versions").initialize(build())
    if (catalog["curriculum_ruleset"]["ruleset_id"], catalog["curriculum_ruleset"]["ruleset_version"]) != (
        "CRS-CE-2026-CORE", 1
    ):
        raise ValueError("The active catalog is not the reviewed 2026 Core RuleSet v1")
    actual, normalized = reconstruct_actual_state(args.source_pdf, catalog, args.original_entry_year,
                                                   args.expected_source_sha256)
    if row_manifest(actual) != args.expected_row_manifest:
        raise ValueError("Reconstructed StudentState differs from the supplied upload row manifest")
    actual_before = canonical(actual)
    graph = Graph(Path(":memory:"), catalog)
    try:
        simulation, audit = make_simulation(actual, normalized, graph, args.assumed_entry_year)
    finally:
        graph.close()
    payload = query_api(args.port, simulation)
    if payload["decision"]["ruleset_id"] != "CRS-CE-2026-CORE" or payload["decision"]["ruleset_version"] != 1:
        raise ValueError("Decision did not pin 2026 Core RuleSet v1")
    if payload["execution_trace"]["data_snapshot_id"] != audit["graph_snapshot_id"]:
        raise ValueError("Candidate graph audit and decision used different data snapshots")
    pre_admission_ids = set(simulation["simulation_context"]["pre_admission_attempt_ids"])
    if any(item["attempt_id"] in pre_admission_ids for item in payload["decision"]["recognitions"]):
        raise ValueError("Pre-admission coursework was recognized without an official recognition rule")
    if canonical(actual) != actual_before or row_manifest(simulation) != args.expected_row_manifest:
        raise ValueError("The actual uploaded StudentState was modified")
    save_private(args.output_dir / "actual_student_state.json", actual)
    save_private(args.output_dir / "simulation_student_state_entry2026.json", simulation)
    save_private(args.output_dir / "simulation_decision_entry2026.json", payload)
    save_private(args.output_dir / "catalog_candidate_audit_entry2026.json", audit)
    write_private_report(args.output_dir / "simulation_report_entry2026.md", actual, simulation, audit, payload)
    decision = payload["decision"]
    print(json.dumps({"label": LABEL, "source_rows": len(actual["course_attempts"]),
                      "source_printed_credits": sum(item.get("earned_credits") or 0 for item in actual["course_attempts"]),
                      "pre_assumed_admission_rows": len(pre_admission_ids),
                      "row_manifest": row_manifest(actual), "ruleset_id": decision["ruleset_id"],
                      "ruleset_version": decision["ruleset_version"],
                      "recognized_records": len(decision["recognitions"]),
                      "excluded_records": len(decision["excluded"]),
                      "decision_status": decision["decision_status"],
                      "graduation_outcome": decision["graduation_outcome"],
                      "actual_preserved": canonical(actual) == actual_before}, ensure_ascii=False))


if __name__ == "__main__":
    main()
