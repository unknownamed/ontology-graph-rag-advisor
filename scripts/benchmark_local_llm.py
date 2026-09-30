"""Measure the local model's guarded Korean interpretation on non-evaluation prompts."""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from build_catalog import build  # noqa: E402
from curriculum_assistant.local_llm import interpret_with_local_llm  # noqa: E402

CASES = [
    ("고자구 몇 학점이야?", "COURSE_LOOKUP"),
    ("데베 들으면 전공학점 어떻게 바뀌어?", "WHAT_IF"),
    ("컴구 이수구분 알려줘", "COURSE_LOOKUP"),
    ("지금까지 인정받은 학점 얼마야?", "CREDIT_SUMMARY"),
    ("졸업 가능하고 부족한 게 뭐야?", "GRADUATION_STATUS"),
    ("전공필수 중에 남은 과목 있어?", "REQUIREMENT_GAPS"),
    ("2025학번 컴퓨터공학과 졸업학점은?", "POLICY_LOOKUP"),
    ("그 과목 하나 더 들으면?", "WHAT_IF"),
]


def main() -> None:
    catalog = build()
    context = {"last_course_id": "CDA0143"}
    rows = []
    for question, expected in CASES:
        parsed = interpret_with_local_llm(question, catalog, context)
        query = parsed.get("structured_query") or {}
        observed = query.get("intent")
        rows.append({"question": question, "expected_intent": expected, "intent": observed,
                     "correct": observed == expected, "llm": parsed.get("llm", {}),
                     "interpretation_status": parsed["interpretation_status"]})
        print(f"{'PASS' if observed == expected else 'FAIL'} {observed or 'UNRESOLVED'} "
              f"{parsed.get('llm', {}).get('status', 'N/A')} {question}")
    elapsed = [row["llm"].get("wall_seconds") for row in rows if row["llm"].get("wall_seconds") is not None]
    report = {"correct": sum(row["correct"] for row in rows), "total": len(rows),
              "model_calls": len(elapsed), "latency_seconds_median": statistics.median(elapsed) if elapsed else None,
              "latency_seconds_max": max(elapsed) if elapsed else None, "cases": rows}
    output = ROOT / "logs/local_llm_benchmark.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"SUMMARY {report['correct']}/{report['total']} guarded intents; model calls={report['model_calls']}, "
          f"median={report['latency_seconds_median']}s, max={report['latency_seconds_max']}s")


if __name__ == "__main__":
    main()
