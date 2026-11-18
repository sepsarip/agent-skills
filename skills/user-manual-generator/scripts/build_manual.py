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
            last_line = updated_body.splitlines()[-1].lstrip() if updated_body else ""
            sep = "\n\n" if (not updated_body or last_line.startswith(">")) else " "
            updated_body = f"{updated_body}{sep}({labels['see_figure']} {fig_id}).".lstrip()
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
# Inline Markdown & A4 Image / Page Setup Helpers
# ---------------------------------------------------------
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


def _extract_named_dest_pages_pypdf(pdf_path: str) -> Optional[Dict[str, int]]:
    """Extract 0-based page index per named destination bookmark using pypdf when installed."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(pdf_path)
        dest_map: Dict[str, int] = {}
        named = getattr(reader, "named_destinations", {}) or {}
        for name, dest in named.items():
            pg_idx = reader.get_destination_page_number(dest)
            if pg_idx is not None:
                dest_map[str(name).lstrip("/")] = pg_idx
        return dest_map
    except Exception:
        return None


def _find_heading_page(
    target_phrase: str,
    raw_pages_lower: List[str],
    page_texts: List[str],
    start_idx: int,
) -> Optional[int]:
    """Locate 0-based page index of heading, preferring line-start matches before substring matches."""
    if not target_phrase:
        return None
    line_pat = re.compile(rf"(?:^|\n)\s*{re.escape(target_phrase)}\b")
    for p_idx in range(start_idx, len(raw_pages_lower)):
        collapsed_lines = re.sub(r"[ \t]+", " ", raw_pages_lower[p_idx])
        if line_pat.search(collapsed_lines):
            return p_idx
    for p_idx in range(start_idx, len(page_texts)):
        if target_phrase in page_texts[p_idx]:
            return p_idx
    return None


def extract_page_map_from_pdf(
    pdf_path: str, spec: Dict[str, Any]
) -> Dict[str, str]:
    """
    Extract exact page numbers for each chapter, section, and figure bookmark
    from the rendered PDF (via pypdf named destinations or line-anchored pdftotext fallback).
    """
    raw_pages = _extract_pdf_page_texts(pdf_path)
    if not raw_pages:
        return {}

    labels = get_labels(spec.get("language", "en"))
    page_map: Dict[str, str] = {}

    def _clean_ws(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip().lower()

    raw_pages_lower = [txt.lower() for txt in raw_pages]
    page_texts = [_clean_ws(txt) for txt in raw_pages]
    dest_pages = _extract_named_dest_pages_pypdf(pdf_path) or {}

    chapters = spec.get("chapters", [])
    first_ch_num = chapters[0].get("number", 1) if chapters else 1
    first_ch_title = chapters[0].get("title", "") if chapters else ""
    first_ch_full = _clean_ws(f"{labels['chapter']} {first_ch_num}: {first_ch_title}")
    first_ch_short = _clean_ws(f"{labels['chapter']} {first_ch_num}")
    toc_label = _clean_ws(labels["toc"])

    main_start_page_idx = 1
    first_bm = f"umgCh{first_ch_num}"
    if first_bm in dest_pages and dest_pages[first_bm] >= 1:
        main_start_page_idx = dest_pages[first_bm]
    else:
        for idx, text in enumerate(page_texts):
            if idx == 0 or toc_label in text:
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
        p_idx = dest_pages.get(ch_bm)
        if p_idx is None or p_idx < main_start_page_idx:
            p_idx = _find_heading_page(target_phrase, raw_pages_lower, page_texts, main_start_page_idx)
        if p_idx is not None:
            ch_page_idx = p_idx
            page_map[ch_bm] = str(p_idx - main_start_page_idx + 1)

        ch_fig_counter = 0
        sec_search_start = ch_page_idx
        for sec_idx, sec in enumerate(ch.get("sections", []), start=1):
            sec_num = sec.get("number", f"{ch_num}.{sec_idx}")
            sec_title = sec.get("title", "")
            sec_slug = re.sub(r"[^\w]", "", str(sec_num))
            sec_bm = f"umgSec{sec_slug}"
            target_sec = _clean_ws(f"{sec_num} {sec_title}")

            sp_idx = dest_pages.get(sec_bm)
            if sp_idx is None or sp_idx < main_start_page_idx:
                sp_idx = _find_heading_page(target_sec, raw_pages_lower, page_texts, sec_search_start)
            if sp_idx is not None:
                sec_search_start = sp_idx
                page_map[sec_bm] = str(sp_idx - main_start_page_idx + 1)

            for fig in sec.get("figures", []):
                ch_fig_counter += 1
                fig_id = str(fig.get("id", f"{ch_num}.{ch_fig_counter}"))
                fig_title = fig.get("title", "")
                fig_slug = re.sub(r"[^\w]", "", str(fig_id))
                fig_bm = f"umgFig{fig_slug}"
                target_fig = _clean_ws(f"{labels['figure']} {fig_id}: {fig_title}")

                fp_idx = dest_pages.get(fig_bm)
                if fp_idx is None or fp_idx < main_start_page_idx:
                    fp_idx = _find_heading_page(target_fig, raw_pages_lower, page_texts, sec_search_start)
                if fp_idx is not None:
                    page_map[fig_bm] = str(fp_idx - main_start_page_idx + 1)

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


def _oxml_append_prose_paragraphs(
    body: ET.Element,
    text: str,
    before_dxa: str = "0",
    after_dxa: str = "100",
    keep_last_with_next: bool = False,
) -> None:
    """Split prose on blank lines into justified paragraphs and styled callout blockquotes."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", str(text).strip()) if b.strip()]
    for idx, block in enumerate(blocks):
        is_last = idx == len(blocks) - 1
        is_callout = all(line.lstrip().startswith(">") for line in block.splitlines())
        p_el = ET.SubElement(body, _w("p"))
        p_pr = ET.SubElement(p_el, _w("pPr"))
        if is_last and keep_last_with_next:
            ET.SubElement(p_pr, _w("keepNext"))
        if is_callout:
            p_bdr = ET.SubElement(p_pr, _w("pBdr"))
            ET.SubElement(
                p_bdr,
                _w("left"),
                {_w("val"): "single", _w("sz"): "18", _w("space"): "8", _w("color"): "3B82F6"},
            )
            ET.SubElement(
                p_pr,
                _w("shd"),
                {_w("val"): "clear", _w("color"): "auto", _w("fill"): "F8FAFC"},
            )
        ET.SubElement(
            p_pr,
            _w("spacing"),
            {
                _w("before"): "60" if is_callout else before_dxa,
                _w("after"): after_dxa,
                _w("line"): "288",
                _w("lineRule"): "auto",
            },
        )
        if is_callout:
            ET.SubElement(p_pr, _w("ind"), {_w("left"): "240", _w("right"): "240"})
        ET.SubElement(p_pr, _w("jc"), {_w("val"): "both"})
        clean_block = (
            re.sub(r"^\s*>\s?", "", block, flags=re.MULTILINE).replace("\n", " ").strip()
            if is_callout
            else block.replace("\n", " ")
        )
        _oxml_add_markdown_runs(p_el, clean_block, sz_half_pt=21)


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
    using 100% Python standard library (zero external dependencies):
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
            _oxml_append_prose_paragraphs(
                body, str(ch["intro"]), before_dxa="40", after_dxa="120"
            )

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
                _oxml_append_prose_paragraphs(
                    body, body_text, before_dxa="0", after_dxa="100", keep_last_with_next=bool(figures)
                )

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


