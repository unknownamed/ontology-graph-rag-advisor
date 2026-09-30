"""Versioned official-document and rule-set registry. No document text enters a rule automatically."""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path

DOCUMENT_TYPES = {"CURRICULUM", "ACADEMIC_REGULATION", "COURSE_EQUIVALENCE_TABLE",
                  "GRADUATION_CERTIFICATION_NOTICE", "OFFICIAL_NOTICE", "OTHER"}
AUTHORITY_STATUSES = {"AUTHORITATIVE", "NON_AUTHORITATIVE", "EVALUATION_ONLY", "USER_UPLOADED_CONTEXT"}
RELATIONS = {"SUPPLEMENTS", "CLARIFIES", "OVERRIDES", "CONFLICTS_WITH", "APPLIES_TO", "SUPERSEDES"}
EXECUTABLE_TYPES = {"MIN_CREDITS", "REQUIRED_COURSES", "ANY_COURSE", "ANY_COURSE_OR_EXEMPTION",
                    "ALL_AREAS", "CREDIT_CAP", "REQUIRED_EVIDENCE"}
CORE_DOCUMENT_ID = "CURRICULUM-2026"
CORE_SET_ID = "ADS-CE-2026-CORE"
CORE_RULESET_ID = "CRS-CE-2026-CORE"
CORE_SCOPE = {"department_id": "DEPT-COMPUTER-ENGINEERING", "credit_policy_year": 2026,
              "catalog_year": 2026, "program_types": ["SINGLE"]}


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                   separators=(",", ":")).encode("utf-8")).hexdigest()


def rule_ref(rule: dict) -> str:
    return f"{rule['rule_id']}@v{rule['rule_version']}"


def _scope_overlaps(a: dict, b: dict) -> bool:
    for field in ("department_id", "credit_policy_year", "catalog_year", "student_category"):
        if a.get(field) is not None and b.get(field) is not None and a[field] != b[field]:
            return False
    if a.get("program_types") and b.get("program_types") and not set(a["program_types"]) & set(b["program_types"]):
        return False
    return True


def scope_status(scope: dict, student: dict) -> str:
    for field in ("department_id", "credit_policy_year", "catalog_year", "student_category"):
        if scope.get(field) is not None:
            if student.get(field) is None:
                return "NEEDS_INFORMATION"
            if student[field] != scope[field]:
                return "NOT_APPLICABLE"
    if scope.get("program_types"):
        if student.get("program_type") is None:
            return "NEEDS_INFORMATION"
        if student["program_type"] not in scope["program_types"]:
            return "NOT_APPLICABLE"
    return "APPLICABLE"


def scope_applies(scope: dict, student: dict) -> bool:
    return scope_status(scope, student) != "NOT_APPLICABLE"


def core_registry(catalog: dict, source_path: str, source_hash: str) -> dict:
    """Pin the already verified curriculum PDF and rules as immutable v1 metadata."""
    document = {"document_id": CORE_DOCUMENT_ID, "title": "2026학년도 교육과정",
                "document_type": "CURRICULUM", "issuer": None, "issued_at": None,
                "effective_from": None, "effective_to": None, "revision": None,
                "source_file": source_path, "source_hash": source_hash,
                "verification_status": "VERIFIED", "authority_status": "AUTHORITATIVE",
                "ingestion_status": "VERIFIED", "authority_evidence": "PROJECT_REQUIREMENTS:CURRENT_BASELINE",
                "metadata_missing": ["issuer", "issued_at", "effective_from", "effective_to", "revision"]}
    for locator in catalog["source_locators"]:
        locator["source_document_id"] = CORE_DOCUMENT_ID
        locator["source_hash"] = source_hash
    for rule in catalog["requirements"]:
        rule["rule_version"] = 1
        rule["effective_scope"] = {"department_id": rule["department_id"],
                                   "credit_policy_year": rule["credit_policy_year"],
                                   "catalog_year": 2026,
                                   "program_types": rule.get("program_types", ["SINGLE", "MINOR", "DOUBLE"])}
        rule["source_documents"] = [CORE_DOCUMENT_ID]
        rule["supporting_evidence"] = [{"document_id": CORE_DOCUMENT_ID, "source_ref": ref}
                                       for ref in rule["source_refs"]]
        rule["supersedes"] = None
        rule["conflict_status"] = "NONE"
    catalog["authoritative_documents"] = [document]
    catalog["document_relations"] = []
    catalog["authoritative_document_set"] = {
        "set_id": CORE_SET_ID, "set_version": 1, "created_at": "2026-09-29",
        "included_documents": [CORE_DOCUMENT_ID], "excluded_documents": [],
        "effective_scope": CORE_SCOPE, "status": "VERIFIED"}
    catalog["curriculum_ruleset"] = {
        "ruleset_id": CORE_RULESET_ID, "ruleset_version": 1,
        "source_document_set_id": CORE_SET_ID, "source_document_set_version": 1,
        "created_at": "2026-09-29", "effective_scope": CORE_SCOPE,
        "included_rule_ids": sorted(r["rule_id"] for r in catalog["requirements"]),
        "unresolved_conflicts": [],
        "verification_summary": {"verified_rules": sum(r["verification_status"] == "VERIFIED"
                                                  for r in catalog["requirements"]),
                                 "unverified_rules": sum(r["verification_status"] != "VERIFIED"
                                                    for r in catalog["requirements"])},
        "status": "VERIFIED_FOR_CORE_SCOPE"}
    catalog["rule_lineage"] = []
    validate_registry(catalog)
    return catalog


