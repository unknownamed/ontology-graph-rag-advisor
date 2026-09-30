"""Check the running API's bounded graduation path with synthetic input."""
from __future__ import annotations

import json
import sys
import urllib.request
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from curriculum_assistant.verifier import verify_payload  # noqa: E402


def query(port: int, student: dict, use_local_llm: bool) -> dict:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/query",
        data=json.dumps({"student_state": student, "utterance": "졸업 가능해?",
                         "use_local_llm": use_local_llm}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.load(response)


def main(port: int) -> None:
    fixture = json.loads((ROOT / "tests/fixtures/core_eligible_synthetic.json").read_text(encoding="utf-8"))
    assert fixture["fixture_notice"].startswith("SYNTHETIC INPUT ONLY")
    student = fixture["student_state"]
    plain = query(port, student, False)
    local = query(port, student, True)
    for payload in (plain, local):
        verify_payload(payload)
        assert payload["decision"]["graduation_outcome"] == "ELIGIBLE_PDF"
        assert payload["credited_amount"]["total"] == 130
        assert payload["decision"]["coverage_complete"]
        assert [e["result"] for e in payload["execution_trace"]["events"]
                if e["event_type"] == "COVERAGE_CHECK"] == ["COMPLETE"]
    for key in ("decision", "requirement_results", "credited_amount", "missing_amount",
                "missing_courses", "needs_information", "evidence", "execution_trace", "answer_text"):
        assert plain[key] == local[key], key
    assert local["interpretation"]["llm"]["status"] == "VALIDATED_SUGGESTION"
    assert local["llm_expression"]["status"] == "VERIFIED_STYLE"
    evidence = local["evidence"]
    used = {edge_id for result in local["requirement_results"]
            for edge_id in result["used_relationship_ids"]}
    used.update(edge_id for recognition in local["decision"]["recognitions"]
                for edge_id in recognition["relationship_ids"])
    graph_edges = [edge for edge in evidence["relationship_details"] if edge["id"] in used]
    graph_nodes = {node_id for edge in graph_edges for node_id in (edge["src"], edge["dst"])}
    assert graph_edges and graph_nodes
    prior_catalog = deepcopy(student)
    prior_catalog["catalog_year"] = 2025
    restricted = query(port, prior_catalog, False)
    verify_payload(restricted)
    assert restricted["decision"]["graduation_outcome"] == "UNKNOWN"
    assert "VERIFIED_2026_CREDIT_AND_CATALOG_APPLICABILITY" in restricted["needs_information"]
    print(f"PASS synthetic graduation live: {local['decision']['decision_id']}; "
          f"{len(graph_edges)} displayed edges; {len(graph_nodes)} displayed nodes; "
          f"{len(local['requirement_results'])} rules; {len(local['execution_trace']['events'])} events; "
          "LLM invariance, verified expression, and prior-catalog guard")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 18473)
