---
name: license-audit
description: Audits a project's third-party licenses for compliance. Inventories dependencies, packages, fonts, icons, images, vendored code and CDN assets from manifests, lockfiles and source files, checks license compatibility against the project's own license and how it is distributed, and recommends fixes. Use whenever the user asks for a license audit, license compliance check, open source compliance review, third-party license inventory, "can we ship or sell this", "is this dependency safe to use", GPL/AGPL/copyleft risk, attribution or NOTICE requirements, or wants fonts and icons checked for licensing, even if they never say "audit". Do not use for security vulnerability scanning (SAST/DAST), code quality audits, or commercial SaaS API terms of service negotiation. Does not give legal advice.
license: MIT
compatibility: Works offline. Python 3.8+ stdlib for bundled scripts (zero pip dependencies required). Web access, when available, is used only to verify licenses that cannot be confirmed from local files.
metadata:
  version: "0.2.0"
---

# License Audit

Audit the third-party licenses used by a codebase, decide whether they fit how the project is used and distributed, and say what to fix. The output is a structured report (`LICENSE-AUDIT.md`) with three parts: an inventory, a compatibility assessment, and remediation recommendations.

This skill produces engineering and technical findings, not formal legal conclusions. State this clearly in the final deliverable. Ambiguous, high-risk, or contentious cases should be flagged for qualified legal counsel.

## Principles

1. **Evidence over memory.** A license claim is only as good as its source. Never state a license from recollection without labeling it `Unverified`.
2. **Audit what is actually used.** Use the locked version of each dependency from lockfiles, not the loose manifest range. Licenses change between versions.
3. **Report uncertainty, do not hide it.** `Unknown` is a valid finding. A guess presented as a verified fact is the worst outcome of an audit.
4. **Read-only by default.** Do not edit `LICENSE`, `NOTICE`, manifests, or lockfiles unless the user explicitly asks. Propose changes instead.

## Workflow

Copy and track progress using this checklist:

```markdown
- [ ] Step 0: Establish context and distribution model
- [ ] Step 1: Scan repository manifests, lockfiles, and assets (`scripts/scan_licenses.py`)
- [ ] Step 2: Determine licenses, confidence ratings, and normalize SPDX
- [ ] Step 3: Assess compatibility against project distribution model
- [ ] Step 4: Check obligations and attribution status
- [ ] Step 5: Draft remediation recommendations and generate report (`assets/report-template.md`)
- [ ] Step 6: Verify report structure and schema gate (`scripts/validate_report.py`)
```

### Step 0: Establish context

The same dependency can be completely permissible in an internal tool and a critical blocker in a distributed binary, so the audit verdict depends strictly on context. First infer what you can from repository artifacts (`LICENSE`, `package.json`/`pyproject.toml` license fields, README, Dockerfile, app-store configs). Then ask the user, in a single batch, only for what you could not reliably infer:

- **Project license**: What license is the project under, or is it proprietary/closed source?
- **Distribution model**: Internal use only, hosted service (SaaS/network service), distributed binary (desktop/mobile app, container image), or published library?
- **Commercial use**: Is the application sold, monetized, or used for commercial operations?
- **Audit scope**: Entire repository, or specific directories/workspaces? Are dev/build/test tools in scope?

*Fallback*: If the user cannot answer or the session is non-interactive, proceed with the most conservative assumption (closed-source, commercial, distributed to end users). List these assumptions clearly at the top of the report.

### Step 1: Discover components and scan assets

> [!TIP]
> Read `references/ecosystems-matrix.md` before analyzing multi-ecosystem repositories, lockfiles, PEP 639 metadata, or embedded digital assets.

Run the bundled scanner from the repository root to deterministically inventory manifests, lockfiles, and non-package digital assets:

```bash
python3 skills/license-audit/scripts/scan_licenses.py . --format json
```

The script extracts declared components across npm, Python, PHP, Rust, Go, and identifies digital media (fonts, icons, license texts).

**Key discovery areas:**
1. **Package Managers & Lockfiles**: Always prefer locked versions (`package-lock.json`, `poetry.lock`, `composer.lock`, `Cargo.lock`). Manifests without lockfiles indicate unresolved transitive dependencies; note this explicitly.
2. **Python Metadata**: Check PEP 639 `License-Expression` headers, Trove Classifiers (`Classifier: License :: ...`), and `*.dist-info/METADATA` as outlined in `references/ecosystems-matrix.md`.
3. **Non-Package Digital Assets**:
   - **Fonts**: `.woff`, `.woff2`, `.ttf`, `.otf`, `@font-face` definitions in CSS.
   - **Icons**: Icon packages (FontAwesome, Lucide), SVG sprites, raw graphics.
   - **CDN Includes & URL Imports**: `<script src="https://...">`, ESM URL imports (`esm.sh`).
   - **Inlined Assets**: Search for base64 data URIs (`data:font/`, `data:image/`, `base64,`).
   - **Vendored Code**: Committed `vendor/`, `third_party/`, or source files with license headers (`/* SPDX-License-Identifier: ... */`).

Record for each component: name, version, ecosystem/type, location, and scope (`runtime`, `dev`, or `bundled`).

### Step 2: Determine licenses and confidence ratings

> [!TIP]
> Read `references/spdx-classifications.md` for standard SPDX 2.3 identifiers, compound expressions (`AND`, `OR`, `WITH`), and exception parsing.

