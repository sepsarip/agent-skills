#!/usr/bin/env python3
"""
Compile a structured manual_spec.json into Markdown (.md) and Word (.docx)
with Table of Contents, chapter-based figure citations, bullet-point explanations,
working hyperlinks, roman front-matter numbering, and page-number-only footers.
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

_scripts_dir = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

try:
    from embed_images import embed_images_in_docx
except ImportError:
    embed_images_in_docx = None


def validate_workspace_path(target_path: str, must_exist: bool = False) -> str:
    """Verify that target_path stays within the active workspace directory."""
    cwd = os.path.realpath(os.getcwd())
    real_target = os.path.realpath(target_path)
    if not (real_target == cwd or real_target.startswith(cwd + os.sep)):
        raise ValueError(
            f"Security Error: Path '{target_path}' escapes the active workspace '{cwd}'."
        )
    if must_exist and not os.path.exists(real_target):
        raise FileNotFoundError(f"File not found: {real_target}")
    return real_target


def get_labels(lang: str) -> Dict[str, str]:
    """Return localized structural labels based on manual language (defaults to English)."""
    if lang.lower().startswith("id"):
        return {
            "default_title": "Buku Panduan Pengguna",
            "toc": "Daftar Isi",
            "lof": "Daftar Gambar",
            "chapter": "Bab",
            "figure": "Gambar",
            "see_figure": "Lihat Gambar",
            "version": "Versi",
            "date": "Tanggal Pembaruan",
        }
    return {
        "default_title": "Application User Manual",
        "toc": "Table of Contents",
        "lof": "List of Figures",
        "chapter": "Chapter",
        "figure": "Figure",
        "see_figure": "See Figure",
        "version": "Version",
        "date": "Last Updated",
    }


def to_roman(n: int) -> str:
    """Convert integer to lowercase Roman numeral (for front matter)."""
    val = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    syb = ["m", "cm", "d", "cd", "c", "xc", "l", "xl", "x", "ix", "v", "iv", "i"]
    roman_num = ""
    i = 0
    while n > 0:
        for _ in range(n // val[i]):
            roman_num += syb[i]
            n -= val[i]
        i += 1
    return roman_num or "i"


def ensure_citation_in_text(
    body: str, figures: List[Dict[str, Any]], labels: Dict[str, str]
) -> str:
    """Guarantee every figure in a section is cited in the text."""
    updated_body = body.strip()
    for fig in figures:
        fig_id = str(fig.get("id", ""))
        citation_token = f"{labels['figure']} {fig_id}"
        if citation_token.lower() not in updated_body.lower():
            updated_body += f" ({labels['see_figure']} {fig_id})."
    return updated_body


# ---------------------------------------------------------
# Markdown Generator
# ---------------------------------------------------------
def build_markdown(spec: Dict[str, Any], md_path: str, out_dir: str) -> None:
    """
    Generate Markdown manual book:
    - Cover page: Title & metadata, no footer number.
    - TOC: Pure anchor links without page numbers (as requested).
    - Chapters: Numbered footers (*X*), explicit HTML anchors for guaranteed navigation.
    """
    labels = get_labels(spec.get("language", "en"))
    chapters = spec.get("chapters", [])
    lines: List[str] = []

    # Styling for justified text alignment
    lines.append('<style>\np, li { text-align: justify; text-justify: inter-word; }\n</style>\n')

    # Cover Page: Logo or Placeholder
    logo_path = spec.get("logo_path")
    has_logo = False
    if logo_path:
        try:
            real_logo = validate_workspace_path(logo_path, must_exist=True)
            rel_logo = os.path.relpath(real_logo, start=out_dir)
            lines.append(f'<div align="center" style="margin-top: 40px; margin-bottom: 24px;"><img src="{rel_logo}" alt="Logo" style="max-height: 90px; max-width: 250px;" /></div>\n')
            has_logo = True
        except Exception:
            has_logo = False
    if not has_logo:
        lines.append('<div align="center" style="margin-top: 40px; margin-bottom: 30px;"><div style="border: 2px dashed #94a3b8; padding: 20px 40px; display: inline-block; border-radius: 8px; color: #64748b; font-weight: bold; font-size: 14pt;">[ LOGO APLIKASI ]</div></div>\n')

    # Title & Metadata
    lines.append(f"# {spec.get('title', labels['default_title'])}\n")
    if spec.get("subtitle"):
        lines.append(f"**{spec['subtitle']}**\n")
    meta_parts = []
    if spec.get("version"):
        meta_parts.append(f"**{labels['version']}**: {spec['version']}")
    if spec.get("date"):
        meta_parts.append(f"**{labels['date']}**: {spec['date']}")
    if meta_parts:
        lines.append(" | ".join(meta_parts) + "\n")

    # Cover occupies 1 full page
    lines.append('<div style="page-break-after: always;"></div>\n')

    # Table of Contents (anchor links only)
    lines.append(f"## {labels['toc']}\n")

    for ch in chapters:
        ch_num = ch.get("number")
        ch_title = ch.get("title", "")
        ch_anchor = f"umg-ch-{ch_num}"
        lines.append(f"- [{labels['chapter']} {ch_num}: {ch_title}](#{ch_anchor})")

        for sec in ch.get("sections", []):
            sec_num = sec.get("number", "")
            sec_title = sec.get("title", "")
            sec_slug = re.sub(r"[^\w-]", "", sec_num.replace(".", "-"))
            sec_anchor = f"umg-sec-{sec_slug}"
            lines.append(f"  - [{sec_num} {sec_title}](#{sec_anchor})")

    # Front-matter page break (Roman numeral 'i' conceptually)
    lines.append("\n---\n*i*")
    lines.append('<div style="page-break-after: always;"></div>\n')

    # Main Chapters (Arabic numerals starting at 1)
    for idx, ch in enumerate(chapters, start=1):
        ch_num = ch.get("number")
        ch_title = ch.get("title", "")
        ch_anchor = f"umg-ch-{ch_num}"

        lines.append(f'<a id="{ch_anchor}"></a>')
        lines.append(f"## {labels['chapter']} {ch_num}: {ch_title}\n")
        if ch.get("intro"):
            lines.append(f"{ch['intro']}\n")

        for sec in ch.get("sections", []):
            sec_num = sec.get("number", "")
            sec_title = sec.get("title", "")
            sec_slug = re.sub(r"[^\w-]", "", sec_num.replace(".", "-"))
            sec_anchor = f"umg-sec-{sec_slug}"

            figures = sec.get("figures", [])
            body_text = ensure_citation_in_text(sec.get("body", ""), figures, labels)

            lines.append(f'<a id="{sec_anchor}"></a>')
            lines.append(f"### {sec_num} {sec_title}\n")
            lines.append(f"{body_text}\n")

            for fig in figures:
                fig_id = str(fig.get("id", ""))
                fig_title = fig.get("title", "")
                fig_slug = re.sub(r"[^\w-]", "", fig_id.replace(".", "-"))
                fig_anchor = f"umg-fig-{fig_slug}"

                raw_img_path = fig.get("image_path", "")
                if raw_img_path:
                    abs_img = validate_workspace_path(raw_img_path, must_exist=False)
                    rel_img = os.path.relpath(abs_img, start=out_dir)
                else:
                    rel_img = ""

                caption = f"{labels['figure']} {fig_id}: {fig_title}"
                lines.append(f'<a id="{fig_anchor}"></a>')
                if rel_img:
                    lines.append('<div align="center">')
                    lines.append(f'  <img src="{rel_img}" alt="{caption}" style="max-width: 100%; max-height: 500px; height: auto;" /><br/>')
                    lines.append(f'  <p><em><b>{caption}</b></em></p>')
                    lines.append('</div>\n')
                else:
                    lines.append(f'<div align="center"><p><em><b>{caption}</b></em></p></div>\n')

                for bullet in fig.get("bullets", []):
                    lines.append(f"- {bullet}")
                lines.append("")

        # Footer shows single page number: *X*
        lines.append(f"---\n*{idx}*")
        if idx < len(chapters):
            lines.append('<div style="page-break-after: always;"></div>\n')

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).strip() + "\n")
    print(f"[OK] Markdown manual generated: {md_path}")


# ---------------------------------------------------------
# DOCX Low-level XML Helpers (Bookmarks, Hyperlinks, PAGEREF, Leaders)
# ---------------------------------------------------------
def _create_bookmark_id() -> int:
    global _CURRENT_BM_ID
    _CURRENT_BM_ID += 1
    return _CURRENT_BM_ID


_CURRENT_BM_ID = 100


def _add_bookmark_to_paragraph(paragraph: Any, bookmark_name: str) -> None:
    """Enclose paragraph content in a Word bookmark (alphanumeric, no underscores)."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    bm_id = str(_create_bookmark_id())
    bm_start = OxmlElement("w:bookmarkStart")
    bm_start.set(qn("w:id"), bm_id)
    bm_start.set(qn("w:name"), bookmark_name)

    bm_end = OxmlElement("w:bookmarkEnd")
    bm_end.set(qn("w:id"), bm_id)

    # In ECMA-376 schema, w:pPr must be the first child of w:p.
    # Therefore, insert bm_start immediately after pPr if present, else at index 0.
    pPr = paragraph._p.pPr
    if pPr is not None:
        pPr.addnext(bm_start)
    else:
        paragraph._p.insert(0, bm_start)
    paragraph._p.append(bm_end)


