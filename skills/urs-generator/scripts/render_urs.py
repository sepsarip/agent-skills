#!/usr/bin/env python3
"""
render_urs.py — Compiles a Markdown URS document into an interactive HTML dashboard
using the `assets/urs-template.html` shell.
"""
import sys
import re
import html
from pathlib import Path

def simple_md_to_html(md_text: str) -> str:
    # Strip YAML frontmatter
    md_text = re.sub(r"^---\n.*?\n---\n", "", md_text, flags=re.S)

    # Convert code blocks
    def repl_code(m):
        code = html.escape(m.group(2).strip())
        return f"<pre><code>{code}</code></pre>"
    md_text = re.sub(r"```(\w*)\n(.*?)```", repl_code, md_text, flags=re.S)

    lines = md_text.splitlines()
    out = []
    in_table = False
    in_list = False

    for line in lines:
        stripped = line.strip()

        # Markdown Table
        if stripped.startswith("|") and stripped.endswith("|"):
            if re.match(r"^\|[\s\-:|]+\|$", stripped):
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if not in_table:
                out.append("<table><thead><tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr></thead><tbody>")
                in_table = True
            else:
                out.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            continue
        elif in_table:
            out.append("</tbody></table>")
            in_table = False

        # Heading
        h_match = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if h_match:
            if in_list:
                out.append("</ul>")
                in_list = False
            lvl = len(h_match.group(1))
            out.append(f"<h{lvl}>{h_match.group(2)}</h{lvl}>")
            continue

        # Blockquote
        if stripped.startswith(">"):
            out.append(f"<blockquote>{stripped.lstrip('> ').strip()}</blockquote>")
            continue

        # List item
        if stripped.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{stripped[2:]}</li>")
            continue
        elif in_list and not stripped:
            out.append("</ul>")
            in_list = False

        if stripped:
            out.append(f"<p>{stripped}</p>")

    if in_table:
        out.append("</tbody></table>")
    if in_list:
        out.append("</ul>")

    full_html = "\n".join(out)
    # Inline formatting (bold and inline code)
    full_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", full_html)
    full_html = re.sub(r"`([^`]+)`", r"<code>\1</code>", full_html)
    return full_html

def main():
    if len(sys.argv) < 3:
        print("Usage: python render_urs.py <input_urs.md> <output_urs.html>")
        sys.exit(1)

    md_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    template_path = Path(__file__).resolve().parent.parent / "assets" / "urs-template.html"

    md_content = md_path.read_text(encoding="utf-8")
    html_shell = template_path.read_text(encoding="utf-8")

    title_match = re.search(r'project_name:\s*"?([^"\n]+)"?', md_content)
    project_name = title_match.group(1) if title_match else md_path.stem

    body_html = simple_md_to_html(md_content)
    final_html = html_shell.replace("{{PROJECT_NAME}}", project_name).replace("{{HTML_CONTENT}}", body_html)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(final_html, encoding="utf-8")
    print(f"✅ Successfully compiled interactive HTML to: {out_path}")

if __name__ == "__main__":
    main()
