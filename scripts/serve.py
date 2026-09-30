"""Launch the local chat prototype."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from build_catalog import build  # noqa: E402
from curriculum_assistant.authority import RuleSetStore  # noqa: E402
from curriculum_assistant.graph import Graph, canonical  # noqa: E402
from curriculum_assistant.server import serve  # noqa: E402
import hashlib  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    catalog = RuleSetStore(ROOT / "data/processed/ruleset_versions").initialize(build())
    snapshot = hashlib.sha256(canonical(catalog).encode()).hexdigest()
    graph = Graph(ROOT / "data/processed" / f"knowledge_graph_{snapshot[:16]}.sqlite", catalog)
    try:
        serve(graph, args.port)
    finally:
        graph.close()


if __name__ == "__main__":
    main()
