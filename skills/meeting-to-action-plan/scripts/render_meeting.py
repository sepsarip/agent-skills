#!/usr/bin/env python3
"""
render_meeting.py — Compiles a validated meeting-report.md into a standalone
interactive HTML dashboard (meeting-report.html) featuring:
  - Clickable @[HH:MM:SS - HH:MM:SS] chips wired to seek the local audio player.
  - Lifecycle badges ([ACTIVE], [OVERTURNED], [NEEDS-REVIEW]).
  - Live Mermaid state evolution diagrams.
  - One-click .ics calendar export.
Runs strictly on Python 3.8+ standard library.
"""

import argparse
import html
import re
import sys
from pathlib import Path

TS_CHIP_RE = re.compile(r"@\[(\d{2}:\d{2}:\d{2}(?:\s*(?:-|->)\s*\d{2}:\d{2}:\d{2})?)\]")


def format_inline(text: str) -> str:
    escaped = html.escape(text)
    # Convert @[HH:MM:SS - HH:MM:SS] into clickable seek chips
    escaped = TS_CHIP_RE.sub(
        r'<span class="ts-chip" onclick="seekToTimestamp(\'\1\')" title="Click to jump audio to \1">🎧 @[\1]</span>',
        escaped
    )
    # Convert lifecycle tags into styled badges
    escaped = (
        escaped
        .replace("`[ACTIVE]`", '<span class="badge badge-active">[ACTIVE]</span>')
        .replace("[ACTIVE]", '<span class="badge badge-active">[ACTIVE]</span>')
        .replace("`[OVERTURNED]`", '<span class="badge badge-overturned">[OVERTURNED]</span>')
        .replace("[OVERTURNED]", '<span class="badge badge-overturned">[OVERTURNED]</span>')
        .replace("`[NEEDS-REVIEW]`", '<span class="badge badge-review">[NEEDS-REVIEW]</span>')
        .replace("[NEEDS-REVIEW]", '<span class="badge badge-review">[NEEDS-REVIEW]</span>')
    )
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


def compile_markdown_to_html(md_text: str) -> tuple:
    title = "Meeting Intelligence Report"
    lines = md_text.splitlines()
    out = []
    in_list = False
    in_ol = False
    in_table = False
    in_code = False
    code_lang = ""
    code_buf = []

    def close_blocks():
        nonlocal in_list, in_ol, in_table
        if in_list:
            out.append("</ul>")
            in_list = False
        if in_ol:
            out.append("</ol>")
            in_ol = False
        if in_table:
            out.append("</tbody></table></div>")
            in_table = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```"):
            close_blocks()
            if not in_code:
                in_code = True
                code_lang = stripped[3:].strip().lower()
                code_buf = []
            else:
                in_code = False
                raw_code = "\n".join(code_buf)
                if code_lang == "mermaid":
                    out.append(f'<div class="mermaid-box"><pre class="mermaid">{html.escape(raw_code)}</pre></div>')
                else:
                    out.append(f'<pre class="json-box"><code>{html.escape(raw_code)}</code></pre>')
            continue

        if in_code:
            code_buf.append(line)
            continue

        if not stripped or stripped == "---":
            close_blocks()
            continue

        if stripped.startswith("# "):
            close_blocks()
            title = stripped[2:].strip()
            out.append(f"<h1>{format_inline(title)}</h1>")
        elif stripped.startswith("## "):
            close_blocks()
            out.append(f"<h2>{format_inline(stripped[3:].strip())}</h2>")
        elif stripped.startswith("### "):
            close_blocks()
            out.append(f"<h3>{format_inline(stripped[4:].strip())}</h3>")
        elif stripped.startswith(("* ", "- ")):
            if in_table or in_ol:
                close_blocks()
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{format_inline(stripped[2:].strip())}</li>")
        elif re.match(r"^\d+\.\s+", stripped):
            if in_table or in_list:
                close_blocks()
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            item_txt = re.sub(r"^\d+\.\s+", "", stripped)
            out.append(f"<li>{format_inline(item_txt)}</li>")
        elif stripped.startswith("|") and stripped.endswith("|"):
            if in_list or in_ol:
                close_blocks()
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(re.match(r"^:?-+:?$", c) for c in cells if c):
                continue
            if not in_table:
                out.append('<div class="table-wrap"><table><thead><tr>')
                for c in cells:
                    out.append(f"<th>{format_inline(c)}</th>")
                out.append("</tr></thead><tbody>")
                in_table = True
            else:
                out.append("<tr>")
                for c in cells:
                    out.append(f"<td>{format_inline(c)}</td>")
                out.append("</tr>")
        else:
            close_blocks()
            out.append(f"<p>{format_inline(stripped)}</p>")

    close_blocks()
    return title, "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render meeting-report.md into interactive HTML.")
    parser.add_argument("report_md", help="Input meeting-report.md path")
    parser.add_argument("--output", required=True, help="Output meeting-report.html path")
    parser.add_argument("--lang", choices=["en", "id"], default="en", help="UI language (default: en)")
    parser.add_argument(
        "--mermaid-url",
        default="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js",
        help="Mermaid CDN URL"
    )
    args = parser.parse_args()

    md_path = Path(args.report_md)
    if not md_path.exists():
        print(f"Error: Input file '{md_path}' not found.", file=sys.stderr)
        return 1

    tpl_path = Path(__file__).resolve().parent.parent / "assets" / "meeting-report-template.html"
    if not tpl_path.exists():
        print(f"Error: HTML template not found at '{tpl_path}'.", file=sys.stderr)
        return 1

    raw_md = md_path.read_text(encoding="utf-8", errors="replace")
    title, body_html = compile_markdown_to_html(raw_md)
    tpl_html = tpl_path.read_text(encoding="utf-8", errors="replace")

    rendered = (
        tpl_html
        .replace("{{LANG}}", args.lang)
        .replace("{{REPORT_TITLE}}", html.escape(title))
        .replace("{{REPORT_BODY_HTML}}", body_html)
        .replace("{{MERMAID_CDN}}", args.mermaid_url)
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(f"✅ Interactive Meeting Intelligence dashboard rendered to: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

