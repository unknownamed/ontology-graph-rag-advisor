"""Extract an official-document candidate for review; never publish rules here."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from build_catalog import build  # noqa: E402
from curriculum_assistant.authority import (DOCUMENT_TYPES, RuleSetStore,
                                            find_rule_candidates, stage_document)  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--type", choices=sorted(DOCUMENT_TYPES), required=True)
    parser.add_argument("--issuer")
    parser.add_argument("--issued-at")
    parser.add_argument("--effective-from")
    parser.add_argument("--effective-to")
    parser.add_argument("--revision")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    staged = stage_document(args.file, document_id=args.id, title=args.title,
                            document_type=args.type, authority_status="AUTHORITATIVE",
                            issuer=args.issuer, issued_at=args.issued_at,
                            effective_from=args.effective_from, effective_to=args.effective_to,
                            revision=args.revision)
    current = RuleSetStore(ROOT / "data/processed/ruleset_versions").initialize(build())
    staged["candidate_relations"] = find_rule_candidates(staged, current)
    destination = args.output or ROOT / "data/raw/authority_staging" / f"{args.id}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise SystemExit("Staging file exists; choose a new document ID or output path")
    destination.write_text(json.dumps(staged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Staged {args.id}: {staged['page_count']} pages; REVIEW_REQUIRED; {destination}")


if __name__ == "__main__":
    main()
