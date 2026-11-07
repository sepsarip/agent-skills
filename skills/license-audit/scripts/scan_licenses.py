#!/usr/bin/env python3
"""scan_licenses.py - Scans codebase for package manifests, lockfiles, and digital assets.

Extracts declared dependency versions, licenses, and asset paths using Python 3
standard library only (zero pip dependencies).
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

def is_ignored_dir(dirname: str) -> bool:
    """Determine if a directory should be skipped during source tree walk."""
    if dirname in IGNORED_DIRS:
        return True
    if dirname.startswith(".venv") or dirname.startswith("venv"):
        return True
    return False
IGNORED_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".tox",
    "target",
    "dist",
    "build",
    ".idea",
    ".vscode",
    "vendor",  # scanned separately for license texts
}

FONT_EXTENSIONS = {".woff", ".woff2", ".ttf", ".otf", ".eot"}
LICENSE_FILE_PATTERN = re.compile(
    r"^(LICENSE|COPYING|NOTICE|THIRD_PARTY_NOTICES?|PATENTS?)([-._].*)?$",
    re.IGNORECASE,
)


def parse_package_json(filepath: Path) -> dict:
    """Extract top-level package metadata and declared dependency ranges."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"error": str(e)}

    license_val = data.get("license")
    if isinstance(license_val, dict):
        license_str = license_val.get("type", "Unknown")
    elif isinstance(license_val, str):
        license_str = license_val
    else:
        license_str = "Unknown"

    components = []
    deps = data.get("dependencies", {})
    dev_deps = data.get("devDependencies", {})

    if isinstance(deps, dict):
        for name, ver in deps.items():
            components.append({
                "name": name,
                "version_spec": str(ver),
                "scope": "runtime",
                "ecosystem": "npm",
                "license": "Unverified",
                "confidence": "Unverified",
                "evidence": str(filepath),
            })

    if isinstance(dev_deps, dict):
        for name, ver in dev_deps.items():
            components.append({
                "name": name,
                "version_spec": str(ver),
                "scope": "dev",
                "ecosystem": "npm",
                "license": "Unverified",
                "confidence": "Unverified",
                "evidence": str(filepath),
            })

    return {
        "project_name": data.get("name"),
        "project_license": license_str,
        "components": components,
    }


def parse_package_lock(filepath: Path) -> list:
    """Extract locked dependencies and licenses from package-lock.json v1/v2/v3."""
    components = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return [{"error": str(e), "evidence": str(filepath)}]

    # v2 and v3 package-lock have a 'packages' object
    packages = data.get("packages")
    if isinstance(packages, dict):
        for path_key, meta in packages.items():
            if not path_key or not isinstance(meta, dict):
                continue
            # path_key is typically "node_modules/foo" or "" (root)
            name = meta.get("name")
            if not name:
                parts = path_key.replace("\\", "/").split("node_modules/")
                if len(parts) > 1:
                    name = parts[-1]
                else:
                    continue

            version = meta.get("version", "unknown")
            is_dev = meta.get("dev", False)
            scope = "dev" if is_dev else "runtime"
            lic = meta.get("license")
            if isinstance(lic, str) and lic.strip():
                license_val = lic.strip()
                confidence = "Declared"
            else:
                license_val = "Unknown"
                confidence = "Unknown"

            components.append({
                "name": name,
                "version": version,
                "scope": scope,
                "ecosystem": "npm",
                "license": license_val,
                "confidence": confidence,
                "evidence": f"{filepath} ({path_key})",
            })
        return components

    # v1 fallback
    dependencies = data.get("dependencies")
    if isinstance(dependencies, dict):
        for name, meta in dependencies.items():
            if not isinstance(meta, dict):
                continue
            version = meta.get("version", "unknown")
            is_dev = meta.get("dev", False)
            scope = "dev" if is_dev else "runtime"
            components.append({
                "name": name,
                "version": version,
                "scope": scope,
                "ecosystem": "npm",
                "license": "Unknown",
                "confidence": "Unknown",
                "evidence": str(filepath),
            })
    return components


