# Agent Skills

A collection of modular skills for AI coding agents.

---

## 🚀 Overview

**Agent Skills** provide structured, domain-specific capabilities for AI coding assistants and autonomous agents. Each skill packages specialized expertise, decision trees, and operational workflows into a portable folder format using **progressive disclosure**:

1. **Discovery:** Agents read lightweight metadata (name and description) at startup without filling the context window.
2. **Activation:** When a user prompt matches a skill's triggers or goals, the agent loads the full instructions (`SKILL.md`).
3. **Execution:** The agent follows step-by-step procedures, consults bundled reference materials, and executes tasks deterministically.

---

## 📦 Available Skills

| Skill | Version | Compatibility | Description | Docs |
|---|---|---|---|---|
| [`license-audit`](skills/license-audit/SKILL.md) | `0.1.0` | Offline-first | Audits third-party dependency and asset licenses, checks compatibility against project distribution models, identifies copyleft/IP risks, and generates actionable remediation reports. | [Guide](skills/license-audit/README.md) |
| [`code-to-business-flow`](skills/code-to-business-flow/SKILL.md) | `0.1.0` | Python 3.8+ (stdlib) | Reverse-engineers application source code into business flows, user journeys, status lifecycles, and business rules with evidence tags and Mermaid diagrams. | [Guide](skills/code-to-business-flow/README.md) |

---

## 📂 Repository Structure

```text
agent-skills/
├── LICENSE
├── README.md
└── skills/
    ├── code-to-business-flow/
    │   ├── README.md
    │   ├── SKILL.md
    │   ├── assets/
    │   │   ├── report-template.html
    │   │   └── report-template.md
    │   ├── references/
    │   │   └── discovery-signals.md
    │   └── scripts/
    │       ├── render_report.py
    │       ├── scan_repo.py
    │       └── validate_report.py
    └── license-audit/
        ├── README.md
        └── SKILL.md
```

---

## 🛠️ Installation & Usage

You can install skills directly into your project or agent environment using the `skills` CLI:

```bash
# Install all skills from this repository
npx skills add sepsarip/agent-skills

# Or install a specific skill
npx skills add sepsarip/agent-skills --skill license-audit
npx skills add sepsarip/agent-skills --skill code-to-business-flow
```

---

### 💬 Using a Skill

Once installed, your agent will discover the skill automatically based on your prompt:

**License Compliance Audit:**
> *"Audit the third-party licenses in this repository and prepare a compliance report."*
>
> *(Activates `license-audit`)*

**Business Flow Reverse-Engineering:**
> *"Explain the business flow of this repository and generate a visual journey report."*
>
> *(Activates `code-to-business-flow`)*

---

## 🧩 Adding a New Skill

Each skill resides in its own directory under `skills/<skill-name>/`:

```text
skills/<skill-name>/
├── SKILL.md          # Core skill definition and workflow (required)
├── README.md         # Human-readable guide and usage documentation (recommended)
├── scripts/          # Helper scripts executable by the agent (optional)
└── references/       # Additional documentation or templates (optional)
```

### `SKILL.md` Specification

Every skill must define YAML frontmatter followed by structured Markdown instructions:

```markdown
---
name: your-skill-name
description: Clear, concise description of when and how the agent should use this skill.
compatibility: Environment requirements or prerequisites. (optional)
metadata: (optional)
  version: "0.1.0"
---

# Skill Name

Brief overview of the skill's purpose and scope.

## Principles
Core operational rules the agent must adhere to.

## Workflow
Step-by-step execution phases:
- Step 0: Establish context
- Step 1: Discover inputs
- Step 2: Process & validate
- Step 3: Present results
```

---

## 🤝 Contributing

Contributions are welcome! If you'd like to add a new skill or improve existing ones:

1. Fork the repository.
2. Create your feature branch (`git checkout -b skill/my-new-skill`).
3. Follow the `SKILL.md` specification and test with your agent.
4. Submit a Pull Request.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
