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
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
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
            "logo_placeholder": "[ LOGO APLIKASI ]",
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
        "logo_placeholder": "[ APPLICATION LOGO ]",
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


def resolve_spec_asset_path(
    raw_path: str,
    spec_dir: Optional[str] = None,
    out_dir: Optional[str] = None,
    must_exist: bool = False,
) -> str:
    """
    Resolve an asset path from manual_spec.json inside the active workspace.
    Falls back to spec_dir / out_dir (including portable 'assets/...' suffixes)
    when a manual folder has been relocated or renamed from 'docs/manual_book/'.
    """
    if not raw_path:
        raise ValueError("Empty asset path.")

    primary = validate_workspace_path(raw_path, must_exist=False)
    if os.path.exists(primary):
        return primary

    norm = raw_path.replace("\\", "/")
    assets_idx = norm.find("assets/")
    suffix = norm[assets_idx:] if assets_idx >= 0 else None

    for base_dir in (spec_dir, out_dir):
        if not base_dir:
            continue
        for rel_cand in (raw_path, suffix):
            if not rel_cand:
                continue
            try:
                cand = validate_workspace_path(os.path.join(base_dir, rel_cand), must_exist=False)
                if os.path.exists(cand):
                    return cand
            except Exception:
                continue

    if norm.startswith("assets/") and (spec_dir or out_dir):
        return validate_workspace_path(
            os.path.join(spec_dir or out_dir or ".", raw_path), must_exist=must_exist
        )
    return validate_workspace_path(raw_path, must_exist=must_exist)


def normalize_prose_arrows(text: str) -> str:
    """Replace raw ASCII arrows (' -> ') outside inline code spans with typographic ' → '."""
    if not text or "->" not in text:
        return text
    parts = re.split(r"(`[^`]*`)", text)
    for idx in range(0, len(parts), 2):
        parts[idx] = re.sub(r"\s*->\s*", " → ", parts[idx])
    return "".join(parts)


def ensure_citation_in_text(
    body: str, figures: List[Dict[str, Any]], labels: Dict[str, str]
) -> str:
    """Guarantee every figure in a section is cited in the text."""
    updated_body = normalize_prose_arrows(body.strip())
    for fig in figures:
        fig_id = str(fig.get("id", ""))
        citation_token = f"{labels['figure']} {fig_id}"
        if citation_token.lower() not in updated_body.lower():
            updated_body += f" ({labels['see_figure']} {fig_id})."
    return updated_body


# ---------------------------------------------------------
# Markdown Generator
# ---------------------------------------------------------
def build_markdown(
    spec: Dict[str, Any],
    md_path: str,
    out_dir: str,
    spec_dir: Optional[str] = None,
) -> None:
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
            real_logo = resolve_spec_asset_path(logo_path, spec_dir=spec_dir, out_dir=out_dir, must_exist=True)
            rel_logo = os.path.relpath(real_logo, start=out_dir)
            lines.append(f'<div align="center" style="margin-top: 40px; margin-bottom: 24px;"><img src="{rel_logo}" alt="Logo" style="max-height: 90px; max-width: 250px;" /></div>\n')
            has_logo = True
        except Exception:
            has_logo = False
    if not has_logo:
        lines.append(
            f'<div align="center" style="margin-top: 40px; margin-bottom: 30px;">'
            f'<div style="border: 2px dashed #94a3b8; padding: 20px 40px; display: inline-block; border-radius: 8px; color: #64748b; font-weight: bold; font-size: 14pt;">'
            f'{labels["logo_placeholder"]}</div></div>\n'
        )

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
            lines.append(f"{normalize_prose_arrows(ch['intro'])}\n")

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
                    abs_img = resolve_spec_asset_path(
                        raw_img_path, spec_dir=spec_dir, out_dir=out_dir, must_exist=False
                    )
                    rel_img = os.path.relpath(abs_img, start=out_dir)
                else:
                    rel_img = ""

                caption = f"{labels['figure']} {fig_id}: {fig_title}"
                lines.append(f'<a id="{fig_anchor}"></a>')
                if rel_img:
                    lines.append('<div align="center">')
                    lines.append(
                        f'  <img src="{rel_img}" alt="{caption}" style="max-width: 100%; max-height: 460px; height: auto; border: 1px solid #cbd5e1; border-radius: 4px;" /><br/>'
                    )
                    lines.append(f'  <p><em><b>{caption}</b></em></p>')
                    lines.append('</div>\n')
                else:
                    lines.append(f'<div align="center"><p><em><b>{caption}</b></em></p></div>\n')

                for bullet in fig.get("bullets", []):
                    lines.append(f"- {normalize_prose_arrows(bullet)}")
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

    footer = section.footer
    p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    p.text = ""
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    fld_page = OxmlElement("w:fldSimple")
    fld_page.set(qn("w:instr"), "PAGE")

    r = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), "18")  # 9 pt
    rPr.append(sz)
    col = OxmlElement("w:color")
    col.set(qn("w:val"), "64748B")
    rPr.append(col)
    r.append(rPr)
    t = OxmlElement("w:t")
    t.text = "1"
    r.append(t)
    fld_page.append(r)

    p._p.append(fld_page)


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


def _tokenize_inline_markdown(text: str) -> List[Tuple[str, bool, bool, bool]]:
    """
    Tokenize inline markdown into (segment_text, is_bold, is_italic, is_code) tuples
    after normalizing raw ASCII arrows (' -> ' -> ' → ').
    """
    if not text:
        return []
    cleaned = normalize_prose_arrows(text)
    pattern = re.compile(r"(\*\*.*?\*\*|__.*?__|`.*?`|\*.*?\*)")
    out: List[Tuple[str, bool, bool, bool]] = []
    for token in pattern.split(cleaned):
        if not token:
            continue
        if (token.startswith("**") and token.endswith("**") and len(token) >= 4) or (
            token.startswith("__") and token.endswith("__") and len(token) >= 4
        ):
            out.append((token[2:-2], True, False, False))
        elif token.startswith("`") and token.endswith("`") and len(token) >= 2:
            out.append((token[1:-1], False, False, True))
        elif token.startswith("*") and token.endswith("*") and len(token) >= 2:
            out.append((token[1:-1], False, True, False))
        else:
            out.append((token, False, False, False))
    return out


