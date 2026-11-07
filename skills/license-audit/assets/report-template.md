# License Audit Report

## Summary
- **Overall Verdict**: [Ready to ship | Blocker identified | Review required]
- **Issue Counts**: [X] Blocker, [X] High, [X] Medium, [X] Low, [X] Info
- **Key Highlights**:
  - [Top issue 1: Component, license, and practical impact]
  - [Top issue 2: Component, license, and practical impact]
  - [Top issue 3: Component, license, and practical impact]

## Context and assumptions
- **Project License**: [e.g. Proprietary / Closed Source | MIT | Apache-2.0]
- **Distribution Model**: [e.g. Hosted SaaS / Network Service | Distributed Desktop/Mobile App | Library / SDK | Internal Only]
- **Commercial Intent**: [e.g. Commercial / Revenue Generating | Non-commercial]
- **Audit Scope**: [e.g. Production runtime only | Full repository including dev/build tools]
- **Assumptions**: [List any assumptions made due to unstated context, e.g. "Assumed closed-source commercial distribution as conservative baseline"]

## Coverage
- **Checked Ecosystems & Locations**:
  - [e.g. `package.json` & `package-lock.json` (npm runtime & dev)]
  - [e.g. `pyproject.toml` & `poetry.lock` (Python runtime)]
  - [e.g. `public/fonts/` (Web fonts)]
- **Skipped / Unchecked Locations & Services**:
  - [e.g. External SaaS APIs / Terms of Service (out of scope)]
  - [e.g. Transitive C++ build dependencies (unresolved)]

## Inventory
| Component | Version | Type | Scope | License (SPDX) | Confidence | Evidence |
|---|---|---|---|---|---|---|
| [example-pkg] | [1.0.0] | [npm] | [runtime] | [MIT] | [Verified] | [`node_modules/example-pkg/LICENSE`] |
| [sample-font] | [2.1] | [font] | [bundled] | [OFL-1.1] | [Declared] | [`public/fonts/FONTLOG.txt`] |

> **Confidence Legend**:
> - `Verified`: Read directly from an included license text or authoritative checksummed manifest.
> - `Declared`: Stated only in top-level manifest metadata without verifying accompanying license text.
> - `Unverified`: Inferred or unconfirmed; requires explicit human confirmation.
> - `Unknown`: Missing license information or unparseable terms. Treat as blocker until clarified.

## Findings
| # | Severity | Component | Issue | Why It Matters in This Context |
|---|---|---|---|---|
| 1 | [Blocker] | [component-name] | [GPL-3.0-only in closed-source app] | [Redistributing GPL code in proprietary binary forces release of entire source code.] |
| 2 | [Medium] | [component-name] | [Apache-2.0 missing NOTICE file] | [Apache-2.0 section 4(d) requires retaining original NOTICE file text.] |

> **Severity Scale**:
> - `Blocker`: Cannot ship or distribute as planned without severe IP/legal exposure.
> - `High`: Probable non-compliance or restrictive conditions requiring resolution.
> - `Medium`: Required compliance obligations unfulfilled (attribution, notices, modified files).
> - `Low`: Minor or dev/test-only tool licensing questions.
> - `Info`: Informational notice or clean license observations.

## Obligations
| Component | License (SPDX) | Required Obligations | Current Repository Status |
|---|---|---|---|
| [component-name] | [Apache-2.0] | Include original copyright, Apache-2.0 license text, and NOTICE file | [Missing NOTICE file in distribution bundle] |
| [component-name] | [MIT] | Include copyright notice and permission notice | [Satisfied in THIRD_PARTY_NOTICES.md] |

## Recommendations
| # | Finding Reference | Recommended Action | Alternative / Workaround | Effort |
|---|---|---|---|---|
| 1 | Finding #1 | [Replace dependency with permissive alternative (e.g. `foo`)] | [Isolate as an out-of-process microservice via REST/gRPC API] | [Medium] |
| 2 | Finding #2 | [Copy upstream NOTICE file to project `THIRD_PARTY_NOTICES.md`] | [None required] | [Low] |

## Unverified and limitations
- **Unverified Items**: [List all components marked `Declared` or `Unverified` and specific verification next steps.]
- **Legal Disclaimer**: This audit report represents an engineering and technical evaluation based on inspectable codebase metadata and license texts. It does not constitute formal legal counsel.