def _add_toc_entry_hyperlink(
    paragraph: Any,
    bookmark_name: str,
    title_text: str,
    page_str: str,
    is_bold: bool = False,
    indent_level: int = 0,
    tab_pos_dxa: int = 9029,
) -> None:
    """
    Construct a clickable TOC entry pointing to bookmark_name with dot leader and PAGEREF.
    """
    from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Inches, Pt, RGBColor

    p = paragraph._p
    pPr = paragraph._element.get_or_add_pPr()

    # Indentation
    if indent_level > 0:
        ind = OxmlElement("w:ind")
        ind.set(qn("w:left"), str(int(indent_level * 360)))  # ~0.25 inch per level
        pPr.append(ind)

    # Right-aligned tab stop with dot leader matching printable margin boundary (9029 dxa = 6.27 inches for A4)
    tabs = OxmlElement("w:tabs")
    tab = OxmlElement("w:tab")
    tab.set(qn("w:val"), "right")
    tab.set(qn("w:leader"), "dot")
    tab.set(qn("w:pos"), str(tab_pos_dxa))
    tabs.append(tab)
    pPr.append(tabs)

    # Create Hyperlink element: <w:hyperlink w:anchor="bookmark_name">
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("w:anchor"), bookmark_name)
    hyperlink.set(qn("w:history"), "1")

    # Run for Title Text
    r_text = OxmlElement("w:r")
    rPr_text = OxmlElement("w:rPr")
    if is_bold:
        b = OxmlElement("w:b")
        rPr_text.append(b)
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), "21")  # 10.5 pt
    rPr_text.append(sz)
    col = OxmlElement("w:color")
    col.set(qn("w:val"), "0F172A")
    rPr_text.append(col)
    r_text.append(rPr_text)

    t_text = OxmlElement("w:t")
    t_text.text = title_text
    r_text.append(t_text)
    hyperlink.append(r_text)

    # Run for Dot Leader Tab
    r_tab = OxmlElement("w:r")
    rPr_tab = OxmlElement("w:rPr")
    r_tab.append(rPr_tab)
    tab_elem = OxmlElement("w:tab")
    r_tab.append(tab_elem)
    hyperlink.append(r_tab)

    # Complex Field for PAGEREF:
    # 1. <w:fldChar w:fldCharType="begin"/>
    # 2. <w:instrText>PAGEREF bookmark_name \h</w:instrText>
    # 3. <w:fldChar w:fldCharType="separate"/>
    # 4. <w:t>page_str</w:t> (cached page number)
    # 5. <w:fldChar w:fldCharType="end"/>
    r_fld_begin = OxmlElement("w:r")
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    r_fld_begin.append(fld_begin)
    hyperlink.append(r_fld_begin)

    r_instr = OxmlElement("w:r")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f'PAGEREF {bookmark_name} \\h'
    r_instr.append(instr)
    hyperlink.append(r_instr)

    r_fld_sep = OxmlElement("w:r")
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    r_fld_sep.append(fld_sep)
    hyperlink.append(r_fld_sep)

    r_page = OxmlElement("w:r")
    rPr_page = OxmlElement("w:rPr")
    if is_bold:
        b_page = OxmlElement("w:b")
        rPr_page.append(b_page)
    sz_page = OxmlElement("w:sz")
    sz_page.set(qn("w:val"), "21")
    rPr_page.append(sz_page)
    r_page.append(rPr_page)
    t_page = OxmlElement("w:t")
    t_page.text = str(page_str)
    r_page.append(t_page)
    hyperlink.append(r_page)

    r_fld_end = OxmlElement("w:r")
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    r_fld_end.append(fld_end)
    hyperlink.append(r_fld_end)

    p.append(hyperlink)


def _add_page_number_only_footer(section: Any) -> None:
    """Attach single PAGE number field to footer, right-aligned (just *X*)."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    footer = section.footer
    p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    p.text = ""
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    fld_page = OxmlElement("w:fldSimple")
    fld_page.set(qn("w:instr"), "PAGE")
    p._p.append(fld_page)

    # Style runs
    for run in p.runs:
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(100, 116, 139)


def format_inline_markdown_html(text: str) -> str:
    """Convert inline markdown formatting (**bold**, *italic*, `code`) to HTML tags."""
    if not text:
        return ""
    import html
    escaped = html.escape(text)
    # **bold** or __bold__
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"__(.+?)__", r"<b>\1</b>", escaped)
    # *italic* or _italic_
    escaped = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", escaped)
    escaped = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"<i>\1</i>", escaped)
    # `code`
    escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
    return escaped


def _add_formatted_runs(paragraph: Any, text: str) -> None:
    """Parse **bold**, *italic*, and `code` segments into Word formatted runs."""
    if not text:
        return
    pattern = re.compile(r"(\*\*.*?\*\*|__.*?__|`.*?`|\*.*?\*)")
    tokens = pattern.split(text)
    for token in tokens:
        if not token:
            continue
        if (token.startswith("**") and token.endswith("**") and len(token) >= 4) or \
           (token.startswith("__") and token.endswith("__") and len(token) >= 4):
            run = paragraph.add_run(token[2:-2])
            run.bold = True
        elif token.startswith("`") and token.endswith("`") and len(token) >= 2:
            run = paragraph.add_run(token[1:-1])
            run.font.name = "Consolas"
        elif token.startswith("*") and token.endswith("*") and len(token) >= 2:
            run = paragraph.add_run(token[1:-1])
            run.italic = True
        else:
            paragraph.add_run(token)


def _enable_word_update_fields(doc: Any) -> None:
    """Enable w:updateFields in word/settings.xml so MS Word recomputes fields on open."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    settings = doc.settings._element
    update_fields = OxmlElement("w:updateFields")
    update_fields.set(qn("w:val"), "true")
    settings.append(update_fields)


