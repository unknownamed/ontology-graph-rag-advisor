"""Run the deterministic vertical slice from a structured JSON request."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from curriculum_assistant.engine import execute  # noqa: E402
from curriculum_assistant.graph import Graph  # noqa: E402
from curriculum_assistant.nlp import interpret  # noqa: E402
from curriculum_assistant.local_llm import interpret_with_local_llm  # noqa: E402
from build_catalog import build  # noqa: E402


def main() -> None:
    catalog = build()
    request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8") if len(sys.argv) > 1 else sys.stdin.read())
    snapshot = __import__("hashlib").sha256(json.dumps(catalog, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    graph_path = ROOT / "data/processed" / f"knowledge_graph_{snapshot[:16]}.sqlite"
    graph = Graph(graph_path, catalog)
    try:
        if "structured_query" in request:
            query = request["structured_query"]
            interpretation = None
        else:
            parser = interpret_with_local_llm if request.get("use_local_llm", False) else interpret
            interpretation = parser(request["utterance"], catalog, request.get("context"))
            query = interpretation["structured_query"]
        payload = execute(graph, request["student_state"], query) if query else {"interpretation": interpretation,
                 "answer_text": "질문에서 과목이나 의도를 확정할 수 없습니다. 표현을 더 구체적으로 알려 주세요."}
        if interpretation and query:
            payload["interpretation"] = interpretation
    finally:
        graph.close()
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
