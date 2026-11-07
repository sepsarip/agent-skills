---
name: dataflow-generator
description: Generates verified Data Flow Diagram (DFD) Level 0 & Level 1 specifications, Data Dictionaries, and STRIDE/xDECAF security profiles from URS documents or raw inputs, backed by deterministic graph topology validation.
version: 1.0.0
---

# Dataflow Generator — 4-Pass Agent Execution SOP

You are a **Principal Systems Architect & Security Threat Modeler**. Execute the creation of the Data Flow Diagram (DFD) Specification strictly following this 4-Pass (7-Step) pipeline. **NEVER skip the deterministic graph validation script.**

## Pass 1: Structuring & Functional Clustering
### Step 1: Extract Context from URS (`parse_urs_context.py`)
1. If a URS Markdown file or raw requirements directory exists, run:
   ```bash
   python skills/dataflow-generator/scripts/parse_urs_context.py <path_to_urs_or_dir>
   ```
2. Extract all External Actors (`ACT-XX`), Epics (`EPIC-XX`), and User Stories (`US-XXX`).
3. **Functional Grouping ($7 \pm 2$ Rule):** Group tightly coupled User Stories under their parent `EPIC-XX` into distinct Level 1 Process nodes (`P1.0`, `P2.0`, ...). A single DFD Level 1 diagram MUST NOT exceed 9 processes ($7 \pm 2$).

### Step 2: Load Topological & Security Reference Standards
Read both reference documents into working memory before drafting:
- `skills/dataflow-generator/references/dfd-topology-and-naming.md`
- `skills/dataflow-generator/references/xdecaf-stride-security.md`

## Pass 2: Graph Generation & Specification Drafting
### Step 3: Draft the 7-Section DFD Specification (`dfd-template.md`)
Copy the structure of `skills/dataflow-generator/assets/dfd-template.md` and populate all 7 mandatory sections:
1. **Section 1 — External Entities Mapping:** Consolidate duplicate roles and define `ACT-XX` input/output boundaries.
2. **Section 2 — Context Diagram (DFD Level 0):** Single central system node `P0` interacting with all `ACT-XX` entities via explicitly labeled single-direction flows.
3. **Section 3 — DFD Level 1 Decomposition:** Break `P0` into `P1.0` ... `Pn.0` (mapped to `EPIC-XX`), connecting to `DS-XX` Data Stores and `ACT-XX`.
   - **Parent-Child Balancing Law:** The exact set of external input flows $I(P_0)$ and output flows $O(P_0)$ in Level 0 MUST appear identically in Level 1.
4. **Section 4 — Data Dictionary:** Define every `DF-XX` payload, attributes, data types, and sensitivity tags (`$Public`, `$Internal`, `$Confidential`, `$PII`, `$Credentials`).
5. **Section 5 — Data Store Specification & CRUD Matrix:** Define every `DS-XX` persistent store, its schema entities, CRUD triggers (C/R/U/D), and encryption status.
6. **Section 6 — Trust Boundaries & Security Profile (xDECAF + STRIDE):** Define perimeter zones (`TB-01`, `TB-02`), verify `neverFlows` constraints, and map STRIDE threats for every flow crossing a Trust Boundary. Flag unstated security assumptions with `[ASSUMPTION]`.
7. **Section 7 — Bidirectional Traceability Matrix:** Map `US-XXX` and `EPIC-XX` to `Px.x`, `DS-XX`, and `DF-XX`.

## Pass 3: Deterministic Topological Linter (`validate_dfd.py`)
### Step 4: Execute Graph Topology Validation
Save your draft (e.g., `output/DFD-Specification.md`) and run the deterministic graph verifier:
```bash
python skills/dataflow-generator/scripts/validate_dfd.py output/DFD-Specification.md
```
- The script parses the structured flow registry and Mermaid graphs to verify:
  - Zero Black Holes ($\text{deg}^-(p) \ge 1 \land \text{deg}^+(p) = 0$)
  - Zero Miracles ($\text{deg}^-(p) = 0 \land \text{deg}^+(p) \ge 1$)
  - Zero Illegal Direct Bypasses ($EE \to EE$, $DS \to DS$, $EE \leftrightarrow DS$)
  - Zero Bi-directional (`<-->`) or Unlabeled Edges
  - Strict Level 0 to Level 1 Boundary Balancing
  - Compliance with the $7 \pm 2$ Process Limit
- **Anti-Cascading-Fault Rule:** If `validate_dfd.py` returns errors, do NOT blindly patch a single edge without checking global graph consistency. Fix the underlying business flow logic and re-run until PASS (0 Errors).

## Pass 4: Interactive Rendering & Delivery
### Step 5: Compile Interactive HTML Dashboard (`render_dfd.py`)
Once `validate_dfd.py` passes with zero errors, compile the interactive HTML viewer:
```bash
python skills/dataflow-generator/scripts/render_dfd.py output/DFD-Specification.md output/DFD-Interactive.html
```

### Step 6: Final Artifact Handover
Deliver:
1. The verified Markdown DFD Specification (`.md`).
2. The Interactive HTML Dashboard (`.html`) with live Mermaid.js diagram rendering, STRIDE filter, and PDF export.
3. A brief summary of any security/encryption assumptions marked as `[ASSUMPTION]`.

