# 🔄 Dataflow Generator Skill (Yourdon/DeMarco + xDECAF + STRIDE)

An autonomous agent skill that transforms **User Requirement Specifications (URS)** or raw requirements into mathematically verified **Data Flow Diagram (DFD) Specifications** (Level 0 Context Diagram, Level 1 Epic Decompositions, Data Dictionary, Data Store CRUD Matrix, and STRIDE Security Threat Model).

## ✨ Key Features
- **Deterministic URS-to-DFD Translation:** Directly maps `ACT-XX` to External Entities, `EPIC-XX` / `US-XXX` to Processes, and persistent business objects to `DS-XX` Data Stores.
- **Process Explosion Guardrail ($7 \pm 2$ Rule):** Enforces functional clustering per Epic so no DFD Level 1 diagram exceeds 9 processes.
- **Graph-Theoretic Linter (`validate_dfd.py`):** Models DFD as a directed multi-graph $G=(V,E)$ to automatically detect and block:
  - *Black Holes* ($\text{deg}^-(p) \ge 1 \land \text{deg}^+(p) = 0$)
  - *Miracles / Spontaneous Generation* ($\text{deg}^-(p) = 0 \land \text{deg}^+(p) \ge 1$)
  - *Illegal Component Bypasses* ($EE \to EE$, $DS \to DS$, $EE \leftrightarrow DS$)
  - *Parent-Child Balancing Violations* (Level 0 vs. Level 1 boundary flow mismatch)
  - *Bi-directional or Unlabeled Flows*
- **xDECAF & STRIDE Security Profile:** Maps Trust Boundaries (`TB-XX`), data sensitivity classifications (`$PII`, `$Confidential`, `$Credentials`), `neverFlows` policies, and STRIDE mitigations.
- **Dual Output:** Clean `.md` (with native Mermaid.js diagrams for Obsidian/GitHub) and an interactive `.html` visual dashboard.

