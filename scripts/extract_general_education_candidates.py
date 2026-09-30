"""Extract unverified 2026 general-education table candidates for review.

Automatic table extraction alone does not make a curriculum fact VERIFIED.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]


def extract() -> list[dict]:
    index = json.loads((ROOT / "data/processed/source_index.json").read_text(encoding="utf-8"))
    pdf_path = ROOT / index["source"]["path"]
    if hashlib.sha256(pdf_path.read_bytes()).hexdigest() != index["source"]["sha256"]:
        raise ValueError("Curriculum source hash changed")
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_no in range(34, 46):
            for table in pdf.pages[page_no - 1].extract_tables():
                for row in table:
                    if len(row) < 11 or not row[2] or not re.fullmatch(r"GEA\d{4}", row[2]):
                        continue
                    try:
                        credits = int(row[5])
                    except (TypeError, ValueError):
                        raise ValueError(f"Unparseable credit value at page {page_no}: {row[:6]}")
                    rows.append({"course_id": row[2], "name": (row[3] or "").replace("\n", ""),
                                 "catalog_credits": credits,
                                 "classification": (row[0] or "").replace("\n", ""),
                                 "area": (row[1] or "").replace("\n", ""),
                                 "source": {"document_id": "CURRICULUM-2026", "pdf_page": page_no,
                                            "printed_page": page_no - 8, "section": "02장 2-2 교양 교과목",
                                            "table": "T-GE-2026-COURSES"},
                                 "verification_status": "UNVERIFIED"})
    if len(rows) != 282:
        raise ValueError(f"Expected 282 table candidates; found {len(rows)}")
    counts = Counter(r["course_id"] for r in rows)
    for row in rows:
        if counts[row["course_id"]] > 1:
            row["verification_status"] = "CONFLICTED"
    output = ROOT / "data/raw/general_education_candidates.json"
    output.write_text(json.dumps({"source_sha256": index["source"]["sha256"],
                                  "extraction_status": "UNVERIFIED_EXCEPT_EXPLICIT_CONFLICTS",
                                  "rows": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rows


if __name__ == "__main__":
    result = extract()
    print(f"Extracted {len(result)} candidates; conflict rows: {sum(r['verification_status'] == 'CONFLICTED' for r in result)}")
