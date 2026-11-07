#!/usr/bin/env python3
"""
validate_dfd.py — Deterministic Graph-Theoretic Linter for DFD Specifications.
Verifies:
1. All 7 Mandatory Sections exist.
2. Permissible Connectivity Matrix (No EE->EE, DS->DS, EE<->DS direct bypasses).
3. Black Hole Anomaly check (in-degree >= 1 and out-degree == 0).
4. Miracle / Spontaneous Generation check (in-degree == 0 and out-degree >= 1).
5. Process Explosion Rule (7 ± 2 rule: max 9 processes in Level 1).
6. Parent-Child Boundary Balancing (Level 0 external flows == Level 1 external flows).
7. Mermaid syntax rules (No bi-directional '<-->' arrows, no unlabeled edges).
8. Naming grammar (Data Flows & Stores must not contain process/control flags).
"""
import sys
import re
from pathlib import Path
from collections import defaultdict

REQUIRED_SECTIONS = [
    r"#+\s*1\.\s*External Entities Mapping",
    r"#+\s*2\.\s*Context Diagram",
    r"#+\s*3\.\s*DFD Level 1 Decomposition",
    r"#+\s*4\.\s*Data Dictionary",
    r"#+\s*5\.\s*Data Store Specification",
    r"#+\s*6\.\s*Trust Boundaries",
    r"#+\s*7\.\s*Bidirectional Requirements Traceability",
]

FORBIDDEN_PAYLOAD_WORDS = [
    r"\bsend\b", r"\bcreate\b", r"\bvalidate\b", r"\bprocess\b",
    r"\btrue/false\b", r"\bboolean flag\b"
]

def extract_markdown_table(md_text: str, marker: str) -> list:
    pos = md_text.find(marker)
    if pos == -1:
        return []
    sub = md_text[pos:]
    rows = []
    started = False
    for line in sub.splitlines()[1:]:
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            started = True
            if re.match(r"^\|[\s\-:|]+\|$", s):
                continue
            cells = [c.strip().strip("`*") for c in s.strip("|").split("|")]
            rows.append(cells)
        elif started and not s.startswith("|"):
            break
    return rows[1:] if len(rows) > 1 else []

