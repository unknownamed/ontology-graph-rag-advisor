"""Deterministic remaining requirements and catalog candidates for the pinned RuleSet."""
from __future__ import annotations

from collections import defaultdict


def satisfaction_basis(course: dict, rule: dict) -> str | None:
    """Return the verified Rule IR relationship a catalog row can contribute to."""
    if course.get("verification_status") != "VERIFIED" or rule.get("verification_status") != "VERIFIED":
        return None
    classification = course["classification"]
    code = course["course_id"]
    kind = rule["rule_type"]
    if kind == "REQUIRED_COURSES" and code in rule["course_ids"]:
        return "REQUIRED_COURSE"
    if kind in {"ANY_COURSE", "ANY_COURSE_OR_EXEMPTION"} and code in rule["course_ids"]:
        return "COURSE_GROUP_OPTION"
    if kind == "ALL_AREAS" and classification == "GENERAL_BALANCED" and course.get("general_area") in rule["areas"]:
        return "GENERAL_AREA"
    if kind != "MIN_CREDITS" or course["catalog_credits"] <= 0:
        return None
    area = rule["area"]
    if area == "GRADUATION_TOTAL" and classification.startswith(("MAJOR_", "GENERAL_")):
        return "GRADUATION_CREDIT"
    if area in {"MAJOR_TOTAL", "MAJOR_ADVANCED"} and classification.startswith("MAJOR_"):
        return "MAJOR_CREDIT"
    if area == "GENERAL_TOTAL" and classification.startswith("GENERAL_"):
        return "GENERAL_CREDIT"
    if classification == area:
        return "AREA_CREDIT"
    return None


def summarize_remaining(decision: dict, rules: list[dict]) -> dict:
    """Project the executed RequirementResults; never recalculate rule outcomes."""
    by_rule = {rule["rule_id"]: rule for rule in rules}
    results = decision["requirement_results"]
    groups: dict[str, list[str]] = defaultdict(list)
    progress = {}
    missing_credits = {}
    other_required = []
    for result in results:
        rid = result["rule_id"]
        rule = by_rule[rid]
        if result["status"] == "NOT_APPLICABLE":
            continue
        group = "MAJOR" if rid.startswith("R-CE-") else "GENERAL" if rid.startswith("R-GE-") else "GRADUATION"
        if result["status"] != "SATISFIED":
            groups[group].append(rid)
        if rule["rule_type"] == "MIN_CREDITS":
            progress[rule["area"]] = {"current": result["observed"], "required": result["required"],
                                      "status": result["status"], "rule_id": rid,
                                      "is_lower_bound": result["status"] == "NEEDS_INFORMATION"}
            missing_credits[rule["area"]] = result["missing_amount"]
        elif rule["rule_type"] == "REQUIRED_COURSES":
            progress["MAJOR_REQUIRED_COURSES"] = {"current": result["observed"],
                                                  "required": result["required"], "status": result["status"],
                                                  "rule_id": rid,
                                                  "is_lower_bound": result["status"] == "NEEDS_INFORMATION"}
        elif rule["rule_type"] == "REQUIRED_EVIDENCE" and result["status"] != "SATISFIED":
            other_required.append(rid)
    required = next((r for r in results if by_rule[r["rule_id"]]["rule_type"] == "REQUIRED_COURSES"
                     and r["status"] != "NOT_APPLICABLE"), None)
    return {"satisfied_requirements": sorted(r["rule_id"] for r in results if r["status"] == "SATISFIED"),
            "unsatisfied_requirements": sorted(r["rule_id"] for r in results if r["status"] == "UNSATISFIED"),
            "needs_information": sorted(r["rule_id"] for r in results if r["status"] == "NEEDS_INFORMATION"),
            "not_applicable_requirements": sorted(r["rule_id"] for r in results if r["status"] == "NOT_APPLICABLE"),
            "missing_credits_by_category": missing_credits,
            "missing_required_courses": required["missing_course_ids"] if required else None,
            "remaining_requirement_groups": {key: sorted(value) for key, value in sorted(groups.items())},
            "other_required_requirements": sorted(other_required), "progress": progress,
            "student_information_needed": decision["needs_information"]}


