#!/usr/bin/env python3
"""validate_report.py - Validates LICENSE-AUDIT.md reports against schema and quality standards.

Checks required sections, inventory table structure, valid SPDX confidence ratings,
severity values, and absence of ungrounded or empty placeholders.
Uses Python 3 standard library only.
"""

import argparse
import re
import sys
from pathlib import Path

REQUIRED_SECTIONS = [
    "Summary",
    "Context and assumptions",
    "Coverage",
    "Inventory",
    "Findings",
    "Obligations",
    "Recommendations",
    "Unverified and limitations",
]

VALID_CONFIDENCE = {"verified", "declared", "unverified", "unknown"}
VALID_SEVERITY = {"blocker", "high", "medium", "low", "info"}
REQUIRED_INVENTORY_COLUMNS = [
    "component",
    "version",
    "type",
    "scope",
    "license",
    "confidence",
    "evidence",
]


def validate_report(report_path: Path) -> tuple:
    """Validate a Markdown license audit report against the schema.

    Returns:
        (is_valid: bool, errors: list[str], warnings: list[str])
    """
    errors = []
    warnings = []

    if not report_path.exists():
        return False, [f"Report file not found: {report_path}"], []

    try:
        with open(report_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        return False, [f"Failed to read report file: {e}"], []

    content = "".join(lines)

    # 1. Check title
    title_m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if not title_m:
        errors.append("Missing H1 title (expected '# License Audit Report')")
    elif "license audit" not in title_m.group(1).lower():
        warnings.append(f"H1 title does not contain 'License Audit': {title_m.group(1)!r}")

    # 2. Check required H2 sections
    h2_sections = re.findall(r"^##\s+(.+)$", content, re.MULTILINE)
    normalized_h2 = [s.strip().lower() for s in h2_sections]

    for req in REQUIRED_SECTIONS:
        if req.lower() not in normalized_h2:
            errors.append(f"Missing required section: '## {req}'")

    # Check section order
    last_idx = -1
    for req in REQUIRED_SECTIONS:
        req_lower = req.lower()
        if req_lower in normalized_h2:
            idx = normalized_h2.index(req_lower)
            if idx < last_idx:
                warnings.append(f"Section '## {req}' appears out of recommended canonical order.")
            last_idx = idx

    # 3. Check Inventory table columns and data rows
    inventory_m = re.search(r"^##\s+Inventory\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL | re.MULTILINE | re.IGNORECASE)
    if inventory_m:
        inv_text = inventory_m.group(1)
        table_lines = [l.strip() for l in inv_text.splitlines() if l.strip().startswith("|")]

        if len(table_lines) < 2:
            errors.append("Inventory section missing markdown table (expected header and rows).")
        else:
            # Check header columns
            header_cells = [c.strip().lower() for c in table_lines[0].split("|")[1:-1]]
            for req_col in REQUIRED_INVENTORY_COLUMNS:
                if not any(req_col in c for c in header_cells):
                    errors.append(f"Inventory table missing required column header: '{req_col}'")

            # Find confidence column index
            conf_idx = -1
            for i, c in enumerate(header_cells):
                if "confidence" in c:
                    conf_idx = i
                    break

            # Validate rows
            for row_num, row_line in enumerate(table_lines[2:], start=3):
                cells = [c.strip() for c in row_line.split("|")[1:-1]]
                if len(cells) < len(header_cells):
                    warnings.append(f"Inventory table row {row_num} has fewer columns ({len(cells)}) than header ({len(header_cells)}).")

                if conf_idx != -1 and conf_idx < len(cells):
                    raw_conf = cells[conf_idx].strip().strip("`*[]_").lower()
                    if raw_conf and raw_conf not in VALID_CONFIDENCE:
                        errors.append(
                            f"Inventory row {row_num}: Invalid confidence '{cells[conf_idx]}'. "
                            f"Must be one of: Verified, Declared, Unverified, Unknown."
                        )

    # 4. Check Findings table and severity ratings
    findings_m = re.search(r"^##\s+Findings\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL | re.MULTILINE | re.IGNORECASE)
    if findings_m:
        find_text = findings_m.group(1)
        table_lines = [l.strip() for l in find_text.splitlines() if l.strip().startswith("|")]
        if len(table_lines) >= 3:
            header_cells = [c.strip().lower() for c in table_lines[0].split("|")[1:-1]]
            sev_idx = -1
            for i, c in enumerate(header_cells):
                if "severity" in c:
                    sev_idx = i
                    break

            if sev_idx != -1:
                for row_num, row_line in enumerate(table_lines[2:], start=3):
                    cells = [c.strip() for c in row_line.split("|")[1:-1]]
                    if sev_idx < len(cells):
                        raw_sev = cells[sev_idx].strip().strip("`*[]_").lower()
                        if raw_sev and raw_sev not in VALID_SEVERITY:
                            errors.append(
                                f"Findings row {row_num}: Invalid severity '{cells[sev_idx]}'. "
                                f"Must be one of: Blocker, High, Medium, Low, Info."
                            )

    # 5. Check for unreplaced template placeholders
    placeholder_matches = re.findall(r"\[(e\.g\.|TODO|INSERT|REPLACE|sample-|example-)[^\]]*\]", content, re.IGNORECASE)
    if placeholder_matches:
        warnings.append(f"Found {len(placeholder_matches)} unreplaced template placeholder(s), e.g. {placeholder_matches[:3]}")

    is_valid = len(errors) == 0
    return is_valid, errors, warnings


def main():
    parser = argparse.ArgumentParser(
        description="Validate a LICENSE-AUDIT.md report against structure, schema, and confidence rules."
    )
    parser.add_argument(
        "report",
        nargs="?",
        default="LICENSE-AUDIT.md",
        help="Path to markdown report file (default: LICENSE-AUDIT.md).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors.",
    )

    args = parser.parse_args()
    report_path = Path(args.report)

    is_valid, errors, warnings = validate_report(report_path)

    for w in warnings:
        print(f"[WARN] {w}", file=sys.stderr)

    if errors:
        for e in errors:
            print(f"[ERROR] {e}", file=sys.stderr)

    if not is_valid or (args.strict and warnings):
        print(f"\n[FAIL] Validation failed with {len(errors)} error(s) and {len(warnings)} warning(s).", file=sys.stderr)
        sys.exit(1)

    print(f"[OK] Report '{report_path}' successfully passed validation.")
    sys.exit(0)


if __name__ == "__main__":
    main()