def validate_registry(catalog: dict) -> None:
    documents = {d["document_id"]: d for d in catalog["authoritative_documents"]}
    document_set = catalog["authoritative_document_set"]
    ruleset = catalog["curriculum_ruleset"]
    included = set(document_set["included_documents"])
    if not included or len(included) != len(document_set["included_documents"]):
        raise ValueError("AuthoritativeDocumentSet must have unique documents")
    if any(doc not in documents or documents[doc]["authority_status"] != "AUTHORITATIVE"
           or documents[doc]["verification_status"] != "VERIFIED"
           or documents[doc]["ingestion_status"] != "VERIFIED"
           or documents[doc]["document_type"] not in DOCUMENT_TYPES for doc in included):
        raise ValueError("Only verified authoritative documents may enter the set")
    if set(document_set["excluded_documents"]) & included:
        raise ValueError("A document cannot be included and excluded")
    if (ruleset["source_document_set_id"] != document_set["set_id"] or
            ruleset["source_document_set_version"] != document_set["set_version"]):
        raise ValueError("RuleSet does not pin its document-set version")
    rules = {r["rule_id"]: r for r in catalog["requirements"]}
    if len(rules) != len(catalog["requirements"]) or set(rules) != set(ruleset["included_rule_ids"]):
        raise ValueError("RuleSet IDs differ from its immutable rule catalog")
    locators = {s["id"]: s for s in catalog["source_locators"]}
    relation_ids = set()
    for relation in catalog["document_relations"]:
        if (relation["relation_type"] not in RELATIONS or relation["relation_id"] in relation_ids
                or relation["source_document_id"] not in included
                or relation["target_document_id"] not in included
                or not relation["source_refs"] or not set(relation["source_refs"]).issubset(locators)
                or not any(locators[ref]["source_document_id"] == relation["source_document_id"]
                           for ref in relation["source_refs"])):
            raise ValueError("Document relation identity or evidence is invalid")
        relation_ids.add(relation["relation_id"])
    for locator in locators.values():
        document = documents.get(locator.get("source_document_id"))
        if (document is None or locator.get("source_hash") != document["source_hash"]
                or locator["source_document_id"] not in included):
            raise ValueError("Source locator does not match an included official document")
    for rule in rules.values():
        if rule["verification_status"] == "VERIFIED" and rule["rule_type"] not in EXECUTABLE_TYPES:
            raise ValueError("Verified rule has no deterministic evaluator")
        if not set(rule["source_documents"]).issubset(included):
            raise ValueError("Rule cites a document outside the active official set")
        if not rule["source_refs"] or not set(rule["source_refs"]).issubset(locators):
            raise ValueError("Rule source locator is missing")
        if {(e["document_id"], e["source_ref"]) for e in rule["supporting_evidence"]} != {
                (locators[ref]["source_document_id"], ref) for ref in rule["source_refs"]}:
            raise ValueError("Rule evidence does not match document locators")
    for conflict in ruleset["unresolved_conflicts"]:
        if conflict["resolution_status"] != "UNRESOLVED" or not set(conflict["source_documents"]).issubset(included):
            raise ValueError("RuleSet conflict provenance or status is invalid")


