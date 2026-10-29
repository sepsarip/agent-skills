---
name: license-audit
description: Audits a project's third-party licenses for compliance. Inventories dependencies, packages, fonts, icons, images, vendored code and CDN assets from manifests, lockfiles and source files, checks license compatibility against the project's own license and how it is distributed, and recommends fixes. Use whenever the user asks for a license audit, license compliance check, open source compliance review, third-party license inventory, "can we ship or sell this", "is this dependency safe to use", GPL/AGPL/copyleft risk, attribution or NOTICE requirements, or wants fonts and icons checked for licensing, even if they never say "audit". Does not give legal advice.
compatibility: Works offline. web access, when available, is used only to verify licenses that cannot be confirmed from local files.
metadata:
  version: "0.1.0"
---

# License Audit

Audit the third-party licenses used by a codebase, decide whether they fit how the project is used and distributed, and say what to fix. The output is a report with three parts: an inventory, a compatibility assessment, and remediation recommendations.

This skill produces engineering findings, not legal conclusions. Say so in the report. Ambiguous or high-stakes cases go to a lawyer.

## Principles

1. **Evidence over memory.** A license claim is only as good as its source. Never state a license from recollection without labeling it `Unverified`.
2. **Audit what is actually used.** Use the locked version of each dependency, not the latest one. Licenses change between versions.
3. **Report uncertainty, do not hide it.** Unknown is a valid finding. A guess presented as a fact is the worst outcome of an audit.
4. **Read-only by default.** Do not edit `LICENSE`, `NOTICE`, manifests, or lockfiles unless the user asks. Propose changes instead.

## Workflow

### Step 0: Establish context

The same dependency can be fine in one setup and a blocker in another, so the verdict depends on context. First infer what you can from the repo (`LICENSE`, `package.json`/`composer.json` license field, README, Dockerfile, app-store configs). Then ask the user, in one batch, only for what you could not infer:

- **Project license**: what license is the project under, or is it proprietary/closed source?
- **Distribution model**: internal use only, hosted service (SaaS/network), distributed to users (desktop/mobile app, binary, container image), or published as a library?
- **Commercial use**: is it, or will it be, sold or used commercially?
- **Scope**: whole repo, or specific folders/workspaces? Are dev/test/build tools in scope?

If the user cannot answer or the session is non-interactive, proceed with the most conservative assumption (closed-source, commercial, distributed to end users). List the assumptions at the top of the report so they can be corrected.

### Step 1: Discover components

Build the component list from files, not from assumptions. Cover every ecosystem present; monorepos often have several.

**Package managers.** Prefer lockfiles, because they pin exact versions and include transitive dependencies. If only a manifest exists, say that versions and transitive dependencies are unresolved.

