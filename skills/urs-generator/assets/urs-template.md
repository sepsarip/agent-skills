---
document_id: URS-{{PROJECT_CODE}}-001
project_name: "{{PROJECT_NAME}}"
version: "1.0.0"
date: "{{DATE}}"
standard: "ISO/IEC/IEEE 29148 + EARS + QUS"
---

# User Requirement Specification (URS): {{PROJECT_NAME}}

## 1. Introduction

### 1.1 Document Purpose
{{Describe the purpose of this URS document and its intended audience}}

### 1.2 System Scope
{{Describe the business problem domain addressed by the system and high-level business goals (Business Goals: BG-01, BG-02)}}

### 1.3 Definitions, Acronyms, & Glossary
| Term / Acronym | Business Domain Definition |
| :--- | :--- |
| **{{Term 1}}** | {{Definition}} |

---

## 2. General Description

### 2.1 Actor Profiles & Persona Roles
| Actor ID | Role Name | Actor Category | Business Responsibilities |
| :--- | :--- | :--- | :--- |
| **ACT-01** | `{{Human Role Name}}` | Primary Human Actor | {{Description}} |

### 2.2 Operational Assumptions & Dependencies
- **ASM-01:** {{External operational condition assumed to hold}} `[A1: Inferred Domain Rule]`

### 2.3 Business & Environmental Constraints
- **CON-01:** {{Regulatory, legal compliance, or organizational policy constraint}} `[A2: Verified Source]`

---

## 3. User Requirements Specification (User Requirements & User Stories)

### 3.1 Core User Workflows (Epics)
- **EPIC-01:** {{Core User Workflow Name 1}}
- **EPIC-02:** {{Core User Workflow Name 2}}

### 3.2 User Stories, EARS Statements & Acceptance Criteria

#### [US-001] {{Discrete Feature Title}}
- **Epic:** EPIC-01
- **Business Goal:** BG-01
- **Provenance Status:** `[A2: Verified Source]` *(Use A2, A1, or A0)*
- **Canonical User Story:**
  > **As a** `<Role>`, **I want to** `<Single Action + Object>`, **so that** `<Pure Business Rationale>`.
- **EARS Functional Statement:**
  > **WHEN** `<Trigger/Condition>`, the `<System Name>` **SHALL** `<Action>` `<Object>` `<Measurable Constraint>`.
- **Acceptance Criteria:**
  - **AC-001.1 (Happy Path):**
    ```gherkin
    Given <specific verified precondition>
    When <Actor executes single action>
    Then <System produces observable outcome with measurable parameters>
    And <additional state transition or notification>
    ```
  - **AC-001.2 (Negative Path / Error Handling):**
    ```gherkin
    Given <specific verified precondition>
    When <Actor supplies invalid input or fails authorization>
    Then <System rejects action and displays clear business error message>
    ```
  - **AC-001.3 (Boundary Condition):**
    - **[IF / WHEN]** `<parameter is exactly at boundary threshold X>`, **THEN** `<measurable system response>`.
  - **AC-001.4 (Edge Case / State Transition):**
    - **[IF / WHEN]** `<connection interrupted or session expires>`, **THEN** `<measurable system recovery response>`.

---

## 4. User-Centric Non-Functional Requirements (NFRs)

| NFR ID | Quality Category | EARS-Based Measurable Requirement Statement | Provenance Status |
| :--- | :--- | :--- | :--- |
| **NFR-01** | Availability | The `{{System Name}}` **SHALL** maintain operational accessibility for `{{Actor}}` during `{{99.5%}}` of business hours per calendar month. | `[A0: Candidate Observation]` |
| **NFR-02** | Performance SLA | **WHEN** `{{Actor}}` submits a search query, the `{{System Name}}` **SHALL** display the results within `{{2.0}}` seconds. | `[A2: Verified Source]` |
| **NFR-03** | Security & Privacy | **IF** an unauthenticated user attempts to access restricted business records, **THEN** the `{{System Name}}` **SHALL** block access and redirect to the login page within `{{1.0}}` second. | `[A1: Inferred Domain Rule]` |
| **NFR-04** | Explainability | **WHEN** the `{{System Name}}` rejects a transaction, the `{{System Name}}` **SHALL** display the exact business rule violation reason to the `{{Actor}}`. | `[A1: Inferred Domain Rule]` |

---

## 5. Requirements Traceability Matrix

| User Story ID | Requirement Title | Epic ID | Business Goal | Primary Actor | Provenance | Verification Method |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **US-001** | {{Title}} | EPIC-01 | BG-01 | ACT-01 | `A2` | BDD Automated / UAT |
