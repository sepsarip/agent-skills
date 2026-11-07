#!/usr/bin/env python3
"""
scan_context.py — Scans raw project documents and workspace files to extract candidate Actors,
measurable metrics, and potential ambiguous terms requiring clarification prior to drafting a URS.
"""
import sys
import re
from pathlib import Path

def scan_text(content: str, source_name: str):
    actors = set(re.findall(r'\b(admin(?:istrator)?|user|customer|manager|buyer|seller|operator|client|auditor|staff|cashier|clerk|member|guest)\b', content, re.I))
    metrics = re.findall(r'\b\d+(?:\.\d+)?\s*(?:ms|seconds?|minutes?|hours?|days?|mb|gb|%|users?)\b', content, re.I)
    vague_words = set(re.findall(r'\b(fast|quick|user-friendly|easy|secure|robust|seamless|optimal|efficient|appropriate)\b', content, re.I))

    print(f"=== CONTEXT SCAN RESULTS: {source_name} ===")
    print(f"- Detected Candidate Actors : {', '.join(sorted({a.lower() for a in actors})) or 'None explicitly identified'}")
    print(f"- Detected Numerical Metrics : {', '.join(metrics[:15]) or 'NONE (Warning: Risk of numerical hallucination!)'}")
    if vague_words:
        print(f"- Ambiguous Terms in Input  : {', '.join(sorted({v.lower() for v in vague_words}))}")
        print("  [!] AGENT INSTRUCTION: Clarify numerical benchmarks for ambiguous terms above or tag with [TBD] + [A0].")
    print()

def main():
    if len(sys.argv) < 2:
        print("Usage: python scan_context.py <file_or_dir_path>")
        sys.exit(1)

    target = Path(sys.argv[1])
    if target.is_file():
        scan_text(target.read_text(encoding="utf-8", errors="ignore"), target.name)
    elif target.is_dir():
        for p in sorted(target.rglob("*")):
            if p.suffix.lower() in {".md", ".txt", ".json", ".csv"} and p.is_file():
                scan_text(p.read_text(encoding="utf-8", errors="ignore"), str(p.relative_to(target)))
    else:
        print(f"Path not found: {target}")
        sys.exit(1)

if __name__ == "__main__":
    main()
