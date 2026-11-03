#!/usr/bin/env python3
"""
State, Resume, Coverage, Import, and Renumbering Manager for user-manual-generator.
Provides task continuation, gap analysis against application features,
legacy markdown import, and dynamic citation renumbering.
"""

import argparse
import datetime
import json
import os
import re
import shlex
import sys
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple


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


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json_atomic(path: str, data: Any) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    temp_path = f"{path}.tmp.{uuid.uuid4().hex}"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(temp_path, path)


# ---------------------------------------------------------
# Subcommand: status (Progress and Next Step Determination)
# ---------------------------------------------------------
def cmd_status(args: argparse.Namespace) -> None:
    spec_path = validate_workspace_path(args.spec, must_exist=True)
    out_dir = validate_workspace_path(args.out_dir, must_exist=False)
    progress_path = (
        validate_workspace_path(args.progress, must_exist=False)
        if args.progress
        else os.path.join(os.path.dirname(spec_path), "manual_progress.json")
    )

    spec = load_json(spec_path)
    progress = {}
    if os.path.exists(progress_path):
        try:
            progress = load_json(progress_path)
        except Exception:
            progress = {}

    chapters = spec.get("chapters", [])
    total_figures = 0
    missing_raw = []
    missing_annotated = []
    unverified_figures = []

    fig_verified_map = progress.get("figures", {})
    outline_approved = progress.get("outline_approved", False)

    for ch in chapters:
        for sec in ch.get("sections", []):
            for fig in sec.get("figures", []):
                total_figures += 1
                fig_id = str(fig.get("id", ""))
                final_path = fig.get("image_path", "")
                source_info = fig.get("source", {})
                raw_path = source_info.get("raw", "")
                url = source_info.get("url", "")

                # Check raw capture
                if raw_path and not os.path.exists(raw_path):
                    missing_raw.append({"id": fig_id, "url": url, "raw": raw_path})

                # Check final annotated image
                if not final_path or not os.path.exists(final_path):
                    missing_annotated.append(
                        {
                            "id": fig_id,
                            "raw": raw_path,
                            "final": final_path,
                            "source": source_info,
                        }
                    )
                else:
                    # Final exists, check if visually verified
                    fig_meta = fig_verified_map.get(fig_id, {})
                    if not fig_meta.get("verified", False):
                        unverified_figures.append({"id": fig_id, "final": final_path})

    # Check output documents
    basename = args.basename or spec.get("basename", "Manual_Book")
    md_out = os.path.join(out_dir, f"{basename}.md")
    docx_out = os.path.join(out_dir, f"{basename}.docx")

    out_md_exists = os.path.exists(md_out)
    out_docx_exists = os.path.exists(docx_out)
    spec_mtime = os.path.getmtime(spec_path)
    docx_mtime = os.path.getmtime(docx_out) if out_docx_exists else 0
    md_mtime = os.path.getmtime(md_out) if out_md_exists else 0
    is_stale = (out_docx_exists and spec_mtime > docx_mtime) or (out_md_exists and spec_mtime > md_mtime)
    outputs_missing = not out_docx_exists or not out_md_exists

    # Determine NEXT action
    next_action = None
    if not outline_approved and not args.force:
        next_action = {
            "step": "Approve Outline",
            "command": f"python3 scripts/manual_state.py mark --progress {shlex.quote(progress_path)} --phase outline-approved",
            "reason": "Manual outline is not yet marked as approved by user.",
        }
    elif missing_raw:
        item = missing_raw[0]
        url_arg = f"--url {shlex.quote(item['url'])}" if item["url"] else "--url <URL>"
        next_action = {
            "step": "Capture Raw Screenshot",
            "command": f"python3 scripts/capture_and_annotate.py capture {url_arg} --output {shlex.quote(item['raw'])}",
            "reason": f"Raw screenshot for Figure {item['id']} is missing.",
        }
    elif missing_annotated:
        item = missing_annotated[0]
        targets = item.get("source", {}).get("targets", [])
        if targets:
            t_args = " ".join([f"--target {shlex.quote(t)}" for t in targets])
            cmd = f"python3 scripts/capture_and_annotate.py annotate --auto --input {shlex.quote(item['raw'])} --output {shlex.quote(item['final'])} {t_args}"
        else:
            cmd = f"python3 scripts/capture_and_annotate.py annotate --auto --input {shlex.quote(item['raw'])} --output {shlex.quote(item['final'])}"
        next_action = {
            "step": "Annotate Screenshot",
            "command": cmd,
            "reason": f"Annotated final image for Figure {item['id']} is missing.",
        }
    elif unverified_figures:
        item = unverified_figures[0]
        next_action = {
            "step": "Visual Verification",
            "command": f"python3 scripts/manual_state.py mark --progress {shlex.quote(progress_path)} --figure {shlex.quote(item['id'])} --verified",
            "reason": f"Figure {item['id']} ({item['final']}) needs visual verification to ensure arrows do not occlude text.",
        }
    elif outputs_missing or is_stale:
        if outputs_missing:
            reason = "Output document (.docx or .md) is missing."
        else:
            reason = "Output documents are older than manual_spec.json."
        next_action = {
            "step": "Build Outputs",
            "command": f"python3 scripts/build_manual.py --spec {shlex.quote(spec_path)} --out-dir {shlex.quote(out_dir)} --basename {shlex.quote(basename)}",
            "reason": reason,
        }
    else:
        next_action = {
            "step": "Completed",
            "command": None,
            "reason": "All figures captured, annotated, verified, and documents compiled up to date.",
        }

    status_report = {
        "spec": spec_path,
        "outline_approved": outline_approved,
        "total_chapters": len(chapters),
        "total_figures": total_figures,
        "missing_raw": len(missing_raw),
        "missing_annotated": len(missing_annotated),
        "unverified_figures": len(unverified_figures),
        "output_md_exists": out_md_exists,
        "output_docx_exists": out_docx_exists,
        "output_is_stale": is_stale,
        "next": next_action,
    }

    if args.json:
        print(json.dumps(status_report, indent=2))
        return

    print("=== user-manual-generator Progress Status ===")
    print(f"Spec File: {spec_path}")
    print(f"Outline Approved: {'YES' if outline_approved else 'NO'}")
    print(f"Total Figures: {total_figures}")
    print(f"  - Missing Raw Captures: {len(missing_raw)}")
    print(f"  - Missing Annotations:  {len(missing_annotated)}")
    print(f"  - Unverified Figures:   {len(unverified_figures)}")
    print(f"Output MD:   {'EXISTS' if out_md_exists else 'NOT FOUND'} ({md_out})")
    print(f"Output DOCX: {'EXISTS' if out_docx_exists else 'NOT FOUND'} ({docx_out})")
    if is_stale:
        print("  [!] Output documents are older than manual_spec.json (rebuild required).")

    print("\n---------------------------------------------------------")
    if next_action["command"]:
        print(f"NEXT ACTION: [{next_action['step']}]")
        print(f"Reason: {next_action['reason']}")
        print(f"Run:\n  {next_action['command']}")
    else:
        print("STATUS: ALL DONE! All steps and artifacts are verified and up to date.")
    print("---------------------------------------------------------")


