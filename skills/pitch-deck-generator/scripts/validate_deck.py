#!/usr/bin/env python3
"""
validate_deck.py — Validates a generated Marp pitch deck Markdown file against
Sequoia/YC/DocSend structural rules:
  1. Slide count between 10 and 12 slides.
  2. Action Title present on every slide (no bare '## Problem' headers).
  3. Speaker notes (<!-- _notes: ... -->) present on every slide.
  4. Visual word density <= 45 words per slide (excluding tables, Mermaid, notes).
  5. Provenance tags ([VERIFIED], [BOTTOMS-UP], [FOUNDER-INPUT]) present across deck.
  6. Zero unreplaced {{placeholder}} markers.
  7. Zero banned VC Red-Flag phrases ('no competitors', '1% of', etc.).
Runs strictly on Python 3.8+ standard library.
"""

import argparse
import re
import sys
from pathlib import Path

BANNED_PATTERNS = [
    (re.compile(r"\bno\s+direct\s+competitors\b|\bno\s+competitors\b|\bzero\s+competitors\b", re.I),
     "VC Red Flag: Never claim 'no competitors'. Always compare against Status Quo & incumbents."),
    (re.compile(r"\b1%\s+of\s+(?:a|the)\b|\bcapture\s+1%\b", re.I),
     "VC Red Flag: Top-down '1% of market' claim detected. Use Bottoms-Up math (ICP x ACV)."),
]

PASSIVE_TITLES = re.compile(
    r"^##\s*(?:Slide\s*\d+\s*[—\-:]\s*)?(Problem|Solution|Why Now\??|Market Size|Product|Traction|Business Model|Competition|Team|Financials|The Ask)\s*$",
    re.I | re.M
)

PROVENANCE_TAGS = re.compile(r"\[(VERIFIED|BOTTOMS-UP|FOUNDER-INPUT)\]")
PLACEHOLDER_REGEX = re.compile(r"\{\{[A-Z0-9_]+\}\}")
NOTES_REGEX = re.compile(r"<!--\s*_?notes:(.*?)-->", re.S | re.I)


def strip_frontmatter_and_split_slides(raw_md: str) -> list:
    content = raw_md.strip()
    if content.startswith("---"):
        parts = re.split(r"^---\s*$", content, flags=re.M)
        # parts[0] is empty before first ---, parts[1] is YAML frontmatter, parts[2:] are slides
        if len(parts) >= 3:
            return [s.strip() for s in parts[2:] if s.strip()]
    return [s.strip() for s in re.split(r"^---\s*$", content, flags=re.M) if s.strip()]


def count_visual_words(slide_md: str) -> int:
    # Remove speaker notes
    text = NOTES_REGEX.sub("", slide_md)
    # Remove mermaid/code blocks
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    # Remove markdown tables
    lines = [
        ln for ln in text.splitlines()
        if not ln.strip().startswith("|") and not ln.strip().startswith("#")
    ]
    body = " ".join(lines)
    # Remove provenance badges from word count
    body = PROVENANCE_TAGS.sub("", body)
    words = re.findall(r"\b[\w'-]+\b", body)
    return len(words)


def validate_deck(filepath: Path, max_words: int = 45) -> list:
    errors = []
    raw = filepath.read_text(encoding="utf-8", errors="replace")

    # 1. Check unreplaced {{placeholders}}
    placeholders = PLACEHOLDER_REGEX.findall(raw)
    if placeholders:
        errors.append(f"Unreplaced template placeholders found: {', '.join( sorted(set(placeholders)) )}")

    # 2. Check banned VC red-flag phrases
    for pattern, msg in BANNED_PATTERNS:
        if pattern.search(raw):
            errors.append(msg)

    # 3. Split slides & check count (10-12)
    slides = strip_frontmatter_and_split_slides(raw)
    if not (10 <= len(slides) <= 12):
        errors.append(f"Slide count is {len(slides)} (must be between 10 and 12 slides).")

    # 4. Check provenance tags across deck
    tags_found = PROVENANCE_TAGS.findall(raw)
    if len(tags_found) < 8:
        errors.append(
            f"Insufficient provenance tags found ({len(tags_found)}). "
            "Every major metric/claim must carry [VERIFIED], [BOTTOMS-UP], or [FOUNDER-INPUT]."
        )

    # 5. Per-slide checks
    for idx, slide in enumerate(slides, start=1):
        # Heading check
        if not re.search(r"^#{1,2}\s+.+", slide, flags=re.M):
            errors.append(f"Slide {idx}: Missing level-1 or level-2 heading.")
        if PASSIVE_TITLES.search(slide):
            errors.append(
                f"Slide {idx}: Passive heading detected. Every slide must use a declarative Action Title "
                "(e.g. '## Slide 2 — Problem: Manual Audits Cost Banks $4.2B')."
            )

        # Speaker notes check
        notes_match = NOTES_REGEX.search(slide)
        if not notes_match or len(notes_match.group(1).strip()) < 15:
            errors.append(f"Slide {idx}: Missing or empty '<!-- _notes: ... -->' speaker script.")

        # Visual word density check
        w_count = count_visual_words(slide)
        if w_count > max_words:
            errors.append(
                f"Slide {idx}: Visual body text has {w_count} words (exceeds {max_words}-word skim limit). "
                "Move excess prose into <!-- _notes: ... -->."
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Marp pitch deck Markdown file.")
    parser.add_argument("deck_file", help="Path to deck.md")
    parser.add_argument("--max-words", type=int, default=45, help="Max visual body words per slide (default: 45)")
    args = parser.parse_args()

    deck_path = Path(args.deck_file)
    if not deck_path.exists():
        print(f"[FAIL] File not found: {deck_path}", file=sys.stderr)
        return 1

    errors = validate_deck(deck_path, max_words=args.max_words)
    if errors:
        print(f"❌ VALIDATION FAILED ({len(errors)} issue(s) in {deck_path}):")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(f"✅ VALIDATION PASSED: '{deck_path}' conforms to all Sequoia/YC/DocSend pitch deck standards.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
