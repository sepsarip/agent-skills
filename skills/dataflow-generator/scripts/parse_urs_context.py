#!/usr/bin/env python3
"""
parse_urs_context.py — Scans a URS Markdown file (or directory) to extract:
1. External Actors (ACT-XX)
2. Functional Epics (EPIC-XX)
3. User Stories (US-XXX) with their Role, Action+Object, and candidate Data Stores
Recommends a 7±2 Process Grouping plan for DFD Level 1.
"""
import sys
import re
from pathlib import Path

def parse_urs(content: str, source_name: str):
    actors = re.findall(r"\*\*(ACT-\d+)\*\*\s*\|\s*`?([^|`]+)`?", content)
    epics = re.findall(r"\*\*(EPIC-\d+):\*\*\s*(.+)", content)
    stories = re.findall(
        r"####\s*\[(US-\d+)\]\s*(.+?)\n.*?\*\*As a\*\*\s*`?([^`,]+)`?,\s*\*\*I want to\*\*\s*`?([^`,]+)`?",
        content, re.S | re.I
    )

    print(f"=== URS CONTEXT EXTRACTION FOR DFD: {source_name} ===")
    print(f"\n1. External Entities Detected ({len(actors)}):")
    for act_id, act_name in actors:
        print(f"   - {act_id}: {act_name.strip()}")

    print(f"\n2. Epics / Candidate Level-1 Processes ({len(epics)}):")
    for epic_id, epic_title in epics:
        print(f"   - {epic_id} -> Candidate Process: {epic_title.strip()}")

    if len(epics) > 9:
        print("   [!] WARNING: More than 9 Epics detected! Consolidate into <= 9 Level-1 Processes (7±2 Rule).")

    print(f"\n3. User Stories Mapped ({len(stories)}):")
    for us_id, title, role, action in stories:
        print(f"   - [{us_id}] ({role.strip()}) -> Action: {action.strip()}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python parse_urs_context.py <path_to_urs.md>")
        sys.exit(1)

    target = Path(sys.argv[1])
    if target.is_file():
        parse_urs(target.read_text(encoding="utf-8", errors="ignore"), target.name)
    elif target.is_dir():
        for p in sorted(target.rglob("*.md")):
            parse_urs(p.read_text(encoding="utf-8", errors="ignore"), p.name)
    else:
        print(f"Path not found: {target}")
        sys.exit(1)

if __name__ == "__main__":
    main()

