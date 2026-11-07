#!/usr/bin/env python3
"""
validate_meeting.py — Deterministic validator for meeting-report.md:
  1. Verifies zero unreplaced {{PLACEHOLDER}} markers.
  2. Verifies lifecycle state tags ([ACTIVE], [OVERTURNED], [NEEDS-REVIEW]) are
     accompanied by valid @[HH:MM:SS] or @[HH:MM:SS - HH:MM:SS] citations.
  3. Checks timestamp citations against the recording's max_seconds (if --transcript-meta supplied).
  4. Validates the embedded Constrained Action Item JSON block against required fields,
     ISO 8601 due_date_iso format, and coreference clarity (rejects vague pronouns).
Runs strictly on Python 3.8+ standard library.
"""

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")
TIMESTAMP_CITE_RE = re.compile(
    r"@\[(\d{2}:\d{2}:\d{2})(?:\s*(?:-|->)\s*(\d{2}:\d{2}:\d{2}))?\]"
)
VAGUE_COREF_RE = re.compile(
    r"\b(fix it|do that|handle it|check that|benerin itu|kerjakan itu|urus hal tersebut)\b",
    re.I
)
REQUIRED_JSON_KEYS = {
    "task_id", "task_name", "assignee", "due_date_iso", "status",
    "lifecycle_state", "priority", "context_timestamp", "verbatim_source_quote", "confidence_score"
}


def hms_to_seconds(hms: str) -> int:
    parts = [int(p) for p in hms.split(":")]
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def is_valid_iso_date(val: str) -> bool:
    if val == "TBD":
        return True
    clean = val.replace("Z", "").split("T")[0]
    try:
        datetime.date.fromisoformat(clean)
        return True
    except ValueError:
        return False


def validate_report(report_path: Path, meta_path: Path = None) -> list:
    errors = []
    raw = report_path.read_text(encoding="utf-8", errors="replace")

    max_seconds = None
    if meta_path and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            max_seconds = meta.get("max_seconds")
        except Exception as exc:
            errors.append(f"Failed to read transcript metadata JSON: {exc}")

    # 1. Check unreplaced {{PLACEHOLDERS}}
    placeholders = PLACEHOLDER_RE.findall(raw)
    if placeholders:
        errors.append(f"Unreplaced template placeholders detected: {', '.join(sorted(set(placeholders)))}")

    # 2. Check timestamp citations & bounds
    ts_matches = TIMESTAMP_CITE_RE.findall(raw)
    if not ts_matches:
        errors.append("No @[HH:MM:SS - HH:MM:SS] timestamp citations found in report.")

    for start_hms, end_hms in ts_matches:
        s_sec = hms_to_seconds(start_hms)
        if end_hms:
            e_sec = hms_to_seconds(end_hms)
            if e_sec < s_sec:
                errors.append(f"Invalid timestamp range @[{start_hms} - {end_hms}]: end time precedes start time.")
            if max_seconds and e_sec > max_seconds + 30:
                errors.append(
                    f"Out-of-bounds timestamp @[{start_hms} - {end_hms}] exceeds recording duration ({max_seconds}s)."
                )
        elif max_seconds and s_sec > max_seconds + 30:
            errors.append(f"Out-of-bounds timestamp @[{start_hms}] exceeds recording duration ({max_seconds}s).")

    # 3. Validate embedded JSON Action Item Schema
    json_blocks = re.findall(r"```json\s*(.*?)\s*```", raw, flags=re.S)
    if not json_blocks:
        errors.append("Missing ```json ... ``` Constrained Action Item Schema block in Section 6.")
    else:
        for b_idx, block in enumerate(json_blocks, start=1):
            try:
                items = json.loads(block)
            except json.JSONDecodeError as exc:
                errors.append(f"JSON Block #{b_idx} syntax error: {exc}")
                continue

            if not isinstance(items, list) or not items:
                errors.append(f"JSON Block #{b_idx} must be a non-empty list of Action Item objects.")
                continue

            for item in items:
                tid = item.get("task_id", "UNKNOWN_ID")
                missing = REQUIRED_JSON_KEYS - set(item.keys())
                if missing:
                    errors.append(f"Task '{tid}' in JSON is missing required keys: {', '.join(sorted(missing))}")
                    continue

                tname = str(item.get("task_name", ""))
                if VAGUE_COREF_RE.search(tname) or len(tname.split()) < 4:
                    errors.append(
                        f"Task '{tid}' failed Coreference Resolution ('{tname}'). "
                        "Use a self-contained description with explicit verb and target module."
                    )

                due = str(item.get("due_date_iso", ""))
                if not is_valid_iso_date(due):
                    errors.append(f"Task '{tid}' has invalid ISO 8601 due_date_iso: '{due}'.")

                assignee = str(item.get("assignee", ""))
                state = str(item.get("lifecycle_state", ""))
                if (assignee.lower() == "unassigned" or due == "TBD") and state == "ACTIVE":
                    errors.append(
                        f"Task '{tid}' has Unassigned owner or TBD due date but is marked ACTIVE. "
                        "Route incomplete items to NEEDS-REVIEW."
                    )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate meeting-report.md structure, timestamps, and JSON schema.")
    parser.add_argument("report_md", help="Path to meeting-report.md")
    parser.add_argument("--transcript-meta", help="Optional path to parsed_meeting.json from parse_transcript.py")
    args = parser.parse_args()

    r_path = Path(args.report_md)
    if not r_path.exists():
        print(f"[FAIL] File not found: {r_path}", file=sys.stderr)
        return 1

    meta_path = Path(args.transcript_meta) if args.transcript_meta else None
    errors = validate_report(r_path, meta_path)

    if errors:
        print(f"❌ MEETING VALIDATION FAILED ({len(errors)} issue(s)):")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(f"✅ MEETING VALIDATION PASSED: '{r_path}' conforms to Locate-then-Extract & Temporal Grounding rules.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

