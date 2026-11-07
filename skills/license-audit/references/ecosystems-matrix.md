# Ecosystem License Detection & Manifest Reference

This reference documents where license evidence is declared and stored across modern software ecosystems, including package managers, lockfile schemas, and non-package digital assets.

---

## 1. Supported Ecosystem Matrix

| Ecosystem | Manifest / Lockfile | Primary License Location | Special Characteristics & Gotchas |
|---|---|---|---|
| **JavaScript / TypeScript (npm, pnpm, yarn)** | `package.json`<br>`package-lock.json`<br>`pnpm-lock.yaml`<br>`yarn.lock` | `node_modules/<pkg>/package.json` (`license` field)<br>`node_modules/<pkg>/LICENSE*` | Lockfile v2/v3 carries `packages` map with license fields. Some lockfiles omit licenses entirely; verify against installed `package.json` or license file. |
| **Python** | `pyproject.toml`<br>`poetry.lock`<br>`Pipfile.lock`<br>`requirements*.txt`<br>`uv.lock` | `*.dist-info/METADATA`<br>License files in site-packages | Modern packaging supports PEP 639 `License-Expression`. Legacy uses Trove Classifiers or `License` header. Lockfiles rarely store license data. |
| **PHP (Composer)** | `composer.json`<br>`composer.lock` | `composer.lock` (`license` array)<br>`vendor/<pkg>/LICENSE*` | `composer.lock` is authoritative and typically includes a `license` array for every package. |
| **Rust (Cargo)** | `Cargo.toml`<br>`Cargo.lock` | Crate `Cargo.toml` (`license` or `license-file`)<br>Crate `LICENSE*` files | `Cargo.lock` holds checksums and versions, not license data. Check downloaded crate sources in Cargo cache. |
| **Go** | `go.mod`<br>`go.sum` | `vendor/` directory or module cache `LICENSE*` | `go.sum` contains cryptographic hashes only. Inspect `vendor/` or cache files. |
| **JVM (Java / Kotlin)** | `pom.xml`<br>`build.gradle(.kts)`<br>`gradle/libs.versions.toml`<br>`gradle.lockfile` | Artifact `.pom` (`<licenses>`) in Maven/Gradle cache<br>Embedded `META-INF/LICENSE*` inside JAR | Maven POM contains structured `<licenses>` tags. A JAR may also package third-party code in `META-INF/`. |
| **.NET / C#** | `*.csproj`<br>`packages.config`<br>`packages.lock.json` | `.nuspec` license metadata in NuGet cache | NuGet packages declare licenses in `.nuspec` via `<license type="expression">` or `<licenseUrl>`. |
| **Dart / Flutter** | `pubspec.yaml`<br>`pubspec.lock` | `LICENSE` file in pub cache | Pub packages must include a top-level `LICENSE` file. |
| **Ruby** | `Gemfile`<br>`Gemfile.lock` | Installed gem's `.gemspec` (`licenses` array)<br>Gem root `LICENSE*` | `Gemfile.lock` does not include license metadata. Inspect gemspec or gem installation path. |
| **iOS / macOS (CocoaPods / SPM)** | `Podfile.lock`<br>`Package.resolved` | `Pods/` directory license files<br>DerivedData checkouts | CocoaPods generates `Pods/Target Support Files/Pods-<App>/Pods-<App>-acknowledgements.markdown`. |
| **Containers** | `Dockerfile`<br>`docker-compose.yml` | Base image `FROM` declaration<br>OS package manager databases (`/var/lib/dpkg/status`, `/lib/apk/db/installed`) | Base OS images contain hundreds of packages. `RUN apt-get` installs unpinned versions unless pinned with `=<version>`. |
| **C / C++** | `vcpkg.json`<br>`conanfile.txt`<br>`CMakeLists.txt`<br>`Makefile` | Package cache or vendored source checkouts | Often vendored directly in `third_party/` or fetched via CMake `FetchContent`. Check header comments (`/* SPDX-License-Identifier: ... */`). |
| **Elixir / Erlang** | `mix.exs`<br>`mix.lock`<br>`rebar.config` | `deps/<pkg>/hex_metadata.config`<br>`deps/<pkg>/LICENSE*` | Hex packages list licenses in `hex_metadata.config`. |
| **Infrastructure as Code** | Terraform `*.tf`<br>Helm `Chart.yaml`<br>Ansible `requirements.yml` | Provider / module source repository licenses<br>Images referenced in Helm templates | Terraform providers and Helm charts often run third-party container images under different licenses. |
| **CI / CD Actions** | `.github/workflows/*.yml`<br>GitLab CI / Bitbucket Pipelines | Repositories referenced in `uses: <owner>/<repo>@<ref>` | GitHub Actions are distributed third-party software running in your build environment. |
| **Git Submodules** | `.gitmodules` | Submodule checkout directory `LICENSE*` | If submodules are uninitialized (`git submodule update --init`), local license files will be missing. |