def stage_document(path: Path, *, document_id: str, title: str, document_type: str,
                   authority_status: str = "NON_AUTHORITATIVE", **metadata: object) -> dict:
    """Extract candidate text. Staging never verifies authority or publishes a rule."""
    path = Path(path).resolve()
    if "evaluation" in {part.lower() for part in path.parts}:
        raise ValueError("Evaluation materials are not official-document ingestion inputs")
    if document_type not in DOCUMENT_TYPES or authority_status not in AUTHORITY_STATUSES:
        raise ValueError("Unknown document type or authority status")
    if authority_status in {"EVALUATION_ONLY", "USER_UPLOADED_CONTEXT"}:
        raise ValueError("Non-authoritative materials cannot enter the official ingestion pipeline")
    raw = path.read_bytes()
    if path.suffix.lower() == ".pdf":
        if not raw.startswith(b"%PDF"):
            raise ValueError("Invalid PDF signature")
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            page_count = len(pdf.pages)
    elif path.suffix.lower() == ".txt":
        text, page_count = raw.decode("utf-8"), None
    else:
        raise ValueError("Official staging currently supports PDF or UTF-8 text only")
    document = {"document_id": document_id, "title": title, "document_type": document_type,
                "issuer": metadata.get("issuer"), "issued_at": metadata.get("issued_at"),
                "effective_from": metadata.get("effective_from"), "effective_to": metadata.get("effective_to"),
                "revision": metadata.get("revision"), "source_file": str(path),
                "source_hash": hashlib.sha256(raw).hexdigest(), "verification_status": "UNVERIFIED",
                "authority_status": authority_status, "ingestion_status": "EXTRACTED_PENDING_REVIEW",
                "authority_evidence": None,
                "metadata_missing": [key for key in ("issuer", "issued_at", "effective_from", "effective_to", "revision")
                                     if metadata.get(key) is None]}
    return {"document": document, "extracted_text": text, "page_count": page_count,
            "candidate_status": "REVIEW_REQUIRED", "candidate_relations": []}


