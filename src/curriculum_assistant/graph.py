"""Small persisted property graph with allowlisted, parameterized queries."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from .remaining import satisfaction_basis
from .placement import normalize_placement


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Graph:
    def __init__(self, path: Path, catalog: dict):
        self.path = path
        self.catalog = catalog
        self.snapshot_id = hashlib.sha256(canonical(catalog).encode()).hexdigest()
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        try:
            self._initialize()
        except Exception:
            self.db.close()
            raise

    def _initialize(self) -> None:
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS nodes(
              id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
              verification_status TEXT NOT NULL, source_refs TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS edges(
              id TEXT PRIMARY KEY, kind TEXT NOT NULL, src TEXT NOT NULL,
              dst TEXT NOT NULL, payload TEXT NOT NULL, source_refs TEXT NOT NULL,
              FOREIGN KEY(src) REFERENCES nodes(id), FOREIGN KEY(dst) REFERENCES nodes(id));
            CREATE INDEX IF NOT EXISTS edges_src_kind ON edges(src,kind);
        """)
        old = self.db.execute("SELECT payload FROM nodes WHERE id='CURRICULUM-CE-2026'").fetchone()
        if old:
            if json.loads(old["payload"])["snapshot_id"] != self.snapshot_id:
                raise ValueError("Graph snapshot collision; choose a new database path")
            self._ensure_satisfaction_edges(migrate_legacy=True)
            self._verify_integrity()
            return
        def node(id: str, kind: str, payload: dict, refs: list[str], status: str = "VERIFIED") -> None:
            self.db.execute("INSERT INTO nodes VALUES (?,?,?,?,?)", (id, kind, canonical(payload), status, canonical(refs)))
        def edge(id: str, kind: str, src: str, dst: str, refs: list[str], payload: dict | None = None) -> None:
            self.db.execute("INSERT INTO edges VALUES (?,?,?,?,?,?)", (id, kind, src, dst, canonical(payload or {}), canonical(refs)))
        dept = self.catalog["department"]
        curr = self.catalog["curriculum"]
        node(dept["department_id"], "Department", dept, [dept["source_ref"]])
        node(curr["curriculum_id"], "CurriculumVersion", {**curr, "snapshot_id": self.snapshot_id}, ["CE-COURSES"])
        edge("E-CE-2026-DEPT", "HAS_CURRICULUM", dept["department_id"], curr["curriculum_id"], ["CE-SECTION"])
        for course in self.catalog["courses"]:
            cid = course["course_id"]
            entry = f"ENTRY-CE-2026-{cid}"
            cls = f"CLASS-CE-2026-{cid}"
            refs = [course["fact_id"]]
            status = course["verification_status"]
            node(cid, "Course", {"course_id": cid, "name": course["name"]}, refs, status)
            node(entry, "CatalogEntry", {"catalog_credits": course["catalog_credits"], "grade_term": course.get("grade_term"),
                                         "placement_term_raw": course.get("placement_term_raw"),
                                         "placement_verification_status": course.get("placement_verification_status", status),
                                         "minor_required": course.get("minor_required", False), "general_area": course.get("general_area"),
                                         "eligible_scope": course.get("eligible_scope", "GENERAL"),
                                         "source": course["source"], "fact_id": course["fact_id"]}, refs, status)
            node(cls, "CourseClassification", {"classification": course["classification"], "curriculum_id": curr["curriculum_id"]}, refs, status)
            edge(f"E-CURR-{cid}", "HAS_ENTRY", curr["curriculum_id"], entry, refs)
            edge(f"E-ENTRY-{cid}", "FOR_COURSE", entry, cid, refs)
            edge(f"E-CLASS-{cid}", "CLASSIFIED_AS", entry, cls, refs)
        for rule in self.catalog["requirements"]:
            rid = rule["rule_id"]
            node(rid, "Requirement", rule, rule["source_refs"], rule["verification_status"])
            edge(f"E-REQ-{rid}", "HAS_REQUIREMENT", curr["curriculum_id"], rid, rule["source_refs"])
        for fact in self.catalog.get("policy_facts", []):
            fid = fact["policy_fact_id"]
            node(fid, "PolicyFact", fact, fact["source_refs"], fact["verification_status"])
            edge(f"E-POLICY-{fid}", "HAS_POLICY_FACT", curr["curriculum_id"], fid, fact["source_refs"])
        for fact in self.catalog.get("historical_credit_rows", []):
            cid, fid = fact["curriculum_id"], fact["policy_fact_id"]
            node(cid, "CurriculumVersion", {"curriculum_id": cid, "year": fact["entry_year"],
                                              "snapshot_id": self.snapshot_id}, fact["source_refs"])
            edge(f"E-CE-HISTORICAL-{fact['entry_year']}", "HAS_CURRICULUM", dept["department_id"], cid, fact["source_refs"])
            node(fid, "PolicyFact", fact, fact["source_refs"], fact["verification_status"])
            edge(f"E-POLICY-{fid}", "HAS_POLICY_FACT", cid, fid, fact["source_refs"])
        self.db.commit()
        self._ensure_satisfaction_edges(migrate_legacy=False)
        self._verify_integrity()

    def _expected_satisfaction_edges(self) -> list[tuple[str, str, str, str, str, str]]:
        edges = []
        for course in self.catalog["courses"]:
            if course.get("eligible_scope", "GENERAL") != "GENERAL":
                continue
            for rule in self.catalog["requirements"]:
                basis = satisfaction_basis(course, rule)
                if basis:
                    cid, rid = course["course_id"], rule["rule_id"]
                    edges.append((f"E-SAT-{cid}-{rid}", "SATISFIES", f"ENTRY-CE-2026-{cid}", rid,
                                  canonical({"course_id": cid, "basis": basis}),
                                  canonical([course["fact_id"], *rule["source_refs"]])))
        return edges

    def _ensure_satisfaction_edges(self, *, migrate_legacy: bool) -> None:
        expected = self._expected_satisfaction_edges()
        count = self.db.execute("SELECT COUNT(*) FROM edges WHERE kind='SATISFIES'").fetchone()[0]
        if migrate_legacy and count not in {0, len(expected)}:
            raise ValueError("Partial SATISFIES graph cannot be silently repaired")
        if count == 0:
            self.db.executemany("INSERT INTO edges VALUES (?,?,?,?,?,?)", expected)
            self.db.commit()

    def _verify_integrity(self) -> None:
        historical_count = len(self.catalog.get("historical_credit_rows", []))
        expected_nodes = 2 + 3 * len(self.catalog["courses"]) + len(self.catalog["requirements"]) + len(self.catalog.get("policy_facts", [])) + 2 * historical_count
        expected_edges = (1 + 3 * len(self.catalog["courses"]) + len(self.catalog["requirements"])
                          + len(self.catalog.get("policy_facts", [])) + 2 * historical_count
                          + len(self._expected_satisfaction_edges()))
        nodes = self.db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edges = self.db.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        if (nodes, edges) != (expected_nodes, expected_edges):
            raise ValueError("Graph node/edge count differs from the verified catalog snapshot")
        if self.db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite graph integrity check failed")

    def close(self) -> None:
        self.db.close()

    def query(self, op: str, *, curriculum_id: str, course_id: str | None = None,
              topic: str | None = None, rule_ids: list[str] | None = None,
              classifications: list[str] | None = None,
              course_ids: list[str] | None = None) -> dict | list[dict] | None:
        if op not in {"FETCH_CATALOG_ENTRY", "FETCH_CATALOG_SET", "FETCH_REQUIREMENTS", "FETCH_POLICY_FACTS",
                      "FETCH_COURSE_REQUIREMENT_LINKS"}:
            raise ValueError(f"Query operation is not allowlisted: {op}")
        historical_ids = {r["curriculum_id"] for r in self.catalog.get("historical_credit_rows", [])}
        if curriculum_id != "CURRICULUM-CE-2026" and not (op == "FETCH_POLICY_FACTS" and curriculum_id in historical_ids):
            return None if op == "FETCH_CATALOG_ENTRY" else []
        if op == "FETCH_CATALOG_SET":
            allowed = {"MAJOR_REQUIRED", "MAJOR_ELECTIVE", "GENERAL_BASIC", "GENERAL_BALANCED", "GENERAL_EXPANDED"}
            if not classifications or not set(classifications).issubset(allowed):
                raise ValueError("Catalog classification filter is not allowlisted")
            marks = ",".join("?" for _ in classifications)
            rows = self.db.execute(f"""
                SELECT c.id FROM edges ce
                JOIN nodes en ON en.id=ce.dst
                JOIN edges ec ON ec.src=en.id AND ec.kind='FOR_COURSE'
                JOIN nodes c ON c.id=ec.dst
                JOIN edges ecl ON ecl.src=en.id AND ecl.kind='CLASSIFIED_AS'
                JOIN nodes cl ON cl.id=ecl.dst
                WHERE ce.src=? AND ce.kind='HAS_ENTRY'
                  AND en.verification_status='VERIFIED' AND cl.verification_status='VERIFIED'
                  AND json_extract(cl.payload,'$.classification') IN ({marks})
                ORDER BY c.id
            """, (curriculum_id, *classifications)).fetchall()
            return [self.query("FETCH_CATALOG_ENTRY", curriculum_id=curriculum_id,
                               course_id=row["id"]) for row in rows]
        if op == "FETCH_COURSE_REQUIREMENT_LINKS":
            known_courses = {course["course_id"] for course in self.catalog["courses"]}
            known_rules = {rule["rule_id"] for rule in self.catalog["requirements"]}
            if (not isinstance(course_ids, list) or not isinstance(rule_ids, list)
                    or len(course_ids) > 1000 or len(rule_ids) > 100
                    or not set(course_ids).issubset(known_courses) or not set(rule_ids).issubset(known_rules)):
                raise ValueError("Candidate link filters must contain bounded, known IDs")
            if not course_ids or not rule_ids:
                return []
            courses_sql = ",".join("?" for _ in course_ids)
            rules_sql = ",".join("?" for _ in rule_ids)
            rows = self.db.execute(f"""
                SELECT id,src,dst,payload,source_refs FROM edges
                WHERE kind='SATISFIES' AND src IN ({courses_sql}) AND dst IN ({rules_sql})
                ORDER BY id
            """, (*[f"ENTRY-CE-2026-{code}" for code in course_ids], *rule_ids)).fetchall()
            return [{"relationship_id": row["id"], "entry_id": row["src"], "rule_id": row["dst"],
                     **json.loads(row["payload"]), "source_refs": json.loads(row["source_refs"]),
                     "relationship_detail": {"id": row["id"], "kind": "SATISFIES",
                                             "src": row["src"], "dst": row["dst"]}} for row in rows]
        if op == "FETCH_CATALOG_ENTRY":
            if not course_id:
                raise ValueError("course_id required")
            row = self.db.execute("""
                SELECT c.id course_id,c.payload course_payload,en.id entry_id,en.payload entry_payload,
                       en.verification_status entry_status,cl.verification_status classification_status,
                       cl.id classification_id,cl.payload classification_payload,
                       ce.id catalog_edge_id, ec.id course_edge_id, ecl.id classification_edge_id
                FROM edges ce JOIN nodes en ON en.id=ce.dst
                JOIN edges ec ON ec.src=en.id AND ec.kind='FOR_COURSE'
                JOIN nodes c ON c.id=ec.dst
                JOIN edges ecl ON ecl.src=en.id AND ecl.kind='CLASSIFIED_AS'
                JOIN nodes cl ON cl.id=ecl.dst
                WHERE ce.src=? AND ce.kind='HAS_ENTRY' AND c.id=?
            """, (curriculum_id, course_id)).fetchone()
            if not row:
                return None
            result = {"course_id": row["course_id"], "name": json.loads(row["course_payload"])["name"],
                    "curriculum_id": curriculum_id,
                    "entry_id": row["entry_id"], "classification_id": row["classification_id"],
                    "verification_status": row["entry_status"], "classification_verification_status": row["classification_status"],
                    "classification": json.loads(row["classification_payload"])["classification"],
                    **json.loads(row["entry_payload"]),
                    "relationship_ids": [row["catalog_edge_id"], row["course_edge_id"], row["classification_edge_id"]],
                    "relationship_details": [
                        {"id": row["catalog_edge_id"], "kind": "HAS_ENTRY", "src": curriculum_id, "dst": row["entry_id"]},
                        {"id": row["course_edge_id"], "kind": "FOR_COURSE", "src": row["entry_id"], "dst": row["course_id"]},
                        {"id": row["classification_edge_id"], "kind": "CLASSIFIED_AS", "src": row["entry_id"], "dst": row["classification_id"]},
                    ]}
            result["curriculum_placement"] = normalize_placement(result)
            return result
        if op == "FETCH_REQUIREMENTS":
            if rule_ids is not None and not set(rule_ids).issubset({r["rule_id"] for r in self.catalog["requirements"]}):
                raise ValueError("Requirement filter contains an unknown rule")
            rows = self.db.execute("""
                SELECT n.payload, e.id edge_id FROM edges e JOIN nodes n ON n.id=e.dst
                WHERE e.src=? AND e.kind='HAS_REQUIREMENT' ORDER BY n.id
            """, (curriculum_id,)).fetchall()
            return [{**json.loads(r["payload"]), "relationship_id": r["edge_id"],
                     "relationship_detail": {"id": r["edge_id"], "kind": "HAS_REQUIREMENT", "src": curriculum_id,
                                             "dst": json.loads(r["payload"])["rule_id"]}} for r in rows
                    if rule_ids is None or json.loads(r["payload"])["rule_id"] in rule_ids]
        if op == "FETCH_POLICY_FACTS":
            if topic not in {"APPLICABILITY", "FREE_CHOICE", "EQUIVALENCE", "RECOMMENDATIONS", "TRANSITION", "MULTI_PROGRAM", "HISTORICAL_CREDITS", "GENERAL_CREDITS", "GENERAL_AREAS"}:
                raise ValueError("Policy topic is not allowlisted")
            rows = self.db.execute("""
                SELECT n.payload, e.id edge_id FROM edges e JOIN nodes n ON n.id=e.dst
                WHERE e.src=? AND e.kind='HAS_POLICY_FACT' AND json_extract(n.payload,'$.topic')=?
                ORDER BY n.id
            """, (curriculum_id, topic)).fetchall()
            return [{**json.loads(r["payload"]), "relationship_id": r["edge_id"],
                     "relationship_detail": {"id": r["edge_id"], "kind": "HAS_POLICY_FACT", "src": curriculum_id,
                                             "dst": json.loads(r["payload"])["policy_fact_id"]}} for r in rows]
        raise ValueError(f"Query operation is not allowlisted: {op}")