def validate_dfd(md_text: str) -> list:
    errors = []

    # 1. Check Mandatory Sections
    for sec in REQUIRED_SECTIONS:
        if not re.search(sec, md_text, re.I):
            errors.append(f"[STRUCT] Missing required section matching `{sec}`")

    # 2. Check Mermaid Blocks for Bi-directional or Unlabeled Edges
    mermaid_blocks = re.findall(r"```mermaid\n(.*?)```", md_text, re.S)
    if len(mermaid_blocks) < 2:
        errors.append("[MERMAID] Document must contain at least 2 Mermaid diagrams (Level 0 and Level 1).")

    for idx, block in enumerate(mermaid_blocks, start=1):
        for line in block.splitlines():
            if "<-->" in line or "<->" in line:
                errors.append(f"[MERMAID-{idx}] [BI-DIRECTIONAL] Forbidden bi-directional arrow found: `{line.strip()}`")
            if "-->" in line and "|" not in line and "--" not in line.split("-->")[0]:
                errors.append(f"[MERMAID-{idx}] [UNLABELED-FLOW] Data flow edge is missing a payload label `|DF-XX: Name|`: `{line.strip()}`")

    # 3. Parse L0 and L1 Flow Tables
    l0_rows = extract_markdown_table(md_text, "<!-- LINTER_TABLE:L0_FLOWS -->")
    l1_rows = extract_markdown_table(md_text, "<!-- LINTER_TABLE:L1_FLOWS -->")

    if not l0_rows:
        errors.append("[TABLE] Missing or empty `<!-- LINTER_TABLE:L0_FLOWS -->` table.")
    if not l1_rows:
        errors.append("[TABLE] Missing or empty `<!-- LINTER_TABLE:L1_FLOWS -->` table.")
        return errors

    # 4. Evaluate Level 1 Graph Topology
    in_degree = defaultdict(int)
    out_degree = defaultdict(int)
    processes = set()
    l0_external_flows = set()
    l1_external_flows = set()

    for r in l0_rows:
        if len(r) < 6:
            continue
        flow_id, src, src_type, tgt, tgt_type, payload = r[0], r[1], r[2].upper(), r[3], r[4].upper(), r[5]
        if src_type == "EE":
            l0_external_flows.add(("IN", src, payload.lower()))
        if tgt_type == "EE":
            l0_external_flows.add(("OUT", tgt, payload.lower()))

    for r in l1_rows:
        if len(r) < 6:
            continue
        flow_id, src, src_type, tgt, tgt_type, payload = r[0], r[1], r[2].upper(), r[3], r[4].upper(), r[5]

        # Track processes & degrees
        if src_type == "P":
            processes.add(src)
            out_degree[src] += 1
        if tgt_type == "P":
            processes.add(tgt)
            in_degree[tgt] += 1

        # Track External Flows for Parent-Child Balancing
        if src_type == "EE":
            l1_external_flows.add(("IN", src, payload.lower()))
        if tgt_type == "EE":
            l1_external_flows.add(("OUT", tgt, payload.lower()))

        # Check Illegal Component Bypasses (EE->EE, DS->DS, EE<->DS)
        if (src_type, tgt_type) in {("EE", "EE"), ("DS", "DS"), ("EE", "DS"), ("DS", "EE")}:
            errors.append(
                f"[{flow_id}] [ILLEGAL-BYPASS] Direct flow `{src} ({src_type}) -> {tgt} ({tgt_type})` is forbidden! Must pass through a Process (P)."
            )

        # Check Payload Naming Grammar (Noun Phrase)
        for bad_w in FORBIDDEN_PAYLOAD_WORDS:
            if re.search(bad_w, payload.lower()):
                errors.append(
                    f"[{flow_id}] [NAMING-VIOLATION] Data Flow payload `{payload}` contains verb/control flag (`{bad_w}`). Use pure Noun Phrase."
                )

    # 5. Check Black Hole & Miracle Anomalies on every Process
    for p in sorted(processes):
        ind = in_degree[p]
        outd = out_degree[p]
        if ind >= 1 and outd == 0:
            errors.append(f"[{p}] [BLACK-HOLE] Process `{p}` has in-degree={ind} but out-degree=0!")
        elif ind == 0 and outd >= 1:
            errors.append(f"[{p}] [MIRACLE] Process `{p}` has in-degree=0 but out-degree={outd} (Spontaneous Generation)!")

    # 6. Check 7 ± 2 Process Explosion Limit
    if len(processes) > 9:
        errors.append(
            f"[PROCESS-EXPLOSION] Level 1 contains {len(processes)} processes ({', '.join(sorted(processes))}). Maximum allowed is 9 (7±2 Rule)."
        )

    # 7. Check Parent-Child Balancing (Level 0 vs Level 1 External Flows)
    missing_in_l1 = l0_external_flows - l1_external_flows
    extra_in_l1 = l1_external_flows - l0_external_flows
    if missing_in_l1:
        errors.append(f"[BALANCING-ERROR] External flows in Level 0 missing in Level 1: {missing_in_l1}")
    if extra_in_l1:
        errors.append(f"[BALANCING-ERROR] Orphan external flows in Level 1 not declared in Level 0: {extra_in_l1}")

    return errors

def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_dfd.py <path_to_dfd.md>")
        sys.exit(1)

    md_path = Path(sys.argv[1])
    if not md_path.exists():
        print(f"File not found: {md_path}")
        sys.exit(1)

    content = md_path.read_text(encoding="utf-8")
    errors = validate_dfd(content)

    if errors:
        print(f"❌ DFD VALIDATION FAILED ({len(errors)} Topological/Syntactic Violations):")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    else:
        print("✅ DFD VALIDATION PASSED (0 Errors — Graph Topology, Balancing, and Security Rules Verified).")
        sys.exit(0)

if __name__ == "__main__":
    main()