def verify_staged_document(staged: dict, *, authority_evidence: str) -> dict:
    """Record an external human/source verification; never infer it from issue date or model text."""
    document = deepcopy(staged["document"])
    if document["authority_status"] != "AUTHORITATIVE" or not authority_evidence:
        raise ValueError("Explicit official authority evidence is required")
    path = Path(document["source_file"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != document["source_hash"]:
        raise ValueError("Document changed after staging")
    document.update({"verification_status": "VERIFIED", "ingestion_status": "VERIFIED",
                     "authority_evidence": authority_evidence})
    return document


def find_rule_candidates(staged: dict, catalog: dict) -> list[dict]:
    """Lexical review hints only; never classify a relation or change a verified rule."""
    text = staged["extracted_text"].casefold()
    locators = {s["id"]: s for s in catalog["source_locators"]}
    candidates = []
    for rule in catalog["requirements"]:
        titles = " ".join(locators[ref].get("title", "") for ref in rule["source_refs"] if ref in locators)
        terms = {term.casefold() for term in re.findall(r"[가-힣]{2,}|[A-Z]{3}\d{4}", titles)
                 if len(term) >= 2}
        matched = sorted(term for term in terms if term in text)
        if matched:
            candidates.append({"rule_id": rule["rule_id"], "matched_terms": matched,
                               "candidate_status": "UNVERIFIED", "relation_type": None})
    return candidates


def publish_revision(base: dict, document: dict, *, document_scope: dict,
                     relations: list[dict], new_locators: list[dict], changes: list[dict],
                     created_at: str) -> dict:
    """Build a new immutable catalog snapshot from explicitly reviewed candidates."""
    validate_registry(base)
    if document["authority_status"] != "AUTHORITATIVE" or document["verification_status"] != "VERIFIED" or document["ingestion_status"] != "VERIFIED":
        raise ValueError("Only verified official documents can be published")
    if document["document_type"] not in DOCUMENT_TYPES or not any(value is not None for value in document_scope.values()):
        raise ValueError("Document type or effective scope is not established")
    if not document.get("authority_evidence") or "evaluation" in {
            p.lower() for p in Path(document["source_file"]).resolve().parts}:
        raise ValueError("Document authority or evaluation isolation is unverified")
    if hashlib.sha256(Path(document["source_file"]).read_bytes()).hexdigest() != document["source_hash"]:
        raise ValueError("Official source file hash changed")
    result = deepcopy(base)
    old_ids = {d["document_id"] for d in result["authoritative_documents"]}
    if document["document_id"] in old_ids:
        raise ValueError("Document ID already exists; publish a separately identified revision")
    new_id = document["document_id"]
    existing_locators = {s["id"] for s in result["source_locators"]}
    for locator in new_locators:
        if (locator["id"] in existing_locators or locator["source_document_id"] != new_id
                or locator["source_hash"] != document["source_hash"]
                or locator.get("verification_status") != "VERIFIED"):
            raise ValueError("New evidence locator collides or lacks document provenance")
        if Path(document["source_file"]).suffix.lower() == ".pdf" and not locator.get("pdf_page_start"):
            raise ValueError("PDF evidence locator requires its physical page")
    result["source_locators"].extend(deepcopy(new_locators))
    locator_map = {s["id"]: s for s in result["source_locators"]}
    relation_by_type: dict[str, list[dict]] = {}
    normalized_relations = []
    for raw_relation in relations:
        relation = deepcopy(raw_relation)
        kind = relation["relation_type"]
        if kind not in RELATIONS or relation["source_document_id"] != new_id:
            raise ValueError("Unknown or mismatched document relation")
        if relation.get("verification_status") != "VERIFIED" or not relation.get("source_refs"):
            raise ValueError("Document relation lacks verified evidence")
        if not set(relation["source_refs"]).issubset(locator_map):
            raise ValueError("Document relation source locator is missing")
        if not any(locator_map[ref]["source_document_id"] == new_id for ref in relation["source_refs"]):
            raise ValueError("Document relation lacks new document evidence")
        if kind in {"SUPPLEMENTS", "CLARIFIES", "OVERRIDES", "CONFLICTS_WITH", "SUPERSEDES"} and relation["target_document_id"] not in old_ids:
            raise ValueError("Document relation points outside the previous set")
        if kind in {"OVERRIDES", "SUPERSEDES"}:
            if not (_scope_overlaps(document_scope, relation["affected_scope"])
                    and _scope_overlaps(relation["affected_scope"], result["curriculum_ruleset"]["effective_scope"])):
                raise ValueError("Override scope does not overlap the rule set")
            if not (document.get("effective_from") or document.get("revision")) or not relation.get("revision_basis"):
                raise ValueError("Override needs verified effective/revision relation, not issue order")
        relation["relation_id"] = relation.get("relation_id") or "DOCREL-" + digest({
            "kind": kind, "source": new_id, "target": relation["target_document_id"],
            "scope": relation["affected_scope"], "source_refs": relation["source_refs"]})[:16]
        relation_by_type.setdefault(kind, []).append(relation)
        normalized_relations.append(relation)

    def supports(kinds: set[str], scope: dict, previous: dict | None = None) -> bool:
        return any(_scope_overlaps(relation["affected_scope"], scope)
                   and (previous is None or relation["target_document_id"] in previous["source_documents"])
                   for kind in kinds for relation in relation_by_type.get(kind, []))
    result["authoritative_documents"].append(deepcopy(document))
    result["document_relations"].extend(normalized_relations)
    result["authoritative_document_set"]["set_version"] += 1
    result["authoritative_document_set"]["created_at"] = created_at
    result["authoritative_document_set"]["included_documents"].append(new_id)
    ruleset = result["curriculum_ruleset"]
    ruleset["ruleset_version"] += 1
    ruleset["source_document_set_version"] = result["authoritative_document_set"]["set_version"]
    ruleset["created_at"] = created_at
    by_id = {r["rule_id"]: r for r in result["requirements"]}

    def evidence(refs: list[str]) -> tuple[list[str], list[dict]]:
        if not refs or not set(refs).issubset(locator_map):
            raise ValueError("Rule change has no verified source locators")
        pairs = [{"document_id": locator_map[ref]["source_document_id"], "source_ref": ref} for ref in refs]
        return sorted({p["document_id"] for p in pairs}), pairs

    conflicts = []
    for change in changes:
        kind = change["change_type"]
        rid = change["rule_id"]
        scope = change.get("effective_scope", document_scope)
        if not _scope_overlaps(scope, document_scope):
            raise ValueError("Rule change is outside the added document's scope")
        if kind == "ADD":
            if rid in by_id or not supports({"SUPPLEMENTS"}, scope):
                raise ValueError("New requirement needs a verified SUPPLEMENTS relation")
            rule = deepcopy(change["rule"])
            if (rule["rule_id"] != rid or rule["rule_type"] not in EXECUTABLE_TYPES
                    or rule.get("verification_status") != "VERIFIED"
                    or rule.get("department_id") != scope.get("department_id")
                    or rule.get("credit_policy_year") != scope.get("credit_policy_year")
                    or set(rule.get("program_types", [])) != set(scope.get("program_types", []))):
                raise ValueError("Added rule identity or evaluator is unsupported")
            refs = rule["source_refs"]
            docs, pairs = evidence(refs)
            if new_id not in docs:
                raise ValueError("Added rule is not sourced from the new document")
            rule.update({"rule_version": 1, "effective_scope": scope, "source_documents": docs,
                         "supporting_evidence": pairs, "supersedes": None, "conflict_status": "NONE"})
            by_id[rid] = rule
            result["requirements"].append(rule)
        elif kind == "CLARIFY":
            if rid not in by_id or not supports({"CLARIFIES"}, scope, by_id.get(rid)):
                raise ValueError("Clarification needs an existing rule and verified relation")
            old = by_id[rid]
            if (scope != old["effective_scope"] or document_scope != scope
                    or not any(r["affected_scope"] == scope for r in relation_by_type["CLARIFIES"])):
                raise ValueError("Partial-scope clarification needs a separate scoped rule variant")
            refs = list(dict.fromkeys([*old["source_refs"], *change["additional_source_refs"]]))
            docs, pairs = evidence(refs)
            if new_id not in docs:
                raise ValueError("Clarification lacks new document evidence")
            updated = deepcopy(old)
            updated.update({"rule_version": old["rule_version"] + 1, "source_refs": refs,
                            "source_documents": docs, "supporting_evidence": pairs,
                            "supersedes": rule_ref(old)})
            result["requirements"][result["requirements"].index(old)] = updated
            by_id[rid] = updated
            result["rule_lineage"].append({"from": rule_ref(old), "to": rule_ref(updated),
                                           "relation": "CLARIFIES", "source_document_id": new_id})
        elif kind == "OVERRIDE":
            if rid not in by_id or not supports({"OVERRIDES", "SUPERSEDES"}, scope, by_id.get(rid)):
                raise ValueError("Override needs an existing rule and verified priority relation")
            old = by_id[rid]
            if (scope != old["effective_scope"] or document_scope != scope
                    or not any(r["affected_scope"] == scope for kind in ("OVERRIDES", "SUPERSEDES")
                               for r in relation_by_type.get(kind, []))):
                raise ValueError("Partial-scope override needs a separate scoped rule variant")
            if not _scope_overlaps(scope, old["effective_scope"]):
                raise ValueError("Override does not affect the previous rule scope")
            updated = deepcopy(old)
            replacement = deepcopy(change["replacement"])
            if any(key in replacement for key in ("rule_id", "rule_version", "verification_status")):
                raise ValueError("Replacement cannot forge rule identity or verification")
            updated.update(replacement)
            if updated["rule_type"] not in EXECUTABLE_TYPES:
                raise ValueError("Override evaluator is unsupported")
            if (updated.get("department_id") != scope.get("department_id")
                    or updated.get("credit_policy_year") != scope.get("credit_policy_year")
                    or set(updated.get("program_types", [])) != set(scope.get("program_types", []))):
                raise ValueError("Override cannot silently change a rule's executable scope")
            docs, pairs = evidence(updated["source_refs"])
            if new_id not in docs:
                raise ValueError("Override is not sourced from the new document")
            updated.update({"rule_version": old["rule_version"] + 1, "effective_scope": scope,
                            "source_documents": docs, "supporting_evidence": pairs,
                            "supersedes": rule_ref(old), "conflict_status": "NONE"})
            result["requirements"][result["requirements"].index(old)] = updated
            by_id[rid] = updated
            result["rule_lineage"].append({"from": rule_ref(old), "to": rule_ref(updated),
                                           "relation": "SUPERSEDED_BY", "source_document_id": new_id})
        elif kind == "CONFLICT":
            if rid not in by_id or not supports({"CONFLICTS_WITH"}, scope, by_id.get(rid)):
                raise ValueError("Conflict needs an existing rule and a verified conflict relation")
            old = by_id[rid]
            if not _scope_overlaps(scope, old["effective_scope"]):
                raise ValueError("Unrelated scopes do not form a rule conflict")
            refs = change["candidate_source_refs"]
            docs, _ = evidence(refs)
            if new_id not in docs:
                raise ValueError("Conflict candidate lacks source evidence")
            conflicts.append({"conflict_id": f"CONFLICT-{ruleset['ruleset_version']}-{rid}",
                              "rule_candidates": [rule_ref(old), f"{rid}@candidate:{new_id}"],
                              "affected_rule_ids": [rid], "affected_scope": scope,
                              "source_documents": sorted(set([*old["source_documents"], new_id])),
                              "source_refs": sorted(set([*old["source_refs"], *refs])),
                              "conflict_type": change.get("conflict_type", "INCOMPATIBLE_REQUIREMENT"),
                              "resolution_status": "UNRESOLVED", "resolution_basis": None})
        else:
            raise ValueError("Unknown rule change type")
    ruleset["included_rule_ids"] = sorted(by_id)
    ruleset["unresolved_conflicts"].extend(conflicts)
    ruleset["verification_summary"] = {"verified_rules": sum(r["verification_status"] == "VERIFIED" for r in by_id.values()),
                                       "unverified_rules": sum(r["verification_status"] != "VERIFIED" for r in by_id.values())}
    ruleset["status"] = "CONFLICTED" if ruleset["unresolved_conflicts"] else "VERIFIED_FOR_CORE_SCOPE"
    validate_registry(result)
    return result


class RuleSetStore:
    """Content-addressed snapshots and an atomic active pointer. Old versions are never edited."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.pointer = self.directory / "active.json"

    def _save(self, catalog: dict) -> dict:
        validate_registry(catalog)
        content = json.dumps(catalog, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        version = catalog["curriculum_ruleset"]["ruleset_version"]
        path = self.directory / f"ruleset-v{version}-{checksum[:16]}.json"
        if path.exists() and path.read_text(encoding="utf-8") != content:
            raise ValueError("Existing immutable RuleSet snapshot differs")
        if not path.exists():
            path.write_bytes(content.encode("utf-8"))
        return {"version": version, "file": path.name, "sha256": checksum}

    def initialize(self, core_catalog: dict) -> dict:
        previous_base = list(self.directory.glob("ruleset-v1-*.json"))
        if previous_base and (len(previous_base) != 1 or
                              json.loads(previous_base[0].read_text(encoding="utf-8")) != core_catalog):
            raise ValueError("Pinned v1 snapshot changed; create a new RuleSet version")
        core = self._save(core_catalog)
        if not self.pointer.exists():
            self.pointer.write_text(json.dumps(core, indent=2) + "\n", encoding="utf-8")
        current = self.load_active()
        baseline = next(d for d in current["authoritative_documents"] if d["document_id"] == CORE_DOCUMENT_ID)
        if baseline["source_hash"] != core_catalog["source_sha256"]:
            raise ValueError("Active RuleSet uses another curriculum PDF version")
        return current

    def _load(self, entry: dict) -> dict:
        path = (self.directory / entry["file"]).resolve()
        if path.parent != self.directory.resolve() or not path.is_file():
            raise ValueError("RuleSet snapshot path is invalid")
        raw = path.read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        if checksum != entry["sha256"] or not path.name.endswith(f"-{checksum[:16]}.json"):
            raise ValueError("RuleSet snapshot hash differs from active pointer")
        catalog = json.loads(raw)
        validate_registry(catalog)
        project_root = Path(__file__).resolve().parents[2]
        for document in catalog["authoritative_documents"]:
            source = Path(document["source_file"])
            source = source if source.is_absolute() else project_root / source
            if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != document["source_hash"]:
                raise ValueError(f"Official source file is missing or changed: {document['document_id']}")
        return catalog

    def load_active(self) -> dict:
        return self._load(json.loads(self.pointer.read_text(encoding="utf-8")))

    def load_version(self, version: int) -> dict:
        files = list(self.directory.glob(f"ruleset-v{version}-*.json"))
        if len(files) != 1:
            raise ValueError("RuleSet version is missing or ambiguous")
        path = files[0]
        return self._load({"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})

    def activate(self, catalog: dict) -> dict:
        current = self.load_active()
        if (catalog["curriculum_ruleset"]["ruleset_version"] != current["curriculum_ruleset"]["ruleset_version"] + 1
                or catalog["authoritative_document_set"]["set_version"] != current["authoritative_document_set"]["set_version"] + 1):
            raise ValueError("New RuleSet must directly follow the active immutable version")
        old_documents = {d["document_id"]: d for d in current["authoritative_documents"]}
        new_documents = {d["document_id"]: d for d in catalog["authoritative_documents"]}
        if (not set(old_documents).issubset(new_documents)
                or any(new_documents[did] != document for did, document in old_documents.items())):
            raise ValueError("A RuleSet revision cannot rewrite registered official documents")
        previous = {r["rule_id"]: r for r in current["requirements"]}
        revised = {r["rule_id"]: r for r in catalog["requirements"]}
        if not set(previous).issubset(revised):
            raise ValueError("A RuleSet revision cannot discard old rule identities")
        for rid, old in previous.items():
            new = revised[rid]
            if new != old and (new["rule_version"] != old["rule_version"] + 1
                               or new["supersedes"] != rule_ref(old)):
                raise ValueError("Changed rules need an explicit version lineage")
        entry = self._save(catalog)
        temporary = self.directory / "active.json.tmp"
        temporary.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.pointer)
        return catalog

    def archive_decision(self, payload: dict) -> Path:
        """Opt-in immutable local record; never archives raw StudentState automatically."""
        decision = payload["decision"]
        trace = payload["execution_trace"]
        if (decision["ruleset_id"] != trace["ruleset_id"] or
                decision["ruleset_version"] != trace["ruleset_version"] or
                decision["decision_id"] != trace["decision_id"]):
            raise ValueError("Archived decision must match its pinned execution")
        directory = self.directory / "decisions"
        directory.mkdir(exist_ok=True)
        record = {"decision": decision, "execution_trace": trace,
                  "authority": payload["authority"], "evidence": payload["evidence"]}
        raw = (json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        path = directory / f"{trace['execution_id']}-{decision['decision_id']}.json"
        if path.exists() and path.read_bytes() != raw:
            raise ValueError("Archived decision is immutable")
        if not path.exists():
            path.write_bytes(raw)
        return path


def compare_decisions(before: dict, after: dict, old_catalog: dict, new_catalog: dict) -> dict:
    """Explain a rerun with the same StudentState against two pinned RuleSets."""
    first, second = before["decision"], after["decision"]
    if first["student_state_version"] != second["student_state_version"]:
        raise ValueError("Decision comparison requires the same normalized StudentState")
    old = {r["rule_id"]: r for r in old_catalog["requirements"]}
    new = {r["rule_id"]: r for r in new_catalog["requirements"]}
    old_results = {r["rule_id"]: r["status"] for r in first["requirement_results"]}
    new_results = {r["rule_id"]: r["status"] for r in second["requirement_results"]}
    changed_rules = [rid for rid in sorted(old.keys() & new.keys()) if old[rid] != new[rid]]
    return {"from_ruleset": {"id": first["ruleset_id"], "version": first["ruleset_version"]},
            "to_ruleset": {"id": second["ruleset_id"], "version": second["ruleset_version"]},
            "added_rule_ids": sorted(new.keys() - old.keys()),
            "removed_rule_ids": sorted(old.keys() - new.keys()),
            "changed_rule_ids": changed_rules,
            "changed_requirement_results": [{"rule_id": rid, "before": old_results.get(rid), "after": new_results.get(rid)}
                                            for rid in sorted(old_results.keys() | new_results.keys())
                                            if old_results.get(rid) != new_results.get(rid)],
            "graduation_outcome_before": first["graduation_outcome"],
            "graduation_outcome_after": second["graduation_outcome"],
            "source_documents_for_changed_rules": {rid: new[rid]["source_documents"] for rid in changed_rules}}
