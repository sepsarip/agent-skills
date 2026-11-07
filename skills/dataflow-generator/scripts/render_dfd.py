#!/usr/bin/env python3
"""
render_dfd.py — Compiles the verified DFD Markdown file (including Mermaid.js blocks)
into a standalone Interactive HTML Dashboard using `assets/dfd-template.html`.
"""
import sys
import re
import html
from pathlib import Path

def md_to_html_with_mermaid(md_text: str) -> str:
    # Strip YAML frontmatter and HTML comments
    md_text = re.sub(r"^---\n.*?\n---\n", "", md_text, flags=re.S)
    md_text = re.sub(r"<!--.*?-->", "", md_text, flags=re.S)

    # Convert ```mermaid blocks to <div class="mermaid">
    def repl_mermaid(m):
        return f'<div class="mermaid">\n{m.group(1).strip()}\n</div>'
    md_text = re.sub(r"```mermaid\n(.*?)```", repl_mermaid, md_text, flags=re.S)

    # Convert other code blocks
    def repl_code(m):
        return f"<pre><code>{html.escape(m.group(2).strip())}</code></pre>"
    md_text = re.sub(r"```(\w*)\n(.*?)```", repl_code, md_text, flags=re.S)

    lines = md_text.splitlines()
    out = []
    in_table = False
    in_list = False
    in_mermaid = False

    for line in lines:
        if '<div class="mermaid">' in line:
            in_mermaid = True
            out.append(line)
            continue
        if in_mermaid:
            out.append(line)
            if "</div>" in line:
                in_mermaid = False
            continue

        stripped = line.strip()

        # Markdown Tables
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

        # Headings
        h_match = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if h_match:
            if in_list:
                out.append("</ul>")
                in_list = False
            lvl = len(h_match.group(1))
            out.append(f"<h{lvl}>{h_match.group(2)}</h{lvl}>")
            continue

        # Lists
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
    full_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", full_html)
    full_html = re.sub(r"`([^`]+)`", r"<code>\1</code>", full_html)
    return full_html

def main():
    if len(sys.argv) < 3:
        print("Usage: python render_dfd.py <input_dfd.md> <output_dfd.html>")
        sys.exit(1)

    md_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2])
    template_path = Path(__file__).resolve().parent.parent / "assets" / "dfd-template.html"

    md_content = md_path.read_text(encoding="utf-8")
    html_shell = template_path.read_text(encoding="utf-8")

    title_match = re.search(r'project_name:\s*"?([^"\n]+)"?', md_content)
    project_name = title_match.group(1) if title_match else md_path.stem

    body_html = md_to_html_with_mermaid(md_content)
    final_html = html_shell.replace("{{PROJECT_NAME}}", project_name).replace("{{HTML_CONTENT}}", body_html)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(final_html, encoding="utf-8")
    print(f"✅ Successfully rendered Interactive DFD HTML to: {out_path}")

if __name__ == "__main__":
    main()

