#!/usr/bin/env python3
"""test_license_audit.py - Unit tests for license-audit scripts.

Tests scan_licenses.py and validate_report.py using Python unittest standard library.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import scan_licenses
import validate_report


class TestScanLicenses(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_parse_package_json(self):
        pkg_file = self.test_path / "package.json"
        pkg_file.write_text(
            json.dumps({
                "name": "sample-app",
                "license": "MIT",
                "dependencies": {"express": "^4.19.0"},
                "devDependencies": {"jest": "^29.0.0"},
            }),
            encoding="utf-8",
        )
        res = scan_licenses.parse_package_json(pkg_file)
        self.assertEqual(res["project_name"], "sample-app")
        self.assertEqual(res["project_license"], "MIT")
        self.assertEqual(len(res["components"]), 2)
        scopes = {c["name"]: c["scope"] for c in res["components"]}
        self.assertEqual(scopes["express"], "runtime")
        self.assertEqual(scopes["jest"], "dev")

    def test_parse_package_lock_v2(self):
        lock_file = self.test_path / "package-lock.json"
        lock_file.write_text(
            json.dumps({
                "name": "sample-app",
                "lockfileVersion": 3,
                "packages": {
                    "": {"name": "sample-app", "license": "MIT"},
                    "node_modules/lodash": {
                        "version": "4.17.21",
                        "license": "MIT",
                        "dev": False,
                    },
                    "node_modules/mocha": {
                        "version": "10.2.0",
                        "license": "Apache-2.0",
                        "dev": True,
                    },
                },
            }),
            encoding="utf-8",
        )
        comps = scan_licenses.parse_package_lock(lock_file)
        self.assertEqual(len(comps), 2)
        names = {c["name"]: c for c in comps}
        self.assertIn("lodash", names)
        self.assertEqual(names["lodash"]["license"], "MIT")
        self.assertEqual(names["lodash"]["confidence"], "Declared")
        self.assertEqual(names["lodash"]["scope"], "runtime")
        self.assertEqual(names["mocha"]["scope"], "dev")

    def test_parse_pyproject_pep639(self):
        pyproject = self.test_path / "pyproject.toml"
        pyproject.write_text(
            """
[project]
name = "my-library"
license-expression = "MIT OR Apache-2.0"
classifiers = [
    "Classifier :: License :: OSI Approved :: MIT License",
    "Classifier :: License :: OSI Approved :: Apache Software License",
]

[project.dependencies]
requests = ">=2.28.0"
click = "^8.1.0"
""",
            encoding="utf-8",
        )
        res = scan_licenses.parse_pyproject_toml(pyproject)
        self.assertEqual(res["project_name"], "my-library")
        self.assertEqual(res["project_license"], "MIT OR Apache-2.0")
        self.assertEqual(len(res["components"]), 2)
        comp_names = [c["name"] for c in res["components"]]
        self.assertIn("requests", comp_names)
        self.assertIn("click", comp_names)

    def test_parse_composer_lock(self):
        composer_file = self.test_path / "composer.lock"
        composer_file.write_text(
            json.dumps({
                "packages": [
                    {
                        "name": "monolog/monolog",
                        "version": "3.5.0",
                        "license": ["MIT"],
                    }
                ],
                "packages-dev": [
                    {
                        "name": "phpunit/phpunit",
                        "version": "10.5.0",
                        "license": ["BSD-3-Clause"],
                    }
                ],
            }),
            encoding="utf-8",
        )
        comps = scan_licenses.parse_composer_lock(composer_file)
        self.assertEqual(len(comps), 2)
        names = {c["name"]: c for c in comps}
        self.assertEqual(names["monolog/monolog"]["license"], "MIT")
        self.assertEqual(names["monolog/monolog"]["scope"], "runtime")
        self.assertEqual(names["phpunit/phpunit"]["license"], "BSD-3-Clause")
        self.assertEqual(names["phpunit/phpunit"]["scope"], "dev")

    def test_scan_workspace_assets_and_licenses(self):
        # Create a mock font file
        fonts_dir = self.test_path / "public" / "fonts"
        fonts_dir.mkdir(parents=True)
        (fonts_dir / "inter.woff2").write_bytes(b"\x00\x01\x00\x00")

        # Create a mock root license file
        (self.test_path / "LICENSE").write_text("MIT License...", encoding="utf-8")

        res = scan_licenses.scan_workspace(self.test_path)
        self.assertEqual(res["assets_count"], 1)
        self.assertEqual(res["assets"][0]["format"], "woff2")
        self.assertEqual(len(res["license_files"]), 1)
        self.assertEqual(res["license_files"][0]["filename"], "LICENSE")


class TestValidateReport(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_path = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_validate_valid_report(self):
        report_file = self.test_path / "LICENSE-AUDIT.md"
        report_file.write_text(
            """# License Audit Report