---

## 2. Python Package Resolution Deep-Dive (PEP 639 & Trove Classifiers)

Modern Python packaging uses multiple metadata standards. When auditing Python dependencies, evaluate license sources in this priority order (the **Mixed Strategy**):

1. **PEP 639 `License-Expression`**:
   - Modern `pyproject.toml` specification supporting canonical SPDX expressions.
   - Example in `pyproject.toml`:
     ```toml
     [project]
     name = "example-package"
     license = "MIT OR Apache-2.0"
     license-files = ["LICENSE*"]
     ```
   - In `dist-info/METADATA`:
     ```text
     License-Expression: MIT OR Apache-2.0
     ```
2. **Trove Classifiers**:
   - Standard PyPI categorization headers inside `pyproject.toml` or `METADATA`.
   - Iterates lines starting with `Classifier: License ::`:
     ```text
     Classifier: License :: OSI Approved :: MIT License
     Classifier: License :: OSI Approved :: Apache Software License
     ```
   - Strip `Classifier: License :: OSI Approved ::` or `Classifier: License ::` to isolate the canonical identifier.
3. **Legacy `License` Metadata Header**:
   - Often contains informal text (e.g., `License: Apache 2.0`, `License: BSD`, or `License: see LICENSE file`).
   - Treat as `Declared` confidence; normalize to SPDX.

---

## 3. Node.js & npm Resolution Deep-Dive

In npm environments, inspect `package-lock.json` v2/v3:
- In lockfile v2/v3, inspect the root `packages` object:
  ```json
  "packages": {
    "node_modules/debug": {
      "version": "4.3.4",
      "resolved": "https://registry.npmjs.org/debug/-/debug-4.3.4.tgz",
      "integrity": "sha512-...",
      "license": "MIT",
      "dependencies": { "ms": "2.1.2" }
    }
  }
  ```
- If the lockfile was generated by an older npm version (lockfile v1), it may lack `license` fields. Fall back to reading `node_modules/<pkg>/package.json` directly.
- **Pattern Match Markers**: When an identifier is inferred from pattern matching against a license file rather than an explicit manifest declaration, record it with a trailing asterisk or note (e.g. `MIT*` or `Confidence: Declared`).

---

## 4. Non-Package Digital Assets (Fonts, Icons, Media)

Audits often miss assets that lack formal package manifests. The audit must explicitly inspect:

### 4.1 Fonts
- File extensions: `.woff`, `.woff2`, `.ttf`, `.otf`, `.eot`.
- CSS declarations: `@font-face { font-family: '...'; src: url('...'); }`.
- External font services: `fonts.googleapis.com`, `use.typekit.net`.
- Common licenses:
  - **OFL-1.1 (SIL Open Font License)**: Permissive for bundling and web usage; prohibits selling the font on its own; requires retaining copyright and reserved font names.
  - **Commercial Font EULAs**: Restrict pageviews/month, app embedding, server embedding, or desktop usage.

### 4.2 Icons & SVG Sprites
- Bundled icon libraries: FontAwesome, Lucide, Heroicons, Material Icons, Bootstrap Icons.
- Notice: Code vs. asset split! FontAwesome's webfont and SVGs are under **CC-BY-4.0** or commercial Pro licenses, while its code wrapper is under **MIT**.
- Inline SVG files and icons directories (`assets/icons/`, `public/images/`).

### 4.3 CDN Includes & URL Imports
- HTML `<script>` and `<link>` tags pointing to CDNs: `cdnjs.cloudflare.com`, `cdn.jsdelivr.net`, `unpkg.com`.
- Dynamic JavaScript URL imports: `import ... from "https://esm.sh/..."`.
- Self-hosting an asset formerly served via CDN transitions the activity from third-party hosting to **redistribution**, triggering notice and attribution obligations.

### 4.4 Inlined Base64 Data URIs
- CSS and HTML files may embed fonts and graphics directly as base64 strings.
- Search patterns: `data:font/`, `data:image/`, `data:application/font`, and `base64,`.
- Trace origin of inlined assets to confirm licensing provenance.

