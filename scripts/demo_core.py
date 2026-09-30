"""Reproduce the bounded 2026 CE single-major core with synthetic evidence."""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from build_catalog import build  # noqa: E402
from curriculum_assistant.engine import execute  # noqa: E402
from curriculum_assistant.graph import Graph  # noqa: E402
from curriculum_assistant.verifier import verify_payload  # noqa: E402


def main() -> None:
    request = json.loads((ROOT / "tests/fixtures/core_eligible_synthetic.json").read_text(encoding="utf-8"))
    assert request["fixture_notice"].startswith("SYNTHETIC INPUT ONLY")
    base = request["student_state"]
    graph = Graph(Path(":memory:"), build())
    try:
        eligible = execute(graph, base, {"intent": "GRADUATION_STATUS"})
        verify_payload(eligible)
        assert eligible["decision"]["graduation_outcome"] == "ELIGIBLE_PDF"
        assert eligible["credited_amount"]["total"] == 130
        print("PASS synthetic verified 2026 CE single major: 해당 PDF 기준 졸업 가능, 130학점")

        short = deepcopy(base)
        short["course_attempts"] = [a for a in short["course_attempts"] if a["course_id"] != "CDA0163"]
        unmet = execute(graph, short, {"intent": "GRADUATION_STATUS"})
        verify_payload(unmet)
        assert unmet["decision"]["graduation_outcome"] == "NOT_ELIGIBLE_PDF"
        assert unmet["credited_amount"]["total"] == 127
        print("PASS synthetic known shortfall: 해당 PDF 기준 졸업 요건 미충족, 127학점")

        incomplete = deepcopy(base)
        incomplete["completion_coverage"] = "PARTIAL"
        incomplete.pop("completion_coverage_evidence_id")
        unknown = execute(graph, incomplete, {"intent": "GRADUATION_STATUS"})
        verify_payload(unknown)
        assert unknown["decision"]["graduation_outcome"] == "UNKNOWN"
        assert unknown["credited_amount"]["total"] is None
        print("PASS incomplete transcript: 졸업 가능 여부 확인 필요")

        before = deepcopy(short)
        scenario = execute(graph, short, {"intent": "WHAT_IF", "course_id": "CDA0163",
                                          "assumed_completion": "SUCCESS"})
        verify_payload(scenario)
        assert short == before
        assert scenario["credited_amount"]["total"] == 127
        assert scenario["scenario_decision"]["credited_amount"]["total"] == 130
        print("PASS isolated what-if: actual 127학점, hypothetical 130학점")

        multi = deepcopy(base)
        multi["program_type"] = "DOUBLE"
        restricted = execute(graph, multi, {"intent": "GRADUATION_STATUS"})
        verify_payload(restricted)
        assert restricted["decision"]["graduation_outcome"] == "UNKNOWN"
        print("PASS extended-scope guard: second major remains unverified")
    finally:
        graph.close()


if __name__ == "__main__":
    main()