def _add_formatted_runs(paragraph: Any, text: str) -> None:
    """Parse **bold**, *italic*, and `code` segments into Word formatted runs."""
    for seg, is_bold, is_italic, is_code in _tokenize_inline_markdown(text):
        run = paragraph.add_run(seg)
        if is_bold:
            run.bold = True
        if is_italic:
            run.italic = True
        if is_code:
            run.font.name = "Consolas"


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
def _read_image_pixel_size(img_path: str) -> Tuple[int, int]:
    """Read (width, height) in pixels from PNG, JPEG, or WebP headers using stdlib (or Pillow if available)."""
    try:
        from PIL import Image as PILImage
        with PILImage.open(img_path) as im:
            return im.size
    except Exception:
        pass

    try:
        with open(img_path, "rb") as f:
            head = f.read(64)
            # PNG
            if head.startswith(b"\x89PNG\r\n\x1a\n") and len(head) >= 24:
                return struct.unpack(">II", head[16:24])
            # WebP
            if head[:4] == b"RIFF" and head[8:12] == b"WEBP" and len(head) >= 30:
                chunk_type = head[12:16]
                if chunk_type == b"VP8 " and len(head) >= 30:
                    w, h = struct.unpack("<HH", head[26:30])
                    return (w & 0x3FFF, h & 0x3FFF)
                if chunk_type == b"VP8L" and len(head) >= 25:
                    bits = struct.unpack("<I", head[21:25])[0]
                    return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
                if chunk_type == b"VP8X" and len(head) >= 30:
                    w = int.from_bytes(head[24:27], "little") + 1
                    h = int.from_bytes(head[27:30], "little") + 1
                    return (w, h)
            # JPEG
            if head.startswith(b"\xff\xd8"):
                f.seek(2)
                while True:
                    marker_prefix = f.read(1)
                    if not marker_prefix:
                        break
                    if marker_prefix != b"\xff":
                        continue
                    marker = f.read(1)
                    while marker == b"\xff":
                        marker = f.read(1)
                    if not marker:
                        break
                    m_val = marker[0]
                    if m_val in (0xD8, 0xD9) or (0xD0 <= m_val <= 0xD7):
                        continue
                    seg_len_bytes = f.read(2)
                    if len(seg_len_bytes) < 2:
                        break
                    seg_len = struct.unpack(">H", seg_len_bytes)[0]
                    if 0xC0 <= m_val <= 0xCF and m_val not in (0xC4, 0xC8, 0xCC):
                        sof = f.read(5)
                        if len(sof) == 5:
                            _, h, w = struct.unpack(">BHH", sof)
                            return (w, h)
                        break
                    if seg_len < 2:
                        break
                    f.seek(seg_len - 2, os.SEEK_CUR)
    except Exception:
        pass

    return 1600, 900


def _calc_a4_image_dimensions(
    img_path: str,
    max_w: float = 5.8,
    max_h: float = 5.2,
) -> Tuple[float, float]:
    """Calculate scaled width and height in inches to prevent A4 paper overflow."""
    orig_w, orig_h = _read_image_pixel_size(img_path)

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
    spec_dir: Optional[str] = None,
    out_dir: Optional[str] = None,
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
            real_logo = resolve_spec_asset_path(
                logo_path, spec_dir=spec_dir, out_dir=out_dir, must_exist=True
            )
            logo_p = doc.add_paragraph()
            logo_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            logo_p.paragraph_format.space_before = Pt(36)
            logo_p.paragraph_format.space_after = Pt(24)
            logo_p.add_run().add_picture(real_logo, width=Inches(2.4))
            has_logo_file = True
        except Exception:
            has_logo_file = False

    if not has_logo_file:
        logo_p = doc.add_paragraph(labels["logo_placeholder"])
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
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_p.add_run(spec.get("title", labels["default_title"]))
    title_run.bold = True
    title_run.font.size = Pt(26)
    title_run.font.color.rgb = RGBColor(15, 23, 42)

    if spec.get("subtitle"):
        sub_p = doc.add_paragraph()
        sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
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
        meta_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
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
    sectPr_front = sec_front._sectPr
    pgNum_front = OxmlElement("w:pgNumType")
    pgNum_front.set(qn("w:fmt"), "lowerRoman")
    pgNum_front.set(qn("w:start"), "1")
    sectPr_front.append(pgNum_front)
    _add_page_number_only_footer(sec_front)

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
            tab_pos_dxa=9026,
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
                tab_pos_dxa=9026,
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
        h1.paragraph_format.keep_with_next = True
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
            h2.paragraph_format.keep_with_next = True
            _add_bookmark_to_paragraph(h2, sec_bm)

            body_p = doc.add_paragraph()
            body_p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            if figures:
                body_p.paragraph_format.keep_with_next = True
            _add_formatted_runs(body_p, body_text)

            for fig in figures:
                ch_fig_counter += 1
                fig_id = str(fig.get("id", f"{ch_num}.{ch_fig_counter}"))
                fig_title = fig.get("title", "")
                fig_slug = re.sub(r"[^\w]", "", fig_id)
                fig_bm = f"umgFig{fig_slug}"

                img_path = fig.get("image_path", "")
                if img_path:
                    real_img = resolve_spec_asset_path(
                        img_path, spec_dir=spec_dir, out_dir=out_dir, must_exist=True
                    )
                    img_w_in, img_h_in = _calc_a4_image_dimensions(real_img, max_w=5.4, max_h=3.4)
                    img_p = doc.add_paragraph()
                    img_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    img_p.paragraph_format.keep_with_next = True
                    img_p.add_run().add_picture(real_img, width=Inches(img_w_in), height=Inches(img_h_in))

                cap_p = doc.add_paragraph()
                cap_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                cap_p.paragraph_format.keep_with_next = bool(fig.get("bullets"))
                cap_run = cap_p.add_run(f"{labels['figure']} {fig_id}: {fig_title}")
                cap_run.italic = True
                cap_run.bold = True
                cap_run.font.size = Pt(10)
                cap_run.font.color.rgb = RGBColor(51, 65, 85)
                _add_bookmark_to_paragraph(cap_p, fig_bm)

                for bullet in fig.get("bullets", []):
                    b_p = doc.add_paragraph(style="List Bullet")
                    b_p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                    b_p.paragraph_format.keep_together = True
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