def candidate_courses(decision: dict, rules: list[dict], entries: list[dict], links: list[dict],
                      focus: str | None = None) -> list[dict]:
    """Classify queried catalog rows using only confirmed unmet rules and returned graph edges."""
    by_rule = {rule["rule_id"]: rule for rule in rules}
    unmet = {r["rule_id"] for r in decision["requirement_results"] if r["status"] == "UNSATISFIED"}
    completed = {item["course_id"] for item in decision["recognitions"]}
    observed_areas = {item.get("general_area") for item in decision["recognitions"]}
    missing_required = set(decision.get("missing_courses") or [])
    general_cap = next((r["required_value"] for r in rules if r["rule_type"] == "CREDIT_CAP"
                        and r.get("area") == "GENERAL_TOTAL" and r["verification_status"] == "VERIFIED"), None)
    general_counted = decision["credited_amount"]["by_area"].get("GENERAL_TOTAL")
    links_by_entry: dict[str, list[dict]] = defaultdict(list)
    for link in links:
        links_by_entry[link["entry_id"]].append(link)
    candidates = []
    for entry in entries:
        code = entry["course_id"]
        applicable = entry["verification_status"] == "VERIFIED" and entry["classification_verification_status"] == "VERIFIED"
        applicable &= entry.get("eligible_scope") == "GENERAL"
        linked = []
        if applicable and code not in completed:
            for link in links_by_entry[entry["entry_id"]]:
                rid = link["rule_id"]
                if rid not in unmet:
                    continue
                rule = by_rule[rid]
                if rule["rule_type"] == "ALL_AREAS" and entry.get("general_area") in observed_areas:
                    continue
                if (rule.get("area") == "GRADUATION_TOTAL" and entry["classification"].startswith("GENERAL_")
                        and general_cap is not None and general_counted is not None and general_counted >= general_cap):
                    continue
                linked.append(link)
        if code in completed:
            status = "ALREADY_COMPLETED"
        elif code in missing_required and any(link["rule_id"] in unmet for link in linked):
            status = "REQUIRED"
        elif linked:
            status = "ELIGIBLE_OPTION"
        else:
            status = "NOT_APPLICABLE"
        if focus == "MAJOR" and not entry["classification"].startswith("MAJOR_"):
            continue
        if focus == "GENERAL" and not entry["classification"].startswith("GENERAL_"):
            continue
        if focus == "MAJOR_REQUIRED" and entry["classification"] != "MAJOR_REQUIRED":
            continue
        candidates.append({"course_id": code, "course_name": entry["name"],
                           "credits": entry["catalog_credits"],
                           "grade_term": entry.get("grade_term"),
                           "curriculum_placement": entry["curriculum_placement"],
                           "course_classification": entry["classification"],
                           "candidate_status": status, "already_completed": code in completed,
                           "satisfies_requirement_ids": sorted({link["rule_id"] for link in linked}),
                           "relationship_ids": sorted({link["relationship_id"] for link in linked}),
                           "provenance": {"source_document_id": entry["source"]["document_id"],
                                          "source": entry["source"], "fact_id": entry["fact_id"],
                                          "entry_id": entry["entry_id"],
                                          "rule_source_refs": {link["rule_id"]: by_rule[link["rule_id"]]["source_refs"]
                                                               for link in linked}},
                           "next_term_offering_status": "NOT_VERIFIED",
                           "student_eligibility_status": "NOT_VERIFIED",
                           "prerequisite_status": "NOT_VERIFIED"})
    return sorted(candidates, key=lambda c: ({"REQUIRED": 0, "ELIGIBLE_OPTION": 1,
                                             "ALREADY_COMPLETED": 2, "NOT_APPLICABLE": 3}[c["candidate_status"]],
                                            c["course_id"]))
