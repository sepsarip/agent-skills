# 📋 URS Generator Skill (ISO/IEC/IEEE 29148 + EARS + QUS)

Automated agent skill to transform raw meeting notes, transcripts, or product ideas into hallucination-free, measurable, and deterministically validated **User Requirement Specification (URS)** documents following industry standards.

## ✨ Key Features
- **Strict Problem-Domain Boundary:** Rejects technical solution leakage (SQL, REST API, JSON, internal architecture, framework names) that belongs in the SRS.
- **Triple-Standard Syntax:** Combines **ISO 29148**, **EARS** (*Easy Approach to Requirements Syntax*), and **QUS** (*Quality User Story*) + **BDD Gherkin**.
- **Evidential Grounding ($A_0 \rightarrow A_2$):** Traces every requirement claim back to source evidence to suppress hallucination rates below 10%.
- **Deterministic Python Linter:** Validates User Story atomicity, bans ambiguous qualitative qualifiers (*fast, user-friendly, robust*), and checks passive pronouns automatically.
- **Dual Output:** Generates clean Markdown (`.md`) (ready for Obsidian/Git) and an interactive HTML dashboard (`.html`) (complete with actor filters, verification status badges, and print-to-PDF).

## 🚀 How to Use
1. Place raw notes, interview transcripts, or project briefs in your workspace.
2. Prompt your agent: *"Use the `urs-generator` skill to draft a URS document from these project notes."*
3. The agent will run context scanning, ask targeted clarifications for missing numerical metrics, draft the URS, validate it with `validate_urs.py`, and compile the interactive HTML viewer.