# ---------------------------------------------------------
# DOCX Document Construction & A4 Layout Helpers
# ---------------------------------------------------------
def _calc_a4_image_dimensions(
    img_path: str,
    max_w: float = 5.8,
    max_h: float = 5.2,
) -> Tuple[float, float]:
    """Calculate scaled width and height in inches to prevent A4 paper overflow."""
    orig_w, orig_h = 1600, 900
    try:
        from PIL import Image as PILImage
        with PILImage.open(img_path) as im:
            orig_w, orig_h = im.size
    except Exception:
        try:
            with open(img_path, "rb") as f:
                head = f.read(32)
                if head.startswith(b"\x89PNG\r\n\x1a\n") and len(head) >= 24:
                    import struct
                    orig_w, orig_h = struct.unpack(">II", head[16:24])
        except Exception:
            pass

    if orig_w <= 0 or orig_h <= 0:
        return max_w, max_h

    aspect = orig_w / orig_h
    max_aspect = max_w / max_h

    if aspect >= max_aspect:
        w = max_w
        h = max_w / aspect
    else:
        h = max_h
        w = max_h * aspect

    return round(w, 3), round(h, 3)


def _apply_a4_page_setup(sec: Any) -> None:
    """Set standard A4 page dimensions (210mm x 297mm), 1.0 inch margins, and 0.5 inch header/footer distances."""
    try:
        from docx.shared import Inches
    except ImportError:
        class Inches:
            def __init__(self, val: float):
                self.inches = val
                self.val = val

            def __repr__(self):
                return f"Inches({self.inches})"
    sec.page_width = Inches(8.27)
    sec.page_height = Inches(11.69)
    sec.top_margin = Inches(1.0)
    sec.bottom_margin = Inches(1.0)
    sec.left_margin = Inches(1.0)
    sec.right_margin = Inches(1.0)
    sec.header_distance = Inches(0.5)
    sec.footer_distance = Inches(0.5)