## Summary
Ready to ship. 0 blockers.

## Context and assumptions
Closed source SaaS.

## Coverage
Inspected npm lockfile.

## Inventory
| Component | Version | Type | Scope | License (SPDX) | Confidence | Evidence |
|---|---|---|---|---|---|---|
| express | 4.19.2 | npm | runtime | MIT | Verified | package-lock.json |

## Findings
| # | Severity | Component | Issue | Why It Matters in This Context |
|---|---|---|---|---|
| 1 | Low | express | None | Permissive |

## Obligations
Retain MIT notice.

## Recommendations
No action needed.

## Unverified and limitations
None. Not legal advice.
""",
            encoding="utf-8",
        )
        is_valid, errors, warnings = validate_report.validate_report(report_file)
        self.assertTrue(is_valid, f"Errors: {errors}")
        self.assertEqual(len(errors), 0)

    def test_validate_missing_section(self):
        report_file = self.test_path / "LICENSE-AUDIT.md"
        report_file.write_text(
            """# License Audit Report

## Summary
Ready to ship.

## Inventory
| Component | Version | Type | Scope | License (SPDX) | Confidence | Evidence |
|---|---|---|---|---|---|---|
| express | 4.19.2 | npm | runtime | MIT | Verified | package-lock.json |
""",
            encoding="utf-8",
        )
        is_valid, errors, warnings = validate_report.validate_report(report_file)
        self.assertFalse(is_valid)
        self.assertTrue(any("Findings" in e for e in errors))

    def test_validate_invalid_confidence(self):
        report_file = self.test_path / "LICENSE-AUDIT.md"
        report_file.write_text(
            """# License Audit Report

## Summary
Check confidence.

## Context and assumptions
Internal.

## Coverage
npm.

## Inventory
| Component | Version | Type | Scope | License (SPDX) | Confidence | Evidence |
|---|---|---|---|---|---|---|
| my-pkg | 1.0.0 | npm | runtime | MIT | Guessed | package.json |

## Findings
| # | Severity | Component | Issue | Why It Matters in This Context |
|---|---|---|---|---|
| 1 | Low | my-pkg | None | None |

## Obligations
None.

## Recommendations
None.

## Unverified and limitations
None.
""",
            encoding="utf-8",
        )
        is_valid, errors, warnings = validate_report.validate_report(report_file)
        self.assertFalse(is_valid)
        self.assertTrue(any("Invalid confidence" in e for e in errors))

    def test_validate_invalid_severity(self):
        report_file = self.test_path / "LICENSE-AUDIT.md"
        report_file.write_text(
            """# License Audit Report

## Summary
Check severity.

## Context and assumptions
Internal.

## Coverage
npm.

## Inventory
| Component | Version | Type | Scope | License (SPDX) | Confidence | Evidence |
|---|---|---|---|---|---|---|
| my-pkg | 1.0.0 | npm | runtime | MIT | Verified | package.json |

## Findings
| # | Severity | Component | Issue | Why It Matters in This Context |
|---|---|---|---|---|
| 1 | Catastrophic | my-pkg | Critical error | Urgent |

## Obligations
None.

## Recommendations
None.

## Unverified and limitations
None.
""",
            encoding="utf-8",
        )
        is_valid, errors, warnings = validate_report.validate_report(report_file)
        self.assertFalse(is_valid)
        self.assertTrue(any("Invalid severity" in e for e in errors))


if __name__ == "__main__":
    unittest.main()

