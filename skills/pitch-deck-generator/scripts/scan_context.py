#!/usr/bin/env python3
"""
scan_context.py — Scans a target workspace/repository for product signals,
README summaries, package metadata, and markdown documentation to ground
pitch deck claims as [VERIFIED].
Runs strictly on Python 3.8+ standard library.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build",
    ".next", ".nuxt", "vendor", "target", "coverage"
}

DOC_PATTERNS = re.compile(r"(readme|prd|pitch|vision|roadmap|pricing|architecture|spec).*\.md$", re.I)
MANIFEST_FILES = {"package.json", "pyproject.toml", "Cargo.toml", "go.mod"}


def extract_markdown_headings_and_summary(filepath: Path, max_chars: int = 1200) -> dict:
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}
    headings = re.findall(r"^#{1,3}\s+(.+)$", content, flags=re.M)[:12]
    clean_paragraphs = [
        line.strip() for line in content.splitlines()
        if line.strip() and not line.strip().startswith(("#", "```", "<!--", "|"))
    ]
    excerpt = " ".join(clean_paragraphs)[:max_chars]
    return {
        "file": str(filepath),
        "headings": headings,
        "excerpt": excerpt,
    }


def scan_workspace(root_dir: Path, max_files: int = 30) -> dict:
    signals = {
        "root": str(root_dir.resolve()),
        "manifests": [],
        "documentation": [],
        "detected_pricing_or_metrics": [],
    }
    doc_count = 0
    price_regex = re.compile(r"(\$[0-9,.]+(?:/mo|/yr|k|M|B)?|ARR|MRR|ACV|pricing|subscription)", re.I)

    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        rel_dir = Path(dirpath).relative_to(root_dir)

        for fname in filenames:
            fpath = Path(dirpath) / fname
            rel_path = rel_dir / fname

            if fname in MANIFEST_FILES:
                try:
                    raw = fpath.read_text(encoding="utf-8", errors="replace")[:1500]
                    signals["manifests"].append({"file": str(rel_path), "snippet": raw})
                except Exception:
                    pass

            if DOC_PATTERNS.match(fname) and doc_count < max_files:
                doc_count += 1
                info = extract_markdown_headings_and_summary(fpath)
                if info:
                    info["file"] = str(rel_path)
                    signals["documentation"].append(info)
                    matches = price_regex.findall(info.get("excerpt", ""))
                    if matches:
                        signals["detected_pricing_or_metrics"].append({
                            "file": str(rel_path),
                            "signals": list(set(matches))[:10]
                        })

    return signals


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan repository/workspace for pitch deck product signals.")
    parser.add_argument("target", help="Target directory to scan")
    parser.add_argument("--output", default="-", help="Output JSON file path ('-' for stdout)")
    parser.add_argument("--max-files", type=int, default=30, help="Maximum doc files to inspect")
    args = parser.parse_args()

    root = Path(args.target)
    if not root.exists() or not root.is_dir():
        print(f"Error: Target directory '{args.target}' does not exist.", file=sys.stderr)
        return 1

    result = scan_workspace(root, max_files=args.max_files)
    payload = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output == "-":
        print(payload)
    else:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload, encoding="utf-8")
        print(f"Context scan saved to {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