# ---------------------------------------------------------
# Subcommand: mark (Update Progress Markers)
# ---------------------------------------------------------
def cmd_mark(args: argparse.Namespace) -> None:
    progress_path = validate_workspace_path(args.progress, must_exist=False)
    data = {}
    if os.path.exists(progress_path):
        try:
            data = load_json(progress_path)
        except Exception:
            data = {}

    data.setdefault("schema", 1)
    data.setdefault("figures", {})
    data.setdefault("log", [])

    now_iso = datetime.datetime.now().astimezone().isoformat()

    if args.phase:
        if args.phase == "outline-approved":
            data["outline_approved"] = True
            data["log"].append({"at": now_iso, "event": "outline-approved"})
            print(f"[OK] Marked outline as approved in {progress_path}")

    if args.figure:
        fig_id = str(args.figure)
        fig_entry = data["figures"].setdefault(fig_id, {})
        if args.verified:
            fig_entry["verified"] = True
            fig_entry["verified_at"] = now_iso
            data["log"].append({"at": now_iso, "event": f"figure {fig_id} verified"})
            print(f"[OK] Marked figure {fig_id} as verified in {progress_path}")
        if args.comment:
            fig_entry["comment"] = args.comment

    save_json_atomic(progress_path, data)


# ---------------------------------------------------------
# Subcommand: coverage (Gap Analysis against Feature Inventory)
# ---------------------------------------------------------
def cmd_coverage(args: argparse.Namespace) -> None:
    spec_path = validate_workspace_path(args.spec, must_exist=True)
    inventory_path = validate_workspace_path(args.inventory, must_exist=True)

    spec = load_json(spec_path)
    inventory = load_json(inventory_path)

    if isinstance(inventory, list):
        raw_features = inventory
    elif isinstance(inventory, dict):
        raw_features = inventory.get("features")
        if raw_features is None:
            raw_features = inventory.get("items")
        if raw_features is None:
            raw_features = []
    else:
        raise ValueError(
            f"Invalid format in inventory file '{inventory_path}': "
            "expected JSON array '[{...}]' or JSON object with 'features' key."
        )

    if not isinstance(raw_features, list):
        raise ValueError(
            f"Invalid format in inventory file '{inventory_path}': "
            "'features' must be an array of objects or strings."
        )

    features: List[Dict[str, Any]] = []
    for item in raw_features:
        if isinstance(item, dict):
            features.append(item)
        elif isinstance(item, str):
            features.append({"id": item, "name": item, "route": ""})
        else:
            features.append({"id": str(item), "name": str(item), "route": ""})

    # Collect documented features from manual_spec
    documented_keys: Set[str] = set()
    documented_urls: Set[str] = set()
    section_map: Dict[str, List[str]] = {}

    for ch in spec.get("chapters", []):
        for sec in ch.get("sections", []):
            sec_num = sec.get("number", "")
            sec_title = sec.get("title", "")
            sec_label = f"{sec_num} {sec_title}".strip()

            for key in sec.get("covers", []):
                documented_keys.add(key.lower())
                section_map.setdefault(key.lower(), []).append(sec_label)

            for fig in sec.get("figures", []):
                for key in fig.get("covers", []):
                    documented_keys.add(key.lower())
                    section_map.setdefault(key.lower(), []).append(sec_label)
                source_url = fig.get("source", {}).get("url", "")
                if source_url:
                    documented_urls.add(source_url.rstrip("/").lower())

    covered: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []

    inventory_keys: Set[str] = set()
    documented_norms = {re.sub(r"[-_\s]", "", k) for k in documented_keys}

    for feat in features:
        feat_id = str(feat.get("id", "")).lower()
        feat_name = feat.get("name", "")
        feat_route = feat.get("route", "").rstrip("/").lower()
        inventory_keys.add(feat_id)
        feat_norm = re.sub(r"[-_\s]", "", feat_id)

        is_covered = (
            feat_id in documented_keys
            or feat_norm in documented_norms
            or (feat_route and feat_route in documented_urls)
        )

        locs = section_map.get(feat_id, [])
        if is_covered:
            covered.append({"feature": feat, "sections": locs})
        else:
            missing.append(feat)

    # Detect stale items documented in manual but no longer present in inventory
    stale_keys = [k for k in documented_keys if k not in inventory_keys]

    report = {
        "total_inventory_features": len(features),
        "covered_count": len(covered),
        "missing_count": len(missing),
        "stale_count": len(stale_keys),
        "covered": covered,
        "missing": missing,
        "stale_keys": stale_keys,
    }

    if args.json:
        print(json.dumps(report, indent=2))
        return

    # Text presentation
    print("=== Feature Coverage & Manual Gap Analysis ===")
    pct = (len(covered) / len(features) * 100) if features else 100.0
    print(f"Coverage: {len(covered)}/{len(features)} features documented ({pct:.1f}%)\n")

    print("[COVERED FEATURES]")
    if covered:
        for item in covered:
            f = item["feature"]
            sec_str = f" (in: {', '.join(item['sections'])})" if item["sections"] else ""
            print(f"  ✓ [{f.get('id')}] {f.get('name')}{sec_str}")
    else:
        print("  (None)")

    print("\n[MISSING / NOT YET IN MANUAL]")
    if missing:
        for f in missing:
            route_str = f" [Route: {f.get('route')}]" if f.get("route") else ""
            print(f"  ✗ [{f.get('id')}] {f.get('name')}{route_str}")
    else:
        print("  (None - All inventory features covered!)")

    if stale_keys:
        print("\n[STALE / REMOVED FEATURES IN MANUAL]")
        for k in stale_keys:
            print(f"  ? [{k}] exists in manual_spec but not in feature_inventory.json")

    if args.report:
        report_path = validate_workspace_path(args.report, must_exist=False)
        report_dir = os.path.dirname(report_path)
        if report_dir:
            os.makedirs(report_dir, exist_ok=True)
        md_lines = [
            "# Manual Coverage and Gap Analysis Report",
            f"\n- **Coverage**: {len(covered)}/{len(features)} ({pct:.1f}%)",
            f"- **Date**: {datetime.date.today().isoformat()}",
            "\n## Missing Features (To Be Added)",
        ]
        for f in missing:
            md_lines.append(f"- **[{f.get('id')}] {f.get('name')}**: {f.get('description', '')} (Route: `{f.get('route', '-')}`)")
        md_lines.append("\n## Covered Features")
        for item in covered:
            f = item["feature"]
            md_lines.append(f"- **[{f.get('id')}] {f.get('name')}**")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines) + "\n")
        print(f"\n[OK] Markdown gap report saved to: {report_path}")