def build_docx_internal(
    spec: Dict[str, Any],
    docx_path: str,
    page_map: Optional[Dict[str, str]] = None,
    enable_update_prompt: bool = True,
) -> None:
    """Build Word .docx document with exact sections, bookmarks, and cached page numbers."""
    try:
        from docx import Document
        from docx.enum.section import WD_SECTION
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Inches, Pt, RGBColor
    except ImportError:
        raise ImportError("python-docx is required. Run: pip install python-docx")

    labels = get_labels(spec.get("language", "en"))
    chapters = spec.get("chapters", [])
    page_map = page_map or {}

    doc = Document()
    if enable_update_prompt:
        try:
            _enable_word_update_fields(doc)
        except Exception:
            pass

    # =========================================================
    # Section 1: Cover Page (No footer, no page number)
    # =========================================================
    sec_cover = doc.sections[0]
    _apply_a4_page_setup(sec_cover)
    sec_cover.different_first_page_header_footer = True
    # Ensure first page header and footer are clean and empty
    if sec_cover.header.paragraphs:
        sec_cover.header.paragraphs[0].text = ""
    first_page_header = sec_cover.first_page_header
    if first_page_header.paragraphs:
        first_page_header.paragraphs[0].text = ""
    first_page_footer = sec_cover.first_page_footer
    if first_page_footer.paragraphs:
        first_page_footer.paragraphs[0].text = ""

    # Cover Logo or Placeholder Box
    logo_path = spec.get("logo_path")
    has_logo_file = False
    if logo_path:
        try:
            real_logo = validate_workspace_path(logo_path, must_exist=True)
            logo_p = doc.add_paragraph()
            logo_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            logo_p.paragraph_format.space_before = Pt(36)
            logo_p.paragraph_format.space_after = Pt(24)
            logo_p.add_run().add_picture(real_logo, width=Inches(2.5))
            has_logo_file = True
        except Exception:
            has_logo_file = False

    if not has_logo_file:
        logo_p = doc.add_paragraph("[ LOGO APLIKASI ]")
        logo_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        logo_p.paragraph_format.space_before = Pt(36)
        logo_p.paragraph_format.space_after = Pt(24)
        run_logo = logo_p.runs[0]
        run_logo.bold = True
        run_logo.font.size = Pt(13)
        run_logo.font.color.rgb = RGBColor(148, 163, 184)

    # Cover Title & Metadata
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_before = Pt(24)
    title_p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    title_run = title_p.add_run(spec.get("title", labels["default_title"]))
    title_run.bold = True
    title_run.font.size = Pt(26)
    title_run.font.color.rgb = RGBColor(15, 23, 42)

    if spec.get("subtitle"):
        sub_p = doc.add_paragraph()
        sub_run = sub_p.add_run(spec["subtitle"])
        sub_run.font.size = Pt(13)
        sub_run.font.color.rgb = RGBColor(71, 85, 105)

    meta_parts = []
    if spec.get("version"):
        meta_parts.append(f"{labels['version']}: {spec['version']}")
    if spec.get("date"):
        meta_parts.append(f"{labels['date']}: {spec['date']}")
    if meta_parts:
        meta_p = doc.add_paragraph(" | ".join(meta_parts))
        meta_p.paragraph_format.space_before = Pt(140)
        meta_p.runs[0].font.size = Pt(10)
        meta_p.runs[0].font.color.rgb = RGBColor(100, 116, 139)

    # =========================================================
    # Section 2: Front Matter (TOC) - Roman Numerals
    # =========================================================
    sec_front = doc.add_section(WD_SECTION.NEW_PAGE)
    _apply_a4_page_setup(sec_front)
    sec_front.header.is_linked_to_previous = False
    if sec_front.header.paragraphs:
        sec_front.header.paragraphs[0].text = ""
    sec_front.footer.is_linked_to_previous = False
    # Set Roman format: <w:pgNumType w:fmt="lowerRoman" w:start="1"/>
    sectPr_front = sec_front._sectPr
    pgNum_front = OxmlElement("w:pgNumType")
    pgNum_front.set(qn("w:fmt"), "lowerRoman")
    pgNum_front.set(qn("w:start"), "1")
    sectPr_front.append(pgNum_front)
    _add_page_number_only_footer(sec_front)

    # Table of Contents
    toc_heading = doc.add_heading(labels["toc"], level=1)
    toc_heading.paragraph_format.space_after = Pt(12)

    for ch_idx, ch in enumerate(chapters, start=1):
        ch_num = ch.get("number", ch_idx)
        ch_title = ch.get("title", "")
        ch_bm = f"umgCh{ch_num}"
        ch_page = page_map.get(ch_bm, "1")

        p_ch = doc.add_paragraph()
        p_ch.paragraph_format.space_before = Pt(6)
        p_ch.paragraph_format.space_after = Pt(2)
        _add_toc_entry_hyperlink(
            p_ch,
            bookmark_name=ch_bm,
            title_text=f"{labels['chapter']} {ch_num}: {ch_title}",
            page_str=ch_page,
            is_bold=True,
            indent_level=0,
        )

        for sec_idx, sec in enumerate(ch.get("sections", []), start=1):
            sec_num = sec.get("number", f"{ch_num}.{sec_idx}")
            sec_title = sec.get("title", "")
            sec_slug = re.sub(r"[^\w]", "", sec_num)
            sec_bm = f"umgSec{sec_slug}"
            sec_page = page_map.get(sec_bm, ch_page)

            p_sec = doc.add_paragraph()
            p_sec.paragraph_format.space_before = Pt(1)
            p_sec.paragraph_format.space_after = Pt(1)
            _add_toc_entry_hyperlink(
                p_sec,
                bookmark_name=sec_bm,
                title_text=f"{sec_num} {sec_title}",
                page_str=sec_page,
                is_bold=False,
                indent_level=1,
            )

    # =========================================================
    # Section 3: Main Chapters - Arabic Numerals (1, 2, 3...)
    # =========================================================
    sec_main = doc.add_section(WD_SECTION.NEW_PAGE)
    _apply_a4_page_setup(sec_main)
    sec_main.header.is_linked_to_previous = False
    if sec_main.header.paragraphs:
        sec_main.header.paragraphs[0].text = ""
    sec_main.footer.is_linked_to_previous = False
    sectPr_main = sec_main._sectPr
    pgNum_main = OxmlElement("w:pgNumType")
    pgNum_main.set(qn("w:fmt"), "decimal")
    pgNum_main.set(qn("w:start"), "1")
    sectPr_main.append(pgNum_main)
    _add_page_number_only_footer(sec_main)

    for idx, ch in enumerate(chapters, start=1):
        ch_num = ch.get("number", idx)
        ch_title = ch.get("title", "")
        ch_bm = f"umgCh{ch_num}"

        h1 = doc.add_heading(f"{labels['chapter']} {ch_num}: {ch_title}", level=1)
        _add_bookmark_to_paragraph(h1, ch_bm)

        if ch.get("intro"):
            intro_p = doc.add_paragraph()
            intro_p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            _add_formatted_runs(intro_p, ch["intro"])

        ch_fig_counter = 0
        for sec_idx, sec in enumerate(ch.get("sections", []), start=1):
            sec_num = sec.get("number", f"{ch_num}.{sec_idx}")
            sec_title = sec.get("title", "")
            sec_slug = re.sub(r"[^\w]", "", sec_num)
            sec_bm = f"umgSec{sec_slug}"

            figures = sec.get("figures", [])
            body_text = ensure_citation_in_text(sec.get("body", ""), figures, labels)

            h2 = doc.add_heading(f"{sec_num} {sec_title}", level=2)
            _add_bookmark_to_paragraph(h2, sec_bm)

            body_p = doc.add_paragraph()
            body_p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            _add_formatted_runs(body_p, body_text)

            for fig in figures:
                ch_fig_counter += 1
                fig_id = str(fig.get("id", f"{ch_num}.{ch_fig_counter}"))
                fig_title = fig.get("title", "")
                fig_slug = re.sub(r"[^\w]", "", fig_id)
                fig_bm = f"umgFig{fig_slug}"

                img_path = fig.get("image_path", "")
                if img_path:
                    real_img = validate_workspace_path(img_path, must_exist=True)
                    img_w_in, img_h_in = _calc_a4_image_dimensions(real_img, max_w=5.8, max_h=5.2)
                    img_p = doc.add_paragraph()
                    img_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    img_p.paragraph_format.keep_with_next = True
                    img_p.add_run().add_picture(real_img, width=Inches(img_w_in), height=Inches(img_h_in))

                cap_p = doc.add_paragraph()
                cap_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                cap_run = cap_p.add_run(f"{labels['figure']} {fig_id}: {fig_title}")
                cap_run.italic = True
                cap_run.bold = True
                cap_run.font.size = Pt(10)
                cap_run.font.color.rgb = RGBColor(51, 65, 85)
                _add_bookmark_to_paragraph(cap_p, fig_bm)

                for bullet in fig.get("bullets", []):
                    b_p = doc.add_paragraph(style="List Bullet")
                    b_p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                    _add_formatted_runs(b_p, bullet)

        if idx < len(chapters):
            doc.add_page_break()

    doc.save(docx_path)


# ---------------------------------------------------------
# Sandboxed LibreOffice Helper & Page Number Resolution
# ---------------------------------------------------------
def run_soffice(args: List[str], timeout: int = 60) -> subprocess.CompletedProcess:
    """
    Run LibreOffice in headless mode with an isolated temporary user profile in /tmp
    to guarantee safe execution without dconf read-only filesystem errors in Linux sandboxes.
    """
    soffice_bin = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice_bin:
        raise FileNotFoundError("LibreOffice ('soffice') executable not found.")

    profile_dir = tempfile.mkdtemp(prefix="lo_prof_", dir="/tmp")
    cmd = [
        soffice_bin,
        f"-env:UserInstallation=file://{profile_dir}",
        "--headless",
        *args,
    ]
    try:
        env = os.environ.copy()
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            env=env,
        )
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)


def export_docx_to_pdf_official(docx_path: str, out_dir: str) -> Optional[str]:
    """
    Export official PDF from generated DOCX document using sandboxed headless LibreOffice.
    """
    soffice_bin = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice_bin:
        print("[WARNING] LibreOffice not found. Skipping official PDF export.")
        return None

    if not os.path.isfile(docx_path):
        print(f"[ERROR] Cannot export PDF: DOCX source not found: {docx_path}")
        return None

    try:
        os.makedirs(out_dir, exist_ok=True)
        args = [
            "--convert-to",
            "pdf",
            "--outdir",
            out_dir,
            os.path.abspath(docx_path),
        ]
        res = run_soffice(args, timeout=90)
        base = os.path.splitext(os.path.basename(docx_path))[0]
        pdf_out = os.path.join(out_dir, f"{base}.pdf")
        if os.path.isfile(pdf_out):
            print(f"[OK] Official PDF manual exported: {pdf_out}")
            return pdf_out
        else:
            print(f"[WARNING] LibreOffice PDF export produced no file: {res.stderr}")
            return None
    except Exception as err:
        print(f"[ERROR] Official PDF export failed: {err}")
        return None


