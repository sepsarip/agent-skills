# Pitch Deck Generator Skill

Transform raw startup ideas, PRDs, or application repositories into high-density, investor-ready 10–12 slide pitch decks grounded in **Sequoia Capital**, **Y Combinator (YC)**, and **DocSend** empirical benchmarks.

## 📌 Overview

Founders and developers often struggle to translate technical products or raw ideas into compelling venture capital narratives—falling into traps like text walls, top-down market hallucinations (*"1% of a $50B market"*), or generic *"Proprietary AI"* moat claims.

The `pitch-deck-generator` skill solves this by enforcing a disciplined, evidence-backed storytelling workflow. Every metric, market calculation, and claim carries an explicit provenance tag (`[VERIFIED]`, `[BOTTOMS-UP]`, or `[FOUNDER-INPUT]`), producing both a **Marp-compatible Markdown deck** and a **self-contained interactive HTML slide deck** complete with speaker notes and visual diagrams.

## 🚀 Key Features

* **Adaptive Intake (Guided vs. Direct)**: Automatically interviews beginners using plain-language questions (*The Bar Test*) or directly ingests PRDs/repositories for power users.
* **VC Red-Flag Guardrails**: Programmatically prevents the 8 deadly pitch deck sins (passive titles, text walls >45 words, top-down TAM hallucinations, "no competitors" claims, and missing milestones).
* **Provenance-Backed Claims**: Every metric is tagged as `[VERIFIED]`, `[BOTTOMS-UP]`, or `[FOUNDER-INPUT]` so founders know exactly which numbers are factual, calculated, or require real-world validation.
* **Flexible Output Formats**: Selectable upfront based on presentation needs:
  * `deck.md`: Marp-ready Markdown slide deck following `assets/deck-template.md` for VS Code preview, Git version control, and PDF/PPTX export.
  * `deck.html`: Self-contained interactive HTML presentation with keyboard navigation (`←`/`→`), toggleable speaker notes drawer (`S`), slide overview grid (`G`), fullscreen mode (`F`), and live Mermaid diagrams.
  * `Both`: Produces both deliverables (default when unstated).
* **Standard Library Tooling**: Bundled Python scripts run purely on Python 3.8+ standard library—zero `pip install` or Node.js dependencies required.
* **Host Safety**: Designed for clean execution inside sandboxed environments without host machine pollution.

## 📂 Skill Architecture

```text
skills/pitch-deck-generator/
├── SKILL.md                          # Agent instructions, trigger definitions & rules
├── README.md                         # Human-readable documentation & script guide
├── assets/
│   ├── deck-template.md              # 12-slide Marp Markdown structural template
│   └── deck-template.html            # Interactive HTML presentation shell
├── references/
│   └── vc-benchmarks.md              # Sequoia, YC, and DocSend rules & red-flag playbook
└── scripts/
    ├── scan_context.py               # Workspace/PRD/repo signal scanner
    ├── validate_deck.py              # Slide density, structure, and VC red-flag validator
    └── render_deck.py                # Markdown-to-interactive HTML slide deck compiler
```

## 🔄 The 8-Step Workflow

When an agent activates this skill, it executes the following structured workflow:

1. **Scope, Mode & Format Selection**: Detect input maturity (Guided Interview vs. Direct Ingestion), target language (`en` or `id`), and deliverable format (`deck.md`, `deck.html`, or `Both`).
2. **Scan Workspace Context**: If run inside a project directory, execute `scan_context.py` to harvest product descriptions, READMEs, pricing configs, and technical architecture signals.
3. **Conduct Guided Discovery (If Needed)**: Ask up to 2 plain-language questions at a time to establish Problem, ICP, Why Now, Bottoms-Up Market math, Moat, and The Ask.
4. **Consult VC Benchmarks**: Load `references/vc-benchmarks.md` to enforce 1:1 Problem-Solution mirroring, Action Titles, and dynamic traction placement (Slide 2 if ARR ≥ $1M).
5. **Draft Pitch Deck**: Populate `deck.md` based on `assets/deck-template.md` across the standard 10–12 VC slides with mandatory `<!-- _notes: ... -->` speaker scripts.
6. **Validate Deck**: Run `validate_deck.py` to enforce slide count (10–12), visual word density (≤45 words/slide), Action Title formatting, absence of VC red flags, and zero unreplaced `{{placeholders}}`.
7. **Render Interactive HTML**: When HTML or Both is requested, run `render_deck.py` to compile `deck.md` into a standalone interactive `deck.html` presentation.
8. **Handover**: Present output file path(s), summarize key narrative strengths, and list unresolved `[FOUNDER-INPUT]` items requiring founder verification before pitching.

