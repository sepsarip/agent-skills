#!/usr/bin/env python3
"""
validate_urs.py — Deterministic linter to validate URS documents against:
1. Completeness of the 5 mandatory ISO/IEC/IEEE 29148 sections
2. Absence of technical SRS leakage terms (SQL, API, JSON, internal frameworks)
3. Absence of ambiguous qualitative qualifiers (fast, user-friendly, seamless, etc.)
4. Absence of Non-User Roles (As a System / Developer / Database)
5. QUS Story Atomicity (no coordinating conjunctions 'and' / 'as well as' in the Means clause)
6. Minimum of 3 Acceptance Criteria per User Story & Evidential Provenance tags [A0/A1/A2]
"""
import sys
import re
from pathlib import Path

REQUIRED_SECTIONS = [
    r"#+\s*1\.\s*(?:Introduction|Pendahuluan)",
    r"#+\s*2\.\s*(?:General Description|Deskripsi Umum Kebutuhan)",
    r"#+\s*3\.\s*(?:User Requirements Specification|Spesifikasi Kebutuhan Pengguna)",
    r"#+\s*4\.\s*(?:User-Centric Non-Functional Requirements|Kebutuhan Non-Fungsional Pengguna)",
    r"#+\s*5\.\s*(?:Requirements Traceability Matrix|Matriks Keterlacakan Kebutuhan)",
]

SRS_FORBIDDEN_TERMS = [
    r"\bpostgresql\b", r"\bmysql\b", r"\bmongodb\b", r"\bredis\b",
    r"\bvarchar\b", r"\bprimary key\b", r"\bforeign key\b", r"\btable schema\b",
    r"\brest api\b", r"\bgraphql\b", r"\bjson payload\b", r"\bmicroservice\b",
    r"\bcron job\b", r"\bdocker\b", r"\bkubernetes\b", r"/api/v\d+"
]

VAGUE_QUALIFIERS = [
    r"\buser-friendly\b", r"\bseamless\b", r"\brobust\b",
    r"\bas soon as possible\b", r"\basap\b", r"\bsecepat mungkin\b",
    r"\bmudah digunakan\b"
]

FORBIDDEN_ROLES = [
    r"as a\s+(?:system|database|developer|backend|frontend|server|api|microservice)",
    r"sebagai\s+(?:sistem|database|developer|server|api)"
]

def validate_urs(md_text: str) -> list:
    errors = []
    lines = md_text.splitlines()

    # 1. Check Mandatory Sections
    for sec_pattern in REQUIRED_SECTIONS:
        if not re.search(sec_pattern, md_text, re.I):
            errors.append(f"[STRUCT] Mandatory section missing: pattern `{sec_pattern}`")

    # 2. Check Line-by-Line for SRS Leakage, Vague Words, Forbidden Roles, and Atomicity
    for idx, line in enumerate(lines, start=1):
        low = line.lower()

        for srs_pat in SRS_FORBIDDEN_TERMS:
            if re.search(srs_pat, low):
                errors.append(f"[Line {idx}] [SRS-LEAK] Prohibited SRS technical term found (`{srs_pat}`): {line.strip()}")

        for vague_pat in VAGUE_QUALIFIERS:
            if re.search(vague_pat, low):
                errors.append(f"[Line {idx}] [AMBIGUOUS] Prohibited ambiguous qualitative word (`{vague_pat}`): {line.strip()}")

        for role_pat in FORBIDDEN_ROLES:
            if re.search(role_pat, low):
                errors.append(f"[Line {idx}] [NON-USER-ROLE] Actor cannot be an internal component or developer: {line.strip()}")

        # Check Atomicity on Canonical User Story
        us_match = re.search(r"i want to\s+(.+?),\s*so that", low)
        if us_match:
            means_clause = us_match.group(1)
            if re.search(r"\b(and|as well as|serta|dan)\b", means_clause):
                errors.append(
                    f"[Line {idx}] [QUS-ATOMICITY] Atomicity violation! 'I want to' clause contains coordinating conjunction (`{means_clause}`). Split into 2 User Stories!"
                )

    # 3. Check each User Story block [US-XXX]
    us_blocks = re.split(r"(?=####\s*\[US-\d+\])", md_text)
    us_found = 0
    for block in us_blocks:
        header_match = re.match(r"####\s*\[(US-\d+)\]", block)
        if not header_match:
            continue
        us_found += 1
        us_id = header_match.group(1)

        # Check Provenance Tag
        if not re.search(r"\[A[012]:[^\]]+\]", block):
            errors.append(f"[{us_id}] [PROVENANCE] Missing Evidential Grounding tag (`[A0: ...]`, `[A1: ...]`, or `[A2: ...]`).")

        # Check EARS Keyword
        if not re.search(r"\b(SHALL|SHOULD|MAY|WILL)\b", block):
            errors.append(f"[{us_id}] [ISO-29148] Missing uppercase normative keyword (SHALL/SHOULD/MAY/WILL).")

        # Check Acceptance Criteria count (minimum 3)
        ac_count = len(re.findall(r"AC-\d+\.\d+", block))
        if ac_count < 3:
            errors.append(f"[{us_id}] [AC-COUNT] Contains only {ac_count} Acceptance Criteria (Minimum 3 required: Happy, Negative, Boundary/Edge).")

    if us_found == 0:
        errors.append("[CONTENT] No User Story blocks formatted as `#### [US-001]` were found.")

    return errors

def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_urs.py <path_to_urs.md>")
        sys.exit(1)

    md_path = Path(sys.argv[1])
    if not md_path.exists():
        print(f"File not found: {md_path}")
        sys.exit(1)

    content = md_path.read_text(encoding="utf-8")
    errors = validate_urs(content)

    if errors:
        print(f"❌ URS VALIDATION FAILED ({len(errors)} Violation(s) Detected):")
        for err in errors:
            print("  -", err)
        sys.exit(1)
    else:
        print("✅ URS VALIDATION PASSED (0 ISO 29148 / EARS / QUS Violations).")
        sys.exit(0)

if __name__ == "__main__":
    main()