def _extract_pdf_page_texts(pdf_path: str) -> List[str]:
    """
    Extract per-page raw text strings from a PDF using pypdf if installed,
    falling back automatically to the system 'pdftotext' utility.
    """
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        return [page.extract_text() or "" for page in reader.pages]
    except ImportError:
        pass
    except Exception as err:
        print(f"[WARNING] pypdf failed ({err}); trying pdftotext fallback.")

    pdftotext_bin = shutil.which("pdftotext")
    if pdftotext_bin:
        try:
            proc = subprocess.run(
                [pdftotext_bin, pdf_path, "-"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
            )
            if proc.returncode == 0 and proc.stdout:
                raw_pages = proc.stdout.split("\x0c")
                if raw_pages and raw_pages[-1] == "":
                    raw_pages = raw_pages[:-1]
                return raw_pages
        except Exception as err:
            print(f"[WARNING] pdftotext extraction failed: {err}")

    print("[WARNING] Neither pypdf nor pdftotext is available to extract PDF page numbers.")
    return []


def extract_page_map_from_pdf(
    pdf_path: str, spec: Dict[str, Any]
) -> Dict[str, str]:
    """
    Extract exact page numbers for each chapter, section, and figure bookmark
    from the rendered PDF (via pypdf or pdftotext fallback).
    """
    raw_pages = _extract_pdf_page_texts(pdf_path)
    if not raw_pages:
        return {}

    labels = get_labels(spec.get("language", "en"))
    page_map: Dict[str, str] = {}

    def _clean_ws(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip().lower()

    page_texts = [_clean_ws(txt) for txt in raw_pages]

    chapters = spec.get("chapters", [])
    first_ch_num = chapters[0].get("number", 1) if chapters else 1
    first_ch_title = chapters[0].get("title", "") if chapters else ""
    first_ch_full = _clean_ws(f"{labels['chapter']} {first_ch_num}: {first_ch_title}")
    first_ch_short = _clean_ws(f"{labels['chapter']} {first_ch_num}")
    toc_label = _clean_ws(labels["toc"])

    main_start_page_idx = 1
    for idx, text in enumerate(page_texts):
        if idx == 0:
            continue
        if toc_label in text:
            continue
        if (first_ch_full and first_ch_full in text) or (first_ch_short in text):
            main_start_page_idx = idx
            break

    for ch_idx, ch in enumerate(chapters, start=1):
        ch_num = ch.get("number", ch_idx)
        ch_title = ch.get("title", "")
        ch_bm = f"umgCh{ch_num}"
        target_phrase = _clean_ws(f"{labels['chapter']} {ch_num}: {ch_title}")

        ch_page_idx = main_start_page_idx
        found_page = None
        for p_idx in range(main_start_page_idx, len(page_texts)):
            if target_phrase in page_texts[p_idx]:
                ch_page_idx = p_idx
                found_page = str(p_idx - main_start_page_idx + 1)
                break
        if found_page:
            page_map[ch_bm] = found_page

        ch_fig_counter = 0
        sec_search_start = ch_page_idx
        for sec_idx, sec in enumerate(ch.get("sections", []), start=1):
            sec_num = sec.get("number", f"{ch_num}.{sec_idx}")
            sec_title = sec.get("title", "")
            sec_slug = re.sub(r"[^\w]", "", str(sec_num))
            sec_bm = f"umgSec{sec_slug}"
            target_sec = _clean_ws(f"{sec_num} {sec_title}")

            sec_found = None
            for p_idx in range(sec_search_start, len(page_texts)):
                if target_sec in page_texts[p_idx]:
                    sec_search_start = p_idx
                    sec_found = str(p_idx - main_start_page_idx + 1)
                    break
            if sec_found:
                page_map[sec_bm] = sec_found

            for fig in sec.get("figures", []):
                ch_fig_counter += 1
                fig_id = str(fig.get("id", f"{ch_num}.{ch_fig_counter}"))
                fig_title = fig.get("title", "")
                fig_slug = re.sub(r"[^\w]", "", str(fig_id))
                fig_bm = f"umgFig{fig_slug}"
                target_fig = _clean_ws(f"{labels['figure']} {fig_id}: {fig_title}")

                fig_found = None
                for p_idx in range(sec_search_start, len(page_texts)):
                    if target_fig in page_texts[p_idx]:
                        fig_found = str(p_idx - main_start_page_idx + 1)
                        break
                if fig_found:
                    page_map[fig_bm] = fig_found

    return page_map


# ---------------------------------------------------------
# Pure-Stdlib Native OpenXML (.docx) Builder
# ---------------------------------------------------------
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"
XML_NS = "http://www.w3.org/XML/1998/namespace"

ET.register_namespace("w", W_NS)
ET.register_namespace("r", R_NS)
ET.register_namespace("wp", WP_NS)
ET.register_namespace("a", A_NS)
ET.register_namespace("pic", PIC_NS)


def _w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def _r(tag: str) -> str:
    return f"{{{R_NS}}}{tag}"


def _wp(tag: str) -> str:
    return f"{{{WP_NS}}}{tag}"


def _a(tag: str) -> str:
    return f"{{{A_NS}}}{tag}"


def _pic(tag: str) -> str:
    return f"{{{PIC_NS}}}{tag}"


def _oxml_make_sect_pr(
    footer_rid: Optional[str] = None,
    num_fmt: Optional[str] = None,
    num_start: Optional[int] = None,
    is_next_page: bool = False,
) -> ET.Element:
    """Create an A4 w:sectPr element (11906x16838 dxa, 1-inch 1440 dxa margins)."""
    sect_pr = ET.Element(_w("sectPr"))
    if footer_rid:
        f_ref = ET.SubElement(sect_pr, _w("footerReference"))
        f_ref.set(_w("type"), "default")
        f_ref.set(_r("id"), footer_rid)
    if is_next_page:
        t_el = ET.SubElement(sect_pr, _w("type"))
        t_el.set(_w("val"), "nextPage")
    pg_sz = ET.SubElement(sect_pr, _w("pgSz"))
    pg_sz.set(_w("w"), "11906")
    pg_sz.set(_w("h"), "16838")
    pg_mar = ET.SubElement(sect_pr, _w("pgMar"))
    pg_mar.set(_w("top"), "1440")
    pg_mar.set(_w("right"), "1440")
    pg_mar.set(_w("bottom"), "1440")
    pg_mar.set(_w("left"), "1440")
    pg_mar.set(_w("header"), "720")
    pg_mar.set(_w("footer"), "720")
    pg_mar.set(_w("gutter"), "0")
    if num_fmt:
        pg_num = ET.SubElement(sect_pr, _w("pgNumType"))
        pg_num.set(_w("fmt"), num_fmt)
        if num_start is not None:
            pg_num.set(_w("start"), str(num_start))
    return sect_pr


def _oxml_add_run(
    p_el: ET.Element,
    text: str,
    bold: bool = False,
    italic: bool = False,
    code: bool = False,
    sz_half_pt: int = 21,
    color_hex: str = "0F172A",
) -> ET.Element:
    r_el = ET.SubElement(p_el, _w("r"))
    r_pr = ET.SubElement(r_el, _w("rPr"))
    r_fonts = ET.SubElement(r_pr, _w("rFonts"))
    font_name = "DejaVu Sans Mono" if code else "DejaVu Sans"
    r_fonts.set(_w("ascii"), font_name)
    r_fonts.set(_w("hAnsi"), font_name)
    r_fonts.set(_w("cs"), font_name)
    if bold:
        ET.SubElement(r_pr, _w("b"))
    if italic:
        ET.SubElement(r_pr, _w("i"))
    sz = ET.SubElement(r_pr, _w("sz"))
    sz.set(_w("val"), str(sz_half_pt))
    sz_cs = ET.SubElement(r_pr, _w("szCs"))
    sz_cs.set(_w("val"), str(sz_half_pt))
    col = ET.SubElement(r_pr, _w("color"))
    col.set(_w("val"), color_hex)
    t_el = ET.SubElement(r_el, _w("t"))
    t_el.set(f"{{{XML_NS}}}space", "preserve")
    t_el.text = text
    return r_el


def _oxml_add_markdown_runs(
    p_el: ET.Element,
    text: str,
    sz_half_pt: int = 21,
    color_hex: str = "0F172A",
) -> None:
    for seg, is_bold, is_italic, is_code in _tokenize_inline_markdown(text):
        _oxml_add_run(
            p_el,
            seg,
            bold=is_bold,
            italic=is_italic,
            code=is_code,
            sz_half_pt=19 if is_code else sz_half_pt,
            color_hex="1E293B" if is_code else color_hex,
        )


def _oxml_wrap_bookmark(p_el: ET.Element, bm_id: int, bm_name: str) -> None:
    bm_start = ET.Element(_w("bookmarkStart"))
    bm_start.set(_w("id"), str(bm_id))
    bm_start.set(_w("name"), bm_name)
    bm_end = ET.Element(_w("bookmarkEnd"))
    bm_end.set(_w("id"), str(bm_id))
    insert_idx = 1 if (len(p_el) > 0 and p_el[0].tag == _w("pPr")) else 0
    p_el.insert(insert_idx, bm_start)
    p_el.append(bm_end)


def _oxml_add_inline_picture(
    p_el: ET.Element,
    r_id: str,
    doc_pr_id: int,
    width_in: float,
    height_in: float,
    descr: str,
    with_border: bool = True,
) -> None:
    cx = int(round(width_in * 914400))
    cy = int(round(height_in * 914400))
    r_el = ET.SubElement(p_el, _w("r"))
    drawing = ET.SubElement(r_el, _w("drawing"))
    inline = ET.SubElement(
        drawing,
        _wp("inline"),
        {"distT": "0", "distB": "0", "distL": "0", "distR": "0"},
    )
    ET.SubElement(inline, _wp("extent"), {"cx": str(cx), "cy": str(cy)})
    eff = "9525" if with_border else "0"
    ET.SubElement(inline, _wp("effectExtent"), {"l": eff, "t": eff, "r": eff, "b": eff})
    ET.SubElement(
        inline,
        _wp("docPr"),
        {"id": str(doc_pr_id), "name": f"Picture {doc_pr_id}", "descr": descr},
    )
    c_nv_gf = ET.SubElement(inline, _wp("cNvGraphicFramePr"))
    ET.SubElement(c_nv_gf, _a("graphicFrameLocks"), {"noChangeAspect": "1"})
    graphic = ET.SubElement(inline, _a("graphic"))
    g_data = ET.SubElement(
        graphic,
        _a("graphicData"),
        {"uri": "http://schemas.openxmlformats.org/drawingml/2006/picture"},
    )
    pic_el = ET.SubElement(g_data, _pic("pic"))
    nv_pic = ET.SubElement(pic_el, _pic("nvPicPr"))
    ET.SubElement(
        nv_pic,
        _pic("cNvPr"),
        {"id": str(doc_pr_id), "name": f"image_{doc_pr_id}", "descr": descr},
    )
    ET.SubElement(nv_pic, _pic("cNvPicPr"))
    blip_fill = ET.SubElement(pic_el, _pic("blipFill"))
    blip = ET.SubElement(blip_fill, _a("blip"))
    blip.set(_r("embed"), r_id)
    stretch = ET.SubElement(blip_fill, _a("stretch"))
    ET.SubElement(stretch, _a("fillRect"))
    sp_pr = ET.SubElement(pic_el, _pic("spPr"))
    xfrm = ET.SubElement(sp_pr, _a("xfrm"))
    ET.SubElement(xfrm, _a("off"), {"x": "0", "y": "0"})
    ET.SubElement(xfrm, _a("ext"), {"cx": str(cx), "cy": str(cy)})
    prst = ET.SubElement(sp_pr, _a("prstGeom"), {"prst": "rect"})
    ET.SubElement(prst, _a("avLst"))
    if with_border:
        ln = ET.SubElement(sp_pr, _a("ln"), {"w": "9525"})
        s_fill = ET.SubElement(ln, _a("solidFill"))
        ET.SubElement(s_fill, _a("srgbClr"), {"val": "CBD5E1"})


def _oxml_footer_bytes() -> bytes:
    ftr = ET.Element(_w("ftr"))
    p = ET.SubElement(ftr, _w("p"))
    p_pr = ET.SubElement(p, _w("pPr"))
    jc = ET.SubElement(p_pr, _w("jc"))
    jc.set(_w("val"), "right")
    fld = ET.SubElement(p, _w("fldSimple"))
    fld.set(_w("instr"), "PAGE")
    _oxml_add_run(fld, "1", sz_half_pt=18, color_hex="64748B")
    return ET.tostring(ftr, encoding="utf-8", xml_declaration=True)


def build_docx_stdlib_oxml(
    spec: Dict[str, Any],
    docx_path: str,
    page_map: Optional[Dict[str, str]] = None,
    enable_update_prompt: bool = True,
    spec_dir: Optional[str] = None,
    out_dir: Optional[str] = None,
) -> bool:
    """
    Build a publication-grade multi-section ECMA-376 OpenXML (.docx) package
    using 100% Python standard library (zero python-docx or HTML import limitations):
      - Section 1: Cover page within A4 margins, no footer/page number.
      - Section 2: Table of Contents with lowerRoman numbering ('i'), dot leaders
        at 9026 dxa, 360 dxa subsection indentation, hyperlinks, and PAGEREF fields.
      - Section 3: Main Chapters with decimal numbering starting at 1, chapter page
        breaks, justified paragraphs & bullets, keepNext/keepLines pagination chains,
        and embedded media with subtle borders.
    """
    labels = get_labels(spec.get("language", "en"))
    chapters = spec.get("chapters", [])
    page_map = page_map or {}

    doc_el = ET.Element(_w("document"))
    body = ET.SubElement(doc_el, _w("body"))

    media_entries: List[Tuple[str, str, str]] = []  # (rId, archive_rel_path, source_disk_path)
    next_img_idx = 1
    next_bm_id = 100

    def _register_image(src_path: str) -> str:
        nonlocal next_img_idx
        ext = os.path.splitext(src_path)[1].lower() or ".png"
        if ext == ".jpg":
            ext = ".jpeg"
        r_id = f"rIdImg{next_img_idx}"
        rel_media = f"media/image_{next_img_idx}{ext}"
        next_img_idx += 1
        media_entries.append((r_id, rel_media, src_path))
        return r_id

    # =========================================================
    # Section 1: Cover Page (No footer, fits A4 9026 dxa cleanly)
    # =========================================================
    logo_path = spec.get("logo_path")
    has_logo = False
    if logo_path:
        try:
            real_logo = resolve_spec_asset_path(
                logo_path, spec_dir=spec_dir, out_dir=out_dir, must_exist=True
            )
            lw, lh = _calc_a4_image_dimensions(real_logo, max_w=2.4, max_h=1.2)
            r_id_logo = _register_image(real_logo)
            p_logo = ET.SubElement(body, _w("p"))
            p_pr = ET.SubElement(p_logo, _w("pPr"))
            ET.SubElement(p_pr, _w("jc"), {_w("val"): "center"})
            ET.SubElement(p_pr, _w("spacing"), {_w("before"): "720", _w("after"): "480"})
            _oxml_add_inline_picture(
                p_logo, r_id_logo, next_img_idx, lw, lh, "Logo", with_border=False
            )
            has_logo = True
        except Exception:
            has_logo = False

    if not has_logo:
        p_spacer = ET.SubElement(body, _w("p"))
        p_sp_pr = ET.SubElement(p_spacer, _w("pPr"))
        ET.SubElement(p_sp_pr, _w("spacing"), {_w("before"): "600", _w("after"): "120"})

        tbl = ET.SubElement(body, _w("tbl"))
        tbl_pr = ET.SubElement(tbl, _w("tblPr"))
        ET.SubElement(tbl_pr, _w("tblW"), {_w("w"): "4800", _w("type"): "dxa"})
        ET.SubElement(tbl_pr, _w("jc"), {_w("val"): "center"})
        tbl_bdr = ET.SubElement(tbl_pr, _w("tblBorders"))
        for side in ("top", "left", "bottom", "right"):
            ET.SubElement(
                tbl_bdr,
                _w(side),
                {_w("val"): "dashed", _w("sz"): "8", _w("space"): "0", _w("color"): "94A3B8"},
            )
        tbl_grid = ET.SubElement(tbl, _w("tblGrid"))
        ET.SubElement(tbl_grid, _w("gridCol"), {_w("w"): "4800"})
        tr = ET.SubElement(tbl, _w("tr"))
        tc = ET.SubElement(tr, _w("tc"))
        tc_pr = ET.SubElement(tc, _w("tcPr"))
        ET.SubElement(tc_pr, _w("tcW"), {_w("w"): "4800", _w("type"): "dxa"})
        tc_mar = ET.SubElement(tc_pr, _w("tcMar"))
        for side, pad_v in (("top", "240"), ("bottom", "240"), ("left", "280"), ("right", "280")):
            ET.SubElement(tc_mar, _w(side), {_w("w"): pad_v, _w("type"): "dxa"})
        p_box = ET.SubElement(tc, _w("p"))
        p_box_pr = ET.SubElement(p_box, _w("pPr"))
        ET.SubElement(p_box_pr, _w("jc"), {_w("val"): "center"})
        ET.SubElement(p_box_pr, _w("spacing"), {_w("before"): "0", _w("after"): "0"})
        _oxml_add_run(
            p_box, labels["logo_placeholder"], bold=True, sz_half_pt=26, color_hex="64748B"
        )

    p_title = ET.SubElement(body, _w("p"))
    pt_pr = ET.SubElement(p_title, _w("pPr"))
    ET.SubElement(pt_pr, _w("jc"), {_w("val"): "center"})
    ET.SubElement(
        pt_pr,
        _w("spacing"),
        {_w("before"): "560", _w("after"): "200", _w("line"): "300", _w("lineRule"): "auto"},
    )
    _oxml_add_run(
        p_title,
        str(spec.get("title", labels["default_title"])),
        bold=True,
        sz_half_pt=52,
        color_hex="0F172A",
    )

    if spec.get("subtitle"):
        p_sub = ET.SubElement(body, _w("p"))
        ps_pr = ET.SubElement(p_sub, _w("pPr"))
        ET.SubElement(ps_pr, _w("jc"), {_w("val"): "center"})
        ET.SubElement(
            ps_pr,
            _w("spacing"),
            {_w("before"): "0", _w("after"): "360", _w("line"): "288", _w("lineRule"): "auto"},
        )
        _oxml_add_run(p_sub, str(spec["subtitle"]), sz_half_pt=26, color_hex="475569")

    meta_parts = []
    if spec.get("version"):
        meta_parts.append(f"{labels['version']}: {spec['version']}")
    if spec.get("date"):
        meta_parts.append(f"{labels['date']}: {spec['date']}")
    if meta_parts:
        p_meta = ET.SubElement(body, _w("p"))
        pm_pr = ET.SubElement(p_meta, _w("pPr"))
        ET.SubElement(pm_pr, _w("jc"), {_w("val"): "center"})
        p_bdr = ET.SubElement(pm_pr, _w("pBdr"))
        ET.SubElement(
            p_bdr,
            _w("top"),
            {_w("val"): "single", _w("sz"): "6", _w("space"): "12", _w("color"): "CBD5E1"},
        )
        ET.SubElement(pm_pr, _w("spacing"), {_w("before"): "2800", _w("after"): "120"})
        _oxml_add_run(p_meta, "   |   ".join(meta_parts), sz_half_pt=20, color_hex="64748B")

    # End of Section 1 (Cover Page -> No Footer)
    p_sec1_end = ET.SubElement(body, _w("p"))
    p_sec1_pr = ET.SubElement(p_sec1_end, _w("pPr"))
    p_sec1_pr.append(_oxml_make_sect_pr(footer_rid=None, num_fmt=None, is_next_page=False))

    # =========================================================
    # Section 2: Table of Contents (Roman Numerals: i, ii...)
    # =========================================================
    p_toc_h = ET.SubElement(body, _w("p"))
    pth_pr = ET.SubElement(p_toc_h, _w("pPr"))
    ET.SubElement(pth_pr, _w("pStyle"), {_w("val"): "Heading1"})
    pth_bdr = ET.SubElement(pth_pr, _w("pBdr"))
    ET.SubElement(
        pth_bdr,
        _w("bottom"),
        {_w("val"): "single", _w("sz"): "8", _w("space"): "6", _w("color"): "CBD5E1"},
    )
    ET.SubElement(pth_pr, _w("spacing"), {_w("before"): "120", _w("after"): "240"})
    _oxml_add_run(p_toc_h, labels["toc"], bold=True, sz_half_pt=36, color_hex="0F172A")

    def _append_toc_line(
        bm_name: str,
        label_str: str,
        pg_str: str,
        is_chapter: bool,
    ) -> None:
        p_line = ET.SubElement(body, _w("p"))
        pl_pr = ET.SubElement(p_line, _w("pPr"))
        if not is_chapter:
            ET.SubElement(pl_pr, _w("ind"), {_w("left"): "360"})
        tabs = ET.SubElement(pl_pr, _w("tabs"))
        ET.SubElement(
            tabs,
            _w("tab"),
            {_w("val"): "right", _w("leader"): "dot", _w("pos"): "9026"},
        )
        ET.SubElement(
            pl_pr,
            _w("spacing"),
            {
                _w("before"): "120" if is_chapter else "30",
                _w("after"): "40" if is_chapter else "30",
                _w("line"): "276",
                _w("lineRule"): "auto",
            },
        )
        hl = ET.SubElement(
            p_line,
            _w("hyperlink"),
            {_w("anchor"): bm_name, _w("history"): "1"},
        )
        _oxml_add_run(
            hl,
            label_str,
            bold=is_chapter,
            sz_half_pt=21 if is_chapter else 20,
            color_hex="0F172A" if is_chapter else "334155",
        )
        r_tab = ET.SubElement(hl, _w("r"))
        ET.SubElement(r_tab, _w("tab"))

        r_begin = ET.SubElement(hl, _w("r"))
        ET.SubElement(r_begin, _w("fldChar"), {_w("fldCharType"): "begin"})
        r_instr = ET.SubElement(hl, _w("r"))
        instr = ET.SubElement(r_instr, _w("instrText"))
        instr.set(f"{{{XML_NS}}}space", "preserve")
        instr.text = f"PAGEREF {bm_name} \\h"
        r_sep = ET.SubElement(hl, _w("r"))
        ET.SubElement(r_sep, _w("fldChar"), {_w("fldCharType"): "separate"})
        _oxml_add_run(
            hl,
            str(pg_str),
            bold=is_chapter,
            sz_half_pt=21 if is_chapter else 20,
            color_hex="0F172A" if is_chapter else "475569",
        )
        r_end = ET.SubElement(hl, _w("r"))
        ET.SubElement(r_end, _w("fldChar"), {_w("fldCharType"): "end"})

    for ch_idx, ch in enumerate(chapters, start=1):
        ch_num = ch.get("number", ch_idx)
        ch_title = ch.get("title", "")
        ch_bm = f"umgCh{ch_num}"
        ch_page = page_map.get(ch_bm, str(ch_idx))
        _append_toc_line(
            ch_bm, f"{labels['chapter']} {ch_num}: {ch_title}", ch_page, is_chapter=True
        )
        for sec_idx, sec in enumerate(ch.get("sections", []), start=1):
            sec_num = sec.get("number", f"{ch_num}.{sec_idx}")
            sec_title = sec.get("title", "")
            sec_slug = re.sub(r"[^\w]", "", str(sec_num))
            sec_bm = f"umgSec{sec_slug}"
            sec_page = page_map.get(sec_bm, ch_page)
            _append_toc_line(sec_bm, f"{sec_num} {sec_title}", sec_page, is_chapter=False)

    # End of Section 2 (TOC -> Roman Footer 'i')
    p_sec2_end = ET.SubElement(body, _w("p"))
    p_sec2_pr = ET.SubElement(p_sec2_end, _w("pPr"))
    p_sec2_pr.append(
        _oxml_make_sect_pr(
            footer_rid="rIdFooterRoman",
            num_fmt="lowerRoman",
            num_start=1,
            is_next_page=True,
        )
    )

    # =========================================================
    # Section 3: Main Chapters (Arabic Numerals starting at 1)
    # =========================================================
    for ch_idx, ch in enumerate(chapters, start=1):
        ch_num = ch.get("number", ch_idx)
        ch_title = ch.get("title", "")
        ch_bm = f"umgCh{ch_num}"

        p_ch = ET.SubElement(body, _w("p"))
        pch_pr = ET.SubElement(p_ch, _w("pPr"))
        ET.SubElement(pch_pr, _w("pStyle"), {_w("val"): "Heading1"})
        if ch_idx > 1:
            ET.SubElement(pch_pr, _w("pageBreakBefore"))
        ET.SubElement(pch_pr, _w("keepNext"))
        pch_bdr = ET.SubElement(pch_pr, _w("pBdr"))
        ET.SubElement(
            pch_bdr,
            _w("bottom"),
            {_w("val"): "single", _w("sz"): "6", _w("space"): "4", _w("color"): "CBD5E1"},
        )
        ET.SubElement(pch_pr, _w("spacing"), {_w("before"): "120", _w("after"): "140"})
        _oxml_add_run(
            p_ch,
            f"{labels['chapter']} {ch_num}: {ch_title}",
            bold=True,
            sz_half_pt=34,
            color_hex="0F172A",
        )
        next_bm_id += 1
        _oxml_wrap_bookmark(p_ch, next_bm_id, ch_bm)

        if ch.get("intro"):
            p_intro = ET.SubElement(body, _w("p"))
            pi_pr = ET.SubElement(p_intro, _w("pPr"))
            ET.SubElement(pi_pr, _w("jc"), {_w("val"): "both"})
            ET.SubElement(
                pi_pr,
                _w("spacing"),
                {_w("before"): "40", _w("after"): "120", _w("line"): "288", _w("lineRule"): "auto"},
            )
            _oxml_add_markdown_runs(p_intro, str(ch["intro"]), sz_half_pt=21)

        ch_fig_counter = 0
        for sec_idx, sec in enumerate(ch.get("sections", []), start=1):
            sec_num = sec.get("number", f"{ch_num}.{sec_idx}")
            sec_title = sec.get("title", "")
            sec_slug = re.sub(r"[^\w]", "", str(sec_num))
            sec_bm = f"umgSec{sec_slug}"

            figures = sec.get("figures", [])
            body_text = ensure_citation_in_text(sec.get("body", ""), figures, labels)

            p_sec = ET.SubElement(body, _w("p"))
            ps_pr = ET.SubElement(p_sec, _w("pPr"))
            ET.SubElement(ps_pr, _w("pStyle"), {_w("val"): "Heading2"})
            ET.SubElement(ps_pr, _w("keepNext"))
            ET.SubElement(ps_pr, _w("spacing"), {_w("before"): "180", _w("after"): "80"})
            _oxml_add_run(
                p_sec,
                f"{sec_num} {sec_title}",
                bold=True,
                sz_half_pt=26,
                color_hex="1E293B",
            )
            next_bm_id += 1
            _oxml_wrap_bookmark(p_sec, next_bm_id, sec_bm)

            if body_text:
                p_body = ET.SubElement(body, _w("p"))
                pb_pr = ET.SubElement(p_body, _w("pPr"))
                ET.SubElement(pb_pr, _w("jc"), {_w("val"): "both"})
                if figures:
                    ET.SubElement(pb_pr, _w("keepNext"))
                ET.SubElement(
                    pb_pr,
                    _w("spacing"),
                    {
                        _w("before"): "0",
                        _w("after"): "100",
                        _w("line"): "288",
                        _w("lineRule"): "auto",
                    },
                )
                _oxml_add_markdown_runs(p_body, body_text, sz_half_pt=21)

            for fig in figures:
                ch_fig_counter += 1
                fig_id = str(fig.get("id", f"{ch_num}.{ch_fig_counter}"))
                fig_title = str(fig.get("title", ""))
                fig_slug = re.sub(r"[^\w]", "", str(fig_id))
                fig_bm = f"umgFig{fig_slug}"
                caption_str = f"{labels['figure']} {fig_id}: {fig_title}"

                img_path = fig.get("image_path", "")
                if img_path:
                    real_img = resolve_spec_asset_path(
                        img_path, spec_dir=spec_dir, out_dir=out_dir, must_exist=True
                    )
                    iw, ih = _calc_a4_image_dimensions(real_img, max_w=5.4, max_h=3.4)
                    r_id_img = _register_image(real_img)
                    p_img = ET.SubElement(body, _w("p"))
                    pimg_pr = ET.SubElement(p_img, _w("pPr"))
                    ET.SubElement(pimg_pr, _w("jc"), {_w("val"): "center"})
                    ET.SubElement(pimg_pr, _w("keepNext"))
                    ET.SubElement(pimg_pr, _w("spacing"), {_w("before"): "80", _w("after"): "60"})
                    _oxml_add_inline_picture(
                        p_img,
                        r_id_img,
                        next_img_idx,
                        iw,
                        ih,
                        caption_str,
                        with_border=True,
                    )

                bullets = fig.get("bullets", [])
                p_cap = ET.SubElement(body, _w("p"))
                pcap_pr = ET.SubElement(p_cap, _w("pPr"))
                ET.SubElement(pcap_pr, _w("jc"), {_w("val"): "center"})
                if bullets:
                    ET.SubElement(pcap_pr, _w("keepNext"))
                ET.SubElement(pcap_pr, _w("spacing"), {_w("before"): "20", _w("after"): "90"})
                _oxml_add_run(
                    p_cap, caption_str, bold=True, italic=True, sz_half_pt=20, color_hex="334155"
                )
                next_bm_id += 1
                _oxml_wrap_bookmark(p_cap, next_bm_id, fig_bm)

                for b_item in bullets:
                    p_bul = ET.SubElement(body, _w("p"))
                    pbul_pr = ET.SubElement(p_bul, _w("pPr"))
                    ET.SubElement(pbul_pr, _w("pStyle"), {_w("val"): "ListBullet"})
                    num_pr = ET.SubElement(pbul_pr, _w("numPr"))
                    ET.SubElement(num_pr, _w("ilvl"), {_w("val"): "0"})
                    ET.SubElement(num_pr, _w("numId"), {_w("val"): "1"})
                    ET.SubElement(pbul_pr, _w("keepLines"))
                    ET.SubElement(pbul_pr, _w("jc"), {_w("val"): "both"})
                    ET.SubElement(
                        pbul_pr,
                        _w("spacing"),
                        {
                            _w("before"): "20",
                            _w("after"): "60",
                            _w("line"): "280",
                            _w("lineRule"): "auto",
                        },
                    )
                    _oxml_add_markdown_runs(p_bul, str(b_item), sz_half_pt=21)

    # Body-level sectPr for Section 3 (Main Content -> Arabic '1')
    body.append(
        _oxml_make_sect_pr(
            footer_rid="rIdFooterMain",
            num_fmt="decimal",
            num_start=1,
            is_next_page=True,
        )
    )

    # Assemble OpenXML package parts
    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:styles xmlns:w="{W_NS}">'
        '<w:docDefaults>'
        '<w:rPrDefault><w:rPr>'
        '<w:rFonts w:ascii="DejaVu Sans" w:hAnsi="DejaVu Sans" w:cs="DejaVu Sans"/>'
        '<w:sz w:val="21"/><w:szCs w:val="21"/><w:color w:val="0F172A"/>'
        '</w:rPr></w:rPrDefault>'
        '</w:docDefaults>'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1">'
        '<w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>'
        '<w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading2">'
        '<w:name w:val="heading 2"/><w:basedOn w:val="Normal"/>'
        '<w:pPr><w:outlineLvl w:val="1"/></w:pPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="ListBullet">'
        '<w:name w:val="List Bullet"/><w:basedOn w:val="Normal"/></w:style>'
        '</w:styles>'
    )

    numbering_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:numbering xmlns:w="{W_NS}">'
        '<w:abstractNum w:abstractNumId="0">'
        '<w:multiLevelType w:val="singleLevel"/>'
        '<w:lvl w:ilvl="0">'
        '<w:start w:val="1"/>'
        '<w:numFmt w:val="bullet"/>'
        '<w:lvlText w:val="\u2022"/>'
        '<w:lvlJc w:val="left"/>'
        '<w:pPr><w:ind w:left="420" w:hanging="220"/></w:pPr>'
        '<w:rPr><w:rFonts w:ascii="DejaVu Sans" w:hAnsi="DejaVu Sans"/></w:rPr>'
        '</w:lvl>'
        '</w:abstractNum>'
        '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
        '</w:numbering>'
    )

    upd_tag = '<w:updateFields w:val="true"/>' if enable_update_prompt else ""
    settings_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:settings xmlns:w="{W_NS}">{upd_tag}</w:settings>'
    )

    rels_items = [
        '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>',
        '<Relationship Id="rIdSettings" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>',
        '<Relationship Id="rIdNumbering" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>',
        '<Relationship Id="rIdFooterRoman" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>',
        '<Relationship Id="rIdFooterMain" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer2.xml"/>',
    ]
    for r_id, rel_media, _ in media_entries:
        rels_items.append(
            f'<Relationship Id="{r_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="{rel_media}"/>'
        )
    doc_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(rels_items)
        + "</Relationships>"
    )

    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '</Relationships>'
    )

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="png" ContentType="image/png"/>'
        '<Default Extension="jpeg" ContentType="image/jpeg"/>'
        '<Default Extension="jpg" ContentType="image/jpeg"/>'
        '<Default Extension="webp" ContentType="image/webp"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
        '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
        '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
        '<Override PartName="/word/footer2.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
        '</Types>'
    )

    footer_bytes = _oxml_footer_bytes()
    doc_bytes = ET.tostring(doc_el, encoding="utf-8", xml_declaration=True)

    parent_dir = os.path.dirname(os.path.abspath(docx_path))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    with zipfile.ZipFile(docx_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml.encode("utf-8"))
        zf.writestr("_rels/.rels", root_rels_xml.encode("utf-8"))
        zf.writestr("word/document.xml", doc_bytes)
        zf.writestr("word/_rels/document.xml.rels", doc_rels_xml.encode("utf-8"))
        zf.writestr("word/styles.xml", styles_xml.encode("utf-8"))
        zf.writestr("word/numbering.xml", numbering_xml.encode("utf-8"))
        zf.writestr("word/settings.xml", settings_xml.encode("utf-8"))
        zf.writestr("word/footer1.xml", footer_bytes)
        zf.writestr("word/footer2.xml", footer_bytes)
        for _, rel_media, src_path in media_entries:
            zf.write(src_path, f"word/{rel_media}")

    return True