## 🏷️ Provenance & Evidence Rules

To eliminate hallucinated traction or fantasy financials, all quantitative claims and market statements must carry one of three explicit tags:

| Tag | Definition | Required Evidence |
| :--- | :--- | :--- |
| `[VERIFIED]` | Fact directly provided by the founder, PRD, or repository codebase. | Exact metric, feature, or citation from user input/repo. |
| `[BOTTOMS-UP]` | Market size or financial forecast derived via unit math. | Explicit formula (`Target ICP Count × ACV` or `Users × Price`). |
| `[FOUNDER-INPUT]` | Crucial business metric not yet known or provided by the user. | Expressed as a concrete placeholder metric to confirm before pitching. |

## 📊 Slide & Visual Conventions

* **Action Titles**: Every slide heading (`##`) must state a declarative takeaway (e.g., `## Problem: Manual Compliance Costs Mid-Market Banks $4.2B Annually`), never a passive label (`## Problem`).
* **High Density (Skim Test)**: Visual body text must stay ≤ 45 words per slide (excluding tables, Mermaid blocks, and speaker notes) to pass the 2m40s DocSend investor skim test.
* **1:1 Problem-Solution Mirroring**: The 3 pain points on the Problem slide must be directly mirrored by 3 corresponding outcomes on the Solution slide.
* **Product Workflow Diagram**: Slide 6 uses a clean `flowchart LR` (maximum 6 nodes) showing Input ➡️ Core Engine ➡️ Customer Outcome.
* **Speaker Notes**: Every slide must include a `<!-- _notes: ... -->` block containing a 20–30 second spoken pitch script and delivery tip.

## 🛠️ Bundled Scripts

All scripts are located in `scripts/` and run using Python 3.8+ standard library:

### 1. `scan_context.py`
Scans a target project directory or documentation folder for READMEs, package manifests, docs, and product signals.

```bash
python3 skills/pitch-deck-generator/scripts/scan_context.py /path/to/project --output /tmp/context.json
```

**Options:**
* `--output FILE`: Output destination (`-` for stdout).
* `--max-files N`: Maximum markdown/config files to inspect (default: 30).

### 2. `validate_deck.py`
Validates slide count, visual word density, speaker notes, provenance tags, and checks against banned VC red-flag phrases.

```bash
python3 skills/pitch-deck-generator/scripts/validate_deck.py deck.md
```

**Checks:**
* Verifies slide count is between 10 and 12 slides.
* Enforces visual word limit (≤ 45 words per slide, excluding tables/diagrams/notes).
* Confirms every slide contains an Action Title and a `<!-- _notes: ... -->` speaker script.
* Flags banned VC red flags ("no competitors", "1% of", "proprietary AI" without data/workflow context).
* Detects unreplaced `{{placeholder}}` markers.

### 3. `render_deck.py`
Compiles `deck.md` into a standalone interactive `deck.html` slide deck with keyboard navigation, speaker notes drawer, and print-to-PDF support.

```bash
python3 skills/pitch-deck-generator/scripts/render_deck.py deck.md --output deck.html --lang en
```

**Options:**
* `--output FILE`: Destination HTML file (required).
* `--lang en|id`: UI language for controls and badge legends (default: `en`).

## 📋 Compatibility & Requirements

* **Runtime**: Python 3.8+ (standard library only, zero external pip packages).
* **Environment Isolation**: Execute all bundled scripts inside the sandbox environment whenever available.
* **Viewing Presentations**:
  * `deck.html` opens directly in any modern browser (`←`/`→` to navigate, `S` for speaker notes, `F` for fullscreen, `Ctrl+P` / `Cmd+P` to save as PDF).
  * `deck.md` is 100% compatible with the Marp for VS Code extension and `@marp-team/marp-cli`.
