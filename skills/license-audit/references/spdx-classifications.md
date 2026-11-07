# SPDX Classifications & License Compatibility Reference

This reference provides canonical SPDX 2.3/3.0 identifier classifications, compound expression rules, and distribution model compatibility matrices.

---

## 1. SPDX Identifier Categorization

| Category | Typical SPDX Identifiers | Key Rights & Core Obligations |
|---|---|---|
| **Permissive** | `MIT`, `Apache-2.0`, `BSD-2-Clause`, `BSD-3-Clause`, `ISC`, `0BSD`, `Zlib`, `PostgreSQL` | Free commercial use, modification, and redistribution. Requires retaining copyright notices and original license text. `Apache-2.0` also includes explicit patent grant and `NOTICE` file retention. |
| **Public Domain Equivalent** | `CC0-1.0`, `Unlicense`, `WTFPL` | Dedicated to the public domain with minimal or no conditions. Ensure dedication is legally effective in target jurisdictions. |
| **Weak Copyleft** | `LGPL-2.1-only`, `LGPL-2.1-or-later`, `LGPL-3.0-only`, `LGPL-3.0-or-later`, `MPL-2.0`, `EPL-2.0`, `CDDL-1.0` | Modifications to covered library files must be released under same license. Applications linking to covered library (dynamically) usually do not become subject to copyleft. |
| **Strong Copyleft** | `GPL-2.0-only`, `GPL-2.0-or-later`, `GPL-3.0-only`, `GPL-3.0-or-later` | Derivative and combined works distributed to third parties must be licensed in full under the same GPL version. Source code must be made available. |
| **Network Copyleft** | `AGPL-3.0-only`, `AGPL-3.0-or-later`, `SSPL-1.0` | Extends copyleft triggers to network interactions (SaaS). If users interact with the software over a network, corresponding complete source code must be provided. |
| **Source-Available / Restricted** | `BUSL-1.1`, `Elastic-2.0`, `PolyForm-*`, `Commons-Clause` | Not OSI-approved open source. Imposes field-of-use restrictions, often forbidding competing commercial SaaS offerings or monetized hosting. |
| **Content & Media** | `CC-BY-4.0`, `CC-BY-SA-4.0`, `CC-BY-NC-4.0`, `CC-BY-ND-4.0`, `OFL-1.1` | Tailored for media, fonts, documentation. `SA` requires share-alike (copyleft); `NC` prohibits commercial use; `ND` prohibits modifications. |
| **Proprietary / Custom** | `Proprietary`, EULAs, commercial seat licenses | Governed strictly by negotiated contract terms. Check allowed domains, platforms, seat limits, and redistribution clauses. |

---

## 2. Compound SPDX Expressions & Operators

Modern package manifests use compound SPDX expressions to express dual-licensing or conditional grants.

### 2.1 Operators Grammar
- **`A OR B` (Disjunctive Choice)**:
  - The licensee may select either license terms.
  - *Example*: `MIT OR Apache-2.0`. A proprietary project may choose `MIT` or `Apache-2.0`.
  - When auditing: Document which branch of the `OR` the project selects.
- **`A AND B` (Conjunctive Combination)**:
  - Both licenses apply simultaneously. The licensee must satisfy obligations for both.
  - *Example*: `LGPL-2.1-only AND BSD-3-Clause`.
  - Incompatibility check: If `A` and `B` cannot legally co-exist in a single binary, `A AND B` is a critical blocker.
- **`WITH <exception-id>` (License Exception)**:
  - Modifies the base license to relax specific requirements.
  - Treat the license + exception as an atomic unit (e.g. `Apache-2.0 WITH LLVM-exception` or `GPL-2.0-or-later WITH Classpath-exception-2.0`).
  - *Example*: The `Classpath-exception-2.0` allows independent modules to link to the library without triggering the GPL copyleft requirement on the independent code.
- **`+` Suffix (Forward Compatibility)**:
  - Indicates that the terms of the stated version or any later version published by the licensor may be used.
  - Canonical SPDX replaces `GPL-2.0+` with `GPL-2.0-or-later`.

---

## 3. Compatibility Matrix by Distribution Model

Evaluate each dependency's classification against the project's distribution scenario:

| Category | Internal Tool Only | Hosted Service (SaaS) | Distributed Binary / App (Closed Source) | Distributed Open Source |
|---|:---:|:---:|:---:|:---:|
| **Permissive** (`MIT`, `Apache-2.0`) | ✅ OK | ✅ OK | ✅ OK (retain notices) | ✅ OK (retain notices) |
| **Weak Copyleft** (`LGPL`, `MPL`) | ✅ OK | ✅ OK (if unmodified) | ⚠️ Review linking (dynamic vs static) | ✅ Usually OK |
| **Strong Copyleft** (`GPL`) | ✅ OK | ✅ OK (no distribution) | ⛔ **Blocker** (forces source disclosure) | ⚠️ Check license alignment |
| **Network Copyleft** (`AGPL`) | ⚠️ Review | ⛔ **High Risk** (network trigger) | ⛔ **Blocker** | ⚠️ Check license alignment |
| **Source-Available** (`BUSL`, `SSPL`) | ⚠️ Review terms | ⛔ Often Blocker | ⚠️ Review terms | ⚠️ Incompatible with OSS |
| **Content `NC` / `ND`** | ⚠️ Review | ⚠️ Review | ⛔ **Blocker** (if commercial/modified) | ⚠️ Restricts downstream use |
| **Unknown / Unlicensed** | ⛔ **Blocker** | ⛔ **Blocker** | ⛔ **Blocker** | ⛔ **Blocker** |

---

## 4. High-Stakes Incompatibilities & Critical Gotchas

### 4.1 GPL-2.0-only vs. Apache-2.0 Incompatibility
- `GPL-2.0-only` is legally incompatible with `Apache-2.0`.
- **Reason**: Apache-2.0 contains patent termination provisions and indemnification clauses that the Free Software Foundation considers "further restrictions" forbidden by GPL-2.0 Section 6.
- **Resolution**: `GPL-3.0` is compatible with `Apache-2.0`. If a GPL-2.0 dependency permits `GPL-2.0-or-later`, the combination can be distributed under `GPL-3.0`. If strictly `GPL-2.0-only`, they cannot be combined into a single distributed binary.

### 4.2 LGPL Dynamic vs. Static Linking
- **Dynamic Linking (`.so`, `.dll`, `.dylib`)**: Allowed in closed-source software provided the end user can replace the LGPL library with a modified version (e.g. via dynamic linker path or relinking).
- **Static Linking**: In closed-source desktop, mobile apps (iOS App Store), or embedded firmware, static linking combines the proprietary code and LGPL code into an inseparable binary. This requires providing object files (`.o`) to allow relinking, which is often commercially or technically unfeasible. Flag static LGPL linking as a **Blocker** or **High Risk**.

### 4.3 AGPL in Microservices and Backends
- Even if no compiled binary is downloaded by end users, running an `AGPL-3.0` service that users interact with over a network triggers the source disclosure requirement for that service and any closely coupled modifications.
- Check whether communication occurs via clean network APIs (REST/gRPC across separate processes) or if code is directly linked into the core service.

### 4.4 Stack Overflow Code Snippets
- Code snippets published on Stack Overflow are licensed under **CC-BY-SA** (Creative Commons Attribution-ShareAlike).
- `CC-BY-SA` contains a copyleft share-alike clause incompatible with closed-source commercial licensing. Pasting non-trivial code snippets directly into proprietary codebases is a compliance finding.