Evaluate license evidence using the strongest available source:
1. **License text file** shipped with the installed package or vendored asset.
2. **Structured metadata** for that exact version (`package.json`, `.dist-info/METADATA`, `composer.lock`).
3. **Upstream registry / repository** metadata (when permitted by network access).
4. **General knowledge** (weakest source; must always be labeled `Unverified`).

Assign an explicit **Confidence Rating** to every component:
- **`Verified`**: License confirmed by directly inspecting included license text or authoritative checksummed manifest.
- **`Declared`**: Stated in manifest/lockfile metadata, but accompanying license text was not inspected.
- **`Unverified`**: Inferred from external recollection or directory names. Requires explicit verification before clearing.
- **`Unknown`**: Missing license text, `UNLICENSED`, or unparseable. Treat as blocker until clarified.

Normalize all license names to canonical **SPDX identifiers** (`MIT`, `Apache-2.0`, `GPL-3.0-only`, `LGPL-2.1-or-later`). Parse compound expressions:
- `A OR B`: Licensee may choose either; record assumed selection.
- `A AND B`: Both apply simultaneously; both sets of obligations must be met.
- `WITH <exception>`: Modifies the base license (e.g. `Classpath-exception-2.0`); treat as an atomic unit.

### Step 3: Assess compatibility

Evaluate each component's license category against the project's distribution scenario established in Step 0:

| Category | Hosted SaaS | Distributed Binary (Closed Source) | Distributed Open Source |
|---|:---:|:---:|:---:|
| **Permissive** (`MIT`, `Apache-2.0`, `BSD-3-Clause`) | ✅ OK | ✅ OK (retain notices) | ✅ OK (retain notices) |
| **Weak Copyleft** (`LGPL-3.0-only`, `MPL-2.0`) | ✅ OK (unmodified) | ⚠️ Review linking (dynamic vs static) | ✅ Usually OK |
| **Strong Copyleft** (`GPL-2.0-only`, `GPL-3.0-only`) | ✅ OK (no distribution) | ⛔ **Blocker** (forces source disclosure) | ⚠️ Check compatibility |
| **Network Copyleft** (`AGPL-3.0-only`, `SSPL-1.0`) | ⛔ **High Risk** | ⛔ **Blocker** | ⚠️ Check compatibility |
| **Source-Available** (`BUSL-1.1`, `Elastic-2.0`) | ⛔ Often Blocker | ⚠️ Review terms | ⚠️ Review terms |
| **Unknown / None** | ⛔ **Blocker** | ⛔ **Blocker** | ⛔ **Blocker** |

*Key compatibility checks (detailed in `references/spdx-classifications.md`):*
- `GPL-2.0-only` is legally incompatible with `Apache-2.0` in a combined work.
- Static linking of LGPL libraries in iOS apps or closed-source binaries triggers object-code relinking obligations.
- AGPL copyleft triggers on network interaction even without client binary distribution.

### Step 4: Check obligations and attribution

For every permissible dependency, catalog obligations and verify whether the repository already fulfills them:
- **Copyright notices & license text**: Required for all permissive licenses (`MIT`, `BSD`). Check if a `THIRD_PARTY_NOTICES.md` or in-app "About/Licenses" screen exists.
- **`NOTICE` files**: Apache-2.0 section 4(d) requires preserving text from upstream `NOTICE` files.
- **Source code disclosure / offer**: Required for distributed copyleft components.
- **State modification notices**: Required when modifying Apache-2.0 or LGPL files.

### Step 5: Draft remediation recommendations and generate report

Rank findings by severity:
- **`Blocker`**: Cannot ship as planned without severe IP/legal exposure.
- **`High`**: Probable non-compliance or field-of-use restriction.
- **`Medium`**: Missing mandatory attribution or notices.
- **`Low`**: Minor dev/test tool questions.
- **`Info`**: Clean license observations.

Provide concrete remediation steps for each finding (in preferred order: Clarify, Document, Change version, Replace, Isolate as microservice, or Acquire commercial license).

Generate the report adhering strictly to the schema in `assets/report-template.md`, saving it to `LICENSE-AUDIT.md`.

### Step 6: Verify report structure (Verification Gate)

Run the deterministic validation script to verify that the report satisfies schema requirements, contains valid SPDX confidence ratings, and has no missing sections:

```bash
python3 skills/license-audit/scripts/validate_report.py LICENSE-AUDIT.md
```

- If validation passes (`[OK] Report successfully passed validation`), conclude the audit and present the summary to the user.
- If validation fails, correct the missing sections or invalid values before final handover.

## Gotchas

- **Manifest `license` fields can be wrong or stale.** When possible, inspect the actual license text in `node_modules` or crate caches; report discrepancies.
- **Lockfiles are the source of truth.** Manifest ranges (`^1.2.0`) do not tell you what exact version was resolved and installed.
- **Dual licenses with CC-BY.** Icon and font packages often license wrapper code under MIT but graphics under Creative Commons (`CC-BY-4.0` or `CC-BY-SA`). Verify the asset license, not just the package wrapper.
- **Unpinned container installs.** `apt-get install` or `pip install` in a Dockerfile resolves to latest upstream at build time. Flag as unpinned and subject to license drift.