def render_docx_to_pdf_libreoffice(docx_path: str, temp_dir: str) -> Optional[str]:
    """Convert DOCX to PDF using headless LibreOffice with sandboxed profile."""
    soffice_bin = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice_bin:
        return None

    try:
        args = [
            "--convert-to",
            'pdf:writer_pdf_Export:{"ExportBookmarksToPDFDestination":{"type":"boolean","value":"true"}}',
            "--outdir",
            temp_dir,
            os.path.abspath(docx_path),
        ]
        proc = run_soffice(args, timeout=60)
        base = os.path.splitext(os.path.basename(docx_path))[0]
        pdf_path = os.path.join(temp_dir, f"{base}.pdf")
        if os.path.isfile(pdf_path):
            return pdf_path
        print(f"[WARNING] LibreOffice PDF conversion produced no output: {proc.stderr}")
    except Exception as err:
        print(f"[WARNING] LibreOffice PDF conversion failed: {err}")
    return None


def extract_page_map_from_pdf(
    pdf_path: str, spec: Dict[str, Any]
) -> Dict[str, str]:
    """
    Extract exact page numbers for each chapter, section, and figure bookmark.
    Uses pypdf to parse page texts and locate headings in the rendered document body.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        print("[WARNING] pypdf is not installed. Run: pip install pypdf")
        return {}

    labels = get_labels(spec.get("language", "en"))
    reader = PdfReader(pdf_path)
    page_map: Dict[str, str] = {}

    def _clean_ws(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip().lower()

    # Extract text from every page and clean whitespace
    page_texts: List[str] = []
    for page in reader.pages:
        page_texts.append(_clean_ws(page.extract_text() or ""))

    # Identify end of front-matter (TOC)
    # The first occurrence of Chapter 1 heading marks start of main content
    first_ch_heading = _clean_ws(f"{labels['chapter']} 1")
    toc_label = _clean_ws(labels["toc"])
    main_start_page_idx = 1
    for idx, text in enumerate(page_texts):
        # Skip cover page (idx 0)
        if idx == 0:
            continue
        # If page contains chapter 1 heading and is not the TOC page
        if first_ch_heading in text and toc_label not in text:
            main_start_page_idx = idx
            break

    # Resolve bookmarks for chapters, sections, and figures
    for ch_idx, ch in enumerate(spec.get("chapters", []), start=1):
        ch_num = ch.get("number", ch_idx)
        ch_title = ch.get("title", "")
        ch_bm = f"umgCh{ch_num}"
        target_phrase = _clean_ws(f"{labels['chapter']} {ch_num}: {ch_title}")

        found_page = None
        for p_idx in range(main_start_page_idx, len(page_texts)):
            if target_phrase in page_texts[p_idx]:
                found_page = str(p_idx - main_start_page_idx + 1)
                break
        if found_page:
            page_map[ch_bm] = found_page

        ch_fig_counter = 0
        for sec_idx, sec in enumerate(ch.get("sections", []), start=1):
            sec_num = sec.get("number", f"{ch_num}.{sec_idx}")
            sec_title = sec.get("title", "")
            sec_slug = re.sub(r"[^\w]", "", sec_num)
            sec_bm = f"umgSec{sec_slug}"
            target_sec = _clean_ws(f"{sec_num} {sec_title}")

            sec_found = None
            for p_idx in range(main_start_page_idx, len(page_texts)):
                if target_sec in page_texts[p_idx]:
                    sec_found = str(p_idx - main_start_page_idx + 1)
                    break
            if sec_found:
                page_map[sec_bm] = sec_found

            for fig in sec.get("figures", []):
                ch_fig_counter += 1
                fig_id = str(fig.get("id", f"{ch_num}.{ch_fig_counter}"))
                fig_title = fig.get("title", "")
                fig_slug = re.sub(r"[^\w]", "", fig_id)
                fig_bm = f"umgFig{fig_slug}"
                target_fig = _clean_ws(f"{labels['figure']} {fig_id}: {fig_title}")

                fig_found = None
                for p_idx in range(main_start_page_idx, len(page_texts)):
                    if target_fig in page_texts[p_idx]:
                        fig_found = str(p_idx - main_start_page_idx + 1)
                        break
                if fig_found:
                    page_map[fig_bm] = fig_found

    return page_map


def build_docx_via_libreoffice(
    spec: Dict[str, Any], docx_path: str, out_dir: str
) -> bool:
    """Fallback compiler: Build structured HTML and convert to .docx via headless LibreOffice."""
    soffice_bin = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice_bin:
        return False

    labels = get_labels(spec.get("language", "en"))
    chapters = spec.get("chapters", [])
    temp_dir = tempfile.mkdtemp(prefix="umg_lo_")
    try:
        # Precompute estimated page map for TOC
        curr_page = 1
        est_map: Dict[str, str] = {}
        for ch_idx, ch in enumerate(chapters, start=1):
            ch_num = ch.get("number", ch_idx)
            est_map[f"umgCh{ch_num}"] = str(curr_page)
            ch_fig_counter = 0
            for sec_idx, sec in enumerate(ch.get("sections", []), start=1):
                sec_num = sec.get("number", f"{ch_num}.{sec_idx}")
                sec_slug = re.sub(r"[^\w]", "", str(sec_num))
                est_map[f"umgSec{sec_slug}"] = str(curr_page)
                for fig in sec.get("figures", []):
                    ch_fig_counter += 1
                    fig_id = str(fig.get("id", f"{ch_num}.{ch_fig_counter}"))
                    fig_slug = re.sub(r"[^\w]", "", str(fig_id))
                    est_map[f"umgFig{fig_slug}"] = str(curr_page)
            curr_page += 1

        html_lines = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            '<meta charset="utf-8">',
            "<style>",
            "@page { size: 210mm 297mm; margin-top: 25.4mm; margin-bottom: 25.4mm; margin-left: 25.4mm; margin-right: 25.4mm; mso-header-margin: 12.7mm; mso-footer-margin: 12.7mm; mso-footer: f1; }",
            '@page:first { @bottom-center { content: ""; } }',
            "body { font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #0f172a; margin: 0; }",
            ".cover-table { width: 100%; max-width: 100%; height: 220mm; border: none; border-collapse: collapse; table-layout: fixed; box-sizing: border-box; }",
            ".cover-logo-box { border: 2px dashed #94a3b8; padding: 24pt 36pt; border-radius: 8px; color: #64748b; font-weight: bold; font-size: 14pt; display: inline-block; }",
            "h1.title { font-size: 26pt; font-weight: bold; margin-top: 24pt; margin-bottom: 8pt; color: #0f172a; }",
            "p.subtitle { font-size: 13pt; color: #475569; margin-bottom: 20pt; }",
            ".cover-meta { border-top: 1px solid #cbd5e1; padding-top: 14pt; margin-top: 20pt; }",
            "p.meta { font-size: 10pt; color: #64748b; margin-bottom: 8pt; }",
            "h1 { font-size: 18pt; margin-top: 24pt; margin-bottom: 12pt; border-bottom: 1px solid #e2e8f0; padding-bottom: 4pt; }",
            "h2 { font-size: 14pt; margin-top: 18pt; margin-bottom: 8pt; }",
            "p { font-size: 11pt; margin-bottom: 8pt; text-align: justify; text-justify: inter-word; line-height: 1.5; }",
            "ul { margin-bottom: 12pt; }",
            "li { font-size: 11pt; margin-bottom: 4pt; text-align: justify; text-justify: inter-word; line-height: 1.5; }",
            ".center { text-align: center; margin: 16pt auto; }",
            ".center img { max-width: 5.8in; max-height: 5.2in; height: auto; }",
            ".caption { font-size: 10pt; font-style: italic; font-weight: bold; color: #334155; margin-top: 6pt; text-align: center; }",
            ".page-break { page-break-after: always; break-after: page; mso-break-type: section-break; }",
            "table.toc-table { width: 100%; max-width: 100%; border: none; border-collapse: collapse; box-sizing: border-box; }",
            "table.toc-table td { border: none; }",
            "</style>",
            "</head>",
            "<body>",
            "<div title='footer' style='mso-element:footer' id='f1'>",
            "<p align='center' style='text-align:center; font-size:10pt; color:#64748b; margin:0;'>",
            "<!--[if supportFields]><span style='mso-element:field-begin'></span>PAGE<span style='mso-element:field-end'></span><![endif]-->",
            "<sdfield type=PAGE SUBTYPE=RANDOM>1</sdfield>",
            "</p>",
            "</div>",
        ]

        # Cover page (1 Full Page via controlled table layout)
        logo_path = spec.get("logo_path")
        logo_html = ""
        if logo_path:
            try:
                abs_logo = validate_workspace_path(logo_path, must_exist=True)
                logo_html = (
                    f"<div align='center' style='margin-bottom: 24pt;'>"
                    f"<img src='file://{os.path.abspath(abs_logo)}' alt='Logo' style='max-height: 90px; max-width: 250px;' />"
                    f"</div>"
                )
            except Exception:
                logo_html = ""

        if not logo_html:
            logo_html = (
                "<div align='center' style='margin-bottom: 24pt;'>"
                "<div class='cover-logo-box'>[ LOGO APLIKASI ]</div>"
                "</div>"
            )

        title = spec.get("title", labels["default_title"])
        subtitle_html = ""
        if spec.get("subtitle"):
            subtitle_html = f"<p class='subtitle'>{spec['subtitle']}</p>"

        meta_parts = []
        if spec.get("version"):
            meta_parts.append(f"<b>{labels['version']}</b>: {spec['version']}")
        if spec.get("date"):
            meta_parts.append(f"<b>{labels['date']}</b>: {spec['date']}")
        meta_html = ""
        if meta_parts:
            meta_html = f"<div class='cover-meta'><p class='meta'>{' &nbsp;|&nbsp; '.join(meta_parts)}</p></div>"

        html_lines.append("<table class='cover-table' style='width:100%; height:220mm; border:none; border-collapse:collapse; table-layout:fixed;'>")
        html_lines.append("<tr><td style='vertical-align:top; text-align:center; padding-top:20pt; border:none;'>")
        html_lines.append(logo_html)
        html_lines.append(f"<h1 class='title'>{title}</h1>")
        if subtitle_html:
            html_lines.append(subtitle_html)
        html_lines.append("</td></tr>")
        html_lines.append("<tr><td style='vertical-align:bottom; padding-bottom:20pt; border:none;'>")
        if meta_html:
            html_lines.append(meta_html)
        html_lines.append("</td></tr>")
        html_lines.append("</table>")
        html_lines.append("<div class='page-break' style='page-break-after:always; mso-break-type:section-break;'><br style='page-break-before:always; clear:both;' /></div>")

        # Table of Contents & List of Figures (Page 2)
        html_lines.append(f"<h1>{labels['toc']}</h1>")
        html_lines.append("<table class='toc-table' style='width:100%; border:none; border-collapse:collapse;'>")
        for ch_idx, ch in enumerate(chapters, start=1):
            ch_num = ch.get("number", ch_idx)
            ch_title = ch.get("title", "")
            bm_ch = f"umgCh{ch_num}"
            ch_page = est_map.get(bm_ch, str(ch_idx))
            html_lines.append(
                f"<tr>"
                f"<td style='padding:4pt 0; border:none;'><a href='#{bm_ch}' style='text-decoration:none; color:#0f172a; font-weight:bold;'>"
                f"{labels['chapter']} {ch_num}: {ch_title}</a></td>"
                f"<td style='padding:4pt 0; text-align:right; white-space:nowrap; border:none;'><a href='#{bm_ch}' style='text-decoration:none; color:#64748b; font-weight:bold;'>"
                f"{ch_page}</a></td>"
                f"</tr>"
            )
            for sec_idx, sec in enumerate(ch.get("sections", []), start=1):
                sec_num = sec.get("number", f"{ch_num}.{sec_idx}")
                sec_title = sec.get("title", "")
                sec_slug = re.sub(r"[^\w]", "", str(sec_num))
                bm_sec = f"umgSec{sec_slug}"
                sec_page = est_map.get(bm_sec, ch_page)
                html_lines.append(
                    f"<tr>"
                    f"<td style='padding:2pt 0 2pt 20pt; border:none;'><a href='#{bm_sec}' style='text-decoration:none; color:#334155;'>"
                    f"{sec_num} {sec_title}</a></td>"
                    f"<td style='padding:2pt 0; text-align:right; white-space:nowrap; border:none;'><a href='#{bm_sec}' style='text-decoration:none; color:#64748b;'>"
                    f"{sec_page}</a></td>"
                    f"</tr>"
                )
        html_lines.append("</table>")

        # Strict page break so Chapter 1 starts on a new page!
        html_lines.append("<div class='page-break' style='page-break-after:always; mso-break-type:section-break;'><br style='page-break-before:always; clear:both;' /></div>")

        # Chapters (Starting on new page)
        for ch_idx, ch in enumerate(chapters, start=1):
            ch_num = ch.get("number", ch_idx)
            ch_title = ch.get("title", "")
            bm_ch = f"umgCh{ch_num}"

            html_lines.append(f"<a id='{bm_ch}' name='{bm_ch}'></a>")
            html_lines.append(f"<h1>{labels['chapter']} {ch_num}: {ch_title}</h1>")
            if ch.get("intro"):
                html_lines.append(f"<p align='justify'>{format_inline_markdown_html(ch['intro'])}</p>")

            ch_fig_counter = 0
            for sec_idx, sec in enumerate(ch.get("sections", []), start=1):
                sec_num = sec.get("number", f"{ch_num}.{sec_idx}")
                sec_title = sec.get("title", "")
                sec_slug = re.sub(r"[^\w]", "", str(sec_num))
                bm_sec = f"umgSec{sec_slug}"

                figures = sec.get("figures", [])
                body_text = ensure_citation_in_text(sec.get("body", ""), figures, labels)

                html_lines.append(f"<a id='{bm_sec}' name='{bm_sec}'></a>")
                html_lines.append(f"<h2>{sec_num} {sec_title}</h2>")
                html_lines.append(f"<p align='justify'>{format_inline_markdown_html(body_text)}</p>")

                for fig in figures:
                    ch_fig_counter += 1
                    fig_id = str(fig.get("id", f"{ch_num}.{ch_fig_counter}"))
                    fig_title = fig.get("title", "")
                    fig_slug = re.sub(r"[^\w]", "", str(fig_id))
                    bm_fig = f"umgFig{fig_slug}"
                    img_path = fig.get("image_path", "")
                    caption = f"{labels['figure']} {fig_id}: {fig_title}"

                    html_lines.append(f"<a id='{bm_fig}' name='{bm_fig}'></a>")
                    if img_path:
                        abs_img = validate_workspace_path(img_path, must_exist=False)
                        if os.path.exists(abs_img):
                            html_lines.append(
                                f"<div class='center' align='center'>"
                                f"<img src='file://{os.path.abspath(abs_img)}' alt='{caption}' /><br/>"
                                f"<p class='caption'><em><b>{caption}</b></em></p>"
                                f"</div>"
                            )
                        else:
                            html_lines.append(
                                f"<div class='center' align='center'>"
                                f"<p class='caption'><em><b>{caption}</b></em></p>"
                                f"</div>"
                            )
                    else:
                        html_lines.append(
                            f"<div class='center' align='center'>"
                            f"<p class='caption'><em><b>{caption}</b></em></p>"
                            f"</div>"
                        )

                    bullets = fig.get("bullets", [])
                    if bullets:
                        html_lines.append("<ul>")
                        for b in bullets:
                            html_lines.append(f"<li align='justify'>{format_inline_markdown_html(b)}</li>")
                        html_lines.append("</ul>")

            if ch_idx < len(chapters):
                html_lines.append("<div class='page-break' style='page-break-after:always; mso-break-type:section-break;'><br style='page-break-before:always; clear:both;' /></div>")

        html_lines.append("</body></html>")

        html_file = os.path.join(temp_dir, "manual.html")
        with open(html_file, "w", encoding="utf-8") as f:
            f.write("\n".join(html_lines))

        args = [
            "--convert-to",
            "docx:Office Open XML Text",
            html_file,
            "--outdir",
            temp_dir,
        ]
        res = run_soffice(args, timeout=60)
        converted_docx = os.path.join(temp_dir, "manual.docx")
        if os.path.isfile(converted_docx):
            shutil.copy2(converted_docx, docx_path)
            # Post-process: embed external linked images and constrain to A4 margins
            if embed_images_in_docx:
                embed_images_in_docx(docx_path, max_w_inches=5.8)
            print(f"[OK] DOCX manual generated via LibreOffice fallback: {docx_path}")
            return True
        else:
            print(f"[WARNING] LibreOffice DOCX conversion produced no output: {res.stderr}")
            return False
    except Exception as err:
        print(f"[WARNING] LibreOffice fallback failed: {err}")
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def build_docx_2pass(
    spec: Dict[str, Any],
    docx_path: str,
    page_source: str = "auto",
    no_update_prompt: bool = False,
    out_dir: Optional[str] = None,
) -> bool:
    """
    Two-pass compiler:
    Pass 1: Build draft with estimated page numbers using python-docx.
    Pass 2: Render PDF, compute exact page numbers via pypdf, rebuild with exact page numbers.
    Fallback: If python-docx is not installed, use LibreOffice fallback.
    """
    try:
        import docx
    except ImportError:
        print("[NOTICE] python-docx is not installed. Attempting LibreOffice conversion fallback...")
        target_dir = out_dir or os.path.dirname(docx_path) or "."
        success = build_docx_via_libreoffice(spec, docx_path, target_dir)
        if not success:
            print(
                "[NOTICE] Neither python-docx nor LibreOffice is available. Skipping .docx generation. "
                "The Markdown manual was successfully generated."
            )
        return success

    enable_update_prompt = not no_update_prompt
    temp_dir = tempfile.mkdtemp(prefix="umg_build_")
    try:
        # Initial estimate map
        curr_page = 1
        est_map: Dict[str, str] = {}
        for ch_idx, ch in enumerate(spec.get("chapters", []), start=1):
            ch_num = ch.get("number", ch_idx)
            est_map[f"umgCh{ch_num}"] = str(curr_page)
            ch_fig_counter = 0
            for sec_idx, sec in enumerate(ch.get("sections", []), start=1):
                sec_num = sec.get("number", f"{ch_num}.{sec_idx}")
                sec_slug = re.sub(r"[^\w]", "", sec_num)
                est_map[f"umgSec{sec_slug}"] = str(curr_page)
                for fig in sec.get("figures", []):
                    ch_fig_counter += 1
                    fig_id = str(fig.get("id", f"{ch_num}.{ch_fig_counter}"))
                    fig_slug = re.sub(r"[^\w]", "", fig_id)
                    est_map[f"umgFig{fig_slug}"] = str(curr_page)
            curr_page += 1

        # Pass 1 build
        build_docx_internal(spec, docx_path, page_map=est_map, enable_update_prompt=enable_update_prompt)

        # Check page_source
        pdf_path = None
        if page_source == "none":
            print("[NOTICE] --page-source none: Using Word field PAGEREF with estimated preview numbers.")
            print("[OK] DOCX manual generated: " + docx_path)
            return True
        elif page_source.startswith("pdf:"):
            custom_pdf = page_source.split(":", 1)[1]
            pdf_path = validate_workspace_path(custom_pdf, must_exist=True)
        elif page_source == "auto":
            pdf_path = render_docx_to_pdf_libreoffice(docx_path, temp_dir)

        if pdf_path and os.path.isfile(pdf_path):
            exact_map = extract_page_map_from_pdf(pdf_path, spec)
            if exact_map:
                # Pass 2 build with exact page numbers
                build_docx_internal(
                    spec, docx_path, page_map=exact_map, enable_update_prompt=enable_update_prompt
                )
                print(f"[OK] Resolved {len(exact_map)} exact page numbers via rendered PDF.")
            else:
                print("[NOTICE] PDF parsed but no bookmarks mapped. Keeping estimated layout.")
        else:
            print(
                "[NOTICE] LibreOffice not available for auto PDF render. DOCX contains dynamic PAGEREF fields that update automatically when opened in Word."
            )

        print(f"[OK] DOCX manual generated: {docx_path}")
        return True
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------------
# Verification Suite
# ---------------------------------------------------------
def verify_outputs(
    md_path: Optional[str] = None,
    docx_path: Optional[str] = None,
    pdf_path: Optional[str] = None,
) -> bool:
    """Validate hyperlinks, bookmark integrity, embedded media, and PDF standards."""
    all_ok = True
    print("\n=== Output Verification ===")

    # Verify Markdown
    if md_path:
        if os.path.isfile(md_path):
            with open(md_path, "r", encoding="utf-8") as f:
                md_text = f.read()

            anchors_in_md = set(re.findall(r'<a id="([^"]+)"></a>', md_text))
            links_in_md = set(re.findall(r'\]\(#(umg-[^)]+)\)', md_text))

            missing_md = links_in_md - anchors_in_md
            if missing_md:
                print(f"[FAIL] MD has broken internal links: {missing_md}")
                all_ok = False
            else:
                print(f"[PASS] MD: All {len(links_in_md)} TOC links have valid anchors.")

            # Check footer pattern
            footers = re.findall(r"^---$\n^\*([^*]+)\*$", md_text, re.MULTILINE)
            invalid_footers = [ft for ft in footers if "halaman" in ft.lower() or "page" in ft.lower()]
            if invalid_footers:
                print(f"[FAIL] MD footers contain 'Page/Halaman' instead of plain number: {invalid_footers}")
                all_ok = False
            else:
                print(f"[PASS] MD: Footers formatted as plain page numbers.")
        else:
            print(f"[FAIL] MD file not found: {md_path}")
            all_ok = False

    # Verify DOCX
    if docx_path:
        if os.path.isfile(docx_path):
            import zipfile
            import xml.etree.ElementTree as ET

            try:
                with zipfile.ZipFile(docx_path, "r") as z:
                    xml_info = z.getinfo("word/document.xml")
                    if xml_info.file_size > 20_000_000:
                        raise ValueError(
                            f"Safety Error: document.xml uncompressed size ({xml_info.file_size} bytes) exceeds 20MB limit."
                        )
                    doc_xml = z.read("word/document.xml")
                    root = ET.fromstring(doc_xml)

                    ns = {
                        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                    }

                    bookmarks = {el.attrib.get(f"{{{ns['w']}}}name") for el in root.iter(f"{{{ns['w']}}}bookmarkStart")}
                    hyperlinks = {el.attrib.get(f"{{{ns['w']}}}anchor") for el in root.iter(f"{{{ns['w']}}}hyperlink") if el.attrib.get(f"{{{ns['w']}}}anchor")}

                    missing_bm = {h for h in hyperlinks if h and h.startswith("umg") and h not in bookmarks}
                    if missing_bm:
                        print(f"[FAIL] DOCX has hyperlinks pointing to missing bookmarks: {missing_bm}")
                        all_ok = False
                    else:
                        print(f"[PASS] DOCX: All {len(hyperlinks)} internal hyperlinks match valid bookmarks.")

                    # Inspect embedded media and external links
                    namelist = z.namelist()
                    media_files = [f for f in namelist if f.startswith("word/media/")]
                    rels_data = ""
                    if "word/_rels/document.xml.rels" in namelist:
                        rels_data = z.read("word/_rels/document.xml.rels").decode("utf-8", errors="ignore")

                    external_imgs = [
                        m
                        for m in re.findall(
                            r'<Relationship[^>]+Target="([^"]+)"[^>]+TargetMode="External"',
                            rels_data,
                        )
                        if any(m.lower().endswith(e) for e in [".png", ".jpg", ".jpeg", ".webp"])
                    ]
                    if external_imgs:
                        print(f"[FAIL] DOCX contains un-embedded external image links: {external_imgs}")
                        all_ok = False
                    else:
                        print(f"[PASS] DOCX: All images properly embedded ({len(media_files)} files in word/media/).")

            except Exception as err:
                print(f"[WARNING] DOCX XML inspection failed: {err}")
        else:
            print(f"[FAIL] DOCX file not found: {docx_path}")
            all_ok = False

    # Verify PDF
    if pdf_path:
        if os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 0:
            print(f"[PASS] PDF: Official PDF exists ({os.path.getsize(pdf_path)} bytes).")
        else:
            print(f"[FAIL] PDF file not found or empty: {pdf_path}")
            all_ok = False

    return all_ok


# ---------------------------------------------------------
# Main CLI
# ---------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Markdown (.md) and Word (.docx) user manuals from manual_spec.json."
    )
    parser.add_argument(
        "--spec",
        default="docs/manual_book/manual_spec.json",
        help="Path to manual_spec.json (default: docs/manual_book/manual_spec.json).",
    )
    parser.add_argument(
        "--out-dir",
        default="docs/manual_book",
        help="Output directory inside workspace (default: docs/manual_book).",
    )
    parser.add_argument("--basename", default="Manual_Book", help="Base filename without extension.")
    parser.add_argument(
        "--format",
        choices=["all", "md", "docx", "pdf"],
        default="all",
        help="Target output format: 'all' (.md and .docx), 'md' (.md only), 'docx' (.docx only), or 'pdf' (.pdf official export). Default: 'all'.",
    )
    parser.add_argument(
        "--export-pdf",
        action="store_true",
        help="Also export an official PDF (.pdf) alongside the generated documents via sandboxed LibreOffice.",
    )
    parser.add_argument(
        "--page-source",
        default="auto",
        help="Page resolution mode: 'auto' (LibreOffice render), 'pdf:<path>' (use existing PDF), or 'none' (rely on Word fields).",
    )
    parser.add_argument(
        "--no-word-update-prompt",
        action="store_true",
        help="Disable automatic update prompt when opening in Microsoft Word.",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Do not archive previous outputs before building.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run verification on generated artifacts.",
    )
    args = parser.parse_args()

    try:
        spec_path = validate_workspace_path(args.spec, must_exist=True)
        out_dir = validate_workspace_path(args.out_dir, must_exist=False)
        os.makedirs(out_dir, exist_ok=True)

        if not re.match(r"^[A-Za-z0-9_-]+$", args.basename):
            raise ValueError(
                "Validation Error: --basename may only contain letters, digits, underscores, and hyphens."
            )

        with open(spec_path, "r", encoding="utf-8") as f:
            spec_data = json.load(f)

        md_out = os.path.join(out_dir, f"{args.basename}.md")
        docx_out = os.path.join(out_dir, f"{args.basename}.docx")
        pdf_out = os.path.join(out_dir, f"{args.basename}.pdf")

        format_choice = args.format.lower()
        should_build_md = format_choice in ("all", "md")
        should_build_docx = format_choice in ("all", "docx", "pdf")
        should_export_pdf = args.export_pdf or format_choice == "pdf"

        # Archive existing outputs before rebuilding
        if not args.no_archive and (
            (should_build_md and os.path.exists(md_out))
            or (should_build_docx and os.path.exists(docx_out))
            or (should_export_pdf and os.path.exists(pdf_out))
        ):
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_dir = os.path.join(out_dir, "archive", f"{args.basename}_{ts}")
            os.makedirs(archive_dir, exist_ok=True)
            if should_build_md and os.path.exists(md_out):
                shutil.copy2(md_out, archive_dir)
            if should_build_docx and os.path.exists(docx_out):
                shutil.copy2(docx_out, archive_dir)
            if should_export_pdf and os.path.exists(pdf_out):
                shutil.copy2(pdf_out, archive_dir)
            print(f"[OK] Archived previous outputs to: {archive_dir}")

        if should_build_md:
            build_markdown(spec_data, md_out, out_dir)

        docx_built = False
        if should_build_docx:
            docx_built = build_docx_2pass(
                spec_data,
                docx_out,
                page_source=args.page_source,
                no_update_prompt=args.no_word_update_prompt,
                out_dir=out_dir,
            )

        pdf_created = None
        if should_export_pdf and docx_built:
            pdf_created = export_docx_to_pdf_official(docx_out, out_dir)

        # Run verification automatically or when requested
        verify_outputs(
            md_path=md_out if should_build_md else None,
            docx_path=docx_out if (should_build_docx and docx_built) else None,
            pdf_path=pdf_out if (should_export_pdf and pdf_created) else None,
        )

    except Exception as err:
        sys.exit(f"[ERROR] {err}")


if __name__ == "__main__":
    main()