build_docx_internal = build_docx_stdlib_oxml


def build_docx_2pass(
    spec: Dict[str, Any],
    docx_path: str,
    page_source: str = "auto",
    no_update_prompt: bool = False,
    out_dir: Optional[str] = None,
    spec_dir: Optional[str] = None,
    export_pdf_path: Optional[str] = None,
) -> bool:
    """
    Two-pass compiler using pure-stdlib OpenXML:
    Pass 1: Build multi-section .docx with estimated page numbers.
    Pass 2: Render PDF via LibreOffice, extract exact page numbers (via pypdf or pdftotext),
            and rebuild .docx only when page numbers differ from Pass 1 estimates.
    """
    target_dir = out_dir or os.path.dirname(docx_path) or "."
    enable_update_prompt = not no_update_prompt

    def _compile_pass(p_map: Dict[str, str]) -> None:
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
            if export_pdf_path:
                export_docx_to_pdf_official(docx_path, os.path.dirname(os.path.abspath(export_pdf_path)))
            print("[OK] DOCX manual generated: " + docx_path)
            return True
        elif page_source.startswith("pdf:"):
            custom_pdf = page_source.split(":", 1)[1]
            pdf_path = validate_workspace_path(custom_pdf, must_exist=True)
        elif page_source == "auto":
            pdf_path = render_docx_to_pdf_libreoffice(docx_path, temp_dir)

        needs_rebuild = False
        if pdf_path and os.path.isfile(pdf_path):
            exact_map = extract_page_map_from_pdf(pdf_path, spec)
            if exact_map:
                merged_map = {**est_map, **exact_map}
                needs_rebuild = any(merged_map.get(k) != est_map.get(k) for k in merged_map)
                if needs_rebuild:
                    _compile_pass(merged_map)
                print(f"[OK] Resolved {len(exact_map)} exact page numbers via rendered PDF.")
            else:
                print("[NOTICE] PDF parsed but no bookmarks mapped. Keeping estimated layout.")
        else:
            print(
                "[NOTICE] LibreOffice not available for auto PDF render. DOCX contains dynamic PAGEREF fields that update automatically when opened in Word."
            )

        if export_pdf_path:
            if page_source == "auto" and pdf_path and os.path.isfile(pdf_path) and not needs_rebuild:
                os.makedirs(os.path.dirname(os.path.abspath(export_pdf_path)), exist_ok=True)
                shutil.copy2(pdf_path, export_pdf_path)
                print(f"[OK] Official PDF manual exported: {export_pdf_path}")
            else:
                export_docx_to_pdf_official(docx_path, os.path.dirname(os.path.abspath(export_pdf_path)))

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
        pdf_created = None
        if should_build_docx:
            docx_built = build_docx_2pass(
                spec_data,
                docx_out,
                page_source=args.page_source,
                no_update_prompt=args.no_word_update_prompt,
                out_dir=out_dir,
                spec_dir=spec_dir,
                export_pdf_path=pdf_out if should_export_pdf else None,
            )
            if should_export_pdf and docx_built and os.path.isfile(pdf_out):
                pdf_created = pdf_out

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
