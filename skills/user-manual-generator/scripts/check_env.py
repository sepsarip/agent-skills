#!/usr/bin/env python3
"""
Environment and dependency verifier for user-manual-generator.
Inspects Python version, optional modules (PIL, pycairo, playwright, pypdf),
Playwright Chromium browser binary, and LibreOffice / PDF rendering tools.
Works in both sandboxed and host environments.
"""

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from typing import Any, Dict


REQUIRED_MODULES = {
    "PIL": "Pillow",
    "cairo": "pycairo",
    "playwright": "playwright",
    "pypdf": "pypdf",
}


def check_python_version() -> Dict[str, Any]:
    version = sys.version_info
    valid = version >= (3, 9)
    return {
        "version": f"{version.major}.{version.minor}.{version.micro}",
        "valid": valid,
        "detail": "Python 3.9+ required" if not valid else "OK",
    }


def check_modules() -> Dict[str, Any]:
    results = {}
    missing = []
    for mod_name, pkg_name in REQUIRED_MODULES.items():
        spec = importlib.util.find_spec(mod_name)
        installed = spec is not None
        version = None
        if installed:
            try:
                mod = importlib.import_module(mod_name)
                version = getattr(mod, "__version__", "installed")
            except Exception:
                version = "installed"
        else:
            missing.append(pkg_name)
        results[mod_name] = {
            "package": pkg_name,
            "installed": installed,
            "version": version,
        }
    return {"modules": results, "missing_packages": missing}


def _find_cached_or_system_chromium() -> str:
    cache_roots = [
        os.path.join(os.getcwd(), ".venv-manual", "ms-playwright"),
        os.path.expanduser("~/.cache/ms-playwright"),
    ]
    for root in cache_roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _, filenames in os.walk(root):
            for cand_name in ("chrome", "chrome-headless-shell", "chromium"):
                if cand_name in filenames:
                    cand = os.path.join(dirpath, cand_name)
                    if os.access(cand, os.X_OK):
                        return cand
    for bin_name in ("chromium", "chromium-browser", "google-chrome", "microsoft-edge"):
        found = shutil.which(bin_name)
        if found:
            return found
    return ""


def check_playwright_chromium() -> Dict[str, Any]:
    spec = importlib.util.find_spec("playwright")
    cached_or_sys = _find_cached_or_system_chromium()
    if not spec:
        return {
            "installed": False,
            "system_browser": cached_or_sys or None,
            "detail": f"playwright module missing (system browser: {cached_or_sys})"
            if cached_or_sys
            else "playwright module missing",
        }
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            exec_path = p.chromium.executable_path
            exists = bool(exec_path and os.path.exists(exec_path))
            resolved = exec_path if exists else cached_or_sys
            return {
                "installed": bool(resolved),
                "executable_path": resolved or exec_path,
                "detail": "OK" if resolved else "Chromium executable not found",
            }
    except Exception as err:
        return {"installed": False, "system_browser": cached_or_sys or None, "detail": str(err)}


def check_soffice() -> Dict[str, Any]:
    path = shutil.which("soffice") or shutil.which("libreoffice")
    return {
        "available": bool(path),
        "path": path,
        "detail": "LibreOffice available for automatic PDF rendering"
        if path
        else "LibreOffice not in PATH (Word-fields mode available)",
    }


def check_pdftotext() -> Dict[str, Any]:
    path = shutil.which("pdftotext")
    return {
        "available": bool(path),
        "path": path,
        "detail": "pdftotext available for 2-pass PDF TOC extraction" if path else "pdftotext not in PATH",
    }