def parse_pyproject_toml(filepath: Path) -> dict:
    """Extract PEP 639 license expressions, Trove classifiers, and dependencies from pyproject.toml."""
    components = []
    project_license = "Unknown"
    project_name = None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return {"error": str(e)}

    # Check project name
    name_m = re.search(r'^\s*name\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    if name_m:
        project_name = name_m.group(1)

    # Check PEP 639 / standard license fields
    # 1. license-expression = "MIT OR Apache-2.0"
    exp_m = re.search(r'^\s*license-expression\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    if exp_m:
        project_license = exp_m.group(1)
    else:
        # 2. license = "MIT" or license = { text = "MIT" }
        lic_str_m = re.search(r'^\s*license\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
        if lic_str_m:
            project_license = lic_str_m.group(1)
        else:
            lic_dict_m = re.search(r'^\s*license\s*=\s*\{[^}]*text\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
            if lic_dict_m:
                project_license = lic_dict_m.group(1)

    # Check Trove classifiers for license
    classifiers = re.findall(r'["\']Classifier\s*::\s*License\s*::[^"\']*::\s*([^"\']+)["\']', content, re.IGNORECASE)
    if not classifiers:
        classifiers = re.findall(r'["\']License\s*::\s*([^"\']+)["\']', content, re.IGNORECASE)

    # Extract [project.dependencies]
    deps_match = re.search(r'\[project\.dependencies\](.*?)(?=\n\[|\Z)', content, re.DOTALL)
    if not deps_match:
        # Check poetry dependencies [tool.poetry.dependencies]
        deps_match = re.search(r'\[tool\.poetry\.dependencies\](.*?)(?=\n\[|\Z)', content, re.DOTALL)

    if deps_match:
        for line in deps_match.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Format: 'pkg = ">=1.0"' or '"pkg>=1.0"'
            pkg_m = re.match(r'^([a-zA-Z0-9_\-]+)\s*=', line)
            if pkg_m:
                pkg_name = pkg_m.group(1)
                if pkg_name.lower() != "python":
                    components.append({
                        "name": pkg_name,
                        "version_spec": line,
                        "scope": "runtime",
                        "ecosystem": "python",
                        "license": "Unverified",
                        "confidence": "Unverified",
                        "evidence": str(filepath),
                    })
            else:
                str_pkg_m = re.match(r'^["\']([a-zA-Z0-9_\-]+)', line)
                if str_pkg_m:
                    components.append({
                        "name": str_pkg_m.group(1),
                        "version_spec": line,
                        "scope": "runtime",
                        "ecosystem": "python",
                        "license": "Unverified",
                        "confidence": "Unverified",
                        "evidence": str(filepath),
                    })

    return {
        "project_name": project_name,
        "project_license": project_license,
        "classifiers": classifiers,
        "components": components,
    }


def parse_poetry_lock(filepath: Path) -> list:
    """Extract locked package names and versions from poetry.lock."""
    components = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return [{"error": str(e), "evidence": str(filepath)}]

    package_blocks = re.split(r'\[\[package\]\]', content)
    for block in package_blocks[1:]:
        name_m = re.search(r'^\s*name\s*=\s*["\']([^"\']+)["\']', block, re.MULTILINE)
        ver_m = re.search(r'^\s*version\s*=\s*["\']([^"\']+)["\']', block, re.MULTILINE)
        cat_m = re.search(r'^\s*category\s*=\s*["\']([^"\']+)["\']', block, re.MULTILINE)
        if name_m and ver_m:
            scope = "dev" if cat_m and cat_m.group(1) == "dev" else "runtime"
            components.append({
                "name": name_m.group(1),
                "version": ver_m.group(1),
                "scope": scope,
                "ecosystem": "python",
                "license": "Unknown",
                "confidence": "Unknown",
                "evidence": str(filepath),
            })
    return components


def parse_composer_lock(filepath: Path) -> list:
    """Extract locked PHP packages and declared licenses from composer.lock."""
    components = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return [{"error": str(e), "evidence": str(filepath)}]

    def process_pkg_list(pkg_list, scope_name):
        if not isinstance(pkg_list, list):
            return
        for pkg in pkg_list:
            if not isinstance(pkg, dict):
                continue
            name = pkg.get("name", "unknown")
            version = pkg.get("version", "unknown")
            licenses = pkg.get("license", [])
            if isinstance(licenses, list) and licenses:
                lic_str = " OR ".join(licenses)
                conf = "Declared"
            elif isinstance(licenses, str) and licenses.strip():
                lic_str = licenses.strip()
                conf = "Declared"
            else:
                lic_str = "Unknown"
                conf = "Unknown"

            components.append({
                "name": name,
                "version": version,
                "scope": scope_name,
                "ecosystem": "composer",
                "license": lic_str,
                "confidence": conf,
                "evidence": str(filepath),
            })

    process_pkg_list(data.get("packages", []), "runtime")
    process_pkg_list(data.get("packages-dev", []), "dev")
    return components


def parse_cargo_lock(filepath: Path) -> list:
    """Extract locked Rust crates from Cargo.lock."""
    components = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return [{"error": str(e), "evidence": str(filepath)}]

    package_blocks = re.split(r'\[\[package\]\]', content)
    for block in package_blocks[1:]:
        name_m = re.search(r'^\s*name\s*=\s*["\']([^"\']+)["\']', block, re.MULTILINE)
        ver_m = re.search(r'^\s*version\s*=\s*["\']([^"\']+)["\']', block, re.MULTILINE)
        if name_m and ver_m:
            components.append({
                "name": name_m.group(1),
                "version": ver_m.group(1),
                "scope": "runtime",
                "ecosystem": "cargo",
                "license": "Unknown",
                "confidence": "Unknown",
                "evidence": str(filepath),
            })
    return components


def scan_workspace(root_path: Path, include_dev: bool = True) -> dict:
    """Scans workspace directory for all manifests, lockfiles, and non-package assets."""
    manifests_found = []
    components = []
    assets = []
    license_files = []

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Filter directories in-place to avoid deep traversal into ignored folders
        dirnames[:] = [d for d in dirnames if not is_ignored_dir(d)]
        curr_dir = Path(dirpath)

        for fname in filenames:
            fpath = curr_dir / fname
            rel_path = str(fpath.relative_to(root_path))
            ext = fpath.suffix.lower()

            # Check for license files
            if LICENSE_FILE_PATTERN.match(fname):
                license_files.append({
                    "path": rel_path,
                    "filename": fname,
                })

            # Check for font files
            if ext in FONT_EXTENSIONS:
                assets.append({
                    "type": "font",
                    "path": rel_path,
                    "format": ext.lstrip("."),
                    "license": "Unknown",
                    "confidence": "Unknown",
                })

            # Check for manifests and lockfiles
            if fname == "package-lock.json":
                manifests_found.append(rel_path)
                components.extend(parse_package_lock(fpath))
            elif fname == "package.json":
                manifests_found.append(rel_path)
                res = parse_package_json(fpath)
                # If package-lock does not exist, include dependencies from package.json
                lock_sibling = fpath.parent / "package-lock.json"
                if not lock_sibling.exists():
                    components.extend(res.get("components", []))
            elif fname == "composer.lock":
                manifests_found.append(rel_path)
                components.extend(parse_composer_lock(fpath))
            elif fname == "pyproject.toml":
                manifests_found.append(rel_path)
                res = parse_pyproject_toml(fpath)
                lock_sibling = fpath.parent / "poetry.lock"
                if not lock_sibling.exists():
                    components.extend(res.get("components", []))
            elif fname == "poetry.lock":
                manifests_found.append(rel_path)
                components.extend(parse_poetry_lock(fpath))
            elif fname == "Cargo.lock":
                manifests_found.append(rel_path)
                components.extend(parse_cargo_lock(fpath))
            elif fname == "go.mod":
                manifests_found.append(rel_path)

    # Filter out dev dependencies if not requested
    if not include_dev:
        components = [c for c in components if c.get("scope") != "dev"]

    # Deduplicate components by name + version + ecosystem
    seen = set()
    deduped_components = []
    for c in components:
        key = (c.get("name"), c.get("version", c.get("version_spec")), c.get("ecosystem"))
        if key not in seen:
            seen.add(key)
            deduped_components.append(c)

    return {
        "root": str(root_path.resolve()),
        "manifests_detected": manifests_found,
        "license_files": license_files,
        "component_count": len(deduped_components),
        "components": deduped_components,
        "assets_count": len(assets),
        "assets": assets,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Scan workspace for package manifests, lockfiles, licenses, and digital assets."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Root path to scan (defaults to current directory).",
    )
    parser.add_argument(
        "--format",
        choices=["json", "summary"],
        default="json",
        help="Output format: structured json (default) or human-readable summary.",
    )
    parser.add_argument(
        "--include-dev",
        action="store_true",
        default=True,
        help="Include development/build-time dependencies (default: True).",
    )
    parser.add_argument(
        "--no-dev",
        dest="include_dev",
        action="store_false",
        help="Exclude development dependencies.",
    )

    args = parser.parse_args()
    target_path = Path(args.path)

    if not target_path.exists():
        print(f"Error: Target path does not exist: {target_path}", file=sys.stderr)
        sys.exit(1)

    results = scan_workspace(target_path, include_dev=args.include_dev)

    if args.format == "json":
        print(json.dumps(results, indent=2))
    else:
        print(f"License Scan Results for: {results['root']}")
        print(f"- Manifests detected ({len(results['manifests_detected'])}): {', '.join(results['manifests_detected']) or 'None'}")
        print(f"- License files found ({len(results['license_files'])}): {', '.join(f['path'] for f in results['license_files']) or 'None'}")
        print(f"- Components discovered: {results['component_count']}")
        print(f"- Digital assets (fonts, icons): {results['assets_count']}")


if __name__ == "__main__":
    main()
