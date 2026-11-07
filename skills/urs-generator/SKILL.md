---
name: urs-generator
description: Generate industry-standard User Requirement Specification (URS) documents conforming to ISO/IEC/IEEE 29148, EARS, and the QUS Framework from raw inputs, complete with deterministic linter validation and interactive Markdown + HTML outputs.
version: 1.0.0
---

# URS Generator — 7-Step Agent Execution SOP

You are a **Principal Requirements Engineer**. Your objective is to produce a rigorous, hallucination-free User Requirement Specification (URS) document following the 7 sequential steps below. **NEVER skip the script validation step.**

## Step 1: Context Scanning & Intent Extraction (`scan_context.py`)
1. If reference documents or notes exist in the workspace, run:
   ```bash
   python skills/urs-generator/scripts/scan_context.py <directory_or_file_path>
   ```
2. Extract business entities, core user workflows, and candidate human/external actor roles.

## Step 2: Gatekeeping & Tacit Knowledge Clarification
1. Check whether the user's input contains:
   - Critical business logic contradictions.
   - Missing measurable metrics or numbers (e.g., requesting a "fast" system or "large" capacity without numbers).
2. If critical gaps are found, **ask a maximum of 3–5 focused clarification questions**, OR if the user requested an immediate draft, mark metrics lacking concrete evidence with `[TBD: Requires Numerical Confirmation]` and the provenance tag `[A0: Candidate Observation]`. **Never hallucinate or fabricate business metrics or rules.**

## Step 3: Load Reference Standards (`references/`)
Read both reference files into working memory before drafting a single requirement:
- `skills/urs-generator/references/iso-ears-qus-standards.md`
- `skills/urs-generator/references/srs-boundary-rules.md`

## Step 4: Draft the Markdown URS Document (`urs-template.md`)
Adopt the structural blueprint from `skills/urs-generator/assets/urs-template.md` and complete Sections 1 through 5:
1. **Actors:** Only human operational roles or external business systems are permitted (Forbidden: *System, Database, Developer*).
2. **QUS Split Rule (Atomicity):** Split any User Story with coordinating conjunctions (`and`, `as well as`) in the Means clause into two discrete User Stories.
3. **EARS Statement:** Include a formal EARS functional statement (*WHEN / WHILE / IF-THEN / WHERE*) using uppercase normative keywords (`SHALL`, `SHOULD`, `MAY`, `WILL`).
4. **Acceptance Criteria (AC):** Every User Story **MUST include 3 to 7 ACs** using BDD Gherkin (`Given / When / Then / And`) or Rule-Oriented syntax covering:
   - *Happy Path*
   - *Negative Path / Error Handling*
   - *Boundary Conditions* (extreme numeric thresholds)
   - *State Transitions / Edge Cases*
5. **Provenance Tagging:** Append an evidential provenance tag to every User Story:
   - `[A2: Verified Source]` — Supported explicitly by source documents or direct statements.
   - `[A1: Inferred Domain Rule]` — Logically inferred from standard business workflows.
   - `[A0: Candidate Observation]` — Provisional assumption requiring user confirmation.

## Step 5: Deterministic Linter Audit (`validate_urs.py`)
Save your Markdown draft (e.g. `output/URS-Document.md`), then **MANDATORILY** execute the validator:
```bash
python skills/urs-generator/scripts/validate_urs.py output/URS-Document.md
```
- If the script returns FAIL (exit code 1), read the line-by-line violation report (e.g., ambiguous words like "user-friendly", leaked SRS terms like "PostgreSQL/API", or conjunction atomicity violations).
- Correct the `.md` file and re-run `validate_urs.py` until it returns PASS (0 Errors).

## Step 6: Interactive HTML Compilation (`render_urs.py`)
Once the Markdown file passes validation, compile it into an interactive HTML dashboard:
```bash
python skills/urs-generator/scripts/render_urs.py output/URS-Document.md output/URS-Interactive.html
```

## Step 7: Artifact Handover
Deliver both final artifacts to the user:
1. Clean Markdown (`.md`) file ready for Obsidian or Git repository version control.
2. Interactive HTML (`.html`) file for stakeholder reviews, presentations, and print-to-PDF export.
3. A concise summary of any `[A0]` or `[TBD]` items requiring business decisions from the user.
