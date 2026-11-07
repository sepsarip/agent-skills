# ISO 29148, EARS, QUS Framework Standards & 7 Anti-Patterns

## 1. Functional Requirement Syntax Patterns (ISO 29148 & EARS)
Every system requirement statement must use active voice, specific nouns, and normative capitalized keywords:
- **`SHALL`**: Mandatory, verifiable system requirement.
- **`SHOULD`**: Recommended feature that is desired but non-fatal if omitted.
- **`MAY`**: Optional behavior or extension.
- **`WILL`**: Statement of future fact/context, not a testable requirement.

### 5 EARS Patterns (Easy Approach to Requirements Syntax)
1. **Ubiquitous (Always Active):** `The <System Name> SHALL <Action> <Object> <Measurable Constraint>.`
2. **Event-Driven:** `WHEN <Specific Trigger/Event>, the <System Name> SHALL <Action> <Object> <Constraint>.`
3. **State-Driven:** `WHILE <Specific State/Condition>, the <System Name> SHALL <Action> <Object> <Constraint>.`
4. **Unwanted Behavior (Error Handling):** `IF <Invalid Condition/Fault>, THEN the <System Name> SHALL <Action> <Object>.`
5. **Optional Feature:** `WHERE <Feature is Enabled>, the <System Name> SHALL <Action> <Object>.`

---

## 2. Canonical User Story Formula (QUS Standard)
Mandatory syntax:
> **As a** `<Specific Human/Business Role>`, **I want to** `<Single Action Verb + Direct Object>`, **so that** `<Pure Business Value/Rationale>`.

---

## 3. Acceptance Criteria Format (3–7 ACs per User Story)
Use **BDD Gherkin** for behavioral flows:
```gherkin
Given <verified initial state with specific nouns>
When <single action executed by explicit Actor>
Then <externally observable outcome with measurable parameters>
And <additional state transition or notification>
```

Use **Rule-Oriented** syntax for boundary validations:
- **[IF / WHEN]** `<measurable condition>`, **THEN** `<exact observable system response with threshold>`.

---

## 4. 15-Point Quality Checklist (QUS + ISO 29148)

1. **Well-Formed**: Clear Role and Means clauses.
2. **Atomic**: Exactly 1 discrete capability per story (free of coordinating conjunctions like `and`, `as well as` in the Means clause).
3. **Minimal**: Free of implementation notes or bracketed technical comments.
4. **Conceptually Sound**: The End clause (`so that`) contains pure business value, not hidden prerequisite features.
5. **Problem-Oriented**: Free of SRS technical jargon.
6. **Unambiguous**: Free of vague qualitative descriptors; all performance goals have numerical metrics.
7. **Conflict-Free**: No logical contradictions across user stories.
8. **Full Sentence**: Complete grammatically correct sentences.
9. **Estimatable**: Specific enough to evaluate implementation scope.
10. **Unique**: No duplicate requirements.
11. **Uniform**: Consistent formatting throughout the document.
12. **Independent**: No hidden operational coupling with the execution order of other stories.
13. **Complete**: Covers end-to-end user workflows.
14. **Verifiable**: Has clear pass/fail observable conditions.
15. **Evidentially Grounded**: Carries a provenance status tag (`[A0]`, `[A1]`, or `[A2]`).

---

## 5. 7 Strictly Forbidden Anti-Patterns

1. **Ungrounded Claims (Hallucinated Numbers):** Inventing numerical limits without source evidence. (Remedy: Tag with `[TBD]` + `[A0]`).
2. **Solution-Oriented Bias:** Referencing databases, APIs, libraries, or architectural patterns.
3. **Atomicity Violation:** Joining two distinct user actions with `and` / `as well as`.
4. **Implicit Dependency Injection:** Sneaking secondary capabilities into the `so that...` clause.
5. **Non-User Role:** Writing `As a System` / `Developer` / `DB Admin`.
6. **Vague Qualifiers:** Using subjective terms: *fast, user-friendly, secure, robust, efficient, seamless, appropriate, as soon as possible, optimal* without numerical benchmarks.
7. **Pronoun & Passive Ambiguity:** Using vague pronouns (*it, he, she, they, this, that*) or passive constructions that obscure who performs the action.
