"""Local-only chat UI and API. Student input stays in memory for each request."""
from __future__ import annotations

import json
import base64
import binascii
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .engine import execute
from .file_extract import extract_upload, normalize_upload
from .graph import Graph
from .local_llm import express_with_local_llm, interpret_with_local_llm
from .nlp import interpret, partial_policy_query

ROOT = Path(__file__).resolve().parents[2]
PAGE = Path(__file__).parent / "web/index.html"
CURRICULUM = ROOT / "docs/curriculum/2026년도 교육과정.pdf"


def catalog_query_context() -> dict:
    """Use the verified 2026 catalog without asserting facts about a student."""
    return {"student_state_id": "CATALOG-ONLY-2026", "admission_year": None,
            "department_id": "DEPT-COMPUTER-ENGINEERING", "credit_policy_year": 2026,
            "catalog_year": 2026, "applicability_status": "VERIFIED", "program_type": "SINGLE",
            "completion_coverage": "PARTIAL", "course_attempts": []}


class Handler(BaseHTTPRequestHandler):
    graph: Graph

    def _json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path in {"/", "/index.html"}:
            body = PAGE.read_bytes()
            mime = "text/html; charset=utf-8"
        elif self.path == "/api/health":
            return self._json(200, {"status": "ok", "snapshot_id": self.graph.snapshot_id,
                                    "course_count": len(self.graph.catalog["courses"])})
        elif self.path == "/curriculum.pdf":
            body = CURRICULUM.read_bytes()
            mime = "application/pdf"
        else:
            return self._json(404, {"error": "NOT_FOUND"})
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path not in {"/api/query", "/api/extract", "/api/normalize-upload"}:
            return self._json(404, {"error": "NOT_FOUND"})
        if "application/json" not in self.headers.get("Content-Type", ""):
            return self._json(415, {"error": "JSON_REQUIRED"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            limit = 14_000_000 if self.path in {"/api/extract", "/api/normalize-upload"} else 2_000_000
            if not 0 < size <= limit:
                return self._json(413, {"error": "INPUT_SIZE_LIMIT"})
            request = json.loads(self.rfile.read(size).decode("utf-8"))
            if self.path in {"/api/extract", "/api/normalize-upload"}:
                encoded = request["content_base64"]
                if not isinstance(encoded, str) or len(encoded) > 13_400_000:
                    raise ValueError("File data exceeds the upload limit")
                try:
                    file_bytes = base64.b64decode(encoded, validate=True)
                except binascii.Error as exc:
                    raise ValueError("Invalid base64 upload") from exc
                extracted = extract_upload(request["filename"], file_bytes, self.graph.catalog)
                if self.path == "/api/extract":
                    return self._json(200, extracted)
                if request.get("source_id") != extracted["source_id"]:
                    raise ValueError("Upload source hash changed between extraction and review")
                return self._json(200, normalize_upload(extracted, request["review"], self.graph.catalog))
            state = request.get("student_state")
            if "structured_query" in request:
                parsed = None
                query = request["structured_query"]
            else:
                parser = interpret_with_local_llm if request.get("use_local_llm", True) else interpret
                parsed = parser(request["utterance"], self.graph.catalog, request.get("context"))
                query = parsed["structured_query"]
            if query is None:
                return self._json(200, {"interpretation": parsed,
                                        "answer_text": "질문에서 과목이나 의도를 확정할 수 없습니다. 표현을 더 구체적으로 알려 주세요."})
            if state is None:
                if query["intent"] not in {"COURSE_LOOKUP", "POLICY_LOOKUP", "CATALOG_AGGREGATE", "ENTITY_CHECK", "PLACEMENT_LOOKUP"}:
                    fallback = partial_policy_query(request.get("utterance", "")) if parsed is not None else None
                    if fallback is None:
                        raise ValueError("StudentState is required for personal credit and graduation decisions")
                    parsed = {**parsed, "personal_intent_without_state": query["intent"],
                              "structured_query": fallback}
                    query = fallback
                state = catalog_query_context()
            payload = execute(self.graph, state, query)
            if request.get("use_local_llm", True):
                payload = express_with_local_llm(payload)
            if parsed is not None:
                payload["interpretation"] = parsed
            from .verifier import verify_payload
            verify_payload(payload)
            return self._json(200, payload)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            return self._json(400, {"error": "INVALID_INPUT", "detail": str(error)})

    def log_message(self, format: str, *args: object) -> None:
        # Avoid recording student input in request logs.
        return


def serve(graph: Graph, port: int = 8765) -> None:
    class BoundHandler(Handler):
        pass
    BoundHandler.graph = graph
    server = HTTPServer(("127.0.0.1", port), BoundHandler)
    print(f"Local curriculum assistant: http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