| Ecosystem | Manifest / lockfile | Where license evidence usually lives |
|---|---|---|
| npm / yarn / pnpm | `package.json`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml` | `node_modules/<pkg>/package.json` and `LICENSE*`; some lockfiles carry a `license` field, many do not |
| Composer (PHP) | `composer.json`, `composer.lock` | `license` per package in `composer.lock`; `vendor/<pkg>/LICENSE*` |
| Python | `requirements*.txt`, `pyproject.toml`, `Pipfile.lock`, `poetry.lock`, `uv.lock` | `*.dist-info/METADATA` and license files in site-packages; lockfiles usually lack license data |
| Go | `go.mod`, `go.sum` | `LICENSE` in `vendor/` or the module cache; `go.sum` holds only hashes |
| Rust | `Cargo.toml`, `Cargo.lock` | each crate's own `Cargo.toml` (`license` field) and license files; `Cargo.lock` has no license data |
| Ruby | `Gemfile`, `Gemfile.lock` | installed gem's gemspec and license files |
| JVM / Android (Kotlin, Java) | `pom.xml`, `build.gradle(.kts)`, `gradle/libs.versions.toml`, `gradle.lockfile` | the artifact's `.pom` (`<licenses>`) in the Maven/Gradle cache; license files inside the jar/aar |
| .NET | `*.csproj`, `packages.config`, `packages.lock.json` | `.nuspec` license metadata in the NuGet cache |
| Dart / Flutter | `pubspec.yaml`, `pubspec.lock` | `LICENSE` in the pub cache |
| iOS | `Package.resolved`, `Podfile.lock` | license files in the checkout or `Pods/` |
| Containers | `Dockerfile` (`FROM` and `RUN apt/apk/pip/npm install` lines), compose files | base image license, plus the OS and language packages installed in the image; installs are often unpinned, so say so |
| C / C++ | `vcpkg.json`, `conanfile.txt` / `conanfile.py`, CMake `FetchContent` / `ExternalProject`, `Makefile` | license files in the checkout or package cache |
| Elixir / Erlang | `mix.exs`, `mix.lock`, `rebar.config` | package metadata and license files in `deps/` |
| Infrastructure as code | Terraform `*.tf` (providers, modules), Helm `Chart.yaml`, Ansible `requirements.yml` | license of the provider, chart, or role repository; also the images a chart references |
| CI/CD | `.github/workflows/*.yml` (`uses:` entries), other CI configs, install steps in build scripts | license of each action's repository; tools installed in build steps (usually dev/build scope) |
| Git submodules | `.gitmodules` | `LICENSE` in the submodule checkout (empty if the submodule is not initialized) |

**Dependencies that bypass the registry.** Manifest entries that point to a git URL, a tarball URL, or a local path (for example `git+https://...`, `github:user/repo`, `file:`, a Composer `repositories` entry of type `vcs` or `path`) carry no registry license metadata. Read the license from the source repository or checkout, and record the exact commit or tag.

**Non-package assets.** These are the ones audits usually miss, because they have no manifest. Search the source tree for:

- **Fonts**: `@font-face`, `fonts.googleapis.com`, `.woff`, `.woff2`, `.ttf`, `.otf`, `.eot`, a `fonts/` directory, font packages in manifests.
- **Icons**: icon libraries in manifests (Font Awesome, Material Icons, Lucide, Heroicons, Feather, Bootstrap Icons, Tabler, Phosphor and similar), `icons/` directories, SVG sprites, app launcher icons.
- **Images, illustrations, audio, video**: `public/`, `static/`, `assets/`, `res/`, `Assets.xcassets`. Look for attribution files or credits.
- **CDN includes**: `<script src="https://...">`, `<link href="https://...">`, `cdn.jsdelivr`, `cdnjs`, `unpkg`.
- **URL imports**: `import ... from "https://..."` (for example `esm.sh`, `skypack`), dynamic `import()` of URLs, import maps, Deno URL imports.
- **Embedded assets**: fonts, images, and SVGs inlined as base64 `data:` URIs in CSS, HTML, or JS. They do not show up when searching by file name, so search for `data:font`, `data:image`, and `base64,`.
- **Purchased or downloaded templates and themes**: admin dashboards, UI kits, landing-page templates, WordPress themes and plugins. These often carry commercial licenses with limits (single project, no redistribution, no resale of the template itself). Look for a license file, receipt, or the marketplace's license type.
- **Vendored or copied code**: committed `vendor/`, `third_party/`, `lib/`, minified files with license banners (`/*! ... */`), files with `SPDX-License-Identifier` or `Copyright (c)` headers, code pasted from Stack Overflow or gists.
- **Models and datasets**: `.onnx`, `.pt`, `.safetensors`, `.tflite`, data files shipped with the app.
- **The project's own files**: `LICENSE`, `COPYING`, `NOTICE`, `THIRD_PARTY_NOTICES*`, `package.json` `license` field.

For each component record: name, version, ecosystem or type, where it was found, and whether it is a runtime, dev/build/test, or bundled-into-output dependency. Include transitive dependencies; direct ones alone understate the risk.

**Track coverage.** No search finds everything, so keep a running list of which locations and ecosystems above you checked, which you did not, and why (not present, no access, out of the user's scope). This list goes into the report. Silence about a location reads as "checked and clean", which is false if you never looked.

Out of scope for this skill: the terms of service of external APIs and SaaS products. If the project calls such services, mention them in the report as not covered.

### Step 2: Determine each component's license

Use the strongest evidence available, in this order:

1. The license text file shipped with the exact version in use (installed package directory, vendored folder, file next to the asset).
2. Structured metadata for that version (manifest `license` field, lockfile, `.pom`, `.nuspec`, `METADATA`).
3. Registry or upstream repository page for that version, if you have web access.
4. Your own knowledge. This is the weakest source and must be labeled.

Label every result with a confidence level:

- **Verified**: you read the license text or an exact-version authoritative record.
- **Declared**: only metadata says so; the text was not checked.
- **Unverified**: from memory or inference. Never use this level to clear a component; it can only be listed as "needs confirmation".

Then normalize:

- Convert to **SPDX identifiers** (`MIT`, `Apache-2.0`, `GPL-3.0-only`, `LGPL-2.1-or-later`). Keep `-only` and `-or-later` distinct; they behave differently.
- Parse SPDX expressions. `A OR B` is a choice: record which one you assume the project takes. `A AND B` means both apply. `WITH` adds an exception that changes the terms; read the exception.
- If the metadata and the license file disagree, report both and treat the file as authoritative.
- If there is no license, or `UNLICENSED`, or `SEE LICENSE IN ...` pointing at a file you cannot find: record it as **Unknown**. Absence of a license grants no permission to use the code.

Fonts, icons, and images need extra care. A package's code license often differs from its asset license (for example, an icon pack whose code is MIT but whose icons are under a Creative Commons license). Find the license for the assets themselves. If an asset has no documented source or license, record it as Unknown and recommend documenting its provenance; do not infer the license from the file name.

If you cannot verify something because you are offline or the files are not installed, say exactly that. "Could not verify: dependencies not installed and no network" is an acceptable finding.

### Step 3: Assess compatibility

Classify each component, then judge it against the Step 0 context.

| Category | Examples (SPDX) | What it generally means |
|---|---|---|
| Permissive | `MIT`, `BSD-2-Clause`, `BSD-3-Clause`, `ISC`, `Apache-2.0`, `Zlib`, `0BSD` | Keep notices and license text. `Apache-2.0` also has a NOTICE file and a patent clause. |
| Public-domain-like | `CC0-1.0`, `Unlicense` | Few or no obligations; confirm the dedication is genuine. |
| Weak copyleft | `LGPL-2.1-only`, `LGPL-3.0-only`, `MPL-2.0`, `EPL-2.0`, `CDDL-1.0` | Changes to the covered library or files must be shared; linking conditions apply (LGPL). |
| Strong copyleft | `GPL-2.0-only`, `GPL-3.0-only` | A combined work that is distributed generally must be offered under the GPL. |
| Network copyleft | `AGPL-3.0-only` | Like GPL, and also triggered by letting users interact with it over a network. |
| Source-available / restricted | `BUSL-1.1`, `SSPL-1.0`, `Elastic-2.0`, `PolyForm-*`, Commons Clause | Not open source. Field-of-use limits, often restricting commercial or hosted use. |
| Content licenses | `CC-BY-4.0`, `CC-BY-SA-4.0`, `CC-BY-NC-*`, `CC-BY-ND-*`, `OFL-1.1` | Attribution; `SA` is copyleft for adaptations; `NC` and `ND` restrict commercial use or modification. |
| Proprietary / commercial | EULAs, purchased font or icon licenses | Follow the terms: seats, domains, platforms, embedding rights. |
| Unknown | none, `UNLICENSED`, unparseable | No permission by default. Treat as a blocker until clarified. |

**Starting-point risk by context.** This table is a first pass, not a verdict. Mark anything marked "Review" for human or legal attention.

| Category | Internal use only | Hosted service (SaaS) | Distributed, closed source | Distributed, open source |
|---|---|---|---|---|
| Permissive | OK | OK | OK, with notices | OK, with notices |
| Weak copyleft | OK | Usually OK if unmodified | Review (linking, modified files) | Usually OK |
| Strong copyleft | OK | Usually OK (no distribution) | Blocker | Check compatibility with project license |
| Network copyleft | Review | High | Blocker | Check compatibility with project license |
| Source-available / restricted | Review terms | Often a blocker | Review terms | Review terms |
| Content `NC` / `ND` | Review (business use may count as commercial) | Review | Blocker if commercial | Review |
| Unknown | Blocker until clarified | Blocker until clarified | Blocker until clarified | Blocker until clarified |

**Rules to apply, and to double-check against the current license texts before relying on them:**

- Dev, build, and test tools usually are not shipped in the product, so they carry lower risk. Still list them, and confirm they are not bundled into the output.
- `GPL-2.0-only` code and `Apache-2.0` code cannot be combined in one distributed work; `GPL-3.0` can include `Apache-2.0` code. `GPL-2.0-only` and `GPL-3.0-only` cannot be combined with each other, but `-or-later` variants can.
- `LGPL` is usually manageable through dynamic linking where users can replace the library. Static linking, or bundling in mobile apps and firmware, is a frequent source of problems; flag it for review.
- `AGPL` matters for hosted services even when nothing is distributed.
- Creative Commons licenses are not designed for software; for icons, images, and fonts they are normal, but check the specific variant.
- Stack Overflow content is licensed under CC BY-SA, which requires attribution and share-alike. Code copied from it is a finding.
- A project's own license limits what it can include. Check each dependency against the project license, not against a generic "safe list".

### Step 4: Check obligations

Compliance is not only about blockers. For every component that is allowed, list what is owed and whether the repo already does it:

- License text and copyright notices included with distributed copies.
- `NOTICE` content carried over (Apache-2.0).
- Attribution shown where required (CC-BY assets, some icon sets).
- Source code or an offer of it (copyleft).
- Modifications marked as such, where the license asks for it.
- A third-party notices file or an in-app "licenses" screen exists and is current.

Compare against what is actually present (`THIRD_PARTY_NOTICES*`, `NOTICE`, an about/licenses page). Missing attribution is usually a quick fix and still counts as a finding.

### Step 5: Recommend remediation

For every finding above Info, give a concrete next step. Prefer these, roughly in order:

1. **Clarify**: ask the maintainer or vendor to state the license, or find the missing license text. Best for Unknown.
2. **Document**: add the missing attribution, notices file, or provenance record.
3. **Change version**: move to a version under a compatible license, if one exists. Check that version's license, not just its number.
4. **Replace**: swap in an alternative with a compatible license. Verify the alternative's license with the same process; never recommend a replacement on reputation alone.
5. **Isolate**: separate the component (for example, run it as a separate process or service) to change how the license applies. This is a legal-structure decision; always mark it "needs legal review".
6. **Buy or negotiate**: obtain a commercial license, or an extended font/icon license.
7. **Remove**: drop the component if it is unused or cheap to replace.
8. **Change the project's license or distribution plan**: only when the other options are worse; flag it as a decision for the owner.

Rank findings: **Blocker** (cannot ship as planned), **High** (likely non-compliant or restricted), **Medium** (obligation missing or needs review), **Low** (minor or dev-only), **Info** (no action).

## Output format

Write the report in Markdown with these sections, in this order. Keep the summary short; put detail in the tables.

```
# License Audit Report

