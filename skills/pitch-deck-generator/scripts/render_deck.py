#!/usr/bin/env python3
"""
render_deck.py — Compiles a validated Marp pitch deck Markdown file (deck.md)
into a self-contained interactive HTML slide presentation (deck.html).
Supports tables, blockquotes, lists, Mermaid diagrams, speaker notes drawer,
provenance badges, keyboard navigation, and PDF printing.
Runs strictly on Python 3.8+ standard library.
"""

import argparse
import html
import re
import sys
from pathlib import Path

NOTES_REGEX = re.compile(r"<!--\s*_?notes:(.*?)-->", re.S | re.I)


def inline_format(text: str) -> str:
    escaped = html.escape(text)
    # Provenance badges
    escaped = escaped.replace(
        "[VERIFIED]", '<span class="badge badge-verified">[VERIFIED]</span>'
    ).replace(
        "[BOTTOMS-UP]", '<span class="badge badge-bottomsup">[BOTTOMS-UP]</span>'
    ).replace(
        "[FOUNDER-INPUT]", '<span class="badge badge-input">[FOUNDER-INPUT]</span>'
    )
    # Bold & Italic & Inline code
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


def render_slide_markdown(md_text: str) -> str:
    lines = md_text.splitlines()
    out = []
    in_list = False
    in_table = False
    in_mermaid = False
    mermaid_buf = []

    def close_blocks():
        nonlocal in_list, in_table
        if in_list:
            out.append("</ul>")
            in_list = False
        if in_table:
            out.append("</tbody></table>")
            in_table = False

    for line in lines:
        stripped = line.strip()

        # Mermaid code block handling
        if stripped.startswith("```mermaid"):
            close_blocks()
            in_mermaid = True
            mermaid_buf = []
            continue
        if in_mermaid:
            if stripped.startswith("```"):
                in_mermaid = False
                diagram_code = "\n".join(mermaid_buf)
                out.append(f'<div class="mermaid-box"><pre class="mermaid">{html.escape(diagram_code)}</pre></div>')
            else:
                mermaid_buf.append(line)
            continue

        if not stripped:
            close_blocks()
            continue

        # Headings
        if stripped.startswith("# "):
            close_blocks()
            out.append(f"<h1>{inline_format(stripped[2:].strip())}</h1>")
        elif stripped.startswith("## "):
            close_blocks()
            out.append(f"<h2>{inline_format(stripped[3:].strip())}</h2>")
        elif stripped.startswith("### "):
            close_blocks()
            out.append(f"<h3>{inline_format(stripped[4:].strip())}</h3>")
        # Blockquotes
        elif stripped.startswith(">"):
            close_blocks()
            out.append(f"<blockquote>{inline_format(stripped[1:].strip())}</blockquote>")
        # Unordered list
        elif stripped.startswith(("* ", "- ")):
            if in_table:
                out.append("</tbody></table>")
                in_table = False
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{inline_format(stripped[2:].strip())}</li>")
        # Markdown Table
        elif stripped.startswith("|") and stripped.endswith("|"):
            if in_list:
                out.append("</ul>")
                in_list = False
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            # Skip separator row (| :--- | :--- |)
            if all(re.match(r"^:?-+:?$", c) for c in cells if c):
                continue
            if not in_table:
                out.append("<table><thead><tr>")
                for c in cells:
                    out.append(f"<th>{inline_format(c)}</th>")
                out.append("</tr></thead><tbody>")
                in_table = True
            else:
                out.append("<tr>")
                for c in cells:
                    out.append(f"<td>{inline_format(c)}</td>")
                out.append("</tr>")
        else:
            close_blocks()
            out.append(f"<p>{inline_format(stripped)}</p>")

    close_blocks()
    return "\n".join(out)


def parse_deck(raw_md: str) -> tuple:
    title = "Startup Pitch Deck"
    m_title = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', raw_md, flags=re.M)
    if m_title:
        title = m_title.group(1)

    content = raw_md.strip()
    if content.startswith("---"):
        parts = re.split(r"^---\s*$", content, flags=re.M)
        slides_raw = [s.strip() for s in parts[2:] if s.strip()] if len(parts) >= 3 else []
    else:
        slides_raw = [s.strip() for s in re.split(r"^---\s*$", content, flags=re.M) if s.strip()]

    slides_html = []
    total = len(slides_raw)
    for idx, s_raw in enumerate(slides_raw, start=1):
        notes_match = NOTES_REGEX.search(s_raw)
        notes_text = notes_match.group(1).strip() if notes_match else ""
        visual_md = NOTES_REGEX.sub("", s_raw).strip()
        body_html = render_slide_markdown(visual_md)
        escaped_notes = html.escape(notes_text, quote=True)
        slides_html.append(
            f'<section class="slide" data-notes="{escaped_notes}">\n'
            f'{body_html}\n'
            f'<div class="slide-number">Slide {idx} / {total}</div>\n'
            f'</section>'
        )

    return title, "\n".join(slides_html)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile deck.md into an interactive deck.html presentation.")
    parser.add_argument("deck_md", help="Input Markdown file (deck.md)")
    parser.add_argument("--output", required=True, help="Output HTML file path (deck.html)")
    parser.add_argument("--lang", choices=["en", "id"], default="en", help="UI language (default: en)")
    parser.add_argument(
        "--mermaid-url",
        default="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js",
        help="Mermaid CDN URL"
    )
    args = parser.parse_args()

    md_path = Path(args.deck_md)
    if not md_path.exists():
        print(f"Error: Input file '{md_path}' does not exist.", file=sys.stderr)
        return 1

    template_path = Path(__file__).resolve().parent.parent / "assets" / "deck-template.html"
    if not template_path.exists():
        print(f"Error: HTML template not found at '{template_path}'.", file=sys.stderr)
        return 1

    raw_md = md_path.read_text(encoding="utf-8", errors="replace")
    deck_title, slides_html = parse_deck(raw_md)
    template_html = template_path.read_text(encoding="utf-8", errors="replace")

    rendered = (
        template_html
        .replace("{{LANG}}", args.lang)
        .replace("{{DECK_TITLE}}", html.escape(deck_title))
        .replace("{{SLIDES_HTML}}", slides_html)
        .replace("{{MERMAID_CDN}}", args.mermaid_url)
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(f"✅ Interactive HTML pitch deck rendered to: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