def build_docx_2pass(
    spec: Dict[str, Any],
    docx_path: str,
    page_source: str = "auto",
    no_update_prompt: bool = False,
    out_dir: Optional[str] = None,
    spec_dir: Optional[str] = None,
) -> bool:
    """
    Two-pass compiler:
    Pass 1: Build multi-section .docx with estimated page numbers (via python-docx or pure-stdlib OpenXML).
    Pass 2: Render PDF via LibreOffice, extract exact page numbers (via pypdf or pdftotext),
            and rebuild .docx with exact TOC page numbers.
    """
    has_python_docx = False
    try:
        import docx  # noqa: F401
        has_python_docx = True
    except ImportError:
        print("[NOTICE] python-docx is not installed. Using native stdlib OpenXML .docx builder...")

    target_dir = out_dir or os.path.dirname(docx_path) or "."
    enable_update_prompt = not no_update_prompt

    def _compile_pass(p_map: Dict[str, str]) -> None:
        if has_python_docx:
            build_docx_internal(
                spec,
                docx_path,
                page_map=p_map,
                enable_update_prompt=enable_update_prompt,
                spec_dir=spec_dir,
                out_dir=target_dir,
            )
        else:
            build_docx_stdlib_oxml(
                spec,
                docx_path,
                page_map=p_map,
                enable_update_prompt=enable_update_prompt,
                spec_dir=spec_dir,
                out_dir=target_dir,
            )

    temp_dir = tempfile.mkdtemp(prefix="umg_build_")
    try:
        curr_page = 1
        est_map: Dict[str, str] = {}
        for ch_idx, ch in enumerate(spec.get("chapters", []), start=1):
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

        # Pass 1 build
        _compile_pass(est_map)

        # Resolve exact page numbers via PDF
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
                _compile_pass(exact_map)
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
    """Validate hyperlinks, bookmark integrity, A4 table widths, embedded media, and PDF standards."""
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
            try:
                with zipfile.ZipFile(docx_path, "r") as z:
                    xml_info = z.getinfo("word/document.xml")
                    if xml_info.file_size > 20_000_000:
                        raise ValueError(
                            f"Safety Error: document.xml uncompressed size ({xml_info.file_size} bytes) exceeds 20MB limit."
                        )
                    doc_xml = z.read("word/document.xml")
                    root = ET.fromstring(doc_xml)

                    bookmarks = {
                        el.attrib.get(_w("name"))
                        for el in root.iter(_w("bookmarkStart"))
                    }
                    hyperlinks = {
                        el.attrib.get(_w("anchor"))
                        for el in root.iter(_w("hyperlink"))
                        if el.attrib.get(_w("anchor"))
                    }

                    missing_bm = {
                        h for h in hyperlinks if h and h.startswith("umg") and h not in bookmarks
                    }
                    if missing_bm:
                        print(f"[FAIL] DOCX has hyperlinks pointing to missing bookmarks: {missing_bm}")
                        all_ok = False
                    else:
                        print(f"[PASS] DOCX: All {len(hyperlinks)} internal hyperlinks match valid bookmarks.")

                    # Check table widths do not overflow A4 printable width (9026 dxa)
                    oversized_tables = []
                    for tbl_w in root.iter(_w("tblW")):
                        if tbl_w.attrib.get(_w("type")) == "dxa":
                            w_val = int(tbl_w.attrib.get(_w("w"), "0") or 0)
                            if w_val > 9050:
                                oversized_tables.append(w_val)
                    if oversized_tables:
                        print(f"[FAIL] DOCX has tables exceeding A4 printable width (9026 dxa): {oversized_tables}")
                        all_ok = False

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
                print(f"[FAIL] DOCX XML inspection failed: {err}")
                all_ok = False
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
        spec_dir = os.path.dirname(spec_path)
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
            build_markdown(spec_data, md_out, out_dir, spec_dir=spec_dir)

        docx_built = False
        if should_build_docx:
            docx_built = build_docx_2pass(
                spec_data,
                docx_out,
                page_source=args.page_source,
                no_update_prompt=args.no_word_update_prompt,
                out_dir=out_dir,
                spec_dir=spec_dir,
            )

        pdf_created = None
        if should_export_pdf and docx_built:
            pdf_created = export_docx_to_pdf_official(docx_out, out_dir)

        ok = verify_outputs(
            md_path=md_out if should_build_md else None,
            docx_path=docx_out if (should_build_docx and docx_built) else None,
            pdf_path=pdf_out if (should_export_pdf and pdf_created) else None,
        )
        if not ok:
            sys.exit(1)

    except Exception as err:
        sys.exit(f"[ERROR] {err}")


if __name__ == "__main__":
    main()