def check_liberation_sans() -> Dict[str, Any]:
    fc_list = shutil.which("fc-list")
    if not fc_list:
        return {
            "available": None,
            "detail": "fc-list not in PATH (font check skipped)",
        }
    try:
        proc = subprocess.run(
            [fc_list, ":family=Liberation Sans", "family"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        found = proc.returncode == 0 and "liberation sans" in proc.stdout.lower()
        return {
            "available": found,
            "detail": (
                "Liberation Sans installed (metric-compatible Arial fallback for LibreOffice)"
                if found
                else "WARNING: Liberation Sans not found (install fonts-liberation for accurate LibreOffice PDF pagination)"
            ),
        }
    except Exception as err:
        return {
            "available": False,
            "detail": f"WARNING: Liberation Sans check failed ({err})",
        }


def check_venv() -> Dict[str, Any]:
    is_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    cwd = os.getcwd()
    local_venv = os.path.join(cwd, ".venv-manual")
    has_local_venv = os.path.isdir(local_venv)
    return {
        "is_active_venv": is_venv,
        "sys_prefix": sys.prefix,
        "local_venv_exists": has_local_venv,
        "local_venv_path": local_venv if has_local_venv else None,
    }


def check_pip() -> Dict[str, Any]:
    has_pip = importlib.util.find_spec("pip") is not None or shutil.which("pip3") is not None
    return {
        "available": bool(has_pip),
        "detail": "pip available" if has_pip else "pip not installed (offline / restricted environment)",
    }


def inspect_environment(profile: str = "all") -> Dict[str, Any]:
    py_info = check_python_version()
    mod_info = check_modules()
    pw_info = check_playwright_chromium()
    so_info = check_soffice()
    pdf_txt_info = check_pdftotext()
    lib_sans_info = check_liberation_sans()
    venv_info = check_venv()
    pip_info = check_pip()

    has_docx = py_info["valid"]
    docx_engine = "stdlib-oxml + libreoffice" if so_info["available"] else "stdlib-oxml"
    has_pdf_toc = so_info["available"] and (
        mod_info["modules"]["pypdf"]["installed"] or pdf_txt_info["available"]
    )
    pdf_toc_engine = (
        f"soffice + {'pypdf' if mod_info['modules']['pypdf']['installed'] else 'pdftotext'}"
        if has_pdf_toc
        else ("soffice only" if so_info["available"] else "none")
    )

    has_annotation = (
        mod_info["modules"]["PIL"]["installed"]
        or mod_info["modules"]["cairo"]["installed"]
    )
    if mod_info["modules"]["cairo"]["installed"] and mod_info["modules"]["PIL"]["installed"]:
        annotation_engine = "PyCairo + Pillow"
    elif mod_info["modules"]["cairo"]["installed"]:
        annotation_engine = "PyCairo"
    elif mod_info["modules"]["PIL"]["installed"]:
        annotation_engine = "Pillow"
    else:
        annotation_engine = "none"

    capabilities = {
        "markdown": py_info["valid"],
        "state_gap_analysis": py_info["valid"],
        "docx": has_docx,
        "docx_engine": docx_engine,
        "pdf_2pass_toc": has_pdf_toc,
        "pdf_2pass_engine": pdf_toc_engine,
        "browser_capture": pw_info["installed"],
        "annotation": has_annotation,
        "annotation_engine": annotation_engine,
    }

    missing_critical = [
        pkg
        for pkg in mod_info["missing_packages"]
        if pkg not in ("Pillow", "pycairo")
    ]
    if not has_annotation:
        missing_critical.append("Pillow or pycairo")

    ready_full = (
        py_info["valid"]
        and len(missing_critical) == 0
        and pw_info["installed"]
    )
    ready_core = py_info["valid"] and has_docx

    if profile == "markdown":
        profile_ready = capabilities["markdown"]
    elif profile == "docx":
        profile_ready = capabilities["docx"]
    elif profile == "capture":
        profile_ready = capabilities["browser_capture"]
    else:
        profile_ready = ready_full

    return {
        "ready": profile_ready,
        "ready_full": ready_full,
        "ready_core": ready_core,
        "capabilities": capabilities,
        "python": py_info,
        "dependencies": mod_info,
        "playwright_chromium": pw_info,
        "libreoffice": so_info,
        "pdftotext": pdf_txt_info,
        "liberation_sans": lib_sans_info,
        "virtualenv": venv_info,
        "pip": pip_info,
    }


def format_text_report(info: Dict[str, Any], profile: str = "all") -> str:
    lines = []
    lines.append("=== user-manual-generator Environment & Capability Check ===")
    py = info["python"]
    lines.append(f"Python: {py['version']} [{'OK' if py['valid'] else 'FAIL'}]")

    lines.append("\nCapability Matrix:")
    caps = info["capabilities"]
    lines.append("  ✓ Markdown Manual (.md): READY (100% Python Standard Library)")
    lines.append("  ✓ State & Gap Analysis: READY (100% Python Standard Library)")
    if caps["docx"]:
        lines.append(f"  ✓ Word Export (.docx): READY (Engine: {caps['docx_engine']})")
    else:
        lines.append("  ✗ Word Export (.docx): NOT READY (Python 3.9+ required)")

    if caps["pdf_2pass_toc"]:
        lines.append(f"  ✓ PDF Export & 2-Pass TOC: READY (Engine: {caps['pdf_2pass_engine']})")
    elif info["libreoffice"]["available"]:
        lines.append("  ⚠ PDF Export & 2-Pass TOC: PARTIAL (LibreOffice available; pypdf/pdftotext missing for exact TOC pages)")
    else:
        lines.append("  ⚠ PDF Export & 2-Pass TOC: OPTIONAL (LibreOffice not found; dynamic PAGEREF fields active)")

    if caps["browser_capture"]:
        lines.append("  ✓ Browser Auto-Capture: READY (Playwright Chromium)")
    else:
        lines.append("  ⚠ Browser Auto-Capture: OPTIONAL (Playwright missing; use Browser MCP/DevTools or manual raw screenshots)")

    if caps["annotation"]:
        lines.append(f"  ✓ Visual Arrow Annotation: READY (Engine: {caps['annotation_engine']})")
    else:
        lines.append("  ⚠ Visual Arrow Annotation: OPTIONAL (Pillow and PyCairo missing; place pre-annotated screenshots in final/)")

    lines.append("\nTooling & Runtime Details:")
    for mod, data in info["dependencies"]["modules"].items():
        status = f"OK ({data['version']})" if data["installed"] else "MISSING"
        lines.append(f"  - {data['package']} ({mod}): {status}")

    pw = info["playwright_chromium"]
    lines.append(f"  - Playwright Chromium: {'OK' if pw['installed'] else 'MISSING'}")

    so = info["libreoffice"]
    lines.append(f"  - LibreOffice (soffice): {'AVAILABLE' if so['available'] else 'NOT FOUND'}")

    pt = info["pdftotext"]
    lines.append(f"  - pdftotext (poppler): {'AVAILABLE' if pt['available'] else 'NOT FOUND'}")

    ls_font = info["liberation_sans"]
    if ls_font["available"] is True:
        ls_status = "AVAILABLE"
    elif ls_font["available"] is False:
        ls_status = "WARNING - NOT FOUND (install fonts-liberation for LibreOffice Arial metrics)"
    else:
        ls_status = "SKIPPED (fc-list not in PATH)"
    lines.append(f"  - Liberation Sans Font: {ls_status}")

    pip_data = info["pip"]
    lines.append(f"  - Pip Package Manager: {'AVAILABLE' if pip_data['available'] else 'NOT INSTALLED'}")

    lines.append("\nSummary:")
    if info["ready"]:
        lines.append(f"  [STATUS: READY] Profile '{profile}' is fully satisfied.")
    elif info["ready_core"]:
        lines.append("  [STATUS: VIABLE FOR CORE WORKFLOW]")
        lines.append("  Core capabilities (Markdown, Gap Analysis, and stdlib OpenXML DOCX) are READY to use.")
        lines.append("  No internet connection or external pip package is required for core manual generation.")
    else:
        lines.append("  [STATUS: SETUP NEEDED] Python 3.9+ required.")

    if not info["ready_full"]:
        lines.append("\nOffline & Fallback Workflow Notes:")
        lines.append("1. Markdown & DOCX Manuals: Built-in 100% Python stdlib OpenXML builder requires zero pip packages.")
        lines.append("2. Screenshots: Place images directly in 'docs/manual_book/assets/raw/' or use Browser MCP tools.")
        if pip_data["available"]:
            lines.append("3. Full Suite Installation (if internet is available):")
            lines.append("   python3 -m venv .venv-manual")
            lines.append("   .venv-manual/bin/pip install Pillow playwright pypdf")
            lines.append("   PLAYWRIGHT_BROWSERS_PATH=.venv-manual/ms-playwright .venv-manual/bin/python -m playwright install chromium")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check environment readiness for user-manual-generator.")
    parser.add_argument(
        "--profile",
        choices=["all", "markdown", "docx", "capture"],
        default="all",
        help="Target capability profile to verify (default: 'all').",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Strict mode: require all optional packages (Pillow/pycairo, playwright, pypdf) to pass.",
    )
    parser.add_argument("--json", action="store_true", help="Output report in JSON format.")
    parser.add_argument("--quiet", action="store_true", help="Suppress output, exit code indicates readiness.")
    args = parser.parse_args()

    info = inspect_environment(profile=args.profile)

    if not args.quiet:
        if args.json:
            print(json.dumps(info, indent=2))
        else:
            print(format_text_report(info, profile=args.profile))

    if args.strict:
        is_ready = info["ready_full"]
    else:
        is_ready = info["ready_core"] if args.profile == "all" else info["ready"]

    sys.exit(0 if is_ready else 1)


if __name__ == "__main__":
    main()

