"""Version visually checked PDF placement cells; executable rules stay unchanged."""
from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from curriculum_assistant.authority import RuleSetStore

CHECKED = ROOT / "data/processed/curriculum_placement_2026.json"


def refined_catalog(catalog: dict) -> dict:
    cells = json.loads(CHECKED.read_text(encoding="utf-8"))
    pdf = ROOT / "docs/curriculum/2026년도 교육과정.pdf"
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != cells["source_sha256"] or cells["source_sha256"] != catalog["source_sha256"]:
        raise ValueError("Placement source PDF hash changed")
    rows = {row["course_id"]: row for row in cells["rows"]}
    if len(rows) != len(cells["rows"]):
        raise ValueError("Reviewed placement cells must have unique catalog identities")
    result = deepcopy(catalog)
    for course in result["courses"]:
        if course["course_id"] not in rows:
            continue
        row = rows.pop(course["course_id"])
        if (course["source"]["pdf_page"] != row["pdf_page"] or
                course["source"]["printed_page"] != row["printed_page"] or
                course["verification_status"] != row["verification_status"]):
            raise ValueError("Reviewed placement source/scope does not match catalog row")
        course["placement_term_raw"] = row["raw_term"]
        course["placement_verification_status"] = row["verification_status"]
    if rows:
        raise ValueError("Placement source cannot create new courses")
    ruleset = result["curriculum_ruleset"]
    ruleset["ruleset_version"] += 1
    ruleset["created_at"] = "2026-10-01"
    ruleset["verification_summary"]["placement_raw_cells_visually_checked"] = len(cells["rows"])
    return result


def main() -> None:
    store = RuleSetStore(ROOT / "data/processed/ruleset_versions")
    catalog = store.load_active()
    if all("placement_term_raw" in c for c in catalog["courses"] if c["classification"].startswith("GENERAL_")):
        print("Already migrated; immutable snapshots unchanged")
        return
    result = store.activate_placement_refinement(refined_catalog(catalog))
    print("Placement catalog refinement:", result["curriculum_ruleset"]["ruleset_version"], "(rules and document set unchanged)")


if __name__ == "__main__":
    main()
