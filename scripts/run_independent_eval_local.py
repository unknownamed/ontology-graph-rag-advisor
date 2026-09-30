"""Start an isolated current-code HTTP server for the independent scenario evaluator."""
from __future__ import annotations

import subprocess
import sys
import threading
from http.server import HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from curriculum_assistant.graph import Graph  # noqa: E402
from curriculum_assistant.server import Handler  # noqa: E402
from generate_mock_2026_transcripts import catalog_v1  # noqa: E402


def main() -> None:
    class BoundHandler(Handler):
        pass

    server = HTTPServer(("127.0.0.1", 0), BoundHandler)
    ready = threading.Event()

    def serve() -> None:
        graph = Graph(Path(":memory:"), catalog_v1())
        BoundHandler.graph = graph
        ready.set()
        try:
            server.serve_forever()
        finally:
            graph.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    if not ready.wait(timeout=10):
        raise RuntimeError("Isolated evaluation server could not start")
    try:
        result = subprocess.run([sys.executable, str(ROOT / "scripts/evaluate_independent_scenarios.py"),
                                 "--port", str(server.server_address[1])], cwd=ROOT, check=False)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
