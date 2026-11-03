#!/usr/bin/env python3
"""
Environment and dependency verifier for user-manual-generator.
Inspects Python version, required modules (PIL, python-docx, playwright, pypdf),
Playwright Chromium browser binary, and LibreOffice / PDF rendering tools.
Works in both sandboxed and host environments.
"""

import argparse
import importlib.util
import json
import os
import shutil
import sys
from typing import Any, Dict


REQUIRED_MODULES = {
    "PIL": "Pillow",
    "cairo": "pycairo",
    "docx": "python-docx",
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


def check_playwright_chromium() -> Dict[str, Any]:
    spec = importlib.util.find_spec("playwright")
    if not spec:
        return {"installed": False, "detail": "playwright module missing"}
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            exec_path = p.chromium.executable_path
            exists = os.path.exists(exec_path) if exec_path else False
            return {
                "installed": exists,
                "executable_path": exec_path,
                "detail": "OK" if exists else "Chromium executable not found",
            }
    except Exception as err:
        return {"installed": False, "detail": str(err)}


def check_soffice() -> Dict[str, Any]:
    path = shutil.which("soffice") or shutil.which("libreoffice")
    return {
        "available": bool(path),
        "path": path,
        "detail": "LibreOffice available for automatic PDF rendering"
        if path
        else "LibreOffice not in PATH (manual PDF export or Word-fields mode available)",
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
    venv_info = check_venv()
    pip_info = check_pip()

    has_docx = mod_info["modules"]["docx"]["installed"] or so_info["available"]
    docx_engine = (
        "python-docx"
        if mod_info["modules"]["docx"]["installed"]
        else ("libreoffice" if so_info["available"] else "none")
    )

    has_annotation = (
        mod_info["modules"]["PIL"]["installed"]
        or mod_info["modules"]["cairo"]["installed"]
    )
    annotation_engine = (
        "Pillow"
        if mod_info["modules"]["PIL"]["installed"]
        else ("PyCairo" if mod_info["modules"]["cairo"]["installed"] else "none")
    )

    capabilities = {
        "markdown": py_info["valid"],
        "state_gap_analysis": py_info["valid"],
        "docx": has_docx,
        "docx_engine": docx_engine,
        "browser_capture": pw_info["installed"],
        "annotation": has_annotation,
        "annotation_engine": annotation_engine,
    }

    # Annotation is satisfied if either Pillow or PyCairo is present
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
    lines.append(f"  ✓ Markdown Manual (.md): READY (100% Python Standard Library)")
    lines.append(f"  ✓ State & Gap Analysis: READY (100% Python Standard Library)")
    if caps["docx"]:
        lines.append(f"  ✓ Word Export (.docx): READY (Engine: {caps['docx_engine']})")
    else:
        lines.append(f"  ✗ Word Export (.docx): NOT READY (python-docx and LibreOffice missing)")

    if caps["browser_capture"]:
        lines.append(f"  ✓ Browser Auto-Capture: READY (Playwright Chromium)")
    else:
        lines.append(f"  ⚠ Browser Auto-Capture: OPTIONAL (Playwright missing; use Browser MCP/DevTools or manual raw screenshots)")

    if caps["annotation"]:
        lines.append(f"  ✓ Visual Arrow Annotation: READY (Engine: {caps['annotation_engine']})")
    else:
        lines.append(f"  ⚠ Visual Arrow Annotation: OPTIONAL (Pillow and PyCairo missing; place pre-annotated screenshots in final/)")

    lines.append("\nTooling & Runtime Details:")
    for mod, data in info["dependencies"]["modules"].items():
        status = f"OK ({data['version']})" if data["installed"] else "MISSING"
        lines.append(f"  - {data['package']} ({mod}): {status}")

    pw = info["playwright_chromium"]
    lines.append(f"  - Playwright Chromium: {'OK' if pw['installed'] else 'MISSING'}")

    so = info["libreoffice"]
    lines.append(f"  - LibreOffice (/usr/bin/soffice): {'AVAILABLE' if so['available'] else 'NOT FOUND'}")

    pip_data = info["pip"]
    lines.append(f"  - Pip Package Manager: {'AVAILABLE' if pip_data['available'] else 'NOT INSTALLED'}")

    lines.append("\nSummary:")
    if info["ready"]:
        lines.append(f"  [STATUS: READY] Profile '{profile}' is fully satisfied.")
    elif info["ready_core"]:
        lines.append(f"  [STATUS: VIABLE FOR CORE WORKFLOW]")
        lines.append("  Core capabilities (Markdown, Gap Analysis, and DOCX via fallback) are READY to use.")
        lines.append("  No internet connection or external pip package is required for core manual generation.")
    else:
        lines.append("  [STATUS: SETUP NEEDED] Python 3.9+ or document conversion engine missing.")

    if not info["ready_full"]:
        lines.append("\nOffline & Fallback Workflow Notes:")
        lines.append("1. Markdown Manuals: Run 'python3 scripts/build_manual.py --format md ...' (no pip needed).")
        lines.append("2. Word Documents: Fallback to LibreOffice is automatic if python-docx is not installed.")
        lines.append("3. Screenshots: Place images directly in 'docs/manual_book/assets/raw/' or use Browser MCP tools.")
        if pip_data["available"]:
            lines.append("4. Full Suite Installation (if internet is available):")
            lines.append("   python3 -m venv .venv-manual")
            lines.append("   .venv-manual/bin/pip install Pillow python-docx playwright pypdf")
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
        help="Strict mode: require all optional packages (Pillow, python-docx, playwright) to pass.",
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

