"""Promote only manually checked PDF table rows to runtime catalog facts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/general_education_candidates.json"
OUTPUT = ROOT / "data/processed/general_education_2026.json"

# Critical prerequisite and CE-recommended rows independently transcribed from the rendered pages.
CHECKED = {
    "GEA8001": ("대학생활의설계(CDP-C)", 1, 34, "기초교양", "미래설계"),
    "GEA8810": ("인공지능시대의파이썬프로그래밍", 3, 34, "기초교양", "AI융합기초"),
    "GEA8811": ("인문사회계열을위한인공지능입문", 3, 34, "기초교양", "AI융합기초"),
    "GEA8812": ("자연공학계열을위한인공지능입문", 3, 34, "기초교양", "AI융합기초"),
    "GEA8813": ("인공지능데이터활용기초", 3, 34, "기초교양", "AI융합기초"),
    "GEA8814": ("인공지능과디지털사회", 3, 34, "기초교양", "AI융합기초"),
    "GEA8510": ("인문학글쓰기", 3, 34, "기초교양", "열린사고와표현"),
    "GEA8511": ("사회과학글쓰기", 3, 34, "기초교양", "열린사고와표현"),
    "GEA8512": ("과학기술글쓰기", 3, 34, "기초교양", "열린사고와표현"),
    "GEA8656": ("계열통합글쓰기(외국인)", 3, 34, "기초교양", "열린사고와표현"),
    "GEA8704": ("대학영어Ⅰ", 2, 34, "기초교양", "글로벌의사소통"),
    "GEA8705": ("대학영어Ⅱ", 2, 34, "기초교양", "글로벌의사소통"),
    "GEA8658": ("디지털협력기반문제중심학습(DC-PBL)", 3, 34, "균형교양", "디지털커뮤니케이션"),
    "GEA8659": ("디지털시대의글로벌리더십Ⅰ-AdventureDesign", 3, 34, "균형교양", "디지털커뮤니케이션"),
    "GEA8623": ("디지털휴머니즘", 3, 35, "균형교양", "디지털커뮤니케이션"),
    "GEA8660": ("디지털시대의미디어와개인", 3, 35, "균형교양", "디지털커뮤니케이션"),
    "GEA7261": ("컴퓨터프로그래밍", 3, 35, "균형교양", "디지털커뮤니케이션"),
    "GEA8666": ("한국SF문학의이해", 3, 36, "균형교양", "인문예술"),
    "GEA8585": ("문학과인간", 3, 36, "균형교양", "인문예술"),
    "GEA7562": ("민주시민과헌법", 3, 39, "균형교양", "사회와문화"),
    "GEA3070": ("현대민주주의이해", 3, 39, "균형교양", "사회와문화"),
    "GEA7308": ("통계학및연습1", 3, 41, "균형교양", "자연·과학·기술의이해"),
    "GEA7003": ("통계학", 3, 41, "균형교양", "자연·과학·기술의이해"),
    "GEA7260": ("컴퓨터개론", 3, 41, "균형교양", "자연·과학·기술의이해"),
    "GEA7301": ("공업수학", 3, 41, "균형교양", "자연·과학·기술의이해"),
    "GEA7300": ("응용수학", 3, 41, "균형교양", "자연·과학·기술의이해"),
    "GEA7006": ("물리학실험1", 1, 41, "균형교양", "자연·과학·기술의이해"),
}

# All rows on PDF pages 34–45 were compared with page images. These hashes freeze
# the reviewed code/name/credit/classification/area sequence; GEA8617 is excluded
# because pages 42 and 45 conflict, and the automatic p42 credit extraction is wrong.
PAGE_HASHES = {
    34: "2b336db93d8ecd2435d31492c518dd4160c2e06fa60ec88eed542c183b5c6b85",
    35: "dc77c5d8ec69ee50242cad87d116066d868484640b572766190b46cb6e21823e",
    36: "246350c3b68979456dbf05d62df26d7a51273abdaa60ad2782dfb0a23019616f",
    37: "2c825f9a78b5a39be7e83e5df1abd4ee1c433fcede86c7c0bd872c18f211ab53",
    38: "38ad857dba0d70fcb35fa1f173f98f1c0d80ecefd12351c90e0d51f921956c45",
    39: "0d315b0a32d7669aaf3bcd7f0fc8a1d7df376318febf3efc72bbb67c81231950",
    40: "8547bb1eeced7c3206832893685024dcdafca37d03a32b432cf16c37cad09a03",
    41: "064aa1d382030e3207edc42e52a239786a359d5653d5366856e57a46c872e59e",
    42: "9b4e5e04aecdbf5ad947c4154593cd47ac8c2f9e034df6ad80d1d1f9ff9c7bcc",
    43: "3ac6c7770fddecaabc107ed4fa38d9a41dd6a3bca3b33ba7f7b924986d39ebb2",
    44: "4c230229e712ea3352db69b070dee5551db0eb4ac47ebf3b7569d07fa6cf3372",
    45: "daa2c5c67c988431559b87990941e0ca0a50a50f3dcb4b555307480ddea8164b",
}
PAGE_COUNTS = {34: 17, 35: 24, 36: 25, 37: 24, 38: 25, 39: 24, 40: 26, 41: 26,
               42: 24, 43: 25, 44: 23, 45: 17}
FOREIGN_ONLY = {"GEA8656", "GEA8831", "GEA8832", "GEA8679"}

AREA = {"미래설계": "FUTURE_DESIGN", "AI융합기초": "AI_FOUNDATION",
        "열린사고와표현": "WRITING", "글로벌의사소통": "ENGLISH",
        "디지털커뮤니케이션": "DIGITAL_COMMUNICATION", "인문예술": "HUMANITIES_ARTS",
        "사회와문화": "SOCIETY_CULTURE", "자연·과학·기술의이해": "SCIENCE_TECHNOLOGY",
        "언어의세계": "LANGUAGES", "소양교육": "LITERACY"}
CLASSIFICATION = {"기초교양": "GENERAL_BASIC", "균형교양": "GENERAL_BALANCED", "확대교양": "GENERAL_EXPANDED"}


def promote() -> list[dict]:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    index = json.loads((ROOT / "data/processed/source_index.json").read_text(encoding="utf-8"))
    pdf = ROOT / index["source"]["path"]
    if raw["source_sha256"] != index["source"]["sha256"] or hashlib.sha256(pdf.read_bytes()).hexdigest() != raw["source_sha256"]:
        raise ValueError("Curriculum PDF changed after visual cross-check")
    by_code = {}
    for row in raw["rows"]:
        by_code.setdefault(row["course_id"], []).append(row)
    if len(raw["rows"]) != 282 or len(by_code.get("GEA8617", [])) != 2:
        raise ValueError("General-education extraction shape changed")
    for page, expected_hash in PAGE_HASHES.items():
        rows = [row for row in raw["rows"] if row["source"]["pdf_page"] == page and row["course_id"] != "GEA8617"]
        frozen = [[row[key] for key in ("course_id", "name", "catalog_credits", "classification", "area")] for row in rows]
        actual_hash = hashlib.sha256(json.dumps(frozen, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        if len(rows) != PAGE_COUNTS[page] or actual_hash != expected_hash:
            raise ValueError(f"Visual-page transcription changed: PDF {page}")
    selected = []
    for code, expected in CHECKED.items():
        rows = by_code.get(code, [])
        if len(rows) != 1 or rows[0]["verification_status"] != "UNVERIFIED":
            raise ValueError(f"Ambiguous or missing selected row: {code}")
        row = rows[0]
        actual = (row["name"], row["catalog_credits"], row["source"]["pdf_page"], row["classification"], row["area"])
        if actual != expected:
            raise ValueError(f"Visual transcription mismatch for {code}: {actual}")
    for row in raw["rows"]:
        code = row["course_id"]
        if code == "GEA8617":
            continue
        if row["verification_status"] != "UNVERIFIED" or row["source"]["pdf_page"] not in PAGE_HASHES:
            raise ValueError(f"Unexpected source status or page: {code}")
        selected.append({"course_id": code, "name": row["name"], "catalog_credits": row["catalog_credits"],
                         "classification": CLASSIFICATION[row["classification"]], "general_area": AREA[row["area"]],
                         "catalog_year": 2026, "department_id": None, "verification_status": "VERIFIED",
                         "fact_id": f"GE-2026-COURSE-{code}", "source": row["source"],
                         "eligible_scope": "FOREIGN_ONLY" if code in FOREIGN_ONLY else "NON_ENGINEERING_ONLY" if code == "GEA8811" else "GENERAL"})
    if len(selected) != 280 or len({row["course_id"] for row in selected}) != 280:
        raise ValueError("Expected 280 unambiguous visually reviewed general-education rows")
    OUTPUT.write_text(json.dumps({"source_document_id": "CURRICULUM-2026", "source_sha256": raw["source_sha256"],
                                  "scope": "2026 PDF pages 34-45 visual-page-checked unambiguous rows", "courses": selected,
                                  "known_conflicts": [{"course_id": "GEA8617", "pdf_pages": [42, 45],
                                                       "reason": "PDF 42: 수식없는물리로보는세상, 균형교양, 2학점 (raw extraction incorrectly says 3); PDF 45: 융합프로젝트Ⅰ, 확대교양, 3학점. Same code is unresolved."}]},
                                 ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return selected


if __name__ == "__main__":
    print(f"Promoted {len(promote())} visually checked general-education entries")
