"""One-time reviewed migration: facts verified in the existing official PDF.

The v1 document set and executable graduation rules are preserved. No
evaluation or user-uploaded document is read by this script.
"""
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from curriculum_assistant.authority import RuleSetStore, validate_registry  # noqa: E402


def refined_catalog(base: dict) -> dict:
    validate_registry(base)
    if base["curriculum_ruleset"]["ruleset_version"] != 1:
        raise ValueError("This reviewed PDF refinement starts from RuleSet v1")
    result = deepcopy(base)
    additions = [
        {"policy_fact_id": "PF-GE-2026-EXCEPTIONS", "topic": "GENERAL_AREAS",
         "predicate": "GENERAL_AREA_APPLICABILITY_EXCEPTIONS",
         "value": {"general_obligation_exempt": ["TRANSFER"],
                   "area_minimum_exempt": ["NIGHT", "EMPLOYED_ADULT", "CONTRACT"],
                   "reduced_total_minimum_categories": ["TEACHER", "NURSING", "NIGHT", "EMPLOYED_ADULT", "CONTRACT"],
                   "reduced_total_minimum": 26},
         "source_refs": ["GE-RULES-2026"]},
        {"policy_fact_id": "PF-GE-2026-CAP-TREATMENT", "topic": "GENERAL_CREDITS",
         "predicate": "GENERAL_CAP_EXCESS_TREATMENT",
         "value": {"earned_total_counts": True, "grade_counts": True,
                   "graduation_total_counts": False, "residual_counts": False},
         "source_refs": ["GE-RULES-2026"]},
    ]
    for fact in additions:
        fact.update({"department_id": "DEPT-COMPUTER-ENGINEERING",
                     "verification_status": "VERIFIED"})
    result["policy_facts"].extend(additions)
    result["curriculum_ruleset"]["ruleset_version"] = 2
    result["curriculum_ruleset"]["created_at"] = "2026-09-30"
    result["curriculum_ruleset"]["verification_summary"]["verified_policy_facts"] = len(result["policy_facts"])
    validate_registry(result)
    return result


def main() -> None:
    store = RuleSetStore(ROOT / "data/processed/ruleset_versions")
    current = store.load_active()
    if current["curriculum_ruleset"]["ruleset_version"] == 2:
        print("Source refinement v2 already active")
        return
    store.activate_source_refinement(refined_catalog(current))
    print("Activated source-backed policy refinement: CRS-CE-2026-CORE v2; ADS v1 unchanged")


if __name__ == "__main__":
    main()