# ---------------------------------------------------------
# Subcommand: import-md (Extract Structure from Existing Markdown)
# ---------------------------------------------------------
def cmd_import_md(args: argparse.Namespace) -> None:
    in_path = validate_workspace_path(args.input, must_exist=True)
    out_spec = validate_workspace_path(args.spec_out, must_exist=False)
    spec_dir = os.path.dirname(out_spec)
    if spec_dir:
        os.makedirs(spec_dir, exist_ok=True)

    with open(in_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.splitlines()
    spec: Dict[str, Any] = {
        "title": "Application User Manual",
        "subtitle": "",
        "version": "1.0.0",
        "date": datetime.date.today().isoformat(),
        "language": "en",
        "chapters": [],
    }

    current_ch: Optional[Dict[str, Any]] = None
    current_sec: Optional[Dict[str, Any]] = None
    current_fig: Optional[Dict[str, Any]] = None

    re_h1 = re.compile(r"^#\s+(.+)$")
    re_h2 = re.compile(r"^##\s+(?:Chapter|Bab)?\s*(\d+)?[:.]?\s*(.+)$", re.IGNORECASE)
    re_h3 = re.compile(r"^###\s+(\d+\.\d+)?\s*(.+)$")
    re_img = re.compile(r"^!\[(.*?)\]\((.*?)\)$")
    re_footer = re.compile(r"^\*?(?:Page|Halaman)\s+\d+(?:\s+(?:of|dari)\s+\d+)?\*?$", re.IGNORECASE)

    ch_counter = 0

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped == "---" or stripped.startswith("<div style="):
            continue
        if re_footer.match(stripped):
            continue

        # Check H1
        m1 = re_h1.match(stripped)
        if m1 and not current_ch:
            spec["title"] = m1.group(1).strip()
            continue

        # Check H2 (Chapter)
        m2 = re_h2.match(stripped)
        if m2:
            ch_title = m2.group(2).strip()
            if ch_title.lower() in {"table of contents", "daftar isi", "list of figures", "daftar gambar"}:
                continue
            ch_counter += 1
            ch_num = int(m2.group(1)) if m2.group(1) else ch_counter
            current_ch = {
                "number": ch_num,
                "title": ch_title,
                "intro": "",
                "sections": [],
            }
            spec["chapters"].append(current_ch)
            current_sec = None
            current_fig = None
            continue

        # Check H3 (Section)
        m3 = re_h3.match(stripped)
        if m3 and current_ch:
            sec_num = m3.group(1) or f"{current_ch['number']}.{len(current_ch['sections']) + 1}"
            sec_title = m3.group(2).strip()
            current_sec = {
                "number": sec_num,
                "title": sec_title,
                "body": "",
                "figures": [],
            }
            current_ch["sections"].append(current_sec)
            current_fig = None
            continue

        # Check Image
        m_img = re_img.match(stripped)
        if m_img and current_sec:
            caption = m_img.group(1).strip()
            img_path = m_img.group(2).strip()
            # Parse figure id if present: "Figure 1.1: Title"
            fig_id = f"{current_sec['number']}.{len(current_sec['figures']) + 1}"
            fig_title = caption
            m_cap = re.match(r"^(?:Figure|Gambar)\s*(\d+\.\d+)[:.]?\s*(.*)$", caption, re.IGNORECASE)
            if m_cap:
                fig_id = m_cap.group(1)
                fig_title = m_cap.group(2) or caption

            current_fig = {
                "id": fig_id,
                "title": fig_title,
                "image_path": img_path,
                "bullets": [],
            }
            current_sec["figures"].append(current_fig)
            continue

        # Check Bullets for current figure
        if stripped.startswith("- ") and current_fig:
            current_fig["bullets"].append(stripped[2:].strip())
            continue

        # If non-bullet text is encountered, figure bullet list is ended
        if current_fig and not stripped.startswith("- "):
            current_fig = None

        # Body text
        if current_sec:
            if current_sec["body"]:
                current_sec["body"] += "\n\n" + stripped if stripped.startswith("- ") else " " + stripped
            else:
                current_sec["body"] = stripped
        elif current_ch and not current_sec:
            if current_ch["intro"]:
                current_ch["intro"] += " " + stripped
            else:
                current_ch["intro"] = stripped

    save_json_atomic(out_spec, spec)
    print(f"[OK] Imported {len(spec['chapters'])} chapters into spec: {out_spec}")


# ---------------------------------------------------------
# Subcommand: renumber (Consistent Renumbering of Chapters, Figures, Citations)
# ---------------------------------------------------------
def cmd_renumber(args: argparse.Namespace) -> None:
    spec_path = validate_workspace_path(args.spec, must_exist=True)
    spec = load_json(spec_path)

    id_map: Dict[str, str] = {}
    lang = spec.get("language", "en")
    fig_word = "Gambar" if lang.lower().startswith("id") else "Figure"

    # Assign sequential numbers
    for ch_idx, ch in enumerate(spec.get("chapters", []), start=1):
        ch["number"] = ch_idx
        fig_counter = 0
        for sec_idx, sec in enumerate(ch.get("sections", []), start=1):
            sec["number"] = f"{ch_idx}.{sec_idx}"
            for fig in sec.get("figures", []):
                fig_counter += 1
                old_id = str(fig.get("id", ""))
                new_id = f"{ch_idx}.{fig_counter}"
                if old_id and old_id != new_id:
                    id_map[old_id] = new_id
                fig["id"] = new_id

    # If ID mapping changed, replace citations safely in 2 phases
    if id_map:
        temp_map: Dict[str, str] = {}
        for old_id, new_id in id_map.items():
            temp_token = f"__FIG_TOKEN_{uuid.uuid4().hex[:8]}__"
            temp_map[temp_token] = new_id

            # Phase 1: old_id -> temp_token
            # Matches Figure 1.2, Gambar 1.2, (Figure 1.2), etc.
            pattern = re.compile(rf"\b(Figure|Gambar|Fig\.)\s+{re.escape(old_id)}\b", re.IGNORECASE)

            def _replace_phase1(text: str) -> str:
                return pattern.sub(rf"\1 {temp_token}", text)

            for ch in spec.get("chapters", []):
                if ch.get("intro"):
                    ch["intro"] = _replace_phase1(ch["intro"])
                for sec in ch.get("sections", []):
                    if sec.get("body"):
                        sec["body"] = _replace_phase1(sec["body"])
                    for fig in sec.get("figures", []):
                        fig["bullets"] = [_replace_phase1(b) for b in fig.get("bullets", [])]

        # Phase 2: temp_token -> new_id
        for temp_token, new_id in temp_map.items():
            for ch in spec.get("chapters", []):
                if ch.get("intro"):
                    ch["intro"] = ch["intro"].replace(temp_token, new_id)
                for sec in ch.get("sections", []):
                    if sec.get("body"):
                        sec["body"] = sec["body"].replace(temp_token, new_id)
                    for fig in sec.get("figures", []):
                        fig["bullets"] = [b.replace(temp_token, new_id) for b in fig.get("bullets", [])]

    save_json_atomic(spec_path, spec)
    print(f"[OK] Renumbered {len(spec.get('chapters', []))} chapters. Updated {len(id_map)} figure IDs in {spec_path}.")


# ---------------------------------------------------------
# Subcommand: outline-docx (Read-only Outline from DOCX)
# ---------------------------------------------------------
def cmd_outline_docx(args: argparse.Namespace) -> None:
    docx_path = validate_workspace_path(args.input, must_exist=True)
    try:
        from docx import Document
    except ImportError:
        sys.exit("Error: python-docx is required for outline-docx. Run: pip install python-docx")

    doc = Document(docx_path)
    print(f"=== Document Outline: {docx_path} ===")
    for p in doc.paragraphs:
        style_name = p.style.name if p.style else ""
        text = p.text.strip()
        if not text:
            continue
        if "Heading 1" in style_name:
            print(f"# {text}")
        elif "Heading 2" in style_name:
            print(f"  ## {text}")
        elif "Heading 3" in style_name:
            print(f"    ### {text}")
        elif text.lower().startswith("figure") or text.lower().startswith("gambar"):
            print(f"      [Image Caption] {text}")


# ---------------------------------------------------------
# CLI Parser Setup
# ---------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="State, resume, gap coverage, import, and renumbering manager."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # status
    p_stat = sub.add_parser("status", help="Check progress and determine NEXT actionable command.")
    p_stat.add_argument(
        "--spec",
        default="docs/manual_book/manual_spec.json",
        help="Path to manual_spec.json (default: docs/manual_book/manual_spec.json).",
    )
    p_stat.add_argument(
        "--out-dir",
        default="docs/manual_book",
        help="Output directory containing .md/.docx (default: docs/manual_book).",
    )
    p_stat.add_argument("--basename", default="", help="Base name of generated manual book.")
    p_stat.add_argument("--progress", default="", help="Path to manual_progress.json (default: <spec_dir>/manual_progress.json).")
    p_stat.add_argument("--force", action="store_true", help="Ignore outline-approved gate.")
    p_stat.add_argument("--json", action="store_true", help="Output status as JSON.")
    p_stat.set_defaults(func=cmd_status)

    # mark
    p_mark = sub.add_parser("mark", help="Record progress milestones and visual verification.")
    p_mark.add_argument(
        "--progress",
        default="docs/manual_book/manual_progress.json",
        help="Path to manual_progress.json (default: docs/manual_book/manual_progress.json).",
    )
    p_mark.add_argument("--phase", choices=["outline-approved"], help="Record milestone phase.")
    p_mark.add_argument("--figure", help="Figure ID to mark (e.g. '1.1').")
    p_mark.add_argument("--verified", action="store_true", help="Mark figure as visually verified.")
    p_mark.add_argument("--comment", help="Optional comment or inspection note.")
    p_mark.set_defaults(func=cmd_mark)

    # coverage
    p_cov = sub.add_parser("coverage", help="Analyze manual coverage against feature inventory.")
    p_cov.add_argument(
        "--spec",
        default="docs/manual_book/manual_spec.json",
        help="Path to manual_spec.json (default: docs/manual_book/manual_spec.json).",
    )
    p_cov.add_argument(
        "--inventory",
        default="docs/manual_book/feature_inventory.json",
        help="Path to feature_inventory.json (default: docs/manual_book/feature_inventory.json).",
    )
    p_cov.add_argument(
        "--report",
        default="docs/manual_book/manual_gap_report.md",
        help="Output path for Markdown gap report (default: docs/manual_book/manual_gap_report.md).",
    )
    p_cov.add_argument("--json", action="store_true", help="Output coverage as JSON.")
    p_cov.set_defaults(func=cmd_coverage)

    # import-md
    p_imp = sub.add_parser("import-md", help="Convert existing Markdown manual into manual_spec.json.")
    p_imp.add_argument("--input", required=True, help="Input Markdown file.")
    p_imp.add_argument(
        "--spec-out",
        default="docs/manual_book/manual_spec.json",
        help="Output manual_spec.json path (default: docs/manual_book/manual_spec.json).",
    )
    p_imp.set_defaults(func=cmd_import_md)

    # renumber
    p_ren = sub.add_parser("renumber", help="Renumber chapters, sections, and figures sequentially.")
    p_ren.add_argument(
        "--spec",
        default="docs/manual_book/manual_spec.json",
        help="Path to manual_spec.json (default: docs/manual_book/manual_spec.json).",
    )
    p_ren.set_defaults(func=cmd_renumber)

    # outline-docx
    p_od = sub.add_parser("outline-docx", help="Extract headings and captions from DOCX.")
    p_od.add_argument("--input", required=True, help="Path to DOCX file.")
    p_od.set_defaults(func=cmd_outline_docx)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as err:
        sys.exit(f"[ERROR] {err}")


if __name__ == "__main__":
    main()
