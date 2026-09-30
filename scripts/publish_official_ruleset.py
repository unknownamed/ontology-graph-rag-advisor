"""Publish a separately reviewed official document and immutable RuleSet revision."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from build_catalog import build  # noqa: E402
from curriculum_assistant.authority import RuleSetStore, publish_revision, verify_staged_document  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review", type=Path, required=True,
                        help="Reviewed JSON with staged_file, authority_evidence, scope, relations, locators and changes")
    args = parser.parse_args()
    review = json.loads(args.review.read_text(encoding="utf-8"))
    staged = json.loads(Path(review["staged_file"]).read_text(encoding="utf-8"))
    document = verify_staged_document(staged, authority_evidence=review["authority_evidence"])
    store = RuleSetStore(ROOT / "data/processed/ruleset_versions")
    active = store.initialize(build())
    revised = publish_revision(active, document, document_scope=review["document_scope"],
                               relations=review["relations"], new_locators=review["source_locators"],
                               changes=review["rule_changes"], created_at=review["created_at"])
    store.activate(revised)
    print(f"Activated {revised['curriculum_ruleset']['ruleset_id']} v{revised['curriculum_ruleset']['ruleset_version']}; "
          "restart the local server for subsequent decisions")


if __name__ == "__main__":
    main()