## Summary
Counts by severity, the top 3 issues, and an overall statement (e.g. "Not ready to ship as closed-source: 2 blockers").

## Context and assumptions
Project license, distribution model, commercial use, scope, what was and was not audited,
any assumption made because the user did not answer.

## Coverage
Checked: the manifests, lockfiles, and asset locations that were inspected.
Not checked: locations or ecosystems skipped, and why. Also external services (API/SaaS terms) if used.

## Inventory
| Component | Version | Type | Scope | License (SPDX) | Confidence | Evidence |
Scope = runtime | dev | bundled. Evidence = file path or source consulted.

## Findings
| # | Severity | Component | Issue | Why it matters in this context |

## Obligations
What is owed per component, and whether the repo already satisfies it.

## Recommendations
Per finding: the recommended action from Step 5, an alternative if one exists, and effort (low/medium/high).

## Unverified and limitations
Everything marked Declared or Unverified, anything that could not be checked and why,
and a note that this is not legal advice.
```

Save the report as `LICENSE-AUDIT.md` (or the path the user names) when you can write files. Otherwise print it in full. If the inventory is long, group permissive components compactly and expand only the ones that need attention.

## Gotchas

- **Manifest `license` fields can be wrong, stale, or missing.** Prefer the license file; report mismatches.
- **A lockfile is the source of truth for versions.** A manifest with ranges like `^1.2.0` does not tell you what is installed.
- **Bundled sub-components.** A package under a permissive license can ship third-party code under a different one. Check `NOTICE` files and bundled license files.
- **Workspaces and monorepos.** Audit each package; a root manifest alone misses most dependencies.
- **License changes between versions.** Some widely used projects moved from open-source to source-available licenses in later releases (Elasticsearch in 2021 and HashiCorp products in 2023 are well-known examples). Check the version in use, and flag version bumps that cross such a change.
- **CDN versus self-hosted.** The license applies in both cases. Self-hosting a font or script means you are redistributing it, which may add obligations.
- **Unpinned installs.** `apt install foo` or `pip install bar` in a Dockerfile or CI script resolves to whatever version is current at build time. Record the component as "unpinned" and note that its license may differ between builds.
- **Minified and generated files** often keep their license only in a header comment. Read it before assuming there is none.
- **Do not trust a familiar name.** Whether a font, icon pack, or library "is free" is exactly the kind of claim that needs a file to back it up.

## When to stop and ask

Stop and ask the user, rather than guessing, when:

- the distribution model or project license is unknown and changes the verdict,
- a component's license cannot be determined and no source of evidence exists locally,
- two licenses conflict on the same component,
- the user's goal (for example, "make it open source later") would change the assessment.
